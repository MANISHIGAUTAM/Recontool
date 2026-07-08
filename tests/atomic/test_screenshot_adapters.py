"""Pure unit tests for the hand-written screenshot adapters (aquatone +
EyeWitness). No subprocess, no network, no real binaries.

Mirrors the gowitness contract: both adapters are active, off by default,
consume ``live_host`` and produce ``screenshot``, and their ``available()``
gate is driven entirely by ``shutil.which`` (False in CI, where neither binary
is installed).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from recontool.adapters import screenshot
from recontool.adapters.screenshot import Aquatone, EyeWitness

ADAPTERS = [Aquatone, EyeWitness]
WHICH = {Aquatone: "aquatone", EyeWitness: "eyewitness"}


@pytest.fixture
def ctx():
    """A minimal context object — available() never dereferences it."""
    return SimpleNamespace()


@pytest.mark.parametrize("cls", ADAPTERS)
def test_class_attributes(cls):
    a = cls()
    assert a.name == WHICH[cls]
    assert a.is_active is True
    assert a.default_on is False
    assert a.consumes == ("live_host",)
    assert a.produces == ("screenshot",)


@pytest.mark.parametrize("cls", ADAPTERS)
def test_distinct_names(cls):
    # The two adapters must not collide on name.
    assert Aquatone.name != EyeWitness.name


@pytest.mark.parametrize("cls", ADAPTERS)
def test_available_false_when_binary_absent(cls, ctx, monkeypatch):
    # In CI neither binary is installed -> which() returns None -> available False.
    monkeypatch.setattr(screenshot.shutil, "which", lambda _name: None)
    assert cls().available(ctx) is False


@pytest.mark.parametrize("cls", ADAPTERS)
def test_available_true_when_binary_present(cls, ctx, monkeypatch):
    # When which() finds the binary, the adapter reports available.
    monkeypatch.setattr(screenshot.shutil, "which", lambda _name: f"/usr/bin/{_name}")
    assert cls().available(ctx) is True


@pytest.mark.parametrize("cls", ADAPTERS)
def test_available_queries_correct_binary(cls, ctx, monkeypatch):
    # available() must look up *its own* binary name, not a hard-coded one.
    seen: list[str] = []

    def fake_which(name: str):
        seen.append(name)
        return None

    monkeypatch.setattr(screenshot.shutil, "which", fake_which)
    cls().available(ctx)
    assert seen == [WHICH[cls]]
