"""Per-provider QPS (rate-limit COMPLIANCE, not evasion).

Confirms the engine throttles rate-sensitive sources below their published limits
and that every scan's HTTP client is built with those per-provider buckets.
"""
from __future__ import annotations

from recontool.config import DEFAULT_PROVIDER_QPS, settings
from recontool.net.rate_limiter import RateLimiter


def test_provider_rate_limits_have_conservative_defaults():
    limits = settings.provider_rate_limits()
    # HackerTarget's free API allows only a few requests/min -> hard throttle.
    assert limits["hackertarget"] <= 0.5
    # Every built-in default is surfaced.
    for bucket in DEFAULT_PROVIDER_QPS:
        assert bucket in limits and limits[bucket] > 0


def test_rate_limiter_accepts_per_bucket_configuration():
    rl = RateLimiter(default_rate=10.0)
    for bucket, qps in settings.provider_rate_limits().items():
        rl.configure(bucket, qps)
    snap = rl.snapshot()
    assert {"hackertarget", "crtsh", "otx"} <= set(snap)


def test_build_scan_infra_applies_provider_qps():
    from recontool.engine.runner import build_scan_infra

    _, _, http, _ = build_scan_infra("example.com", "domain", "normal")
    snap = http.limiter.snapshot()
    assert "hackertarget" in snap   # per-provider bucket was pre-configured
    assert "crtsh" in snap
