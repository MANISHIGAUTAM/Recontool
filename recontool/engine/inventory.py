"""Canonical tool-inventory ingestion.

The hand-curated YAML files (``config/tools.yaml`` + ``config/tools_generic.yaml``)
describe ~75 tools with full invocation/IO contracts. The authoritative catalogue
of every reconnaissance tool lives in ``data/tool_inventory.json`` (532 canonical
tools, deduplicated by slug). This module turns each inventory record into a
``ToolSpec``-compatible dict so the registry can span the *entire* canonical set,
not just the curated subset.

Design rules (see docs/engine/02-tool-registry.md):

* **Slug is the canonical identity.** Curated entries OVERRIDE inventory-derived
  defaults for the same slug; inventory provides the base for the long tail.
* **Section -> category is 1:1** (inventory sections are numbered 1..19 and map
  onto the first 19 of the 28 engine categories). Multi-section tools keep every
  membership in ``categories_all`` but pick the lowest section number as the
  deterministic primary category.
* **Category -> phase** is a fixed, documented table (``CATEGORY_PHASE``).
* **classification -> type/is_active**: passive -> passive, active/hybrid -> active.
* **integration_modes -> integration/binary**: api or cli tools are auto-executable
  (cli binary inferred from slug); web/gui/dataset/mobile-only tools are registered
  but flagged ``non_executable`` with a clear reason so the orchestrator skips them.
* Input/output key types are inherited from the category contract
  (``config/categories.yaml``) so inventory-derived tools chain correctly.

Everything here is pure (stdlib + json); no network, no subprocess.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from recontool.categories import load_categories
from recontool.config import REPO_ROOT

INVENTORY_JSON = REPO_ROOT / "data" / "tool_inventory.json"

# Sentinel marking a tool that was materialised from the canonical inventory
# rather than from a hand-curated YAML contract.
INVENTORY_DERIVED = "inventory_derived"

# ---------------------------------------------------------------------------
# Deterministic mappings
# ---------------------------------------------------------------------------

# Inventory sections are "N. Title"; section N maps directly to engine category N.
# (Categories 20-28 are deep/active engine categories with no inventory section.)
SECTION_TO_CATEGORY: dict[int, int] = {n: n for n in range(1, 20)}

# Category -> pipeline phase. Derived from config/categories.yaml stages and the
# dominant phase of the curated tools in each category (see docs).
CATEGORY_PHASE: dict[int, str] = {
    1: "p1_seed",        # Internet-wide search / asset discovery
    2: "p1_seed",        # Passive DNS & subdomain enumeration
    3: "p3_enrichment",  # WHOIS / ASN / BGP / network intel
    4: "p3_enrichment",  # Search-engine dorking & index recon
    5: "p4_verify",      # Web technology fingerprinting (active)
    6: "p3_enrichment",  # Historical & archive recon
    7: "p3_enrichment",  # Email / username / identity
    8: "p3_enrichment",  # Social media recon
    9: "p3_enrichment",  # GitHub / GitLab / source-code recon
    10: "p3_enrichment", # Cloud & storage recon
    11: "p3_enrichment", # Metadata & document recon
    12: "p6_vuln",       # Malware / IOC / threat intel (CVE mapping)
    13: "p4_verify",     # Visual recon & screenshotting (active)
    14: "p1_seed",       # Frameworks & automation suites
    15: "p3_enrichment", # Physical / geo / wireless
    16: "p3_enrichment", # Dark web & onion recon
    17: "p3_enrichment", # APIs & intelligence feeds
    18: "p3_enrichment", # Massive living indexes (resource; non-executable)
    19: "p1_seed",       # Common recon workflows (preset; non-executable)
    20: "p5_deep",       # Content & directory discovery
    21: "p4_verify",     # Port scanning & service detect
    22: "p5_deep",       # JavaScript analysis & secrets
    23: "p5_deep",       # API & GraphQL recon
    24: "p4_verify",     # TLS/SSL & certificate analysis
    25: "p5_deep",       # Parameter discovery & fuzz prep
    26: "p5_deep",       # Mobile / APK recon
    27: "p6_vuln",       # Active vulnerability detection
    28: "p3_enrichment", # Wordlists & recon resources
}

# Categories that are reference/preset material, never network-executed.
RESOURCE_CATEGORIES = {18, 19}

# Integration modes that imply a programmatic execution path.
EXECUTABLE_MODES = ("api", "cli")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def slugify(name: str) -> str:
    """Normalise a tool name to the same slug style used by the inventory.

    ``"Abuse.ch" -> "abuse-ch"``, ``"crt.sh" -> "crt-sh"``.
    """
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def section_number(section: str) -> int | None:
    """Extract the leading integer from a section label like ``"12. Malware..."``."""
    m = re.match(r"\s*(\d+)", section or "")
    return int(m.group(1)) if m else None


def primary_category(sections: list[str]) -> int:
    """Deterministic primary category = lowest section number present (else 0)."""
    nums = [n for n in (section_number(s) for s in sections or []) if n is not None]
    if not nums:
        return 0
    return SECTION_TO_CATEGORY.get(min(nums), min(nums))


def all_categories(sections: list[str]) -> list[int]:
    """Every category a tool belongs to (preserves multi-section membership)."""
    nums = sorted({n for n in (section_number(s) for s in sections or []) if n is not None})
    return [SECTION_TO_CATEGORY.get(n, n) for n in nums]


def phase_for_category(category: int) -> str:
    return CATEGORY_PHASE.get(category, "p3_enrichment")


def classification_to_type(classification: str) -> tuple[str, bool]:
    """Map passive/active/hybrid -> (type, is_active)."""
    c = (classification or "").lower()
    if c == "active":
        return "active", True
    if c == "hybrid":
        # Hybrid tools can touch the target; treat as active for safety gating.
        return "hybrid", True
    return "passive", False


def derive_integration(modes: list[str], slug: str) -> tuple[str, str]:
    """Return (integration, binary). CLI tools infer their binary from the slug.

    Preference order: cli (we can synthesise an invocation) > api > first mode.
    """
    modes = modes or []
    if "cli" in modes:
        return "cli", slug.replace("-", "")
    if "api" in modes:
        return "api", ""
    return (modes[0] if modes else ""), ""


def non_executable_reason(modes: list[str], web_only: bool, category: int) -> str | None:
    """Return a clear reason if the tool cannot be auto-executed, else None."""
    if category in RESOURCE_CATEGORIES:
        return (
            "resource_index: reference/awesome-list, never network-executed"
            if category == 18
            else "workflow_preset: composes other categories, not a runnable tool"
        )
    modes = modes or []
    if any(m in modes for m in EXECUTABLE_MODES):
        return None
    if not modes:
        return "no_integration_mode: no documented programmatic interface"
    if web_only or modes == ["web"]:
        return "web_only: interactive website, no API/CLI to invoke"
    descriptor = "/".join(modes)
    return f"{descriptor}_only: no API/CLI interface to invoke programmatically"


def category_io(category: int) -> tuple[list[str], list[str]]:
    """Input/output key types for a category, from config/categories.yaml.

    These let inventory-derived tools chain through the scheduler exactly like
    curated tools (eligibility = consumed types intersect available keys).
    """
    try:
        contract = load_categories().get(category, {})
    except Exception:  # noqa: BLE001 - missing/broken yaml must not crash loading
        contract = {}
    inputs = list(contract.get("input_types", []) or [])
    outputs = list(contract.get("output_types", []) or [])
    return inputs, outputs


# ---------------------------------------------------------------------------
# Inventory record -> ToolSpec dict
# ---------------------------------------------------------------------------
def build_inventory_spec(raw: dict[str, Any]) -> dict[str, Any]:
    """Translate one canonical inventory record into a ToolSpec-compatible dict."""
    name = raw.get("name") or raw.get("slug") or "unknown"
    slug = raw.get("slug") or slugify(name)
    sections = raw.get("sections") or []
    category = primary_category(sections)
    cats_all = all_categories(sections)
    phase = phase_for_category(category)
    tool_type, is_active = classification_to_type(raw.get("classification", "passive"))
    modes = raw.get("integration_modes") or []
    integration, binary = derive_integration(modes, slug)
    web_only = bool(raw.get("web_only", False))

    reason = non_executable_reason(modes, web_only, category)
    non_exec = reason is not None

    consumes, produces = category_io(category)

    # Compose human-readable purpose/notes from inventory free-text fields.
    best_use = raw.get("best_use") or []
    notes_list = raw.get("notes") or []
    caveats = raw.get("caveats") or []
    purpose = "; ".join(best_use) if best_use else ""
    note_parts: list[str] = []
    if notes_list:
        note_parts.extend(notes_list)
    if caveats:
        note_parts.append("caveats: " + "; ".join(caveats))
    notes = " | ".join(note_parts)

    spec: dict[str, Any] = {
        "name": name,
        "slug": slug,
        "category": category,
        "categories_all": cats_all,
        "phase": phase,
        "type": tool_type,
        "is_active": is_active,
        "integration": integration,
        "binary": binary,
        "purpose": purpose,
        "notes": notes,
        "supported_input_types": consumes,
        "consumes": consumes,
        "output_types": produces,
        "produces": produces,
        # Provenance / quality metadata straight from the inventory.
        "classification": raw.get("classification", ""),
        "confidence_score": float(raw.get("confidence_score") or 0.0),
        "reliability": raw.get("reliability", "") or "",
        "scale": raw.get("scale", "") or "",
        "cost_tier": raw.get("cost_tier", "") or "",
        "data_quality": "; ".join(raw.get("data_quality_values") or []),
        "web_only": web_only,
        "sections": list(sections),
        "aliases": list(raw.get("possible_aliases") or []),
        "provenance": raw.get("provenance", "") or "",
        # Bookkeeping / queryability.
        "source": "inventory",
        "validation_status": INVENTORY_DERIVED,
        "non_executable": non_exec,
        "non_executable_reason": reason or "",
        # Non-executable tools are disabled so the scheduler skips them gracefully;
        # executable inventory stubs stay enabled and selectable.
        "enabled": not non_exec,
        "default_on": False,
        "metadata": {
            "integration_modes": list(modes),
            "worth_values": raw.get("worth_values") or [],
            "difficulty_values": raw.get("difficulty_values") or [],
            "free_paid_values": raw.get("free_paid_values") or [],
            "scale_values": raw.get("scale_values") or [],
            "categories": raw.get("categories") or [],
            "row_refs": raw.get("row_refs") or [],
            "appearances": raw.get("appearances", 0),
        },
    }
    return spec


def load_inventory_records(path: Path | None = None) -> list[dict[str, Any]]:
    """Read the raw inventory tool records. Returns [] if the file is absent."""
    path = path or INVENTORY_JSON
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:  # noqa: BLE001 - malformed inventory must not crash loading
        return []
    tools = data.get("tools", [])
    return tools if isinstance(tools, list) else []


def load_inventory_specs(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Return {slug: ToolSpec-dict} for every canonical inventory tool (deduped)."""
    specs: dict[str, dict[str, Any]] = {}
    for raw in load_inventory_records(path):
        spec = build_inventory_spec(raw)
        slug = spec["slug"]
        if not slug:
            continue
        # First occurrence wins (inventory is already slug-deduped, but be safe).
        specs.setdefault(slug, spec)
    return specs
