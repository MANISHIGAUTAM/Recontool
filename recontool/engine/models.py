"""SQLAlchemy models for the event-driven engine.

These models track tool execution state, pending key resolution, and scan
checkpointing. They use the same Base and conventions as recontool/core/models.py.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from recontool.core.models import Base


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class ToolRun(Base):
    """Record of a single tool execution within a scan."""

    __tablename__ = "tool_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[str] = mapped_column(String(36), index=True)
    tool_name: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    started_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    input_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))
    config_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))
    output_fingerprint: Mapped[Optional[str]] = mapped_column(String(64))
    exit_code: Mapped[Optional[int]] = mapped_column(Integer)
    artifact_paths: Mapped[list[Any]] = mapped_column(JSON, default=list)
    entity_count: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_detail: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    command_executed: Mapped[Optional[str]] = mapped_column(Text)


class PendingKeyRecord(Base):
    """Persistent record of a pending key (dependency between tools)."""

    __tablename__ = "pending_key"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[str] = mapped_column(String(36), index=True)
    key_type: Mapped[str] = mapped_column(String(64), index=True)
    key_value: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_by_tool: Mapped[Optional[str]] = mapped_column(String(128))
    resolved_by_tool: Mapped[Optional[str]] = mapped_column(String(128))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    resolved_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    fingerprint: Mapped[Optional[str]] = mapped_column(String(64))


class ScanState(Base):
    """Checkpoint for scan orchestration state."""

    __tablename__ = "scan_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[str] = mapped_column(String(36), index=True, unique=True)
    status: Mapped[str] = mapped_column(String(24), default="initializing")
    iteration: Mapped[int] = mapped_column(Integer, default=0)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    checkpoint_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
