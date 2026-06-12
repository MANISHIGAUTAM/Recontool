"""Atomic tests for the engine<->adapter bridge (the recursion-depth fix).

These guard the regression where the event-driven engine could only run generic
(YAML) adapters, so the pure-Python tools needed to resolve/probe/crawl a
discovered subdomain (dns_resolve, httpx_probe, pycrawl, naabu fallback) never
ran and recursion died after passive subdomain discovery. No network/subprocess.
"""
from __future__ import annotations

from recontool.engine.adapters_bridge import (
    python_adapter_classes,
    register_python_adapters,
)
from recontool.engine.execution import build_adapter_for, plan_execution
from recontool.engine.registry import ToolRegistry
from recontool.engine.selection import apply_selection

# The pure-Python chain that makes deep recursion work without any Go binary.
_CORE = ("crtsh", "dns_resolve", "httpx_probe", "pycrawl", "naabu")


def test_bridge_registers_handwritten_adapters_as_python_specs():
    reg = ToolRegistry(tools={})
    n = register_python_adapters(reg)
    assert n >= 10  # crtsh, dns_resolve, httpx_probe, pycrawl, naabu, wayback, ...
    for name in _CORE:
        spec = reg.get(name)
        assert spec is not None, f"{name} not bridged into the registry"
        assert spec.integration == "python"
        assert plan_execution(spec).runnable, f"{name} should be runnable"


def test_bridged_tools_are_routable_by_input_type():
    """A discovered subdomain must reach the tools that consume it (recursion)."""
    reg = ToolRegistry(tools={})
    register_python_adapters(reg)
    consumers = {s.name for s in reg.by_input_type("subdomain")}
    assert {"dns_resolve", "httpx_probe", "pycrawl"} <= consumers


def test_handwritten_adapters_win_on_name_collision():
    from recontool.adapters.active import DnsResolve, HttpProbe
    from recontool.adapters.crawler import PyCrawler
    from recontool.adapters.passive import CrtSh

    reg = ToolRegistry(tools={})
    register_python_adapters(reg)
    assert build_adapter_for(reg.get("crtsh")) is CrtSh
    assert build_adapter_for(reg.get("dns_resolve")) is DnsResolve
    assert build_adapter_for(reg.get("httpx_probe")) is HttpProbe
    assert build_adapter_for(reg.get("pycrawl")) is PyCrawler


def test_active_tools_are_gated_behind_authorization():
    reg = ToolRegistry(tools={})
    register_python_adapters(reg)

    apply_selection(reg, "default", authorize_active=False)
    assert reg.get("crtsh").enabled is True          # passive always available
    assert reg.get("dns_resolve").enabled is False   # active gated off by default
    assert reg.get("pycrawl").enabled is False

    apply_selection(reg, "default", authorize_active=True)
    assert reg.get("dns_resolve").enabled is True    # unlocked with authorization
    assert reg.get("pycrawl").enabled is True


def test_python_adapter_classes_excludes_generic():
    """Only hand-written adapters are bridged; generic YAML adapters are not."""
    from recontool.adapters.generic import GenericApiAdapter, GenericCliAdapter

    for cls in python_adapter_classes().values():
        assert not issubclass(cls, (GenericApiAdapter, GenericCliAdapter))


def test_url_tools_get_default_firehose_cap():
    """URL-producing generic tools are capped (bounds the historical-URL firehose);
    an explicit max_records wins; non-URL tools get no default cap."""
    from recontool.engine.execution import to_generic_spec
    from recontool.engine.registry import ToolSpec

    url_tool = ToolSpec(name="gau_x", integration="cli", binary="gau",
                        consumes=["domain"], produces=["url"])
    assert to_generic_spec(url_tool)["max_records"] == 5000

    explicit = ToolSpec(name="gau_y", integration="cli", binary="gau",
                        consumes=["domain"], produces=["url"], max_records=100)
    assert to_generic_spec(explicit)["max_records"] == 100

    sub_tool = ToolSpec(name="sub_z", integration="cli", binary="z",
                        consumes=["domain"], produces=["subdomain"])
    assert to_generic_spec(sub_tool)["max_records"] is None
