"""Atomic check C4 (Normalize): idempotent upsert + dedupe + confidence.

Proves that re-discovering the same asset does NOT create duplicates and that
corroboration from multiple sources raises confidence (noisy-OR).
"""
from __future__ import annotations

from sqlalchemy import func, select

from recontool.adapters.base import Event
from recontool.core.db import session_scope
from recontool.core.models import Asset, Service
from recontool.normalize.engine import Normalizer


def _count_assets(scan_id):
    with session_scope() as s:
        return s.execute(
            select(func.count()).select_from(Asset).where(Asset.scan_id == scan_id)
        ).scalar()


def test_dedupe_no_duplicates(scan_db):
    events = [
        Event.asset("crtsh", "subdomain", "api.example.com"),
        Event.asset("subfinder", "subdomain", "API.example.com."),  # same after canonicalize
    ]
    with session_scope() as s:
        Normalizer(s, scan_db).ingest(events)
    assert _count_assets(scan_db) == 1   # collapsed to one canonical asset


def test_reingest_is_idempotent(scan_db):
    ev = [Event.asset("crtsh", "subdomain", "api.example.com")]
    with session_scope() as s:
        Normalizer(s, scan_db).ingest(ev)
    with session_scope() as s:
        Normalizer(s, scan_db).ingest(ev)   # run again
    assert _count_assets(scan_db) == 1


def test_multisource_confidence_rises(scan_db):
    # one source
    with session_scope() as s:
        Normalizer(s, scan_db).ingest([Event.asset("hackertarget", "subdomain", "a.example.com")])
    with session_scope() as s:
        a1 = s.execute(select(Asset).where(Asset.value == "a.example.com")).scalar_one()
        c1 = a1.confidence
    # second independent source -> confidence must increase (noisy-OR)
    with session_scope() as s:
        Normalizer(s, scan_db).ingest([Event.asset("crtsh", "subdomain", "a.example.com")])
    with session_scope() as s:
        a2 = s.execute(select(Asset).where(Asset.value == "a.example.com")).scalar_one()
        assert a2.confidence > c1
        assert len(a2.sources) == 2


def test_service_attaches_to_host(scan_db):
    with session_scope() as s:
        Normalizer(s, scan_db).ingest([Event.service("shodan", "1.2.3.4", 443, product="nginx")])
    with session_scope() as s:
        # host IP asset auto-created
        assert s.execute(select(Asset).where(Asset.value == "1.2.3.4")).scalar_one()
        svc = s.execute(select(Service).where(Service.port == 443)).scalar_one()
        assert svc.product == "nginx"


def test_tags_merge_on_asset(scan_db):
    with session_scope() as s:
        Normalizer(s, scan_db).ingest([Event.asset("seed", "ip", "9.9.9.9")])
    with session_scope() as s:
        Normalizer(s, scan_db).ingest([Event.asset("greynoise", "ip", "9.9.9.9",
                                                    tags=["mass_scanner"])])
    with session_scope() as s:
        a = s.execute(select(Asset).where(Asset.value == "9.9.9.9")).scalar_one()
        assert "mass_scanner" in a.tags
