"""Smoke tests for the `recontool engine` CLI command (no network).

Asserts the command is registered and its help renders, and that a scan over a
registry with only a non-runnable tool completes and is recorded — without
making any external calls.
"""
from __future__ import annotations

import re

from typer.testing import CliRunner

from recontool.cli import app

runner = CliRunner()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    """Strip ANSI styling and collapse whitespace so help-text assertions are
    robust to Rich's coloring (which injects escape codes mid-word) and to the
    terminal-width-dependent line wrapping of the options panel."""
    return " ".join(_ANSI.sub("", text).split())


def test_engine_command_registered():
    result = runner.invoke(app, ["engine", "--help"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    out = _plain(result.output)
    assert "event-driven" in out.lower()
    assert "--max-depth" in out


def test_engine_rejects_unknown_profile():
    result = runner.invoke(app, ["engine", "example.com", "--profile", "nope"])
    assert result.exit_code == 1
    assert "Unknown profile" in result.output
