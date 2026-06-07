"""Unit tests for provider fixture loading, observability (trace ids/logs), and
the all-28-lanes registry guarantee."""
from __future__ import annotations

import json
import re

import pytest

from recontool.testing.fixtures import list_fixtures, load_fixture


# ── fixtures ─────────────────────────────────────────────────────────────────
def test_every_provider_fixture_loads():
    from recontool.providers import load_providers
    reg = load_providers()
    for p in reg.providers:
        if p.mock_fixture:
            data = load_fixture(p.mock_fixture)
            assert data is not None


def test_load_fixture_missing_raises():
    with pytest.raises(FileNotFoundError):
        load_fixture("providers/does_not_exist.json")


def test_load_fixture_malformed_json_raises(tmp_path, monkeypatch):
    import recontool.testing.fixtures as fx
    bad = tmp_path / "providers"
    bad.mkdir()
    (bad / "bad.json").write_text("{not valid json")
    monkeypatch.setattr(fx, "FIXTURE_ROOT", tmp_path)
    with pytest.raises(ValueError):
        fx.load_fixture("providers/bad.json")


def test_list_fixtures_nonempty():
    fixtures = list_fixtures()
    assert any(f.startswith("providers/") for f in fixtures)


# ── observability ────────────────────────────────────────────────────────────
def test_trace_id_set_and_get():
    from recontool.obs import get_trace_id, set_trace_id
    tid = set_trace_id("abc123")
    assert tid == "abc123" and get_trace_id() == "abc123"
    auto = set_trace_id()
    assert re.fullmatch(r"[0-9a-f]{16}", auto)


def test_log_event_emits_json_with_trace(capsys):
    from recontool.obs import configure_logging, log_event, set_trace_id
    configure_logging()
    set_trace_id("traceXYZ")
    log_event("test.action", foo="bar", n=3)
    err = capsys.readouterr().err.strip().splitlines()
    line = next(ln for ln in err if "test.action" in ln)
    rec = json.loads(line)
    assert rec["trace_id"] == "traceXYZ"
    assert rec["action"] == "test.action" and rec["foo"] == "bar" and rec["n"] == 3


# ── all 28 lanes represented ─────────────────────────────────────────────────
def test_all_28_lanes_have_at_least_one_adapter():
    from recontool.adapters.registry import all_adapters, load_builtin
    load_builtin()
    cats = set()
    for c in all_adapters().values():
        m = re.search(r"(\d+)", c.category or "")
        if m:
            cats.add(int(m.group(1)))
    missing = set(range(1, 29)) - cats
    assert not missing, f"lanes with no adapter: {sorted(missing)}"


def test_disabled_specs_register_but_unavailable():
    """Lane-completeness specs (enabled:false) are registered but not available."""
    from recontool.adapters.base import AdapterContext
    from recontool.adapters.registry import all_adapters, load_builtin
    from recontool.config import PROFILES
    from recontool.core.scope import Scope
    load_builtin()
    ad = all_adapters()
    # hunter_emails is enabled:false in tools_generic.yaml
    assert "hunter_emails" in ad
    ctx = AdapterContext(scan_id="x", scope=Scope.from_seed("example.com", "domain"),
                         profile=PROFILES["normal"], http=None, artifacts=None,
                         inputs={}, api_keys={})
    assert ad["hunter_emails"]().available(ctx) is False
