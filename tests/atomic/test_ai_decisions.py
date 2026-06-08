"""Tests for the AI decision layer with heuristic fallback."""
from __future__ import annotations

import asyncio
import logging
import time

import pytest

from recontool.engine.ai_decision import (
    AIDecisionLayer,
    Anomaly,
    Decision,
    ErrorDecision,
    StrategyAdjustment,
)
from recontool.engine.log_analyzer import LogAnalyzer


@pytest.fixture(autouse=True)
def _suppress_obs_logging(monkeypatch):
    """Prevent AI decision logging from configuring the global recontool logger,
    which would interfere with other tests that rely on capsys stderr capture."""
    monkeypatch.setattr("recontool.obs.configure_logging", lambda *a, **kw: None)


@pytest.fixture
def log_analyzer():
    return LogAnalyzer()


@pytest.fixture
def ai_layer(log_analyzer):
    return AIDecisionLayer(log_analyzer=log_analyzer, supervisor=None)


@pytest.fixture
def ai_layer_with_stream(log_analyzer):
    events = []

    def stream(event, **kw):
        events.append((event, kw))

    layer = AIDecisionLayer(log_analyzer=log_analyzer, supervisor=None, stream=stream)
    return layer, events


# ── Error handling tests ─────────────────────────────────────────────────────

class TestErrorHandling:
    def test_auth_error_skips(self, ai_layer):
        decision = ai_layer.handle_error(
            "shodan", "401 Unauthorized", "p2_expansion"
        )
        assert decision.action == "skip"
        assert "auth" in decision.reason.lower() or "credential" in decision.reason.lower()

    def test_rate_limit_retries(self, ai_layer):
        decision = ai_layer.handle_error(
            "crtsh", "HTTP 429 Too Many Requests", "p1_seed"
        )
        assert decision.action == "retry"
        assert decision.retry_delay > 0

    def test_timeout_retries_first_time(self, ai_layer):
        decision = ai_layer.handle_error(
            "subfinder", "Request timeout after 30s", "p2_expansion"
        )
        assert decision.action == "retry"

    def test_network_error_tries_alternative(self, ai_layer):
        decision = ai_layer.handle_error(
            "crtsh", "Connection refused: DNS resolution failed",
            "p1_seed",
            available_alternatives=["certspotter", "subdomaincenter"],
        )
        assert decision.action == "alternative"
        assert decision.alternative_adapter == "certspotter"

    def test_consecutive_failures_skip(self, ai_layer):
        # Simulate 3 consecutive failures
        for _ in range(4):
            ai_layer.log_analyzer.record_failure("broken_adapter", 1.0)
        decision = ai_layer.handle_error(
            "broken_adapter", "Some error", "p2_expansion"
        )
        assert decision.action == "skip"
        assert "consecutive" in decision.reason.lower() or "skip" in decision.reason.lower()

    def test_two_failures_tries_alternative(self, ai_layer):
        ai_layer.log_analyzer.record_failure("flaky", 1.0)
        ai_layer.log_analyzer.record_failure("flaky", 1.0)
        decision = ai_layer.handle_error(
            "flaky", "Timeout", "p1_seed",
            available_alternatives=["backup_adapter"],
        )
        assert decision.action == "alternative"
        assert decision.alternative_adapter == "backup_adapter"

    def test_error_decision_logged(self, ai_layer):
        ai_layer.handle_error("test_adapter", "500 Internal Server Error", "p1_seed")
        assert len(ai_layer.decisions) == 1
        assert ai_layer.decisions[0].decision_type == "error_handling"


# ── Strategy adjustment tests ────────────────────────────────────────────────

class TestStrategyAdjustment:
    def test_high_discovery_rate_explores_deeper(self, ai_layer):
        result = ai_layer.adjust_strategy(
            "p1_seed",
            {"asset": 50, "endpoint": 10, "finding": 0},
            total_assets=100,
            scan_elapsed=30.0,
        )
        assert result.explore_deeper is True
        assert "growing" in result.reason.lower() or "discovery" in result.reason.lower()

    def test_many_findings_explores_deeper(self, ai_layer):
        result = ai_layer.adjust_strategy(
            "p3_enrichment",
            {"asset": 5, "endpoint": 20, "finding": 8},
            total_assets=200,
            scan_elapsed=60.0,
        )
        assert result.explore_deeper is True
        assert "finding" in result.reason.lower()

    def test_no_discoveries_moves_on(self, ai_layer):
        result = ai_layer.adjust_strategy(
            "p2_expansion",
            {"asset": 0, "endpoint": 0, "finding": 0},
            total_assets=50,
            scan_elapsed=60.0,
        )
        assert result.explore_deeper is False
        assert "no new" in result.reason.lower() or "moving" in result.reason.lower()

    def test_long_running_low_yield_converges(self, ai_layer):
        result = ai_layer.adjust_strategy(
            "p3_enrichment",
            {"asset": 2, "endpoint": 1, "finding": 0},
            total_assets=100,
            scan_elapsed=400.0,
        )
        assert result.explore_deeper is False
        assert "converg" in result.reason.lower()

    def test_strategy_logged(self, ai_layer):
        ai_layer.adjust_strategy("p1_seed", {"asset": 5}, total_assets=50, scan_elapsed=10)
        assert len(ai_layer.decisions) == 1
        assert ai_layer.decisions[0].decision_type == "strategy"


# ── Anomaly detection tests ──────────────────────────────────────────────────

class TestAnomalyDetection:
    def test_detects_internal_ip_leak(self, ai_layer):
        anomalies = ai_layer.detect_anomalies({
            "ips": ["192.168.1.100", "10.0.0.5", "8.8.8.8"],
            "subdomains": [],
            "endpoints": [],
        })
        internal = [a for a in anomalies if a.category == "internal_ip_leak"]
        assert len(internal) == 2
        assert all(a.severity == "high" for a in internal)

    def test_detects_staging_subdomains(self, ai_layer):
        anomalies = ai_layer.detect_anomalies({
            "ips": [],
            "subdomains": ["staging.example.com", "dev.example.com", "www.example.com"],
            "endpoints": [],
        })
        staging = [a for a in anomalies if a.category == "staging_exposed"]
        assert len(staging) == 2

    def test_detects_debug_endpoints(self, ai_layer):
        anomalies = ai_layer.detect_anomalies({
            "ips": [],
            "subdomains": [],
            "endpoints": ["https://example.com/admin", "https://example.com/.env",
                         "https://example.com/api/v1/users"],
        })
        debug = [a for a in anomalies if a.category == "debug_endpoint"]
        assert len(debug) == 2

    def test_detects_sensitive_files(self, ai_layer):
        anomalies = ai_layer.detect_anomalies({
            "ips": [],
            "subdomains": [],
            "endpoints": ["https://example.com/backup.sql",
                         "https://example.com/config.bak",
                         "https://example.com/index.html"],
        })
        sensitive = [a for a in anomalies if a.category == "sensitive_path"]
        assert len(sensitive) == 2

    def test_no_anomalies_for_clean_data(self, ai_layer):
        anomalies = ai_layer.detect_anomalies({
            "ips": ["1.2.3.4", "5.6.7.8"],
            "subdomains": ["www.example.com", "api.example.com"],
            "endpoints": ["https://example.com/", "https://example.com/about"],
        })
        assert len(anomalies) == 0

    def test_anomalies_accumulated(self, ai_layer):
        ai_layer.detect_anomalies({"ips": ["10.0.0.1"], "subdomains": [], "endpoints": []})
        ai_layer.detect_anomalies({"ips": ["172.16.0.1"], "subdomains": [], "endpoints": []})
        assert len(ai_layer.anomalies) == 2


# ── Decision logging and stream tests ────────────────────────────────────────

class TestDecisionLogging:
    def test_decisions_logged_to_list(self, ai_layer):
        ai_layer.handle_error("adapter1", "timeout", "p1_seed")
        ai_layer.adjust_strategy("p1_seed", {"asset": 5}, 50, 10.0)
        assert len(ai_layer.decisions) == 2

    def test_stream_callback_receives_events(self, ai_layer_with_stream):
        layer, events = ai_layer_with_stream
        layer.handle_error("adapter1", "timeout", "p1_seed")
        ai_events = [e for e in events if e[0] == "ai_decision"]
        assert len(ai_events) == 1
        assert ai_events[0][1]["decision_type"] == "error_handling"

    def test_format_decisions_log_empty(self, ai_layer):
        text = ai_layer.format_decisions_log()
        assert "No AI decisions" in text

    def test_format_decisions_log_with_entries(self, ai_layer):
        ai_layer.handle_error("test", "error", "p1_seed")
        text = ai_layer.format_decisions_log()
        assert "ERROR_HANDLING" in text
        assert "test" in text

    def test_generate_summary(self, ai_layer):
        ai_layer.handle_error("adapter1", "timeout", "p1_seed")
        ai_layer.detect_anomalies({"ips": ["10.0.0.1"], "subdomains": [], "endpoints": []})
        summary = ai_layer.generate_summary("scan123", "example.com", [])
        assert "example.com" in summary
        assert "scan123" in summary
        assert "Error Handling" in summary or "error" in summary.lower()
        assert "Anomal" in summary


# ── Heuristic decide tests (event-driven path) ──────────────────────────────

class TestHeuristicDecide:
    def test_depth_limit_blocks(self, ai_layer):
        from recontool.engine.events import EngineEvent, EventType
        event = EngineEvent(type=EventType.NEW_SUBDOMAIN, data={}, depth=10)
        decision = asyncio.run(
            ai_layer.decide(event, ["adapter1", "adapter2"])
        )
        assert decision.should_process is False
        assert "depth" in decision.reason

    def test_all_skipped_adapters_blocks(self, ai_layer):
        from recontool.engine.events import EngineEvent, EventType
        # Mark all adapters as failed
        for _ in range(4):
            ai_layer.log_analyzer.record_failure("adapter1", 1.0)
            ai_layer.log_analyzer.record_failure("adapter2", 1.0)
        event = EngineEvent(type=EventType.NEW_SUBDOMAIN, data={}, depth=1)
        decision = asyncio.run(
            ai_layer.decide(event, ["adapter1", "adapter2"])
        )
        assert decision.should_process is False

    def test_normal_decision_proceeds(self, ai_layer):
        from recontool.engine.events import EngineEvent, EventType
        event = EngineEvent(type=EventType.NEW_SUBDOMAIN, data={}, depth=1)
        decision = asyncio.run(
            ai_layer.decide(event, ["adapter1", "adapter2"])
        )
        assert decision.should_process is True
        assert decision.adapters_to_run == ["adapter1", "adapter2"]


# ── No-LLM fallback test ────────────────────────────────────────────────────

class TestHeuristicFallback:
    """Verify all paths work without an LLM configured (supervisor=None)."""

    def test_no_supervisor_uses_heuristics(self):
        layer = AIDecisionLayer(log_analyzer=LogAnalyzer(), supervisor=None)
        # Error handling works
        d = layer.handle_error("test", "500 error", "p1_seed")
        assert d.action in ("retry", "skip", "alternative")
        # Strategy works
        s = layer.adjust_strategy("p1_seed", {"asset": 10}, 30, 15.0)
        assert isinstance(s, StrategyAdjustment)
        # Anomaly detection works
        a = layer.detect_anomalies({"ips": ["10.0.0.1"], "subdomains": [], "endpoints": []})
        assert len(a) == 1
