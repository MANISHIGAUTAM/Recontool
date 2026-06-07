"""Normalization engine — the SOLE writer of canonical records (ADR-011).

Ingests Events from adapters and performs idempotent upserts keyed on
deterministic dedupe_keys. Re-discovery strengthens confidence (noisy-OR over
distinct sources) instead of creating duplicates. Also resolves the host asset
for services/endpoints and records relationship edges.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from recontool.adapters.base import Event
from recontool.core import dedupe
from recontool.core.confidence import confidence_from_tools, source_weight
from recontool.core.models import Asset, AssetSource, Edge, Endpoint, Finding, Service


class Normalizer:
    def __init__(self, session: Session, scan_id: str, scope=None):
        self.s = session
        self.scan_id = scan_id
        self.scope = scope
        # in-memory cache: dedupe_key -> Asset (per scan) to cut DB round-trips
        self._asset_cache: dict[str, Asset] = {}

    # ── public API ────────────────────────────────────────────────────────
    def ingest(self, events: list[Event]) -> dict[str, int]:
        counts = {"asset": 0, "service": 0, "endpoint": 0, "finding": 0, "edge": 0}
        # order matters: assets first (so services/endpoints can resolve hosts)
        order = {"asset": 0, "edge": 1, "service": 2, "endpoint": 2, "finding": 3}
        for ev in sorted(events, key=lambda e: order.get(e.entity, 9)):
            handler = getattr(self, f"_on_{ev.entity}", None)
            if handler and handler(ev):
                counts[ev.entity] += 1
        self.s.flush()
        return counts

    # ── handlers ──────────────────────────────────────────────────────────
    def _on_asset(self, ev: Event) -> bool:
        d = ev.data
        atype, value = d.get("type"), d.get("value")
        if not atype or not value:
            return False
        asset = self._upsert_asset(atype, value, ev.tool, raw_ref=ev.raw_ref)
        # merge optional attributes
        if d.get("is_live") is not None:
            asset.is_live = bool(d["is_live"])
        if d.get("tech"):
            asset.tech = sorted(set((asset.tech or []) + list(d["tech"])))
        if d.get("tags"):
            asset.tags = sorted(set((asset.tags or []) + list(d["tags"])))
        extra = {k: v for k, v in d.items()
                 if k not in ("type", "value", "is_live", "tech", "tags")}
        if extra:
            merged = dict(asset.attributes or {})
            merged.update(extra)
            asset.attributes = merged
        return True

    def _on_service(self, ev: Event) -> bool:
        d = ev.data
        host = d.get("host")
        port = d.get("port")
        if not host or port is None:
            return False
        # resolve/auto-create the host asset
        atype = "ip" if _is_ip(host) else "subdomain"
        asset = self._upsert_asset(atype, host, ev.tool)
        existing = self.s.execute(
            select(Service).where(
                Service.asset_id == asset.id, Service.port == int(port),
                Service.protocol == d.get("protocol", "tcp"),
            )
        ).scalar_one_or_none()
        if existing:
            for f in ("service_name", "product", "version", "banner"):
                if d.get(f):
                    setattr(existing, f, d[f])
            return False
        self.s.add(Service(
            asset_id=asset.id, port=int(port), protocol=d.get("protocol", "tcp"),
            service_name=d.get("service_name"), product=d.get("product"),
            version=d.get("version"), banner=d.get("banner"), tls=d.get("tls"),
        ))
        return True

    def _on_endpoint(self, ev: Event) -> bool:
        d = ev.data
        url = d.get("url")
        if not url:
            return False
        host = _host_of(url)
        atype = "ip" if _is_ip(host) else "subdomain"
        asset = self._upsert_asset(atype, host, ev.tool)
        key = dedupe.endpoint_key(url)
        existing = self.s.execute(
            select(Endpoint).where(Endpoint.asset_id == asset.id, Endpoint.dedupe_key == key)
        ).scalar_one_or_none()
        if existing:
            if d.get("status") is not None:
                existing.status_code = d["status"]
            if d.get("title"):
                existing.title = d["title"][:512]
            if d.get("params"):
                existing.params = sorted(set((existing.params or []) + list(d["params"])))
            return False
        self.s.add(Endpoint(
            asset_id=asset.id, url=url[:2048], status_code=d.get("status"),
            title=(d.get("title") or "")[:512] or None, source=d.get("source"),
            params=sorted(set(d.get("params") or [])),
            risk_class=_risk_class(url), dedupe_key=key,
        ))
        return True

    def _on_finding(self, ev: Event) -> bool:
        d = ev.data
        detector = d.get("detector", ev.tool)
        sig = d.get("title", "") + str(d.get("evidence_redacted", {}).get("sha1", ""))
        key = dedupe.finding_key(d.get("asset_value", ""), detector, sig)
        existing = self.s.execute(
            select(Finding).where(Finding.scan_id == self.scan_id, Finding.dedupe_key == key)
        ).scalar_one_or_none()
        if existing:
            existing.confidence = min(1.0, existing.confidence + 0.1)
            return False
        self.s.add(Finding(
            scan_id=self.scan_id, asset_value=d.get("asset_value"),
            kind=d.get("kind", "exposure"), title=d.get("title", "")[:512],
            cve_id=d.get("cve_id"), severity=d.get("severity", "info"),
            confidence=source_weight(ev.tool), detector=detector,
            evidence_ref=d.get("evidence_ref"), evidence_redacted=d.get("evidence_redacted"),
            dedupe_key=key,
        ))
        return True

    def _on_edge(self, ev: Event) -> bool:
        d = ev.data
        src, dst, rel = d.get("src"), d.get("dst"), d.get("rel")
        if not (src and dst and rel):
            return False
        existing = self.s.execute(
            select(Edge).where(Edge.src == src, Edge.dst == dst, Edge.rel == rel)
        ).scalar_one_or_none()
        if existing:
            return False
        self.s.add(Edge(scan_id=self.scan_id, src=src[:1024], dst=dst[:1024], rel=rel,
                        attributes=d.get("attributes", {})))
        return True

    # ── upsert core ─────────────────────────────────────────────────────────
    def _upsert_asset(self, atype: str, value: str, tool: str, raw_ref: str | None = None) -> Asset:
        key = dedupe.dedupe_key(atype, value)
        canon = dedupe.canonical_value(atype, value)
        if key in self._asset_cache:
            asset = self._asset_cache[key]
        else:
            asset = self.s.execute(
                select(Asset).where(Asset.scan_id == self.scan_id, Asset.dedupe_key == key)
            ).scalar_one_or_none()
            if asset is None:
                in_scope = self.scope.contains(atype, canon) if self.scope else True
                asset = Asset(
                    scan_id=self.scan_id, type=atype, value=canon, dedupe_key=key,
                    in_scope=in_scope, attributes={}, tech=[], tags=[],
                )
                self.s.add(asset)
                self.s.flush()
            self._asset_cache[key] = asset

        # record source sighting (unique per tool) + recompute confidence
        src = self.s.execute(
            select(AssetSource).where(AssetSource.asset_id == asset.id, AssetSource.tool == tool)
        ).scalar_one_or_none()
        if src is None:
            self.s.add(AssetSource(
                asset_id=asset.id, tool=tool,
                source_confidence=source_weight(tool), raw_ref=raw_ref,
            ))
            self.s.flush()
        tools = [s.tool for s in self.s.execute(
            select(AssetSource).where(AssetSource.asset_id == asset.id)
        ).scalars()]
        asset.confidence = confidence_from_tools(tools)
        return asset


# ── helpers ──────────────────────────────────────────────────────────────────
_HIGH_VALUE = ("admin", "login", "auth", "api", "upload", "dashboard", "debug",
               "internal", "staging", "dev", "test", "jenkins", "git", "vpn")


def _risk_class(url: str) -> str | None:
    low = url.lower()
    for kw in _HIGH_VALUE:
        if kw in low:
            return kw
    return None


def _is_ip(host: str) -> bool:
    import ipaddress

    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _host_of(url: str) -> str:
    from urllib.parse import urlsplit

    if "://" in url:
        return urlsplit(url).hostname or url
    return url.split("/")[0]
