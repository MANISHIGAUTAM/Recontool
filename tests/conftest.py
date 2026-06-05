"""Shared pytest fixtures — an isolated, file-backed SQLite DB per test."""
from __future__ import annotations

import pytest

from recontool.core import db
from recontool.core.models import Scan


@pytest.fixture()
def scan_db(tmp_path):
    """Fresh DB + a Scan row; yields the scan_id."""
    db.init_engine(f"sqlite:///{tmp_path / 'test.db'}")
    db.create_all()
    scan_id = "testscan0001"
    with db.session_scope() as s:
        s.add(Scan(id=scan_id, seed="example.com", seed_type="domain",
                   profile="normal", status="running", scope_json={}))
    return scan_id
