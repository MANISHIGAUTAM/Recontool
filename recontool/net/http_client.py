"""Async HTTP client integrating proxy rotation + rate limiting + retries.

Every outbound request:
  1. acquires a rate-limit token for its bucket (provider/egress),
  2. picks a proxy from the pool (IP rotation),
  3. applies profile jitter (stealth),
  4. retries with exponential backoff on transient errors / 429,
  5. reports proxy health back to the pool,
  6. rotates User-Agent.

This is the single egress chokepoint, which is what makes rate-limit avoidance
and OPSEC controls actually enforceable.
"""
from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Any

import httpx

from recontool.config import RateProfile, settings
from recontool.net.proxy_pool import ProxyPool
from recontool.net.rate_limiter import RateLimiter

logger = logging.getLogger("recontool.net.http")

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


@dataclass
class Response:
    status: int
    text: str
    headers: dict[str, str]
    url: str
    content: bytes
    json_ok: bool = False
    _json: Any = None

    def json(self) -> Any:
        return self._json


class HttpClient:
    def __init__(
        self,
        profile: RateProfile | None = None,
        proxy_pool: ProxyPool | None = None,
        limiter: RateLimiter | None = None,
        timeout: float = 20.0,
        max_retries: int = 3,
    ):
        self.profile = profile or settings.profile()
        self.proxies = proxy_pool or ProxyPool(
            settings.proxies, strategy=settings.proxy_strategy
        )
        self.limiter = limiter or RateLimiter(default_rate=self.profile.requests_per_second)
        self.timeout = timeout
        self.max_retries = max_retries
        # Track the egress IP actually used (for audit). Populated lazily.
        self.last_egress: str | None = None

    async def get(self, url: str, *, bucket: str = "_global", **kw) -> Response:
        return await self.request("GET", url, bucket=bucket, **kw)

    async def post(self, url: str, *, bucket: str = "_global", **kw) -> Response:
        # `json=`/`data=` are forwarded through request() to httpx (form vs JSON
        # body). Used by GenericApiAdapter for POST-body APIs (abuse.ch, …).
        return await self.request("POST", url, bucket=bucket, **kw)

    async def request(
        self,
        method: str,
        url: str,
        *,
        bucket: str = "_global",
        headers: dict | None = None,
        params: dict | None = None,
        sticky_key: str | None = None,
        **kw,
    ) -> Response:
        await self.limiter.acquire(bucket)
        if self.profile.jitter_seconds:
            await asyncio.sleep(random.uniform(0, self.profile.jitter_seconds))

        hdrs = {"User-Agent": random.choice(_USER_AGENTS)}
        if headers:
            hdrs.update(headers)

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            proxy = self.proxies.acquire(key=sticky_key or url)
            self.last_egress = proxy or "direct"
            try:
                async with httpx.AsyncClient(
                    proxy=proxy, timeout=self.timeout, follow_redirects=True, verify=False
                ) as client:
                    resp = await client.request(method, url, headers=hdrs, params=params, **kw)
                # 429 / 5xx => backoff + (implicitly) rotate proxy next loop
                if resp.status_code == 429 or resp.status_code >= 500:
                    self.proxies.report(proxy, ok=False)
                    raise httpx.HTTPStatusError(
                        f"retryable status {resp.status_code}", request=resp.request, response=resp
                    )
                self.proxies.report(proxy, ok=True)
                logger.debug("%s %s -> %s (egress=%s, bucket=%s)",
                             method, url, resp.status_code, self.last_egress, bucket)
                return _wrap(resp)
            except Exception as exc:  # noqa: BLE001 — retry on any transport/HTTP error
                last_exc = exc
                self.proxies.report(proxy, ok=False)
                if attempt < self.max_retries:
                    backoff = (2 ** attempt) + random.uniform(0, 0.5)
                    await asyncio.sleep(backoff)
                    continue
        raise last_exc  # type: ignore[misc]


def _wrap(resp: httpx.Response) -> Response:
    r = Response(
        status=resp.status_code,
        text=resp.text,
        headers=dict(resp.headers),
        url=str(resp.url),
        content=resp.content,
    )
    try:
        r._json = resp.json()
        r.json_ok = True
    except Exception:  # noqa: BLE001
        r.json_ok = False
    return r
