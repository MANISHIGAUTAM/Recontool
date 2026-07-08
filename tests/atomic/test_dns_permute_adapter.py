"""Atomic checks for the dnsgen permutation adapter (network-free).

These tests exercise ONLY the pure scope-filter helper `_in_scope_candidates`
and the adapter's declared contract. NO real DNS, NO subprocess, NO registry —
the live resolve-gate in run() (which additionally drops every candidate that
does not actually resolve) is intentionally NOT touched here.
"""
from __future__ import annotations

from recontool.adapters.dns_permute import DnsPermute
from recontool.core.scope import Scope

# A realistic slice of dnsgen stdout: one candidate hostname per line.
# Mixes in-scope names, an out-of-scope name, a sibling-suffix collision, an
# apex line, a duplicate (different case + trailing dot), and blank lines.
SAMPLE_STDOUT = """\
dev.example.com
api2.example.com
staging.example.com

DEV.example.com
api2.example.com.
example.com
admin.evil.com
m.testexample.com
"""


def _adapter() -> DnsPermute:
    return DnsPermute()


def test_in_scope_candidates_keeps_in_scope_drops_out_of_scope():
    scope = Scope.from_seed("example.com", "domain")
    got = _adapter()._in_scope_candidates(SAMPLE_STDOUT, scope)

    # in-scope subdomains are kept
    assert "dev.example.com" in got
    assert "api2.example.com" in got
    assert "staging.example.com" in got
    # the apex itself is in scope and kept
    assert "example.com" in got

    # out-of-scope domain is dropped
    assert "admin.evil.com" not in got
    # sibling-suffix collision must NOT match example.com
    assert "m.testexample.com" not in got


def test_in_scope_candidates_dedupes_and_normalizes():
    scope = Scope.from_seed("example.com", "domain")
    got = _adapter()._in_scope_candidates(SAMPLE_STDOUT, scope)

    # "dev.example.com" and "DEV.example.com" collapse to one (case-folded)
    assert got.count("dev.example.com") == 1
    # "api2.example.com" and "api2.example.com." collapse to one (trailing dot)
    assert got.count("api2.example.com") == 1
    # blank lines never produce empty entries
    assert "" not in got
    # every survivor is lower-case and dot-stripped
    assert all(h == h.lower() and not h.endswith(".") for h in got)


def test_empty_stdout_yields_nothing():
    scope = Scope.from_seed("example.com", "domain")
    assert _adapter()._in_scope_candidates("", scope) == []
    assert _adapter()._in_scope_candidates("\n\n  \n", scope) == []


def test_adapter_contract():
    a = _adapter()
    assert a.name == "dnsgen"
    assert a.is_active is False
    assert a.default_on is False
    assert a.consumes == ("subdomain",)
    assert a.produces == ("subdomain",)
