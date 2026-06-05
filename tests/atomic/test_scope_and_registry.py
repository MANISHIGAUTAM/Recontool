"""Atomic checks C5 (Scope) and C6 (Chain) + dedupe-key + registry integrity."""
from __future__ import annotations

from recontool.adapters.registry import PHASES, all_adapters, load_builtin
from recontool.config import load_tool_registry
from recontool.core import dedupe
from recontool.core.scope import Scope, apex_domain, classify_seed


# ── C5: scope ──────────────────────────────────────────────────────────────
def test_scope_allows_subdomains_blocks_others():
    sc = Scope.from_seed("www.example.com", "domain")
    assert sc.contains("subdomain", "api.example.com")
    assert sc.contains("domain", "example.com")
    assert not sc.contains("subdomain", "evil.attacker.com")


def test_scope_deny_overrides_allow():
    sc = Scope(allow_domains={"example.com"}, deny_domains={"secret.example.com"})
    assert sc.contains("subdomain", "ok.example.com")
    assert not sc.contains("subdomain", "secret.example.com")


def test_scope_cidr():
    sc = Scope.from_seed("10.0.0.0/24", "cidr")
    assert sc.contains("ip", "10.0.0.5")
    assert not sc.contains("ip", "10.0.1.5")


def test_classify_seed():
    assert classify_seed("www.xyz.com") == "domain"
    assert classify_seed("1.2.3.4") == "ip"
    assert classify_seed("10.0.0.0/24") == "cidr"
    assert classify_seed("AS13335") == "asn"
    assert classify_seed("https://x.com/a") == "url"


def test_apex_domain():
    assert apex_domain("www.example.com") == "example.com"
    assert apex_domain("a.b.c.example.co") == "example.co"  # naive last-2 labels
    assert apex_domain("https://api.example.com/path") == "example.com"


def test_is_subdomain_of_rejects_false_positives():
    from recontool.core.scope import is_subdomain_of
    # real subdomains / apex
    assert is_subdomain_of("api.example.com", "example.com")
    assert is_subdomain_of("example.com", "example.com")
    assert is_subdomain_of("*.example.com", "example.com")
    # sibling-suffix collision must be rejected
    assert not is_subdomain_of("m.testexample.com", "example.com")
    assert not is_subdomain_of("notexample.com", "example.com")
    # emails are not hosts
    assert not is_subdomain_of("subjectname@example.com", "example.com")


# ── dedupe keys ──────────────────────────────────────────────────────────────
def test_dedupe_key_canonicalization():
    assert dedupe.dedupe_key("subdomain", "API.Example.com.") == \
        dedupe.dedupe_key("subdomain", "api.example.com")


def test_dedupe_key_url_param_order():
    a = dedupe.endpoint_key("https://x.com/p?b=2&a=1")
    b = dedupe.endpoint_key("https://x.com/p?a=1&b=2")
    assert a == b   # query params sorted -> same key


# ── C6: chaining + registry integrity ────────────────────────────────────────
def test_all_adapters_register_in_valid_phase():
    load_builtin()
    for name, cls in all_adapters().items():
        assert getattr(cls, "phase", None) in PHASES, name
        assert cls.consumes, f"{name} must declare consumes"


def test_category1_adapters_present():
    load_builtin()
    names = set(all_adapters())
    for expected in ("uncover", "shodan", "internetdb", "censys", "netlas",
                     "leakix", "fullhunt", "urlscan", "greynoise", "criminalip"):
        assert expected in names, f"missing Cat-1 adapter: {expected}"


def test_chain_outputs_feed_some_consumer():
    """Every produced artifact type should be consumable by some adapter
    (or be a terminal type), proving the pipeline actually chains."""
    load_builtin()
    consumed = set()
    for cls in all_adapters().values():
        consumed.update(cls.consumes)
    terminal = {"finding", "tag", "screenshot", "service", "cert", "bucket", "email", "cidr", "asn"}
    for name, cls in all_adapters().items():
        for out in cls.produces:
            assert out in consumed or out in terminal, \
                f"{name} produces '{out}' that nothing consumes"


def test_tool_registry_contract_complete():
    reg = load_tool_registry()
    assert len(reg) > 50
    for name, t in reg.items():
        for field in ("category", "type", "integration", "input", "output"):
            assert field in t, f"{name} missing '{field}' in tools.yaml"
        assert t["type"] in ("passive", "active"), name
