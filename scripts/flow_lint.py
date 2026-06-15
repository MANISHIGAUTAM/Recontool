#!/usr/bin/env python3
"""Flow reachability lint over the LIVE tool registry.

Reports routes that can never fire (a consumed type no tool produces), recursion
dead-ends (a produced type no tool consumes), and non-canonical types. This is the
"don't miss anything" guard for the routing-flow work — run it before/after each
milestone; it must not gain new violations.

  python scripts/flow_lint.py            # exit 1 if any violation
  python scripts/flow_lint.py --warn     # always exit 0 (report only)
  python scripts/flow_lint.py --all      # include non-schedulable tools too
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from recontool.engine.flow_graph import analyze


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--warn", action="store_true", help="exit 0 even with violations")
    ap.add_argument("--all", action="store_true", help="include non-schedulable tools")
    args = ap.parse_args()

    r = analyze(schedulable_only=not args.all)

    def show(title: str, items: list[str], note: str) -> None:
        print(f"\n{title}: {len(items)}")
        if items and note:
            print(f"  ({note})")
        for t in items:
            print(f"  - {t}")

    overlay_dw = sorted(set(r["dead_weight"]) - set(r["dead_weight_in_scope"]))
    overlay_de = sorted(set(r["dead_end"]) - set(r["dead_end_in_scope"]))

    print("=== ReconTool flow reachability lint (live ToolRegistry) ===")
    show("non-canonical types", r["non_canonical"],
         "not in categories.yaml meta.dedupe_forms")
    show("dead-weight IN SCOPE (consumed, 0 producers, not a seed)",
         r["dead_weight_in_scope"], "tools consuming these can never be scheduled")
    show("dead-end IN SCOPE (produced, 0 consumers, not terminal)",
         r["dead_end_in_scope"], "recursion stops here")
    show("overlay/deferred gaps (off-by-default + file-analysis/enrichment follow-on)",
         overlay_dw + overlay_de, "tracked, not core-flow breaks — see flow_graph")

    in_scope = (len(r["non_canonical"]) + len(r["dead_weight_in_scope"])
                + len(r["dead_end_in_scope"]))
    print(f"\nIN-SCOPE violations: {in_scope}  "
          f"(+{len(overlay_dw) + len(overlay_de)} overlay, informational)")
    return 1 if (in_scope and not args.warn) else 0


if __name__ == "__main__":
    sys.exit(main())
