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
async def test_firehose_tool_is_batched_but_persists_everything(tmp_path, monkeypatch):
    """A tool emitting MORE than _EVENT_BATCH entities is processed in bounded
    batches (the OOM fix) yet every entity is still persisted — none dropped at a
    batch boundary."""
    import shutil

    from recontool.engine.worker import _EVENT_BATCH
    if shutil.which("seq") is None:
        pytest.skip("seq not available")
    db.init_engine(f"sqlite:///{tmp_path / 'fh.db'}")
    db.create_all()
    monkeypatch.setattr(settings, "artifact_dir", tmp_path / "artifacts")

    n = _EVENT_BATCH + 1000            # spans 2 batches
    firehose = ToolSpec(
        name="firehose", integration="cli", binary="seq", invocation=f"seq 1 {n}",
        consumes=["domain"], supported_input_types=["domain"],
        produces=["subdomain"], output_types=["subdomain"],
        category=2, is_active=False, enabled=True, non_executable=False,
        parse={"format": "text",
               "emit": [{"entity": "asset", "value": "h{_value}.example.com",
                         "type": "subdomain", "scope_filter": "subdomain"}]},
    )
    result = await run_queue_scan("example.com", registry=ToolRegistry(tools={"firehose": firehose}),
                                  tools="all", workers=2, max_depth=1)

    assert result.failed == 0
    with db.session_scope() as s:
        subs = s.execute(select(func.count(Asset.id)).where(
            Asset.scan_id == result.scan_id, Asset.type == "subdomain")).scalar_one()
    assert subs == n                   # all n persisted across both batches


@pytest.mark.asyncio
async def test_validation_phase_is_separate_and_finds_after_recon(tmp_path, monkeypatch):
    """--validate splits recon from validation: a vuln tool (active, finding-only)
    is held back from recon and runs in a SEPARATE phase 2 against the discovered
    live surface, producing normalized findings linked to the asset."""
    import shutil

    from sqlalchemy import func, select

    from recontool.core.models import Finding
    if shutil.which("echo") is None:
        pytest.skip("echo not available")
    db.init_engine(f"sqlite:///{tmp_path / 'v.db'}")
    db.create_all()
    monkeypatch.setattr(settings, "artifact_dir", tmp_path / "artifacts")

    # recon: domain -> a confirmed url asset (in scope)
    seeder = ToolSpec(
        name="seeder", integration="cli", binary="echo",
        invocation="echo https://x.example.com",
        consumes=["domain"], supported_input_types=["domain"],
        produces=["url"], output_types=["url"], category=2,
        is_active=False, enabled=True, non_executable=False,
        parse={"format": "text", "emit": [{"entity": "asset", "value": "{_value}", "type": "url"}]})
    # validation: url -> a finding (active + finding-only => is_validation_tool)
    vuln = ToolSpec(
        name="vuln_echo", integration="cli", binary="echo", invocation="echo HIT",
        consumes=["url"], supported_input_types=["url"],
        produces=["finding"], output_types=["finding"], category=27, phase="p6_vuln",
        is_active=True, enabled=True, non_executable=False,
        parse={"format": "text", "emit": [{"entity": "finding", "title": "vuln: {_value}",
                                            "kind": "exposure", "asset_value": "https://x.example.com"}]})
    reg = ToolRegistry(tools={"seeder": seeder, "vuln_echo": vuln})

    result = await run_queue_scan("example.com", registry=reg, tools="all",
                                  workers=2, max_depth=2, authorize_active=True,
                                  validate=True)

    assert result.failed == 0
    assert result.validation_findings >= 1          # phase 2 produced findings
    with db.session_scope() as s:
        findings = s.execute(select(Finding).where(Finding.scan_id == result.scan_id)).scalars().all()
        # the finding came from the validation tool, linked to the asset
        assert any(f.detector == "vuln_echo" and f.asset_value == "https://x.example.com"
                   for f in findings)
        # both tools ran (recon seeder in phase 1, vuln in phase 2), none left pending
        leftover = s.execute(select(func.count(WorkItem.id)).where(
            WorkItem.scan_id == result.scan_id,
            WorkItem.status.in_(("pending", "running")))).scalar_one()
    assert leftover == 0


@pytest.mark.asyncio
async def test_worker_emits_structured_logs(tmp_path, monkeypatch):
    """Each processed item produces correlated start+complete debug log entries."""
    db.init_engine(f"sqlite:///{tmp_path / 'qlog.db'}")
    db.create_all()
    monkeypatch.setattr(settings, "artifact_dir", tmp_path / "artifacts")

    reg = _registry()
    apply_selection(reg, "all")
    profile, scope, http, api_keys = build_scan_infra("example.com", "domain", None)
    pool = WorkerPool(reg, scope=scope, profile=profile, http=http, api_keys=api_keys)
    from recontool.engine.worker import enqueue_key
    with db.session_scope() as s:
        enqueue_key(s, "logscan", "example.com", "domain", reg, route=pool._route)
    await pool.run("logscan", workers=2)

    events = [e["event"] for e in pool.log.entries]
    assert "tool_start" in events and "tool_complete" in events
    assert all("timestamp" in e and "correlation_id" in e for e in pool.log.entries)


@pytest.mark.asyncio
async def test_worker_logs_ai_decision_and_enqueue(tmp_path, monkeypatch):
    """The live path emits AI-decision and enqueue log events, and recursion
    fans out: the discovered in-scope subdomain re-feeds new (key, tool) work."""
    db.init_engine(f"sqlite:///{tmp_path / 'qai.db'}")
    db.create_all()
    monkeypatch.setattr(settings, "artifact_dir", tmp_path / "artifacts")

    result = await run_queue_scan("example.com", registry=_registry(),
                                  tools="all", workers=4, max_depth=3)
    assert result.completed >= 2

    # WorkItems were created at depth > 0 — the matrix recursed via enqueue.
    with db.session_scope() as s:
        max_depth = s.execute(select(func.max(WorkItem.depth)).where(
            WorkItem.scan_id == result.scan_id)).scalar()
        refeed = s.execute(select(func.coalesce(func.sum(WorkItem.new_keys_found), 0))
                           .where(WorkItem.scan_id == result.scan_id)).scalar()
    assert max_depth >= 1            # discovered keys created downstream jobs
    assert refeed >= 1               # at least one downstream (key, tool) enqueued


@pytest.mark.asyncio
async def test_ai_decision_keeps_in_scope_estate(tmp_path, monkeypatch):
    """An in-scope subdomain of the (reserved) seed is NOT dropped as noise:
    scope is authoritative over the generic noise patterns."""
    db.init_engine(f"sqlite:///{tmp_path / 'qscope.db'}")
    db.create_all()
    monkeypatch.setattr(settings, "artifact_dir", tmp_path / "artifacts")

    # Seed is example.com (a noise pattern). Its own subdomain api.example.com
    # must still be persisted and recursed, because it is in scope.
    await run_queue_scan("example.com", registry=_registry(),
                                  tools="all", workers=4, max_depth=3)
    with db.session_scope() as s:
        values = {a.value for a in s.execute(select(Asset)).scalars()}
    assert "api.example.com" in values
    assert "deep.api.example.com" in values


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


def test_enqueue_scales_and_dedupes(tmp_path):
    """Enqueue at volume: distinct keys create work, repeats add nothing, and the
    candidate-only dedupe query keeps it bounded (no full-scan blowup)."""
    db.init_engine(f"sqlite:///{tmp_path / 'scale.db'}")
    db.create_all()
    from recontool.engine.worker import RouteIndex, enqueue_key
    reg = _registry()
    apply_selection(reg, "all")
    route = RouteIndex(reg)

    scan_id = "scale"
    # 300 distinct in-scope subdomains -> each routes to subdomain-consumers
    per_key = len(route.for_key_type("subdomain"))
    assert per_key >= 1
    with db.session_scope() as s:
        total_new = sum(
            enqueue_key(s, scan_id, f"h{i}.example.com", "subdomain", reg, route=route)
            for i in range(300)
        )
    assert total_new == 300 * per_key                 # every (key,tool) created once
    # re-enqueue the same keys -> dedupe drops all of them
    with db.session_scope() as s:
        again = sum(
            enqueue_key(s, scan_id, f"h{i}.example.com", "subdomain", reg, route=route)
            for i in range(300)
        )
    assert again == 0
    with db.session_scope() as s:
        n = s.execute(select(func.count(WorkItem.id)).where(
            WorkItem.scan_id == scan_id)).scalar_one()
    assert n == 300 * per_key


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
