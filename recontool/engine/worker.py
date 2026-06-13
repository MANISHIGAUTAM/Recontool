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
import functools
import json
import logging
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select, update

from recontool.adapters.base import Event
from recontool.config import settings as _cfg_settings
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

# Max events held in flight per tool while persisting/writing/recursing. Bounds
# the heap watermark so a firehose tool (wayback_cdx ~200k urls) processed across
# 128 concurrent workers can't OOM the box. Large enough to keep DB round-trips
# amortized; small relative to a 200k firehose.
_EVENT_BATCH = 5000


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _reuse_eligible(spec) -> bool:
    """Whether a tool's prior run may be REUSED on an incremental rescan.

    Incremental reuse is only correct when a tool's output for a given input is
    STABLE across the freshness window. Passive discovery (crt.sh, wayback, OSINT
    APIs) qualifies. ACTIVE / vulnerability tools (httpx probing, nuclei, nmap,
    naabu, …) must ALWAYS re-execute: the target's live state changes between
    scans, so reusing a stale nuclei/nmap result would silently miss newly
    introduced services or vulnerabilities — a correctness/security failure. The
    registry is the source of truth: an explicit ``incremental_safe=True`` forces
    reuse; otherwise it's derived from the (populated) passive/active flags.
    """
    if spec is None:
        return False
    if getattr(spec, "incremental_safe", False):
        return True
    return getattr(spec, "type", "passive") == "passive" and not getattr(spec, "is_active", False)


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


# Static availability gate: an enabled tool whose binary isn't installed (or whose
# required API key is absent) would only be claimed-then-skipped at EVERY recursion
# level. Pruning these from routing removes that dead churn -- the single biggest
# queue-size win on a --tools all scan (hundreds of inventory stubs have no binary).
# Python adapters without a declared binary are kept (they decide at runtime); the
# handful that gate on a binary are listed so they prune too.
_PY_ADAPTER_BINARY = {
    "nuclei": "nuclei", "naabu": "naabu", "nmap": "nmap", "sslyze": "sslyze",
    "gitleaks": "gitleaks", "whatweb": "whatweb", "gowitness": "gowitness",
}

# High-output producers that must be concurrency-gated for MEMORY regardless of
# integration: each can emit 10^5-10^6 events for a big target, so several running
# at once (esp. the Python crawlers, which were NOT gated before) drive the heap
# past the box limit. CLI tools are already gated; these add the Python crawlers +
# the Wayback API firehose. (The earlier batching fix bounds the per-tool
# downstream; this bounds how many big producers materialize concurrently.)
_HIGH_OUTPUT = {
    "pycrawl", "js_analyze", "js-render", "js_render", "wayback_cdx",
    "waybackurls", "gau", "gauplus", "waymore", "katana", "hakrawler",
    "gospider", "cariddi",
}

# Hard ceiling on concurrent heavy/high-output tools, independent of --workers.
# Light tools (DNS, small APIs) still use the full worker pool; only the
# memory-heavy producers serialize through this, keeping peak RSS bounded so the
# engine and Postgres coexist on a modest shared box.
_HEAVY_MAX = 16


def _tool_available(spec) -> bool:
    integ = getattr(spec, "integration", "")
    if integ == "api":
        ke = getattr(spec, "requires_key", None)
        return (not ke) or bool(getattr(spec, "key_optional", False)) or bool(_cfg_settings.api_key(ke))
    binary = getattr(spec, "binary", None) or _PY_ADAPTER_BINARY.get(spec.name)
    if binary:
        return shutil.which(binary) is not None
    return True


class RouteIndex:
    """Precomputed `input_type -> [enabled tool specs]` map, built once per scan.

    Avoids scanning the whole (560+ tool) registry on every discovered entity —
    routing becomes a dict lookup proportional to the matches, not the registry.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._by_type: dict[str, list] = {}
        self.pruned_unavailable: list[str] = []
        for spec in registry.all_tools().values():
            if not spec.enabled:
                continue
            if not _tool_available(spec):
                self.pruned_unavailable.append(spec.name)
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


# Host-like key types in order from most general to most specific, mirroring
# router.SUBSUMES (domain <- subdomain <- live_host <- url). Used to normalize
# the key_type component of a tool's dedupe_key — see _dedupe_key_type.
_HOST_TYPES_BY_GENERALITY = ("domain", "subdomain", "live_host", "url")


def _dedupe_key_type(spec, key_type: str) -> str:
    """Pick ONE canonical key_type for a tool's dedupe_key, regardless of which
    host-like entity type (domain/subdomain/live_host/url) triggered enqueueing it.

    Without this, the apex hostname discovered as BOTH `domain` (the seed) and
    `subdomain` (crtsh/urlscan return the apex itself as a cert SAN) gets two
    different dedupe_keys for the same (tool, hostname) — every domain-consuming
    tool then runs twice on an identical input. A tool is reachable from any
    trigger type that SUBSUMES one of its declared `consumes` types, so picking
    the most general declared type it consumes gives the same answer no matter
    which trigger fired.
    """
    consumes = set(spec.consumes or []) | set(spec.supported_input_types or [])
    for t in _HOST_TYPES_BY_GENERALITY:
        if t in consumes:
            return t
    return key_type


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
    candidates = {
        work_dedupe_key(_dedupe_key_type(s, key_type), key, s.name): s for s in specs
    }
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
        # Hard ceiling per work item: no tool may pin a worker forever. A CLI
        # tool already self-bounds via its spec timeout (default 1800s); this
        # is the backstop for in-process Python adapters (crawler/js-render) and
        # any wedged await, so the queue always makes forward progress.
        self.item_timeout = 2400
        self._stores: dict[str, ArtifactStore] = {}
        self._route = RouteIndex(registry)   # built once; reused for every enqueue
        self.log = EngineLogger("recontool.worker")  # structured, correlated debug logs
        if self._route.pruned_unavailable:
            _pr = sorted(self._route.pruned_unavailable)
            logger.info("\u2298 %d tools pruned at routing (no binary/key) \u2014 not enqueued: %s%s",
                        len(_pr), ", ".join(_pr[:12]), " \u2026" if len(_pr) > 12 else "")
        # AI decisioning layer: classifies each tool's output (persist / discard
        # noise / trigger downstream) before anything is re-fed into the loop.
        # Heuristic by default; model-augmented when `router` is enabled (the
        # heuristic remains the deterministic floor + scope-safety guarantee).
        self.ai = ai_service or AIDecisionService(scope=scope)
        self.router = router or ModelRouter()
        self.processed = 0
        self.skipped = 0
        # Serialize DB I/O through a dedicated executor: ONE thread for SQLite so
        # it never sees concurrent writers from the worker pool (the recurring
        # 'database is locked' cause); a small pool for Postgres, which handles
        # concurrent writes natively. The event loop stays free for async I/O.
        from recontool.config import settings as _settings
        _sqlite = (_settings.db_url or "").startswith("sqlite")
        self._db_pool = ThreadPoolExecutor(
            max_workers=1 if _sqlite else 8, thread_name_prefix="recon-db")
        # Concurrency weighting: subprocess-spawning tools (CLI + the handwritten
        # adapters that shell out) are resource-heavy and get a bounded semaphore
        # so they can never monopolise the pool; pure-network tools (API + dns/http
        # python adapters) run unbounded. NO tool is capped or dropped -- heavy
        # ones just can't all run AT ONCE. Sized in run() from the worker count.
        self._heavy_sem = asyncio.Semaphore(8)
        # Per-tool serialization locks for tools the registry marks
        # concurrency_safety=False (raw-socket scanners, fixed-output-path tools):
        # only one run of such a tool executes at a time across the whole pool.
        self._conc_locks: dict[str, asyncio.Lock] = {}

    async def _db(self, fn, *args, **kwargs):
        """Run a synchronous DB unit-of-work on the dedicated DB executor.

        Serializing DB ops (for SQLite) eliminates concurrent writers while
        keeping the event loop free for the workers' async HTTP/DNS.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._db_pool, functools.partial(fn, *args, **kwargs))

    def _store(self, scan_id: str) -> ArtifactStore:
        if scan_id not in self._stores:
            self._stores[scan_id] = ArtifactStore(scan_id)
        return self._stores[scan_id]

    def _is_heavy(self, spec) -> bool:
        if spec.name in _HIGH_OUTPUT:
            return True
        integ = getattr(spec, "integration", "")
        if integ == "cli":
            return True
        if integ == "python":
            return spec.name in _PY_ADAPTER_BINARY
        return False

    async def _run_with_policy(self, spec, scan_id: str, inputs: dict, store):
        """Execute a tool honoring the registry's concurrency + retry policy.

        - ``concurrency_safety=False`` -> serialize all runs of this tool through a
          per-tool lock (one at a time across the pool), for tools that aren't
          parallel-safe (raw-socket scanners, fixed shared output paths).
        - ``retry_policy.max_retries`` -> re-execute on an ``error`` outcome only
          (never on ``skip``/``ok``), waiting ``backoff_factor**attempt`` seconds
          (capped) between tries. Default policy (max_retries=0) = no retry, so
          behavior is unchanged unless a tool opts in.
        Each attempt is still bounded by the heavy semaphore + per-item wall-clock.
        """
        rp = getattr(spec, "retry_policy", None)
        max_retries = max(0, getattr(rp, "max_retries", 0) or 0)
        backoff = getattr(rp, "backoff_factor", 1.0) or 1.0
        lock = (self._conc_locks.setdefault(spec.name, asyncio.Lock())
                if not getattr(spec, "concurrency_safety", True) else None)

        async def _once():
            heavy = self._is_heavy(spec)
            if heavy:
                await self._heavy_sem.acquire()
            try:
                return await asyncio.wait_for(
                    run_tool_spec(
                        spec, scan_id, inputs, scope=self.scope, profile=self.profile,
                        http=self.http, api_keys=self.api_keys, artifacts=store,
                    ),
                    timeout=self.item_timeout,
                )
            finally:
                if heavy:
                    self._heavy_sem.release()

        attempt = 0
        while True:
            if lock is not None:
                async with lock:
                    outcome = await _once()
            else:
                outcome = await _once()
            if outcome.status != "error" or attempt >= max_retries:
                return outcome
            attempt += 1
            self.log.log_concurrency_decision(
                scan_id, spec.name, "retry",
                f"attempt {attempt}/{max_retries} after error: {(outcome.reason or '')[:80]}")
            await asyncio.sleep(min(30.0, backoff ** attempt))

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
        if self.incremental and _reuse_eligible(spec):
            reused = await self._try_incremental(item, scan_id, fp)
            if reused is not None:
                await self._db(self._finish_item, item.id, "completed", reused)
                await self._db(
                    self._record_run, scan_id, item.tool_slug, fp, "skipped", 0, [])
                self.log.log_tool_complete(
                    run_id, scan_id, item.tool_slug, duration_ms=0,
                    entity_count=0, key_type=item.key_type,
                    artifact_paths=["(reused prior run — incremental)"])
                self.skipped += 1
                self.processed += 1
                return

        tool_status, skip_reason = "ok", ""
        if spec is None:
            status, reason = "failed", "unknown tool"
        else:
            outcome = await self._run_with_policy(spec, scan_id, inputs, store)
            tool_status = outcome.status
            if outcome.status == "error":
                status, reason = "failed", outcome.reason
            elif outcome.status == "skip":
                skip_reason = outcome.reason
            events = outcome.events
            if events:
                # AI decisioning (model-augmented when a router is enabled, else
                # the deterministic heuristic). Classifies persist / discard noise
                # BEFORE persisting or re-feeding; logged so the operator sees it.
                #
                # MEMORY: process the events in bounded batches. A firehose tool
                # (wayback_cdx emitting 200k+ urls) otherwise holds its full event
                # list PLUS the decision/persist copy PLUS the write buffers PLUS
                # the enqueue working set simultaneously, and with 128 workers
                # several such tools at once exhaust the heap (OOM, exit 137).
                # Batching caps the per-tool watermark to ~_EVENT_BATCH events
                # without dropping anything — every event is still classified,
                # persisted, written to its typed file, and recursed.
                out_seen: set[str] = set()
                for _b in range(0, len(events), _EVENT_BATCH):
                    batch = events[_b:_b + _EVENT_BATCH]
                    decision = await decide_on_events_ai(
                        batch, item.tool_slug, service=self.ai, router=self.router)
                    if _b == 0:
                        self.log.log_ai_decision(scan_id, decision.reasoning,
                                                 tool_name=item.tool_slug)
                    dropped = discarded_asset_pairs(decision)
                    persist_events = decision.persist or batch
                    await self._db(self._ingest, scan_id, persist_events)
                    out_seen.update(await asyncio.to_thread(
                        write_typed_outputs, store, item.tool_slug, persist_events))
                    new_keys += await self._enqueue_discovered(
                        scan_id, batch, item.depth + 1, item.key, item.tool_slug, dropped)
                out_paths = sorted(out_seen)

        await self._db(self._finish_item, item.id, status, new_keys)
        dur_ms = int((time.monotonic() - t0) * 1000)
        # ALWAYS record a ToolRun — real per-tool execution history + the
        # input fingerprint that powers incremental delta-only reruns.
        await self._db(self._record_run, scan_id, item.tool_slug, fp, status,
                                len(events), out_paths, dur_ms=dur_ms, error=reason)
        if status == "failed":
            self.log.log_tool_fail(run_id, scan_id, item.tool_slug, reason)
        else:
            self.log.log_tool_complete(run_id, scan_id, item.tool_slug,
                                       duration_ms=dur_ms, entity_count=len(events),
                                       key_type=item.key_type, artifact_paths=out_paths,
                                       status=tool_status, skip_reason=skip_reason)
        self.processed += 1

    def _finish_item(self, item_id: int, status: str, new_keys: int) -> None:
        with session_scope() as s:
            row = s.get(WorkItem, item_id)
            if row is not None:
                row.status = status
                row.finished_at = _now()
                row.new_keys_found = new_keys

    def _ingest(self, scan_id: str, events: list) -> None:
        """Sync DB unit-of-work (run in a thread): normalize events into the DB.

        Chunked into short transactions so a huge batch (e.g. a crawl that emits
        100k+ endpoints) never holds the SQLite write lock for minutes — each
        chunk commits and releases the lock so other workers can interleave.
        """
        chunk = 1000
        for i in range(0, len(events), chunk):
            batch = events[i:i + chunk]
            try:
                with session_scope() as s:
                    Normalizer(s, scan_id, scope=self.scope).ingest(batch)
            except Exception as exc:  # noqa: BLE001
                # A single malformed/over-limit event must not lose the other 999
                # in the chunk (the whole txn rolls back). Retry the batch one
                # event at a time so every salvageable row is persisted.
                logger.warning("ingest: chunk failed (%s) — retrying per-event", exc)
                for ev in batch:
                    try:
                        with session_scope() as s:
                            Normalizer(s, scan_id, scope=self.scope).ingest([ev])
                    except Exception as exc2:  # noqa: BLE001
                        logger.warning("ingest: dropped 1 unpersistable event: %s", exc2)

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
        results = await self._db(
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
        paths = await self._db(self._find_prior, item.tool_slug, fp, scan_id)
        if paths is None:
            return None
        events = await asyncio.to_thread(_load_typed_events, paths, item.tool_slug)
        if events:
            await self._db(self._ingest, scan_id, events)
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
            item = await self._db(self._claim, scan_id)
            if item is None:
                if not await self._db(_has_active, scan_id):
                    return
                await asyncio.sleep(0.02)
                continue
            try:
                await self._process(item, scan_id)
            except asyncio.CancelledError:
                raise  # legitimate shutdown — let the pool unwind
            except Exception as exc:  # noqa: BLE001
                # A SINGLE item's failure (tool crash, DB error, parse bug) must
                # NEVER tear down the pool. asyncio.gather() re-raises the first
                # worker exception and cancels the rest — which would orphan their
                # in-flight subprocesses and deadlock the whole scan (the exact
                # failure mode we hit: one over-long-value DB INSERT killed a 128-
                # worker run with 5,797 items still pending). Mark the item failed,
                # log it, and keep draining the queue.
                logger.warning("worker: item %s tool=%s failed, continuing: %s",
                               item.id, item.tool_slug, exc)
                try:
                    await self._db(self._finish_item, item.id, "failed", 0)
                except Exception:  # noqa: BLE001
                    pass
                self.processed += 1

    async def run(self, scan_id: str, workers: int = 24) -> None:
        # Heavy/high-output tools are bounded to at most _HEAVY_MAX concurrent
        # (independent of --workers) so their large stdout buffers + event lists
        # can't blow the heap; light/fast tools still use the full pool. Capping
        # by an absolute number (not workers//2) is what lets a 128-worker scan
        # of a firehose target fit alongside Postgres on a ~8GB box.
        self._heavy_sem = asyncio.Semaphore(max(2, min(workers // 2, _HEAVY_MAX)))
        try:
            await asyncio.gather(*(self._worker(scan_id) for _ in range(max(1, workers))))
        finally:
            self._db_pool.shutdown(wait=True)   # flush any pending DB writes


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
    summary: str | None = None


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
    # Silence benign subprocess-teardown noise: a stdin-fed CLI tool
    # (puredns/massdns/tlsx) that exits without draining all of stdin, or a
    # SIGKILL'd process, leaves an unretrieved BrokenPipeError on the stdin write
    # transport ("Future exception was never retrieved"). It does not affect
    # results — drop it; everything else goes to the default handler.
    _loop = asyncio.get_running_loop()
    _prev_handler = _loop.get_exception_handler()

    def _ignore_pipe_noise(loop, context):
        if isinstance(context.get("exception"), (BrokenPipeError, ConnectionResetError)):
            return
        (_prev_handler or loop.default_exception_handler)(context)

    _loop.set_exception_handler(_ignore_pipe_noise)
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
    # Final AI (or heuristic) wrap-up — written into the bundle + out/scan_summary.md.
    from recontool.engine.summary import generate_summary
    summary, facts = await generate_summary(scan_id, pool.router)
    bundle_path = write_scan_bundle(
        scan_id, summary=summary, tool_stats=facts.get("tools"))
    if bundle_path:
        logger.info("✓ scan bundle written → %s", bundle_path)
    return QueueScanResult(scan_id=scan_id, items_processed=pool.processed,
                           completed=completed, failed=failed, entities=entities,
                           skipped=pool.skipped, bundle_path=bundle_path,
                           summary=summary)
