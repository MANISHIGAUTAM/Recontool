"""Tool-selection profiles — which tools a scan is allowed to run (flag-gated).

  default    — the curated/recommended set only (hand-wired contracts).
               Correct parsers, predictable output; what runs out of the box.
  all        — every GROUNDED tool: curated contracts PLUS inventory tools that
               carry a real invocation/endpoint contract. EXCLUDES *synthesized*
               tools (inventory rows with no contract, where the engine would
               guess a `<binary> {value}` invocation + a default parser). Broad
               but every tool actually knows how to run + parse. Pair with
               `--noise-control`.
  excessive  — also enables the synthesized/guessed tools (kitchen sink: runs an
               inferred `<binary> {value}` for every inventory binary, even file
               analyzers fed a domain string). Noisy, best-effort, mostly 0-yield;
               opt in only when you knowingly want guessed invocations.

WHY `all` excludes synthesized (the overscanning fix): a synthesized plan INVENTS
both the invocation and the output parser. Under the old `all == excessive`, that
ran `binwalk <domain>`, `strings <domain>`, `arjun <domain>`, `trufflehog <domain>`
— file/repo analyzers fed a domain string — burning the majority of scan time for
zero output, while every real producer was a contract. Gating synthesized out of
`all` removes that waste and loses no data, and honors "never invent invocation/
output" — guessed runs are now `excessive`-only.

Tools with no programmatic interface (web/manual/reference) are never enabled.
Selection just flips `ToolSpec.enabled`, which the scheduler already honors.
"""
from __future__ import annotations

from recontool.engine.execution import plan_execution
from recontool.engine.registry import ToolRegistry

# Modes that also enable SYNTHESIZED (guessed-invocation) inventory tools.
EXCESSIVE = {"excessive", "everything", "max", "full"}
# Modes that enable every GROUNDED tool (contracts only; synthesized excluded).
ALL_GROUNDED = {"all"}


def is_excessive(mode: str) -> bool:
    """True only for the kitchen-sink modes that include synthesized/guessed tools."""
    return (mode or "default").lower() in EXCESSIVE


def is_all(mode: str) -> bool:
    """True for `all` (every grounded contract) or any excessive mode."""
    m = (mode or "default").lower()
    return m in ALL_GROUNDED or m in EXCESSIVE


def apply_selection(
    registry: ToolRegistry, mode: str = "default", *, authorize_active: bool = False
) -> int:
    """Enable the tools allowed by `mode`; disable the rest. Returns the count
    enabled.

    Gating rules (applied in order):
      * non-runnable tools are always disabled (they would only skip);
      * **active** tools are disabled unless ``authorize_active`` is set — the
        passive→active safety gate (``docs/D6-opsec.md``);
      * ``default`` → curated only (inventory-derived stubs disabled);
        ``all`` → every GROUNDED tool (synthesized/guessed excluded — the
        overscanning fix); ``excessive`` → also the synthesized tools.
    """
    excessive = is_excessive(mode)
    grounded_all = (mode or "default").lower() in ALL_GROUNDED
    enabled = 0
    for spec in registry.all_tools().values():
        plan = plan_execution(spec)
        if not plan.runnable:
            spec.enabled = False
            continue
        if spec.is_active and not authorize_active:
            spec.enabled = False           # passive-by-default safety gate
            continue
        if excessive:
            keep = True                              # kitchen sink incl. synthesized
        elif grounded_all:
            keep = not plan.synthesized              # `all`: grounded contracts only
        else:
            keep = not spec.is_inventory_derived     # `default`: curated only
        spec.enabled = keep
        enabled += int(keep)
    return enabled
