"""Auto-register generic adapters from config/tools_generic.yaml.

Every tool in that file becomes a live adapter via build_adapter_class(), unless a
hand-written adapter with the same name already exists (hand-written wins). This is
how the long tail of tools is "implemented" - as declarative specs, not bespoke code.
"""
from __future__ import annotations

from functools import lru_cache

from recontool.config import CONFIG_DIR
from recontool.adapters.generic import build_adapter_class

GENERIC_YAML = CONFIG_DIR / "tools_generic.yaml"
AUTOGEN_YAML = CONFIG_DIR / "tools_autogen.yaml"
REAL_YAML = CONFIG_DIR / "tools_real_endpoints.yaml"


@lru_cache(maxsize=1)
def load_generic_specs() -> list[dict]:
    """Load specs from all YAML tool spec files (real endpoints take priority)."""
    specs: list[dict] = []
    seen_names: set[str] = set()
    # Load real endpoints FIRST (they override autogen placeholders)
    for path in (REAL_YAML, GENERIC_YAML, AUTOGEN_YAML):
        if not path.exists():
            continue
        try:
            import yaml
            data = yaml.safe_load(path.read_text()) or {}
            for spec in data.get("tools", []):
                name = spec.get("name")
                if name and name not in seen_names:
                    specs.append(spec)
                    seen_names.add(name)
        except Exception:  # noqa: BLE001
            continue
    return specs


def register_generic() -> int:
    """Build + register adapter classes for every generic spec not already
    covered by a hand-written adapter. Returns the count registered.

    Specs marked ``enabled: false`` ARE still registered (so their lane is
    represented + auditable + planner-visible), but their adapter reports
    unavailable until enabled in config — so they never run by default."""
    from recontool.adapters.registry import PHASES, all_adapters, register

    existing = set(all_adapters())
    count = 0
    for spec in load_generic_specs():
        name = spec.get("name")
        phase = spec.get("phase")
        if not name or phase not in PHASES or name in existing:
            continue
        cls = build_adapter_class(spec)
        register(phase)(cls)
        existing.add(name)
        count += 1
    return count
