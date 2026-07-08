"""Atomic check: JS file content IS written to local storage and analyzed.

Network-free proof of the requirement "any js file content in local storage":
  1. ArtifactStore.save_js writes JS bytes/text to artifacts/<scan>/js/<host>/.
  2. js_analyze reads those files back, extracts endpoints, and detects secrets
     (stored REDACTED: hash + mask + location, never the raw secret).
"""
from __future__ import annotations

import asyncio

from recontool.adapters.active import JsAnalyze
from recontool.adapters.base import AdapterContext
from recontool.config import PROFILES, settings
from recontool.core.artifacts import ArtifactStore
from recontool.core.scope import Scope

SAMPLE_JS = """
(function(){
  var api = "/api/internal/users";
  fetch("https://api.example.com/v2/orders");
  var awsKey = "AKIAIOSFODNN7EXAMPLE";
  var gKey = "AIzaSyA1234567890abcdefghijklmnopqrstuvz";
})();
"""


def test_js_saved_to_local_storage_and_analyzed(tmp_path, monkeypatch):
    # point the artifact store at a temp dir
    monkeypatch.setattr(settings, "artifact_dir", tmp_path)
    scan_id = "jsstore01"
    store = ArtifactStore(scan_id)

    # 1. save JS content to local storage
    ref = store.save_js("app.example.com", "main.js", SAMPLE_JS)
    saved = tmp_path / ref
    assert saved.exists(), "JS file was not written to local storage"
    assert "AKIAIOSFODNN7EXAMPLE" in saved.read_text()
    assert ref.startswith(f"{scan_id}/js/")  # correct layout

    # 2. js_analyze reads the harvested js_file back (M5: keyed on the js_file asset
    #    pycrawl emits — an absolute path — not a blind scan of the whole js dir).
    ctx = AdapterContext(
        scan_id=scan_id, scope=Scope.from_seed("example.com", "domain"),
        profile=PROFILES["normal"], http=None, artifacts=store,
        inputs={"js_file": [str(saved)]}, api_keys={},
    )
    events = asyncio.run(JsAnalyze().run(ctx))

    endpoints = [e for e in events if e.entity == "endpoint"]
    findings = [e for e in events if e.entity == "finding"]

    # endpoints extracted from the JS
    urls = " ".join(e.data["url"] for e in endpoints)
    assert "/api/internal/users" in urls or "api.example.com" in urls

    # secrets detected and REDACTED (no raw secret persisted)
    assert findings, "no secret finding emitted from JS"
    f = findings[0].data
    assert f["kind"] == "secret"
    ev = f["evidence_redacted"]
    assert ev["sha1"] and ev["file"].endswith(".js")
    assert "AKIAIOSFODNN7EXAMPLE" not in str(ev), "raw secret must NOT be stored"
    assert "*" in ev["preview"]  # masked


def test_save_js_handles_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "artifact_dir", tmp_path)
    store = ArtifactStore("jsbytes")
    ref = store.save_js("h.example.com", "x", b"console.log(1)")
    assert (tmp_path / ref).read_bytes() == b"console.log(1)"
