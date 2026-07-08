"""Deterministic Router + dedupe-aware WorkQueue enqueue.

The Router answers "which tools consume this key type?" by a plain query over the
persisted `ToolRow` registry — NOT an AI call (canonical spec §2). `enqueue`
turns a discovered entity into `(key, tool)` WorkItems, skipping any pair that
already exists for the scan, so a re-discovered key never triggers a rescan
(canonical spec §1).
"""
from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from recontool.core import dedupe
from recontool.engine.models import ToolRow, WorkItem


# Type subsumption for INPUT eligibility: a key of type K is also a valid input
# to tools that consume any of its supertypes. A discovered subdomain must be
# eligible for every domain-consuming source (that is how recursion fans out); a
# live_host is also a subdomain and a domain for input purposes.
# M9 — narrowed to stop "scan everything". A `url` or `live_host` no longer subsumes
# up to subdomain/domain: a crawled URL must NOT re-trigger subdomain enumeration or
# the whole domain-consuming wave (~340 tools), and a validated live_host routes only
# to the active/deep layer that consumes live_host — not back into discovery. Only
# `subdomain -> domain` is kept: that is the legitimate recursive subdomain discovery
# the engine is built on (a discovered subdomain feeds CT/passive-DNS sources declared
# on `domain`), and idempotent keys make the overlap free.
SUBSUMES: dict[str, list[str]] = {
    "subdomain": ["domain"],
    "live_host": [],
    "url": [],
    "cidr": ["asn"],
    "ip": [],
}


def _eligible_types(key_type: str) -> set[str]:
    return {key_type, *SUBSUMES.get(key_type, [])}


def work_dedupe_key(key_type: str, key: str, tool_slug: str) -> str:
    """Stable per-(entity, tool) key. Equivalent entity spellings collapse via
    the same canonicalization used by the normalizer (core.dedupe)."""
    canon = dedupe.canonical_value(key_type, key)
    return hashlib.sha1(f"{key_type}:{canon}::{tool_slug}".encode()).hexdigest()


def tools_for_key_type(
    session: Session, key_type: str, *, default_only: bool = False,
    runnable_only: bool = False,
) -> list[ToolRow]:
    """All registered tools that consume `key_type`.

    Deterministic join. `default_only` limits to the recommended profile;
    `runnable_only` limits to tools with a real executable contract today.
    The registry is small (~560 rows) so we filter in Python for exact list
    membership rather than fragile SQL LIKE matching.
    """
    wanted = _eligible_types(key_type)
    rows = session.execute(select(ToolRow)).scalars().all()
    out = []
    for r in rows:
        if not wanted & set(r.consumes or []):
            continue
        if default_only and not r.default_on:
            continue
        if runnable_only and not r.runnable:
            continue
        out.append(r)
    return out


def enqueue(
    session: Session, scan_id: str, key: str, key_type: str, *,
    parent_key: str | None = None, depth: int = 0,
    default_only: bool = True, runnable_only: bool = False,
) -> int:
    """Create pending WorkItems for every tool that consumes `key_type`.

    Returns the number of NEW items created. A `(scan_id, key, tool)` pair that
    already exists is skipped (the "push only if new" rule), so overlapping tools
    rediscovering the same entity cost nothing and nothing is rescanned.
    """
    tools = tools_for_key_type(
        session, key_type, default_only=default_only, runnable_only=runnable_only
    )
    if not tools:
        return 0

    existing = {
        dk for (dk,) in session.execute(
            select(WorkItem.dedupe_key).where(WorkItem.scan_id == scan_id)
        )
    }
    created = 0
    for tool in tools:
        dk = work_dedupe_key(key_type, key, tool.slug)
        if dk in existing:
            continue
        existing.add(dk)
        session.add(WorkItem(
            scan_id=scan_id, key=key, key_type=key_type, tool_slug=tool.slug,
            dedupe_key=dk, status="pending", parent_key=parent_key, depth=depth,
        ))
        created += 1
    return created
