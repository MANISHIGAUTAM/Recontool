"""Database engine + session management. SQLite by default, PostgreSQL-ready."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from recontool.config import settings
from recontool.core.models import Base

# Import engine models so their tables are registered with Base.metadata
import recontool.engine.models  # noqa: F401

_engine = None
_Session: sessionmaker | None = None


def _connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        # check_same_thread=False: the engine offloads DB work to a thread pool.
        # timeout: driver-level busy timeout (seconds) so a writer WAITS for the
        # lock instead of immediately raising "database is locked".
        return {"check_same_thread": False, "timeout": 30}
    return {}


def _enable_sqlite_concurrency(engine) -> None:
    """WAL + busy_timeout + synchronous=NORMAL so many concurrent workers can
    write to one SQLite file without 'database is locked'. WAL lets readers run
    while a writer holds the lock; busy_timeout makes a second writer wait (up to
    30s) for the lock rather than erroring. No-op/ignored on :memory: DBs."""

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        try:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")   # 30s — wait, don't crash
            cur.execute("PRAGMA synchronous=NORMAL")   # safe with WAL, much faster
        except Exception:  # noqa: BLE001 — pragmas must never block startup
            pass
        finally:
            cur.close()


def init_engine(url: str | None = None):
    global _engine, _Session
    url = url or settings.db_url
    _engine = create_engine(url, future=True, connect_args=_connect_args(url))
    if url.startswith("sqlite"):
        _enable_sqlite_concurrency(_engine)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False, class_=Session)
    return _engine


# Columns widened to TEXT after the SQLite->Postgres move (Postgres enforces
# varchar length; SQLite didn't). create_all() only CREATES missing tables — it
# never ALTERs an existing column — so widen them idempotently here for DBs that
# predate the model change. Postgres only; on SQLite varchar/text are equivalent.
_TEXT_WIDENINGS = (("work_item", "key"), ("work_item", "parent_key"))


def _migrate_widen_text(engine) -> None:
    if engine.dialect.name != "postgresql":
        return
    from sqlalchemy import text
    with engine.begin() as conn:
        for table, col in _TEXT_WIDENINGS:
            try:
                conn.execute(text(f'ALTER TABLE {table} ALTER COLUMN "{col}" TYPE TEXT'))
            except Exception:  # noqa: BLE001 — table may not exist yet; harmless
                pass


def create_all() -> None:
    """Create all tables. Idempotent."""
    if _engine is None:
        init_engine()
    Base.metadata.create_all(_engine)
    _migrate_widen_text(_engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session context."""
    if _Session is None:
        init_engine()
    sess = _Session()  # type: ignore[misc]
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()
