"""Atomic checks for the Frontier Manager, Dead-letter, and Checkpoint."""
from __future__ import annotations

from recontool.core.scope import Scope
from recontool.orchestrator.frontier import (
    Checkpoint,
    DeadLetter,
    FrontierItem,
    FrontierManager,
)


def _item(t, v, depth=0):
    return FrontierItem(entity_type=t, value=v, dedupe_key=f"{t}:{v}", depth=depth)


def test_dedupe_only_new_entities_admitted():
    fm = FrontierManager()
    assert fm.add(_item("subdomain", "a.example.com")) is True
    assert fm.add(_item("subdomain", "a.example.com")) is False   # already seen
    assert fm.stats["enqueued"] == 1 and fm.stats["skipped_seen"] == 1


def test_priority_ordering_hosts_before_urls():
    fm = FrontierManager()
    fm.add(_item("url", "https://x.example.com/a"))
    fm.add(_item("live_host", "https://x.example.com"))
    fm.add(_item("subdomain", "y.example.com"))
    order = [fm.pop().entity_type for _ in range(3)]
    assert order == ["live_host", "subdomain", "url"]   # priority 10 < 20 < 60


def test_scope_filtering():
    fm = FrontierManager(scope=Scope.from_seed("example.com", "domain"))
    assert fm.add(_item("subdomain", "api.example.com")) is True
    assert fm.add(_item("subdomain", "evil.attacker.com")) is False
    assert fm.stats["skipped_scope"] == 1


def test_depth_cap():
    fm = FrontierManager(max_depth=2)
    assert fm.add(_item("subdomain", "a.example.com", depth=2)) is True
    assert fm.add(_item("subdomain", "b.example.com", depth=3)) is False
    assert fm.stats["skipped_depth"] == 1


def test_terminal_types_not_expandable():
    fm = FrontierManager()
    assert fm.add(_item("finding", "x")) is False
    assert fm.add(_item("screenshot", "y")) is False
    assert fm.stats["skipped_type"] == 2


def test_convergence_when_drained():
    fm = FrontierManager()
    fm.add_many([_item("subdomain", f"h{i}.example.com") for i in range(5)])
    assert not fm.converged
    while fm.pop():
        pass
    assert fm.converged and len(fm) == 0


def test_max_items_budget():
    fm = FrontierManager(max_items=2)
    assert fm.add(_item("subdomain", "a.example.com")) is True
    assert fm.add(_item("subdomain", "b.example.com")) is True
    assert fm.add(_item("subdomain", "c.example.com")) is False   # budget hit
    assert fm.stats["skipped_budget"] == 1


def test_snapshot_restore_roundtrip():
    fm = FrontierManager(max_depth=4)
    fm.add_many([_item("subdomain", f"h{i}.example.com") for i in range(4)])
    fm.pop()                                  # consume one
    snap = fm.snapshot()
    fm2 = FrontierManager()
    fm2.restore(snap)
    assert fm2.seen_count() == fm.seen_count()
    assert len(fm2) == len(fm)
    # re-adding a seen item is still rejected after restore (resumable dedupe)
    assert fm2.add(_item("subdomain", "h0.example.com")) is False


def test_dead_letter_add_and_replay():
    dl = DeadLetter()
    dl.add({"tool": "censys", "target": "x"}, reason="quota_exhausted", attempts=3)
    dl.add({"tool": "github", "target": "y"}, reason="secondary_rate_limit", attempts=5)
    assert len(dl) == 2
    snap = dl.snapshot()
    dl2 = DeadLetter(); dl2.restore(snap)
    jobs = dl2.replay()
    assert len(jobs) == 2 and len(dl2) == 0     # replay drains
    assert {j["tool"] for j in jobs} == {"censys", "github"}


def test_checkpoint_atomic_save_load(tmp_path):
    cp = Checkpoint(tmp_path / "run.ckpt")
    assert cp.load() is None
    fm = FrontierManager()
    fm.add_many([_item("subdomain", f"h{i}.example.com") for i in range(3)])
    state = {"scan_id": "s1", "completed_stages": ["p1_seed"],
             "frontier": fm.snapshot(), "circuits": {}, "dead_letter": {}}
    cp.save(state)
    loaded = cp.load()
    assert loaded["scan_id"] == "s1"
    assert loaded["completed_stages"] == ["p1_seed"]
    fm2 = FrontierManager(); fm2.restore(loaded["frontier"])
    assert fm2.seen_count() == 3
    cp.clear()
    assert not cp.exists()
