"""Integration: provider config + recorded fixtures drive adapter execution
without any network, and demo mode makes zero live provider calls."""
from __future__ import annotations

import asyncio

import pytest

from recontool.adapters.base import AdapterContext
from recontool.adapters.generic import GenericApiAdapter, build_adapter_class
from recontool.config import PROFILES
from recontool.core.mode import LiveEgressBlocked, RunMode
from recontool.core.scope import Scope
from recontool.net.http_client import HttpClient
from recontool.providers import load_providers
from recontool.testing.fixtures import load_fixture
from recontool.testing.mock_env import DEMO_APEX, MockEnv


def test_provider_registry_initializes_adapter_endpoints():
    """Every enabled provider exposes a resolvable endpoint URL (adapter init)."""
    reg = load_providers()
    for p in reg.enabled():
        # at least one endpoint resolves to an absolute URL
        assert p.endpoints, f"{p.name} has no endpoints"
        for name in p.endpoints:
            url = p.endpoint(name)
            assert url.startswith(("http://", "https://")), f"{p.name}.{name}={url}"


def test_fixture_backed_generic_adapter_executes_without_network():
    """A generic API adapter, run in demo mode against MockEnv, yields events with
    no real egress — proving fixture/mock-driven adapter execution."""
    spec = {
        "name": "crtsh_test", "phase": "p1_seed", "category": 2, "integration": "api",
        "consumes": ["domain"], "produces": ["subdomain"],
        "endpoint": "https://crt.sh/?q=%25.{domain}&output=json",
        "bucket": "crtsh",
        "parse": {"format": "json", "emit": [
            {"entity": "asset", "value": "{name_value}", "type": "subdomain",
             "scope_filter": "subdomain"}]},
    }
    cls = build_adapter_class(spec)
    assert issubclass(cls, GenericApiAdapter)
    http = HttpClient(mode=RunMode.DEMO, mock_env=MockEnv(apex=DEMO_APEX))
    ctx = AdapterContext(scan_id="x", scope=Scope.from_seed(DEMO_APEX, "domain"),
                         profile=PROFILES["normal"], http=http,
                         artifacts=_NullArtifacts(), inputs={"domain": [DEMO_APEX]},
                         api_keys={})
    events = asyncio.run(cls().run(ctx))
    subs = [e.data["value"] for e in events if e.entity == "asset"]
    assert any(s.endswith(DEMO_APEX) for s in subs)
    assert http.last_egress == "mock"


def test_demo_mode_makes_zero_live_calls():
    """A live HttpClient in test mode (no mock) must raise rather than egress."""
    http = HttpClient(mode=RunMode.TEST, mock_env=None)
    with pytest.raises(LiveEgressBlocked):
        asyncio.run(http.get("https://crt.sh/"))


def test_fixture_shape_matches_parser_expectations():
    """crtsh fixture parses into the same shape the real adapter expects."""
    data = load_fixture("providers/crtsh.json")
    assert isinstance(data, list) and "name_value" in data[0]


class _NullArtifacts:
    """Minimal artifact store stub for adapter runs that call save_raw/save_text."""
    root = None

    def save_raw(self, *a, **k):
        return "raw/x"

    def save_text(self, *a, **k):
        return "text/x"

    def save_js(self, *a, **k):
        return "js/x"
