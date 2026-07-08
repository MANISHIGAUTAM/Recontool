"""Heavy/light concurrency weighting: subprocess tools are bounded so they can't
monopolise the worker pool; pure-network tools run unbounded. No tool is capped
or dropped -- heavy ones just can't all run at once."""
from __future__ import annotations

import asyncio

from recontool.engine.worker import WorkerPool


class _Spec:
    def __init__(self, name, integration):
        self.name = name
        self.integration = integration


def _pool():
    # minimal pool — only _is_heavy / _heavy_sem are exercised
    return WorkerPool.__new__(WorkerPool)


def test_is_heavy_classification():
    p = _pool()
    assert p._is_heavy(_Spec("amass", "cli")) is True            # subprocess
    assert p._is_heavy(_Spec("nmap", "python")) is True          # handwritten shell-out
    assert p._is_heavy(_Spec("sslyze", "python")) is True
    assert p._is_heavy(_Spec("dns_resolve", "python")) is False  # network-only python
    assert p._is_heavy(_Spec("crtsh", "api")) is False           # network-only API


def test_heavy_sem_capped_at_heavy_max():
    # run() sizes the heavy semaphore as max(2, min(workers//2, _HEAVY_MAX)) so a
    # big --workers value can't let unboundedly many memory-heavy tools run at once.
    from recontool.engine.worker import _HEAVY_MAX

    for workers, expect in [(24, 12), (8, 4), (2, 2), (40, _HEAVY_MAX), (256, _HEAVY_MAX)]:
        sem = asyncio.Semaphore(max(2, min(workers // 2, _HEAVY_MAX)))
        assert sem._value == expect


# ── B2/B3: registry retry_policy + concurrency_safety are HONORED ─────────────
class _Outcome:
    def __init__(self, status, reason="", events=None):
        self.status, self.reason, self.events = status, reason, events or []


class _PolicySpec:
    def __init__(self, name, *, integration="api", concurrency_safety=True,
                 max_retries=0, backoff_factor=0.01):
        self.name, self.integration = name, integration
        self.concurrency_safety = concurrency_safety

        class _RP:
            pass
        self.retry_policy = _RP()
        self.retry_policy.max_retries = max_retries
        self.retry_policy.backoff_factor = backoff_factor
        self.retry_policy.retryable_errors = []


def _policy_pool():
    p = WorkerPool.__new__(WorkerPool)
    p._heavy_sem = asyncio.Semaphore(10)
    p._conc_locks = {}
    p.item_timeout = 30
    p.scope = p.profile = p.http = p.api_keys = None

    class _Log:
        def log_concurrency_decision(self, *a, **k):
            pass
    p.log = _Log()
    return p


def test_retry_policy_reexecutes_on_error_then_succeeds(monkeypatch):
    from recontool.engine import worker as W
    calls = {"n": 0}

    async def fake(spec, *a, **k):
        calls["n"] += 1
        return _Outcome("error", "boom") if calls["n"] < 3 else _Outcome("ok")
    monkeypatch.setattr(W, "run_tool_spec", fake)

    out = asyncio.run(_policy_pool()._run_with_policy(
        _PolicySpec("flaky", max_retries=3), "s", {"domain": ["x"]}, None))
    assert out.status == "ok" and calls["n"] == 3   # 1 try + 2 retries


def test_retry_caps_at_max_and_never_retries_skip(monkeypatch):
    from recontool.engine import worker as W

    calls = {"n": 0}

    async def always_err(spec, *a, **k):
        calls["n"] += 1
        return _Outcome("error", "boom")
    monkeypatch.setattr(W, "run_tool_spec", always_err)
    out = asyncio.run(_policy_pool()._run_with_policy(
        _PolicySpec("x", max_retries=2), "s", {"domain": ["x"]}, None))
    assert out.status == "error" and calls["n"] == 3   # 1 + 2 retries, then stop

    calls["n"] = 0

    async def skip(spec, *a, **k):
        calls["n"] += 1
        return _Outcome("skip", "no key")
    monkeypatch.setattr(W, "run_tool_spec", skip)
    out = asyncio.run(_policy_pool()._run_with_policy(
        _PolicySpec("y", max_retries=5), "s", {"domain": ["x"]}, None))
    assert out.status == "skip" and calls["n"] == 1   # skip is intentional — no retry


def test_concurrency_unsafe_tool_is_serialized(monkeypatch):
    from recontool.engine import worker as W
    state = {"cur": 0, "max": 0}

    async def fake(spec, *a, **k):
        state["cur"] += 1
        state["max"] = max(state["max"], state["cur"])
        await asyncio.sleep(0.01)   # overlap window
        state["cur"] -= 1
        return _Outcome("ok")
    monkeypatch.setattr(W, "run_tool_spec", fake)

    p = _policy_pool()
    unsafe = _PolicySpec("masscan", concurrency_safety=False)

    async def go(spec):
        await asyncio.gather(*(p._run_with_policy(spec, "s", {"domain": ["x"]}, None)
                               for _ in range(5)))
    asyncio.run(go(unsafe))
    assert state["max"] == 1   # never two at once

    state.update(cur=0, max=0)
    asyncio.run(go(_PolicySpec("crtsh", concurrency_safety=True)))
    assert state["max"] > 1    # concurrency-safe tool overlaps freely
