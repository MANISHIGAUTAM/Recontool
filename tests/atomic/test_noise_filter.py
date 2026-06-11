"""Unit tests for the optional noise-control layer (engine/noise.py).

All hermetic: the resolver/cdn helpers are stubs, so no network is touched.
"""
from __future__ import annotations

import pytest

from recontool.core.scope import Scope
from recontool.engine.noise import NoiseConfig, NoiseFilter


def _scope():
    return Scope.from_seed("example.com", "domain")


@pytest.mark.asyncio
async def test_disabled_keeps_everything():
    nf = NoiseFilter(scope=_scope(), config=NoiseConfig(enabled=False))
    assert await nf.keep("s1", "subdomain", "anything.evil.com") is True
    assert nf.dropped == 0


@pytest.mark.asyncio
async def test_dedupe_drops_repeats_per_scan():
    nf = NoiseFilter(scope=_scope(), config=NoiseConfig(enabled=True))
    assert await nf.keep("s1", "subdomain", "api.example.com") is True
    assert await nf.keep("s1", "subdomain", "api.example.com") is False   # dup
    assert await nf.keep("s2", "subdomain", "api.example.com") is True    # other scan
    assert nf.stats["duplicate"] == 1


@pytest.mark.asyncio
async def test_scope_gate_drops_out_of_scope():
    nf = NoiseFilter(scope=_scope(), config=NoiseConfig(enabled=True))
    assert await nf.keep("s1", "subdomain", "api.example.com") is True
    assert await nf.keep("s1", "subdomain", "api.attacker.com") is False
    assert nf.stats["out_of_scope"] == 1


@pytest.mark.asyncio
async def test_wildcard_drops_only_wildcard_hosts():
    # Stub resolver: the random probe AND junk.* resolve to the wildcard IP;
    # real.example.com resolves elsewhere.
    wildcard_ip = {"10.0.0.9"}

    async def resolver(host: str) -> set:
        if host.startswith("real."):
            return {"203.0.113.5"}
        return wildcard_ip  # probe + any wildcard-backed host

    nf = NoiseFilter(scope=_scope(),
                     config=NoiseConfig(enabled=True, wildcard=True),
                     resolver=resolver)
    assert await nf.keep("s1", "subdomain", "junk.example.com") is False   # wildcard noise
    assert await nf.keep("s1", "subdomain", "real.example.com") is True    # real host
    assert nf.stats["wildcard_dns"] == 1


@pytest.mark.asyncio
async def test_wildcard_noop_when_apex_has_no_wildcard():
    async def resolver(host: str) -> set:
        return set()  # nothing resolves -> no wildcard record

    nf = NoiseFilter(scope=_scope(),
                     config=NoiseConfig(enabled=True, wildcard=True),
                     resolver=resolver)
    # in-scope, apex has no wildcard -> kept
    assert await nf.keep("s1", "subdomain", "whatever.example.com") is True


@pytest.mark.asyncio
async def test_cdn_filter_drops_edge_ips():
    async def cdn_check(ip: str) -> bool:
        return ip.startswith("104.16.")   # pretend this is a CDN range

    # scope_gate off to isolate CDN behavior (a domain-only scope allows no IPs).
    nf = NoiseFilter(scope=_scope(),
                     config=NoiseConfig(enabled=True, scope_gate=False, cdn=True),
                     cdn_check=cdn_check)
    assert await nf.keep("s1", "ip", "104.16.1.1") is False
    assert await nf.keep("s1", "ip", "203.0.113.7") is True
    assert nf.stats["cdn_edge"] == 1
