"""Execution matrix: entity x tool status tracking.

Provides a matrix view of which tools have been run (or need to run)
against each discovered entity. Rows = entities, columns = tool names,
cells = execution status (pending/scanning/done/failed/skipped).

Usage:
    populate_pending(scan_id)        # queue up tools for all entities
    get_next_pending(scan_id)        # pick the next task to run
    mark_done(scan_id, entity, tool) # mark completed
    get_matrix(scan_id)              # full matrix as dict
    export_csv(scan_id, path)        # write CSV file
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path
from typing import Any

from sqlalchemy import select, update

from recontool.adapters.registry import all_adapters, load_builtin
from recontool.core.db import create_all, session_scope
from recontool.core.models import Asset, ToolExecution


def _entity_type_matches_consumes(entity_type: str, consumes: tuple[str, ...]) -> bool:
    """Check if an entity type matches an adapter's consumes declaration."""
    # Direct match
    if entity_type in consumes:
        return True
    # "subdomain" adapters also apply to "domain" entities (domains are supersets)
    if entity_type == "domain" and "subdomain" in consumes:
        return True
    return False


def populate_pending(scan_id: str) -> int:
    """Read all entities for a scan, determine applicable tools, create pending rows.

    Returns the number of new pending rows created.
    """
    create_all()
    load_builtin()
    adapters = all_adapters()

    count = 0
    with session_scope() as s:
        assets = s.execute(
            select(Asset).where(Asset.scan_id == scan_id)
        ).scalars().all()

        # Get existing (entity_value, tool_name) pairs to avoid duplicates
        existing = set()
        existing_rows = s.execute(
            select(ToolExecution.entity_value, ToolExecution.tool_name).where(
                ToolExecution.scan_id == scan_id
            )
        ).all()
        for row in existing_rows:
            existing.add((row[0], row[1]))

        for asset in assets:
            for tool_name, cls in adapters.items():
                consumes = getattr(cls, "consumes", ())
                if not consumes:
                    continue
                if not _entity_type_matches_consumes(asset.type, consumes):
                    continue
                if (asset.value, tool_name) in existing:
                    continue

                # Determine priority: active tools lower, passive higher
                priority = 10 if not getattr(cls, "is_active", False) else 5

                s.add(ToolExecution(
                    scan_id=scan_id,
                    entity_value=asset.value,
                    entity_type=asset.type,
                    tool_name=tool_name,
                    status="pending",
                    priority=priority,
                ))
                existing.add((asset.value, tool_name))
                count += 1

    return count


def get_next_pending(scan_id: str) -> dict[str, Any] | None:
    """Return the highest-priority pending item and atomically mark it scanning.

    Returns a dict with keys: entity_value, entity_type, tool_name, id
    or None if no pending items remain.
    """
    with session_scope() as s:
        row = s.execute(
            select(ToolExecution).where(
                ToolExecution.scan_id == scan_id,
                ToolExecution.status == "pending",
            ).order_by(
                ToolExecution.priority.desc(),
                ToolExecution.id.asc(),
            ).limit(1)
        ).scalar_one_or_none()

        if row is None:
            return None

        row.status = "scanning"
        row.started_at = dt.datetime.now(dt.timezone.utc)

        return {
            "id": row.id,
            "entity_value": row.entity_value,
            "entity_type": row.entity_type,
            "tool_name": row.tool_name,
        }


def mark_done(
    scan_id: str,
    entity_value: str,
    tool_name: str,
    events_produced: int = 0,
) -> None:
    """Mark a (scan, entity, tool) execution as done."""
    with session_scope() as s:
        s.execute(
            update(ToolExecution).where(
                ToolExecution.scan_id == scan_id,
                ToolExecution.entity_value == entity_value,
                ToolExecution.tool_name == tool_name,
            ).values(
                status="done",
                finished_at=dt.datetime.now(dt.timezone.utc),
                events_produced=events_produced,
            )
        )


def mark_failed(
    scan_id: str,
    entity_value: str,
    tool_name: str,
    error: str = "",
) -> None:
    """Mark a (scan, entity, tool) execution as failed."""
    with session_scope() as s:
        s.execute(
            update(ToolExecution).where(
                ToolExecution.scan_id == scan_id,
                ToolExecution.entity_value == entity_value,
                ToolExecution.tool_name == tool_name,
            ).values(
                status="failed",
                finished_at=dt.datetime.now(dt.timezone.utc),
                error=error[:2000] if error else "",
            )
        )


def mark_skipped(
    scan_id: str,
    entity_value: str,
    tool_name: str,
) -> None:
    """Mark a (scan, entity, tool) execution as skipped."""
    with session_scope() as s:
        s.execute(
            update(ToolExecution).where(
                ToolExecution.scan_id == scan_id,
                ToolExecution.entity_value == entity_value,
                ToolExecution.tool_name == tool_name,
            ).values(status="skipped")
        )


def get_matrix(scan_id: str) -> dict[str, Any]:
    """Return the full execution matrix as a dict for display/export.

    Returns:
        {
            "tools": ["tool1", "tool2", ...],
            "entities": [
                {
                    "value": "example.com",
                    "type": "domain",
                    "tools": {"tool1": "done", "tool2": "pending", ...}
                },
                ...
            ],
            "stats": {"pending": N, "scanning": N, "done": N, "failed": N, "skipped": N}
        }
    """
    with session_scope() as s:
        rows = s.execute(
            select(ToolExecution).where(ToolExecution.scan_id == scan_id)
        ).scalars().all()

    if not rows:
        return {"tools": [], "entities": [], "stats": {}}

    # Collect unique tool names and entity values
    tool_names: set[str] = set()
    entity_map: dict[str, dict[str, Any]] = {}  # entity_value -> info

    stats: dict[str, int] = {"pending": 0, "scanning": 0, "done": 0, "failed": 0, "skipped": 0}

    for row in rows:
        tool_names.add(row.tool_name)
        stats[row.status] = stats.get(row.status, 0) + 1

        if row.entity_value not in entity_map:
            entity_map[row.entity_value] = {
                "value": row.entity_value,
                "type": row.entity_type,
                "tools": {},
            }
        entity_map[row.entity_value]["tools"][row.tool_name] = row.status

    tools_sorted = sorted(tool_names)
    entities_sorted = sorted(entity_map.values(), key=lambda e: (e["type"], e["value"]))

    return {
        "tools": tools_sorted,
        "entities": entities_sorted,
        "stats": stats,
    }


def export_csv(scan_id: str, path: str | Path) -> Path:
    """Write the execution matrix as a CSV file.

    Columns: entity_value | entity_type | tool1 | tool2 | ... | toolN
    Each cell contains the status for that (entity, tool) pair.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    matrix = get_matrix(scan_id)
    tools = matrix["tools"]
    entities = matrix["entities"]

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        # Header row
        writer.writerow(["entity_value", "entity_type"] + tools)
        # Data rows
        for entity in entities:
            row = [entity["value"], entity["type"]]
            for tool in tools:
                row.append(entity["tools"].get(tool, ""))
            writer.writerow(row)

    return path
