"""Flow-graph reachability analysis over the LIVE tool registry.

The engine routes via ``ToolRegistry`` (``engine/registry.py``): ``RouteIndex`` keys
each schedulable tool by the types it consumes, and a discovered entity is re-fed to
every tool consuming its type. A route is therefore only *real* when some schedulable
tool **produces** a type that a downstream tool **consumes**. This module builds that
producer/consumer graph from the live registry — the same source the engine routes on,
NOT the ``flow_plan.json``/``tool_row`` planning view — and reports three invariant
violations:

  * ``non_canonical`` — a consumed/produced type outside the canonical vocabulary
    (``config/categories.yaml`` ``meta.dedupe_forms``). It cannot dedupe or chain cleanly.
  * ``dead_weight``  — a type consumed by a schedulable tool that NO schedulable tool
    produces and that is not an external seed. Those tools can never fire (the manual:
    "a tool with no reachable input is not useful").
  * ``dead_end``     — a type produced by a schedulable tool that NO tool consumes and
    that is not a terminal/evidence type. The recursion stops there.

Used by ``scripts/flow_lint.py`` and ``tests/atomic/test_flow_reachability.py``.
Pure: no network, no DB, no subprocess.
"""
from __future__ import annotations

import collections

import yaml

from recontool.config import REPO_ROOT
from recontool.engine.registry import ToolRegistry

_CATEGORIES_YAML = REPO_ROOT / "config" / "categories.yaml"

# Types that legitimately terminate a chain (evidence / intel / reports). A producer
# of one of these is NOT a dead-end even though nothing consumes it.
#
# endpoint/param/tech/cert are RECURSION-terminal by design (M6): they are recorded
# evidence that feeds reports + bounded analysis (nuclei runs on the validated
# live_host+url set), but they are deliberately NOT re-fed as new keys. Re-feeding the
# gau/katana endpoint firehose (100k+ URLs) would explode the scan — "endpoints should
# not go for rescan / don't scan everything". The no-rescan invariant is pinned in
# tests/atomic/test_flow_reachability.py.
TERMINAL_TYPES = {
    "finding", "screenshot", "ioc", "report", "tag", "secret", "onion",
    "endpoint", "param", "tech", "cert",
    # dns_record (F1): recorded MX/TXT/CAA intelligence — feeds reports + OSINT/forest +
    # future SaaS/NS-takeover & mail-posture analyzers; not re-fed as a recursion key.
    "dns_record",
}

# Sentinel input markers for seed/entrypoint tools (no real upstream entity).
SENTINEL_TYPES = {"none", "any", "seed"}

# Overlay categories (geo, social, favicon pivot) ship OFF by default, so a consumed
# type with no producer there is a known/accepted gap, not an in-scope routing break.
# Kept separate so the in-scope guard tracks the routes we actually run.
OVERLAY_TYPES = {"coords", "bssid", "handle", "analytics_id", "favicon"}

# Deferred types: REAL gaps whose wiring is a follow-on batch, not core flow.
#  - file-analysis (document/binary/apk): exiftool/binwalk/metagoofil are unwired
#    inventory stubs. The type-gating is already correct-by-design — binwalk consumes
#    `binary`, exiftool `document` — so they only fire when that artifact type is
#    produced ("binwalk only on a binary"); wiring the producers is coverage work.
#  - enrichment (cpe/cve/hash/keyword): real consumers (nvd/vulners/threat-intel,
#    code search) exist, but the producers (service->cpe derivation, org->keyword)
#    are an enrichment pipeline, not the core recon flow. Tracked, not silenced.
DEFERRED_TYPES = {"document", "binary", "apk", "cpe", "cve", "hash", "keyword"}


def _meta() -> dict:
    try:
        return yaml.safe_load(_CATEGORIES_YAML.read_text()).get("meta", {}) or {}
    except Exception:  # noqa: BLE001 - a broken yaml must not crash the lint import
        return {}


def canonical_types() -> set[str]:
    """The canonical entity vocabulary = categories.yaml meta.dedupe_forms keys."""
    return set(_meta().get("dedupe_forms", {})) | {"seed", "any", "none"}


def seed_types() -> set[str]:
    """Types that enter externally (a scan seed), so having no producer is fine."""
    return set(_meta().get("seed_routing", {}))


def _schedulable(spec) -> bool:
    """A tool the engine could actually enqueue: executable + not gated off."""
    if getattr(spec, "non_executable", False):
        return False
    return bool(getattr(spec, "enabled", True))


def _consumes(spec) -> set[str]:
    return set(spec.supported_input_types or []) | set(spec.consumes or [])


def _produces(spec) -> set[str]:
    return set(spec.output_types or []) | set(spec.produces or [])


def build_graph(registry: ToolRegistry | None = None, *, schedulable_only: bool = True):
    """Return (producers, consumers): type -> sorted list of tool names."""
    reg = registry or ToolRegistry.load(include_inventory=True)
    prod: dict[str, set[str]] = collections.defaultdict(set)
    cons: dict[str, set[str]] = collections.defaultdict(set)
    for name, spec in reg.all_tools().items():
        if schedulable_only and not _schedulable(spec):
            continue
        for t in _produces(spec):
            prod[t].add(name)
        for t in _consumes(spec):
            cons[t].add(name)
    return prod, cons


def analyze(registry: ToolRegistry | None = None, *, schedulable_only: bool = True) -> dict:
    """Compute the reachability report over the live registry."""
    prod, cons = build_graph(registry, schedulable_only=schedulable_only)
    canon = canonical_types()
    seeds = seed_types()
    types = set(prod) | set(cons)
    non_canonical = sorted(t for t in types if t not in canon)
    not_a_seed = seeds | SENTINEL_TYPES
    dead_weight = sorted(t for t in cons if not prod.get(t) and t not in not_a_seed)
    dead_end = sorted(t for t in prod if not cons.get(t) and t not in TERMINAL_TYPES)
    # In-scope = the core recon flow: excludes off-by-default overlay categories and
    # the deferred (file-analysis / enrichment) follow-on types. This is what the guard
    # must drive to zero; OVERLAY/DEFERRED are reported separately, never silenced.
    _aside = OVERLAY_TYPES | DEFERRED_TYPES
    dead_weight_in_scope = [t for t in dead_weight if t not in _aside]
    dead_end_in_scope = [t for t in dead_end if t not in _aside]
    return {
        "producers": {k: sorted(v) for k, v in prod.items()},
        "consumers": {k: sorted(v) for k, v in cons.items()},
        "non_canonical": non_canonical,
        "dead_weight": dead_weight,
        "dead_end": dead_end,
        "dead_weight_in_scope": dead_weight_in_scope,
        "dead_end_in_scope": dead_end_in_scope,
    }
