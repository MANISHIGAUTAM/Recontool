"""Unit tests for structured logging and metrics collection.

Covers: structured log output format, correlation ID propagation,
metrics counter increments, metrics snapshot output.
"""
from __future__ import annotations

import json

import pytest

from recontool.engine.logging import EngineLogger
from recontool.engine.metrics import MetricsCollector


# ---------------------------------------------------------------------------
# Structured Logging Tests
# ---------------------------------------------------------------------------


class TestEngineLogger:
    @pytest.fixture()
    def logger(self):
        return EngineLogger(correlation_id="test-corr-001")

    def test_correlation_id_set(self, logger):
        assert logger.correlation_id == "test-corr-001"

    def test_auto_correlation_id(self):
        logger = EngineLogger()
        assert logger.correlation_id
        assert len(logger.correlation_id) == 36  # UUID format

    def test_log_tool_start_format(self, logger):
        logger.log_tool_start(
            tool_run_id="run-001",
            scan_id="scan-001",
            tool_name="crtsh",
            inputs={"domain": ["example.com"]},
        )
        entries = logger.entries
        assert len(entries) == 1
        entry = entries[0]
        assert entry["event"] == "tool_start"
        assert entry["scan_id"] == "scan-001"
        assert entry["tool_run_id"] == "run-001"
        assert entry["tool_name"] == "crtsh"
        assert entry["inputs"] == {"domain": ["example.com"]}
        assert entry["correlation_id"] == "test-corr-001"
        assert "timestamp" in entry

    def test_log_tool_complete_format(self, logger):
        logger.log_tool_complete(
            tool_run_id="run-001",
            scan_id="scan-001",
            tool_name="crtsh",
            duration_ms=1500,
            exit_code=0,
            entity_count=42,
            input_fingerprint="abc123",
            output_fingerprint="def456",
            artifact_paths=["/tmp/out.json"],
            command="",
            retry_count=0,
        )
        entry = logger.entries[0]
        assert entry["event"] == "tool_complete"
        assert entry["duration_ms"] == 1500
        assert entry["exit_code"] == 0
        assert entry["entity_count"] == 42
        assert entry["input_fingerprint"] == "abc123"
        assert entry["output_fingerprint"] == "def456"
        assert entry["artifact_paths"] == ["/tmp/out.json"]

    def test_log_tool_fail_format(self, logger):
        logger.log_tool_fail(
            tool_run_id="run-002",
            scan_id="scan-001",
            tool_name="subfinder",
            error="timeout after 30s",
            exit_code=124,
            retry_count=2,
            failure_reason="network timeout",
        )
        entry = logger.entries[0]
        assert entry["event"] == "tool_fail"
        assert entry["tool_name"] == "subfinder"
        assert entry["error"] == "timeout after 30s"
        assert entry["exit_code"] == 124
        assert entry["retry_count"] == 2
        assert entry["failure_reason"] == "network timeout"

    def test_log_entity_discovered(self, logger):
        logger.log_entity_discovered(
            scan_id="scan-001",
            entity_type="subdomain",
            entity_value="api.target.com",
            tool_name="crtsh",
            parent_entity_id="ent-parent-001",
        )
        entry = logger.entries[0]
        assert entry["event"] == "entity_discovered"
        assert entry["entity_type"] == "subdomain"
        assert entry["entity_value"] == "api.target.com"
        assert entry["parent_entity_id"] == "ent-parent-001"

    def test_log_pending_key_change(self, logger):
        logger.log_pending_key_change(
            scan_id="scan-001",
            key_type="subdomain",
            key_value="api.target.com",
            action="created",
            tool_name="crtsh",
        )
        entry = logger.entries[0]
        assert entry["event"] == "pending_key_change"
        assert entry["action"] == "created"
        assert entry["key_type"] == "subdomain"

    def test_log_concurrency_decision(self, logger):
        logger.log_concurrency_decision(
            scan_id="scan-001",
            tool_name="nmap",
            decision="blocked",
            reason="rate limit exceeded",
        )
        entry = logger.entries[0]
        assert entry["event"] == "concurrency_decision"
        assert entry["concurrency_decision"] == "blocked"
        assert entry["reason"] == "rate limit exceeded"

    def test_log_ai_decision(self, logger):
        logger.log_ai_decision(
            scan_id="scan-001",
            summary="Persisting 5 entities, discarding 2 noise",
            tool_name="crtsh",
        )
        entry = logger.entries[0]
        assert entry["event"] == "ai_decision"
        assert "Persisting 5" in entry["ai_decision_summary"]

    def test_correlation_id_propagation(self, logger):
        """All entries share the same correlation_id."""
        logger.log_tool_start("r1", "s1", "tool1")
        logger.log_tool_complete("r1", "s1", "tool1")
        logger.log_entity_discovered("s1", "subdomain", "a.com")
        entries = logger.entries
        assert len(entries) == 3
        for entry in entries:
            assert entry["correlation_id"] == "test-corr-001"

    def test_multiple_entries_accumulated(self, logger):
        logger.log_tool_start("r1", "s1", "tool1")
        logger.log_tool_start("r2", "s1", "tool2")
        assert len(logger.entries) == 2

    def test_timestamp_present_in_all_entries(self, logger):
        logger.log_tool_start("r1", "s1", "tool1")
        logger.log_tool_fail("r2", "s1", "tool2", "error")
        for entry in logger.entries:
            assert "timestamp" in entry
            assert "T" in entry["timestamp"]  # ISO format


# ---------------------------------------------------------------------------
# Metrics Collection Tests
# ---------------------------------------------------------------------------


class TestMetricsCollector:
    @pytest.fixture()
    def metrics(self):
        return MetricsCollector()

    def test_record_tool_run_success(self, metrics):
        metrics.record_tool_run("crtsh", "success", 1.5)
        snap = metrics.snapshot()
        assert snap["tool_runs_total"]["crtsh"]["success"] == 1

    def test_record_tool_run_failure(self, metrics):
        metrics.record_tool_run("nmap", "failed", 5.0)
        snap = metrics.snapshot()
        assert snap["tool_runs_total"]["nmap"]["failed"] == 1

    def test_tool_run_counter_increments(self, metrics):
        metrics.record_tool_run("crtsh", "success", 1.0)
        metrics.record_tool_run("crtsh", "success", 2.0)
        metrics.record_tool_run("crtsh", "failed", 0.5)
        snap = metrics.snapshot()
        assert snap["tool_runs_total"]["crtsh"]["success"] == 2
        assert snap["tool_runs_total"]["crtsh"]["failed"] == 1

    def test_tool_duration_stats(self, metrics):
        metrics.record_tool_run("crtsh", "success", 1.0)
        metrics.record_tool_run("crtsh", "success", 3.0)
        snap = metrics.snapshot()
        dur = snap["tool_duration_seconds"]["crtsh"]
        assert dur["count"] == 2
        assert dur["min"] == 1.0
        assert dur["max"] == 3.0
        assert dur["avg"] == 2.0
        assert dur["total"] == 4.0

    def test_record_entity(self, metrics):
        metrics.record_entity("subdomain")
        metrics.record_entity("subdomain")
        metrics.record_entity("ip")
        snap = metrics.snapshot()
        assert snap["entities_discovered_total"]["subdomain"] == 2
        assert snap["entities_discovered_total"]["ip"] == 1

    def test_record_pending_key_created(self, metrics):
        metrics.record_pending_key("created")
        metrics.record_pending_key("created")
        snap = metrics.snapshot()
        assert snap["pending_keys_created_total"] == 2

    def test_record_pending_key_resolved(self, metrics):
        metrics.record_pending_key("resolved")
        snap = metrics.snapshot()
        assert snap["pending_keys_resolved_total"] == 1

    def test_duplicate_suppression(self, metrics):
        metrics.record_duplicate_suppression()
        metrics.record_duplicate_suppression()
        snap = metrics.snapshot()
        assert snap["duplicate_suppression_total"] == 2

    def test_retry_total(self, metrics):
        metrics.record_retry("crtsh")
        metrics.record_retry("crtsh")
        metrics.record_retry("nmap")
        snap = metrics.snapshot()
        assert snap["retry_total"]["crtsh"] == 2
        assert snap["retry_total"]["nmap"] == 1

    def test_scan_depth_gauge(self, metrics):
        metrics.set_scan_depth(3)
        snap = metrics.snapshot()
        assert snap["scan_depth_current"] == 3
        metrics.set_scan_depth(5)
        snap = metrics.snapshot()
        assert snap["scan_depth_current"] == 5

    def test_queue_depth_gauge(self, metrics):
        metrics.set_queue_depth(10)
        snap = metrics.snapshot()
        assert snap["queue_depth_current"] == 10

    def test_blocked_tools_gauge(self, metrics):
        metrics.set_blocked_tools(2)
        snap = metrics.snapshot()
        assert snap["blocked_tools_current"] == 2

    def test_snapshot_initial_state(self, metrics):
        snap = metrics.snapshot()
        assert snap["tool_runs_total"] == {}
        assert snap["entities_discovered_total"] == {}
        assert snap["pending_keys_created_total"] == 0
        assert snap["pending_keys_resolved_total"] == 0
        assert snap["scan_depth_current"] == 0
        assert snap["duplicate_suppression_total"] == 0
        assert snap["queue_depth_current"] == 0
        assert snap["retry_total"] == {}
        assert snap["blocked_tools_current"] == 0
        assert "uptime_seconds" in snap

    def test_to_json_export(self, metrics):
        metrics.record_tool_run("crtsh", "success", 1.5)
        metrics.record_entity("subdomain")
        json_str = metrics.to_json()
        data = json.loads(json_str)
        assert data["tool_runs_total"]["crtsh"]["success"] == 1
        assert data["entities_discovered_total"]["subdomain"] == 1

    def test_snapshot_returns_dict(self, metrics):
        snap = metrics.snapshot()
        assert isinstance(snap, dict)
        # Should be JSON serializable
        json.dumps(snap)
