"""Integration: error-handling paths — missing keys, invalid endpoints, quota
exhaustion, pagination/parse errors — degrade gracefully (never crash a scan)."""
from __future__ import annotations

import asyncio

import pytest

from recontool.adapters.base import AdapterContext
from recontool.adapters.generic import build_adapter_class
from recontool.config import PROFILES
from recontool.core.mode import RunMode
from recontool.core.scope import Scope
from recontool.net.circuit import BudgetExhausted, BudgetLedger, CircuitOpen, CircuitRegistry
from recontool.net.http_client import HttpClient
from recontool.testing.mock_env import DEMO_APEX, MockEnv


class _NullArtifacts:
    root = None
    def save_raw(self, *a, **k): return "raw/x"
    def save_text(self, *a, **k): return "text/x"
    def save_js(self, *a, **k): return "js/x"


def _ctx(http, inputs=None):
    return AdapterContext(scan_id="x", scope=Scope.from_seed(DEMO_APEX, "domain"),
                          profile=PROFILES["normal"], http=http,
                          artifacts=_NullArtifacts(),
                          inputs=inputs or {"domain": [DEMO_APEX]}, api_keys={})


def test_missing_key_adapter_unavailable():
    spec = {"name": "needs_key_x", "phase": "p1_seed", "category": 1, "integration": "api",
            "consumes": ["domain"], "produces": ["subdomain"], "requires_key": "UNSET_KEY_X",
            "endpoint": "https://api.example.com/{domain}", "parse": {"format": "json", "emit": []}}
    cls = build_adapter_class(spec)
    http = HttpClient(mode=RunMode.DEMO, mock_env=MockEnv())
    assert cls().available(_ctx(http)) is False


def test_invalid_endpoint_returns_no_events_not_crash():
    spec = {"name": "bad_ep", "phase": "p1_seed", "category": 1, "integration": "api",
            "consumes": ["domain"], "produces": ["subdomain"],
            "endpoint": "https://nonexistent.invalid.host.local/{domain}",
            "bucket": "bad", "parse": {"format": "json", "emit": [
                {"entity": "asset", "value": "{x}", "type": "subdomain"}]}}
    cls = build_adapter_class(spec)
    # mock env returns 404 for unknown hosts -> parser yields nothing, no crash
    http = HttpClient(mode=RunMode.DEMO, mock_env=MockEnv())
    events = asyncio.run(cls().run(_ctx(http)))
    assert events == []


def test_quota_exhaustion_raises_budget_exhausted():
    budget = BudgetLedger()
    budget.set_budget("crtsh", 1)
    http = HttpClient(mode=RunMode.DEMO, mock_env=MockEnv(), budget=budget)
    asyncio.run(http.get("https://crt.sh/", bucket="crtsh"))
    with pytest.raises(BudgetExhausted):
        asyncio.run(http.get("https://crt.sh/", bucket="crtsh"))


def test_circuit_open_raises():
    circuits = CircuitRegistry(failure_threshold=1, cooldown=999)
    circuits.record("crtsh", ok=False)
    http = HttpClient(mode=RunMode.DEMO, mock_env=MockEnv(), circuits=circuits)
    with pytest.raises(CircuitOpen):
        asyncio.run(http.get("https://crt.sh/", bucket="crtsh"))


def test_malformed_json_parse_yields_nothing():
    """A non-JSON body must not crash the JSON parser path (degrades to empty)."""
    from recontool.adapters.generic import emit_events, parse_records
    recs = parse_records({"format": "json"}, "<html>not json</html>")
    # safe-json degrades to an empty object; no asset values can be emitted
    events = emit_events({"emit": [{"entity": "asset", "value": "{x}", "type": "subdomain"}]},
                         recs, "t", None)
    assert events == []
