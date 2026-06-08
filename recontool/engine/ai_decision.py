"""AI decision layer for the event-driven engine.

Provides intelligent decision-making with LLM integration and heuristic fallback.
When an LLM is available, it advises on which adapters to run and priority
adjustments. When unavailable, pure heuristic rules drive decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from recontool.engine.events import EngineEvent, EventType
from recontool.engine.log_analyzer import LogAnalyzer


@dataclass
class Decision:
    """A decision about whether/how to process an event."""

    should_process: bool = True
    adapters_to_run: list[str] | None = None  # None = use default handler
    priority_adjustment: float = 0.0
    reason: str = ""


class AIDecisionLayer:
    """Makes intelligent decisions about event processing.

    When an AI supervisor is available, consults it for complex decisions.
    Falls back to heuristic rules otherwise.
    """

    def __init__(
        self,
        log_analyzer: LogAnalyzer,
        supervisor: Any = None,
        max_depth: int = 5,
    ) -> None:
        self.log_analyzer = log_analyzer
        self.supervisor = supervisor
        self.max_depth = max_depth

    async def decide(self, event: EngineEvent, available_adapters: list[str]) -> Decision:
        """Decide how to handle an event.

        Uses heuristic rules (fast) and optionally AI supervision for
        complex decisions.
        """
        # Always apply heuristic rules first
        decision = self._heuristic_decide(event, available_adapters)

        # If AI supervisor is available and decision is ambiguous, consult it
        if self.supervisor and decision.should_process and event.depth >= 3:
            ai_decision = await self._ai_decide(event, available_adapters)
            if ai_decision is not None:
                return ai_decision

        return decision

    def _heuristic_decide(self, event: EngineEvent, available_adapters: list[str]) -> Decision:
        """Pure heuristic decision-making (no LLM needed)."""
        # Depth limit: stop deep exploration
        if event.depth > self.max_depth:
            return Decision(
                should_process=False,
                reason=f"depth {event.depth} exceeds limit {self.max_depth}",
            )

        # Filter out adapters that should be skipped
        filtered = [
            a for a in available_adapters
            if not self.log_analyzer.should_skip(a)
        ]

        if not filtered:
            return Decision(
                should_process=False,
                reason="all candidate adapters are in skip state",
            )

        # Deprioritize adapters that are underperforming
        priority_adj = 0.0
        deprioritized = [
            a for a in filtered
            if self.log_analyzer.should_deprioritize(a)
        ]
        if len(deprioritized) == len(filtered):
            priority_adj = -0.3  # Lower priority if all adapters are weak

        return Decision(
            should_process=True,
            adapters_to_run=filtered,
            priority_adjustment=priority_adj,
            reason="heuristic",
        )

    async def _ai_decide(self, event: EngineEvent, available_adapters: list[str]) -> Decision | None:
        """Consult AI supervisor for decision (returns None if AI unavailable)."""
        if not self.supervisor or not hasattr(self.supervisor, "plan_phase"):
            return None

        try:
            # Ask supervisor which adapters to keep for this event
            keep = await self.supervisor.plan_phase(
                f"event_{event.type.value}",
                available_adapters,
                event.data.get("scan_id", ""),
            )
            if keep is not None:
                return Decision(
                    should_process=True,
                    adapters_to_run=list(keep),
                    reason="ai_supervisor",
                )
        except Exception:  # noqa: BLE001
            pass
        return None
