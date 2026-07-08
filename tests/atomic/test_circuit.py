"""Atomic checks for provider-aware reliability primitives (no-evasion policy):
circuit breaker state machine + per-run budget ledger. Deterministic via an
injected clock (no real sleeping)."""
from __future__ import annotations

from recontool.net.circuit import BudgetLedger, CircuitBreaker, CircuitRegistry, State


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, secs):
        self.t += secs


# ── circuit breaker ──────────────────────────────────────────────────────────
def test_breaker_trips_open_after_threshold():
    clk = FakeClock()
    b = CircuitBreaker(failure_threshold=3, cooldown=30, clock=clk)
    assert b.state is State.CLOSED and b.allow()
    b.record_failure()
    b.record_failure()
    assert b.state is State.CLOSED                 # not yet
    b.record_failure()                              # 3rd -> trip
    assert b.state is State.OPEN
    assert b.allow() is False                       # fails fast while open


def test_breaker_half_open_then_close_on_success():
    clk = FakeClock()
    b = CircuitBreaker(failure_threshold=2, cooldown=30, half_open_max=1, clock=clk)
    b.record_failure()
    b.record_failure()
    assert b.state is State.OPEN and not b.allow()
    clk.advance(31)                                 # cooldown elapsed
    assert b.state is State.HALF_OPEN
    assert b.allow() is True                         # one probe permitted
    assert b.allow() is False                        # half_open_max=1 -> no more probes
    b.record_success()                               # probe ok -> close
    assert b.state is State.CLOSED and b.allow()


def test_breaker_half_open_failure_reopens():
    clk = FakeClock()
    b = CircuitBreaker(failure_threshold=1, cooldown=10, clock=clk)
    b.record_failure()
    assert b.state is State.OPEN
    clk.advance(11)
    assert b.state is State.HALF_OPEN
    b.allow()
    b.record_failure()                    # probe fails -> reopen
    assert b.state is State.OPEN
    assert not b.allow()


def test_success_resets_consecutive_failures():
    b = CircuitBreaker(failure_threshold=3)
    b.record_failure()
    b.record_failure()
    b.record_success()                               # reset
    b.record_failure()
    b.record_failure()
    assert b.state is State.CLOSED                   # never reached 3 in a row


# ── registry ───────────────────────────────────────────────────────────────
def test_registry_per_provider_isolation():
    clk = FakeClock()
    reg = CircuitRegistry(failure_threshold=1, cooldown=5, clock=clk)
    reg.record("github", ok=False)                   # trip github only
    assert reg.allow("github") is False
    assert reg.allow("brave") is True                # independent
    assert reg.open_providers() == ["github"]


# ── budget ledger ────────────────────────────────────────────────────────────
def test_budget_ledger_spend_and_defer():
    led = BudgetLedger()
    led.set_budget("censys", 3)
    assert led.try_spend("censys", 2) is True
    assert led.remaining("censys") == 1
    assert led.can_spend("censys", 2) is False        # only 1 left
    assert led.try_spend("censys", 2) is False        # defer, not deduct
    assert led.remaining("censys") == 1               # unchanged after failed spend
    assert led.try_spend("censys", 1) is True
    assert led.exhausted("censys") is True


def test_budget_unbudgeted_provider_is_unlimited():
    led = BudgetLedger()
    assert led.remaining("wayback") == float("inf")
    assert led.try_spend("wayback", 999) is True      # free/no-key source -> no cap
