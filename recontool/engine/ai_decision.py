"""AI decisioning layer for the event-driven engine.

Classifies tool output entities and recommends actions (persist, discard,
trigger downstream, rescan, manual review). The default implementation uses
deterministic heuristics with no AI calls. An AI-augmented path can override
individual methods via the existing Supervisor/ModelRouter pattern.

IMPORTANT: AI only classifies/recommends - it does NOT run tools.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from recontool.adapters.base import Event
from recontool.engine.output import NormalizedOutput


@dataclass
class DecisionResult:
    """Outcome of AI decisioning on a set of entities."""

    persist: list[Event] = field(default_factory=list)
    discard: list[Event] = field(default_factory=list)
    trigger_downstream: list[str] = field(default_factory=list)
    rescan_tools: list[str] = field(default_factory=list)
    manual_review: list[Event] = field(default_factory=list)
    reasoning: str = ""


class AIDecisionService:
    """Heuristic-based decisioning service for entity classification.

    All methods are designed to be overridden or mocked for testing.
    The default implementation uses simple rules without AI API calls.
    """

    # Noise patterns: entities matching these are considered noise
    NOISE_PATTERNS: list[str] = [
        "localhost",
        "127.0.0.1",
        "::1",
        "example.com",
        "example.org",
        "example.net",
        "invalid",
        "test.invalid",
    ]

    # Entity types that always trigger downstream processing
    DOWNSTREAM_TRIGGERS: set[str] = {"subdomain", "ip", "domain"}

    def classify_results(self, normalized_output: NormalizedOutput) -> DecisionResult:
        """Classify all entities in a normalized output into action buckets.

        Uses heuristics to decide which entities to persist, discard,
        trigger downstream tools for, or flag for manual review.
        """
        persist: list[Event] = []
        discard: list[Event] = []
        trigger_downstream: list[str] = []
        manual_review: list[Event] = []

        for entity in normalized_output.discovered_entities:
            if self.is_noise(entity):
                discard.append(entity)
            elif self.needs_manual_review(entity):
                manual_review.append(entity)
                persist.append(entity)
            else:
                persist.append(entity)
                if self.should_trigger_downstream(entity):
                    value = entity.data.get("value", "")
                    if value and value not in trigger_downstream:
                        trigger_downstream.append(value)

        # Determine rescan needs based on confidence
        rescan_tools: list[str] = []
        tool_name = normalized_output.metadata.get("tool_name", "")
        if tool_name and self.should_rescan(
            tool_name, {"confidence": normalized_output.confidence_score}
        ):
            rescan_tools.append(tool_name)

        reasoning = self._build_reasoning(
            persist, discard, trigger_downstream, rescan_tools, manual_review
        )

        return DecisionResult(
            persist=persist,
            discard=discard,
            trigger_downstream=trigger_downstream,
            rescan_tools=rescan_tools,
            manual_review=manual_review,
            reasoning=reasoning,
        )

    def should_persist(self, entity: Event) -> bool:
        """Determine if an entity should be persisted to the database."""
        return not self.is_noise(entity)

    def is_noise(self, entity: Event) -> bool:
        """Determine if an entity is noise (should be discarded).

        Checks against known noise patterns like localhost, example.com, etc.
        """
        value = entity.data.get("value", "").lower()
        if not value:
            return False
        for pattern in self.NOISE_PATTERNS:
            if value == pattern or value.endswith(f".{pattern}"):
                return True
        return False

    def should_trigger_downstream(self, entity: Event) -> bool:
        """Determine if an entity should trigger downstream tool execution."""
        entity_type = entity.data.get("type", "")
        return entity_type in self.DOWNSTREAM_TRIGGERS

    def are_pending_keys_fulfilled(self, keys: list[str]) -> list[str]:
        """Check which pending keys from the list are considered fulfilled.

        Returns the subset of keys that are fulfilled based on heuristics.
        Default: all non-empty keys are considered fulfilled.
        """
        return [k for k in keys if k and k.strip()]

    def should_rescan(self, tool_name: str, context: dict[str, Any]) -> bool:
        """Determine if a tool should be rescanned.

        Default heuristic: rescan if confidence is below threshold.
        """
        confidence = context.get("confidence", 1.0)
        return confidence < 0.5

    def needs_manual_review(self, entity: Event) -> bool:
        """Determine if an entity needs manual review.

        Default heuristic: findings always need review; low-confidence
        entities with unusual attributes need review.
        """
        if entity.entity == "finding":
            return True
        return False

    def _build_reasoning(
        self,
        persist: list[Event],
        discard: list[Event],
        trigger_downstream: list[str],
        rescan_tools: list[str],
        manual_review: list[Event],
    ) -> str:
        """Build a human-readable reasoning string for the decision."""
        parts: list[str] = []
        if persist:
            parts.append(f"Persisting {len(persist)} entities")
        if discard:
            parts.append(f"Discarding {len(discard)} noise entities")
        if trigger_downstream:
            parts.append(
                f"Triggering downstream for {len(trigger_downstream)} values"
            )
        if rescan_tools:
            parts.append(f"Recommending rescan for: {', '.join(rescan_tools)}")
        if manual_review:
            parts.append(f"Flagging {len(manual_review)} for manual review")
        return "; ".join(parts) if parts else "No entities to classify"
