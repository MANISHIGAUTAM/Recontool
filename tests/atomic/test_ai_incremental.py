"""Tests for model-backed AI decisioning (b) and incremental wiring (c)."""
from __future__ import annotations

import datetime as dt

import pytest

from recontool.adapters.base import Event
from recontool.config import settings
from recontool.core import db
from recontool.core.artifacts import ArtifactStore
from recontool.core.scope import Scope
from recontool.engine.ai_decision import AIDecisionService, decide_on_events_ai
from recontool.engine.fingerprint import fingerprint_inputs
from recontool.engine.incremental import IncrementalEngine
from recontool.engine.models import ToolRun
from recontool.engine.worker import _load_typed_events


# ── (b) model-backed decisioning ─────────────────────────────────────────────
class _FakeRouter:
    """Stand-in ModelRouter that flags both an in-scope and an out-of-scope value."""

    enabled = True

    async def decide_json(self, system, payload, tier="light", max_tokens=200):
        return {"drop": ["evil.com", "api.example.com"], "reason": "model judgment"}


@pytest.mark.asyncio
async def test_model_decisioning_respects_scope_floor():
    scope = Scope.from_seed("example.com", "domain")
    svc = AIDecisionService(scope=scope)
    events = [
        Event.asset("t", "subdomain", "api.example.com"),  # in scope
        Event.asset("t", "subdomain", "evil.com"),         # out of scope
    ]
    res = await decide_on_events_ai(events, "t", service=svc, router=_FakeRouter())
    persisted = {e.data["value"] for e in res.persist}
    discarded = {e.data["value"] for e in res.discard}
    # Scope floor: model wanted to drop api.example.com but it's in scope -> kept.
    assert "api.example.com" in persisted
    # Model-flagged AND out-of-scope -> dropped.
    assert "evil.com" in discarded
    assert "AI(model)" in res.reasoning


@pytest.mark.asyncio
async def test_no_router_falls_back_to_heuristic():
    scope = Scope.from_seed("example.com", "domain")
    svc = AIDecisionService(scope=scope)
    events = [Event.asset("t", "subdomain", "api.example.com")]
    res = await decide_on_events_ai(events, "t", service=svc, router=None)
    assert {e.data["value"] for e in res.persist} == {"api.example.com"}
    assert "AI(model)" not in res.reasoning


# ── (c) incremental ──────────────────────────────────────────────────────────
def test_find_fresh_completed_is_cross_scan_and_fresh(tmp_path):
    db.init_engine(f"sqlite:///{tmp_path / 'i.db'}")
    db.create_all()
    fp = fingerprint_inputs("crtsh", {"domain": ["example.com"]})
    now = dt.datetime.now(dt.timezone.utc)
    with db.session_scope() as s:
        eng = IncrementalEngine(s)
        eng.record_run(ToolRun(scan_id="scanA", tool_name="crtsh", status="completed",
                               input_fingerprint=fp, finished_at=now,
                               artifact_paths=["scanA/out/crtsh.subdomain.jsonl"]))
        eng.record_run(ToolRun(scan_id="scanOld", tool_name="crtsh", status="completed",
                               input_fingerprint="otherfp",
                               finished_at=now - dt.timedelta(hours=2)))
    with db.session_scope() as s:
        eng = IncrementalEngine(s)
        # reusable cross-scan (a different scan can skip this exact input)
        assert eng.find_fresh_completed("crtsh", fp, exclude_scan="scanB") is not None
        # excluding the owning scan -> nothing
        assert eng.find_fresh_completed("crtsh", fp, exclude_scan="scanA") is None
        # different input fingerprint -> nothing
        assert eng.find_fresh_completed("crtsh", "nope") is None
        # stale (2h old vs 1h window) -> nothing
        assert eng.find_fresh_completed("crtsh", "otherfp", max_age_seconds=3600) is None
        # within a wider window -> found
        assert eng.find_fresh_completed("crtsh", "otherfp", max_age_seconds=10800) is not None


def test_load_typed_events_reconstructs_assets_and_urls(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "artifact_dir", tmp_path / "artifacts")
    store = ArtifactStore("scanZ")
    p_sub = store.save_typed("crtsh", "subdomain", ["a.example.com"])
    p_url = store.save_typed("crtsh", "url", ["https://a.example.com/x"])
    p_find = store.save_typed("crtsh", "finding", ["some finding title"])

    events = _load_typed_events([p_sub, p_url, p_find], "crtsh")
    assert any(e.entity == "asset" and e.data.get("value") == "a.example.com" for e in events)
    assert any(e.entity == "endpoint" and e.data.get("url") == "https://a.example.com/x"
               for e in events)
    assert all(e.entity != "finding" for e in events)   # findings are skipped on reuse
    assert len(events) == 2
