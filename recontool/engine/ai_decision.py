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

    Pass ``scope`` (a ``core.scope.Scope``) so the service is scope-aware: an
    asset that is inside the scan's authorized scope is NEVER classified as
    noise, even if it matches a generic noise pattern. Without this, scanning a
    reserved documentation domain (e.g. example.com itself) would see all of its
    own in-scope subdomains discarded and recursion would dead-end.
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

    def __init__(self, scope: Any | None = None) -> None:
        self._scope = scope

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

        Scope wins: an asset inside the authorized scan scope is never noise.
        Otherwise checks against known noise patterns (localhost, example.com…).
        """
        value = entity.data.get("value", "").lower()
        if not value:
            return False
        # In-scope assets are authoritative — never drop the target's own estate.
        if self._scope is not None and entity.entity == "asset":
            atype = entity.data.get("type", "")
            try:
                if atype and self._scope.contains(atype, entity.data.get("value", "")):
                    return False
            except Exception:  # noqa: BLE001 — defensive: scope check never blocks
                pass
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


def discarded_asset_pairs(decision: "DecisionResult") -> set[tuple[str, str]]:
    """The (entity_type, value) pairs the decision marked as noise to drop.

    Used by the execution paths to keep a discarded asset out of the recursion
    re-feed: a tool may still have produced it, but AI decisioning said it is
    noise, so it must not spawn downstream work.
    """
    pairs: set[tuple[str, str]] = set()
    for ev in decision.discard:
        if ev.entity == "asset":
            t, v = ev.data.get("type"), ev.data.get("value")
            if t and v:
                pairs.add((t, v))
    return pairs


def decide_on_events(
    events: list[Event],
    tool_name: str,
    *,
    service: AIDecisionService | None = None,
    confidence: float = 1.0,
) -> DecisionResult:
    """Run AI decisioning over one tool's output events.

    The single entry point both engine execution paths use so the heuristic (or
    an AI-augmented override) is applied uniformly. Wraps the raw adapter events
    in a NormalizedOutput and classifies them into persist/discard/trigger
    buckets. Returns the DecisionResult; the caller logs it and acts on it.
    """
    svc = service or AIDecisionService()
    normalized = NormalizedOutput(
        discovered_entities=list(events),
        confidence_score=confidence,
        metadata={"tool_name": tool_name},
    )
    return svc.classify_results(normalized)


# The §11 decisioning prompt: AI classifies/prioritizes, never executes or invents.
AI_DECISION_SYSTEM = (
    "You are the decisioning layer for a recursive reconnaissance platform. "
    "You do NOT execute tools, schedule jobs, or invent data. Given the entities "
    "one tool just produced, classify which are NOISE (placeholder, junk, clearly "
    "out-of-target) versus SIGNAL, and which deserve priority follow-up. Rules: "
    "only classify the entities provided — never add new ones; prefer keeping when "
    "unsure; an entity that is clearly the target's own asset is always SIGNAL. "
    'Return ONLY compact JSON: {"drop":[values],"priority":[values],"reason":"..."} '
    'where "drop" lists entity VALUES that are noise and must not spawn follow-up work.'
)


def _asset_entities(events: list[Event]) -> list[dict]:
    """Compact [{type,value}] of asset events — the only thing the model sees."""
    out: list[dict] = []
    for ev in events:
        if ev.entity == "asset":
            t, v = ev.data.get("type"), ev.data.get("value")
            if t and v:
                out.append({"type": t, "value": v})
    return out


async def decide_on_events_ai(
    events: list[Event],
    tool_name: str,
    *,
    service: AIDecisionService | None = None,
    router: Any | None = None,
    confidence: float = 1.0,
) -> DecisionResult:
    """Model-augmented decisioning with a deterministic heuristic floor.

    Computes the heuristic decision first, then — only if a ``ModelRouter`` is
    enabled and within its per-scan call budget — asks the model to flag noise
    among the SAME entities (it can never add entities). A model-flagged value is
    moved to ``discard`` ONLY when it is not in the authorized scope (the
    scope-safety floor), so the model can prune noise but never drops the target's
    own estate. Falls back to the pure heuristic when the model is absent, over
    budget, or returns junk — so behavior is deterministic without an API key.
    """
    svc = service or AIDecisionService()
    base = decide_on_events(events, tool_name, service=svc, confidence=confidence)
    if router is None or not getattr(router, "enabled", False) or not events:
        return base
    assets = _asset_entities(events)
    if not assets:
        return base
    resp = await router.decide_json(
        AI_DECISION_SYSTEM, {"tool": tool_name, "entities": assets[:60]},
        tier="light", max_tokens=300,
    )
    if not resp or not isinstance(resp.get("drop"), list):
        return base  # unavailable / over-budget / malformed -> heuristic floor
    drop_vals = {str(v).strip().lower() for v in resp["drop"] if str(v).strip()}
    if not drop_vals:
        return base
    scope = getattr(svc, "_scope", None)
    keep: list[Event] = []
    discard: list[Event] = list(base.discard)
    for ev in base.persist:
        value = str(ev.data.get("value", "")).strip().lower()
        atype = ev.data.get("type", "")
        in_scope = False
        if scope is not None and ev.entity == "asset" and atype:
            try:
                in_scope = bool(scope.contains(atype, ev.data.get("value", "")))
            except Exception:  # noqa: BLE001 — scope check never blocks a decision
                in_scope = False
        if ev.entity == "asset" and value in drop_vals and not in_scope:
            discard.append(ev)          # model says noise + not in scope -> drop
        else:
            keep.append(ev)             # scope floor / non-asset / kept by model
    reason = f"{base.reasoning} | AI(model): {str(resp.get('reason', '')).strip()}"[:300]
    return DecisionResult(
        persist=keep, discard=discard, trigger_downstream=base.trigger_downstream,
        rescan_tools=base.rescan_tools, manual_review=base.manual_review,
        reasoning=reason,
    )
