"""Multi-worker queue execution: atomic claim, drain, recursion, selection.

Hermetic — uses `echo` tools, no network.
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from recontool.config import settings
from recontool.core import db
from recontool.core.models import Asset
from recontool.engine.models import WorkItem
from recontool.engine.registry import ToolRegistry, ToolSpec
from recontool.engine.selection import apply_selection
from recontool.engine.worker import WorkerPool, run_queue_scan
from recontool.engine.runner import build_scan_infra


def _echo(name, consumes, produces, value):
    return ToolSpec(
        name=name, integration="cli", binary="echo", invocation=f"echo {value}",
        consumes=consumes, supported_input_types=consumes,
        produces=produces, output_types=produces,
        category=2, is_active=False, enabled=True, non_executable=False,
        parse={"format": "text",
               "emit": [{"entity": "asset", "value": "{_value}",
                         "type": produces[0], "scope_filter": "subdomain"}]},
    )


def _registry():
    return ToolRegistry(tools={
        "sub_echo": _echo("sub_echo", ["domain"], ["subdomain"], "api.example.com"),
        "deep_echo": _echo("deep_echo", ["subdomain"], ["subdomain"], "deep.api.example.com"),
    })


@pytest.mark.asyncio
async def test_queue_scan_drains_and_recurses(tmp_path, monkeypatch):
    db.init_engine(f"sqlite:///{tmp_path / 'q.db'}")
    db.create_all()
    monkeypatch.setattr(settings, "artifact_dir", tmp_path / "artifacts")

    result = await run_queue_scan("example.com", registry=_registry(),
                                  tools="all", workers=4, max_depth=3)

    assert result.failed == 0
    assert result.completed >= 2          # sub_echo + deep_echo(s) ran
    assert result.entities >= 2
    with db.session_scope() as s:
        values = {a.value for a in s.execute(select(Asset)).scalars()}
        leftover = s.execute(select(func.count(WorkItem.id)).where(
            WorkItem.scan_id == result.scan_id,
            WorkItem.status.in_(("pending", "running")))).scalar_one()
    assert "api.example.com" in values and "deep.api.example.com" in values
    assert leftover == 0                  # queue fully drained


@pytest.mark.asyncio
async def test_no_item_processed_twice(tmp_path, monkeypatch):
    """Atomic claim: with many workers, processed == number of work items."""
    db.init_engine(f"sqlite:///{tmp_path / 'q2.db'}")
    db.create_all()
    monkeypatch.setattr(settings, "artifact_dir", tmp_path / "artifacts")

    reg = _registry()
    apply_selection(reg, "all")
    profile, scope, http, api_keys = build_scan_infra("example.com", "domain", None)
    pool = WorkerPool(reg, scope=scope, profile=profile, http=http,
                      api_keys=api_keys, max_depth=3)

    # Pre-seed several independent items, then drain with 6 workers.
    scan_id = "claimtest"
    from recontool.engine.worker import enqueue_key
    with db.session_scope() as s:
        enqueue_key(s, scan_id, "example.com", "domain", reg, depth=0)

    await pool.run(scan_id, workers=6)

    with db.session_scope() as s:
        total = s.execute(select(func.count(WorkItem.id)).where(
            WorkItem.scan_id == scan_id)).scalar_one()
        completed = s.execute(select(func.count(WorkItem.id)).where(
            WorkItem.scan_id == scan_id, WorkItem.status == "completed")).scalar_one()
    # every created item ended completed exactly once; processed count matches
    assert completed == total
    assert pool.processed == total


def test_selection_default_vs_excessive():
    inv = _echo("inv_tool", ["domain"], ["subdomain"], "x.example.com")
    inv.source = "inventory"                    # inventory-derived runnable tool
    reg = ToolRegistry(tools={
        "sub_echo": _echo("sub_echo", ["domain"], ["subdomain"], "api.example.com"),
        "deep_echo": _echo("deep_echo", ["subdomain"], ["subdomain"], "deep.example.com"),
        "inv_tool": inv,
    })
    assert apply_selection(reg, "default") == 2          # curated only (inventory excluded)
    assert apply_selection(reg, "all") == 3              # everything runnable
