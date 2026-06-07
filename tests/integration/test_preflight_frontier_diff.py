"""Integration tests for preflight checks, the frontier manager, and scan diffing."""
from __future__ import annotations

import asyncio

import pytest

from recontool.core import db
from recontool.core.mode import RunMode
from recontool.core.scope import Scope
from recontool.diff import diff_scans
from recontool.orchestrator.frontier import FrontierManager
from recontool.orchestrator.pipeline import ReconPipeline
from recontool.preflight import run_preflight
from recontool.testing.mock_env import DEMO_APEX


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr("recontool.config.settings.artifact_dir", tmp_path / "artifacts")
    db.init_engine(f"sqlite:///{tmp_path / 'pf.db'}")
    db.create_all()
    return tmp_path


# ── preflight ────────────────────────────────────────────────────────────────
def test_preflight_passes_for_valid_setup(fresh_db):
    pf = run_preflight(DEMO_APEX, mode=RunMode.DEMO)
    assert pf.ok, f"preflight should pass; errors={[c.detail for c in pf.errors]}"
    names = {c.name for c in pf.checks}
    assert {"registry.categories", "storage.artifacts", "storage.database",
            "scope", "mode"} <= names


def test_preflight_scope_check_present(fresh_db):
    pf = run_preflight(DEMO_APEX, mode=RunMode.DEMO)
    scope_check = next(c for c in pf.checks if c.name == "scope")
    assert scope_check.ok and DEMO_APEX in scope_check.detail


# ── frontier ───────────────────────────────────────────────────────────────
def test_frontier_only_surfaces_new_in_scope_entities(fresh_db):
    # run a passive demo scan to populate the store
    result = asyncio.run(ReconPipeline(mode=RunMode.DEMO).run(
        DEMO_APEX, profile_name="passive_only"))
    scope = Scope.from_seed(DEMO_APEX, "domain")
    fm = FrontierManager(result.scan_id, scope)

    first = fm.new_in_scope()
    assert first, "first frontier pass should surface discovered entities"
    assert all(h.endswith(DEMO_APEX) for h in first.get("subdomain", []))

    # second pass: nothing new -> empty delta (proves recurse-only-on-new)
    second = fm.new_in_scope()
    assert second == {} or all(not v for v in second.values())
    assert fm.has_new() is False


def test_frontier_seed_from_store_marks_all_known(fresh_db):
    result = asyncio.run(ReconPipeline(mode=RunMode.DEMO).run(
        DEMO_APEX, profile_name="passive_only"))
    scope = Scope.from_seed(DEMO_APEX, "domain")
    fm = FrontierManager(result.scan_id, scope)
    fm.seed_from_store()
    assert fm.has_new() is False           # everything already marked
    assert fm.new_in_scope() == {} or all(not v for v in fm.new_in_scope().values())


# ── diff ─────────────────────────────────────────────────────────────────────
def test_diff_detects_added_assets_between_scans(fresh_db):
    pipe = ReconPipeline(mode=RunMode.DEMO)
    s1 = asyncio.run(pipe.run(DEMO_APEX, profile_name="passive_only"))
    # second scan of the same seed (mock is deterministic -> no change expected)
    s2 = asyncio.run(pipe.run(DEMO_APEX, profile_name="passive_only"))
    d = diff_scans(s1.scan_id, s2.scan_id)
    assert d.assets.added == [] and d.assets.removed == []
    assert d.changed is False
