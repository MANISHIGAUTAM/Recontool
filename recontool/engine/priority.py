"""Entity scoring for prioritization in the event-driven engine.

Each entity (event) gets a composite score based on multiple signals:
  - novelty: how recently discovered (newer = higher)
  - depth: how deep in the discovery chain (shallower = higher)
  - sensitivity: keywords indicating high-value targets
  - connectivity: how many other entities link to it
  - confidence: source confidence from the normalizer
  - expected_yield: predicted adapter output volume
  - branch_activity: how active this branch of exploration is
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from recontool.engine.events import EngineEvent

# Keywords that indicate high-value targets
_SENSITIVE_KEYWORDS = frozenset({
    "admin", "api", "auth", "login", "internal", "staging", "dev", "test",
    "jenkins", "git", "vpn", "dashboard", "upload", "debug", "backup",
    "secret", "token", "config", "env", "private", "key", "password",
})


@dataclass
class EntityScore:
    """Composite priority score for an event/entity."""

    novelty: float = 0.0
    depth: float = 0.0
    sensitivity: float = 0.0
    connectivity: float = 0.0
    confidence: float = 0.0
    expected_yield: float = 0.0
    branch_activity: float = 0.0

    @property
    def total(self) -> float:
        """Weighted composite score (higher = process first)."""
        return (
            self.novelty * 0.20
            + self.depth * 0.15
            + self.sensitivity * 0.25
            + self.connectivity * 0.10
            + self.confidence * 0.10
            + self.expected_yield * 0.10
            + self.branch_activity * 0.10
        )


class PriorityScorer:
    """Scores events to determine processing order in the priority queue."""

    def __init__(self) -> None:
        self._discovery_times: dict[str, float] = {}
        self._connections: dict[str, int] = {}
        self._branch_counts: dict[str, int] = {}

    def score(self, event: EngineEvent) -> EntityScore:
        """Compute the priority score for an event."""
        now = time.time()
        value = event.value.lower()

        # Novelty: exponential decay from discovery time
        first_seen = self._discovery_times.get(value, now)
        if value not in self._discovery_times:
            self._discovery_times[value] = now
        age_seconds = now - first_seen
        novelty = max(0.0, 1.0 - (age_seconds / 3600.0))  # decays over 1 hour

        # Depth: shallower is better (inverse relationship)
        depth_score = max(0.0, 1.0 - (event.depth * 0.2))

        # Sensitivity: check for high-value keywords
        sensitivity = 0.0
        for kw in _SENSITIVE_KEYWORDS:
            if kw in value:
                sensitivity = 1.0
                break

        # Connectivity: how many relationships this entity has
        conn_count = self._connections.get(value, 0)
        connectivity = min(1.0, conn_count / 10.0)

        # Confidence: from source data
        confidence = event.data.get("confidence", 0.5)

        # Expected yield: based on event type
        yield_map = {
            "new_subdomain": 0.8,
            "host_validated_live": 0.9,
            "new_js_file": 0.7,
            "new_endpoint": 0.5,
            "new_port": 0.6,
            "archive_url_found": 0.4,
            "cert_san_discovered": 0.7,
            "form_discovered": 0.3,
            "new_finding": 0.1,
        }
        expected_yield = yield_map.get(event.type.value, 0.5)

        # Branch activity: how active this branch is
        branch = event.branch_id or "root"
        self._branch_counts[branch] = self._branch_counts.get(branch, 0) + 1
        # More active branches get slightly lower priority (spread exploration)
        branch_activity = max(0.0, 1.0 - (self._branch_counts[branch] / 100.0))

        return EntityScore(
            novelty=novelty,
            depth=depth_score,
            sensitivity=sensitivity,
            connectivity=connectivity,
            confidence=confidence,
            expected_yield=expected_yield,
            branch_activity=branch_activity,
        )

    def record_connection(self, entity: str) -> None:
        """Record a new connection for an entity (increases its connectivity score)."""
        entity = entity.lower()
        self._connections[entity] = self._connections.get(entity, 0) + 1
