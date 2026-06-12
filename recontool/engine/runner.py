"""Real execution bridge — makes the event-driven engine ALIVE (spec gap G1).

`make_execute_fn` returns the `execute_fn` the `ParallelExecutor` calls for every
scheduled job. It:

  1. resolves the tool to a runnable generic adapter (`engine.execution`),
  2. runs it against the job's inputs,
  3. persists the results via the `Normalizer` (idempotent dedupe into the DB —
     a re-discovered entity strengthens confidence, never duplicates),
  4. publishes `EntityDiscovered` for each new in-scope asset so the scheduler
     fans out downstream tools — this closes the recursion loop.

Non-runnable / unavailable / keyless tools return a clean no-op success (skipped),
so a scan over the full 563-tool registry runs whatever it actually can and keeps
going. `run_engine_scan` wires the whole thing (infra + registry + orchestrator).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

from recontool.adapters.base import AdapterContext
from recontool.core.artifacts import ArtifactStore
from recontool.core.db import session_scope
from recontool.core.scope import Scope
from recontool.engine.ai_decision import (
    AIDecisionService, decide_on_events, discarded_asset_pairs,
)
from recontool.engine.events import EntityDiscovered, EventBus
from recontool.engine.execution import build_adapter_for, plan_execution
from recontool.engine.executor import ExecutionResult
from recontool.engine.logging import EngineLogger
from recontool.engine.registry import ToolRegistry
from recontool.engine.scheduler import ScheduledJob
from recontool.normalize.engine import Normalizer

if TYPE_CHECKING:
    from recontool.engine.noise import NoiseFilter

logger = logging.getLogger(__name__)

ExecuteFn = Callable[[ScheduledJob], Awaitable[ExecutionResult]]


@dataclass
class ToolOutcome:
    """Result of running one tool spec against one set of inputs."""

    status: str          # "ok" | "skip" | "error"
    events: list = field(default_factory=list)
    reason: str = ""


async def run_tool_spec(
    spec, scan_id: str, inputs: dict, *,
    scope: Scope, profile: Any, http: Any,
    api_keys: dict, artifacts: ArtifactStore,
) -> ToolOutcome:
    """Build the generic adapter for a tool and run it once. Shared by the
    event-bus runner and the multi-worker queue (single source of execution)."""
    plan = plan_execution(spec)
    adapter_cls = build_adapter_for(spec) if plan.runnable else None
    if adapter_cls is None:
        return ToolOutcome("skip", reason=plan.reason or "not runnable")
    adapter = adapter_cls()
    ctx = AdapterContext(
        scan_id=scan_id, scope=scope, profile=profile, http=http,
        artifacts=artifacts, inputs=inputs or {}, api_keys=api_keys,
    )
    if not adapter.available(ctx):
        return ToolOutcome("skip", reason="unavailable (missing binary/key)")
    try:
        events = await adapter.run(ctx)
    except Exception as exc:  # noqa: BLE001
        return ToolOutcome("error", reason=str(exc)[:500])
    return ToolOutcome("ok", events=events or [])


def write_typed_outputs(store: ArtifactStore, tool: str, events: list) -> None:
    """Append discovered entities to typed out/<tool>.<type>.jsonl files (G7)."""
    by_type: dict[str, list[str]] = {}
    for ev in events:
        if ev.entity == "asset":
            by_type.setdefault(ev.data.get("type", "asset"), []).append(ev.data.get("value", ""))
        elif ev.entity == "endpoint":
            by_type.setdefault("url", []).append(ev.data.get("url", ""))
        elif ev.entity == "service":
            by_type.setdefault("service", []).append(
                f"{ev.data.get('host', '')}:{ev.data.get('port', '')}")
        elif ev.entity == "finding":
            by_type.setdefault("finding", []).append(ev.data.get("title", ""))
    for etype, vals in by_type.items():
        vals = [v for v in vals if v]
        if vals:
            store.save_typed(tool, etype, vals)


def discovered_assets(events: list) -> list[tuple[str, str]]:
    """Unique (entity_type, value) asset pairs from a tool's events."""
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for ev in events:
        if ev.entity != "asset":
            continue
        t, v = ev.data.get("type"), ev.data.get("value")
        if t and v and (t, v) not in seen:
            seen.add((t, v))
            out.append((t, v))
    return out


def make_execute_fn(
    bus: EventBus,
    registry: ToolRegistry,
    *,
    scope: Scope,
    profile: Any,
    http: Any,
    api_keys: Optional[dict[str, str | None]] = None,
    noise: Optional["NoiseFilter"] = None,
    persist: bool = True,
    ai_service: Optional[AIDecisionService] = None,
) -> ExecuteFn:
    """Build the execute_fn closure shared across all jobs in a scan.

    Artifacts are written under ``settings.artifact_dir``; set that (or
    ``RECON_ARTIFACT_DIR``) to redirect output, e.g. for tests. Pass ``noise`` to
    gate the re-feed path (G4); ``None`` (default) means no filtering. ``ai_service``
    overrides the default heuristic AI-decisioning layer.
    """
    api_keys = api_keys or {}
    _stores: dict[str, ArtifactStore] = {}
    ai = ai_service or AIDecisionService(scope=scope)
    elog = EngineLogger("recontool.engine")

    def _artifacts(scan_id: str) -> ArtifactStore:
        if scan_id not in _stores:
            _stores[scan_id] = ArtifactStore(scan_id)
        return _stores[scan_id]

    async def execute_fn(job: ScheduledJob) -> ExecutionResult:
        spec = registry.get(job.tool_name)
        if spec is None:
            return ExecutionResult(tool_name=job.tool_name, scan_id=job.scan_id,
                                   success=False, error="unknown tool")

        outcome = await run_tool_spec(
            spec, job.scan_id, job.inputs or {}, scope=scope, profile=profile,
            http=http, api_keys=api_keys, artifacts=_artifacts(job.scan_id),
        )
        if outcome.status == "skip":
            return ExecutionResult(tool_name=job.tool_name, scan_id=job.scan_id,
                                   success=True, error=f"skipped: {outcome.reason}")
        if outcome.status == "error":
            return ExecutionResult(tool_name=job.tool_name, scan_id=job.scan_id,
                                   success=False, error=outcome.reason)

        events = outcome.events
        # AI decisioning: classify entities before persisting/re-feeding so noise
        # never spawns downstream work; the decision is logged for visibility.
        dropped: set[tuple[str, str]] = set()
        if events:
            decision = decide_on_events(events, job.tool_name, service=ai)
            elog.log_ai_decision(job.scan_id, decision.reasoning, tool_name=job.tool_name)
            dropped = discarded_asset_pairs(decision)
            persist_events = decision.persist or events
            if persist:
                with session_scope() as s:
                    Normalizer(s, job.scan_id, scope=scope).ingest(persist_events)
            write_typed_outputs(_artifacts(job.scan_id), job.tool_name, persist_events)

        # Fan out: publish each unique discovered asset so the scheduler can
        # select tools that consume the new entity type (the recursion). The
        # optional noise gate (G4) drops dup / out-of-scope / wildcard / CDN
        # leads before they spawn more work.
        for etype, evalue in discovered_assets(events):
            if (etype, evalue) in dropped:
                continue  # AI decisioning flagged it as noise
            if noise is not None and not await noise.keep(job.scan_id, etype, evalue):
                continue
            elog.log_entity_discovered(job.scan_id, etype, evalue, tool_name=job.tool_name)
            await bus.publish(EntityDiscovered(
                scan_id=job.scan_id, entity_type=etype, entity_value=evalue,
                tool_name=job.tool_name,
            ))

        return ExecutionResult(tool_name=job.tool_name, scan_id=job.scan_id, success=True)

    return execute_fn


_API_KEY_ENVS = (
    "SHODAN_API_KEY", "VIRUSTOTAL_API_KEY", "SECURITYTRAILS_API_KEY",
    "GITHUB_TOKEN", "CENSYS_API_ID", "CENSYS_API_SECRET", "CHAOS_API_KEY",
    "NETLAS_API_KEY", "GREYNOISE_API_KEY", "LEAKIX_API_KEY",
    "URLSCAN_API_KEY", "FULLHUNT_API_KEY", "CRIMINALIP_API_KEY",
    "CERTSPOTTER_API_KEY", "IPINFO_TOKEN",
)


def build_scan_infra(seed: str, seed_type: str, profile_name: str | None):
    """Shared setup for both execution paths: (profile, scope, http, api_keys)."""
    from recontool.config import PROFILES, settings
    from recontool.core.scope import Scope as _Scope
    from recontool.net.http_client import HttpClient
    from recontool.net.proxy_pool import ProxyPool
    from recontool.net.rate_limiter import RateLimiter

    profile = PROFILES.get(profile_name, settings.profile()) if profile_name else settings.profile()
    scope = _Scope.from_seed(seed, seed_type)
    proxies = ProxyPool(settings.proxies, strategy=settings.proxy_strategy)
    limiter = RateLimiter(default_rate=profile.requests_per_second)
    # Per-provider QPS ceilings (compliance): keep each source under its published
    # limit so shared keys / many workers never collectively exceed it.
    for bucket, qps in settings.provider_rate_limits().items():
        limiter.configure(bucket, qps)
    http = HttpClient(profile=profile, proxy_pool=proxies, limiter=limiter)
    api_keys = {k: settings.api_key(k) for k in _API_KEY_ENVS}
    return profile, scope, http, api_keys


def build_noise(scope, noise_control: bool, wildcard_filter: bool):
    """Construct the optional NoiseFilter (or None when disabled)."""
    if not (noise_control or wildcard_filter):
        return None
    from recontool.engine.noise import NoiseConfig, NoiseFilter, build_default_resolver
    return NoiseFilter(
        scope=scope,
        config=NoiseConfig(enabled=True, wildcard=wildcard_filter),
        resolver=build_default_resolver() if wildcard_filter else None,
    )


def load_engine_registry(
    tools: str = "default",
    *,
    authorize_active: bool = False,
    registry: ToolRegistry | None = None,
) -> ToolRegistry:
    """Load the unified tool registry the engine runs against.

    Single source for every execution path (in-process engine + queue workers):
      1. load the catalogue (inventory + curated + generic specs),
      2. **bridge the hand-written Python adapters** in as runnable, routable
         tools (dns_resolve, httpx_probe, pycrawl, naabu fallback, …) so the
         recursion does not dead-end where no Go binary is installed,
      3. apply the tool profile + the passive/active gate.
    """
    from recontool.engine.adapters_bridge import register_python_adapters
    from recontool.engine.selection import apply_selection

    # Only bridge the hand-written adapters when WE load the catalogue. A caller
    # that supplies its own registry (e.g. a focused test) gets it used as-is.
    bridge = registry is None
    registry = registry or ToolRegistry.load()
    if bridge:
        register_python_adapters(registry)
    apply_selection(registry, tools, authorize_active=authorize_active)
    return registry


async def run_engine_scan(
    seed: str,
    *,
    seed_type: str = "domain",
    profile_name: str | None = None,
    registry: ToolRegistry | None = None,
    tools: str = "default",
    authorize_active: bool = False,
    noise_control: bool = False,
    wildcard_filter: bool = False,
    max_iterations: int = 50,
    max_depth: int = 3,
):
    """Run a single-process event-driven scan with real tool execution.

    Discovery fans out as soon as a tool's inputs are available, recurses on each
    new entity, and converges when no eligible tools remain. `tools` selects the
    profile ("default" curated vs "all"/"excessive"). Active tools (resolve /
    probe / port / crawl / vuln) only run when ``authorize_active`` is set.
    Returns a ScanResult.
    """
    from recontool.core.db import create_all
    from recontool.engine.orchestrator import EventDrivenOrchestrator, ScanConfig

    create_all()
    profile, scope, http, api_keys = build_scan_infra(seed, seed_type, profile_name)
    registry = load_engine_registry(
        tools, authorize_active=authorize_active, registry=registry
    )
    noise = build_noise(scope, noise_control, wildcard_filter)

    bus = EventBus()
    execute_fn = make_execute_fn(
        bus, registry, scope=scope, profile=profile, http=http,
        api_keys=api_keys, noise=noise,
    )
    orchestrator = EventDrivenOrchestrator(bus=bus, registry=registry, execute_fn=execute_fn)
    return await orchestrator.run_scan(
        seed, ScanConfig(seed=seed, seed_type=seed_type,
                         max_iterations=max_iterations, max_depth=max_depth),
    )
