"""Routing prunes unavailable tools so they are never enqueued (avoids the
claim-then-skip churn that dominated --tools all scans)."""
from __future__ import annotations

from recontool.engine.worker import RouteIndex, _tool_available


class _Spec:
    def __init__(self, name, integration="cli", binary=None, requires_key=None,
                 key_optional=False):
        self.name = name; self.integration = integration; self.binary = binary
        self.requires_key = requires_key; self.key_optional = key_optional


def test_tool_available_rules():
    assert _tool_available(_Spec("real", binary="sh")) is True          # sh exists
    assert _tool_available(_Spec("ghost", binary="definitely-not-installed-xyz")) is False
    assert _tool_available(_Spec("py", integration="python", binary=None)) is True
    assert _tool_available(_Spec("keyed", integration="api", requires_key="X")) is False
    assert _tool_available(_Spec("keyless", integration="api")) is True
    assert _tool_available(_Spec("opt", integration="api", requires_key="X", key_optional=True)) is True


class _Reg:
    def __init__(self, specs):
        self._s = {s.name: s for s in specs}
    def all_tools(self):
        return self._s


def test_routeindex_prunes_unavailable():
    specs = [
        _type_spec("good", "sh", ["subdomain"]),
        _type_spec("ghost", "definitely-not-installed-xyz", ["subdomain"]),
    ]
    ri = RouteIndex(_Reg(specs))
    routed = {s.name for s in ri.for_key_type("subdomain")}
    assert "good" in routed
    assert "ghost" not in routed
    assert "ghost" in ri.pruned_unavailable


def _type_spec(name, binary, consumes):
    s = _Spec(name, binary=binary)
    s.enabled = True
    s.supported_input_types = consumes
    s.consumes = consumes
    return s
