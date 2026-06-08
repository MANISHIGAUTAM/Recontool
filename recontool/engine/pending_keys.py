"""Pending-key model and store for inter-tool dependency tracking.

A "pending key" represents a data dependency between tools. For example, a
subdomain enumeration tool produces subdomain keys that a port scanner requires.
The PendingKeyStore persists these to the DB and provides queries for the
scheduler to determine tool readiness.

Rules:
  - If required keys are missing -> tool is pending (blocked).
  - When new keys are produced -> dependent tools become reschedulable.
  - When all keys are available -> tool can be scheduled.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Optional

from recontool.engine.models import PendingKeyRecord


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


@dataclass
class PendingKey:
    """In-memory representation of a pending key."""

    key_type: str
    key_value: str
    created_by_tool: str
    scan_id: str
    status: str = "pending"  # pending | resolved | expired
    created_at: dt.datetime = field(default_factory=_now)
    resolved_at: Optional[dt.datetime] = None
    resolved_by_tool: Optional[str] = None


class PendingKeyStore:
    """DB-backed CRUD for pending keys.

    Requires a SQLAlchemy session (from recontool.core.db.session_scope).
    """

    def __init__(self, session) -> None:  # noqa: ANN001
        self._session = session

    def create_key(
        self,
        scan_id: str,
        key_type: str,
        key_value: str,
        created_by_tool: str,
    ) -> PendingKeyRecord:
        """Create and persist a new pending key."""
        record = PendingKeyRecord(
            scan_id=scan_id,
            key_type=key_type,
            key_value=key_value,
            status="pending",
            created_by_tool=created_by_tool,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def resolve_key(
        self,
        scan_id: str,
        key_type: str,
        key_value: str,
        resolved_by_tool: str,
    ) -> Optional[PendingKeyRecord]:
        """Mark a pending key as resolved. Returns the record or None if not found."""
        record = (
            self._session.query(PendingKeyRecord)
            .filter_by(scan_id=scan_id, key_type=key_type, key_value=key_value, status="pending")
            .first()
        )
        if record is None:
            return None
        record.status = "resolved"
        record.resolved_by_tool = resolved_by_tool
        record.resolved_at = _now()
        self._session.flush()
        return record

    def get_pending_for_tool(self, scan_id: str, key_type: str) -> list[PendingKeyRecord]:
        """Get all pending (unresolved) keys of a given type for a scan."""
        return (
            self._session.query(PendingKeyRecord)
            .filter_by(scan_id=scan_id, key_type=key_type, status="pending")
            .all()
        )

    def get_resolved_keys(self, scan_id: str, key_type: str) -> list[PendingKeyRecord]:
        """Get all resolved keys of a given type for a scan."""
        return (
            self._session.query(PendingKeyRecord)
            .filter_by(scan_id=scan_id, key_type=key_type, status="resolved")
            .all()
        )

    def is_tool_ready(self, scan_id: str, required_key_types: list[str]) -> bool:
        """Check if all required key types have at least one resolved key.

        Returns True if every required key type has at least one resolved record,
        meaning the dependent tool can proceed.
        """
        for key_type in required_key_types:
            resolved = (
                self._session.query(PendingKeyRecord)
                .filter_by(scan_id=scan_id, key_type=key_type, status="resolved")
                .first()
            )
            if resolved is None:
                return False
        return True
