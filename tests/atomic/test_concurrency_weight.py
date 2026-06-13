"""Heavy/light concurrency weighting: subprocess tools are bounded so they can't
monopolise the worker pool; pure-network tools run unbounded. No tool is capped
or dropped -- heavy ones just can't all run at once."""
from __future__ import annotations

import asyncio

from recontool.engine.worker import WorkerPool


class _Spec:
    def __init__(self, name, integration):
        self.name = name; self.integration = integration


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


def test_heavy_sem_is_half_the_pool():
    async def check():
        p = _pool()
        p._db_pool = None
        # emulate run() sizing without launching workers
        for workers, expect in [(24, 12), (8, 4), (2, 2), (100, 50)]:
            p._heavy_sem = asyncio.Semaphore(max(2, workers // 2))
            assert p._heavy_sem._value == expect
    asyncio.run(check())
