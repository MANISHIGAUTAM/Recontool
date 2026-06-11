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
from typing import Any, Awaitable, Callable, Optional

from recontool.adapters.base import AdapterContext
from recontool.core.artifacts import ArtifactStore
from recontool.core.db import session_scope
from recontool.core.scope import Scope
from recontool.engine.events import EntityDiscovered, EventBus
from recontool.engine.execution import build_adapter_for, plan_execution
from recontool.engine.executor import ExecutionResult
from recontool.engine.registry import ToolRegistry
from recontool.engine.scheduler import ScheduledJob
from recontool.normalize.engine import Normalizer

logger = logging.getLogger(__name__)

ExecuteFn = Callable[[ScheduledJob], Awaitable[ExecutionResult]]


def make_execute_fn(
    bus: EventBus,
    registry: ToolRegistry,
    *,
    scope: Scope,
    profile: Any,
    http: Any,
    api_keys: Optional[dict[str, str | None]] = None,
    persist: bool = True,
) -> ExecuteFn:
    """Build the execute_fn closure shared across all jobs in a scan.

    Artifacts are written under ``settings.artifact_dir``; set that (or
    ``RECON_ARTIFACT_DIR``) to redirect output, e.g. for tests.
    """
    api_keys = api_keys or {}
    _stores: dict[str, ArtifactStore] = {}

    def _artifacts(scan_id: str) -> ArtifactStore:
        if scan_id not in _stores:
            _stores[scan_id] = ArtifactStore(scan_id)
        return _stores[scan_id]

    async def execute_fn(job: ScheduledJob) -> ExecutionResult:
        spec = registry.get(job.tool_name)
        if spec is None:
            return ExecutionResult(
                tool_name=job.tool_name, scan_id=job.scan_id,
                success=False, error="unknown tool",
            )

        plan = plan_execution(spec)
        adapter_cls = build_adapter_for(spec) if plan.runnable else None
        if adapter_cls is None:
            # documented stub / web-only / no contract — skip cleanly, keep scanning
            return ExecutionResult(
                tool_name=job.tool_name, scan_id=job.scan_id,
                success=True, error=f"skipped: {plan.reason or 'not runnable'}",
            )

        adapter = adapter_cls()
        ctx = AdapterContext(
            scan_id=job.scan_id, scope=scope, profile=profile, http=http,
            artifacts=_artifacts(job.scan_id), inputs=job.inputs or {},
            api_keys=api_keys,
        )
        if not adapter.available(ctx):
            return ExecutionResult(
                tool_name=job.tool_name, scan_id=job.scan_id,
                success=True, error="unavailable (missing binary/key)",
            )

        try:
            events = await adapter.run(ctx)
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(
                tool_name=job.tool_name, scan_id=job.scan_id,
                success=False, error=str(exc)[:500],
            )

        if persist and events:
            with session_scope() as s:
                Normalizer(s, job.scan_id, scope=scope).ingest(events)

        # Fan out: publish each unique discovered asset so the scheduler can
        # select tools that consume the new entity type (the recursion).
        seen: set[tuple[str, str]] = set()
        for ev in events:
            if ev.entity != "asset":
                continue
            etype, evalue = ev.data.get("type"), ev.data.get("value")
            if not etype or not evalue or (etype, evalue) in seen:
                continue
            seen.add((etype, evalue))
            await bus.publish(EntityDiscovered(
                scan_id=job.scan_id, entity_type=etype, entity_value=evalue,
                tool_name=job.tool_name,
            ))

        return ExecutionResult(
            tool_name=job.tool_name, scan_id=job.scan_id, success=True,
        )

    return execute_fn


async def run_engine_scan(
    seed: str,
    *,
    seed_type: str = "domain",
    profile_name: str | None = None,
    registry: ToolRegistry | None = None,
    max_iterations: int = 50,
    max_depth: int = 3,
):
    """Run a full event-driven scan with real tool execution.

    The complement to the linear ReconPipeline: discovery fans out as soon as a
    tool's inputs are available, recurses on each new entity, and converges when
    no eligible tools remain. Returns the orchestrator's ScanResult.
    """
    from recontool.config import PROFILES, settings
    from recontool.core.db import create_all
    from recontool.core.scope import Scope as _Scope
    from recontool.engine.orchestrator import EventDrivenOrchestrator, ScanConfig
    from recontool.net.http_client import HttpClient
    from recontool.net.proxy_pool import ProxyPool
    from recontool.net.rate_limiter import RateLimiter

    create_all()
    profile = PROFILES.get(profile_name, settings.profile()) if profile_name else settings.profile()
    scope = _Scope.from_seed(seed, seed_type)
    registry = registry or ToolRegistry.load()

    proxies = ProxyPool(settings.proxies, strategy=settings.proxy_strategy)
    limiter = RateLimiter(default_rate=profile.requests_per_second)
    http = HttpClient(profile=profile, proxy_pool=proxies, limiter=limiter)

    api_keys = {
        k: settings.api_key(k) for k in (
            "SHODAN_API_KEY", "VIRUSTOTAL_API_KEY", "SECURITYTRAILS_API_KEY",
            "GITHUB_TOKEN", "CENSYS_API_ID", "CENSYS_API_SECRET", "CHAOS_API_KEY",
            "NETLAS_API_KEY", "GREYNOISE_API_KEY", "LEAKIX_API_KEY",
            "URLSCAN_API_KEY", "FULLHUNT_API_KEY", "CRIMINALIP_API_KEY",
            "CERTSPOTTER_API_KEY", "IPINFO_TOKEN",
        )
    }

    bus = EventBus()
    execute_fn = make_execute_fn(
        bus, registry, scope=scope, profile=profile, http=http,
        api_keys=api_keys,
    )
    orchestrator = EventDrivenOrchestrator(bus=bus, registry=registry, execute_fn=execute_fn)
    return await orchestrator.run_scan(
        seed, ScanConfig(seed=seed, seed_type=seed_type,
                         max_iterations=max_iterations, max_depth=max_depth),
    )
