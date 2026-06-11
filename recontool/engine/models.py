"""SQLAlchemy models for the event-driven engine.

These models track tool execution state, pending key resolution, and scan
checkpointing. They use the same Base and conventions as recontool/core/models.py.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from recontool.core.models import Base


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class ToolRow(Base):
    """Persisted tool capability registry — the static half of the matrix.

    One row per canonical tool (ALL of them, including web-only / no-integration
    tools, which are kept and flagged, never removed). Seeded idempotently from
    the full catalog by `recontool.inventory.seed_matrix`. The dynamic half is
    `WorkItem`. `consumes`/`produces` are canonical entity types and drive the
    deterministic Router (`recontool.engine.router`).
    """

    __tablename__ = "tool_row"

    slug: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    category: Mapped[str] = mapped_column(String(64), default="")
    classification: Mapped[str] = mapped_column(String(16), default="passive")
    integration: Mapped[list[Any]] = mapped_column(JSON, default=list)  # cli|api|python|dataset|web
    consumes: Mapped[list[Any]] = mapped_column(JSON, default=list)
    produces: Mapped[list[Any]] = mapped_column(JSON, default=list)
    runnable: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    web_only: Mapped[bool] = mapped_column(Boolean, default=False)
    default_on: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    source: Mapped[str] = mapped_column(String(16), default="extracted")  # extracted|suggested
    modes: Mapped[list[Any]] = mapped_column(JSON, default=list)


class WorkItem(Base):
    """A single (key, tool) job — the dynamic half of the matrix (WorkQueue).

    `dedupe_key` is unique per scan, so the same (entity, tool) pair is enqueued
    at most once: a re-discovered key never triggers a rescan. Status lifecycle:
    pending -> in_progress -> completed | failed.
    """

    __tablename__ = "work_item"
    __table_args__ = (
        UniqueConstraint("scan_id", "dedupe_key", name="uq_workitem_dedupe"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[str] = mapped_column(String(36), index=True)
    key: Mapped[str] = mapped_column(String(1024))
    key_type: Mapped[str] = mapped_column(String(64), index=True)
    tool_slug: Mapped[str] = mapped_column(String(128), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    parent_key: Mapped[Optional[str]] = mapped_column(String(1024))
    depth: Mapped[int] = mapped_column(Integer, default=0)
    output_path: Mapped[Optional[str]] = mapped_column(Text)
    new_keys_found: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))


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
