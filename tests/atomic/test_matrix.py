"""Atomic tests for the execution matrix module (recontool/matrix.py)."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from recontool.core.db import create_all, init_engine, session_scope
from recontool.core.models import Asset, Scan, ToolExecution
from recontool.matrix import (
    export_csv,
    get_matrix,
    get_next_pending,
    mark_done,
    mark_failed,
    mark_skipped,
    populate_pending,
)


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path):
    """Set up a fresh SQLite DB for each test."""
    db_path = tmp_path / "test.db"
    init_engine(f"sqlite:///{db_path}")
    create_all()
    yield


@pytest.fixture()
def scan_id():
    """Create a test scan and return its ID."""
    _id = "test_scan_001"
    with session_scope() as s:
        s.add(Scan(
            id=_id, seed="example.com", seed_type="domain",
            profile="normal", status="running",
        ))
    return _id


@pytest.fixture()
def scan_with_assets(scan_id):
    """Create a scan with various asset types."""
    with session_scope() as s:
        s.add(Asset(
            scan_id=scan_id, type="domain", value="example.com",
            dedupe_key="domain:example.com", confidence=1.0,
        ))
        s.add(Asset(
            scan_id=scan_id, type="subdomain", value="api.example.com",
            dedupe_key="subdomain:api.example.com", confidence=0.8,
        ))
        s.add(Asset(
            scan_id=scan_id, type="ip", value="93.184.216.34",
            dedupe_key="ip:93.184.216.34", confidence=0.9,
        ))
    return scan_id


# ── populate_pending ───────────────────────────────────────────────────────


def test_populate_pending_creates_rows(scan_with_assets):
    """populate_pending creates ToolExecution rows for matching entity/tool pairs."""
    count = populate_pending(scan_with_assets)
    assert count > 0

    with session_scope() as s:
        rows = s.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(ToolExecution).where(
                ToolExecution.scan_id == scan_with_assets
            )
        ).scalars().all()
        assert len(rows) == count
        # All rows should be pending
        for row in rows:
            assert row.status == "pending"


def test_populate_pending_idempotent(scan_with_assets):
    """Calling populate_pending twice does not create duplicate rows."""
    count1 = populate_pending(scan_with_assets)
    count2 = populate_pending(scan_with_assets)
    assert count1 > 0
    assert count2 == 0  # no new rows created


def test_populate_pending_empty_scan(scan_id):
    """populate_pending on a scan with no assets creates zero rows."""
    count = populate_pending(scan_id)
    assert count == 0


# ── get_next_pending ───────────────────────────────────────────────────────


def test_get_next_pending_returns_item(scan_with_assets):
    """get_next_pending returns a pending item and marks it scanning."""
    populate_pending(scan_with_assets)

    item = get_next_pending(scan_with_assets)
    assert item is not None
    assert "entity_value" in item
    assert "entity_type" in item
    assert "tool_name" in item
    assert "id" in item

    # Verify it was marked as scanning in the DB
    with session_scope() as s:
        row = s.get(ToolExecution, item["id"])
        assert row.status == "scanning"
        assert row.started_at is not None


def test_get_next_pending_returns_none_when_empty(scan_id):
    """get_next_pending returns None when no pending items exist."""
    item = get_next_pending(scan_id)
    assert item is None


def test_get_next_pending_respects_priority(scan_with_assets):
    """get_next_pending returns higher-priority items first."""
    populate_pending(scan_with_assets)

    # Get items until exhausted; track priorities
    priorities = []
    while True:
        item = get_next_pending(scan_with_assets)
        if item is None:
            break
        with session_scope() as s:
            row = s.get(ToolExecution, item["id"])
            priorities.append(row.priority)

    # Verify priorities are non-increasing (higher priority served first)
    for i in range(len(priorities) - 1):
        assert priorities[i] >= priorities[i + 1]


# ── mark_done ──────────────────────────────────────────────────────────────


def test_mark_done(scan_with_assets):
    """mark_done updates status and events_produced."""
    populate_pending(scan_with_assets)

    item = get_next_pending(scan_with_assets)
    assert item is not None

    mark_done(scan_with_assets, item["entity_value"], item["tool_name"], events_produced=5)

    with session_scope() as s:
        row = s.get(ToolExecution, item["id"])
        assert row.status == "done"
        assert row.events_produced == 5
        assert row.finished_at is not None


# ── mark_failed ────────────────────────────────────────────────────────────


def test_mark_failed(scan_with_assets):
    """mark_failed updates status and records error."""
    populate_pending(scan_with_assets)

    item = get_next_pending(scan_with_assets)
    assert item is not None

    mark_failed(scan_with_assets, item["entity_value"], item["tool_name"], error="timeout")

    with session_scope() as s:
        row = s.get(ToolExecution, item["id"])
        assert row.status == "failed"
        assert row.error == "timeout"
        assert row.finished_at is not None


# ── mark_skipped ───────────────────────────────────────────────────────────


def test_mark_skipped(scan_with_assets):
    """mark_skipped updates status to skipped."""
    populate_pending(scan_with_assets)

    item = get_next_pending(scan_with_assets)
    assert item is not None

    mark_skipped(scan_with_assets, item["entity_value"], item["tool_name"])

    with session_scope() as s:
        row = s.get(ToolExecution, item["id"])
        assert row.status == "skipped"


# ── get_matrix ─────────────────────────────────────────────────────────────


def test_get_matrix_returns_structure(scan_with_assets):
    """get_matrix returns correct structure with tools, entities, stats."""
    populate_pending(scan_with_assets)

    matrix = get_matrix(scan_with_assets)
    assert "tools" in matrix
    assert "entities" in matrix
    assert "stats" in matrix
    assert isinstance(matrix["tools"], list)
    assert isinstance(matrix["entities"], list)
    assert len(matrix["entities"]) > 0

    # Check entity structure
    entity = matrix["entities"][0]
    assert "value" in entity
    assert "type" in entity
    assert "tools" in entity

    # All should be pending since we just populated
    assert matrix["stats"]["pending"] > 0


def test_get_matrix_empty_scan(scan_id):
    """get_matrix on a scan with no matrix data returns empty."""
    matrix = get_matrix(scan_id)
    assert matrix["tools"] == []
    assert matrix["entities"] == []


def test_get_matrix_reflects_status_changes(scan_with_assets):
    """get_matrix reflects updated statuses after mark_done/mark_failed."""
    populate_pending(scan_with_assets)

    item = get_next_pending(scan_with_assets)
    mark_done(scan_with_assets, item["entity_value"], item["tool_name"], events_produced=3)

    matrix = get_matrix(scan_with_assets)
    # Find the entity and tool
    for entity in matrix["entities"]:
        if entity["value"] == item["entity_value"]:
            if item["tool_name"] in entity["tools"]:
                assert entity["tools"][item["tool_name"]] == "done"
                break


# ── export_csv ─────────────────────────────────────────────────────────────


def test_export_csv(scan_with_assets, tmp_path):
    """export_csv writes a valid CSV file with proper headers and data."""
    populate_pending(scan_with_assets)

    csv_path = tmp_path / "matrix.csv"
    result_path = export_csv(scan_with_assets, csv_path)

    assert result_path == csv_path
    assert csv_path.exists()

    # Read and validate CSV
    with open(csv_path) as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header[0] == "entity_value"
        assert header[1] == "entity_type"
        assert len(header) > 2  # at least one tool column

        rows = list(reader)
        assert len(rows) > 0


def test_export_csv_creates_parent_dirs(scan_with_assets, tmp_path):
    """export_csv creates parent directories if they don't exist."""
    populate_pending(scan_with_assets)

    csv_path = tmp_path / "nested" / "dir" / "matrix.csv"
    result_path = export_csv(scan_with_assets, csv_path)
    assert result_path.exists()
