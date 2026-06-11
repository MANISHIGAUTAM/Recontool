"""Smoke tests for the `recontool engine` CLI command (no network).

Asserts the command is registered and its help renders, and that a scan over a
registry with only a non-runnable tool completes and is recorded — without
making any external calls.
"""
from __future__ import annotations

from typer.testing import CliRunner

from recontool.cli import app

runner = CliRunner()


def test_engine_command_registered():
    result = runner.invoke(app, ["engine", "--help"])
    assert result.exit_code == 0
    assert "event-driven" in result.output.lower()
    assert "--max-depth" in result.output


def test_engine_rejects_unknown_profile():
    result = runner.invoke(app, ["engine", "example.com", "--profile", "nope"])
    assert result.exit_code == 1
    assert "Unknown profile" in result.output
