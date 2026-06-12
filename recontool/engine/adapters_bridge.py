"""Bridge the hand-written Python adapters into the event-driven engine.

The engine routes/executes over the :class:`~recontool.engine.registry.ToolRegistry`
and historically could only run *generic* (declarative YAML) adapters via
:func:`recontool.engine.execution.build_adapter_for`. The rich hand-written
adapters in ``recontool/adapters/*.py`` — DNS resolution, HTTP probing, the
pure-Python crawler (``pycrawl``), the connect-scan port fallback (``naabu``),
content discovery (``pydirb``), param mining, JS analysis — were **invisible to
the engine**. A recursive scan therefore died right after passive subdomain
discovery: it had no runnable tool to resolve / probe / crawl a discovered
subdomain locally (the curated/inventory specs for those steps need Go binaries
that are usually not installed).

This module registers a :class:`ToolSpec` for every hand-written adapter (marked
``integration="python"``) so the deterministic router can route to it and tool
selection can enable it, while :mod:`recontool.engine.execution` returns the real
adapter class for it. Hand-written adapters **win on a name collision** (the
canonical contract in ``docs/00-FINAL-ARCHITECTURE.md`` §7): a curated/inventory
spec of the same name is upgraded to the Python implementation, with the correct
``consumes``/``produces`` and active/passive classification.
"""
from __future__ import annotations

from functools import lru_cache

from recontool.engine.registry import ToolRegistry, ToolSpec


def _is_generic(cls: type) -> bool:
    """True if ``cls`` is one of the declarative generic adapters.

    Generic adapters are built from YAML specs (``build_adapter_class``); they are
    *not* hand-written, so the bridge must skip them — the engine already reaches
    them through :func:`recontool.engine.execution.to_generic_spec`.
    """
    from recontool.adapters.generic import GenericApiAdapter, GenericCliAdapter

    return issubclass(cls, (GenericApiAdapter, GenericCliAdapter))


@lru_cache(maxsize=1)
def python_adapter_classes() -> dict[str, type]:
    """Map ``tool name -> hand-written adapter class`` (excludes generic adapters).

    Triggers ``load_builtin()`` so every ``@register`` decorator has fired. The
    result is cached because adapter registration happens once at import time and
    is stable for the life of the process.
    """
    from recontool.adapters.registry import all_adapters, load_builtin

    load_builtin()
    return {
        name: cls
        for name, cls in all_adapters().items()
        if not _is_generic(cls)
    }


def _category_int(cls: type) -> int:
    """Coerce an adapter's ``CAT-N`` (or int) category into a ToolSpec int."""
    raw = getattr(cls, "category", "") or ""
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and "-" in raw:
        tail = raw.split("-", 1)[1].strip()
        if tail.isdigit():
            return int(tail)
    return 0


def _spec_for(cls: type) -> dict:
    """Build a ToolSpec field dict for a hand-written adapter class."""
    consumes = list(getattr(cls, "consumes", ()) or ())
    produces = list(getattr(cls, "produces", ()) or ())
    is_active = bool(getattr(cls, "is_active", False))
    key_env = getattr(cls, "key_env", None)
    return {
        "name": cls.name,
        "category": _category_int(cls),
        "integration": "python",
        "is_active": is_active,
        "type": "active" if is_active else "passive",
        "consumes": consumes,
        "produces": produces,
        "supported_input_types": consumes,
        "output_types": produces,
        "source": "curated",
        "enabled": True,
        "default_on": True,
        "requires_key": key_env,
        # key_optional: a keyed adapter still runs (keyless/limited) — the adapter's
        # own available()/run() decide. Mark optional so selection never hard-drops it.
        "key_optional": bool(key_env),
        "notes": "hand-written python adapter",
    }


def register_python_adapters(registry: ToolRegistry) -> int:
    """Inject/upgrade ToolSpecs for every hand-written adapter into ``registry``.

    Hand-written adapters win on name collision: an existing spec of the same
    name is replaced by the Python-backed spec so it becomes runnable with the
    real implementation and the correct entity contract. Returns the number of
    adapters bridged. The registry is re-indexed so routing reflects the change.
    """
    classes = python_adapter_classes()
    if not classes:
        return 0
    specs: list[ToolSpec] = []
    existing = registry.all_tools()
    for name, cls in classes.items():
        data = _spec_for(cls)
        prior = existing.get(name)
        if prior is not None and prior.slug:
            data["slug"] = prior.slug  # keep canonical slug stable for dedupe/matrix
        specs.append(ToolSpec(**data))
    registry.upsert_many(specs)
    return len(specs)
