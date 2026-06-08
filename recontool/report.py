"""Reporting & export — read the canonical store and render summaries / exports."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, select

from recontool.core.db import session_scope
from recontool.core.models import Asset, Edge, Endpoint, Finding, Service


def write_output_files(scan_id: str, seed: str, output_dir: Path | None = None) -> Path:
    """Write all scan results to structured text and JSON files.

    Creates the following files in output_dir/<seed>/:
        subdomains.txt  - one subdomain per line
        ips.txt         - one IP per line
        live_hosts.txt  - live assets (one per line)
        services.txt    - host:port format
        endpoints.txt   - URLs
        findings.txt    - human-readable findings
        edges.txt       - src -> dst (rel)
        full_report.json - complete JSON export
        summary.txt     - human-readable summary

    This function is safe to call multiple times (overwrites existing files),
    so it can be invoked after each phase to capture partial results.
    """
    if output_dir is None:
        output_dir = Path("output")
    out = output_dir / seed
    out.mkdir(parents=True, exist_ok=True)

    with session_scope() as s:
        assets = s.execute(select(Asset).where(Asset.scan_id == scan_id)).scalars().all()
        asset_ids = [a.id for a in assets]

        # Subdomains
        subdomains = sorted({
            a.value for a in assets if a.type in ("subdomain", "domain")
        })
        (out / "subdomains.txt").write_text("\n".join(subdomains) + ("\n" if subdomains else ""))

        # IPs
        ips = sorted({a.value for a in assets if a.type == "ip"})
        (out / "ips.txt").write_text("\n".join(ips) + ("\n" if ips else ""))

        # Live hosts
        live_hosts = sorted({a.value for a in assets if a.is_live})
        (out / "live_hosts.txt").write_text(
            "\n".join(live_hosts) + ("\n" if live_hosts else "")
        )

        # Services
        services = s.execute(
            select(Service).where(Service.asset_id.in_(asset_ids))
        ).scalars().all() if asset_ids else []
        # Build host:port lines by joining with the asset
        asset_map = {a.id: a.value for a in assets}
        service_lines = sorted({
            f"{asset_map.get(sv.asset_id, '?')}:{sv.port}"
            for sv in services
        })
        (out / "services.txt").write_text(
            "\n".join(service_lines) + ("\n" if service_lines else "")
        )

        # Endpoints
        endpoints = s.execute(
            select(Endpoint).where(Endpoint.asset_id.in_(asset_ids))
        ).scalars().all() if asset_ids else []
        endpoint_lines = sorted({e.url for e in endpoints})
        (out / "endpoints.txt").write_text(
            "\n".join(endpoint_lines) + ("\n" if endpoint_lines else "")
        )

        # Findings
        findings = s.execute(
            select(Finding).where(Finding.scan_id == scan_id)
        ).scalars().all()
        finding_lines = []
        for f in findings:
            line = f"[{f.severity.upper()}] {f.title}"
            if f.asset_value:
                line += f" | asset={f.asset_value}"
            if f.detector:
                line += f" | detector={f.detector}"
            if f.cve_id:
                line += f" | {f.cve_id}"
            finding_lines.append(line)
        (out / "findings.txt").write_text(
            "\n".join(finding_lines) + ("\n" if finding_lines else "")
        )

        # Edges
        edges = s.execute(
            select(Edge).where(Edge.scan_id == scan_id)
        ).scalars().all()
        edge_lines = sorted({f"{ed.src} -> {ed.dst} ({ed.rel})" for ed in edges})
        (out / "edges.txt").write_text(
            "\n".join(edge_lines) + ("\n" if edge_lines else "")
        )

        # Full report JSON
        data = {
            "scan_id": scan_id,
            "seed": seed,
            "assets": [
                {
                    "type": a.type, "value": a.value, "confidence": a.confidence,
                    "is_live": a.is_live, "in_scope": a.in_scope, "tags": a.tags,
                    "tech": a.tech, "attributes": a.attributes,
                    "sources": [src.tool for src in a.sources],
                }
                for a in assets
            ],
            "services": [
                {"host": asset_map.get(sv.asset_id, "?"), "port": sv.port,
                 "protocol": sv.protocol, "service": sv.service_name,
                 "product": sv.product, "version": sv.version}
                for sv in services
            ],
            "endpoints": [
                {"url": e.url, "status": e.status_code, "title": e.title,
                 "risk_class": e.risk_class, "source": e.source}
                for e in endpoints
            ],
            "findings": [
                {"kind": f.kind, "title": f.title, "severity": f.severity,
                 "cve": f.cve_id, "detector": f.detector, "asset": f.asset_value,
                 "evidence": f.evidence_redacted}
                for f in findings
            ],
            "edges": [
                {"src": ed.src, "dst": ed.dst, "rel": ed.rel}
                for ed in edges
            ],
        }
        (out / "full_report.json").write_text(
            json.dumps(data, indent=2, default=str)
        )

        # Summary text
        by_type: dict[str, int] = {}
        for a in assets:
            by_type[a.type] = by_type.get(a.type, 0) + 1
        summary_lines = [
            f"Scan ID: {scan_id}",
            f"Seed: {seed}",
            "",
            "=== Asset Inventory ===",
        ]
        for t, c in sorted(by_type.items()):
            summary_lines.append(f"  {t}: {c}")
        summary_lines.append(f"  live: {len(live_hosts)}")
        summary_lines.append(f"  services: {len(services)}")
        summary_lines.append(f"  endpoints: {len(endpoints)}")
        summary_lines.append("")
        summary_lines.append("=== Findings ===")
        if findings:
            sev_counts: dict[str, int] = {}
            for f in findings:
                sev_counts[f.severity] = sev_counts.get(f.severity, 0) + 1
            for sev in ("critical", "high", "medium", "low", "info"):
                if sev in sev_counts:
                    summary_lines.append(f"  {sev}: {sev_counts[sev]}")
        else:
            summary_lines.append("  (none)")
        summary_lines.append("")
        (out / "summary.txt").write_text("\n".join(summary_lines) + "\n")

    return out


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
