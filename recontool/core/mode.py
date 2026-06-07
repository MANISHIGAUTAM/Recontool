"""Run-mode model + test-mode egress enforcement (demo | test | live).

The mode is the single highest-level safety switch, layered ABOVE the scope gate
and the active-authorization gate:

    demo  : run the full pipeline against a built-in MOCK environment only.
            No real network egress is permitted at all. Safe to demo anywhere.
    test  : run against recorded fixtures / mock; real network egress is BLOCKED.
            Used for deterministic integration/E2E tests in CI.
    live  : run against real (authorized) targets. Real egress permitted, still
            subject to scope + active-authorization gates.

Enforcement is centralised here and consulted by the single HTTP egress
chokepoint (recontool/net/http_client.py). If a tool ever tries to touch a real
host in demo/test mode, a LiveEgressBlocked error is raised — a hard guarantee
that E2E validation never touches a live target (matches the spec requirement
"test-mode enforcement so no live target is touched during E2E validation").
"""
from __future__ import annotations

from enum import Enum


class RunMode(str, Enum):
    DEMO = "demo"
    TEST = "test"
    LIVE = "live"

    @classmethod
    def parse(cls, value: str | None) -> "RunMode":
        if not value:
            return cls.LIVE
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return cls.LIVE

    @property
    def allows_real_egress(self) -> bool:
        """Only LIVE mode may make real outbound network calls."""
        return self is RunMode.LIVE

    @property
    def uses_mock(self) -> bool:
        """demo/test route HTTP through the in-process mock environment."""
        return self in (RunMode.DEMO, RunMode.TEST)


class LiveEgressBlocked(RuntimeError):
    """Raised when code attempts real network egress in demo/test mode."""

    def __init__(self, url: str, mode: RunMode):
        super().__init__(
            f"live egress to {url!r} blocked in mode={mode.value}: "
            "real targets are never touched in demo/test mode"
        )
        self.url = url
        self.mode = mode
