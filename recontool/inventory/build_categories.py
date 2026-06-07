#!/usr/bin/env python3
"""Render the 28-category registry into build-ready docs.

Outputs:
  docs/categories/CATEGORY-CONTRACTS.md  - per-category contract (the 10 sections)
  docs/categories/BUILD-CHECKLIST.md     - implementation checklist + seed routing

Run: python -m recontool.inventory.build_categories
"""
from __future__ import annotations

from pathlib import Path

from recontool import categories as C

REPO = Path(__file__).resolve().parent.parent.parent
OUT = REPO / "docs" / "categories"


def _fmt(v):
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) if v else "—"
    if isinstance(v, dict):
        return "; ".join(f"{k}={x}" for k, x in v.items())
    return str(v)


def render_contracts() -> str:
    cats = C.load_categories()
    m = C.meta()
    L = ["# 28-Category Build-Ready Contracts\n",
         "> Generated from `config/categories.yaml` by "
         "`recontool.inventory.build_categories`. Authorized-only, no-evasion "
         "(see `docs/blueprint/`).\n",
         f"**Provenance fields (every entity):** `{', '.join(m['provenance_standard'])}`\n",
         "## Seed routing (which categories a seed activates, in planner order)\n",
         "| Seed type | Categories (priority order) |",
         "|-----------|------------------------------|"]
    for st in m.get("seed_routing", {}):
        L.append(f"| `{st}` | {', '.join(str(i) for i in C.route_seed(st))} |")
    L.append("")
    L.append("## Pipeline priority order (all categories, cheapest high-signal first)\n")
    order = C.plan_order(list(cats))
    L.append(" → ".join(f"{i}" for i in order))
    L.append("")

    for cid in sorted(cats):
        c = C.resolve(cats[cid])
        L.append(f"\n---\n\n## {cid}. {c['name']}\n")
        L.append(f"`stage={c['stage']}` · `active={c['active']}` · "
                 f"`priority={c['priority']}`\n")
        L.append(f"**1. Purpose.** {c['purpose']}\n")
        L.append(f"**2. Input schema (input_types).** `{_fmt(c['input_types'])}`\n")
        L.append(f"**3. Output schema (output_types).** `{_fmt(c['output_types'])}`\n")
        L.append("**Canonical dedupe keys.**")
        for t, form in c["dedupe_keys"].items():
            L.append(f"- `{t}` → `{form}`")
        if not c["dedupe_keys"]:
            L.append("- (none — resource/engine category)")
        L.append("")
        L.append(f"**Provenance fields.** `{', '.join(c['provenance_fields'])}`\n")
        L.append(f"**4. Chaining rules (chain_to).** → categories "
                 f"`{_fmt(c['chain_to'])}`\n")
        L.append(f"**5. Tool families.** {_fmt(c['tool_families'])}\n")
        L.append(f"**6. Priority order.** `{c['priority']}` "
                 f"(lower = earlier; cheapest high-signal first)\n")
        L.append(f"**7. Recursion logic (recursion_triggers).** {_fmt(c['recursion_triggers'])}\n")
        L.append("**8. Failure handling.**")
        L.append(f"- failure_modes: `{_fmt(c['failure_modes'])}`")
        L.append(f"- retry_policy: `{_fmt(c['retry_policy'])}`")
        L.append(f"- quota_policy: `{_fmt(c['quota_policy'])}`")
        L.append("- on exhausted quota: **defer** (planner substitutes); on repeated "
                 "failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.")
        L.append("")
        L.append(f"**9. Storage mapping.** entities: `{c['storage'].get('entities')}` · "
                 f"raw artifacts: `{c['storage'].get('raw')}`\n")
        L.append(f"**10. Operator notes.** {c['operator_notes']}\n")
    return "\n".join(L)


def render_checklist() -> str:
    cats = C.load_categories()
    impl = {  # categories with executable adapters in the repo today
        1, 2, 3, 4, 5, 6, 9, 10, 12, 13, 20, 21, 22, 23, 24, 25, 27,
    }
    live_partial = {4, 10, 23, 25}  # specced/partial
    L = ["# 28-Category Build Checklist\n",
         "> Status reflects executable adapters in this repo. ✅ wired · 🟡 partial · ⬜ specced.\n",
         "## System-wide checklist\n",
         "- [x] Preserve all 28 categories (registry: `config/categories.yaml`)",
         "- [x] Route seeds to the correct subset (`categories.route_seed`)",
         "- [x] Merge all outputs into one canonical graph (`normalize/engine.py`)",
         "- [x] Store raw artifacts separately (`core/artifacts.py`; content-addressing on roadmap)",
         "- [x] Recurse only on new frontier entities (`orchestrator/pipeline.py`)",
         "- [x] Hand off only validated live assets to active detection (auth gate + is_live filter)",
         "- [x] Diffs/reports/graph view (`report.py`; diff engine on roadmap)",
         "- [x] Provider quotas + backoff + circuit breakers (`net/circuit.py`, `net/rate_limiter.py`)",
         "- [x] Checkpoint/resume + dead-letter handling (`models.Checkpoint/DeadLetter`, CLI `replay`)",
         "- [x] Demo/test mode + mock environment + test-mode egress enforcement (`core/mode.py`, `testing/mock_env.py`)",
         "- [x] Preflight health checks (`preflight.py`, CLI `preflight`)",
         "- [x] Continuous diffing (`diff.py`, CLI `diff`)",
         "- [ ] Tuned wordlists + regex packs from learnings (cat 25/28 — roadmap G3)",
         "- [x] Archive/search/code/crawl loops linked via the graph bus",
         "",
         "## Per-category implementation status\n",
         "| # | Category | Stage | Active | Status | Adapters/notes |",
         "|---|----------|-------|:------:|:------:|----------------|"]
    for cid in sorted(cats):
        c = cats[cid]
        st = "✅" if cid in impl and cid not in live_partial else ("🟡" if cid in impl or cid in live_partial else "⬜")
        L.append(f"| {cid} | {c['name']} | {c['stage']} | "
                 f"{'yes' if c['active'] else 'no'} | {st} | "
                 f"{', '.join(c['tool_families'][:4])}… |")
    L.append("")
    L.append("Full per-category contracts: [`CATEGORY-CONTRACTS.md`](CATEGORY-CONTRACTS.md).")
    L.append("Implementation roadmap: [`../blueprint/05-diff-ai-gaps-roadmap.md`]"
             "(../blueprint/05-diff-ai-gaps-roadmap.md).")
    return "\n".join(L)


def main():
    errs = C.validate()
    if errs:
        print("VALIDATION ERRORS:")
        for e in errs:
            print("  -", e)
        raise SystemExit(1)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "CATEGORY-CONTRACTS.md").write_text(render_contracts())
    (OUT / "BUILD-CHECKLIST.md").write_text(render_checklist())
    cats = C.load_categories()
    print(f"categories: {len(cats)} (validated)")
    print(f"active: {sorted(C.active_categories())}")
    print("wrote docs/categories/CATEGORY-CONTRACTS.md + BUILD-CHECKLIST.md")


if __name__ == "__main__":
    main()
