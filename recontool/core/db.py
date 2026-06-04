"""Database engine + session management. SQLite by default, PostgreSQL-ready."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from recontool.config import settings
from recontool.core.models import Base

_engine = None
_Session: sessionmaker | None = None


def _connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def init_engine(url: str | None = None):
    global _engine, _Session
    url = url or settings.db_url
    _engine = create_engine(url, future=True, connect_args=_connect_args(url))
    _Session = sessionmaker(bind=_engine, expire_on_commit=False, class_=Session)
    return _engine


def create_all() -> None:
    """Create all tables. Idempotent."""
    if _engine is None:
        init_engine()
    Base.metadata.create_all(_engine)


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
