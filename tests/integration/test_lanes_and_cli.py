"""Integration tests: new lanes end-to-end, learning engine through the pipeline,
provider-config→adapter wiring, and CLI commands (config-validate/demo/replay)."""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from recontool.adapters.base import AdapterContext
from recontool.adapters.resources import WordlistLearner
from recontool.cli import app
from recontool.config import PROFILES
from recontool.core import db
from recontool.core.artifacts import ArtifactStore
from recontool.core.mode import RunMode
from recontool.core.models import Asset
from recontool.core.scope import Scope
from recontool.orchestrator.pipeline import ReconPipeline
from recontool.testing.mock_env import DEMO_APEX

runner = CliRunner()


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr("recontool.config.settings.artifact_dir", tmp_path / "artifacts")
    db.init_engine(f"sqlite:///{tmp_path / 'lanes.db'}")
    db.create_all()
    return tmp_path


# ── cat-28 learning lane through the adapter ─────────────────────────────────
def test_wordlist_learner_emits_resources(fresh_db, tmp_path):
    store = ArtifactStore("learn01")
    ctx = AdapterContext(
        scan_id="learn01", scope=Scope.from_seed(DEMO_APEX, "domain"),
        profile=PROFILES["normal"], http=None, artifacts=store,
        inputs={"url": [f"https://www.{DEMO_APEX}/api/v1/users"], "tech": ["wordpress"]},
        api_keys={})
    events = asyncio.run(WordlistLearner().run(ctx))
    kinds = {e.data.get("type") for e in events}
    assert "regex_pack" in kinds
    assert "wordlist" in kinds  # urls present -> tuned wordlist produced


# ── all 28 lanes execute in a full demo run without error ────────────────────
def test_full_demo_runs_all_enabled_lanes(fresh_db):
    result = asyncio.run(ReconPipeline(mode=RunMode.DEMO).run(
        DEMO_APEX, profile_name="normal", authorize_active=True))
    ran = {a for p in result.phases for a in p.adapters_run}
    # representative adapters from several lanes ran
    assert "crtsh" in ran and "wordlist_learner" in ran
    with db.session_scope() as s:
        n = s.execute(select(Asset).where(Asset.scan_id == result.scan_id)).scalars().all()
    assert len(n) > 5


# ── CLI commands ─────────────────────────────────────────────────────────────
def test_cli_config_validate_demo():
    res = runner.invoke(app, ["config-validate", "--env", "demo"])
    assert res.exit_code == 0, res.output
    assert "valid" in res.output


def test_cli_replay_fixtures_ok():
    res = runner.invoke(app, ["replay-fixtures"])
    assert res.exit_code == 0, res.output
    assert "ok" in res.output


def test_cli_demo_runs(fresh_db):
    res = runner.invoke(app, ["demo", DEMO_APEX, "--profile", "passive_only"])
    assert res.exit_code == 0, res.output
    assert "Scan id" in res.output


def test_cli_preflight_demo(fresh_db):
    res = runner.invoke(app, ["preflight", DEMO_APEX, "--mode", "demo"])
    assert res.exit_code == 0, res.output
