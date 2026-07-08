"""Unit tests for the AI decisioning layer.

Covers: heuristic classification, noise filtering, downstream trigger logic,
mockability of the AI interface.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from recontool.adapters.base import Event
from recontool.engine.ai_decision import AIDecisionService, DecisionResult
from recontool.engine.output import NormalizedOutput


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def service():
    return AIDecisionService()


@pytest.fixture()
def sample_output():
    """NormalizedOutput with a mix of real and noise entities."""
    entities = [
        Event.asset("crtsh", "subdomain", "api.target.com"),
        Event.asset("crtsh", "subdomain", "mail.target.com"),
        Event.asset("crtsh", "subdomain", "localhost"),
        Event.asset("crtsh", "ip", "192.168.1.1"),
        Event.finding("crtsh", "cert_expired", "Expired certificate on api.target.com"),
    ]
    return NormalizedOutput(
        stdout="",
        discovered_entities=entities,
        confidence_score=0.9,
        metadata={"tool_name": "crtsh"},
    )


@pytest.fixture()
def low_confidence_output():
    """NormalizedOutput with low confidence (should trigger rescan)."""
    entities = [
        Event.asset("tool_x", "subdomain", "test.target.com"),
    ]
    return NormalizedOutput(
        stdout="",
        discovered_entities=entities,
        confidence_score=0.3,
        metadata={"tool_name": "tool_x"},
    )


# ---------------------------------------------------------------------------
# Heuristic classification tests
# ---------------------------------------------------------------------------


class TestClassifyResults:
    def test_basic_classification(self, service, sample_output):
        result = service.classify_results(sample_output)
        assert isinstance(result, DecisionResult)
        # localhost should be discarded
        assert len(result.discard) == 1
        assert result.discard[0].data["value"] == "localhost"
        # Non-noise entities should be persisted
        assert len(result.persist) >= 3

    def test_findings_flagged_for_review(self, service, sample_output):
        result = service.classify_results(sample_output)
        assert len(result.manual_review) == 1
        assert result.manual_review[0].entity == "finding"

    def test_downstream_triggers_for_subdomains(self, service, sample_output):
        result = service.classify_results(sample_output)
        # subdomain and ip types should trigger downstream
        assert "api.target.com" in result.trigger_downstream
        assert "mail.target.com" in result.trigger_downstream

    def test_no_rescan_for_high_confidence(self, service, sample_output):
        result = service.classify_results(sample_output)
        assert result.rescan_tools == []

    def test_rescan_for_low_confidence(self, service, low_confidence_output):
        result = service.classify_results(low_confidence_output)
        assert "tool_x" in result.rescan_tools

    def test_reasoning_populated(self, service, sample_output):
        result = service.classify_results(sample_output)
        assert result.reasoning
        assert "Persisting" in result.reasoning

    def test_empty_output(self, service):
        empty = NormalizedOutput(metadata={"tool_name": "empty_tool"})
        result = service.classify_results(empty)
        assert result.persist == []
        assert result.discard == []
        assert result.trigger_downstream == []
        assert result.reasoning == "No entities to classify"


# ---------------------------------------------------------------------------
# Noise filtering tests
# ---------------------------------------------------------------------------


class TestNoiseFiltering:
    def test_localhost_is_noise(self, service):
        e = Event.asset("tool", "ip", "localhost")
        assert service.is_noise(e) is True

    def test_loopback_is_noise(self, service):
        e = Event.asset("tool", "ip", "127.0.0.1")
        assert service.is_noise(e) is True

    def test_example_com_is_noise(self, service):
        e = Event.asset("tool", "subdomain", "example.com")
        assert service.is_noise(e) is True

    def test_subdomain_of_example_is_noise(self, service):
        e = Event.asset("tool", "subdomain", "sub.example.com")
        assert service.is_noise(e) is True

    def test_real_domain_not_noise(self, service):
        e = Event.asset("tool", "subdomain", "api.realsite.com")
        assert service.is_noise(e) is False

    def test_empty_value_not_noise(self, service):
        e = Event.asset("tool", "subdomain", "")
        assert service.is_noise(e) is False

    def test_ipv6_loopback_is_noise(self, service):
        e = Event.asset("tool", "ip", "::1")
        assert service.is_noise(e) is True


# ---------------------------------------------------------------------------
# Downstream trigger logic tests
# ---------------------------------------------------------------------------


class TestDownstreamTrigger:
    def test_subdomain_triggers_downstream(self, service):
        e = Event.asset("tool", "subdomain", "api.target.com")
        assert service.should_trigger_downstream(e) is True

    def test_ip_triggers_downstream(self, service):
        e = Event.asset("tool", "ip", "10.0.0.1")
        assert service.should_trigger_downstream(e) is True

    def test_domain_triggers_downstream(self, service):
        e = Event.asset("tool", "domain", "target.com")
        assert service.should_trigger_downstream(e) is True

    def test_endpoint_no_downstream(self, service):
        e = Event.endpoint("tool", "https://target.com/path")
        assert service.should_trigger_downstream(e) is False

    def test_service_no_downstream(self, service):
        e = Event.service("tool", "target.com", 443)
        assert service.should_trigger_downstream(e) is False


# ---------------------------------------------------------------------------
# Persistence decision tests
# ---------------------------------------------------------------------------


class TestShouldPersist:
    def test_non_noise_persisted(self, service):
        e = Event.asset("tool", "subdomain", "real.target.com")
        assert service.should_persist(e) is True

    def test_noise_not_persisted(self, service):
        e = Event.asset("tool", "subdomain", "localhost")
        assert service.should_persist(e) is False


# ---------------------------------------------------------------------------
# Pending keys fulfillment
# ---------------------------------------------------------------------------


class TestPendingKeysFulfilled:
    def test_non_empty_keys_fulfilled(self, service):
        keys = ["subdomain:api.target.com", "ip:10.0.0.1"]
        result = service.are_pending_keys_fulfilled(keys)
        assert result == keys

    def test_empty_keys_filtered(self, service):
        keys = ["subdomain:api.target.com", "", "  "]
        result = service.are_pending_keys_fulfilled(keys)
        assert result == ["subdomain:api.target.com"]

    def test_empty_list(self, service):
        assert service.are_pending_keys_fulfilled([]) == []


# ---------------------------------------------------------------------------
# Rescan logic
# ---------------------------------------------------------------------------


class TestShouldRescan:
    def test_rescan_low_confidence(self, service):
        assert service.should_rescan("tool", {"confidence": 0.3}) is True

    def test_no_rescan_high_confidence(self, service):
        assert service.should_rescan("tool", {"confidence": 0.9}) is False

    def test_threshold_boundary(self, service):
        assert service.should_rescan("tool", {"confidence": 0.5}) is False
        assert service.should_rescan("tool", {"confidence": 0.49}) is True


# ---------------------------------------------------------------------------
# Manual review
# ---------------------------------------------------------------------------


class TestNeedsManualReview:
    def test_findings_need_review(self, service):
        e = Event.finding("tool", "vuln", "SQL Injection")
        assert service.needs_manual_review(e) is True

    def test_assets_no_review(self, service):
        e = Event.asset("tool", "subdomain", "api.target.com")
        assert service.needs_manual_review(e) is False


# ---------------------------------------------------------------------------
# Mockability tests
# ---------------------------------------------------------------------------


class TestMockability:
    def test_mock_is_noise(self):
        """Verify the service interface can be mocked."""
        service = AIDecisionService()
        service.is_noise = MagicMock(return_value=True)
        e = Event.asset("tool", "subdomain", "real.domain.com")
        assert service.is_noise(e) is True
        service.is_noise.assert_called_once_with(e)

    def test_mock_classify_results(self):
        """Verify classify_results can be mocked entirely."""
        service = AIDecisionService()
        mock_result = DecisionResult(reasoning="mocked")
        service.classify_results = MagicMock(return_value=mock_result)
        output = NormalizedOutput()
        result = service.classify_results(output)
        assert result.reasoning == "mocked"

    def test_subclass_override(self):
        """Verify the interface can be subclassed for custom AI logic."""

        class CustomAI(AIDecisionService):
            def is_noise(self, entity: Event) -> bool:
                # Custom logic: everything with 'test' is noise
                return "test" in entity.data.get("value", "")

        custom = CustomAI()
        e1 = Event.asset("tool", "subdomain", "test.target.com")
        e2 = Event.asset("tool", "subdomain", "api.target.com")
        assert custom.is_noise(e1) is True
        assert custom.is_noise(e2) is False
