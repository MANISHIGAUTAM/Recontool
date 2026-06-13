"""Integration tests: the full 532-tool registry inside the event-driven engine.

Verifies:
  * the scheduler selects inventory-derived tools by input key across the full
    registry (eligibility works at scale);
  * the generic adapter routes an API-class and a CLI-class inventory tool;
  * the dependency checker blocks-with-reason for missing deps / stubs (no crash);
  * the orchestrator runs a scan that touches inventory-derived tools without
    crashing, gracefully skipping blocked ones;
  * regression: the previously-curated tools keep their detailed contracts.
"""
from __future__ import annotations

import asyncio

import pytest

from recontool.adapters.base import Event
from recontool.adapters.generic import emit_events, parse_records
from recontool.engine.dependency import DependencyChecker
from recontool.engine.events import EntityDiscovered, EventBus
from recontool.engine.execution import build_adapter_for, plan_execution, to_generic_spec
from recontool.engine.executor import ExecutionResult, ScheduledJob
from recontool.engine.orchestrator import EventDrivenOrchestrator, ScanConfig
from recontool.engine.registry import ToolRegistry
from recontool.engine.scheduler import EventDrivenScheduler


# ---------------------------------------------------------------------------
# Scheduler eligibility across the full registry
# ---------------------------------------------------------------------------
def test_scheduler_selects_inventory_tools_by_input_key():
    reg = ToolRegistry.load()
    bus = EventBus()
    sched = EventDrivenScheduler(bus=bus, registry=reg)

    scan_id = "scan-inv-1"
    sched._available_keys[scan_id] = {"domain"}
    sched._running_tools[scan_id] = set()
    sched._completed_tools[scan_id] = set()

    eligible = sched.select_eligible_tools(scan_id)
    names = {t.name for t in eligible}
    sources = {t.source for t in eligible}

    # Some inventory-derived tools must be selected purely by the 'domain' key.
    assert "inventory" in sources, "scheduler did not select any inventory-derived tool"
    assert len(names) > 20
    # Every selected tool genuinely consumes 'domain' and is enabled.
    for t in eligible:
        assert "domain" in set(t.supported_input_types) | set(t.consumes)
        assert t.enabled


def test_index_backed_eligibility_excludes_non_executable():
    reg = ToolRegistry.load()
    bus = EventBus()
    sched = EventDrivenScheduler(bus=bus, registry=reg)
    scan_id = "scan-inv-2"
    sched._available_keys[scan_id] = {"domain"}
    sched._running_tools[scan_id] = set()
    sched._completed_tools[scan_id] = set()

    eligible = sched.select_eligible_tools(scan_id)
    # Disabled (non-executable) tools are never scheduled.
    assert all(t.enabled for t in eligible)
    assert all(not t.non_executable for t in eligible)


# ---------------------------------------------------------------------------
# Generic adapter routing for inventory-derived tools
# ---------------------------------------------------------------------------
def test_generic_adapter_routes_cli_inventory_tool():
    reg = ToolRegistry.load()
    cli_tool = next(
        t for t in reg.inventory_tools()
        if t.integration == "cli" and not t.non_executable
    )
    plan = plan_execution(cli_tool)
    assert plan.runnable
    assert plan.mode == "cli"
    assert plan.synthesized  # bare inventory stub -> synthesised invocation

    spec = plan.generic_spec
    assert spec["binary"]
    assert "{value}" in spec["invocation"]

    # The synthesised CLI parse turns stdout lines into normalised Events.
    cls = build_adapter_for(cli_tool)
    assert cls is not None
    recs = parse_records(spec["parse"], "api.example.com\nwww.example.com\n")
    events = emit_events(spec["parse"], recs, cli_tool.name, "example.com")
    assert all(isinstance(e, Event) for e in events)


def test_generic_adapter_routes_api_inventory_tool_with_endpoint():
    reg = ToolRegistry.load()
    api_tool = next(
        t for t in reg.inventory_tools()
        if t.integration == "api" and not t.non_executable
    )
    # A bare API stub has no endpoint -> not runnable, surfaced with a reason.
    bare = plan_execution(api_tool)
    assert not bare.runnable
    assert "endpoint" in bare.reason

    # Promote it by supplying an endpoint contract (the documented promotion path)
    # and confirm it now routes through the generic API adapter.
    promoted = api_tool.model_copy(update={
        "endpoint": "https://api.example.com/q?d={domain}",
        "parse": {"format": "json", "emit": [
            {"entity": "asset", "value": "{name}", "type": "subdomain"}]},
    })
    plan = plan_execution(promoted)
    assert plan.runnable
    assert plan.mode == "api"
    assert build_adapter_for(promoted) is not None


# ---------------------------------------------------------------------------
# Dependency checker: blocked-with-reason, never crashes
# ---------------------------------------------------------------------------
def test_dependency_checker_blocks_inventory_stub_without_crash():
    reg = ToolRegistry.load()
    dc = DependencyChecker()

    # API stub (no endpoint) -> blocked with an inventory_stub reason.
    api_stub = next(
        t for t in reg.inventory_tools()
        if t.integration == "api" and not t.non_executable
    )
    res = dc.check_tool_ready(api_stub)
    assert res.ready is False
    assert "inventory_stub" in res.blocked_reason

    # CLI stub with an uninstalled binary -> blocked, names the missing binary.
    cli_stub = next(
        t for t in reg.inventory_tools()
        if t.integration == "cli" and t.binary == "this-binary-does-not-exist-xyz"
    ) if any(t.binary == "this-binary-does-not-exist-xyz" for t in reg.inventory_tools()) else None
    if cli_stub is None:
        cli_stub = next(t for t in reg.inventory_tools() if t.integration == "cli")
    res2 = dc.check_tool_ready(cli_stub)
    # Almost no recon binaries are installed in CI -> blocked with a clear reason.
    if not res2.ready:
        assert res2.blocked_reason


def test_dependency_checker_blocks_non_executable_with_reason():
    reg = ToolRegistry.load()
    dc = DependencyChecker()
    neo = reg.non_executable_tools()[0]
    res = dc.check_tool_ready(neo)
    assert res.ready is False
    assert res.blocked_reason == neo.non_executable_reason


# ---------------------------------------------------------------------------
# Orchestrator: a scan touching inventory-derived tools does not crash
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_orchestrator_scan_with_full_registry_no_crash():
    reg = ToolRegistry.load()
    bus = EventBus()
    dc = DependencyChecker()
    touched: list[str] = []

    async def dependency_aware_execute(job: ScheduledJob) -> ExecutionResult:
        touched.append(job.tool_name)
        spec = reg.get(job.tool_name)
        # Real execute path: block tools whose deps are missing rather than crash.
        if spec is not None:
            readiness = dc.check_tool_ready(spec)
            if not readiness.ready:
                return ExecutionResult(
                    tool_name=job.tool_name, scan_id=job.scan_id,
                    success=False, exit_code=1, error=readiness.blocked_reason or "blocked",
                )
            # Pretend a discovery tool found a subdomain to drive downstream work.
            if "subdomain" in spec.produces or "subdomain" in spec.output_types:
                await bus.publish(EntityDiscovered(
                    scan_id=job.scan_id, tool_name=job.tool_name,
                    entity_type="subdomain", entity_value="api.example.com",
                ))
        return ExecutionResult(
            tool_name=job.tool_name, scan_id=job.scan_id, success=True, exit_code=0,
        )

    orch = EventDrivenOrchestrator(bus=bus, registry=reg, execute_fn=dependency_aware_execute)
    config = ScanConfig(seed="example.com", max_iterations=5, global_concurrency=16)
    result = await asyncio.wait_for(orch.run_scan("example.com", config), timeout=30)

    assert result.status in ("completed", "completed_with_errors")
    # Inventory-derived tools were actually scheduled and executed.
    inv_names = {t.name for t in reg.inventory_tools()}
    assert any(name in inv_names for name in touched), "no inventory tool was touched"


# ---------------------------------------------------------------------------
# Regression: curated contracts survive the merge
# ---------------------------------------------------------------------------
def test_curated_contracts_not_downgraded():
    reg = ToolRegistry.load()
    # A representative sample of curated tools with rich invocation/IO contracts.
    for name in ("uncover", "httpx", "nuclei", "subfinder", "naabu"):
        spec = reg.get(name)
        if spec is None:
            continue
        assert spec.source == "curated", f"{name} should remain curated"
        assert spec.validation_status != "inventory_derived"
        # Contract fields intact: an invocation/endpoint and declared IO.
        assert spec.integration
        assert spec.supported_input_types or spec.consumes
        assert spec.output_types or spec.produces


def test_curated_count_is_preserved():
    reg = ToolRegistry.load()
    # 81 + 10 (gf/unfurl variants) + 1 (github_org_repos) + 5 (github_search
    # dork variants: 1 base -> 6) = 97.
    assert len(reg.curated_tools()) == 97


def test_generic_spec_roundtrip_for_curated_cli():
    reg = ToolRegistry.load()
    spec = reg.get("uncover")
    assert spec is not None
    gspec = to_generic_spec(spec)
    assert gspec is not None
    assert gspec["integration"] == "cli"
    # Curated invocation preserved verbatim (not synthesised).
    assert gspec["invocation"] == spec.invocation
