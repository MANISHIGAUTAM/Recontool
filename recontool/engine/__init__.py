"""Event-driven graph expansion engine.

Replaces the phased pipeline with a continuous event-driven loop where every
discovery immediately triggers downstream actions. No phases. No waiting.

Usage:
    from recontool.engine import Engine, create_engine

    engine = create_engine(mode="demo")
    result = await engine.run("example.com", authorize_active=True)
"""
from __future__ import annotations

from typing import Any

from recontool.core.mode import RunMode
from recontool.engine.core import EngineResult, EventDrivenEngine

# Public alias
Engine = EventDrivenEngine


def create_engine(
    *,
    mode: str | RunMode | None = None,
    supervisor: Any = None,
    mock_env: Any = None,
    convergence_config: dict[str, Any] | None = None,
) -> EventDrivenEngine:
    """Factory function to create an event-driven engine instance.

    Args:
        mode: Run mode (demo/test/live). Defaults to config setting.
        supervisor: Optional AI supervisor for intelligent decisions.
        mock_env: Optional mock environment for demo/test modes.
        convergence_config: Override convergence detection parameters.

    Returns:
        Configured EventDrivenEngine ready to run.
    """
    if isinstance(mode, str):
        run_mode = RunMode.parse(mode)
    elif isinstance(mode, RunMode):
        run_mode = mode
    else:
        run_mode = None

    return EventDrivenEngine(
        supervisor=supervisor,
        mode=run_mode,
        mock_env=mock_env,
        convergence_config=convergence_config,
    )


__all__ = [
    "Engine",
    "EventDrivenEngine",
    "EngineResult",
    "create_engine",
]
