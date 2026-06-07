"""Recorded-fixture regression test.

The mock environment is a deterministic fixture set. This test snapshots the
canonical SHAPE of a full demo scan (asset-type counts, live count, finding kinds)
and asserts it stays stable across runs — catching regressions in any adapter,
parser, or the normalizer. Update EXPECTED deliberately when behavior changes.
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select

from recontool.core import db
from recontool.core.mode import RunMode
from recontool.core.models import Asset, Finding
from recontool.orchestrator.pipeline import ReconPipeline
from recontool.testing.mock_env import DEMO_APEX


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr("recontool.config.settings.artifact_dir", tmp_path / "artifacts")
    db.init_engine(f"sqlite:///{tmp_path / 'fx.db'}")
    db.create_all()
    return tmp_path


def _snapshot(scan_id) -> dict:
    with db.session_scope() as s:
        by_type = dict(s.execute(
            select(Asset.type, func.count()).where(Asset.scan_id == scan_id)
            .group_by(Asset.type)).all())
        live = s.execute(select(func.count()).where(
            Asset.scan_id == scan_id, Asset.is_live.is_(True))).scalar()
        finding_kinds = dict(s.execute(
            select(Finding.kind, func.count()).where(Finding.scan_id == scan_id)
            .group_by(Finding.kind)).all())
    return {"by_type": by_type, "live": live, "finding_kinds": finding_kinds}


def test_demo_scan_is_deterministic_across_runs(fresh_db):
    pipe = ReconPipeline(mode=RunMode.DEMO)
    r1 = asyncio.run(pipe.run(DEMO_APEX, profile_name="normal", authorize_active=True))
    snap1 = _snapshot(r1.scan_id)
    r2 = asyncio.run(pipe.run(DEMO_APEX, profile_name="normal", authorize_active=True))
    snap2 = _snapshot(r2.scan_id)
    assert snap1 == snap2, f"demo scan not deterministic: {snap1} != {snap2}"


def test_demo_scan_meets_minimum_surface(fresh_db):
    """Regression floor: the demo scan must always discover a baseline surface."""
    pipe = ReconPipeline(mode=RunMode.DEMO)
    r = asyncio.run(pipe.run(DEMO_APEX, profile_name="normal", authorize_active=True))
    snap = _snapshot(r.scan_id)
    assert snap["by_type"].get("subdomain", 0) >= 8, snap
    assert snap["by_type"].get("ip", 0) >= 1, snap
    assert snap["live"] >= 1, snap
    assert snap["finding_kinds"].get("secret", 0) >= 1, snap
