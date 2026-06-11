"""Atomic tests for the persisted tool matrix + dedupe-aware Router.

Covers: seeding the full catalog (nothing dropped), idempotent re-seed,
deterministic routing with subdomain->domain subsumption, and WorkQueue dedupe
(a re-discovered key — even an equivalent spelling — never re-enqueues).
"""
from __future__ import annotations

import pytest

from recontool.core import db
from recontool.engine.models import ToolRow, WorkItem
from recontool.engine.router import enqueue, tools_for_key_type
from recontool.inventory.catalog import load_all_tools
from recontool.inventory.seed_matrix import seed
from sqlalchemy import func, select


@pytest.fixture()
def seeded(tmp_path):
    db.init_engine(f"sqlite:///{tmp_path / 'matrix.db'}")
    db.create_all()
    stats = seed()
    return stats


def test_full_catalog_seeded_nothing_dropped(seeded):
    catalog = load_all_tools()
    assert seeded["total"] == len(catalog)
    with db.session_scope() as s:
        rows = s.scalar(select(func.count()).select_from(ToolRow))
        web_only = s.scalar(
            select(func.count()).select_from(ToolRow).where(ToolRow.web_only.is_(True))
        )
    assert rows == len(catalog)
    # web-only / no-integration tools are KEPT, not eliminated
    assert web_only > 0


def test_seed_is_idempotent(seeded):
    again = seed()
    assert again["inserted"] == 0
    assert again["updated"] == 0


def test_subdomain_subsumes_domain_consumers(seeded):
    with db.session_scope() as s:
        domain_tools = tools_for_key_type(s, "domain")
        sub_tools = tools_for_key_type(s, "subdomain")
    # a discovered subdomain must be eligible for every domain-consuming tool
    assert len(sub_tools) >= len(domain_tools) > 0


def test_default_only_is_a_subset(seeded):
    with db.session_scope() as s:
        all_ip = tools_for_key_type(s, "ip")
        default_ip = tools_for_key_type(s, "ip", default_only=True)
    assert len(default_ip) <= len(all_ip)
    assert all(t.default_on for t in default_ip)


def test_enqueue_dedupes_rediscovered_keys(seeded):
    with db.session_scope() as s:
        first = enqueue(s, "scan1", "api.grow.in", "subdomain", default_only=True)
        repeat = enqueue(s, "scan1", "api.grow.in", "subdomain", default_only=True)
        equiv = enqueue(s, "scan1", "API.grow.in.", "subdomain", default_only=True)
    assert first > 0
    assert repeat == 0          # same key, same tools -> nothing new
    assert equiv == 0           # canonical spelling collapses -> nothing new
    with db.session_scope() as s:
        jobs = s.scalar(
            select(func.count()).select_from(WorkItem).where(WorkItem.scan_id == "scan1")
        )
    assert jobs == first        # exactly the first batch, no duplicates
