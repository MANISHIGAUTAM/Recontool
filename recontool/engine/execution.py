"""Route registry tools to the generic adapter mechanism.

The engine never hand-writes a Python class per tool. Instead every executable
``ToolSpec`` is turned into the same declarative spec shape that
``config/tools_generic.yaml`` uses, and run by the generic API/CLI executors in
``recontool.adapters.generic``. This is the single bridge between the registry
(the catalogue of *all* 500+ tools) and the runtime (the thin generic adapters).

Three outcomes for any tool (see ``plan_execution``):

* ``api``  — an HTTP-backed tool with an endpoint contract -> GenericApiAdapter.
* ``cli``  — a binary-backed tool (curated invocation, or a synthesised
  ``"{binary} {value}"`` template for inventory stubs) -> GenericCliAdapter.
* ``none`` — non-executable (web/gui/dataset-only, reference index, preset) or an
  API stub with no endpoint contract: ``runnable=False`` with a clear ``reason``.

Pure module: builds specs and classes, performs no network/subprocess itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from recontool.engine.registry import ToolSpec

# Default text-parse used for inventory CLI stubs: one value per stdout line,
# emitted as the tool's primary produced asset type (scope-filtered for hosts).
_HOST_TYPES = {"subdomain", "domain", "live_host"}


@dataclass
class ExecutionPlan:
    """How (and whether) a tool can be executed by the engine."""

    tool_name: str
    mode: str                       # "api" | "cli" | "none"
    runnable: bool
    reason: str = ""
    generic_spec: Optional[dict[str, Any]] = None
    synthesized: bool = False       # True if the invocation/parse was inferred


def _default_parse(produces: list[str]) -> dict[str, Any]:
    """A conservative line-oriented text parse for synthesised CLI stubs."""
    primary = produces[0] if produces else "subdomain"
    if primary in _HOST_TYPES:
        emit = [{"entity": "asset", "value": "{_value}", "type": primary,
                 "scope_filter": "subdomain"}]
    elif primary in ("url", "endpoint"):
        emit = [{"entity": "endpoint", "url": "{_value}"}]
    else:
        emit = [{"entity": "asset", "value": "{_value}", "type": primary}]
    return {"format": "text", "emit": emit}


def to_generic_spec(tool_spec: ToolSpec) -> Optional[dict[str, Any]]:
    """Build a generic-adapter spec dict for a tool, or None if not runnable."""
    if tool_spec.non_executable:
        return None

    consumes = list(tool_spec.consumes or tool_spec.supported_input_types)
    produces = list(tool_spec.produces or tool_spec.output_types)
    base: dict[str, Any] = {
        "name": tool_spec.name,
        "phase": tool_spec.phase,
        "category": tool_spec.category,
        "is_active": tool_spec.is_active,
        "consumes": consumes or ["domain"],
        "produces": produces,
        "requires_key": tool_spec.requires_key,
        "key_optional": tool_spec.key_optional,
        "timeout": tool_spec.timeout,
    }

    if tool_spec.integration == "api":
        if not tool_spec.endpoint:
            return None  # inventory API stub: no endpoint contract to call
        base.update({
            "integration": "api",
            "endpoint": tool_spec.endpoint,
            "headers": tool_spec.headers or {},
            "bucket": tool_spec.bucket or tool_spec.name,
            "max_inputs": tool_spec.max_inputs,
            "parse": tool_spec.parse or _default_parse(produces),
        })
        return base

    if tool_spec.integration == "cli":
        binary = tool_spec.binary
        if not binary and not tool_spec.invocation:
            return None
        invocation = tool_spec.invocation or f"{binary} {{value}}"
        base.update({
            "integration": "cli",
            "binary": binary or invocation.split()[0],
            "invocation": invocation,
            "max_inputs": tool_spec.max_inputs,
            "parse": tool_spec.parse or _default_parse(produces),
            "stdin": tool_spec.stdin,
        })
        return base

    return None


def plan_execution(tool_spec: ToolSpec) -> ExecutionPlan:
    """Decide how a tool runs and surface a clear reason when it cannot."""
    if tool_spec.non_executable:
        return ExecutionPlan(
            tool_name=tool_spec.name,
            mode="none",
            runnable=False,
            reason=tool_spec.non_executable_reason
            or "non_executable: no programmatic interface",
        )

    # Hand-written Python adapters (bridged via engine.adapters_bridge) carry
    # integration="python". They are always runnable — the adapter's own
    # available()/run() decide at runtime (e.g. a missing binary => clean skip).
    if tool_spec.integration == "python":
        return ExecutionPlan(
            tool_name=tool_spec.name,
            mode="python",
            runnable=True,
        )

    spec = to_generic_spec(tool_spec)
    if spec is None:
        # Only API stubs without an endpoint reach here.
        return ExecutionPlan(
            tool_name=tool_spec.name,
            mode=tool_spec.integration or "none",
            runnable=False,
            reason=(
                f"inventory_stub: '{tool_spec.slug or tool_spec.name}' has no API "
                "endpoint contract; promote to a generic adapter spec to execute"
            ),
        )

    synthesized = bool(
        tool_spec.is_inventory_derived
        and (not tool_spec.invocation and not tool_spec.endpoint)
    )
    return ExecutionPlan(
        tool_name=tool_spec.name,
        mode=spec["integration"],
        runnable=True,
        generic_spec=spec,
        synthesized=synthesized,
    )


def _handwritten_adapter(name: str):
    """Return the hand-written (non-generic) adapter class for ``name``, or None.

    Hand-written adapters always win on a name collision (canonical contract),
    and this is also how the engine reaches the pure-Python tools (dns_resolve,
    httpx_probe, pycrawl, naabu fallback, …) that have no generic spec.
    """
    if not name:
        return None
    try:
        from recontool.engine.adapters_bridge import python_adapter_classes

        return python_adapter_classes().get(name)
    except Exception:  # noqa: BLE001 — never let bridging break execution
        return None


def build_adapter_for(tool_spec: ToolSpec):
    """Return a ready-to-run Adapter subclass for a tool, or None.

    Precedence: a hand-written Python adapter of the same name wins; otherwise
    the declarative ``recontool.adapters.generic.build_adapter_class`` powers the
    curated/inventory-derived tools.
    """
    hand = _handwritten_adapter(tool_spec.name)
    if hand is not None:
        return hand

    spec = to_generic_spec(tool_spec)
    if spec is None:
        return None
    from recontool.adapters.generic import build_adapter_class

    return build_adapter_class(spec)
