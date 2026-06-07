"""Proxy / egress-IP rotation pool.

⚠️ POLICY NOTE (authorized-only blueprint, docs/blueprint/README.md §Policy):
    This module's ROTATION-FOR-EVASION behavior is DEPRECATED. The platform is
    authorized-only and does NOT do stealth, proxy rotation to dodge rate limits, or
    detection evasion. Reliability/limit-compliance is now handled by provider quotas,
    backoff, caching, concurrency caps, and circuit breakers (see net/circuit.py and
    net/rate_limiter.py). Retain at most a SINGLE declared egress (e.g. a corporate
    egress IP for allow-listing) — not a rotating pool used to circumvent limits.
    Roadmap item G1 in docs/blueprint/05-diff-ai-gaps-roadmap.md tracks reframing/removal.

Rotates outbound requests across a pool of proxies (legacy behavior, kept for
backward compatibility only).
"""
from __future__ import annotations

import itertools
import random
import threading
import time
from dataclasses import dataclass, field


@dataclass
class _Proxy:
    url: str
    fails: int = 0
    quarantined_until: float = 0.0
    used: int = 0


@dataclass
class ProxyPool:
    proxies: list[str] = field(default_factory=list)
    strategy: str = "round_robin"
    max_fails: int = 3
    cooldown_seconds: float = 60.0
    # If True and pool is empty/all-dead, allow direct egress (passive use).
    allow_direct_fallback: bool = True

    def __post_init__(self):
        self._pool = [_Proxy(u) for u in self.proxies]
        self._lock = threading.Lock()
        self._rr = itertools.cycle(range(len(self._pool))) if self._pool else None
        self._sticky: dict[str, str] = {}

    @property
    def enabled(self) -> bool:
        return bool(self._pool)

    def _healthy(self) -> list[_Proxy]:
        now = time.time()
        return [p for p in self._pool if p.quarantined_until <= now]

    def acquire(self, key: str | None = None) -> str | None:
        """Return a proxy URL (or None for direct egress).

        `key` enables sticky mode (same proxy for the same key)."""
        with self._lock:
            healthy = self._healthy()
            if not healthy:
                if self.allow_direct_fallback:
                    return None
                # No healthy proxy and direct egress forbidden -> signal caller.
                raise RuntimeError("No healthy proxy available and direct egress disabled")

            if self.strategy == "sticky" and key is not None:
                if key in self._sticky:
                    url = self._sticky[key]
                    if any(p.url == url for p in healthy):
                        return url
                chosen = random.choice(healthy)
                self._sticky[key] = chosen.url
                chosen.used += 1
                return chosen.url

            if self.strategy == "random":
                chosen = random.choice(healthy)
            else:  # round_robin (skip quarantined)
                chosen = None
                for _ in range(len(self._pool)):
                    idx = next(self._rr)  # type: ignore[arg-type]
                    cand = self._pool[idx]
                    if cand.quarantined_until <= time.time():
                        chosen = cand
                        break
                chosen = chosen or random.choice(healthy)
            chosen.used += 1
            return chosen.url

    def report(self, url: str | None, ok: bool) -> None:
        """Feed back success/failure so we can quarantine bad proxies."""
        if url is None:
            return
        with self._lock:
            for p in self._pool:
                if p.url == url:
                    if ok:
                        p.fails = 0
                    else:
                        p.fails += 1
                        if p.fails >= self.max_fails:
                            p.quarantined_until = time.time() + self.cooldown_seconds
                            p.fails = 0
                    return

    def stats(self) -> list[dict]:
        now = time.time()
        return [
            {
                "url": _mask(p.url),
                "used": p.used,
                "quarantined": p.quarantined_until > now,
            }
            for p in self._pool
        ]


def _mask(url: str) -> str:
    """Hide credentials in proxy URLs for logs."""
    if "@" in url:
        scheme, rest = url.split("://", 1) if "://" in url else ("", url)
        host = rest.split("@", 1)[1]
        return f"{scheme}://***@{host}" if scheme else f"***@{host}"
    return url
