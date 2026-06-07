#!/usr/bin/env python3
"""Build the normalized tool inventory from the raw spreadsheet rows.

Source of truth : data/recontools_raw.tsv  (every spreadsheet row, verbatim)
Outputs:
  data/tool_rows_raw.json        - every raw row, with stable row ids
  data/tool_inventory.json       - canonical (deduplicated) tools + provenance
  docs/inventory/TOOL-INVENTORY.md - human-readable inventory
  docs/tools/<slug>.md           - per-tool capability doc (one per canonical tool)
  docs/tools/README.md           - per-tool docs index

Design rules (match the task spec):
  * EVERY raw row is preserved (data/tool_rows_raw.json + row_refs on each tool).
  * Dedup is by EXACT normalized name only -> repeated appearances of the same
    tool collapse to ONE canonical record that keeps all category memberships and
    raw row references. Different names are NEVER merged (aliases preserved);
    likely variants are reported as `possible_aliases` for human review.
  * Tags derived: classification (passive/active/hybrid), integration modes
    (cli/api/web/gui/dataset/...), web_only, cost tier, scale, reliability,
    confidence score, and a caveats list.
  * Everything here is provenance = "extracted_from_spreadsheet". Suggested
    additions live separately in docs/pipeline/01-gap-analysis.md and are NEVER
    written into this inventory.

Pure standard library. Run:  python -m recontool.inventory.build_inventory
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
RAW_TSV = REPO / "data" / "recontools_raw.tsv"
DATA_DIR = REPO / "data"
INV_DOC_DIR = REPO / "docs" / "inventory"
TOOLS_DOC_DIR = REPO / "docs" / "tools"

COLUMNS = [
    "tool", "category", "passive_active", "free_paid", "cli_api",
    "difficulty", "data_quality", "scale", "best_use", "worth", "notes",
]

# ── ordering / scoring maps ──────────────────────────────────────────────────
SCALE_ORDER = {
    "small": 1, "medium": 2, "medium-large": 3, "large": 4,
    "massive": 5, "internet-scale": 6, "enterprise": 6,
}
WORTH_SCORE = {
    "very high": 0.95, "high": 0.80, "medium-high": 0.70, "medium": 0.60,
    "low-medium": 0.45, "medium-low": 0.45, "low": 0.30, "niche": 0.40,
}
# tokens that indicate an integration MODE (vs a quality rating like "Excellent")
MODE_TOKENS = {
    "cli": "cli", "api": "api", "web": "web", "gui": "gui",
    "browser": "browser", "dataset": "dataset", "download": "dataset",
    "powershell": "cli", "self-hosted": "self_hosted", "git": "api",
    "github": "web", "mobile": "mobile", "sdk": "api", "limited": None,
    "excellent": None, "good": None, "mixed": "mixed", "ish": None,
}
WEB_ONLY_MODES = {"web", "gui", "browser", "mobile"}
DEPRECATED_HINTS = ("deprecat", "aging", "older", "legacy", "broken",
                    "semi-maintained", "limited adoption", "lesser-known", "niche")
RESOURCE_HINTS = ("index", "collection", "list", "resources", "knowledge base",
                  "curated", "aggregat", "framework category", "toolkit")


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "tool"


def norm_key(name: str) -> str:
    """Exact-match dedup key: lowercase, collapse internal whitespace/punct."""
    return re.sub(r"\s+", " ", name.strip().lower())


# ── parsing ──────────────────────────────────────────────────────────────────
def parse_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    section = None
    rid = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# SECTION:"):
            section = line[len("# SECTION:"):].strip()
            continue
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        # pad/truncate to 11 columns; keep raw for traceability
        fields = (parts + [""] * len(COLUMNS))[: len(COLUMNS)]
        row = dict(zip(COLUMNS, (f.strip() for f in fields)))
        row["row_id"] = rid
        row["section"] = section
        row["_raw"] = line
        row["_col_count"] = len(parts)
        rows.append(row)
        rid += 1
    return rows


# ── derivation helpers ───────────────────────────────────────────────────────
def classify(pa_values: set[str]) -> tuple[str, bool]:
    vals = {v.lower() for v in pa_values if v}
    flat: set[str] = set()
    for v in vals:
        for part in re.split(r"[/,]", v):
            flat.add(part.strip())
    disagree = False
    if "hybrid" in flat:
        return "hybrid", disagree
    has_p, has_a = "passive" in flat, "active" in flat
    if has_p and has_a:
        return "hybrid", True  # rows disagree -> treat as hybrid + caveat
    if has_a:
        return "active", disagree
    if has_p:
        return "passive", disagree
    return "unknown", disagree


def integration_modes(cli_api_values: set[str]) -> tuple[list[str], list[str]]:
    modes: set[str] = set()
    ratings: set[str] = set()
    for cell in cli_api_values:
        for tok in re.split(r"[/ ]", cell.lower()):
            tok = tok.strip()
            if not tok:
                continue
            if tok in ("excellent", "good", "limited"):
                ratings.add(tok)
            mapped = MODE_TOKENS.get(tok)
            if mapped:
                modes.add(mapped)
    return sorted(modes), sorted(ratings)


def cost_tier(free_paid_values: set[str]) -> str:
    vals = {v.lower() for v in free_paid_values if v}
    if not vals:
        return "unknown"
    flat: set[str] = set()
    for v in vals:
        for part in re.split(r"[/,]", v):
            flat.add(part.strip())
    has_free = "free" in flat or "open source" in flat
    has_freemium = "freemium" in flat
    has_paid = "paid" in flat
    if has_paid and (has_free or has_freemium):
        return "freemium" if has_freemium else "mixed"
    if has_freemium:
        return "freemium"
    if has_paid:
        return "paid"
    if has_free:
        return "free"
    return "mixed"


def top_scale(scale_values: set[str]) -> str:
    best, best_v = "", -1
    for s in scale_values:
        v = SCALE_ORDER.get(s.lower().strip(), 0)
        if v > best_v:
            best, best_v = s, v
    return best


def best_worth(worth_values: list[str]) -> tuple[str, float]:
    # pick the most generous worth seen, plus its numeric score
    best, score = "", -1.0
    for w in worth_values:
        s = WORTH_SCORE.get(w.lower().strip(), 0.5)
        if s > score:
            best, score = w, s
    return best, round(score, 2) if score >= 0 else 0.5


def build_caveats(tool: dict, disagree_pa: bool) -> list[str]:
    caveats = []
    if disagree_pa:
        caveats.append(
            "Source rows disagree on passive/active classification; treated as hybrid."
        )
    if tool["cost_tier"] == "unknown":
        caveats.append("Free/Paid not specified in source.")
    if tool["web_only"]:
        caveats.append(
            "Web/GUI/manual only in source - no documented CLI/API; not directly "
            "automatable, flag for manual or scripted-browser handling."
        )
    notes_blob = " ".join(tool["notes"]).lower()
    cats_blob = " ".join(tool["categories"]).lower()
    if any(h in notes_blob for h in DEPRECATED_HINTS):
        caveats.append("Marked deprecated/aging/niche in source notes - keep but verify.")
    if any(h in cats_blob for h in RESOURCE_HINTS) or "18." in " ".join(tool["sections"]):
        caveats.append("Reference list/index/framework, not a single executable tool.")
    if len(tool["row_refs"]) > 1:
        caveats.append(
            f"Appears in {len(tool['row_refs'])} rows across "
            f"{len(tool['sections'])} section(s); all memberships preserved."
        )
    return caveats


def find_possible_aliases(canonical: dict[str, dict]) -> None:
    """Group by first significant token; list co-members as possible_aliases.
    Informational ONLY - never merges records."""
    by_first: dict[str, list[str]] = defaultdict(list)
    for key, tool in canonical.items():
        first = re.split(r"[^a-z0-9]+", tool["name"].lower())[0]
        if first:
            by_first[first].append(key)
    for keys in by_first.values():
        if len(keys) < 2:
            continue
        for k in keys:
            others = [canonical[o]["name"] for o in keys if o != k]
            canonical[k]["possible_aliases"] = sorted(others)


# ── main build ───────────────────────────────────────────────────────────────
def build() -> dict:
    rows = parse_rows(RAW_TSV)
    canonical: dict[str, dict] = {}

    for r in rows:
        key = norm_key(r["tool"])
        t = canonical.get(key)
        if t is None:
            t = {
                "name": r["tool"].strip(),
                "slug": slugify(r["tool"]),
                "provenance": "extracted_from_spreadsheet",
                "sections": [], "categories": [],
                "_pa": set(), "_cli": set(), "_fp": set(),
                "_scale": set(), "_dq": set(), "_worth": [],
                "best_use": [], "notes": [], "difficulty": [],
                "row_refs": [], "possible_aliases": [],
            }
            canonical[key] = t
        t["row_refs"].append(r["row_id"])
        for bucket, col in (("sections", "section"), ("categories", "category")):
            val = r[col]
            if val and val not in t[bucket]:
                t[bucket].append(val)
        if r["passive_active"]:
            t["_pa"].add(r["passive_active"])
        if r["cli_api"]:
            t["_cli"].add(r["cli_api"])
        if r["free_paid"]:
            t["_fp"].add(r["free_paid"])
        if r["scale"]:
            t["_scale"].add(r["scale"])
        if r["data_quality"]:
            t["_dq"].add(r["data_quality"])
        if r["worth"]:
            t["_worth"].append(r["worth"])
        for bucket, col in (("best_use", "best_use"), ("notes", "notes"),
                            ("difficulty", "difficulty")):
            val = r[col]
            if val and val not in t[bucket]:
                t[bucket].append(val)

    # finalize derived fields
    tools = []
    for key, t in canonical.items():
        cls, disagree = classify(t["_pa"])
        modes, ratings = integration_modes(t["_cli"])
        web_only = bool(modes) and all(m in WEB_ONLY_MODES for m in modes)
        worth, score = best_worth(t["_worth"])
        final = {
            "name": t["name"],
            "slug": t["slug"],
            "provenance": t["provenance"],
            "classification": cls,
            "passive_active_values": sorted(t["_pa"]),
            "integration_modes": modes,
            "integration_support_ratings": ratings,
            "web_only": web_only,
            "cost_tier": cost_tier(t["_fp"]),
            "free_paid_values": sorted(t["_fp"]),
            "scale": top_scale(t["_scale"]),
            "scale_values": sorted(t["_scale"]),
            "data_quality_values": sorted(t["_dq"]),
            "reliability": worth,
            "confidence_score": score,
            "worth_values": sorted(set(t["_worth"])),
            "difficulty_values": sorted(set(t["difficulty"])),
            "sections": t["sections"],
            "categories": t["categories"],
            "best_use": t["best_use"],
            "notes": t["notes"],
            "row_refs": t["row_refs"],
            "appearances": len(t["row_refs"]),
            "possible_aliases": [],
        }
        final["cost_tier"] = final["cost_tier"]
        final["caveats"] = build_caveats(final, disagree)
        tools.append(final)
        canonical[key] = final  # replace for alias pass

    find_possible_aliases(canonical)
    tools = sorted(canonical.values(), key=lambda x: x["name"].lower())

    stats = {
        "raw_rows": len(rows),
        "canonical_tools": len(tools),
        "duplicate_rows_collapsed": len(rows) - len(tools),
        "sections": sorted({r["section"] for r in rows}, key=_section_sort),
        "by_classification": _count(tools, "classification"),
        "by_cost_tier": _count(tools, "cost_tier"),
        "web_only_count": sum(1 for t in tools if t["web_only"]),
        "multi_section_tools": sum(1 for t in tools if len(t["sections"]) > 1),
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(RAW_TSV.relative_to(REPO)),
        "note": "All entries extracted verbatim from ReconTools spreadsheet. "
                "Suggested additions are NOT here - see docs/pipeline/01-gap-analysis.md.",
        "stats": stats,
        "tools": tools,
        "raw_rows": rows,
    }


def _section_sort(s: str):
    m = re.match(r"\s*(\d+)\.", s or "")
    return int(m.group(1)) if m else 999


def _count(tools: list[dict], field: str) -> dict:
    out: dict[str, int] = defaultdict(int)
    for t in tools:
        out[t[field]] += 1
    return dict(sorted(out.items()))


if __name__ == "__main__":
    from recontool.inventory.render import write_all

    inv = build()
    write_all(inv, DATA_DIR, INV_DOC_DIR, TOOLS_DOC_DIR, REPO)
