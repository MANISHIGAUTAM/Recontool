"""Pipeline-layer invariants — the E2E contract the engine must always hold:

  artifact storage  -> raw saved per tool; typed output APPENDED, never overwritten
  AI key-extraction -> discovered_assets pulls recursable primary keys (deduped),
                       endpoints/findings are terminal (don't recurse)
  normalize + dedup -> re-discovery upserts (no dup) and raises confidence
  recursion enqueue -> only NEW (key,tool) work items are created

These are fast, container-free unit tests that lock each layer independently so a
regression in any one is caught without a full scan.
"""
from __future__ import annotations

import json

from recontool.adapters.base import Event
from recontool.config import settings
from recontool.core import db
from recontool.core.artifacts import ArtifactStore


# ── artifact storage: append-not-overwrite (the "output not overwritten" rule) ──
def test_save_typed_appends_across_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "artifact_dir", tmp_path)
    store = ArtifactStore("scanX")
    store.save_typed("crtsh", "subdomain", ["a.example.com"])            # key 1
    store.save_typed("crtsh", "subdomain", ["b.example.com", "c.example.com"])  # key 2
    p = tmp_path / "scanX" / "out" / "crtsh.subdomain.jsonl"
    lines = p.read_text().strip().splitlines()
    assert len(lines) == 3                          # appended, NOT truncated to 2
    vals = {json.loads(line)["value"] for line in lines}
    assert vals == {"a.example.com", "b.example.com", "c.example.com"}


def test_save_typed_separates_by_type(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "artifact_dir", tmp_path)
    store = ArtifactStore("scanY")
    store.save_typed("httpx", "url", ["https://x"])
    store.save_typed("httpx", "ip", ["1.2.3.4"])
    out = tmp_path / "scanY" / "out"
    assert (out / "httpx.url.jsonl").exists() and (out / "httpx.ip.jsonl").exists()


def test_save_raw_stored_per_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "artifact_dir", tmp_path)
    rel = ArtifactStore("scanZ").save_raw("urlscan", {"results": [1, 2]})
    assert (tmp_path / rel).exists() and "raw/urlscan" in rel


# ── AI / recursion key-extraction ───────────────────────────────────────────
def test_discovered_assets_pulls_deduped_keys_and_skips_terminal():
    from recontool.engine.runner import discovered_assets
    evs = [
        Event.asset("t", "subdomain", "a.example.com"),
        Event.asset("t", "subdomain", "a.example.com"),   # dup -> collapses
        Event.endpoint("t", "https://a.example.com/x"),    # terminal -> not a key
        Event.finding("t", "exposure", "leak"),            # terminal -> not a key
    ]
    keys = discovered_assets(evs)
    assert ("subdomain", "a.example.com") in keys
    assert sum(1 for k in keys if k[0] == "subdomain") == 1      # deduped
    assert all(k[0] not in ("endpoint", "finding") for k in keys)  # terminal excluded


# ── normalize + dedup: re-discovery upserts + raises confidence ─────────────
def test_reingest_dedups_and_raises_confidence(scan_db):
    from sqlalchemy import func, select

    from recontool.core.models import Asset
    from recontool.normalize.engine import Normalizer
    with db.session_scope() as s:
        Normalizer(s, scan_db).ingest([Event.asset("crtsh", "subdomain", "api.example.com")])
    with db.session_scope() as s:
        Normalizer(s, scan_db).ingest([Event.asset("subfinder", "subdomain", "api.example.com")])
    with db.session_scope() as s:
        n = s.execute(select(func.count(Asset.id)).where(
            Asset.scan_id == scan_db, Asset.type == "subdomain")).scalar_one()
        a = s.execute(select(Asset).where(Asset.scan_id == scan_db)).scalars().first()
        srcs = len(a.sources)
    assert n == 1            # one canonical asset, not two (dedup)
    assert srcs == 2         # two distinct source tools recorded (confidence basis)
    assert a.confidence > 0  # noisy-OR over distinct sources


# ── runner typed-output routing appends per type ────────────────────────────
def test_write_typed_outputs_appends_per_type(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "artifact_dir", tmp_path)
    from recontool.engine.runner import write_typed_outputs
    store = ArtifactStore("scanW")
    evs1 = [Event.asset("subfinder", "subdomain", "a.example.com")]
    evs2 = [Event.asset("subfinder", "subdomain", "b.example.com")]
    write_typed_outputs(store, "subfinder", evs1)
    write_typed_outputs(store, "subfinder", evs2)   # second key-run
    p = tmp_path / "scanW" / "out" / "subfinder.subdomain.jsonl"
    assert len(p.read_text().strip().splitlines()) == 2   # accumulated
