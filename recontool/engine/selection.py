"""Tool-selection profiles — which tools a scan is allowed to run (flag-gated).

  default        — the curated/recommended set only (hand-wired contracts).
                   Correct parsers, predictable output; what runs out of the box.
  all / excessive — every tool the engine can actually execute (curated PLUS
                   inventory tools with a synthesised binary/endpoint). Broad
                   coverage, best-effort parsing, may be noisy — pair with
                   `--noise-control`.

Tools with no programmatic interface (web/manual/reference) are never enabled.
Selection just flips `ToolSpec.enabled`, which the scheduler already honors, so
"everything is wired and ready" — the flag decides what actually fires.
"""
from __future__ import annotations

from recontool.engine.execution import plan_execution
from recontool.engine.registry import ToolRegistry

EXCESSIVE = {"all", "excessive", "everything", "max", "full"}


def is_excessive(mode: str) -> bool:
    return (mode or "default").lower() in EXCESSIVE


def apply_selection(
    registry: ToolRegistry, mode: str = "default", *, authorize_active: bool = False
) -> int:
    """Enable the tools allowed by `mode`; disable the rest. Returns the count
    enabled.

    Gating rules (applied in order):
      * non-runnable tools are always disabled (they would only skip);
      * **active** tools are disabled unless ``authorize_active`` is set — the
        passive→active safety gate (``docs/D6-opsec.md``). The engine is passive
        by default; ``--authorize-active`` unlocks resolve/probe/port/crawl/vuln;
      * in ``default`` mode, inventory-derived stubs are disabled (curated only);
        ``all``/``excessive`` enables every runnable tool.
    """
    everything = is_excessive(mode)
    enabled = 0
    for spec in registry.all_tools().values():
        if not plan_execution(spec).runnable:
            spec.enabled = False
            continue
        if spec.is_active and not authorize_active:
            spec.enabled = False           # passive-by-default safety gate
            continue
        keep = everything or not spec.is_inventory_derived
        spec.enabled = keep
        enabled += int(keep)
    return enabled
