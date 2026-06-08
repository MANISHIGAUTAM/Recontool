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
import random
from dataclasses import dataclass
from typing import Any

import httpx

from recontool.config import RateProfile, settings
from recontool.net.proxy_pool import ProxyPool
from recontool.net.rate_limiter import RateLimiter

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
        timeout: float = 10.0,
        max_retries: int = 2,
        mode=None,
        mock_env=None,
        circuits=None,
        budget=None,
    ):
        self.profile = profile or settings.profile()
        self.proxies = proxy_pool or ProxyPool(
            settings.proxies, strategy=settings.proxy_strategy
        )
        self.limiter = limiter or RateLimiter(default_rate=self.profile.requests_per_second)
        self.timeout = timeout
        self.max_retries = max_retries
        # Run-mode + optional mock environment (demo/test). In demo/test mode every
        # request is served by the mock env; real egress is blocked entirely.
        from recontool.core.mode import RunMode
        self.mode = mode or settings.run_mode
        self.mock_env = mock_env
        if self.mode is None:
            self.mode = RunMode.LIVE
        # Provider-aware reliability: circuit breakers + per-run budget ledger.
        # When a provider's breaker is OPEN, we fail fast (no real call) so the
        # planner can substitute. Budget enforces per-provider quota for the run.
        self.circuits = circuits
        self.budget = budget
        # Track the egress IP actually used (for audit). Populated lazily.
        self.last_egress: str | None = None
        # Shared persistent httpx client for connection pooling (reuses TCP
        # connections across requests instead of opening a new one per call).
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Return (or lazily create) the shared persistent httpx client."""
        if self._client is None or self._client.is_closed:
            proxy = self.proxies.acquire(key="_shared")
            self._client = httpx.AsyncClient(
                proxy=proxy, timeout=self.timeout,
                follow_redirects=True, verify=False,
            )
        return self._client

    async def close(self) -> None:
        """Close the shared client and release pooled connections."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def get(self, url: str, *, bucket: str = "_global", **kw) -> Response:
        return await self.request("GET", url, bucket=bucket, **kw)

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
        # ── PROVIDER-AWARE RELIABILITY (circuit breaker + budget) ───────────
        # `bucket` is the provider key. Applied first (independent of transport):
        # fail fast if the breaker is OPEN or the per-run budget is exhausted, so
        # the planner can substitute a source.
        if self.circuits is not None and not self.circuits.allow(bucket):
            from recontool.net.circuit import CircuitOpen
            raise CircuitOpen(bucket)
        if self.budget is not None and not self.budget.try_spend(bucket, 1.0):
            from recontool.net.circuit import BudgetExhausted
            raise BudgetExhausted(bucket)

        # ── MODE GATE (highest-level safety switch) ─────────────────────────
        # In demo/test mode, NEVER touch the network. Serve from the mock env if
        # present, else hard-fail so a misconfigured test can't leak egress.
        if not self.mode.allows_real_egress:
            if self.mock_env is not None:
                self.last_egress = "mock"
                status, body, hdrs = self.mock_env.handle(
                    method, url, params=params).as_tuple()
                return _wrap_mock(status, body, hdrs, url)
            from recontool.core.mode import LiveEgressBlocked
            raise LiveEgressBlocked(url, self.mode)

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
                client = self._get_client()
                resp = await client.request(method, url, headers=hdrs, params=params, **kw)
                # 429 / 5xx => backoff + (implicitly) rotate proxy next loop
                if resp.status_code == 429 or resp.status_code >= 500:
                    self.proxies.report(proxy, ok=False)
                    if self.circuits is not None:
                        self.circuits.record(bucket, ok=False)
                    raise httpx.HTTPStatusError(
                        f"retryable status {resp.status_code}", request=resp.request, response=resp
                    )
                self.proxies.report(proxy, ok=True)
                if self.circuits is not None:
                    self.circuits.record(bucket, ok=True)
                return _wrap(resp)
            except Exception as exc:  # noqa: BLE001 — retry on any transport/HTTP error
                last_exc = exc
                self.proxies.report(proxy, ok=False)
                if self.circuits is not None:
                    self.circuits.record(bucket, ok=False)
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


def _wrap_mock(status: int, body: str, headers: dict[str, str], url: str) -> Response:
    """Wrap a mock-env response into the same Response shape as a real one."""
    import json as _json

    r = Response(
        status=status,
        text=body,
        headers=headers,
        url=url,
        content=body.encode("utf-8", errors="ignore"),
    )
    try:
        r._json = _json.loads(body)
        r.json_ok = True
    except Exception:  # noqa: BLE001
        r.json_ok = False
    return r
