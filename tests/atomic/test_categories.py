"""Atomic checks for the 28-category registry: completeness, contract integrity,
seed routing, planner ordering, and profile resolution."""
from __future__ import annotations

from recontool import categories as C


def test_all_28_present_and_valid():
    errs = C.validate()
    assert errs == [], f"registry integrity errors: {errs}"
    cats = C.load_categories()
    assert set(cats) == set(range(1, 29))


def test_every_category_has_full_contract():
    for cid, c in C.load_categories().items():
        for field in C.REQUIRED_FIELDS:
            assert field in c, f"cat {cid} missing {field}"
        # resolved contract exposes the build-ready expansions
        r = C.resolve(c)
        assert r["provenance_fields"], cid
        assert "retry_policy" in r and "quota_policy" in r


def test_dedupe_keys_resolve_to_canonical_forms():
    r = C.resolve(C.get(2))           # passive DNS / subdomain
    assert r["dedupe_keys"]["subdomain"] == "domain:{lower_fqdn}"
    assert r["dedupe_keys"]["ip"] == "ip:{normalized}"


def test_chain_to_targets_are_valid_categories():
    ids = set(C.load_categories())
    for cid, c in C.load_categories().items():
        for t in c["chain_to"]:
            assert t in ids, f"cat {cid} chains to missing {t}"


def test_seed_routing_returns_priority_ordered_valid_ids():
    ids = set(C.load_categories())
    for st in ("domain", "ip", "asn", "url", "repo", "apk"):
        route = C.route_seed(st)
        assert route, f"no routing for {st}"
        assert all(i in ids for i in route)
        # priority-ordered (non-decreasing priority)
        prios = [C.get(i)["priority"] for i in route]
        assert prios == sorted(prios), f"{st} route not priority-ordered: {prios}"


def test_domain_seed_routes_to_discovery_first():
    route = C.route_seed("domain")
    # passive discovery (cat 2, priority 10) before active validation (cat 5, priority 52)
    assert route.index(2) < route.index(5)
    # active detection (27) is reached via chaining/gate, NOT direct seed routing
    assert 27 not in route


def test_active_categories_flagged():
    active = set(C.active_categories())
    assert 27 in active and 21 in active and 5 in active   # detection/ports/fingerprint
    assert 18 not in active and 19 not in active           # resource/engine not active


def test_resource_and_engine_categories_have_no_active_egress():
    for cid in (14, 18, 19, 28):
        assert C.get(cid)["active"] is False
