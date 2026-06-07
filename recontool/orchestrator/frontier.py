"""Frontier Manager + Checkpoint + Dead-letter (the diagram's boxes I and U).

The Frontier Manager is the convergence engine: a typed, priority-ordered work queue
that re-feeds ONLY new, in-scope, expandable entities, with a monotonic `seen` set that
guarantees termination (dedup => finite in-scope entity space => converges).

Checkpoint persists run state (frontier + seen + budget + breakers + dead-letter +
cursors) so a killed run resumes exactly where it stopped. Dead-letter captures jobs
that exhausted retries (or tripped a breaker) for inspection and replay.

Pure stdlib; deterministic and unit-testable.
"""
from __future__ import annotations

import heapq
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Lower number = expand earlier. Cheap/high-signal hosts before expensive per-URL work.
DEFAULT_PRIORITY = {
    "domain": 5, "live_host": 10, "subdomain": 20, "cert": 25, "ip": 30,
    "cidr": 35, "asn": 40, "repo": 45, "js_file": 50, "bucket": 55,
    "url": 60, "endpoint": 70, "param": 80,
}
# Entity types worth expanding (others — finding/tag/screenshot/... — are terminal).
EXPANDABLE = set(DEFAULT_PRIORITY)


@dataclass
class FrontierItem:
    entity_type: str
    value: str
    dedupe_key: str
    depth: int = 0
    priority: int = 100
    origin: str = ""           # which category/tool produced it (provenance)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FrontierItem":
        return cls(**{k: d[k] for k in ("entity_type", "value", "dedupe_key",
                                        "depth", "priority", "origin") if k in d})


class FrontierManager:
    """Priority work-queue with dedup-driven convergence and depth/budget caps."""

    def __init__(self, scope=None, max_depth: int = 3, max_items: int = 0,
                 priority_map: dict | None = None, expandable: set | None = None):
        self.scope = scope
        self.max_depth = max_depth
        self.max_items = max_items                 # 0 = unbounded (besides convergence)
        self.priority_map = priority_map or DEFAULT_PRIORITY
        self.expandable = expandable or EXPANDABLE
        self._heap: list[tuple[int, int, FrontierItem]] = []
        self._seen: set[str] = set()               # dedupe_keys ever ENQUEUED
        self._seq = 0
        self.stats = {"enqueued": 0, "skipped_seen": 0, "skipped_scope": 0,
                      "skipped_depth": 0, "skipped_type": 0, "skipped_budget": 0,
                      "popped": 0}

    # -- admission ----------------------------------------------------------
    def add(self, item: FrontierItem) -> bool:
        """Enqueue iff new, in-scope, expandable, within depth/budget. Returns
        True if it was newly admitted."""
        if item.entity_type not in self.expandable:
            self.stats["skipped_type"] += 1
            return False
        if item.dedupe_key in self._seen:
            self.stats["skipped_seen"] += 1
            return False
        if item.depth > self.max_depth:
            self.stats["skipped_depth"] += 1
            return False
        if self.scope is not None and not self._in_scope(item):
            self.stats["skipped_scope"] += 1
            return False
        if self.max_items and len(self._seen) >= self.max_items:
            self.stats["skipped_budget"] += 1
            return False
        if not item.priority or item.priority == 100:
            item.priority = self.priority_map.get(item.entity_type, 100)
        self._seen.add(item.dedupe_key)
        self._seq += 1
        heapq.heappush(self._heap, (item.priority, self._seq, item))
        self.stats["enqueued"] += 1
        return True

    def add_many(self, items) -> int:
        return sum(1 for it in items if self.add(it))

    def _in_scope(self, item: FrontierItem) -> bool:
        try:
            return self.scope.contains(item.entity_type, item.value)
        except Exception:  # noqa: BLE001 — unknown type -> let it through, normalizer tags it
            return True

    # -- consumption --------------------------------------------------------
    def pop(self) -> FrontierItem | None:
        if not self._heap:
            return None
        _, _, item = heapq.heappop(self._heap)
        self.stats["popped"] += 1
        return item

    def pop_batch(self, n: int) -> list[FrontierItem]:
        out = []
        for _ in range(n):
            it = self.pop()
            if it is None:
                break
            out.append(it)
        return out

    def __len__(self) -> int:
        return len(self._heap)

    @property
    def converged(self) -> bool:
        return not self._heap

    def seen_count(self) -> int:
        return len(self._seen)

    # -- checkpoint ---------------------------------------------------------
    def snapshot(self) -> dict:
        return {
            "max_depth": self.max_depth, "max_items": self.max_items, "seq": self._seq,
            "seen": sorted(self._seen),
            "queue": [it.to_dict() for _, _, it in sorted(self._heap, key=lambda x: (x[0], x[1]))],
            "stats": self.stats,
        }

    def restore(self, snap: dict) -> None:
        self.max_depth = snap.get("max_depth", self.max_depth)
        self.max_items = snap.get("max_items", self.max_items)
        self._seq = snap.get("seq", 0)
        self._seen = set(snap.get("seen", []))
        self.stats = snap.get("stats", self.stats)
        self._heap = []
        for d in snap.get("queue", []):
            it = FrontierItem.from_dict(d)
            self._seq += 1
            heapq.heappush(self._heap, (it.priority, self._seq, it))


@dataclass
class DeadLetterEntry:
    job: dict
    reason: str
    last_error: str = ""
    attempts: int = 0
    ts: float = field(default_factory=time.time)


class DeadLetter:
    """Jobs that exhausted retries or were blocked by an open circuit. Inspectable
    and replayable."""

    def __init__(self):
        self.entries: list[DeadLetterEntry] = []

    def add(self, job: dict, reason: str, last_error: str = "", attempts: int = 0) -> None:
        self.entries.append(DeadLetterEntry(job=job, reason=reason,
                                            last_error=last_error, attempts=attempts))

    def replay(self) -> list[dict]:
        """Return the jobs to retry and clear the queue."""
        jobs = [e.job for e in self.entries]
        self.entries = []
        return jobs

    def __len__(self) -> int:
        return len(self.entries)

    def snapshot(self) -> dict:
        return {"entries": [asdict(e) for e in self.entries]}

    def restore(self, snap: dict) -> None:
        self.entries = [DeadLetterEntry(**e) for e in snap.get("entries", [])]


class Checkpoint:
    """Atomic, resumable run-state persistence.

    state = { scan_id, created_at, updated_at, completed_stages[], cursors{},
              frontier{}, budget{}, circuits{}, dead_letter{} }
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def save(self, state: dict) -> None:
        state = dict(state)
        state["updated_at"] = time.time()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, indent=2, default=str))
        os.replace(tmp, self.path)          # atomic: no half-written checkpoints

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text())
        except Exception:  # noqa: BLE001
            return None

    def exists(self) -> bool:
        return self.path.exists()

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
