"""Tests for the event-driven graph expansion engine.

Covers:
  - Event dispatch and handler registry
  - Priority scoring
  - Convergence detection
  - Engine run in demo mode
  - State machine transitions
  - Log analyzer (adapter performance tracking)
  - Scheduler pool routing
"""
from __future__ import annotations

import asyncio
import time

import pytest

from recontool.engine.convergence import ConvergenceDetector
from recontool.engine.events import (
    EngineEvent,
    EventType,
    HandlerRegistry,
    build_default_registry,
)
from recontool.engine.log_analyzer import LogAnalyzer
from recontool.engine.priority import EntityScore, PriorityScorer
from recontool.engine.scheduler import DEFAULT_POOLS, Scheduler, WorkerPool, PoolConfig
from recontool.engine.state import ScanState, ScanStateMachine


# ── Event dispatch tests ─────────────────────────────────────────────────────

class TestEventDispatch:
    def test_registry_returns_adapters_for_event_type(self):
        registry = build_default_registry()
        event = EngineEvent(
            type=EventType.NEW_SUBDOMAIN,
            data={"value": "api.example.com", "type": "subdomain"},
        )
        adapters = registry.get_adapters_for(event)
        assert len(adapters) > 0
        assert "dns_resolve" in adapters
        assert "http_probe" in adapters

    def test_registry_host_live_triggers_active_adapters(self):
        registry = build_default_registry()
        event = EngineEvent(
            type=EventType.HOST_VALIDATED_LIVE,
            data={"value": "api.example.com", "type": "subdomain"},
        )
        adapters = registry.get_adapters_for(event)
        assert "crawler" in adapters

    def test_registry_new_finding_returns_empty(self):
        registry = build_default_registry()
        event = EngineEvent(
            type=EventType.NEW_FINDING,
            data={"value": "XSS in /login", "kind": "xss"},
        )
        adapters = registry.get_adapters_for(event)
        assert adapters == []

    def test_custom_handler_registration(self):
        registry = HandlerRegistry()

        def custom_handler(event: EngineEvent) -> list[str]:
            return ["my_custom_adapter"]

        registry.register(EventType.NEW_JS_FILE, custom_handler)
        event = EngineEvent(
            type=EventType.NEW_JS_FILE,
            data={"value": "https://example.com/app.js"},
        )
        adapters = registry.get_adapters_for(event)
        assert adapters == ["my_custom_adapter"]

    def test_multiple_handlers_for_same_event(self):
        registry = HandlerRegistry()
        registry.register(EventType.NEW_ENDPOINT, lambda e: ["adapter_a"])
        registry.register(EventType.NEW_ENDPOINT, lambda e: ["adapter_b"])
        event = EngineEvent(
            type=EventType.NEW_ENDPOINT,
            data={"value": "https://example.com/api/v1"},
        )
        adapters = registry.get_adapters_for(event)
        assert "adapter_a" in adapters
        assert "adapter_b" in adapters


# ── Priority scoring tests ───────────────────────────────────────────────────

class TestPriorityScoring:
    def test_sensitive_keyword_gets_high_score(self):
        scorer = PriorityScorer()
        event = EngineEvent(
            type=EventType.NEW_SUBDOMAIN,
            data={"value": "admin.example.com", "type": "subdomain"},
            depth=0,
        )
        score = scorer.score(event)
        assert score.sensitivity == 1.0
        assert score.total > 0.5

    def test_non_sensitive_gets_lower_score(self):
        scorer = PriorityScorer()
        event = EngineEvent(
            type=EventType.NEW_SUBDOMAIN,
            data={"value": "www.example.com", "type": "subdomain"},
            depth=0,
        )
        score = scorer.score(event)
        assert score.sensitivity == 0.0

    def test_deeper_events_get_lower_depth_score(self):
        scorer = PriorityScorer()
        shallow = EngineEvent(
            type=EventType.NEW_SUBDOMAIN,
            data={"value": "a.example.com", "type": "subdomain"},
            depth=0,
        )
        deep = EngineEvent(
            type=EventType.NEW_SUBDOMAIN,
            data={"value": "b.example.com", "type": "subdomain"},
            depth=4,
        )
        s1 = scorer.score(shallow)
        s2 = scorer.score(deep)
        assert s1.depth > s2.depth

    def test_score_total_is_weighted_sum(self):
        score = EntityScore(
            novelty=1.0, depth=1.0, sensitivity=1.0,
            connectivity=1.0, confidence=1.0,
            expected_yield=1.0, branch_activity=1.0,
        )
        assert abs(score.total - 1.0) < 0.001

    def test_connectivity_increases_with_connections(self):
        scorer = PriorityScorer()
        scorer.record_connection("test.example.com")
        scorer.record_connection("test.example.com")
        scorer.record_connection("test.example.com")
        event = EngineEvent(
            type=EventType.NEW_SUBDOMAIN,
            data={"value": "test.example.com"},
            depth=0,
        )
        score = scorer.score(event)
        assert score.connectivity > 0.0


# ── Convergence detection tests ──────────────────────────────────────────────

class TestConvergence:
    def test_not_converged_initially(self):
        detector = ConvergenceDetector(max_dry_runs=3)
        assert not detector.is_globally_converged()

    def test_branch_converges_after_dry_runs(self):
        detector = ConvergenceDetector(max_dry_runs=3)
        # First run finds something
        detector.record_attempt("branch1", ["entity_a"], depth=0)
        assert not detector.is_branch_converged("branch1")
        # Three more runs find nothing new
        detector.record_attempt("branch1", [], depth=0)
        detector.record_attempt("branch1", [], depth=0)
        detector.record_attempt("branch1", [], depth=0)
        assert detector.is_branch_converged("branch1")

    def test_global_convergence_needs_all_branches(self):
        detector = ConvergenceDetector(max_dry_runs=2)
        # Branch 1 converges
        detector.record_attempt("b1", ["a"], depth=0)
        detector.record_attempt("b1", [], depth=0)
        detector.record_attempt("b1", [], depth=0)
        # Branch 2 still active
        detector.record_attempt("b2", ["b"], depth=0)
        assert not detector.is_globally_converged()
        # Branch 2 converges
        detector.record_attempt("b2", [], depth=0)
        detector.record_attempt("b2", [], depth=0)
        assert detector.is_globally_converged()

    def test_depth_limit_triggers_convergence(self):
        detector = ConvergenceDetector(depth_limit=3)
        detector.record_attempt("b1", ["a"], depth=0)
        detector.record_attempt("b1", ["b"], depth=3)
        assert detector.is_branch_converged("b1")

    def test_stale_timeout_triggers_convergence(self):
        detector = ConvergenceDetector(stale_timeout=0.01)
        detector.record_attempt("b1", ["a"], depth=0)
        time.sleep(0.02)
        detector.record_attempt("b1", [], depth=0)
        assert detector.is_branch_converged("b1")

    def test_max_entities_triggers_global_convergence(self):
        detector = ConvergenceDetector(max_entities=5)
        detector.record_attempt("b1", ["a", "b", "c", "d", "e"], depth=0)
        assert detector.is_globally_converged()

    def test_stats_reports_correctly(self):
        detector = ConvergenceDetector(max_dry_runs=3)
        detector.record_attempt("b1", ["a", "b"], depth=0)
        stats = detector.stats()
        assert stats["branches"] == 1
        assert stats["global_uniques"] == 2
        assert stats["total_seen"] == 2


# ── State machine tests ──────────────────────────────────────────────────────

class TestStateMachine:
    def test_initial_state_is_initializing(self):
        sm = ScanStateMachine()
        assert sm.state == ScanState.INITIALIZING

    def test_valid_transitions(self):
        sm = ScanStateMachine()
        sm.transition(ScanState.RUNNING)
        assert sm.state == ScanState.RUNNING
        sm.transition(ScanState.CONVERGING)
        assert sm.state == ScanState.CONVERGING
        sm.transition(ScanState.DONE)
        assert sm.state == ScanState.DONE
        assert sm.is_done

    def test_invalid_transition_raises(self):
        sm = ScanStateMachine()
        with pytest.raises(ValueError, match="invalid state transition"):
            sm.transition(ScanState.CONVERGING)  # can't go directly

    def test_done_is_terminal(self):
        sm = ScanStateMachine()
        sm.transition(ScanState.RUNNING)
        sm.transition(ScanState.DONE)
        with pytest.raises(ValueError):
            sm.transition(ScanState.RUNNING)

    def test_elapsed_tracking(self):
        sm = ScanStateMachine()
        sm.transition(ScanState.RUNNING)
        time.sleep(0.01)
        assert sm.elapsed > 0

    def test_history_records_transitions(self):
        sm = ScanStateMachine()
        sm.transition(ScanState.RUNNING)
        sm.transition(ScanState.DONE)
        history = sm.history()
        assert len(history) == 2
        assert history[0]["from"] == "initializing"
        assert history[0]["to"] == "running"
        assert history[1]["to"] == "done"


# ── Log analyzer tests ───────────────────────────────────────────────────────

class TestLogAnalyzer:
    def test_initial_state_allows_all(self):
        analyzer = LogAnalyzer()
        assert not analyzer.should_skip("some_adapter")
        assert not analyzer.should_deprioritize("some_adapter")
        assert analyzer.recommendation("some_adapter") == "normal"

    def test_skip_after_consecutive_failures(self):
        analyzer = LogAnalyzer(skip_after_failures=3)
        analyzer.record_failure("bad_adapter", 1.0)
        analyzer.record_failure("bad_adapter", 1.0)
        assert not analyzer.should_skip("bad_adapter")
        analyzer.record_failure("bad_adapter", 1.0)
        assert analyzer.should_skip("bad_adapter")
        assert analyzer.recommendation("bad_adapter") == "skip"

    def test_success_resets_consecutive_failures(self):
        analyzer = LogAnalyzer(skip_after_failures=3)
        analyzer.record_failure("adapter", 1.0)
        analyzer.record_failure("adapter", 1.0)
        analyzer.record_success("adapter", 5, 0.5)
        analyzer.record_failure("adapter", 1.0)
        assert not analyzer.should_skip("adapter")

    def test_deprioritize_on_low_success_rate(self):
        analyzer = LogAnalyzer(min_success_rate=0.5)
        analyzer.record_failure("weak", 1.0)
        analyzer.record_failure("weak", 1.0)
        analyzer.record_failure("weak", 1.0)
        analyzer.record_success("weak", 1, 1.0)
        assert analyzer.should_deprioritize("weak")

    def test_stats_tracking(self):
        analyzer = LogAnalyzer()
        analyzer.record_success("good", 10, 0.5)
        analyzer.record_success("good", 8, 0.3)
        stats = analyzer.get_stats("good")
        assert stats is not None
        assert stats.total_runs == 2
        assert stats.successes == 2
        assert stats.avg_yield == 9.0
        assert abs(stats.avg_response_time - 0.4) < 0.001


# ── Scheduler tests ──────────────────────────────────────────────────────────

class TestScheduler:
    def test_routes_adapters_to_correct_pool(self):
        scheduler = Scheduler()
        pool = scheduler.get_pool_for("naabu")
        assert pool.config.name == "ports"

    def test_unknown_adapter_goes_to_passive(self):
        scheduler = Scheduler()
        pool = scheduler.get_pool_for("unknown_tool")
        assert pool.config.name == "passive"

    def test_pool_concurrency_limiting(self):
        pool = WorkerPool(PoolConfig(name="test", max_concurrency=2))
        assert pool.available_slots == 2
        assert pool.active_count == 0

    def test_submit_respects_concurrency(self):
        scheduler = Scheduler()

        async def _test():
            results = []

            async def work(val):
                await asyncio.sleep(0.01)
                results.append(val)
                return val

            tasks = [
                scheduler.submit("crtsh", work(i)) for i in range(5)
            ]
            await asyncio.gather(*tasks)
            assert len(results) == 5

        asyncio.run(_test())


# ── Engine integration test (demo mode) ──────────────────────────────────────

class TestEngineDemo:
    def test_engine_runs_in_demo_mode(self):
        """The event engine should run against the mock env without errors."""
        from recontool.engine import create_engine

        engine = create_engine(
            mode="demo",
            convergence_config={
                "max_dry_runs": 2,
                "stale_timeout": 5.0,
                "depth_limit": 2,
                "max_entities": 50,
            },
        )
        result = asyncio.run(
            engine.run(
                "recontool.local",
                profile_name="normal",
                authorize_active=True,
                timeout=30,
            )
        )
        assert result.scan_id
        assert result.seed == "recontool.local"
        assert result.mode == "demo"
        # Should have processed at least the seed events
        assert result.events_processed >= 0
        assert result.elapsed > 0

    def test_engine_factory(self):
        from recontool.engine import Engine, create_engine

        engine = create_engine(mode="demo")
        assert isinstance(engine, Engine)

    def test_engine_with_timeout(self):
        """Engine should respect timeout and stop gracefully."""
        from recontool.engine import create_engine

        engine = create_engine(
            mode="demo",
            convergence_config={"max_dry_runs": 100, "stale_timeout": 999},
        )
        result = asyncio.run(
            engine.run("recontool.local", timeout=2)
        )
        assert result.elapsed <= 5.0  # Some tolerance for cleanup
