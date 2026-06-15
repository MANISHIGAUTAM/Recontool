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

from recontool.engine.flow_graph import analyze

# Known in-scope gaps as of M1/M2. Each milestone that closes a route deletes its
# entry here. The test fails if a type OUTSIDE these sets becomes unreachable —
# i.e. someone added a consumer/producer with no counterpart (a new broken route).
DEAD_WEIGHT_BASELINE = {"cpe", "cve", "hash", "keyword", "live_host"}
DEAD_END_BASELINE = {"cert", "document", "endpoint", "param", "tech"}


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


def test_graph_has_core_chains():
    """Sanity: the working core chains are present in the live graph."""
    r = analyze()
    prod, cons = r["producers"], r["consumers"]
    # domain -> subdomain -> (resolve) ip -> service ; bucket/repo reachable
    assert prod.get("subdomain"), "no subdomain producers"
    assert cons.get("subdomain"), "no subdomain consumers"
    assert prod.get("ip") and cons.get("ip"), "ip chain missing"
    assert prod.get("service") and cons.get("service"), "service chain missing"
