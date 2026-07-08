"""Regression: SQLite is configured for concurrent workers (WAL + busy_timeout).

Guards the 'database is locked' fix — many async/threaded workers writing to one
SQLite file must wait for the write lock, not crash.
"""
from __future__ import annotations

from sqlalchemy import text

from recontool.core import db


def test_sqlite_uses_wal_and_busy_timeout(tmp_path):
    db.init_engine(f"sqlite:///{tmp_path / 'concurrency.db'}")
    db.create_all()
    with db.session_scope() as s:
        assert s.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"
        assert s.execute(text("PRAGMA busy_timeout")).scalar() == 30000
