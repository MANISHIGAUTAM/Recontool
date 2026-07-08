"""Incremental scan logic for the event-driven engine.

Tracks tool execution history and determines when re-execution is needed
based on: input changes, config changes, version changes, and staleness.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from recontool.engine.fingerprint import fingerprint_config, fingerprint_inputs, has_changed
from recontool.engine.models import ToolRun
from recontool.engine.registry import ToolSpec


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _age_seconds(finished: dt.datetime) -> float:
    """Seconds since ``finished``, tolerant of naive timestamps (SQLite returns
    tz-naive datetimes even for tz-aware columns)."""
    now = _now()
    if finished.tzinfo is None:
        now = now.replace(tzinfo=None)
    return (now - finished).total_seconds()


class IncrementalEngine:
    """Determines whether a tool needs to re-run based on state changes.

    Uses a SQLAlchemy session to query/persist ToolRun records.
    """

    def __init__(self, session) -> None:  # noqa: ANN001
        self._session = session

    def should_rerun(
        self,
        tool_name: str,
        scan_id: str,
        current_inputs: dict[str, Any],
        tool_spec: Optional[ToolSpec] = None,
        max_age_seconds: int = 3600,
    ) -> bool:
        """Determine if a tool should re-run.

        A tool should re-run if:
        - It has never run in this scan
        - Its input fingerprint has changed
        - Its config fingerprint has changed (if tool_spec provided)
        - It has exceeded the staleness threshold
        - Its previous run failed
        """
        last_run = self.get_last_run(tool_name, scan_id)
        if last_run is None:
            return True

        # Failed runs should always be retried
        if last_run.status == "failed":
            return True

        # Check input fingerprint change
        new_input_fp = fingerprint_inputs(tool_name, current_inputs)
        if last_run.input_fingerprint and has_changed(last_run.input_fingerprint, new_input_fp):
            return True

        # Check config fingerprint change (if we have a spec)
        if tool_spec is not None and last_run.config_fingerprint:
            new_config_fp = fingerprint_config(tool_spec)
            if has_changed(last_run.config_fingerprint, new_config_fp):
                return True

        # Check staleness
        if last_run.finished_at:
            if _age_seconds(last_run.finished_at) > max_age_seconds:
                return True

        return False

    def record_run(self, tool_run: ToolRun) -> None:
        """Persist a tool run record to the database."""
        self._session.add(tool_run)
        self._session.flush()

    def find_fresh_completed(
        self,
        tool_name: str,
        input_fingerprint: str,
        *,
        max_age_seconds: int = 604800,
        exclude_scan: Optional[str] = None,
    ) -> Optional[ToolRun]:
        """Most recent COMPLETED run of (tool, exact input fingerprint), fresh
        enough to reuse. Cross-scan by default (delta-only reruns): a re-scan can
        skip a tool whose input is byte-identical to one already run recently in
        any scan. Pass ``exclude_scan`` to ignore the current scan's own runs.
        Returns None if none qualify (caller then executes normally).
        """
        q = self._session.query(ToolRun).filter_by(
            tool_name=tool_name, input_fingerprint=input_fingerprint, status="completed"
        )
        if exclude_scan is not None:
            q = q.filter(ToolRun.scan_id != exclude_scan)
        run = q.order_by(ToolRun.id.desc()).first()
        if run is None:
            return None
        if run.finished_at is not None:
            if _age_seconds(run.finished_at) > max_age_seconds:
                return None
        return run

    def get_last_run(self, tool_name: str, scan_id: str) -> Optional[ToolRun]:
        """Get the most recent run of a tool in a scan."""
        return (
            self._session.query(ToolRun)
            .filter_by(tool_name=tool_name, scan_id=scan_id)
            .order_by(ToolRun.id.desc())
            .first()
        )

    def get_stale_tools(self, scan_id: str, max_age_seconds: int = 3600) -> list[str]:
        """Get tool names that have exceeded the staleness threshold."""
        cutoff = _now() - dt.timedelta(seconds=max_age_seconds)
        stale_runs = (
            self._session.query(ToolRun)
            .filter_by(scan_id=scan_id, status="completed")
            .filter(ToolRun.finished_at < cutoff)
            .all()
        )
        return list({run.tool_name for run in stale_runs})
