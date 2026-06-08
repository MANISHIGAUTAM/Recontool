"""Worker pool management for the event-driven engine.

Manages separate worker pools for different adapter categories with
configurable concurrency limits. This prevents slow adapters (e.g., port
scanners) from starving fast ones (e.g., passive DNS lookups).

Pools:
  - passive: passive recon adapters (DNS, cert transparency, etc.)
  - dns: DNS resolution and enumeration
  - http: HTTP probing and crawling
  - ports: port scanning (naabu, masscan)
  - crawl: web crawling and spidering
  - fuzz: directory/parameter fuzzing
  - analysis: JS analysis, content parsing
  - storage: output writing, artifact storage
  - visual: screenshots (gowitness, etc.)
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine


@dataclass
class PoolConfig:
    """Configuration for a single worker pool."""

    name: str
    max_concurrency: int = 5
    # Adapter name patterns that belong to this pool
    adapter_patterns: list[str] = field(default_factory=list)


# Default pool configurations
DEFAULT_POOLS: dict[str, PoolConfig] = {
    "passive": PoolConfig(
        name="passive", max_concurrency=10,
        adapter_patterns=[
            "crtsh", "certspotter", "hackertarget", "otx", "urlscan",
            "virustotal", "securitytrails", "shodan_passive", "censys",
            "chaos", "subfinder", "assetfinder", "amass_passive",
        ],
    ),
    "dns": PoolConfig(
        name="dns", max_concurrency=8,
        adapter_patterns=["dns_resolve", "dns_brute", "dnsgen"],
    ),
    "http": PoolConfig(
        name="http", max_concurrency=6,
        adapter_patterns=["http_probe", "httpx"],
    ),
    "ports": PoolConfig(
        name="ports", max_concurrency=3,
        adapter_patterns=["naabu", "masscan", "nmap"],
    ),
    "crawl": PoolConfig(
        name="crawl", max_concurrency=4,
        adapter_patterns=["crawler", "katana", "gospider"],
    ),
    "fuzz": PoolConfig(
        name="fuzz", max_concurrency=3,
        adapter_patterns=["ffuf", "dirsearch", "feroxbuster"],
    ),
    "analysis": PoolConfig(
        name="analysis", max_concurrency=5,
        adapter_patterns=[
            "js_analyzer", "param_extractor", "nuclei",
            "wayback", "gau", "waybackurls",
        ],
    ),
    "storage": PoolConfig(
        name="storage", max_concurrency=2,
        adapter_patterns=["output_writer", "artifact_store"],
    ),
    "visual": PoolConfig(
        name="visual", max_concurrency=2,
        adapter_patterns=["gowitness", "screenshot"],
    ),
}


class WorkerPool:
    """A single worker pool with a semaphore-based concurrency limiter."""

    def __init__(self, config: PoolConfig) -> None:
        self.config = config
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
        self._active: int = 0
        self._total_dispatched: int = 0

    async def submit(self, coro: Coroutine) -> Any:
        """Submit a coroutine to this pool, respecting concurrency limits."""
        async with self._semaphore:
            self._active += 1
            self._total_dispatched += 1
            try:
                return await coro
            finally:
                self._active -= 1

    @property
    def active_count(self) -> int:
        return self._active

    @property
    def available_slots(self) -> int:
        return self.config.max_concurrency - self._active


class Scheduler:
    """Manages multiple worker pools and routes adapters to the correct pool."""

    def __init__(self, pool_configs: dict[str, PoolConfig] | None = None) -> None:
        configs = pool_configs or DEFAULT_POOLS
        self._pools: dict[str, WorkerPool] = {
            name: WorkerPool(cfg) for name, cfg in configs.items()
        }
        # Build reverse lookup: adapter_pattern -> pool_name
        self._adapter_to_pool: dict[str, str] = {}
        for pool_name, cfg in configs.items():
            for pattern in cfg.adapter_patterns:
                self._adapter_to_pool[pattern] = pool_name

    def get_pool_for(self, adapter_name: str) -> WorkerPool:
        """Determine which pool an adapter belongs to."""
        pool_name = self._adapter_to_pool.get(adapter_name, "passive")
        return self._pools.get(pool_name, self._pools["passive"])

    async def submit(self, adapter_name: str, coro: Coroutine) -> Any:
        """Submit work to the appropriate pool for the given adapter."""
        pool = self.get_pool_for(adapter_name)
        return await pool.submit(coro)

    def stats(self) -> dict[str, dict[str, int]]:
        """Return per-pool stats."""
        return {
            name: {
                "active": pool.active_count,
                "available": pool.available_slots,
                "total_dispatched": pool._total_dispatched,
            }
            for name, pool in self._pools.items()
        }
