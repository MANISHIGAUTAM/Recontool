"""Skip-reason taxonomy: a runnable tool that can't execute logs WHY precisely
(which binary / which API key / no endpoint), not a vague 'missing binary/key'."""
from __future__ import annotations

from types import SimpleNamespace

from recontool.engine.runner import _unavailable_reason


def _spec(**kw):
    base = dict(binary=None, requires_key=None, key_optional=False,
                integration="cli", endpoint="")
    base.update(kw)
    return SimpleNamespace(**base)


def test_unavailable_reason_names_the_missing_binary():
    r = _unavailable_reason(_spec(binary="no_such_bin_xyz123", integration="cli"))
    assert r == "missing binary: no_such_bin_xyz123"


def test_unavailable_reason_names_the_missing_key():
    r = _unavailable_reason(_spec(binary=None, requires_key="FAKE_KEY_ENV_XYZ",
                                  integration="api", endpoint="http://x"))
    assert r == "missing API key: FAKE_KEY_ENV_XYZ"


def test_unavailable_reason_flags_missing_endpoint():
    r = _unavailable_reason(_spec(binary=None, requires_key=None,
                                  integration="api", endpoint=""))
    assert r == "no API endpoint contract"
