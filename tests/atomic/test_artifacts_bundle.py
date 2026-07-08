"""Artifact-path logging + final scan-bundle manifest (roadmap §10 + §8-M6)."""
from __future__ import annotations

import json

from recontool.adapters.base import Event
from recontool.config import settings
from recontool.core import db
from recontool.core.artifacts import ArtifactStore
from recontool.core.models import Asset, Finding, Scan
from recontool.engine.logging import _format_human
from recontool.engine.models import WorkItem
from recontool.engine.runner import write_scan_bundle, write_typed_outputs


def test_write_typed_outputs_returns_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "artifact_dir", tmp_path / "artifacts")
    store = ArtifactStore("scanX")
    events = [
        Event.asset("crtsh", "subdomain", "a.example.com"),
        Event.asset("crtsh", "subdomain", "b.example.com"),
        Event.endpoint("crtsh", "https://a.example.com/"),
    ]
    paths = write_typed_outputs(store, "crtsh", events)
    assert any("crtsh.subdomain.jsonl" in p for p in paths)
    assert any("crtsh.url.jsonl" in p for p in paths)


def test_scan_bundle_indexes_db_and_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "artifact_dir", tmp_path / "artifacts")
    db.init_engine(f"sqlite:///{tmp_path / 'b.db'}")
    db.create_all()
    with db.session_scope() as s:
        s.add(Scan(id="scanB", seed="example.com", seed_type="domain",
                   profile="normal", status="done", scope_json="{}",
                   active_authorized=True))
        s.add(Asset(scan_id="scanB", type="subdomain", value="a.example.com",
                    dedupe_key="k1", confidence=0.9))
        s.add(Finding(scan_id="scanB", kind="exposure", title="x", severity="high",
                      detector="d", dedupe_key="f1"))
        s.add(WorkItem(scan_id="scanB", key="example.com", key_type="domain",
                       tool_slug="crtsh", dedupe_key="w0", status="completed", depth=2))
    ArtifactStore("scanB").save_typed("crtsh", "subdomain", ["a.example.com"])

    path = write_scan_bundle("scanB")
    assert path and path.endswith("scan_bundle.json")
    data = json.loads((settings.artifact_dir / path).read_text())
    assert data["scan_id"] == "scanB"
    assert data["assets_by_type"]["subdomain"] == 1
    assert data["findings_count"] == 1
    assert data["recursion"]["max_depth"] == 2
    assert any("crtsh.subdomain.jsonl" in p for p in data["artifacts"]["typed_outputs"])


def test_tool_complete_log_line_shows_key_and_path():
    line = _format_human({
        "event": "tool_complete", "tool_name": "crtsh", "entity_count": 3,
        "duration_ms": 12, "key_type": "domain",
        "artifact_paths": ["scanB/out/crtsh.subdomain.jsonl"],
    })
    assert "crtsh" in line and "[domain]" in line and "crtsh.subdomain.jsonl" in line
