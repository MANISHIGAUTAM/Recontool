"""Structured logging and observability for the event-driven engine.

Provides an EngineLogger that emits dict-based structured log entries
with correlation IDs, scan context, and timing information. Compatible
with structlog-style JSON logging pipelines.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Any


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


def _format_human(entry: dict[str, Any]) -> str:
    """Render a structured engine entry as one concise, readable line.

    Falls back to the raw dict for any event type without a bespoke format, so
    new event kinds remain loggable without a code change here.
    """
    ev = entry.get("event", "event")
    tool = entry.get("tool_name", "")
    if ev == "tool_start":
        inputs = entry.get("inputs") or {}
        ins = ", ".join(f"{k}={v[0] if isinstance(v, list) and v else v}"
                        for k, v in inputs.items())
        return f"▶ start  {tool}  ← {ins}" if ins else f"▶ start  {tool}"
    if ev == "tool_complete":
        n = entry.get("entity_count", 0)
        ms = entry.get("duration_ms", 0)
        return f"✓ done   {tool}  {n} entities  {ms}ms"
    if ev == "tool_fail":
        return f"✗ fail   {tool}  {entry.get('error', '')[:160]}"
    if ev == "entity_discovered":
        et, val = entry.get("entity_type", "?"), entry.get("entity_value", "")
        src = entry.get("tool_name", "")
        return f"  + {et}={val}" + (f"  (from {src})" if src else "")
    if ev == "pending_key_change":
        return (f"  · key {entry.get('action', '')} "
                f"{entry.get('key_type', '')}={entry.get('key_value', '')}")
    if ev == "ai_decision":
        return f"AI  {tool}: {entry.get('ai_decision_summary', '')}"
    if ev == "concurrency_decision":
        return (f"sched {tool}: {entry.get('concurrency_decision', '')} "
                f"{entry.get('reason', '')}").rstrip()
    if ev == "enqueue":
        return (f"  ↳ enqueued {entry.get('new_items', 0)} work items "
                f"for {entry.get('key_type', '')}={entry.get('key_value', '')} "
                f"(depth {entry.get('depth', 0)})")
    return str(entry)


class EngineLogger:
    """Structured logger for engine events.

    All log entries include scan_id, tool_run_id (when applicable),
    correlation_id, and timestamp. Entries are emitted as dicts and
    optionally forwarded to the standard logging module.
    """

    def __init__(
        self,
        logger_name: str = "recontool.engine",
        correlation_id: str | None = None,
    ) -> None:
        self._logger = logging.getLogger(logger_name)
        self._correlation_id = correlation_id or _uuid()
        self._entries: list[dict[str, Any]] = []

    @property
    def correlation_id(self) -> str:
        return self._correlation_id

    @property
    def entries(self) -> list[dict[str, Any]]:
        """All log entries recorded by this logger instance."""
        return list(self._entries)

    def _emit(self, entry: dict[str, Any]) -> None:
        """Record and emit a structured log entry.

        The dict is appended to ``entries`` (for programmatic/JSON consumers) and
        a concise human-readable line is sent to the stdlib logger so a `-v` scan
        shows readable progress instead of a raw dict dump.
        """
        entry.setdefault("correlation_id", self._correlation_id)
        entry.setdefault("timestamp", _now_iso())
        self._entries.append(entry)
        self._logger.info("%s", _format_human(entry), extra={"engine_event": entry})

    def log_tool_start(
        self,
        tool_run_id: str,
        scan_id: str,
        tool_name: str,
        inputs: dict[str, Any] | None = None,
    ) -> None:
        """Log the start of a tool execution."""
        self._emit({
            "event": "tool_start",
            "scan_id": scan_id,
            "tool_run_id": tool_run_id,
            "tool_name": tool_name,
            "inputs": inputs or {},
        })

    def log_tool_complete(
        self,
        tool_run_id: str,
        scan_id: str,
        tool_name: str,
        duration_ms: int = 0,
        exit_code: int = 0,
        entity_count: int = 0,
        input_fingerprint: str = "",
        output_fingerprint: str = "",
        artifact_paths: list[str] | None = None,
        command: str = "",
        retry_count: int = 0,
    ) -> None:
        """Log the successful completion of a tool execution."""
        self._emit({
            "event": "tool_complete",
            "scan_id": scan_id,
            "tool_run_id": tool_run_id,
            "tool_name": tool_name,
            "duration_ms": duration_ms,
            "exit_code": exit_code,
            "entity_count": entity_count,
            "input_fingerprint": input_fingerprint,
            "output_fingerprint": output_fingerprint,
            "artifact_paths": artifact_paths or [],
            "command": command,
            "retry_count": retry_count,
        })

    def log_tool_fail(
        self,
        tool_run_id: str,
        scan_id: str,
        tool_name: str,
        error: str,
        exit_code: int = 1,
        retry_count: int = 0,
        failure_reason: str = "",
    ) -> None:
        """Log a tool execution failure."""
        self._emit({
            "event": "tool_fail",
            "scan_id": scan_id,
            "tool_run_id": tool_run_id,
            "tool_name": tool_name,
            "error": error,
            "exit_code": exit_code,
            "retry_count": retry_count,
            "failure_reason": failure_reason or error,
        })

    def log_entity_discovered(
        self,
        scan_id: str,
        entity_type: str,
        entity_value: str,
        tool_name: str = "",
        parent_entity_id: str = "",
    ) -> None:
        """Log the discovery of a new entity."""
        self._emit({
            "event": "entity_discovered",
            "scan_id": scan_id,
            "entity_type": entity_type,
            "entity_value": entity_value,
            "tool_name": tool_name,
            "parent_entity_id": parent_entity_id,
        })

    def log_pending_key_change(
        self,
        scan_id: str,
        key_type: str,
        key_value: str,
        action: str,
        tool_name: str = "",
    ) -> None:
        """Log a pending key creation or resolution."""
        self._emit({
            "event": "pending_key_change",
            "scan_id": scan_id,
            "key_type": key_type,
            "key_value": key_value,
            "action": action,
            "tool_name": tool_name,
        })

    def log_concurrency_decision(
        self,
        scan_id: str,
        tool_name: str,
        decision: str,
        reason: str = "",
    ) -> None:
        """Log a concurrency/scheduling decision."""
        self._emit({
            "event": "concurrency_decision",
            "scan_id": scan_id,
            "tool_name": tool_name,
            "concurrency_decision": decision,
            "reason": reason,
        })

    def log_ai_decision(
        self,
        scan_id: str,
        summary: str,
        tool_name: str = "",
        ai_decision_summary: str = "",
    ) -> None:
        """Log an AI decisioning outcome."""
        self._emit({
            "event": "ai_decision",
            "scan_id": scan_id,
            "tool_name": tool_name,
            "ai_decision_summary": ai_decision_summary or summary,
        })

    def log_enqueue(
        self,
        scan_id: str,
        key_type: str,
        key_value: str,
        new_items: int,
        depth: int = 0,
        tool_name: str = "",
    ) -> None:
        """Log how many downstream (key, tool) work items a discovery created.

        This is the visible signal that recursion is fanning out across the
        matrix: a non-zero ``new_items`` means the discovered key matched
        consumers and pushed new jobs onto the queue.
        """
        self._emit({
            "event": "enqueue",
            "scan_id": scan_id,
            "key_type": key_type,
            "key_value": key_value,
            "new_items": new_items,
            "depth": depth,
            "tool_name": tool_name,
        })
