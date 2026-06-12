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
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select, update

from recontool.core.artifacts import ArtifactStore
from recontool.core.db import create_all, session_scope
from recontool.engine.ai_decision import (
    AIDecisionService, decide_on_events, discarded_asset_pairs,
)
from recontool.engine.logging import EngineLogger
from recontool.engine.models import WorkItem
from recontool.engine.registry import ToolRegistry
from recontool.engine.router import _eligible_types, work_dedupe_key
from recontool.engine.runner import (
    build_noise, build_scan_infra, discovered_assets, load_engine_registry,
    run_tool_spec, write_typed_outputs,
)
from recontool.normalize.engine import Normalizer

logger = logging.getLogger(__name__)


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


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
                 noise=None, max_depth: int = 3, ai_service=None):
        self.registry = registry
        self.scope = scope
        self.profile = profile
        self.http = http
        self.api_keys = api_keys
        self.noise = noise
        self.max_depth = max_depth
        self._stores: dict[str, ArtifactStore] = {}
        self._route = RouteIndex(registry)   # built once; reused for every enqueue
        self.log = EngineLogger("recontool.worker")  # structured, correlated debug logs
        # AI decisioning layer: classifies each tool's output (persist / discard
        # noise / trigger downstream) before anything is re-fed into the loop.
        # Heuristic by default; override `ai_service` for an AI-augmented path.
        # Scope-aware so the target's own in-scope estate is never dropped.
        self.ai = ai_service or AIDecisionService(scope=scope)
        self.processed = 0

    def _store(self, scan_id: str) -> ArtifactStore:
        if scan_id not in self._stores:
            self._stores[scan_id] = ArtifactStore(scan_id)
        return self._stores[scan_id]

    async def _process(self, item: ClaimedItem, scan_id: str) -> None:
        spec = self.registry.get(item.tool_slug)
        store = self._store(scan_id)
        new_keys = 0
        status = "completed"
        reason = ""
        events: list = []
        run_id = f"{scan_id}:{item.id}"
        t0 = time.monotonic()
        self.log.log_tool_start(run_id, scan_id, item.tool_slug,
                                inputs={item.key_type: [item.key]})
        if spec is None:
            status, reason = "failed", "unknown tool"
        else:
            outcome = await run_tool_spec(
                spec, scan_id, {item.key_type: [item.key]}, scope=self.scope,
                profile=self.profile, http=self.http, api_keys=self.api_keys,
                artifacts=store,
            )
            if outcome.status == "error":
                status, reason = "failed", outcome.reason
            events = outcome.events
            if events:
                # AI decisioning: classify entities (persist / discard noise /
                # trigger downstream) BEFORE persisting or re-feeding. Visible in
                # the logs so the operator can see what the engine decided.
                decision = decide_on_events(events, item.tool_slug, service=self.ai)
                self.log.log_ai_decision(scan_id, decision.reasoning,
                                         tool_name=item.tool_slug)
                dropped = discarded_asset_pairs(decision)
                persist_events = decision.persist or events
                with session_scope() as s:
                    Normalizer(s, scan_id, scope=self.scope).ingest(persist_events)
                write_typed_outputs(store, item.tool_slug, persist_events)
                if item.depth + 1 <= self.max_depth:
                    with session_scope() as s:
                        for etype, evalue in discovered_assets(events):
                            if (etype, evalue) in dropped:
                                continue  # AI decisioning flagged it as noise
                            if self.noise is not None and not await self.noise.keep(
                                    scan_id, etype, evalue):
                                continue
                            n = enqueue_key(
                                s, scan_id, evalue, etype, self.registry,
                                depth=item.depth + 1, parent=item.key,
                                route=self._route,
                            )
                            new_keys += n
                            self.log.log_entity_discovered(
                                scan_id, etype, evalue, tool_name=item.tool_slug)
                            if n:
                                self.log.log_enqueue(
                                    scan_id, etype, evalue, n,
                                    depth=item.depth + 1, tool_name=item.tool_slug)
        with session_scope() as s:
            row = s.get(WorkItem, item.id)
            if row is not None:
                row.status = status
                row.finished_at = _now()
                row.new_keys_found = new_keys
        dur_ms = int((time.monotonic() - t0) * 1000)
        if status == "failed":
            self.log.log_tool_fail(run_id, scan_id, item.tool_slug, reason)
        else:
            self.log.log_tool_complete(run_id, scan_id, item.tool_slug,
                                       duration_ms=dur_ms, entity_count=len(events))
        self.processed += 1

    async def _worker(self, scan_id: str) -> None:
        while True:
            with session_scope() as s:
                item = claim_one(s, scan_id)
            if item is None:
                if not _has_active(scan_id):
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


async def run_queue_scan(
    seed: str, *, seed_type: str = "domain", profile_name: str | None = None,
    registry: ToolRegistry | None = None, tools: str = "default",
    workers: int = 8, authorize_active: bool = False,
    noise_control: bool = False, wildcard_filter: bool = False,
    max_depth: int = 3, scan_id: str | None = None,
) -> QueueScanResult:
    """Seed the work queue and drain it with `workers` concurrent workers.

    The registry is loaded through ``load_engine_registry`` so the hand-written
    Python adapters are bridged in (deep recursion works with no external
    binaries) and the passive/active gate is honored (``authorize_active``).
    Pass ``scan_id`` to use a known id (e.g. the API returns it before the scan
    finishes); otherwise a fresh one is generated.
    """
    from recontool.core.models import Asset, Scan

    create_all()
    profile, scope, http, api_keys = build_scan_infra(seed, seed_type, profile_name)
    registry = load_engine_registry(
        tools, authorize_active=authorize_active, registry=registry
    )
    noise = build_noise(scope, noise_control, wildcard_filter)

    pool = WorkerPool(registry, scope=scope, profile=profile, http=http,
                      api_keys=api_keys, noise=noise, max_depth=max_depth)

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
    return QueueScanResult(scan_id=scan_id, items_processed=pool.processed,
                           completed=completed, failed=failed, entities=entities)
