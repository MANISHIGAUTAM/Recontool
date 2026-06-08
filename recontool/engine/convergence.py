"""Per-branch intelligent stopping for the event-driven engine.

The convergence detector monitors discovery rates per exploration branch and
signals when further exploration is unlikely to yield new unique results.

Stopping criteria:
  - No new unique entities after N consecutive adapter runs
  - Time since last unique discovery exceeds threshold
  - Depth limit reached for the branch
  - Global entity count exceeds maximum
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class BranchState:
    """Tracks convergence metrics for a single exploration branch."""

    branch_id: str
    total_attempts: int = 0
    unique_count: int = 0
    consecutive_no_new: int = 0
    last_unique_time: float = field(default_factory=time.time)
    max_depth_seen: int = 0


class ConvergenceDetector:
    """Monitors per-branch discovery rates and signals when to stop.

    A branch is considered converged when:
      - consecutive_no_new >= max_dry_runs (default 10), OR
      - time since last unique > stale_timeout (default 120s), OR
      - depth exceeds depth_limit (default 5)

    The global scan converges when ALL active branches are converged.
    """

    def __init__(
        self,
        max_dry_runs: int = 10,
        stale_timeout: float = 120.0,
        depth_limit: int = 5,
        max_entities: int = 10000,
    ) -> None:
        self.max_dry_runs = max_dry_runs
        self.stale_timeout = stale_timeout
        self.depth_limit = depth_limit
        self.max_entities = max_entities
        self._branches: dict[str, BranchState] = {}
        self._seen_entities: set[str] = set()
        self._global_unique_count: int = 0

    def _get_branch(self, branch_id: str) -> BranchState:
        if branch_id not in self._branches:
            self._branches[branch_id] = BranchState(branch_id=branch_id)
        return self._branches[branch_id]

    def record_attempt(self, branch_id: str, entities: list[str], depth: int = 0) -> None:
        """Record an adapter run and its discovered entities.

        Args:
            branch_id: Identifier for the exploration branch.
            entities: List of entity dedupe keys discovered in this run.
            depth: Current depth of exploration for this branch.
        """
        branch = self._get_branch(branch_id)
        branch.total_attempts += 1
        branch.max_depth_seen = max(branch.max_depth_seen, depth)

        new_entities = [e for e in entities if e not in self._seen_entities]
        if new_entities:
            branch.consecutive_no_new = 0
            branch.last_unique_time = time.time()
            branch.unique_count += len(new_entities)
            self._global_unique_count += len(new_entities)
            self._seen_entities.update(new_entities)
        else:
            branch.consecutive_no_new += 1

    def is_branch_converged(self, branch_id: str) -> bool:
        """Check if a specific branch has converged."""
        branch = self._get_branch(branch_id)

        # Not enough attempts to judge
        if branch.total_attempts < 2:
            return False

        # Too many consecutive runs without new results
        if branch.consecutive_no_new >= self.max_dry_runs:
            return True

        # Too long since last unique discovery
        if time.time() - branch.last_unique_time > self.stale_timeout:
            return True

        # Depth limit exceeded
        if branch.max_depth_seen >= self.depth_limit:
            return True

        return False

    def is_globally_converged(self) -> bool:
        """Check if ALL branches have converged (scan should stop)."""
        # Entity count limit
        if self._global_unique_count >= self.max_entities:
            return True

        # No branches yet means we haven't started
        if not self._branches:
            return False

        # All branches must be converged
        return all(
            self.is_branch_converged(bid)
            for bid in self._branches
        )

    def stats(self) -> dict:
        """Return convergence statistics."""
        return {
            "branches": len(self._branches),
            "global_uniques": self._global_unique_count,
            "converged_branches": sum(
                1 for bid in self._branches
                if self.is_branch_converged(bid)
            ),
            "total_seen": len(self._seen_entities),
        }
