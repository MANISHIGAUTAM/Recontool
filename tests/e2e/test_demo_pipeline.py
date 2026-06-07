"""End-to-end tests of the FULL pipeline against the in-process mock environment.

These prove the complete seed -> discovery -> normalize -> live-validate ->
enrich -> active-detect flow works without ever touching a real target, and that
demo/test mode HARD-BLOCKS live egress (the spec's test-mode enforcement).
"""
from __future__ import annotations

import asyncio

import pytest

from recontool.core import db
from recontool.core.mode import LiveEgressBlocked, RunMode
from recontool.core.models import Asset, Checkpoint, Endpoint, Finding
from recontool.net.http_client import HttpClient
from recontool.orchestrator.pipeline import ReconPipeline
from recontool.testing.mock_env import DEMO_APEX, MockEnv
from sqlalchemy import func, select


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr("recontool.config.settings.artifact_dir", tmp_path / "artifacts")
    db.init_engine(f"sqlite:///{tmp_path / 'e2e.db'}")
    db.create_all()
    return tmp_path


def _run(seed, **kw):
    pipe = ReconPipeline(mode=RunMode.DEMO, max_recursion=2)
    return asyncio.run(pipe.run(seed, **kw))


def test_demo_passive_pipeline_discovers_surface(fresh_db):
    result = _run(DEMO_APEX, profile_name="passive_only")
    assert result.mode == "demo"
    # passive phases ran; active gated out by passive_only profile
    phases = {p.phase for p in result.phases}
    assert {"p1_seed", "p2_expansion", "p3_enrichment"} <= phases
    assert not result.active_ran

    with db.session_scope() as s:
        subs = s.execute(
            select(Asset.value).where(Asset.scan_id == result.scan_id,
                                      Asset.type == "subdomain")
        ).scalars().all()
    # mock CT/hackertarget/otx should have produced in-scope subdomains
    assert any(h.endswith(DEMO_APEX) for h in subs)
    assert f"www.{DEMO_APEX}" in subs or f"api.{DEMO_APEX}" in subs


def test_demo_full_active_pipeline_end_to_end(fresh_db):
    result = _run(DEMO_APEX, profile_name="normal", authorize_active=True)
    assert result.active_ran is True
    phases = {p.phase for p in result.phases}
    assert {"p4_verify", "p5_deep", "p6_vuln"} <= phases

    with db.session_scope() as s:
        live = s.execute(
            select(func.count()).where(Asset.scan_id == result.scan_id,
                                       Asset.is_live.is_(True))
        ).scalar()
        endpoints = s.execute(
            select(func.count()).select_from(Endpoint).where(
                Endpoint.asset_id.in_(
                    select(Asset.id).where(Asset.scan_id == result.scan_id)))
        ).scalar()
        secrets = s.execute(
            select(func.count()).where(Finding.scan_id == result.scan_id,
                                       Finding.kind == "secret")
        ).scalar()
    assert live > 0, "live validation should mark mock hosts live"
    assert endpoints > 0, "crawl/content discovery should yield endpoints"
    # mock JS contains a fake AWS key -> secret finding (redacted)
    assert secrets > 0, "JS analysis should detect the planted (fake) secret"


def test_checkpoints_written_per_phase(fresh_db):
    result = _run(DEMO_APEX, profile_name="normal", authorize_active=True)
    with db.session_scope() as s:
        cps = s.execute(
            select(Checkpoint.phase).where(Checkpoint.scan_id == result.scan_id)
        ).scalars().all()
    assert {"p1_seed", "p4_verify", "p6_vuln"} <= set(cps)


def test_resume_skips_completed_phases(fresh_db):
    first = _run(DEMO_APEX, profile_name="passive_only")
    # resume the same scan: all passive phases already checkpointed -> skipped
    pipe = ReconPipeline(mode=RunMode.DEMO)
    resumed = asyncio.run(pipe.run(DEMO_APEX, profile_name="passive_only",
                                   resume_scan_id=first.scan_id))
    assert resumed.resumed is True
    assert resumed.scan_id == first.scan_id
    # no passive phase re-ran (they were checkpointed)
    assert all(p.phase not in ("p1_seed", "p2_expansion", "p3_enrichment")
               for p in resumed.phases)


def test_test_mode_blocks_live_egress_without_mock():
    """In TEST mode with no mock env, any egress attempt must hard-fail."""
    client = HttpClient(mode=RunMode.TEST, mock_env=None)
    with pytest.raises(LiveEgressBlocked):
        asyncio.run(client.get("https://example.com/"))


def test_demo_mode_routes_through_mock_only():
    """DEMO mode serves from the mock env and never raises / never hits network."""
    env = MockEnv()
    client = HttpClient(mode=RunMode.DEMO, mock_env=env)
    resp = asyncio.run(client.get("https://crt.sh/?q=%25.demo.recontool.local&output=json"))
    assert resp.status == 200 and resp.json_ok
    assert client.last_egress == "mock"
    assert env.calls, "mock env should have logged the request"
