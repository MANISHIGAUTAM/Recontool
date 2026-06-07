"""Atomic checks for run-mode parsing + HttpClient egress gating, circuit & budget
enforcement. All network-free."""
from __future__ import annotations

import asyncio

import pytest

from recontool.core.mode import LiveEgressBlocked, RunMode
from recontool.net.circuit import BudgetExhausted, BudgetLedger, CircuitOpen, CircuitRegistry
from recontool.net.http_client import HttpClient
from recontool.testing.mock_env import MockEnv


# ── RunMode ─────────────────────────────────────────────────────────────────
def test_runmode_parse_and_properties():
    assert RunMode.parse("demo") is RunMode.DEMO
    assert RunMode.parse("TEST") is RunMode.TEST
    assert RunMode.parse(None) is RunMode.LIVE
    assert RunMode.parse("garbage") is RunMode.LIVE
    assert RunMode.LIVE.allows_real_egress is True
    assert RunMode.DEMO.allows_real_egress is False
    assert RunMode.TEST.uses_mock and RunMode.DEMO.uses_mock
    assert RunMode.LIVE.uses_mock is False


# ── egress gating ────────────────────────────────────────────────────────────
def test_test_mode_without_mock_blocks_egress():
    client = HttpClient(mode=RunMode.TEST, mock_env=None)
    with pytest.raises(LiveEgressBlocked):
        asyncio.run(client.get("https://api.shodan.io/x"))


def test_demo_mode_with_mock_serves_response():
    client = HttpClient(mode=RunMode.DEMO, mock_env=MockEnv())
    r = asyncio.run(client.get("https://crt.sh/?q=%25.recontool.local&output=json"))
    assert r.status == 200 and r.json_ok and client.last_egress == "mock"


# ── circuit breaker enforcement (uses mock so no real egress) ────────────────
def test_circuit_open_blocks_request():
    circuits = CircuitRegistry(failure_threshold=1, cooldown=999)
    circuits.record("crtsh", ok=False)  # trip immediately
    client = HttpClient(mode=RunMode.DEMO, mock_env=MockEnv(), circuits=circuits)
    # bucket name 'crtsh' is OPEN -> fail fast before serving
    with pytest.raises(CircuitOpen):
        asyncio.run(client.get("https://crt.sh/", bucket="crtsh"))


def test_budget_exhausted_blocks_request():
    budget = BudgetLedger()
    budget.set_budget("crtsh", 1)
    client = HttpClient(mode=RunMode.DEMO, mock_env=MockEnv(), budget=budget)
    # first call spends the only unit
    asyncio.run(client.get("https://crt.sh/", bucket="crtsh"))
    with pytest.raises(BudgetExhausted):
        asyncio.run(client.get("https://crt.sh/", bucket="crtsh"))
