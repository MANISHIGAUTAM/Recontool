"""Atomic checks for the Policy Engine: scope + authorization + demo/test mode."""
from __future__ import annotations

from recontool.core.policy import PolicyEngine


# ── standard mode ────────────────────────────────────────────────────────────
def test_standard_passive_allowed_active_requires_attestation():
    pe = PolicyEngine.for_seed("example.com")
    seed = pe.authorize_seed("example.com")
    assert seed.allowed is True
    # active blocked until attestation
    d = pe.allow_active("subdomain", "api.example.com")
    assert d.allowed is False and "not authorized" in d.reason


def test_standard_active_authorized_in_scope():
    pe = PolicyEngine.for_seed("example.com", authorized_active=True)
    d = pe.allow_active("subdomain", "api.example.com")
    assert d.allowed is True
    # out of scope still blocked even when authorized
    assert pe.allow_active("subdomain", "evil.attacker.com").allowed is False


# ── demo / test mode ─────────────────────────────────────────────────────────
def test_demo_mode_blocks_arbitrary_target():
    pe = PolicyEngine.for_seed("acme-corp.com", mode="demo")
    assert pe.authorize_seed("acme-corp.com").allowed is False


def test_demo_mode_allows_sanctioned_targets():
    for seed in ("scanme.nmap.org", "testphp.vulnweb.com", "example.com"):
        pe = PolicyEngine.for_seed(seed, mode="demo", authorized_active=True)
        assert pe.authorize_seed(seed).allowed is True, seed


def test_demo_mode_allows_subdomain_of_sanctioned_apex():
    pe = PolicyEngine.for_seed("vulnweb.com", mode="demo", authorized_active=True)
    # a subdomain of an allow-listed apex is permitted
    d = pe.allow_active("subdomain", "testphp.vulnweb.com")
    assert d.allowed is True


def test_demo_mode_blocks_active_on_unsanctioned_even_if_authorized():
    pe = PolicyEngine.for_seed("scanme.nmap.org", mode="demo", authorized_active=True)
    # in-scope only covers nmap.org; an unrelated host is rejected by demo allow-list
    assert pe.allow_active("subdomain", "api.example-corp.com").allowed is False


def test_extra_demo_targets_extend_allowlist():
    pe = PolicyEngine.for_seed("my-lab.internal", mode="demo",
                               extra_demo_targets={"my-lab.internal"})
    assert pe.authorize_seed("my-lab.internal").allowed is True
