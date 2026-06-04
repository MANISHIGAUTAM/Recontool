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
import time
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select

from recontool.adapters.base import AdapterContext
from recontool.adapters.registry import adapters_for, load_builtin
from recontool.config import settings
from recontool.core.artifacts import ArtifactStore
from recontool.core.db import create_all, session_scope
from recontool.core.models import Asset, AuditLog, Scan
from recontool.core.scope import Scope, classify_seed
from recontool.net.http_client import HttpClient
from recontool.net.proxy_pool import ProxyPool
from recontool.net.rate_limiter import RateLimiter
from recontool.normalize.engine import Normalizer

PASSIVE_PHASES = ["p1_seed", "p2_expansion", "p3_enrichment"]
ACTIVE_PHASES = ["p4_verify", "p5_deep", "p6_vuln"]


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
    phases: list[PhaseResult] = field(default_factory=list)
    active_ran: bool = False
    gate_reason: str = ""


class ReconPipeline:
    def __init__(self, supervisor=None, max_recursion: int = 1):
        self.supervisor = supervisor          # optional AI supervisor (duck-typed)
        self.max_recursion = max_recursion

    async def run(
        self,
        seed: str,
        *,
        profile_name: str | None = None,
        authorize_active: bool = False,
        progress=None,
    ) -> ScanResult:
        create_all()
        profile = settings.profile() if not profile_name else __import__(
            "recontool.config", fromlist=["PROFILES"]
        ).PROFILES.get(profile_name, settings.profile())

        seed_type = classify_seed(seed)
        scope = Scope.from_seed(seed, seed_type)
        scan_id = uuid.uuid4().hex[:16]

        # shared infra for the whole scan
        proxies = ProxyPool(settings.proxies, strategy=settings.proxy_strategy)
        limiter = RateLimiter(default_rate=profile.requests_per_second)
        http = HttpClient(profile=profile, proxy_pool=proxies, limiter=limiter)
        artifacts = ArtifactStore(scan_id)

        api_keys = {
            k: settings.api_key(k) for k in
            ("SHODAN_API_KEY", "VIRUSTOTAL_API_KEY", "SECURITYTRAILS_API_KEY",
             "GITHUB_TOKEN", "CENSYS_API_ID", "CENSYS_API_SECRET", "CHAOS_API_KEY")
        }

        with session_scope() as s:
            s.add(Scan(
                id=scan_id, seed=seed, seed_type=seed_type, profile=profile.name,
                status="running", scope_json=scope.to_json(),
                active_authorized=authorize_active,
            ))
            s.add(AuditLog(scan_id=scan_id, action="scan.start",
                           target=seed, profile=profile.name,
                           detail={"scope": scope.to_json(), "authorize_active": authorize_active}))

        result = ScanResult(scan_id=scan_id, seed=seed, seed_type=seed_type, profile=profile.name)
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
                inputs = self._gather_inputs(scan_id, scope, active=False)
                pr = await self._run_phase(phase, base_ctx(inputs), scan_id, progress)
                result.phases.append(pr)
            # supervisor decides whether to recurse passive discovery
            if recursion >= self.max_recursion:
                break
            if self.supervisor and not await self._ask_recurse(scan_id, result):
                break
            recursion += 1
            if recursion > self.max_recursion:
                break
            # only recurse if there's genuinely new surface; else stop
            if not self._has_unprobed_growth(scan_id):
                break

        # ── ACTIVE GATE (ADR-009) ───────────────────────────────────────────
        if not profile.active_enabled:
            result.gate_reason = f"profile '{profile.name}' is passive-only"
        elif not authorize_active:
            result.gate_reason = "active scanning not authorized (--authorize-active required)"
        else:
            result.active_ran = True
            for phase in ACTIVE_PHASES:
                inputs = self._gather_inputs(scan_id, scope, active=True)
                pr = await self._run_phase(phase, base_ctx(inputs), scan_id, progress)
                result.phases.append(pr)

        with session_scope() as s:
            scan = s.get(Scan, scan_id)
            if scan:
                scan.status = "done"
                import datetime as _dt
                scan.finished_at = _dt.datetime.now(_dt.timezone.utc)
            s.add(AuditLog(scan_id=scan_id, action="scan.finish",
                           detail={"active_ran": result.active_ran, "gate": result.gate_reason}))
        return result

    # ── phase execution ──────────────────────────────────────────────────
    async def _run_phase(self, phase, ctx: AdapterContext, scan_id, progress) -> PhaseResult:
        t0 = time.time()
        pr = PhaseResult(phase=phase)
        classes = adapters_for(phase)
        instances = []
        for cls in classes:
            inst = cls()
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

        # PARALLEL fan-out across adapters in this phase
        async def run_one(inst):
            try:
                return inst.name, await inst.run(ctx)
            except Exception as exc:  # noqa: BLE001
                with session_scope() as s:
                    s.add(AuditLog(scan_id=scan_id, action="adapter.error",
                                   tool=inst.name, detail={"error": str(exc)[:500]}))
                return inst.name, []

        sem = asyncio.Semaphore(ctx.profile.global_concurrency or 10)

        async def guarded(inst):
            async with sem:
                return await run_one(inst)

        results = await asyncio.gather(*(guarded(i) for i in instances))

        all_events = []
        for name, events in results:
            pr.adapters_run.append(name)
            all_events.extend(events)
            with session_scope() as s:
                s.add(AuditLog(scan_id=scan_id, action="adapter.run", tool=name,
                               egress_ip=ctx.http.last_egress, profile=ctx.profile.name,
                               detail={"events": len(events)}))

        # NORMALIZE (single writer) into the DB
        with session_scope() as s:
            norm = Normalizer(s, scan_id, scope=ctx.scope)
            pr.counts = norm.ingest(all_events)

        pr.duration = round(time.time() - t0, 2)

        # AI supervisor reviews the output of this phase
        if self.supervisor:
            try:
                pr.note = await self.supervisor.review_phase(phase, pr.counts, scan_id) or ""
            except Exception:  # noqa: BLE001
                pr.note = ""
        return pr

    # ── chaining: read discovered assets back as next-phase inputs ─────────
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
