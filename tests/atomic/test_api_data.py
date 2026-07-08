"""Tests for the API/UI data layer (pure DB reads, no web stack required)."""
from __future__ import annotations

import importlib.util

import pytest

from recontool.api import data
from recontool.core import db
from recontool.core.models import Asset, Edge, Finding, Scan
from recontool.engine.models import WorkItem


@pytest.fixture()
def seeded(tmp_path):
    db.init_engine(f"sqlite:///{tmp_path / 'api.db'}")
    db.create_all()
    with db.session_scope() as s:
        s.add(Scan(id="scanA", seed="example.com", seed_type="domain",
                   profile="normal", status="done", scope_json="{}",
                   active_authorized=True))
        s.add(Asset(scan_id="scanA", type="subdomain", value="api.example.com",
                    dedupe_key="k1", confidence=0.9, is_live=True))
        s.add(Asset(scan_id="scanA", type="ip", value="1.2.3.4",
                    dedupe_key="k2", confidence=0.5))
        s.add(Edge(scan_id="scanA", src="api.example.com", dst="1.2.3.4",
                   rel="resolves_to"))
        s.add(Finding(scan_id="scanA", kind="exposure", title="exposed thing",
                      severity="high", detector="d", dedupe_key="f1",
                      asset_value="api.example.com"))
        s.add(WorkItem(scan_id="scanA", key="example.com", key_type="domain",
                       tool_slug="crtsh", dedupe_key="w0", status="completed",
                       depth=0, new_keys_found=2))
        s.add(WorkItem(scan_id="scanA", key="api.example.com", key_type="subdomain",
                       tool_slug="dns_resolve", dedupe_key="w1",
                       status="completed", depth=1))
    return "scanA"


def test_list_scans(seeded):
    assert any(r["scan_id"] == "scanA" for r in data.list_scans())


def test_scan_overview(seeded):
    o = data.scan_overview("scanA")
    assert o["assets_total"] == 2
    assert o["assets_by_type"]["subdomain"] == 1
    assert o["live_assets"] == 1
    assert o["findings"] == 1
    assert o["queue"]["max_depth"] == 1
    assert o["queue"]["downstream_enqueued"] == 2


def test_overview_missing_scan(seeded):
    assert data.scan_overview("nope") is None


def test_assets_filter_and_findings(seeded):
    subs = data.list_assets("scanA", atype="subdomain")
    assert len(subs) == 1 and subs[0]["value"] == "api.example.com"
    fs = data.list_findings("scanA")
    assert fs and fs[0]["severity"] == "high"


def test_graph(seeded):
    g = data.graph("scanA")
    assert g["node_count"] == 2 and g["edge_count"] == 1
    assert g["edges"][0]["rel"] == "resolves_to"


def test_list_tools_and_summary():
    """Pure capability matrix the UI 'Tools' tab renders — no web stack needed."""
    rows = data.list_tools()
    assert rows, "catalog should yield tools"
    sample = rows[0]
    for key in ("slug", "name", "runnable", "default_on", "web_only", "source"):
        assert key in sample
    runnable = data.list_tools(runnable_only=True)
    assert 0 < len(runnable) < len(rows)
    assert all(t["runnable"] for t in runnable)
    summ = data.tools_summary()
    assert summ["total"] == len(rows)
    assert summ["runnable"] == len(runnable)
    assert summ["runnable"] >= 1 and summ["default_on"] >= 1
    assert summ["web_only"] >= 0 and summ["runnable"] <= summ["total"]


def test_app_constructs_when_fastapi_present():
    if importlib.util.find_spec("fastapi") is None:
        pytest.skip("fastapi not installed (optional API extra)")
    from recontool.api.app import create_app

    assert create_app() is not None


def _client(monkeypatch):
    """A TestClient with a known token configured (fastapi-only).

    Uses monkeypatch so the global ``settings.api_token`` is restored after the
    test and can't leak into the rest of the suite."""
    from fastapi.testclient import TestClient

    from recontool.api.app import create_app
    from recontool.config import settings
    monkeypatch.setattr(settings, "api_token", "test-token")
    return TestClient(create_app())


def test_ui_is_served(seeded, monkeypatch):
    if importlib.util.find_spec("fastapi") is None:
        pytest.skip("fastapi not installed (optional API extra)")
    c = _client(monkeypatch)
    r = c.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert "RECON" in body and "control surface" in body
    # self-contained: no external resource references (no CDN phone-home),
    # regardless of scheme (http/https) or mechanism (tag src/href, fetch, CSS url/@import).
    for ext in ('src="http', "src='http", 'href="http', "href='http",
                'fetch("http', "fetch('http", "url(http", "@import"):
        assert ext not in body, f"UI must be self-contained; found external ref {ext!r}"


def test_tools_route_auth_gated(seeded, monkeypatch):
    if importlib.util.find_spec("fastapi") is None:
        pytest.skip("fastapi not installed (optional API extra)")
    c = _client(monkeypatch)
    assert c.get("/tools").status_code == 401          # no bearer
    ok = c.get("/tools", headers={"Authorization": "Bearer test-token"})
    assert ok.status_code == 200 and isinstance(ok.json(), list) and ok.json()
    summ = c.get("/tools/summary", headers={"Authorization": "Bearer test-token"})
    assert summ.status_code == 200 and summ.json()["total"] >= 1
