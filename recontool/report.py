"""Reporting & export — read the canonical store and render summaries / exports."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select

from recontool.core.db import session_scope
from recontool.core.models import Asset, Edge, Endpoint, Finding, Service


def summary(scan_id: str) -> dict:
    with session_scope() as s:
        by_type = {t: c for t, c in s.execute(
            select(Asset.type, func.count()).where(Asset.scan_id == scan_id)
            .group_by(Asset.type)
        ).all()}
        live = s.execute(
            select(func.count()).where(Asset.scan_id == scan_id, Asset.is_live.is_(True))
        ).scalar() or 0
        n_services = s.execute(
            select(func.count()).select_from(Service).where(
                Service.asset_id.in_(select(Asset.id).where(Asset.scan_id == scan_id)))
        ).scalar() or 0
        n_endpoints = s.execute(
            select(func.count()).select_from(Endpoint).where(
                Endpoint.asset_id.in_(select(Asset.id).where(Asset.scan_id == scan_id)))
        ).scalar() or 0
        findings = {sev: c for sev, c in s.execute(
            select(Finding.severity, func.count()).where(Finding.scan_id == scan_id)
            .group_by(Finding.severity)
        ).all()}
    return {
        "scan_id": scan_id,
        "assets_by_type": by_type,
        "live_assets": live,
        "services": n_services,
        "endpoints": n_endpoints,
        "findings_by_severity": findings,
    }


def export_json(scan_id: str, out: Path) -> Path:
    with session_scope() as s:
        asset_ids = [a for (a,) in s.execute(
            select(Asset.id).where(Asset.scan_id == scan_id)).all()]
        data = {
            "scan_id": scan_id,
            "assets": [
                {
                    "type": a.type, "value": a.value, "confidence": a.confidence,
                    "is_live": a.is_live, "in_scope": a.in_scope, "tags": a.tags,
                    "tech": a.tech, "attributes": a.attributes,
                    "sources": [src.tool for src in a.sources],
                }
                for a in s.execute(select(Asset).where(Asset.scan_id == scan_id)).scalars()
            ],
            "services": [
                {"asset_id": sv.asset_id, "port": sv.port, "protocol": sv.protocol,
                 "service": sv.service_name, "product": sv.product, "version": sv.version}
                for sv in s.execute(select(Service).where(Service.asset_id.in_(asset_ids))).scalars()
            ],
            "endpoints": [
                {"url": e.url, "status": e.status_code, "title": e.title,
                 "risk_class": e.risk_class, "source": e.source}
                for e in s.execute(select(Endpoint).where(Endpoint.asset_id.in_(asset_ids))).scalars()
            ],
            "findings": [
                {"kind": f.kind, "title": f.title, "severity": f.severity,
                 "cve": f.cve_id, "detector": f.detector, "asset": f.asset_value,
                 "evidence": f.evidence_redacted}
                for f in s.execute(select(Finding).where(Finding.scan_id == scan_id)).scalars()
            ],
            "edges": [
                {"src": ed.src, "dst": ed.dst, "rel": ed.rel}
                for ed in s.execute(select(Edge).where(Edge.scan_id == scan_id)).scalars()
            ],
        }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, default=str))
    return out


def top_assets(scan_id: str, limit: int = 25) -> list[dict]:
    with session_scope() as s:
        rows = s.execute(
            select(Asset).where(Asset.scan_id == scan_id)
            .order_by(Asset.confidence.desc()).limit(limit)
        ).scalars().all()
        return [
            {"type": a.type, "value": a.value, "conf": round(a.confidence, 3),
             "live": a.is_live, "sources": len(a.sources)}
            for a in rows
        ]


def findings_list(scan_id: str, limit: int = 50) -> list[dict]:
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    with session_scope() as s:
        rows = s.execute(select(Finding).where(Finding.scan_id == scan_id)).scalars().all()
    rows.sort(key=lambda f: sev_order.get(f.severity, 9))
    return [
        {"severity": f.severity, "kind": f.kind, "title": f.title,
         "asset": f.asset_value, "detector": f.detector}
        for f in rows[:limit]
    ]
