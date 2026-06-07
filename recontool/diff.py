"""Scan diffing — compare two scans of the same seed to surface CHANGES.

Powers continuous monitoring: after a re-scan, diff against the previous scan to
report newly appeared / disappeared assets, endpoints, services, and findings.
Pure read-only over the canonical store; deterministic and testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select

from recontool.core.db import session_scope
from recontool.core.models import Asset, Endpoint, Finding, Service


@dataclass
class Delta:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)

    def as_dict(self) -> dict:
        return {"added": sorted(self.added), "removed": sorted(self.removed)}


@dataclass
class ScanDiff:
    old_scan: str
    new_scan: str
    assets: Delta = field(default_factory=Delta)
    endpoints: Delta = field(default_factory=Delta)
    services: Delta = field(default_factory=Delta)
    findings: Delta = field(default_factory=Delta)

    @property
    def changed(self) -> bool:
        return any(d.changed for d in (self.assets, self.endpoints,
                                       self.services, self.findings))

    def as_dict(self) -> dict:
        return {
            "old_scan": self.old_scan,
            "new_scan": self.new_scan,
            "changed": self.changed,
            "assets": self.assets.as_dict(),
            "endpoints": self.endpoints.as_dict(),
            "services": self.services.as_dict(),
            "findings": self.findings.as_dict(),
        }


def _delta(old: set[str], new: set[str]) -> Delta:
    return Delta(added=list(new - old), removed=list(old - new))


def diff_scans(old_scan: str, new_scan: str) -> ScanDiff:
    """Diff two scans by canonical identity (values / urls / host:port / titles)."""
    with session_scope() as s:
        def assets(scan):
            return {f"{a.type}:{a.value}" for a in
                    s.execute(select(Asset).where(Asset.scan_id == scan)).scalars()}

        def endpoints(scan):
            ids = select(Asset.id).where(Asset.scan_id == scan)
            return {e.url for e in
                    s.execute(select(Endpoint).where(Endpoint.asset_id.in_(ids))).scalars()}

        def services(scan):
            ids = select(Asset.id).where(Asset.scan_id == scan)
            out = set()
            for sv in s.execute(select(Service).where(Service.asset_id.in_(ids))).scalars():
                out.add(f"{sv.asset_id}:{sv.port}/{sv.protocol}")
            return out

        def findings(scan):
            return {f.dedupe_key for f in
                    s.execute(select(Finding).where(Finding.scan_id == scan)).scalars()}

        d = ScanDiff(
            old_scan=old_scan, new_scan=new_scan,
            assets=_delta(assets(old_scan), assets(new_scan)),
            endpoints=_delta(endpoints(old_scan), endpoints(new_scan)),
            services=_delta(services(old_scan), services(new_scan)),
            findings=_delta(findings(old_scan), findings(new_scan)),
        )
    return d


def latest_two_scans(seed: str) -> tuple[str | None, str | None]:
    """Return (previous, latest) scan ids for a seed, newest last."""
    from recontool.core.models import Scan
    with session_scope() as s:
        rows = s.execute(
            select(Scan.id).where(Scan.seed == seed).order_by(Scan.created_at.desc()).limit(2)
        ).scalars().all()
    if len(rows) >= 2:
        return rows[1], rows[0]
    if len(rows) == 1:
        return None, rows[0]
    return None, None
