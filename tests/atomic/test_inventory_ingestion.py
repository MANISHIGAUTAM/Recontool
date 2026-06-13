"""Unit tests for canonical tool-inventory ingestion into the ToolRegistry.

Covers (see docs/engine/02-tool-registry.md):
  * inventory loader field mapping (classification/integration/sections/metadata)
  * slug deduplication (532 records -> 531 unique slugs; nuclei-templates dupe)
  * YAML-override precedence (curated contracts beat inventory stubs)
  * section -> category and category -> phase mapping
  * classification -> type / is_active mapping
  * count assertion: the registry covers the full canonical slug set
  * inventory-derived tools are flagged queryably
  * web/gui/dataset-only tools are marked non-executable with a reason
"""
from __future__ import annotations

import json

from recontool.config import REPO_ROOT
from recontool.engine import inventory as inv
from recontool.engine.registry import ToolRegistry

INVENTORY_JSON = REPO_ROOT / "data" / "tool_inventory.json"


# ---------------------------------------------------------------------------
# Pure mapping helpers
# ---------------------------------------------------------------------------
def test_slugify_matches_inventory_style():
    assert inv.slugify("Abuse.ch") == "abuse-ch"
    assert inv.slugify("crt.sh") == "crt-sh"
    assert inv.slugify("Amass (passive)") == "amass-passive"


def test_section_to_category_is_one_to_one():
    for n in range(1, 20):
        assert inv.SECTION_TO_CATEGORY[n] == n


def test_primary_category_picks_lowest_section():
    sections = ["12. Malware, IOC & Threat Intel Platforms",
                "2. Passive DNS & Subdomain Enumeration"]
    assert inv.primary_category(sections) == 2
    assert inv.all_categories(sections) == [2, 12]


def test_phase_for_category_table():
    assert inv.phase_for_category(1) == "p1_seed"
    assert inv.phase_for_category(5) == "p4_verify"
    assert inv.phase_for_category(12) == "p6_vuln"
    assert inv.phase_for_category(27) == "p6_vuln"
    # Unknown category falls back deterministically.
    assert inv.phase_for_category(999) == "p3_enrichment"


def test_classification_to_type_mapping():
    assert inv.classification_to_type("passive") == ("passive", False)
    assert inv.classification_to_type("active") == ("active", True)
    assert inv.classification_to_type("hybrid") == ("hybrid", True)
    assert inv.classification_to_type("") == ("passive", False)


def test_derive_integration_prefers_cli_and_infers_binary():
    assert inv.derive_integration(["cli", "api"], "find-omain") == ("cli", "findomain")
    assert inv.derive_integration(["api"], "shodan") == ("api", "")
    assert inv.derive_integration(["web"], "wigle") == ("web", "")


def test_non_executable_reason_for_web_and_resource():
    assert inv.non_executable_reason(["api"], False, 1) is None
    assert inv.non_executable_reason(["cli"], False, 2) is None
    assert "web_only" in inv.non_executable_reason(["web"], True, 8)
    assert "gui" in inv.non_executable_reason(["gui"], False, 13)
    # Resource/preset categories are never executable regardless of mode.
    assert "resource_index" in inv.non_executable_reason(["api"], False, 18)
    assert "workflow_preset" in inv.non_executable_reason(["cli"], False, 19)


# ---------------------------------------------------------------------------
# build_inventory_spec field mapping
# ---------------------------------------------------------------------------
def test_build_inventory_spec_maps_all_fields():
    raw = {
        "name": "Abuse.ch", "slug": "abuse-ch", "classification": "passive",
        "integration_modes": ["api"], "web_only": False, "cost_tier": "free",
        "scale": "Large", "reliability": "Very High", "confidence_score": 0.95,
        "sections": ["12. Malware, IOC & Threat Intel Platforms"],
        "best_use": ["IOC feeds & malware infra"], "notes": ["Core CTI ecosystem"],
        "possible_aliases": ["abusech"], "provenance": "extracted_from_spreadsheet",
        "caveats": ["rate limited"], "data_quality_values": ["High"],
    }
    spec = inv.build_inventory_spec(raw)
    assert spec["slug"] == "abuse-ch"
    assert spec["category"] == 12
    assert spec["phase"] == "p6_vuln"
    assert spec["type"] == "passive"
    assert spec["is_active"] is False
    assert spec["integration"] == "api"
    assert spec["confidence_score"] == 0.95
    assert spec["reliability"] == "Very High"
    assert spec["cost_tier"] == "free"
    assert spec["source"] == "inventory"
    assert spec["validation_status"] == inv.INVENTORY_DERIVED
    assert spec["purpose"] == "IOC feeds & malware infra"
    assert "Core CTI ecosystem" in spec["notes"]
    assert "rate limited" in spec["notes"]
    assert spec["aliases"] == ["abusech"]
    # Category 12 IO inherited from the category contract.
    assert "ip" in spec["consumes"]
    assert "finding" in spec["produces"] or "ioc" in spec["produces"]


def test_build_inventory_spec_cli_infers_binary():
    raw = {"name": "Subfinder", "slug": "subfinder", "classification": "passive",
           "integration_modes": ["cli"], "sections": ["2. Passive DNS & Subdomain Enumeration"]}
    spec = inv.build_inventory_spec(raw)
    assert spec["integration"] == "cli"
    assert spec["binary"] == "subfinder"
    assert spec["non_executable"] is False
    assert spec["enabled"] is True


def test_build_inventory_spec_web_only_non_executable():
    raw = {"name": "WiGLE", "slug": "wigle", "classification": "passive",
           "integration_modes": ["web"], "web_only": True,
           "sections": ["15. Physical, Geo & Wireless Recon"]}
    spec = inv.build_inventory_spec(raw)
    assert spec["non_executable"] is True
    assert "web_only" in spec["non_executable_reason"]
    assert spec["enabled"] is False


# ---------------------------------------------------------------------------
# load_inventory_specs: dedup
# ---------------------------------------------------------------------------
def test_inventory_specs_deduped_by_slug():
    records = json.loads(INVENTORY_JSON.read_text())["tools"]
    distinct = {t["slug"] for t in records}
    specs = inv.load_inventory_specs()
    # 532 records collapse to the distinct-slug count (one dupe: nuclei-templates).
    assert len(specs) == len(distinct)
    assert len(records) == 532
    assert len(distinct) == 531


# ---------------------------------------------------------------------------
# Registry-level integration of inventory + curated
# ---------------------------------------------------------------------------
def test_registry_covers_full_canonical_slug_set():
    reg = ToolRegistry.load()
    canonical = reg.canonical_slugs()
    # Every canonical slug is represented (either curated-override or inventory).
    assert canonical <= reg.covered_slugs()
    assert len(canonical) == 531  # 532 records, slug-deduped


def test_registry_loads_far_more_than_curated():
    reg = ToolRegistry.load()
    stats = reg.stats()
    assert stats["curated"] == 97          # 81 + 10 (gf/unfurl) + 1 (github_org_repos) + 5 (github_search dorks)
    assert stats["inventory_derived"] >= 450
    assert stats["total"] >= 530
    assert stats["total"] == stats["curated"] + stats["inventory_derived"]


def test_curated_overrides_inventory_precedence():
    """A curated tool that shares a slug with an inventory record keeps its
    detailed contract while inheriting inventory quality metadata."""
    reg = ToolRegistry.load()
    shodan = reg.get("shodan")
    assert shodan is not None
    assert shodan.source == "curated"
    # Curated contract preserved (not downgraded to a stub).
    assert shodan.integration in ("api", "cli")
    assert shodan.supported_input_types  # IO contract intact
    # Inventory quality metadata merged in.
    assert shodan.confidence_score > 0


def test_inventory_derived_tools_are_flagged():
    reg = ToolRegistry.load()
    inv_tools = reg.inventory_tools()
    assert inv_tools, "expected inventory-derived tools"
    for t in inv_tools[:50]:
        assert t.source == "inventory"
        assert t.validation_status == inv.INVENTORY_DERIVED
        assert t.is_inventory_derived


def test_web_only_tools_marked_non_executable_with_reason():
    reg = ToolRegistry.load()
    non_exec = reg.non_executable_tools()
    assert non_exec, "expected some non-executable tools"
    for t in non_exec:
        assert t.non_executable is True
        assert t.non_executable_reason  # never silent
        assert t.enabled is False        # scheduler skips them


def test_executable_tools_have_api_or_cli():
    reg = ToolRegistry.load()
    # Inventory-derived executable tools always carry an api/cli integration mode
    # (curated tools may use other mechanisms like bespoke python/git adapters).
    for t in reg.executable_tools():
        if t.is_inventory_derived:
            assert t.integration in ("api", "cli"), f"{t.name} integration={t.integration!r}"


def test_by_slug_lookup():
    reg = ToolRegistry.load()
    t = reg.by_slug("abuse-ch")
    assert t is not None
    assert t.slug == "abuse-ch"
