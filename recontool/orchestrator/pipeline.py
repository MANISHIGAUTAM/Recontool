"""Recon pipeline orchestrator.

Runs the phased flow from docs/D2-recon-flow.md:
  P1 seed -> P2 expansion -> P3 enrichment  -- [ACTIVE GATE] --  P4 verify -> P5 deep -> P6 vuln

Within a phase, adapters run in PARALLEL (asyncio). Between phases, freshly
discovered assets are read back from the DB and fed as inputs to the next phase
(tool chaining: one tool's output becomes another's input).

An optional AI supervisor is consulted at phase boundaries for runtime decisions
(recurse / skip / re-prioritize). Without it, deterministic defaults are used.
"""
from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select

from recontool.adapters.base import AdapterContext, Event
from recontool.adapters.registry import adapters_for, load_builtin
from recontool.config import settings
from recontool.core.artifacts import ArtifactStore
from recontool.core.db import create_all, session_scope
from recontool.core.mode import RunMode
from recontool.core.models import Asset, AuditLog, Checkpoint, DeadLetter, Scan
from recontool.core.scope import Scope, apex_domain, classify_seed
from recontool.net.http_client import HttpClient
from recontool.net.proxy_pool import ProxyPool
from recontool.net.rate_limiter import RateLimiter
from recontool.normalize.engine import Normalizer
from recontool.orchestrator.frontier import FrontierManager

PASSIVE_PHASES = ["p1_seed", "p2_expansion", "p3_enrichment"]
ACTIVE_PHASES = ["p4_verify", "p5_deep", "p6_vuln"]


def _cat_num(category: str) -> int:
    """Parse an adapter category string like 'CAT-2' -> 2 (0 if unknown)."""
    m = re.search(r"(\d+)", category or "")
    return int(m.group(1)) if m else 0


@dataclass
class PhaseResult:
    phase: str
    adapters_run: list[str] = field(default_factory=list)
    adapters_skipped: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    duration: float = 0.0
    note: str = ""


@dataclass
class ScanResult:
    scan_id: str
    seed: str
    seed_type: str
    profile: str
    mode: str = "live"
    phases: list[PhaseResult] = field(default_factory=list)
    active_ran: bool = False
    gate_reason: str = ""
    resumed: bool = False


class ReconPipeline:
    def __init__(self, supervisor=None, max_recursion: int = 1,
                 mode: RunMode | None = None, mock_env=None):
        self.supervisor = supervisor          # optional AI supervisor (duck-typed)
        self.max_recursion = max_recursion
        self.mode = mode or settings.run_mode
        self.mock_env = mock_env
        # Pipeline-level cache so in-memory backend persists across phases and runs
        from recontool.cache import ResultCache
        self._cache = ResultCache.create(settings.redis_url)

    async def run(
        self,
        seed: str,
        *,
        profile_name: str | None = None,
        authorize_active: bool = False,
        categories: set[int] | None = None,
        progress=None,
        stream=None,
        resume_scan_id: str | None = None,
    ) -> ScanResult:
        self._categories = categories          # None = run all categories
        self._emit = stream                    # live per-adapter event callback
        create_all()
        profile = settings.profile() if not profile_name else __import__(
            "recontool.config", fromlist=["PROFILES"]
        ).PROFILES.get(profile_name, settings.profile())

        seed_type = classify_seed(seed)
        scope = self._build_scope(seed, seed_type)

        # ── demo/test mode: stand up the in-process mock environment ────────
        mock_env = self.mock_env
        if self.mode.uses_mock and mock_env is None:
            from recontool.testing.mock_env import MockEnv
            apex = apex_domain(seed) if seed_type in ("domain", "subdomain", "url") else seed
            mock_env = MockEnv(apex=apex)

        # ── resume vs fresh scan ────────────────────────────────────────────
        resumed = bool(resume_scan_id)
        completed_phases: set[str] = set()
        if resumed:
            scan_id = resume_scan_id
            completed_phases = self._completed_phases(scan_id)
        else:
            scan_id = uuid.uuid4().hex[:16]

        # bind the scan_id as the trace id for all structured logs in this run
        from recontool.obs import log_event, set_trace_id
        set_trace_id(scan_id)
        log_event("scan.begin", seed=seed, seed_type=seed_type, mode=self.mode.value,
                  profile=profile.name, resumed=resumed)

        # shared infra for the whole scan
        proxies = ProxyPool(settings.proxies, strategy=settings.proxy_strategy)
        limiter = RateLimiter(default_rate=profile.requests_per_second)
        from recontool.net.circuit import BudgetLedger, CircuitRegistry
        circuits = CircuitRegistry(failure_threshold=5, cooldown=30.0)
        budget = BudgetLedger()
        http = HttpClient(profile=profile, proxy_pool=proxies, limiter=limiter,
                          mode=self.mode, mock_env=mock_env,
                          circuits=circuits, budget=budget)
        artifacts = ArtifactStore(scan_id)
        frontier = FrontierManager(scan_id, scope)

        api_keys = {
            k: settings.api_key(k) for k in
            ("SHODAN_API_KEY", "VIRUSTOTAL_API_KEY", "SECURITYTRAILS_API_KEY",
             "GITHUB_TOKEN", "CENSYS_API_ID", "CENSYS_API_SECRET", "CHAOS_API_KEY",
             "NETLAS_API_KEY", "GREYNOISE_API_KEY", "LEAKIX_API_KEY", "URLSCAN_API_KEY",
             "FULLHUNT_API_KEY", "CRIMINALIP_API_KEY", "CERTSPOTTER_API_KEY", "IPINFO_TOKEN")
        }

        with session_scope() as s:
            if not resumed:
                s.add(Scan(
                    id=scan_id, seed=seed, seed_type=seed_type, profile=profile.name,
                    status="running", scope_json=scope.to_json(), mode=self.mode.value,
                    active_authorized=authorize_active,
                ))
            else:
                scan = s.get(Scan, scan_id)
                if scan:
                    scan.status = "running"
            s.add(AuditLog(scan_id=scan_id, action="scan.resume" if resumed else "scan.start",
                           target=seed, profile=profile.name,
                           detail={"scope": scope.to_json(), "authorize_active": authorize_active,
                                   "mode": self.mode.value,
                                   "completed_phases": sorted(completed_phases)}))

        # Inject the SEED as the first canonical asset so it flows to adapters as
        # input (without this, the first phase has nothing to consume).
        if not resumed:
            self._seed_asset(scan_id, seed, seed_type, scope)
        else:
            frontier.seed_from_store()  # don't re-expand everything already persisted

        result = ScanResult(scan_id=scan_id, seed=seed, seed_type=seed_type,
                            profile=profile.name, mode=self.mode.value, resumed=resumed)
        load_builtin()

        def base_ctx(inputs: dict[str, list[str]]) -> AdapterContext:
            return AdapterContext(
                scan_id=scan_id, scope=scope, profile=profile, http=http,
                artifacts=artifacts, inputs=inputs, api_keys=api_keys,
            )

        # ── PASSIVE PIPELINE ────────────────────────────────────────────────
        recursion = 0
        while True:
            for phase in PASSIVE_PHASES:
                if phase in completed_phases:
                    continue  # resume: skip already-checkpointed phases
                inputs = self._gather_inputs(scan_id, scope, active=False)
                pr = await self._run_phase(phase, base_ctx(inputs), scan_id, progress)
                result.phases.append(pr)
                self._checkpoint(scan_id, phase, pr.counts, recursion)
            # Frontier-driven recursion: only recurse if NEW in-scope entities exist.
            frontier.new_in_scope()  # advance frontier past what we've seen
            if recursion >= self.max_recursion:
                break
            if not frontier.has_new():
                break
            # With a supervisor, let it veto further passes (cost control).
            if self.supervisor and not await self._ask_recurse(scan_id, result):
                break
            recursion += 1

        # ── ACTIVE GATE (mode + profile + authorization) ────────────────────
        if not self.mode.allows_real_egress and self.mock_env is None and not mock_env:
            result.gate_reason = f"mode '{self.mode.value}' has no live egress"
        if not profile.active_enabled:
            result.gate_reason = f"profile '{profile.name}' is passive-only"
        elif not authorize_active:
            result.gate_reason = "active scanning not authorized (--authorize-active required)"
        else:
            result.active_ran = True
            for phase in ACTIVE_PHASES:
                if phase in completed_phases:
                    continue
                inputs = self._gather_inputs(scan_id, scope, active=True)
                pr = await self._run_phase(phase, base_ctx(inputs), scan_id, progress)
                result.phases.append(pr)
                self._checkpoint(scan_id, phase, pr.counts, recursion)

        with session_scope() as s:
            scan = s.get(Scan, scan_id)
            if scan:
                scan.status = "done"
                import datetime as _dt
                scan.finished_at = _dt.datetime.now(_dt.timezone.utc)
            s.add(AuditLog(scan_id=scan_id, action="scan.finish",
                           detail={"active_ran": result.active_ran, "gate": result.gate_reason,
                                   "frontier": frontier.stats()}))
        return result

    # ── phase execution ──────────────────────────────────────────────────
    async def _run_phase(self, phase, ctx: AdapterContext, scan_id, progress) -> PhaseResult:
        t0 = time.time()
        pr = PhaseResult(phase=phase)
        classes = adapters_for(phase)
        instances = []
        cats = getattr(self, "_categories", None)
        for cls in classes:
            inst = cls()
            if cats is not None and _cat_num(getattr(cls, "category", "")) not in cats:
                continue  # --category filter: skip adapters outside the chosen set
            if inst.available(ctx):
                instances.append(inst)
            else:
                pr.adapters_skipped.append(inst.name)

        # AI supervisor may drop/keep adapters before running (token-cheap planning)
        if self.supervisor:
            keep = await self._ask_plan(phase, [i.name for i in instances], scan_id)
            if keep is not None:
                dropped = [i.name for i in instances if i.name not in keep]
                pr.adapters_skipped += dropped
                instances = [i for i in instances if i.name in keep]

        if progress:
            progress(phase, [i.name for i in instances], pr.adapters_skipped)

        # live per-adapter streaming: emit start/finish so long scans show progress
        emit = getattr(self, "_emit", None)

        # ── result cache: check for cached passive results ──────────────────
        from recontool.cache import hash_inputs
        cache = self._cache
        cache_ttl = settings.cache_ttl
        scope_hash = hash_inputs({}, ctx.scope.to_json() if hasattr(ctx.scope, "to_json") else {})
        input_hash = hash_inputs(ctx.inputs, {})

        cached_results: list[tuple[str, list[Event]]] = []
        to_run: list = []

        for inst in instances:
            # Only cache passive adapters
            if not getattr(inst, "is_active", False):
                cached = await cache.get(inst.name, input_hash, scope_hash)
                if cached is not None:
                    # Reconstruct Event objects from cached dicts
                    events = [
                        Event(
                            entity=e["entity"], tool=e["tool"],
                            data=e["data"], raw_ref=e.get("raw_ref"),
                        )
                        for e in cached
                    ]
                    cached_results.append((inst.name, events))
                    if emit:
                        emit("adapter_done", phase=phase, tool=inst.name,
                             events=len(events), duration=0.0)
                    from recontool.obs import log_event as _log
                    _log("adapter.cached", phase=phase, tool=inst.name, events=len(events))
                    continue
            to_run.append(inst)

        # ── Queue-based dispatch ────────────────────────────────────────────
        # For InMemoryQueue (default, no Redis): execute in-process with the
        # same asyncio.gather pattern. The queue abstraction is in place so
        # switching to RedisQueue with external workers is seamless.
        from recontool.queue import InMemoryQueue, RedisQueue, get_queue
        queue = get_queue(settings.redis_url)
        use_local_execution = isinstance(queue, InMemoryQueue)

        # PARALLEL fan-out across adapters in this phase
        async def run_one(inst):
            t_start = time.time()
            if emit:
                emit("adapter_start", phase=phase, tool=inst.name,
                     category=getattr(inst, "category", ""), active=getattr(inst, "is_active", False))
            from recontool.obs import log_event
            log_event("adapter.start", phase=phase, tool=inst.name)
            try:
                # per-adapter hard timeout so one slow live adapter can't hang the scan
                adapter_timeout = float(getattr(ctx.profile, "adapter_timeout", 0) or 180)
                events = await asyncio.wait_for(inst.run(ctx), timeout=adapter_timeout)
                dt = round(time.time() - t_start, 1)
                if emit:
                    emit("adapter_done", phase=phase, tool=inst.name,
                         events=len(events), duration=dt)
                log_event("adapter.done", phase=phase, tool=inst.name,
                          events=len(events), duration=dt)
                return inst.name, events
            except Exception as exc:  # noqa: BLE001
                dt = round(time.time() - t_start, 1)
                # park failed unit in the dead-letter queue for replay/inspection
                with session_scope() as s:
                    s.add(AuditLog(scan_id=scan_id, action="adapter.error",
                                   tool=inst.name, detail={"error": str(exc)[:500]}))
                    s.add(DeadLetter(scan_id=scan_id, phase=phase, tool=inst.name,
                                     error=str(exc)[:2000],
                                     payload={"category": getattr(inst, "category", "")}))
                if emit:
                    emit("adapter_error", phase=phase, tool=inst.name,
                         error=str(exc)[:200], duration=dt)
                log_event("adapter.error", level="ERROR", phase=phase,
                          tool=inst.name, error=str(exc)[:300])
                return inst.name, []

        if use_local_execution:
            # In-memory path: direct asyncio.gather (same behavior as before)
            sem = asyncio.Semaphore(ctx.profile.global_concurrency or 10)

            async def guarded(inst):
                async with sem:
                    return await run_one(inst)

            results = await asyncio.gather(*(guarded(i) for i in to_run))
        else:
            # Redis queue path: dispatch tasks and wait for results from workers
            results = await self._dispatch_via_queue(
                queue, to_run, phase, ctx, scan_id, emit,
            )

        await queue.close()

        all_events = []
        # Include cached results first
        for name, events in cached_results:
            pr.adapters_run.append(name)
            all_events.extend(events)

        for name, events in results:
            pr.adapters_run.append(name)
            all_events.extend(events)
            with session_scope() as s:
                s.add(AuditLog(scan_id=scan_id, action="adapter.run", tool=name,
                               egress_ip=ctx.http.last_egress, profile=ctx.profile.name,
                               detail={"events": len(events)}))
            # Cache successful passive adapter results
            if events and not any(
                getattr(inst, "is_active", False)
                for inst in instances if inst.name == name
            ):
                event_dicts = [
                    {"entity": e.entity, "tool": e.tool, "data": e.data, "raw_ref": e.raw_ref}
                    for e in events
                ]
                await cache.set(name, input_hash, scope_hash, event_dicts, cache_ttl)

        # NORMALIZE in batches of 2000 events to avoid one massive transaction
        BATCH_SIZE = 2000
        merged_counts: dict[str, int] = {}
        for i in range(0, max(len(all_events), 1), BATCH_SIZE):
            batch = all_events[i:i + BATCH_SIZE]
            if not batch:
                break
            with session_scope() as s:
                norm = Normalizer(s, scan_id, scope=ctx.scope)
                batch_counts = norm.ingest(batch)
                for k, v in batch_counts.items():
                    merged_counts[k] = merged_counts.get(k, 0) + v
        pr.counts = merged_counts

        pr.duration = round(time.time() - t0, 2)

        from recontool.obs import log_event
        log_event("phase.done", phase=phase, ran=pr.adapters_run,
                  skipped=pr.adapters_skipped, counts=pr.counts, duration=pr.duration)
        if getattr(self, "_emit", None):
            self._emit("phase_done", phase=phase, counts=pr.counts,
                       ran=len(pr.adapters_run), duration=pr.duration)

        # AI supervisor reviews the output of this phase
        if self.supervisor:
            try:
                pr.note = await self.supervisor.review_phase(phase, pr.counts, scan_id) or ""
            except Exception:  # noqa: BLE001
                pr.note = ""
        return pr

    async def _dispatch_via_queue(
        self, queue, instances, phase, ctx: AdapterContext, scan_id, emit,
    ) -> list[tuple[str, list[Event]]]:
        """Dispatch adapter tasks to Redis queue and collect results."""
        import uuid as _uuid

        task_ids: list[tuple[str, str]] = []  # (task_id, adapter_name)

        # Serialize the minimal context needed by remote workers.
        # NOTE: API keys are transmitted in plaintext via Redis. In production
        # deployments, secure Redis with TLS + AUTH or inject credentials into
        # workers via environment variables instead of task payloads.
        context_data = {
            "profile_name": ctx.profile.name,
            "inputs": ctx.inputs,
            "api_keys": {k: v for k, v in ctx.api_keys.items() if v},
            "scope_json": ctx.scope.to_json() if hasattr(ctx.scope, "to_json") else {},
        }

        for inst in instances:
            task_id = _uuid.uuid4().hex[:16]
            task_data = {
                "adapter_name": inst.name,
                "phase": phase,
                "scan_id": scan_id,
                "context_data": context_data,
            }
            if emit:
                emit("adapter_start", phase=phase, tool=inst.name,
                     category=getattr(inst, "category", ""),
                     active=getattr(inst, "is_active", False))
            await queue.enqueue(task_id, task_data)
            task_ids.append((task_id, inst.name))

        # Collect results concurrently (not sequentially) so fast adapters
        # are not blocked behind slow ones.
        results: list[tuple[str, list[Event]]] = []
        adapter_timeout = float(getattr(ctx.profile, "adapter_timeout", 0) or 180)

        async def _get_one(task_id: str, adapter_name: str) -> tuple[str, list[Event]]:
            result_data = await queue.get_result(task_id, timeout=adapter_timeout)
            if result_data is None:
                if emit:
                    emit("adapter_error", phase=phase, tool=adapter_name,
                         error="timeout waiting for worker result", duration=adapter_timeout)
                return (adapter_name, [])
            elif result_data.get("status") == "completed":
                event_dicts = result_data.get("result", {}).get("events", [])
                events = [
                    Event(
                        entity=e["entity"], tool=e["tool"],
                        data=e["data"], raw_ref=e.get("raw_ref"),
                    )
                    for e in event_dicts
                ]
                if emit:
                    emit("adapter_done", phase=phase, tool=adapter_name,
                         events=len(events), duration=0.0)
                return (adapter_name, events)
            else:
                error = result_data.get("error", "unknown error")
                if emit:
                    emit("adapter_error", phase=phase, tool=adapter_name,
                         error=error[:200], duration=0.0)
                return (adapter_name, [])

        results = list(await asyncio.gather(
            *(_get_one(tid, name) for tid, name in task_ids)
        ))

        return results

    # ── chaining: read discovered assets back as next-phase inputs ─────────
    def _seed_asset(self, scan_id, seed: str, seed_type: str, scope: Scope) -> None:
        """Write the seed into the canonical store so phase 1 has input to consume.
        For domain/url seeds we seed the APEX domain (recon targets the whole
        footprint), and also the original host if it differs."""
        events: list[Event] = []
        if seed_type in ("domain", "subdomain", "url"):
            apex = apex_domain(seed)
            events.append(Event.asset("seed", "domain", apex))
            host = seed.split("://")[-1].split("/")[0]
            if host and host != apex:
                events.append(Event.asset("seed", "subdomain", host))
        elif seed_type == "ip":
            events.append(Event.asset("seed", "ip", seed))
        elif seed_type == "cidr":
            events.append(Event.asset("seed", "cidr", seed))
        elif seed_type == "asn":
            events.append(Event.asset("seed", "asn", seed))
        else:
            events.append(Event.asset("seed", "domain", seed))
        with session_scope() as s:
            Normalizer(s, scan_id, scope=scope).ingest(events)

    def _gather_inputs(self, scan_id, scope: Scope, active: bool) -> dict[str, list[str]]:
        inputs: dict[str, list[str]] = {}
        with session_scope() as s:
            rows = s.execute(select(Asset).where(Asset.scan_id == scan_id)).scalars().all()
            for a in rows:
                if active and not a.in_scope:
                    continue
                inputs.setdefault(a.type, []).append(a.value)
            # also pass live endpoints as 'url' inputs for active phases
            if active:
                from recontool.core.models import Endpoint

                eps = s.execute(select(Endpoint).where(Endpoint.asset_id.in_(
                    select(Asset.id).where(Asset.scan_id == scan_id)
                ))).scalars().all()
                if eps:
                    urls = [e.url for e in eps]
                    # prefer live-probed http(s) endpoints for nuclei targets
                    inputs.setdefault("url", [])
                    inputs["url"].extend(urls[:2000])
        # dedupe
        return {k: sorted(set(v)) for k, v in inputs.items()}

    def _has_unprobed_growth(self, scan_id) -> bool:
        with session_scope() as s:
            n = s.execute(select(Asset).where(Asset.scan_id == scan_id)).scalars().all()
            return len(n) > 0

    # ── scope / checkpoint / resume helpers ─────────────────────────────────
    def _build_scope(self, seed: str, seed_type: str) -> Scope:
        """Seed-derived scope merged with the config-driven scope allowlist."""
        scope = Scope.from_seed(seed, seed_type)
        cfg = settings.scope_allowlist()
        scope.allow_domains |= set(cfg["allow_domains"])
        scope.allow_cidrs += [c for c in cfg["allow_cidrs"] if c not in scope.allow_cidrs]
        scope.allow_asns |= {a.upper() for a in cfg["allow_asns"]}
        scope.deny_domains |= set(cfg["deny_domains"])
        scope.deny_cidrs += [c for c in cfg["deny_cidrs"] if c not in scope.deny_cidrs]
        scope.__post_init__()
        return scope

    def _completed_phases(self, scan_id) -> set[str]:
        with session_scope() as s:
            rows = s.execute(
                select(Checkpoint.phase).where(
                    Checkpoint.scan_id == scan_id, Checkpoint.status == "done")
            ).scalars().all()
        return set(rows)

    def _checkpoint(self, scan_id, phase, counts, recursion) -> None:
        if not settings.recovery().get("checkpoint_enabled", True):
            return
        with session_scope() as s:
            existing = s.execute(
                select(Checkpoint).where(
                    Checkpoint.scan_id == scan_id, Checkpoint.phase == phase)
            ).scalar_one_or_none()
            if existing:
                existing.status = "done"
                existing.counts = counts
                existing.recursion = recursion
            else:
                s.add(Checkpoint(scan_id=scan_id, phase=phase, status="done",
                                 counts=counts, recursion=recursion))

    # ── supervisor hooks (no-op if absent) ─────────────────────────────────
    async def _ask_plan(self, phase, names, scan_id):
        if not self.supervisor or not hasattr(self.supervisor, "plan_phase"):
            return None
        try:
            return await self.supervisor.plan_phase(phase, names, scan_id)
        except Exception:  # noqa: BLE001
            return None

    async def _ask_recurse(self, scan_id, result) -> bool:
        if not self.supervisor or not hasattr(self.supervisor, "should_recurse"):
            return False
        try:
            return await self.supervisor.should_recurse(scan_id, result)
        except Exception:  # noqa: BLE001
            return False
