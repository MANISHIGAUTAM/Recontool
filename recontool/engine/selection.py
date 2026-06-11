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


def apply_selection(registry: ToolRegistry, mode: str = "default") -> int:
    """Enable the tools allowed by `mode`; disable the rest. Returns the count
    enabled. Non-runnable tools are always disabled (they would only skip)."""
    everything = is_excessive(mode)
    enabled = 0
    for spec in registry.all_tools().values():
        if not plan_execution(spec).runnable:
            spec.enabled = False
            continue
        keep = everything or not spec.is_inventory_derived
        spec.enabled = keep
        enabled += int(keep)
    return enabled
