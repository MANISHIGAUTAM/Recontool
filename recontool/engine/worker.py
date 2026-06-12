"""Multi-worker, queue-driven execution over the persisted `work_item` table.

This is the horizontally-scalable execution path (complement to the in-process
`run_engine_scan`). Workers atomically **claim** a pending item (status
`pending -> running` via a compare-and-set UPDATE that is safe both across the
async pool and across separate processes/hosts), run the tool through the SAME
`run_tool_spec` used by the event engine, persist + write typed outputs, then
enqueue downstream work for each new in-scope entity. Because all state lives in
the DB, a scan is resumable and you can run `recontool worker` on N processes
against one `RECON_DB_URL` for real parallelism.

Selection (`tools=default|all`) and the optional noise gate are honored here too.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select, update

from recontool.adapters.base import Event
from recontool.ai.router import ModelRouter
from recontool.core.artifacts import ArtifactStore
from recontool.core.db import create_all, session_scope
from recontool.engine.ai_decision import (
    AIDecisionService, decide_on_events_ai, discarded_asset_pairs,
)
from recontool.engine.fingerprint import fingerprint_inputs
from recontool.engine.incremental import IncrementalEngine
from recontool.engine.logging import EngineLogger
from recontool.engine.models import ToolRun, WorkItem
from recontool.engine.registry import ToolRegistry
from recontool.engine.router import _eligible_types, work_dedupe_key
from recontool.engine.runner import (
    build_noise, build_scan_infra, discovered_assets, load_engine_registry,
    run_tool_spec, write_scan_bundle, write_typed_outputs,
)
from recontool.normalize.engine import Normalizer

logger = logging.getLogger(__name__)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _load_typed_events(paths: list[str], tool: str) -> list:
    """Reconstruct events from a prior run's typed ``out/*.jsonl`` files (reuse).

    Assets + URLs are re-emitted (they drive recursion); ``service``/``finding``
    lines are skipped (terminal and not losslessly reconstructable from the typed
    record). Used only by the incremental-reuse path.
    """
    from recontool.config import settings

    events: list = []
    for rel in paths or []:
        p = settings.artifact_dir / rel
        if not p.exists():
            continue
        for line in p.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            etype, value = rec.get("type"), rec.get("value")
            if not (etype and value):
                continue
            if etype == "url":
                events.append(Event.endpoint(tool, value, source="incremental"))
            elif etype not in ("service", "finding"):
                events.append(Event.asset(tool, etype, value))
    return events


@dataclass
class ClaimedItem:
    """A detached snapshot of a claimed work item (safe to use post-session)."""

    id: int
    key: str
    key_type: str
    tool_slug: str
    depth: int


def claim_one(session, scan_id: str) -> Optional[ClaimedItem]:
    """Atomically claim one pending item: pending -> running. Returns None if
    none are pending OR another worker won the race (caller simply retries).

    Correctness: the UPDATE's `WHERE status='pending'` is a compare-and-set —
    only one worker's commit can flip a given row, so no item is processed twice.
    On Postgres this also takes a row lock; on SQLite the write lock + CAS suffice.
    """
    row = session.execute(
        select(WorkItem.id)
        .where(WorkItem.scan_id == scan_id, WorkItem.status == "pending")
        .order_by(WorkItem.depth, WorkItem.id)
        .limit(1)
    ).first()
    if not row:
        return None
    item_id = row[0]
    res = session.execute(
        update(WorkItem)
        .where(WorkItem.id == item_id, WorkItem.status == "pending")
        .values(status="running", started_at=_now())
    )
    if res.rowcount != 1:
        return None  # lost the race
    it = session.get(WorkItem, item_id)
    return ClaimedItem(id=it.id, key=it.key, key_type=it.key_type,
                       tool_slug=it.tool_slug, depth=it.depth)


class RouteIndex:
    """Precomputed `input_type -> [enabled tool specs]` map, built once per scan.

    Avoids scanning the whole (560+ tool) registry on every discovered entity —
    routing becomes a dict lookup proportional to the matches, not the registry.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._by_type: dict[str, list] = {}
        for spec in registry.all_tools().values():
            if not spec.enabled:
                continue
            for t in set(spec.supported_input_types) | set(spec.consumes):
                self._by_type.setdefault(t, []).append(spec)

    def for_key_type(self, key_type: str) -> list:
        out, seen = [], set()
        for t in _eligible_types(key_type):
            for spec in self._by_type.get(t, ()):
                if spec.name not in seen:
                    seen.add(spec.name)
                    out.append(spec)
        return out


def enqueue_key(
    session, scan_id: str, key: str, key_type: str, registry: ToolRegistry, *,
    depth: int = 0, parent: str | None = None, route: RouteIndex | None = None,
) -> int:
    """Create pending work items for every ENABLED tool that consumes `key_type`
    (with type subsumption). Deduped on `(scan, key, tool)`. Returns new count.

    Performance: only the small set of CANDIDATE dedupe keys for *this* entity is
    checked against the DB (indexed `dedupe_key IN (...)`), not the whole scan's
    key space — so enqueue stays O(eligible tools), not O(total keys discovered).
    """
    specs = (route or RouteIndex(registry)).for_key_type(key_type)
    if not specs:
        return 0
    candidates = {work_dedupe_key(key_type, key, s.name): s for s in specs}
    existing = {
        dk for (dk,) in session.execute(
            select(WorkItem.dedupe_key).where(
                WorkItem.scan_id == scan_id,
                WorkItem.dedupe_key.in_(list(candidates)),
            )
        )
    }
    created = 0
    for dk, spec in candidates.items():
        if dk in existing:
            continue
        session.add(WorkItem(
            scan_id=scan_id, key=key, key_type=key_type, tool_slug=spec.name,
            dedupe_key=dk, status="pending", parent_key=parent, depth=depth,
        ))
        created += 1
    return created


class WorkerPool:
    """Runs N concurrent async workers against the work_item queue for a scan."""

    def __init__(self, registry, *, scope, profile, http, api_keys,
                 noise=None, max_depth: int = 3, ai_service=None, router=None,
                 incremental: bool = False, incremental_max_age: int = 604800):
        self.registry = registry
        self.scope = scope
        self.profile = profile
        self.http = http
        self.api_keys = api_keys
        self.noise = noise
        self.max_depth = max_depth
        self.incremental = incremental
        self.incremental_max_age = incremental_max_age
        self._stores: dict[str, ArtifactStore] = {}
        self._route = RouteIndex(registry)   # built once; reused for every enqueue
        self.log = EngineLogger("recontool.worker")  # structured, correlated debug logs
        # AI decisioning layer: classifies each tool's output (persist / discard
        # noise / trigger downstream) before anything is re-fed into the loop.
        # Heuristic by default; model-augmented when `router` is enabled (the
        # heuristic remains the deterministic floor + scope-safety guarantee).
        self.ai = ai_service or AIDecisionService(scope=scope)
        self.router = router or ModelRouter()
        self.processed = 0
        self.skipped = 0

    def _store(self, scan_id: str) -> ArtifactStore:
        if scan_id not in self._stores:
            self._stores[scan_id] = ArtifactStore(scan_id)
        return self._stores[scan_id]

    async def _process(self, item: ClaimedItem, scan_id: str) -> None:
        spec = self.registry.get(item.tool_slug)
        store = self._store(scan_id)
        new_keys = 0
        out_paths: list[str] = []
        status = "completed"
        reason = ""
        events: list = []
        run_id = f"{scan_id}:{item.id}"
        t0 = time.monotonic()
        inputs = {item.key_type: [item.key]}
        fp = fingerprint_inputs(item.tool_slug, inputs)
        self.log.log_tool_start(run_id, scan_id, item.tool_slug, inputs=inputs)

        # Incremental: reuse a fresh prior run of this EXACT (tool, input) instead
        # of re-executing it — re-ingest its typed outputs into this scan + re-feed.
        if self.incremental and spec is not None:
            reused = await self._try_incremental(item, scan_id, fp)
            if reused is not None:
                await asyncio.to_thread(self._finish_item, item.id, "completed", reused)
                await asyncio.to_thread(
                    self._record_run, scan_id, item.tool_slug, fp, "skipped", 0, [])
                self.log.log_tool_complete(
                    run_id, scan_id, item.tool_slug, duration_ms=0,
                    entity_count=0, key_type=item.key_type,
                    artifact_paths=["(reused prior run — incremental)"])
                self.skipped += 1
                self.processed += 1
                return

        if spec is None:
            status, reason = "failed", "unknown tool"
        else:
            outcome = await run_tool_spec(
                spec, scan_id, inputs, scope=self.scope, profile=self.profile,
                http=self.http, api_keys=self.api_keys, artifacts=store,
            )
            if outcome.status == "error":
                status, reason = "failed", outcome.reason
            events = outcome.events
            if events:
                # AI decisioning (model-augmented when a router is enabled, else
                # the deterministic heuristic). Classifies persist / discard noise
                # BEFORE persisting or re-feeding; logged so the operator sees it.
                decision = await decide_on_events_ai(
                    events, item.tool_slug, service=self.ai, router=self.router)
                self.log.log_ai_decision(scan_id, decision.reasoning,
                                         tool_name=item.tool_slug)
                dropped = discarded_asset_pairs(decision)
                persist_events = decision.persist or events
                await asyncio.to_thread(self._ingest, scan_id, persist_events)
                out_paths = await asyncio.to_thread(
                    write_typed_outputs, store, item.tool_slug, persist_events)
                new_keys = await self._enqueue_discovered(
                    scan_id, events, item.depth + 1, item.key, item.tool_slug, dropped)

        await asyncio.to_thread(self._finish_item, item.id, status, new_keys)
        dur_ms = int((time.monotonic() - t0) * 1000)
        # ALWAYS record a ToolRun — real per-tool execution history + the
        # input fingerprint that powers incremental delta-only reruns.
        await asyncio.to_thread(self._record_run, scan_id, item.tool_slug, fp, status,
                                len(events), out_paths, dur_ms=dur_ms, error=reason)
        if status == "failed":
            self.log.log_tool_fail(run_id, scan_id, item.tool_slug, reason)
        else:
            self.log.log_tool_complete(run_id, scan_id, item.tool_slug,
                                       duration_ms=dur_ms, entity_count=len(events),
                                       key_type=item.key_type, artifact_paths=out_paths)
        self.processed += 1

    def _finish_item(self, item_id: int, status: str, new_keys: int) -> None:
        with session_scope() as s:
            row = s.get(WorkItem, item_id)
            if row is not None:
                row.status = status
                row.finished_at = _now()
                row.new_keys_found = new_keys

    def _ingest(self, scan_id: str, events: list) -> None:
        """Sync DB unit-of-work (run in a thread): normalize events into the DB."""
        with session_scope() as s:
            Normalizer(s, scan_id, scope=self.scope).ingest(events)

    def _find_prior(self, tool: str, fp: str, scan_id: str):
        """Sync DB unit-of-work (run in a thread): find a reusable prior run's paths."""
        with session_scope() as s:
            prior = IncrementalEngine(s).find_fresh_completed(
                tool, fp, max_age_seconds=self.incremental_max_age, exclude_scan=scan_id)
            return list(prior.artifact_paths or []) if prior is not None else None

    def _record_run(self, scan_id: str, tool: str, fp: str, status: str,
                    entity_count: int, paths, *, dur_ms: int = 0,
                    error: str = "") -> None:
        """Persist a ToolRun row (execution history + incremental fingerprint)."""
        with session_scope() as s:
            IncrementalEngine(s).record_run(ToolRun(
                scan_id=scan_id, tool_name=tool, status=status,
                input_fingerprint=fp, finished_at=_now(),
                exit_code=0 if status != "failed" else 1,
                entity_count=entity_count, artifact_paths=list(paths or []),
                duration_ms=dur_ms, error_detail=error or None,
            ))

    async def _enqueue_discovered(self, scan_id: str, events: list, depth: int,
                                  parent: str, tool: str, dropped: set) -> int:
        """Re-feed each new in-scope asset onto the queue (the recursion step).

        Shared by the normal execution path and the incremental-reuse path so
        both recurse identically through the noise gate + dedupe-on-enqueue.
        """
        if depth > self.max_depth:
            return 0
        # Apply the (async) noise gate first to get the survivor set, THEN enqueue
        # them all in ONE transaction — avoids a separate DB commit per entity.
        survivors: list[tuple[str, str]] = []
        for etype, evalue in discovered_assets(events):
            if (etype, evalue) in dropped:
                continue  # AI decisioning flagged it as noise
            if self.noise is not None and not await self.noise.keep(scan_id, etype, evalue):
                continue
            survivors.append((etype, evalue))
        if not survivors:
            return 0
        # Offload the enqueue transaction to a thread (DB-bound); log on the loop.
        results = await asyncio.to_thread(
            self._enqueue_batch, scan_id, survivors, depth, parent)
        new_keys = 0
        for etype, evalue, n in results:
            new_keys += n
            self.log.log_entity_discovered(scan_id, etype, evalue, tool_name=tool)
            if n:
                self.log.log_enqueue(scan_id, etype, evalue, n, depth=depth, tool_name=tool)
        return new_keys

    def _enqueue_batch(self, scan_id: str, survivors: list, depth: int, parent: str):
        """Sync DB unit-of-work (run in a thread): enqueue all survivors in ONE txn."""
        out: list[tuple[str, str, int]] = []
        with session_scope() as s:
            for etype, evalue in survivors:
                n = enqueue_key(s, scan_id, evalue, etype, self.registry,
                                depth=depth, parent=parent, route=self._route)
                out.append((etype, evalue, n))
        return out

    async def _try_incremental(self, item: ClaimedItem, scan_id: str,
                               fp: str) -> Optional[int]:
        """Reuse a fresh prior run of (tool, input) if one exists.

        Re-ingests the prior run's typed outputs into THIS scan and re-feeds them
        for recursion, so the new scan stays complete without re-executing the
        tool. Returns new_keys enqueued, or None if there's nothing to reuse (the
        caller then executes the tool normally).
        """
        paths = await asyncio.to_thread(self._find_prior, item.tool_slug, fp, scan_id)
        if paths is None:
            return None
        events = await asyncio.to_thread(_load_typed_events, paths, item.tool_slug)
        if events:
            await asyncio.to_thread(self._ingest, scan_id, events)
        new_keys = await self._enqueue_discovered(
            scan_id, events, item.depth + 1, item.key, item.tool_slug, set())
        self.log.log_concurrency_decision(
            scan_id, item.tool_slug, "incremental-skip",
            f"reused prior run ({len(events)} entities)")
        return new_keys

    def _claim(self, scan_id: str) -> Optional[ClaimedItem]:
        """Sync DB unit-of-work (run in a worker thread): atomically claim one item."""
        with session_scope() as s:
            return claim_one(s, scan_id)

    async def _worker(self, scan_id: str) -> None:
        while True:
            # Offload the synchronous DB claim to a thread so the event loop stays
            # free for other workers' async HTTP/DNS I/O (no blocking on DB).
            item = await asyncio.to_thread(self._claim, scan_id)
            if item is None:
                if not await asyncio.to_thread(_has_active, scan_id):
                    return
                await asyncio.sleep(0.02)
                continue
            await self._process(item, scan_id)

    async def run(self, scan_id: str, workers: int = 8) -> None:
        await asyncio.gather(*(self._worker(scan_id) for _ in range(max(1, workers))))


def _has_active(scan_id: str) -> bool:
    """True if any pending or running items remain for the scan."""
    with session_scope() as s:
        n = s.execute(
            select(func.count(WorkItem.id)).where(
                WorkItem.scan_id == scan_id,
                WorkItem.status.in_(("pending", "running")),
            )
        ).scalar_one()
    return n > 0


@dataclass
class QueueScanResult:
    scan_id: str
    items_processed: int
    completed: int
    failed: int
    entities: int
    skipped: int = 0
    bundle_path: str | None = None


async def run_queue_scan(
    seed: str, *, seed_type: str = "domain", profile_name: str | None = None,
    registry: ToolRegistry | None = None, tools: str = "default",
    workers: int = 8, authorize_active: bool = False,
    noise_control: bool = False, wildcard_filter: bool = False,
    max_depth: int = 3, scan_id: str | None = None, incremental: bool = False,
) -> QueueScanResult:
    """Seed the work queue and drain it with `workers` concurrent workers.

    The registry is loaded through ``load_engine_registry`` so the hand-written
    Python adapters are bridged in (deep recursion works with no external
    binaries) and the passive/active gate is honored (``authorize_active``).
    Pass ``scan_id`` to use a known id (e.g. the API returns it before the scan
    finishes); otherwise a fresh one is generated. ``incremental`` skips tools
    whose exact input already ran in a recent prior scan (delta-only reruns).
    """
    from recontool.core.models import Asset, Scan

    create_all()
    profile, scope, http, api_keys = build_scan_infra(seed, seed_type, profile_name)
    registry = load_engine_registry(
        tools, authorize_active=authorize_active, registry=registry
    )
    noise = build_noise(scope, noise_control, wildcard_filter)

    pool = WorkerPool(registry, scope=scope, profile=profile, http=http,
                      api_keys=api_keys, noise=noise, max_depth=max_depth,
                      incremental=incremental)

    scan_id = scan_id or uuid.uuid4().hex[:16]
    # Create the Scan row UP FRONT so the DB is consistent while the queue drains
    # (report/UI can read a live scan; assets have a valid parent scan).
    with session_scope() as s:
        if not s.get(Scan, scan_id):
            s.add(Scan(
                id=scan_id, seed=seed, seed_type=seed_type,
                profile=profile_name or profile.name, status="running",
                scope_json=scope.to_json(), active_authorized=authorize_active,
            ))
    with session_scope() as s:
        enqueue_key(s, scan_id, seed, seed_type, registry, depth=0, route=pool._route)

    await pool.run(scan_id, workers=workers)

    with session_scope() as s:
        completed = s.execute(select(func.count(WorkItem.id)).where(
            WorkItem.scan_id == scan_id, WorkItem.status == "completed")).scalar_one()
        failed = s.execute(select(func.count(WorkItem.id)).where(
            WorkItem.scan_id == scan_id, WorkItem.status == "failed")).scalar_one()
        entities = s.execute(select(func.count(Asset.id)).where(
            Asset.scan_id == scan_id)).scalar_one()
        sc = s.get(Scan, scan_id)
        if sc is not None:
            sc.status = "done"
    bundle_path = write_scan_bundle(scan_id)
    if bundle_path:
        logger.info("✓ scan bundle written → %s", bundle_path)
    return QueueScanResult(scan_id=scan_id, items_processed=pool.processed,
                           completed=completed, failed=failed, entities=entities,
                           skipped=pool.skipped, bundle_path=bundle_path)
