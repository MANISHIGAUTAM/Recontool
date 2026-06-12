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


def test_app_constructs_when_fastapi_present():
    if importlib.util.find_spec("fastapi") is None:
        pytest.skip("fastapi not installed (optional API extra)")
    from recontool.api.app import create_app

    assert create_app() is not None
