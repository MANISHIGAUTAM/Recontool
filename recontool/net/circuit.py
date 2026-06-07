"""Provider-aware reliability primitives — circuit breaker + budget ledger.

Authorized-only, no-evasion policy: we stay within provider limits by HONORING them
(quotas, backoff, circuit breaking) rather than circumventing them. These primitives
replace evasion features (proxy rotation, stealth jitter) as the way the scheduler
stays reliable and within plan limits. See docs/blueprint/04-scheduler-recursion-loops.md.

  CircuitBreaker  : per-provider CLOSED -> OPEN -> HALF_OPEN state machine; fails fast
                    while a provider is flapping/throttling so the planner can substitute.
  CircuitRegistry : one breaker per provider key.
  BudgetLedger    : per-run, per-provider quota ledger; defer (not fail) when exhausted.

Pure + clock-injectable for deterministic tests (no real sleeping).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class State(str, Enum):
    CLOSED = "closed"        # healthy: calls allowed
    OPEN = "open"            # tripped: fail fast, no calls until cooldown
    HALF_OPEN = "half_open"  # probing: limited calls to test recovery


class CircuitOpen(RuntimeError):
    """Raised when a request is attempted while the provider's breaker is OPEN."""

    def __init__(self, provider: str):
        super().__init__(f"circuit OPEN for provider {provider!r}; failing fast")
        self.provider = provider


class BudgetExhausted(RuntimeError):
    """Raised when a provider's per-run quota budget is exhausted."""

    def __init__(self, provider: str):
        super().__init__(f"budget exhausted for provider {provider!r}; deferring")
        self.provider = provider


@dataclass
class CircuitBreaker:
    """Per-provider breaker.

    Trips OPEN after `failure_threshold` consecutive failures. After `cooldown`
    seconds, allows up to `half_open_max` probe calls; a probe success closes it,
    a probe failure re-opens it.
    """

    name: str = "provider"
    failure_threshold: int = 5
    cooldown: float = 30.0
    half_open_max: int = 1
    clock: Callable[[], float] = time.monotonic

    _state: State = field(default=State.CLOSED, init=False)
    _consecutive_failures: int = field(default=0, init=False)
    _opened_at: float = field(default=0.0, init=False)
    _half_open_calls: int = field(default=0, init=False)

    @property
    def state(self) -> State:
        # lazily promote OPEN -> HALF_OPEN once the cooldown has elapsed
        if self._state is State.OPEN and (self.clock() - self._opened_at) >= self.cooldown:
            self._state = State.HALF_OPEN
            self._half_open_calls = 0
        return self._state

    def allow(self) -> bool:
        """Whether a call may proceed right now."""
        st = self.state
        if st is State.CLOSED:
            return True
        if st is State.OPEN:
            return False
        # HALF_OPEN: permit a bounded number of probe calls
        if self._half_open_calls < self.half_open_max:
            self._half_open_calls += 1
            return True
        return False

    def record_success(self) -> None:
        if self.state is State.HALF_OPEN:
            self._reset()                # recovery confirmed
        else:
            self._consecutive_failures = 0

    def record_failure(self) -> None:
        if self.state is State.HALF_OPEN:
            self._trip()                 # probe failed -> back to OPEN
            return
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._trip()

    def _trip(self) -> None:
        self._state = State.OPEN
        self._opened_at = self.clock()
        self._half_open_calls = 0

    def _reset(self) -> None:
        self._state = State.CLOSED
        self._consecutive_failures = 0
        self._half_open_calls = 0

    def snapshot(self) -> dict:
        return {"name": self.name, "state": self.state.value,
                "consecutive_failures": self._consecutive_failures}


class CircuitRegistry:
    """One breaker per provider key (shared across that provider's adapters)."""

    def __init__(self, **defaults):
        self._defaults = defaults
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, provider: str) -> CircuitBreaker:
        if provider not in self._breakers:
            self._breakers[provider] = CircuitBreaker(name=provider, **self._defaults)
        return self._breakers[provider]

    def allow(self, provider: str) -> bool:
        return self.get(provider).allow()

    def record(self, provider: str, ok: bool) -> None:
        b = self.get(provider)
        b.record_success() if ok else b.record_failure()

    def open_providers(self) -> list[str]:
        return [p for p, b in self._breakers.items() if b.state is State.OPEN]

    def snapshot(self) -> dict:
        return {p: b.snapshot() for p, b in self._breakers.items()}


class BudgetLedger:
    """Per-run, per-provider quota ledger.

    Each provider gets a budget of quota units for the run. `try_spend` deducts if
    affordable and returns True; otherwise returns False so the scheduler can DEFER
    the job (not error) and the planner substitutes an alternate source. This is how
    we respect plan limits and avoid surprise bills.
    """

    def __init__(self):
        self._budget: dict[str, float] = {}
        self._used: dict[str, float] = {}

    def set_budget(self, provider: str, units: float) -> None:
        self._budget[provider] = float(units)
        self._used.setdefault(provider, 0.0)

    def remaining(self, provider: str) -> float:
        if provider not in self._budget:
            return float("inf")          # unbudgeted provider = unlimited
        return self._budget[provider] - self._used.get(provider, 0.0)

    def can_spend(self, provider: str, cost: float = 1.0) -> bool:
        return self.remaining(provider) >= cost

    def try_spend(self, provider: str, cost: float = 1.0) -> bool:
        if not self.can_spend(provider, cost):
            return False
        self._used[provider] = self._used.get(provider, 0.0) + cost
        return True

    def exhausted(self, provider: str) -> bool:
        return self.remaining(provider) <= 0

    def snapshot(self) -> dict:
        return {p: {"budget": self._budget.get(p), "used": self._used.get(p, 0.0),
                    "remaining": self.remaining(p)} for p in self._budget}
