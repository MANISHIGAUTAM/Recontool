"""Scan state machine for the event-driven engine.

States:
  - INITIALIZING: setting up scope, loading adapters, seeding the queue
  - RUNNING: actively processing events and dispatching adapters
  - CONVERGING: still processing but convergence signals indicate slowdown
  - DONE: all branches converged or limits reached, scan complete
"""
from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field


class ScanState(str, enum.Enum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    CONVERGING = "converging"
    DONE = "done"


@dataclass
class ScanStateMachine:
    """Manages state transitions for an event-driven scan."""

    state: ScanState = ScanState.INITIALIZING
    started_at: float = 0.0
    finished_at: float = 0.0
    _transitions: list[tuple[ScanState, ScanState, float]] = field(
        default_factory=list
    )

    def transition(self, new_state: ScanState) -> None:
        """Transition to a new state (validates the transition is legal)."""
        valid_transitions = {
            ScanState.INITIALIZING: {ScanState.RUNNING, ScanState.DONE},
            ScanState.RUNNING: {ScanState.CONVERGING, ScanState.DONE},
            ScanState.CONVERGING: {ScanState.RUNNING, ScanState.DONE},
            ScanState.DONE: set(),  # terminal
        }

        allowed = valid_transitions.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(
                f"invalid state transition: {self.state.value} -> {new_state.value}"
            )

        now = time.time()
        self._transitions.append((self.state, new_state, now))
        self.state = new_state

        if new_state == ScanState.RUNNING and self.started_at == 0.0:
            self.started_at = now
        elif new_state == ScanState.DONE:
            self.finished_at = now

    @property
    def is_active(self) -> bool:
        """True if the scan is still processing events."""
        return self.state in (ScanState.RUNNING, ScanState.CONVERGING)

    @property
    def is_done(self) -> bool:
        return self.state == ScanState.DONE

    @property
    def elapsed(self) -> float:
        if self.started_at == 0.0:
            return 0.0
        end = self.finished_at if self.finished_at > 0 else time.time()
        return end - self.started_at

    def history(self) -> list[dict]:
        """Return state transition history."""
        return [
            {"from": f.value, "to": t.value, "at": ts}
            for f, t, ts in self._transitions
        ]
