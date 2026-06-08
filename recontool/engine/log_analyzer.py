"""Adapter performance tracking for the event-driven engine.

Tracks per-adapter metrics (success rate, yield, response time) and provides
signals to deprioritize or skip adapters that are consistently failing or
producing no results.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class AdapterStats:
    """Performance metrics for a single adapter."""

    name: str
    total_runs: int = 0
    successes: int = 0
    failures: int = 0
    total_events_produced: int = 0
    total_response_time: float = 0.0
    last_run_time: float = 0.0
    consecutive_failures: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_runs == 0:
            return 1.0
        return self.successes / self.total_runs

    @property
    def avg_yield(self) -> float:
        if self.successes == 0:
            return 0.0
        return self.total_events_produced / self.successes

    @property
    def avg_response_time(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.total_response_time / self.total_runs


class LogAnalyzer:
    """Tracks adapter performance and recommends skip/deprioritize decisions.

    Adapters are marked as:
      - "skip" if they have > 3 consecutive failures
      - "deprioritize" if success_rate < 0.3 or avg_yield < 0.5
      - "normal" otherwise
    """

    def __init__(
        self,
        skip_after_failures: int = 3,
        min_success_rate: float = 0.3,
        min_avg_yield: float = 0.5,
    ) -> None:
        self.skip_after_failures = skip_after_failures
        self.min_success_rate = min_success_rate
        self.min_avg_yield = min_avg_yield
        self._stats: dict[str, AdapterStats] = {}

    def _get_stats(self, adapter_name: str) -> AdapterStats:
        if adapter_name not in self._stats:
            self._stats[adapter_name] = AdapterStats(name=adapter_name)
        return self._stats[adapter_name]

    def record_success(
        self, adapter_name: str, events_produced: int, duration: float
    ) -> None:
        """Record a successful adapter run."""
        stats = self._get_stats(adapter_name)
        stats.total_runs += 1
        stats.successes += 1
        stats.total_events_produced += events_produced
        stats.total_response_time += duration
        stats.last_run_time = time.time()
        stats.consecutive_failures = 0

    def record_failure(self, adapter_name: str, duration: float) -> None:
        """Record a failed adapter run."""
        stats = self._get_stats(adapter_name)
        stats.total_runs += 1
        stats.failures += 1
        stats.total_response_time += duration
        stats.last_run_time = time.time()
        stats.consecutive_failures += 1

    def should_skip(self, adapter_name: str) -> bool:
        """Should this adapter be skipped entirely?"""
        stats = self._stats.get(adapter_name)
        if stats is None:
            return False
        return stats.consecutive_failures >= self.skip_after_failures

    def should_deprioritize(self, adapter_name: str) -> bool:
        """Should this adapter be deprioritized (run later/less often)?"""
        stats = self._stats.get(adapter_name)
        if stats is None:
            return False
        if stats.total_runs < 3:
            return False  # Not enough data
        if stats.success_rate < self.min_success_rate:
            return True
        if stats.avg_yield < self.min_avg_yield:
            return True
        return False

    def recommendation(self, adapter_name: str) -> str:
        """Get recommendation for an adapter: 'skip', 'deprioritize', or 'normal'."""
        if self.should_skip(adapter_name):
            return "skip"
        if self.should_deprioritize(adapter_name):
            return "deprioritize"
        return "normal"

    def get_stats(self, adapter_name: str) -> AdapterStats | None:
        """Get stats for an adapter (None if never run)."""
        return self._stats.get(adapter_name)

    def all_stats(self) -> dict[str, AdapterStats]:
        """Get all adapter stats."""
        return dict(self._stats)
