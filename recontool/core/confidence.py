"""Confidence scoring via noisy-OR combination of independent sources.

confidence = 1 - Π(1 - source_confidence_i)

More independent corroboration -> higher confidence, with diminishing returns.
Per-tool trust weights live here. See docs/D3-data-schema.md §4.
"""
from __future__ import annotations

from collections.abc import Iterable

# Per-tool trust weights. Authoritative sources (CT logs, live verification)
# score high; scraping/heuristic sources score lower.
SOURCE_WEIGHTS: dict[str, float] = {
    # passive subdomain / DNS
    "crtsh": 0.90,            # certificate transparency = authoritative
    "certspotter": 0.90,
    "securitytrails": 0.80,
    "virustotal": 0.75,
    "chaos": 0.70,
    "hackertarget": 0.55,
    "subfinder": 0.65,        # aggregator (its own sources vary)
    "amass": 0.70,
    "wayback": 0.50,
    "alienvault_otx": 0.55,
    # network intel
    "bgpview": 0.85,
    "ripestat": 0.85,
    "asnmap": 0.80,
    "ipinfo": 0.80,
    "shodan": 0.80,
    "censys": 0.80,
    # active verification — near-certain corroboration
    "dns_resolve": 0.95,
    "httpx": 0.95,
    "httpx_probe": 0.95,
    "naabu": 0.90,
    "nmap": 0.92,
    # default
    "_default": 0.50,
}


def source_weight(tool: str) -> float:
    return SOURCE_WEIGHTS.get(tool, SOURCE_WEIGHTS["_default"])


def combine(weights: Iterable[float]) -> float:
    """Noisy-OR over a set of independent source weights -> [0,1]."""
    product = 1.0
    any_source = False
    for w in weights:
        any_source = True
        w = min(max(w, 0.0), 0.999)  # clamp; never let one source assert certainty
        product *= (1.0 - w)
    if not any_source:
        return 0.0
    return round(1.0 - product, 4)


def confidence_from_tools(tools: Iterable[str]) -> float:
    return combine(source_weight(t) for t in set(tools))
