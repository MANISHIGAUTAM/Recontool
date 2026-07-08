"""Adapter registry — the catalog the orchestrator plans against.

Adapters self-register via the @register decorator. The orchestrator queries the
registry by phase to build each phase's parallel batch.
"""
from __future__ import annotations

from collections import defaultdict

from recontool.adapters.base import Adapter

# Pipeline phases (see docs/D2-recon-flow.md).
PHASES = [
    "p1_seed",          # passive seed discovery
    "p2_expansion",     # passive asset expansion
    "p3_enrichment",    # passive enrichment
    "p4_verify",        # active live verification
    "p5_deep",          # active deep enumeration
    "p6_vuln",          # active vuln surface
]

_REGISTRY: dict[str, list[type[Adapter]]] = defaultdict(list)
_BY_NAME: dict[str, type[Adapter]] = {}


def register(phase: str):
    if phase not in PHASES:
        raise ValueError(f"unknown phase {phase!r}; valid: {PHASES}")

    def deco(cls: type[Adapter]):
        _REGISTRY[phase].append(cls)
        _BY_NAME[cls.name] = cls
        cls.phase = phase  # type: ignore[attr-defined]
        return cls

    return deco


def adapters_for(phase: str) -> list[type[Adapter]]:
    return list(_REGISTRY.get(phase, []))


def all_adapters() -> dict[str, type[Adapter]]:
    return dict(_BY_NAME)


def load_builtin() -> None:
    """Import adapter modules so their @register decorators fire, then register
    the declarative generic adapters (config/tools_generic.yaml)."""
    from recontool.adapters import passive  # noqa: F401
    from recontool.adapters import active    # noqa: F401
    from recontool.adapters import internet_search  # noqa: F401  (Category 1)
    from recontool.adapters import crawler   # noqa: F401  (pure-python web crawler)
    from recontool.adapters import content_discovery  # noqa: F401  (dir brute-force)
    from recontool.adapters import params    # noqa: F401  (param/form extraction)
    from recontool.adapters import org_forest  # noqa: F401  (org-forest fingerprints)
    from recontool.adapters import screenshot  # noqa: F401  (aquatone/eyewitness screenshots)
    from recontool.adapters import file_metadata  # noqa: F401  (exiftool doc/image metadata)
    from recontool.adapters import dns_permute  # noqa: F401  (dnsgen permute + resolve-gate)
    from recontool.adapters.autoload import register_generic

    register_generic()
