"""Integration tests for pending key lifecycle.

Verifies:
- Create pending key when tool discovers new subdomain
- Resolve pending key when live_host confirmed
- Trigger downstream tool only when live_host key resolved
- Prevent duplicate tool runs via fingerprint check
- Blocked tools remain blocked when dependencies missing
"""
from __future__ import annotations

import pytest

from recontool.core import db
from recontool.core.models import Scan
from recontool.engine.fingerprint import fingerprint_inputs
from recontool.engine.incremental import IncrementalEngine
from recontool.engine.models import ToolRun
from recontool.engine.pending_keys import PendingKeyStore


@pytest.fixture()
def engine_db(tmp_path):
    """Fresh SQLite database with scan + engine tables."""
    db.init_engine(f"sqlite:///{tmp_path / 'engine_test.db'}")
    db.create_all()
    scan_id = "pending-key-test-scan"
    with db.session_scope() as s:
        s.add(Scan(id=scan_id, seed="example.com", seed_type="domain",
                   profile="normal", status="running", scope_json={}))
    return scan_id


class TestPendingKeyLifecycle:
    """Integration tests for PendingKeyStore interactions with the DB."""

    def test_create_pending_key_on_subdomain_discovery(self, engine_db):
        """When a tool discovers a subdomain, a pending key is created."""
        scan_id = engine_db
        with db.session_scope() as session:
            store = PendingKeyStore(session)
            record = store.create_key(
                scan_id=scan_id,
                key_type="live_host",
                key_value="sub.example.com",
                created_by_tool="crtsh",
            )

            assert record.id is not None
            assert record.status == "pending"
            assert record.key_type == "live_host"
            assert record.key_value == "sub.example.com"
            assert record.created_by_tool == "crtsh"

    def test_resolve_pending_key_on_live_host_confirmed(self, engine_db):
        """When DNS/HTTP confirms a host is live, pending key is resolved."""
        scan_id = engine_db
        with db.session_scope() as session:
            store = PendingKeyStore(session)
            # Create a pending key
            store.create_key(
                scan_id=scan_id,
                key_type="live_host",
                key_value="api.example.com",
                created_by_tool="crtsh",
            )

            # Resolve it
            resolved = store.resolve_key(
                scan_id=scan_id,
                key_type="live_host",
                key_value="api.example.com",
                resolved_by_tool="httpx",
            )

            assert resolved is not None
            assert resolved.status == "resolved"
            assert resolved.resolved_by_tool == "httpx"
            assert resolved.resolved_at is not None

    def test_trigger_downstream_only_when_resolved(self, engine_db):
        """Downstream tools should only be marked ready when all keys resolved."""
        scan_id = engine_db
        with db.session_scope() as session:
            store = PendingKeyStore(session)

            # Create pending keys
            store.create_key(
                scan_id=scan_id,
                key_type="live_host",
                key_value="a.example.com",
                created_by_tool="crtsh",
            )
            store.create_key(
                scan_id=scan_id,
                key_type="open_port",
                key_value="a.example.com:443",
                created_by_tool="naabu",
            )

            # Tool needs both live_host and open_port
            assert not store.is_tool_ready(scan_id, ["live_host", "open_port"])

            # Resolve live_host only
            store.resolve_key(scan_id, "live_host", "a.example.com", "httpx")
            assert not store.is_tool_ready(scan_id, ["live_host", "open_port"])

            # Resolve open_port
            store.resolve_key(scan_id, "open_port", "a.example.com:443", "naabu")
            assert store.is_tool_ready(scan_id, ["live_host", "open_port"])

    def test_prevent_duplicate_tool_runs_via_fingerprint(self, engine_db):
        """Fingerprint check prevents redundant tool re-execution."""
        scan_id = engine_db
        with db.session_scope() as session:
            engine = IncrementalEngine(session)

            # Record a successful run with a known fingerprint
            inputs = {"domain": ["example.com"]}
            fp = fingerprint_inputs("crtsh", inputs)

            run = ToolRun(
                scan_id=scan_id,
                tool_name="crtsh",
                status="completed",
                input_fingerprint=fp,
                exit_code=0,
            )
            engine.record_run(run)

            # Same inputs should not require rerun
            assert not engine.should_rerun("crtsh", scan_id, inputs)

            # Different inputs should require rerun
            new_inputs = {"domain": ["other.com"]}
            assert engine.should_rerun("crtsh", scan_id, new_inputs)

    def test_blocked_tools_remain_blocked_when_deps_missing(self, engine_db):
        """Tools requiring unresolved keys remain blocked."""
        scan_id = engine_db
        with db.session_scope() as session:
            store = PendingKeyStore(session)

            # Create a key but do not resolve it
            store.create_key(
                scan_id=scan_id,
                key_type="live_host",
                key_value="blocked.example.com",
                created_by_tool="crtsh",
            )

            # Tool needs live_host - should not be ready
            assert not store.is_tool_ready(scan_id, ["live_host"])

            # Get pending keys - should return the unresolved one
            pending = store.get_pending_for_tool(scan_id, "live_host")
            assert len(pending) == 1
            assert pending[0].key_value == "blocked.example.com"
            assert pending[0].status == "pending"

    def test_resolve_nonexistent_key_returns_none(self, engine_db):
        """Resolving a key that does not exist returns None."""
        scan_id = engine_db
        with db.session_scope() as session:
            store = PendingKeyStore(session)
            result = store.resolve_key(
                scan_id=scan_id,
                key_type="live_host",
                key_value="nonexistent.example.com",
                resolved_by_tool="httpx",
            )
            assert result is None

    def test_multiple_keys_same_type(self, engine_db):
        """Multiple pending keys of the same type can coexist."""
        scan_id = engine_db
        with db.session_scope() as session:
            store = PendingKeyStore(session)

            store.create_key(scan_id, "live_host", "a.example.com", "crtsh")
            store.create_key(scan_id, "live_host", "b.example.com", "crtsh")
            store.create_key(scan_id, "live_host", "c.example.com", "crtsh")

            pending = store.get_pending_for_tool(scan_id, "live_host")
            assert len(pending) == 3

            # Resolve one
            store.resolve_key(scan_id, "live_host", "a.example.com", "httpx")
            pending = store.get_pending_for_tool(scan_id, "live_host")
            assert len(pending) == 2

            resolved = store.get_resolved_keys(scan_id, "live_host")
            assert len(resolved) == 1
            assert resolved[0].key_value == "a.example.com"

    def test_failed_tool_run_triggers_rerun(self, engine_db):
        """A previously failed tool should always be eligible for rerun."""
        scan_id = engine_db
        with db.session_scope() as session:
            engine = IncrementalEngine(session)

            inputs = {"domain": ["example.com"]}
            fp = fingerprint_inputs("flaky_tool", inputs)

            run = ToolRun(
                scan_id=scan_id,
                tool_name="flaky_tool",
                status="failed",
                input_fingerprint=fp,
                exit_code=1,
                error_detail="timeout",
            )
            engine.record_run(run)

            # Failed runs should always trigger a rerun
            assert engine.should_rerun("flaky_tool", scan_id, inputs)
