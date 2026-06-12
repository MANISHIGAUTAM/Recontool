"""Read-only data access for the API / UI layer.

Pure DB queries returning plain dicts — **no FastAPI dependency**, so this is
unit-testable without the web stack installed. ``recontool/api/app.py`` is the
thin HTTP/SSE wiring on top of these helpers.

Everything here is read-only; the only write path (starting a scan) lives in the
auth-gated control endpoint in ``app.py``.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import func, select

from recontool.core.db import session_scope
from recontool.core.models import Asset, Edge, Finding, Scan
from recontool.engine.models import WorkItem


def list_scans(limit: int = 50) -> list[dict[str, Any]]:
    with session_scope() as s:
        rows = s.query(Scan).order_by(Scan.created_at.desc()).limit(limit).all()
        return [
            {
                "scan_id": r.id, "seed": r.seed, "seed_type": r.seed_type,
                "profile": r.profile, "status": r.status,
                "active_authorized": bool(r.active_authorized),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


def queue_stats(scan_id: str) -> dict[str, Any]:
    """WorkQueue breakdown — the recursion view (status, depth fan-out, re-feed)."""
    with session_scope() as s:
        by_status = dict(s.execute(
            select(WorkItem.status, func.count(WorkItem.id))
            .where(WorkItem.scan_id == scan_id).group_by(WorkItem.status)
        ).all())
        by_depth = dict(s.execute(
            select(WorkItem.depth, func.count(WorkItem.id))
            .where(WorkItem.scan_id == scan_id).group_by(WorkItem.depth)
            .order_by(WorkItem.depth)
        ).all())
        max_depth = s.execute(
            select(func.max(WorkItem.depth)).where(WorkItem.scan_id == scan_id)
        ).scalar() or 0
        refeed = s.execute(
            select(func.coalesce(func.sum(WorkItem.new_keys_found), 0))
            .where(WorkItem.scan_id == scan_id)
        ).scalar() or 0
    total = sum(by_status.values())
    pending = by_status.get("pending", 0) + by_status.get("running", 0)
    return {
        "scan_id": scan_id,
        "by_status": by_status,
        "by_depth": {f"d{d}": n for d, n in by_depth.items()},
        "max_depth": int(max_depth),
        "downstream_enqueued": int(refeed),
        "total_items": total,
        "active": pending > 0,
    }


def scan_overview(scan_id: str) -> Optional[dict[str, Any]]:
    with session_scope() as s:
        scan = s.get(Scan, scan_id)
        if scan is None:
            return None
        assets_by_type = dict(s.execute(
            select(Asset.type, func.count(Asset.id))
            .where(Asset.scan_id == scan_id).group_by(Asset.type)
        ).all())
        live = s.execute(
            select(func.count(Asset.id)).where(
                Asset.scan_id == scan_id, Asset.is_live.is_(True))
        ).scalar() or 0
        findings = s.execute(
            select(func.count(Finding.id)).where(Finding.scan_id == scan_id)
        ).scalar() or 0
        meta = {
            "scan_id": scan.id, "seed": scan.seed, "seed_type": scan.seed_type,
            "profile": scan.profile, "status": scan.status,
            "active_authorized": bool(scan.active_authorized),
        }
    return {
        **meta,
        "assets_by_type": assets_by_type,
        "assets_total": sum(assets_by_type.values()),
        "live_assets": int(live),
        "findings": int(findings),
        "queue": queue_stats(scan_id),
    }


def list_assets(scan_id: str, *, atype: str | None = None,
                limit: int = 500, offset: int = 0) -> list[dict[str, Any]]:
    with session_scope() as s:
        q = select(Asset).where(Asset.scan_id == scan_id)
        if atype:
            q = q.where(Asset.type == atype)
        q = q.order_by(Asset.confidence.desc(), Asset.id).limit(limit).offset(offset)
        return [
            {
                "type": a.type, "value": a.value, "confidence": round(a.confidence, 3),
                "is_live": a.is_live, "in_scope": a.in_scope,
                "tech": a.tech or [],
            }
            for a in s.execute(q).scalars().all()
        ]


def list_findings(scan_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
    with session_scope() as s:
        rows = s.execute(
            select(Finding).where(Finding.scan_id == scan_id)
            .order_by(Finding.severity, Finding.id).limit(limit)
        ).scalars().all()
        return [
            {
                "severity": f.severity, "kind": f.kind, "title": f.title,
                "asset": f.asset_value, "detector": f.detector,
                "cve_id": f.cve_id, "status": f.status,
            }
            for f in rows
        ]


def graph(scan_id: str, *, limit: int = 2000) -> dict[str, Any]:
    """Nodes (assets) + edges for the relationship graph front-end."""
    with session_scope() as s:
        assets = s.execute(
            select(Asset.type, Asset.value, Asset.confidence, Asset.is_live)
            .where(Asset.scan_id == scan_id).limit(limit)
        ).all()
        edges = s.execute(
            select(Edge.src, Edge.dst, Edge.rel)
            .where(Edge.scan_id == scan_id).limit(limit)
        ).all()
    nodes = [
        {"id": v, "type": t, "confidence": round(c, 3), "is_live": live}
        for (t, v, c, live) in assets
    ]
    return {
        "scan_id": scan_id,
        "nodes": nodes,
        "edges": [{"source": src, "target": dst, "rel": rel} for (src, dst, rel) in edges],
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
