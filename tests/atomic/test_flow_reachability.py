"""Routing-flow reachability invariants over the LIVE tool registry.

The engine routes on ``ToolRegistry`` (not the flow_plan/tool_row planning view), so
these assertions run against ``flow_graph.analyze()`` — the same producer/consumer
graph ``RouteIndex`` builds. Two guards:

  1. The canonical vocabulary is complete: every consumed/produced type has a
     ``meta.dedupe_forms`` entry (M1). This must stay at zero.
  2. No NEW broken routes: in-scope dead-weight/dead-end types stay within a frozen
     baseline. As milestones M3-M9 wire the missing producers/consumers they REMOVE
     entries from these baselines (tighten the assertion); nothing may ADD one.

Pure: no network, no DB, no subprocess.
"""
from __future__ import annotations

from recontool.adapters.base import Event
from recontool.engine.flow_graph import analyze
from recontool.engine.runner import discovered_assets

# Known in-scope gaps as of M1/M2. Each milestone that closes a route deletes its
# entry here. The test fails if a type OUTSIDE these sets becomes unreachable —
# i.e. someone added a consumer/producer with no counterpart (a new broken route).
# live_host removed by M3 (httpx now produces it; active/deep layer consumes it).
DEAD_WEIGHT_BASELINE = {"cpe", "cve", "hash", "keyword"}
# M6 reclassified endpoint/param/tech/cert as recursion-terminals (evidence, not
# re-fed — see flow_graph.TERMINAL_TYPES). Only `document` remains (M8 wires it).
DEAD_END_BASELINE = {"document"}


def test_canonical_vocabulary_complete():
    """Every type used by a schedulable tool must be in the canonical vocabulary."""
    r = analyze()
    assert r["non_canonical"] == [], (
        f"non-canonical types in the live registry (add a dedupe_form): "
        f"{r['non_canonical']}"
    )


def test_no_new_broken_routes():
    """In-scope dead-weight/dead-end stay within the frozen baseline (no regressions)."""
    r = analyze()
    new_dw = set(r["dead_weight_in_scope"]) - DEAD_WEIGHT_BASELINE
    new_de = set(r["dead_end_in_scope"]) - DEAD_END_BASELINE
    assert not new_dw, f"NEW dead-weight routes (consumed, nothing produces): {sorted(new_dw)}"
    assert not new_de, f"NEW dead-end routes (produced, nothing consumes): {sorted(new_de)}"


def test_endpoints_are_not_re_fed_no_rescan():
    """M6 no-rescan invariant: endpoint events (the gau/katana firehose) must NOT
    become recursion keys — only asset events re-feed. Re-feeding every crawled URL
    would explode the scan. A bounded live_host/url ASSET still recurses."""
    events = [
        Event.endpoint("katana", "https://app.example.com/a?x=1", source="katana"),
        Event.endpoint("gau", "https://app.example.com/old/page.php", source="gau"),
        Event.asset("httpx", "live_host", "https://app.example.com", is_live=True),
    ]
    refed = {t for t, _ in discovered_assets(events)}
    assert "endpoint" not in refed, "endpoints must not be re-fed (firehose guard)"
    assert "url" not in refed, "raw endpoint URLs must not be re-fed as url keys"
    assert "live_host" in refed, "bounded validated assets still recurse"


def test_graph_has_core_chains():
    """Sanity: the working core chains are present in the live graph."""
    r = analyze()
    prod, cons = r["producers"], r["consumers"]
    # domain -> subdomain -> (resolve) ip -> service ; bucket/repo reachable
    assert prod.get("subdomain"), "no subdomain producers"
    assert cons.get("subdomain"), "no subdomain consumers"
    assert prod.get("ip") and cons.get("ip"), "ip chain missing"
    assert prod.get("service") and cons.get("service"), "service chain missing"
