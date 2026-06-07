"""Integration tests for discovery -> normalize -> enrichment CHAINS.

Each test wires a real adapter to the real Normalizer + DB (mock HTTP only),
proving the handoff between stages works — not just isolated parse logic.
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from recontool.adapters.base import AdapterContext
from recontool.adapters.passive import CrtSh, HackerTarget
from recontool.adapters.internet_search import InternetDB
from recontool.config import PROFILES
from recontool.core import db
from recontool.core.artifacts import ArtifactStore
from recontool.core.models import Asset, Edge, Service
from recontool.core.mode import RunMode
from recontool.core.scope import Scope
from recontool.net.http_client import HttpClient
from recontool.normalize.engine import Normalizer
from recontool.testing.mock_env import DEMO_APEX, MockEnv


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr("recontool.config.settings.artifact_dir", tmp_path)
    db.init_engine(f"sqlite:///{tmp_path / 'integ.db'}")
    db.create_all()
    scan_id = "integ01"
    from recontool.core.models import Scan
    with db.session_scope() as s:
        s.add(Scan(id=scan_id, seed=DEMO_APEX, seed_type="domain",
                   profile="normal", status="running", scope_json={}))
    scope = Scope.from_seed(DEMO_APEX, "domain")
    http = HttpClient(mode=RunMode.DEMO, mock_env=MockEnv(apex=DEMO_APEX))
    ctx = AdapterContext(scan_id=scan_id, scope=scope, profile=PROFILES["normal"],
                         http=http, artifacts=ArtifactStore(scan_id),
                         inputs={"domain": [DEMO_APEX]}, api_keys={})
    return scan_id, ctx, scope


def _ingest(scan_id, scope, events):
    with db.session_scope() as s:
        return Normalizer(s, scan_id, scope=scope).ingest(events)


def test_crtsh_to_canonical_assets(env):
    scan_id, ctx, scope = env
    events = asyncio.run(CrtSh().run(ctx))
    counts = _ingest(scan_id, scope, events)
    assert counts["asset"] > 0
    with db.session_scope() as s:
        subs = s.execute(select(Asset.value).where(
            Asset.scan_id == scan_id, Asset.type == "subdomain")).scalars().all()
    assert all(h.endswith(DEMO_APEX) for h in subs)
    assert f"www.{DEMO_APEX}" in subs


def test_hackertarget_chain_creates_resolves_to_edges(env):
    scan_id, ctx, scope = env
    events = asyncio.run(HackerTarget().run(ctx))
    _ingest(scan_id, scope, events)
    with db.session_scope() as s:
        edges = s.execute(select(Edge).where(
            Edge.scan_id == scan_id, Edge.rel == "resolves_to")).scalars().all()
        ips = s.execute(select(Asset).where(
            Asset.scan_id == scan_id, Asset.type == "ip")).scalars().all()
    assert edges, "host->ip resolves_to edges must be recorded"
    assert ips, "IP assets must be created from hostsearch"


def test_internetdb_ip_to_service_and_finding_chain(env):
    scan_id, ctx, scope = env
    # seed an in-scope IP and feed it to InternetDB enrichment
    _ingest(scan_id, scope, [
        __import__("recontool.adapters.base", fromlist=["Event"]).Event.asset(
            "seed", "ip", "192.0.2.50")])
    # widen scope to include the demo IP range so enrichment is allowed
    scope.allow_cidrs.append("192.0.2.0/24")
    scope.__post_init__()
    ctx.inputs = {"ip": ["192.0.2.50"]}
    events = asyncio.run(InternetDB().run(ctx))
    counts = _ingest(scan_id, scope, events)
    assert counts["service"] > 0
    with db.session_scope() as s:
        svcs = s.execute(select(Service)).scalars().all()
    assert {sv.port for sv in svcs} & {80, 443, 22}
