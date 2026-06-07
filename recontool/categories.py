"""28-category registry loader + seed routing.

Loads config/categories.yaml (the build-ready category contracts) and exposes:
  load_categories()      -> {id: contract}
  meta()                 -> shared meta (dedupe_forms, profiles, seed_routing)
  route_seed(seed_type)  -> ordered list of category ids a seed activates
  plan_order(ids)        -> ids sorted by priority (cheapest high-signal first)
  resolve(contract)      -> contract with provenance/dedupe/retry/quota EXPANDED
  validate()             -> structural integrity checks (used by tests)

Pure stdlib + pyyaml. No network.
"""
from __future__ import annotations

from functools import lru_cache

from recontool.config import CONFIG_DIR

CATEGORIES_YAML = CONFIG_DIR / "categories.yaml"

REQUIRED_FIELDS = (
    "id", "name", "stage", "active", "priority", "purpose",
    "input_types", "output_types", "dedupe", "chain_to", "tool_families",
    "recursion_triggers", "retry", "quota", "failure_modes", "storage",
    "operator_notes",
)
VALID_STAGES = {
    "discover", "validate", "enrich", "network", "deep",
    "detect", "overlay", "resource", "engine",
}


@lru_cache(maxsize=1)
def _raw() -> dict:
    import yaml
    return yaml.safe_load(CATEGORIES_YAML.read_text()) or {}


def meta() -> dict:
    return _raw().get("meta", {})


@lru_cache(maxsize=1)
def load_categories() -> dict[int, dict]:
    return {c["id"]: c for c in _raw().get("categories", [])}


def get(cat_id: int) -> dict:
    return load_categories()[cat_id]


def route_seed(seed_type: str) -> list[int]:
    """Category ids a seed type activates, ordered by priority (planner order)."""
    ids = meta().get("seed_routing", {}).get(seed_type, [])
    return plan_order(ids)


def plan_order(ids: list[int]) -> list[int]:
    """Sort category ids by priority (lower = cheaper/earlier high-signal)."""
    cats = load_categories()
    return sorted(ids, key=lambda i: cats.get(i, {}).get("priority", 999))


def resolve(contract: dict) -> dict:
    """Expand profile references into concrete contract fields (build-ready)."""
    m = meta()
    out = dict(contract)
    out["provenance_fields"] = m.get("provenance_standard", [])
    out["dedupe_keys"] = {
        t: m.get("dedupe_forms", {}).get(t, f"{t}:{{value}}")
        for t in contract.get("dedupe", [])
    }
    out["retry_policy"] = m.get("retry_profiles", {}).get(contract.get("retry"), {})
    out["quota_policy"] = m.get("quota_profiles", {}).get(contract.get("quota"), {})
    return out


def active_categories() -> list[int]:
    return [i for i, c in load_categories().items() if c.get("active")]


def validate() -> list[str]:
    """Return a list of integrity errors (empty = OK)."""
    errs: list[str] = []
    cats = load_categories()
    ids = set(cats)
    if ids != set(range(1, 29)):
        errs.append(f"expected categories 1..28, got {sorted(ids)}")
    m = meta()
    dforms = m.get("dedupe_forms", {})
    retry_p = m.get("retry_profiles", {})
    quota_p = m.get("quota_profiles", {})
    for cid, c in cats.items():
        for f in REQUIRED_FIELDS:
            if f not in c:
                errs.append(f"cat {cid}: missing field '{f}'")
        if c.get("stage") not in VALID_STAGES:
            errs.append(f"cat {cid}: invalid stage {c.get('stage')!r}")
        if c.get("retry") not in retry_p:
            errs.append(f"cat {cid}: unknown retry profile {c.get('retry')!r}")
        if c.get("quota") not in quota_p:
            errs.append(f"cat {cid}: unknown quota profile {c.get('quota')!r}")
        for t in c.get("chain_to", []):
            if t not in ids:
                errs.append(f"cat {cid}: chain_to references unknown category {t}")
        for t in c.get("dedupe", []):
            if t not in dforms:
                errs.append(f"cat {cid}: dedupe type '{t}' has no canonical form")
    # seed routing must reference real categories
    for st, lst in m.get("seed_routing", {}).items():
        for t in lst:
            if t not in ids:
                errs.append(f"seed_routing[{st}] references unknown category {t}")
    return errs
