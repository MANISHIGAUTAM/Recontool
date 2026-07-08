"""Unit tests for the event-driven engine core components.

Covers: EventBus dispatch, ToolRegistry loading, PendingKeyStore CRUD,
DependencyChecker logic, fingerprint generation, IncrementalEngine decisions,
scheduler eligibility logic, executor concurrency bounds.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
from unittest.mock import patch

import pytest

from recontool.core import db
from recontool.core.models import Scan
from recontool.engine.dependency import DependencyChecker
from recontool.engine.events import (
    EntityDiscovered,
    EventBus,
    ToolCompleted,
    ToolFailed,
)
from recontool.engine.executor import ExecutionResult, ParallelExecutor
from recontool.engine.fingerprint import (
    fingerprint_config,
    fingerprint_inputs,
    fingerprint_output,
    has_changed,
)
from recontool.engine.incremental import IncrementalEngine
from recontool.engine.models import ToolRun
from recontool.engine.output import NormalizedOutput, OutputNormalizer
from recontool.engine.pending_keys import PendingKeyStore
from recontool.engine.registry import ToolRegistry, ToolSpec
from recontool.engine.scheduler import EventDrivenScheduler, ScheduledJob


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine_db(tmp_path):
    """Fresh DB for engine tests."""
    db.init_engine(f"sqlite:///{tmp_path / 'engine_test.db'}")
    db.create_all()
    scan_id = "scan-test-001"
    with db.session_scope() as s:
        s.add(Scan(id=scan_id, seed="example.com", seed_type="domain",
                   profile="normal", status="running", scope_json={}))
    return scan_id


@pytest.fixture()
def bus():
    return EventBus()


@pytest.fixture()
def registry():
    """Minimal registry with test tools."""
    tools = {
        "subfinder": ToolSpec(
            name="subfinder",
            category=2,
            binary="subfinder",
            supported_input_types=["domain"],
            output_types=["subdomain"],
            produces=["subdomain"],
            consumes=["domain"],
            parallel_safe=True,
            concurrency_safety=True,
            enabled=True,
        ),
        "nmap": ToolSpec(
            name="nmap",
            category=4,
            binary="nmap",
            supported_input_types=["subdomain", "ip"],
            output_types=["service"],
            produces=["service"],
            consumes=["subdomain", "ip"],
            parallel_safe=True,
            concurrency_safety=True,
            enabled=True,
        ),
        "disabled_tool": ToolSpec(
            name="disabled_tool",
            category=1,
            supported_input_types=["domain"],
            enabled=False,
        ),
    }
    return ToolRegistry(tools)


# ---------------------------------------------------------------------------
# EventBus tests
# ---------------------------------------------------------------------------


class TestEventBus:
    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(ToolCompleted, handler)
        event = ToolCompleted(scan_id="scan1", tool_name="nmap", exit_code=0)
        await bus.publish(event)

        assert len(received) == 1
        assert received[0].tool_name == "nmap"

    @pytest.mark.asyncio
    async def test_multiple_handlers(self, bus):
        results = []

        async def handler_a(event):
            results.append("a")

        async def handler_b(event):
            results.append("b")

        bus.subscribe(ToolCompleted, handler_a)
        bus.subscribe(ToolCompleted, handler_b)
        await bus.publish(ToolCompleted(scan_id="scan1", tool_name="test"))

        assert sorted(results) == ["a", "b"]

    @pytest.mark.asyncio
    async def test_no_cross_event_dispatch(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(ToolCompleted, handler)
        # Publishing a different event type should NOT trigger handler
        await bus.publish(ToolFailed(scan_id="scan1", tool_name="test"))

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_unsubscribe(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(ToolCompleted, handler)
        bus.unsubscribe(ToolCompleted, handler)
        await bus.publish(ToolCompleted(scan_id="scan1", tool_name="test"))

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_clear(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(ToolCompleted, handler)
        bus.clear()
        await bus.publish(ToolCompleted(scan_id="scan1", tool_name="test"))

        assert len(received) == 0


# ---------------------------------------------------------------------------
# ToolRegistry tests
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def test_get_existing_tool(self, registry):
        spec = registry.get("subfinder")
        assert spec is not None
        assert spec.name == "subfinder"
        assert spec.category == 2

    def test_get_nonexistent_tool(self, registry):
        assert registry.get("nonexistent") is None

    def test_all_tools(self, registry):
        tools = registry.all_tools()
        assert "subfinder" in tools
        assert "nmap" in tools
        assert len(tools) == 3

    def test_by_category(self, registry):
        cat2 = registry.by_category(2)
        assert len(cat2) == 1
        assert cat2[0].name == "subfinder"

    def test_by_input_type(self, registry):
        domain_tools = registry.by_input_type("domain")
        names = [t.name for t in domain_tools]
        assert "subfinder" in names

    def test_by_output_type(self, registry):
        subdomain_tools = registry.by_output_type("subdomain")
        names = [t.name for t in subdomain_tools]
        assert "subfinder" in names

    def test_contains(self, registry):
        assert "subfinder" in registry
        assert "fake_tool" not in registry

    def test_len(self, registry):
        assert len(registry) == 3

    def test_load_from_config(self):
        """Test loading from actual config files."""
        reg = ToolRegistry.load()
        # Should load without errors
        assert len(reg) > 0


# ---------------------------------------------------------------------------
# PendingKeyStore tests
# ---------------------------------------------------------------------------


class TestPendingKeyStore:
    def test_create_key(self, engine_db):
        with db.session_scope() as session:
            store = PendingKeyStore(session)
            record = store.create_key(
                scan_id=engine_db,
                key_type="subdomain",
                key_value="sub.example.com",
                created_by_tool="subfinder",
            )
            assert record.id is not None
            assert record.status == "pending"
            assert record.key_type == "subdomain"

    def test_resolve_key(self, engine_db):
        with db.session_scope() as session:
            store = PendingKeyStore(session)
            store.create_key(
                scan_id=engine_db,
                key_type="subdomain",
                key_value="sub.example.com",
                created_by_tool="subfinder",
            )
            resolved = store.resolve_key(
                scan_id=engine_db,
                key_type="subdomain",
                key_value="sub.example.com",
                resolved_by_tool="nmap",
            )
            assert resolved is not None
            assert resolved.status == "resolved"
            assert resolved.resolved_by_tool == "nmap"

    def test_resolve_nonexistent_key(self, engine_db):
        with db.session_scope() as session:
            store = PendingKeyStore(session)
            result = store.resolve_key(
                scan_id=engine_db,
                key_type="subdomain",
                key_value="nonexistent.com",
                resolved_by_tool="nmap",
            )
            assert result is None

    def test_get_pending_for_tool(self, engine_db):
        with db.session_scope() as session:
            store = PendingKeyStore(session)
            store.create_key(engine_db, "subdomain", "a.example.com", "subfinder")
            store.create_key(engine_db, "subdomain", "b.example.com", "subfinder")
            store.create_key(engine_db, "ip", "1.2.3.4", "dnsx")

            pending = store.get_pending_for_tool(engine_db, "subdomain")
            assert len(pending) == 2

    def test_is_tool_ready(self, engine_db):
        with db.session_scope() as session:
            store = PendingKeyStore(session)
            # No resolved keys yet
            assert not store.is_tool_ready(engine_db, ["subdomain"])

            # Create and resolve a key
            store.create_key(engine_db, "subdomain", "sub.example.com", "subfinder")
            store.resolve_key(engine_db, "subdomain", "sub.example.com", "nmap")
            assert store.is_tool_ready(engine_db, ["subdomain"])

    def test_get_resolved_keys(self, engine_db):
        with db.session_scope() as session:
            store = PendingKeyStore(session)
            store.create_key(engine_db, "subdomain", "a.example.com", "subfinder")
            store.create_key(engine_db, "subdomain", "b.example.com", "subfinder")
            store.resolve_key(engine_db, "subdomain", "a.example.com", "nmap")

            resolved = store.get_resolved_keys(engine_db, "subdomain")
            assert len(resolved) == 1
            assert resolved[0].key_value == "a.example.com"


# ---------------------------------------------------------------------------
# DependencyChecker tests
# ---------------------------------------------------------------------------


class TestDependencyChecker:
    def test_check_binary_available(self):
        checker = DependencyChecker()
        # 'python' or 'python3' should be available in test env
        assert checker.check_binary_available("python3") or checker.check_binary_available("python")
        assert not checker.check_binary_available("totally_fake_binary_xyz_123")

    def test_check_env_vars_present(self):
        checker = DependencyChecker()
        # PATH is always set
        missing = checker.check_env_vars(["PATH"])
        assert missing == []

    def test_check_env_vars_missing(self):
        checker = DependencyChecker()
        missing = checker.check_env_vars(["NONEXISTENT_VAR_XYZ_99"])
        assert "NONEXISTENT_VAR_XYZ_99" in missing

    def test_check_api_key_available(self):
        checker = DependencyChecker()
        with patch.dict(os.environ, {"TEST_API_KEY": "secret123"}):
            assert checker.check_api_key_available("TEST_API_KEY")
        assert not checker.check_api_key_available("NONEXISTENT_KEY_ABC")

    def test_check_tool_ready_no_binary(self):
        checker = DependencyChecker()
        spec = ToolSpec(name="fake_tool", binary="totally_fake_binary_xyz")
        result = checker.check_tool_ready(spec)
        assert not result.ready
        assert "totally_fake_binary_xyz" in result.missing_deps

    def test_check_tool_ready_no_requirements(self):
        checker = DependencyChecker()
        spec = ToolSpec(name="api_tool", binary="")
        result = checker.check_tool_ready(spec)
        assert result.ready
        assert result.blocked_reason is None

    def test_check_tool_ready_with_api_key(self):
        checker = DependencyChecker()
        spec = ToolSpec(name="keyed_tool", binary="", requires_key="FAKE_KEY_VAR")
        result = checker.check_tool_ready(spec)
        assert not result.ready
        assert "FAKE_KEY_VAR" in result.missing_deps

    def test_check_file_permissions(self, tmp_path):
        checker = DependencyChecker()
        # Create a readable file
        f = tmp_path / "readable.txt"
        f.write_text("hello")
        missing = checker.check_file_permissions([str(f)])
        assert missing == []

        # Non-existent file
        missing = checker.check_file_permissions(["/nonexistent/path/xyz"])
        assert len(missing) == 1


# ---------------------------------------------------------------------------
# Fingerprint tests
# ---------------------------------------------------------------------------


class TestFingerprint:
    def test_fingerprint_inputs_deterministic(self):
        fp1 = fingerprint_inputs("nmap", {"target": "example.com", "ports": "1-1000"})
        fp2 = fingerprint_inputs("nmap", {"target": "example.com", "ports": "1-1000"})
        assert fp1 == fp2

    def test_fingerprint_inputs_different_inputs(self):
        fp1 = fingerprint_inputs("nmap", {"target": "example.com"})
        fp2 = fingerprint_inputs("nmap", {"target": "other.com"})
        assert fp1 != fp2

    def test_fingerprint_inputs_order_independent(self):
        fp1 = fingerprint_inputs("nmap", {"a": "1", "b": "2"})
        fp2 = fingerprint_inputs("nmap", {"b": "2", "a": "1"})
        assert fp1 == fp2

    def test_fingerprint_output_deterministic(self):
        fp1 = fingerprint_output("nmap", {"hosts": ["a.com", "b.com"]})
        fp2 = fingerprint_output("nmap", {"hosts": ["a.com", "b.com"]})
        assert fp1 == fp2

    def test_fingerprint_config(self):
        spec = ToolSpec(name="test", version="1.0", timeout=300)
        fp1 = fingerprint_config(spec)
        # Same spec should produce same fingerprint
        spec2 = ToolSpec(name="test", version="1.0", timeout=300)
        fp2 = fingerprint_config(spec2)
        assert fp1 == fp2

    def test_fingerprint_config_changes(self):
        spec1 = ToolSpec(name="test", version="1.0", timeout=300)
        spec2 = ToolSpec(name="test", version="2.0", timeout=300)
        fp1 = fingerprint_config(spec1)
        fp2 = fingerprint_config(spec2)
        assert fp1 != fp2

    def test_has_changed(self):
        assert has_changed("abc", "def")
        assert not has_changed("abc", "abc")

    def test_fingerprint_is_sha256(self):
        fp = fingerprint_inputs("tool", {"key": "value"})
        assert len(fp) == 64  # SHA-256 hex digest is 64 chars
        assert all(c in "0123456789abcdef" for c in fp)


# ---------------------------------------------------------------------------
# IncrementalEngine tests
# ---------------------------------------------------------------------------


class TestIncrementalEngine:
    def test_should_rerun_never_run(self, engine_db):
        with db.session_scope() as session:
            engine = IncrementalEngine(session)
            assert engine.should_rerun("subfinder", engine_db, {"target": "example.com"})

    def test_should_not_rerun_recent_success(self, engine_db):
        with db.session_scope() as session:
            engine = IncrementalEngine(session)
            # Record a successful run
            run = ToolRun(
                scan_id=engine_db,
                tool_name="subfinder",
                status="completed",
                input_fingerprint=fingerprint_inputs("subfinder", {"target": "example.com"}),
                finished_at=dt.datetime.now(dt.timezone.utc),
            )
            engine.record_run(run)

            # Same inputs, recent run - should NOT rerun
            assert not engine.should_rerun(
                "subfinder", engine_db, {"target": "example.com"},
                max_age_seconds=3600,
            )

    def test_should_rerun_changed_inputs(self, engine_db):
        with db.session_scope() as session:
            engine = IncrementalEngine(session)
            run = ToolRun(
                scan_id=engine_db,
                tool_name="subfinder",
                status="completed",
                input_fingerprint=fingerprint_inputs("subfinder", {"target": "old.com"}),
                finished_at=dt.datetime.now(dt.timezone.utc),
            )
            engine.record_run(run)

            # Different inputs - should rerun
            assert engine.should_rerun(
                "subfinder", engine_db, {"target": "new.com"},
                max_age_seconds=3600,
            )

    def test_should_rerun_failed_run(self, engine_db):
        with db.session_scope() as session:
            engine = IncrementalEngine(session)
            run = ToolRun(
                scan_id=engine_db,
                tool_name="subfinder",
                status="failed",
                input_fingerprint=fingerprint_inputs("subfinder", {"target": "example.com"}),
                finished_at=dt.datetime.now(dt.timezone.utc),
            )
            engine.record_run(run)

            # Failed runs should always be retried
            assert engine.should_rerun("subfinder", engine_db, {"target": "example.com"})

    def test_should_rerun_stale(self, engine_db):
        with db.session_scope() as session:
            engine = IncrementalEngine(session)
            # Record a very old run
            old_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
            run = ToolRun(
                scan_id=engine_db,
                tool_name="subfinder",
                status="completed",
                input_fingerprint=fingerprint_inputs("subfinder", {"target": "example.com"}),
                finished_at=old_time,
            )
            engine.record_run(run)

            # Same inputs but stale - should rerun
            assert engine.should_rerun(
                "subfinder", engine_db, {"target": "example.com"},
                max_age_seconds=3600,
            )

    def test_get_last_run(self, engine_db):
        with db.session_scope() as session:
            engine = IncrementalEngine(session)
            run = ToolRun(
                scan_id=engine_db,
                tool_name="subfinder",
                status="completed",
            )
            engine.record_run(run)
            last = engine.get_last_run("subfinder", engine_db)
            assert last is not None
            assert last.tool_name == "subfinder"

    def test_get_stale_tools(self, engine_db):
        with db.session_scope() as session:
            engine = IncrementalEngine(session)
            old_time = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
            run = ToolRun(
                scan_id=engine_db,
                tool_name="subfinder",
                status="completed",
                finished_at=old_time,
            )
            engine.record_run(run)

            stale = engine.get_stale_tools(engine_db, max_age_seconds=3600)
            assert "subfinder" in stale


# ---------------------------------------------------------------------------
# Scheduler tests
# ---------------------------------------------------------------------------


class TestScheduler:
    @pytest.mark.asyncio
    async def test_select_eligible_tools(self, bus, registry):
        scheduler = EventDrivenScheduler(bus=bus, registry=registry)
        scan_id = "scan-test"
        scheduler._available_keys[scan_id] = {"domain"}
        scheduler._running_tools[scan_id] = set()
        scheduler._completed_tools[scan_id] = set()

        eligible = scheduler.select_eligible_tools(scan_id)
        names = [t.name for t in eligible]
        assert "subfinder" in names
        # disabled_tool should not appear
        assert "disabled_tool" not in names

    @pytest.mark.asyncio
    async def test_select_excludes_running(self, bus, registry):
        scheduler = EventDrivenScheduler(bus=bus, registry=registry)
        scan_id = "scan-test"
        scheduler._available_keys[scan_id] = {"domain"}
        scheduler._running_tools[scan_id] = {"subfinder"}
        scheduler._completed_tools[scan_id] = set()

        eligible = scheduler.select_eligible_tools(scan_id)
        names = [t.name for t in eligible]
        assert "subfinder" not in names

    @pytest.mark.asyncio
    async def test_select_excludes_completed(self, bus, registry):
        scheduler = EventDrivenScheduler(bus=bus, registry=registry)
        scan_id = "scan-test"
        scheduler._available_keys[scan_id] = {"domain"}
        scheduler._running_tools[scan_id] = set()
        scheduler._completed_tools[scan_id] = {"subfinder"}

        eligible = scheduler.select_eligible_tools(scan_id)
        names = [t.name for t in eligible]
        assert "subfinder" not in names

    @pytest.mark.asyncio
    async def test_submit_scan_queues_jobs(self, bus, registry):
        scheduler = EventDrivenScheduler(bus=bus, registry=registry)
        await scheduler.submit_scan("scan-1", "example.com", {"seed_type": "domain"})

        # Should have queued at least subfinder (consumes domain)
        jobs = []
        while not scheduler.job_queue.empty():
            jobs.append(await scheduler.job_queue.get())
        tool_names = [j.tool_name for j in jobs]
        assert "subfinder" in tool_names

    @pytest.mark.asyncio
    async def test_convergence_no_running_no_eligible(self, bus, registry):
        scheduler = EventDrivenScheduler(bus=bus, registry=registry)
        scan_id = "scan-test"
        scheduler._available_keys[scan_id] = set()
        scheduler._running_tools[scan_id] = set()
        scheduler._completed_tools[scan_id] = set()

        # No available keys and no running tools = converged (no eligible tools)
        assert scheduler.check_convergence(scan_id)

    @pytest.mark.asyncio
    async def test_convergence_tools_running(self, bus, registry):
        scheduler = EventDrivenScheduler(bus=bus, registry=registry)
        scan_id = "scan-test"
        scheduler._available_keys[scan_id] = {"domain"}
        scheduler._running_tools[scan_id] = {"subfinder"}
        scheduler._completed_tools[scan_id] = set()

        # Tools still running = not converged
        assert not scheduler.check_convergence(scan_id)

    @pytest.mark.asyncio
    async def test_on_entity_discovered_adds_key(self, bus, registry):
        scheduler = EventDrivenScheduler(bus=bus, registry=registry)
        scan_id = "scan-test"
        scheduler._available_keys[scan_id] = {"domain"}
        scheduler._running_tools[scan_id] = set()
        scheduler._completed_tools[scan_id] = set()
        scheduler._blocked_tools[scan_id] = {}

        event = EntityDiscovered(
            scan_id=scan_id,
            tool_name="subfinder",
            entity_type="subdomain",
            entity_value="sub.example.com",
        )
        await scheduler.on_entity_discovered(event)
        assert "subdomain" in scheduler._available_keys[scan_id]


# ---------------------------------------------------------------------------
# Executor tests
# ---------------------------------------------------------------------------


class TestExecutor:
    @pytest.mark.asyncio
    async def test_execute_one_success(self, bus):
        executor = ParallelExecutor(bus=bus, global_limit=5)

        async def mock_execute(job):
            return ExecutionResult(
                tool_name=job.tool_name,
                scan_id=job.scan_id,
                success=True,
                exit_code=0,
                stdout="output",
            )

        job = ScheduledJob(tool_name="nmap", scan_id="scan-1", inputs={})
        result = await executor.execute_one(job, mock_execute)
        assert result.success
        assert result.exit_code == 0
        assert executor.total_executed == 1

    @pytest.mark.asyncio
    async def test_execute_one_failure(self, bus):
        executor = ParallelExecutor(bus=bus, global_limit=5)

        async def mock_execute(job):
            return ExecutionResult(
                tool_name=job.tool_name,
                scan_id=job.scan_id,
                success=False,
                exit_code=1,
                error="timeout",
            )

        job = ScheduledJob(tool_name="nmap", scan_id="scan-1", inputs={})
        result = await executor.execute_one(job, mock_execute)
        assert not result.success
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_execute_batch(self, bus):
        executor = ParallelExecutor(bus=bus, global_limit=10)

        async def mock_execute(job):
            await asyncio.sleep(0.01)
            return ExecutionResult(
                tool_name=job.tool_name,
                scan_id=job.scan_id,
                success=True,
                exit_code=0,
            )

        jobs = [
            ScheduledJob(tool_name=f"tool_{i}", scan_id="scan-1", inputs={})
            for i in range(5)
        ]
        results = await executor.execute_batch(jobs, mock_execute)
        assert len(results) == 5
        assert all(r.success for r in results)
        assert executor.total_executed == 5

    @pytest.mark.asyncio
    async def test_global_concurrency_limit(self, bus):
        """Verify that the global semaphore limits parallel execution."""
        executor = ParallelExecutor(bus=bus, global_limit=2)
        max_concurrent = 0
        current = 0
        lock = asyncio.Lock()

        async def mock_execute(job):
            nonlocal max_concurrent, current
            async with lock:
                current += 1
                if current > max_concurrent:
                    max_concurrent = current
            await asyncio.sleep(0.05)
            async with lock:
                current -= 1
            return ExecutionResult(
                tool_name=job.tool_name,
                scan_id=job.scan_id,
                success=True,
                exit_code=0,
            )

        jobs = [
            ScheduledJob(tool_name=f"tool_{i}", scan_id="scan-1", inputs={})
            for i in range(5)
        ]
        await executor.execute_batch(jobs, mock_execute)
        # Max concurrent should not exceed global limit of 2
        assert max_concurrent <= 2

    @pytest.mark.asyncio
    async def test_per_tool_concurrency_limit(self, bus):
        """Verify per-tool semaphore limits."""
        executor = ParallelExecutor(
            bus=bus, global_limit=10, per_tool_concurrency={"nmap": 1}
        )
        max_concurrent = 0
        current = 0
        lock = asyncio.Lock()

        async def mock_execute(job):
            nonlocal max_concurrent, current
            async with lock:
                current += 1
                if current > max_concurrent:
                    max_concurrent = current
            await asyncio.sleep(0.05)
            async with lock:
                current -= 1
            return ExecutionResult(
                tool_name=job.tool_name,
                scan_id=job.scan_id,
                success=True,
                exit_code=0,
            )

        # All jobs use the same tool with limit=1
        jobs = [
            ScheduledJob(tool_name="nmap", scan_id="scan-1", inputs={})
            for _ in range(4)
        ]
        await executor.execute_batch(jobs, mock_execute)
        assert max_concurrent <= 1

    @pytest.mark.asyncio
    async def test_execute_one_exception(self, bus):
        """Executor handles exceptions gracefully."""
        executor = ParallelExecutor(bus=bus, global_limit=5)

        async def mock_execute(job):
            raise RuntimeError("connection refused")

        job = ScheduledJob(tool_name="nmap", scan_id="scan-1", inputs={})
        result = await executor.execute_one(job, mock_execute)
        assert not result.success
        assert "connection refused" in result.error


# ---------------------------------------------------------------------------
# OutputNormalizer tests
# ---------------------------------------------------------------------------


class TestOutputNormalizer:
    def test_normalize_json_stdout(self):
        normalizer = OutputNormalizer()
        stdout = '{"domains": ["a.example.com", "b.example.com"]}'
        result = normalizer.normalize_tool_output("subfinder", stdout=stdout)

        assert isinstance(result, NormalizedOutput)
        assert result.exit_code == 0
        assert len(result.discovered_entities) == 2
        assert result.confidence_score == 1.0

    def test_normalize_non_json_stdout(self):
        normalizer = OutputNormalizer()
        result = normalizer.normalize_tool_output("nmap", stdout="plain text output")

        assert result.parsed_json == {}
        assert result.confidence_score == 0.7

    def test_normalize_failure_exit_code(self):
        normalizer = OutputNormalizer()
        result = normalizer.normalize_tool_output(
            "nmap", stdout="", stderr="error: timeout", exit_code=1
        )
        assert result.exit_code == 1
        assert result.confidence_score == 0.3
        assert len(result.partial_failures) > 0

    def test_normalize_services(self):
        normalizer = OutputNormalizer()
        stdout = '{"services": [{"host": "example.com", "port": 443}]}'
        result = normalizer.normalize_tool_output("nmap", stdout=stdout)
        assert len(result.discovered_entities) == 1
        assert result.discovered_entities[0].entity == "service"

    def test_normalize_empty_output(self):
        normalizer = OutputNormalizer()
        result = normalizer.normalize_tool_output("tool", stdout="", stderr="")
        assert result.confidence_score == 0.5
        assert result.discovered_entities == []

    def test_normalize_with_warnings(self):
        normalizer = OutputNormalizer()
        result = normalizer.normalize_tool_output(
            "tool", stdout="ok", stderr="warning: rate limited"
        )
        assert len(result.warnings) == 1
        assert "rate limited" in result.warnings[0]
