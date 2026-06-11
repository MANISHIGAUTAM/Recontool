"""End-to-end test that the event-driven engine actually runs tools and recurses.

Uses `echo` as a hermetic stand-in tool (no network, no real binary install) to
prove the full loop: seed domain -> a domain-consuming tool runs and emits a
subdomain -> a subdomain-consuming tool is scheduled and runs on it -> converge.
This is the proof that `runner.make_execute_fn` closes the recursion (spec G1).
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from recontool.config import settings
from recontool.core import db
from recontool.core.models import Asset
from recontool.engine.registry import ToolRegistry, ToolSpec
from recontool.engine.runner import run_engine_scan


def _echo_tool(name: str, consumes: list[str], produces: list[str], emit_value: str) -> ToolSpec:
    """A 'tool' that just echoes a fixed hostname, parsed as a produced asset."""
    return ToolSpec(
        name=name, integration="cli", binary="echo",
        invocation=f"echo {emit_value}",
        consumes=consumes, supported_input_types=consumes,
        produces=produces, output_types=produces,
        category=2, is_active=False, enabled=True, non_executable=False,
        parse={
            "format": "text",
            "emit": [{"entity": "asset", "value": "{_value}",
                      "type": produces[0], "scope_filter": "subdomain"}],
        },
    )


@pytest.mark.asyncio
async def test_engine_runs_and_recurses(tmp_path, monkeypatch):
    db.init_engine(f"sqlite:///{tmp_path / 'engine.db'}")
    db.create_all()
    monkeypatch.setattr(settings, "artifact_dir", tmp_path / "artifacts")

    registry = ToolRegistry(tools={
        "sub_echo": _echo_tool("sub_echo", ["domain"], ["subdomain"], "api.example.com"),
        "deep_echo": _echo_tool("deep_echo", ["subdomain"], ["subdomain"], "deep.api.example.com"),
    })

    result = await run_engine_scan(
        "example.com", registry=registry, max_iterations=20,
    )

    # The domain tool AND the subdomain tool both executed (recursion happened).
    assert result.total_tools_run >= 2
    assert result.total_entities >= 1
    assert result.status in ("completed", "completed_with_errors")

    # Discoveries were persisted via the Normalizer (idempotent dedupe).
    with db.session_scope() as s:
        values = {a.value for a in s.execute(select(Asset)).scalars()}
    assert "api.example.com" in values            # domain -> subdomain
    assert "deep.api.example.com" in values       # subdomain -> deeper subdomain (recursion)


@pytest.mark.asyncio
async def test_engine_skips_nonrunnable_tools_cleanly(tmp_path, monkeypatch):
    """A web-only / no-contract tool must not crash the scan — it's skipped."""
    db.init_engine(f"sqlite:///{tmp_path / 'engine2.db'}")
    db.create_all()
    monkeypatch.setattr(settings, "artifact_dir", tmp_path / "artifacts")

    web_only = ToolSpec(
        name="manual_portal", integration="api", category=1,
        consumes=["domain"], supported_input_types=["domain"],
        produces=["finding"], non_executable=True,
        non_executable_reason="web/gui only",
    )
    registry = ToolRegistry(tools={"manual_portal": web_only})

    result = await run_engine_scan(
        "example.com", registry=registry, max_iterations=5,
    )
    # scan completes without error even though the only tool is non-runnable
    assert result.status in ("completed", "completed_with_errors")
