"""Normalization engine — the SOLE writer of canonical records (ADR-011).

Ingests Events from adapters and performs idempotent upserts keyed on
deterministic dedupe_keys. Re-discovery strengthens confidence (noisy-OR over
distinct sources) instead of creating duplicates. Also resolves the host asset
for services/endpoints and records relationship edges.

BULK ingest: events are batched by type and written with **set-based** SQL —
one ``dedupe_key IN (...)`` lookup + one bulk insert per type, instead of a
SELECT+flush per row. This turns O(n) round-trips into O(n/batch), so a tool that
emits 100k+ rows (e.g. waybackurls) ingests in seconds, not minutes — with the
same dedupe/confidence semantics as the per-row path.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from recontool.adapters.base import Event
from recontool.core import dedupe
from recontool.core.confidence import confidence_from_tools, source_weight
from recontool.core.models import Asset, AssetSource, Edge, Endpoint, Finding, Service

logger = logging.getLogger("recontool.normalize")

# Column-length ceilings (mirror models.py). Enforced so a value longer than its
# varchar(N) never raises on Postgres (SQLite silently allowed it). The full
# original is preserved elsewhere (attributes / typed-output JSONL / raw artifact)
# so bounding the stored column is not data loss.
_ASSET_VALUE_MAX = 1024
_FINDING_ASSET_MAX = 1024
_RAW_REF_MAX = 512
_PRODUCT_MAX = 128
_NAME_MAX = 64


def _cap(value, n):
    """Truncate a string to n chars, leaving None/empty untouched."""
    return value[:n] if isinstance(value, str) and len(value) > n else value


# A syntactically valid DNS hostname (dot-separated labels, alpha TLD; underscore
# allowed for records like _dmarc). Mirrors the adapter-layer check.
_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9_](?:[a-z0-9_-]{0,62})?\.)+[a-z]{2,63}$")


def _host_in_scope(value: str, scope) -> bool:
    """A subdomain/domain asset must be a valid hostname AND in scope.

    Applied at the Normalizer (the SOLE canonical writer, ADR-011) so EVERY
    source is gated uniformly — direct subdomain emits from any adapter (generic
    CLI/API, crawler, js_analyze) AND the host implied by an out-of-scope endpoint
    or service URL (katana/hakrawler crawl third-party links like
    accounts.google.com, which host-resolution would otherwise store as a
    "subdomain" of the target). Garbage (a tool banner line, a bare label) fails
    the shape check; external hosts fail the scope check. Raw evidence is
    untouched — only the asset graph stays target-scoped.
    """
    if not _HOST_RE.match((value or "").lower()):
        return False
    return scope is None or scope.contains("subdomain", value)


def _insert_ignore(session: Session, model, rows: list[dict]) -> None:
    """Bulk INSERT ... ON CONFLICT DO NOTHING (Postgres/SQLite).

    The check-then-insert pattern (SELECT existing, then add the rest) races
    under CONCURRENT writers: two workers both miss the same row in their SELECT
    and both INSERT it, and the second hits the unique constraint. Impossible on
    single-threaded SQLite; real on Postgres with the 8-thread DB pool. An
    insert-or-ignore makes the dedupe atomic so the loser is silently skipped
    (the row is already stored by the winner — no data loss, no error).
    """
    if not rows:
        return
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as _ins
        session.execute(_ins(model).values(rows).on_conflict_do_nothing())
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as _ins
        session.execute(_ins(model).values(rows).on_conflict_do_nothing())
    else:  # other backends: fall back to ORM add (resilience layer covers races)
        session.add_all([model(**r) for r in rows])


class Normalizer:
    def __init__(self, session: Session, scan_id: str, scope=None):
        self.s = session
        self.scan_id = scan_id
        self.scope = scope
        # dedupe_key -> Asset, reused across the per-type bulk phases of one ingest
        # (and across services/endpoints that resolve the same host).
        self._asset_cache: dict[str, Asset] = {}

    # ── public API ────────────────────────────────────────────────────────
    def ingest(self, events: list[Event]) -> dict[str, int]:
        """Bulk-ingest events. Counts: assets = valid asset events processed;
        service/endpoint/finding/edge = NEW rows inserted (matches the prior
        per-row contract)."""
        counts = {"asset": 0, "service": 0, "endpoint": 0, "finding": 0, "edge": 0}
        buckets: dict[str, list[Event]] = {}
        for ev in events:
            buckets.setdefault(ev.entity, []).append(ev)

        # Assets first (so services/endpoints can resolve/auto-create their host).
        counts["asset"] = self._ingest_assets(buckets.get("asset", []))
        counts["edge"] = self._ingest_edges(buckets.get("edge", []))
        counts["service"] = self._ingest_services(buckets.get("service", []))
        counts["endpoint"] = self._ingest_endpoints(buckets.get("endpoint", []))
        counts["finding"] = self._ingest_findings(buckets.get("finding", []))

        self.s.flush()
        if any(counts.values()):
            logger.debug("normalized %s into scan=%s", counts, self.scan_id)
        return counts

    # ── bulk asset upsert (shared by asset events + host resolution) ────────
    def _ensure_assets(self, specs: list[tuple]) -> dict[str, Asset]:
        """Upsert assets in bulk. ``specs`` = list of (atype, value, tool, raw_ref).
        Returns {dedupe_key: Asset}. Records each tool as an AssetSource and
        recomputes confidence (noisy-OR over distinct source tools) — all batched.
        """
        key_info: dict[str, tuple[str, str]] = {}        # key -> (atype, canon)
        key_tools: dict[str, set[tuple[str, str | None]]] = {}  # key -> {(tool, raw_ref)}
        for atype, value, tool, raw_ref in specs:
            if not atype or not value:
                continue
            # Central host gate: drop malformed / out-of-scope subdomain & domain
            # assets at the one writer, covering every adapter + endpoint/service
            # host resolution. (IPs/urls/cidrs keep their in_scope flag as before.)
            if atype in ("subdomain", "domain") and not _host_in_scope(value, self.scope):
                continue
            key = dedupe.dedupe_key(atype, value)
            if key not in key_info:
                key_info[key] = (atype, dedupe.canonical_value(atype, value))
                key_tools[key] = set()
            key_tools[key].add((tool, raw_ref))
        if not key_info:
            return {}

        # 1. resolve existing assets (cache first, then ONE batched query).
        result: dict[str, Asset] = {}
        missing = []
        for key in key_info:
            cached = self._asset_cache.get(key)
            if cached is not None:
                result[key] = cached
            else:
                missing.append(key)
        if missing:
            rows = self.s.execute(
                select(Asset).where(
                    Asset.scan_id == self.scan_id, Asset.dedupe_key.in_(missing))
            ).scalars().all()
            for a in rows:
                result[a.dedupe_key] = a
                self._asset_cache[a.dedupe_key] = a

        # 2. create the genuinely new assets, then ONE flush to assign ids.
        new_created = []
        for key, (atype, canon) in key_info.items():
            if key in result:
                continue
            in_scope = self.scope.contains(atype, canon) if self.scope else True
            # `value` is an indexed varchar(1024). SQLite ignores the length but
            # Postgres ENFORCES it — a crawl URL >1024 chars would raise
            # StringDataRightTruncation and (pre-resilience) kill the whole pool.
            # Bound the stored/indexed value but PRESERVE the full original in
            # attributes (no data loss — dedupe_key is already over the full value).
            stored, attrs = canon, {}
            if len(canon) > _ASSET_VALUE_MAX:
                stored = canon[:_ASSET_VALUE_MAX]
                attrs = {"value_full": canon}
            a = Asset(scan_id=self.scan_id, type=atype, value=stored, dedupe_key=key,
                      in_scope=in_scope, attributes=attrs, tech=[], tags=[])
            self.s.add(a)
            new_created.append((key, a))
        if new_created:
            self.s.flush()
            for key, a in new_created:
                result[key] = a
                self._asset_cache[key] = a

        # 3. AssetSource: batch-load existing (asset_id, tool), bulk-add the new.
        asset_ids = [a.id for a in result.values()]
        pairs: set[tuple[int, str]] = set()      # all (asset_id, tool) after this batch
        if asset_ids:
            for aid, tool in self.s.execute(
                select(AssetSource.asset_id, AssetSource.tool)
                .where(AssetSource.asset_id.in_(asset_ids))
            ):
                pairs.add((aid, tool))
        new_sources = []
        for key, tools in key_tools.items():
            a = result[key]
            for tool, raw_ref in tools:
                if (a.id, tool) in pairs:
                    continue
                pairs.add((a.id, tool))
                new_sources.append(AssetSource(
                    asset_id=a.id, tool=tool,
                    source_confidence=source_weight(tool), raw_ref=_cap(raw_ref, _RAW_REF_MAX)))
        if new_sources:
            self.s.add_all(new_sources)
            self.s.flush()

        # 4. recompute confidence from the full distinct-tool set per asset.
        tools_by_asset: dict[int, set[str]] = {}
        for aid, tool in pairs:
            tools_by_asset.setdefault(aid, set()).add(tool)
        for a in result.values():
            a.confidence = confidence_from_tools(tools_by_asset.get(a.id, set()))
        return result

    def _ingest_assets(self, evs: list[Event]) -> int:
        specs = [(e.data.get("type"), e.data.get("value"), e.tool, e.raw_ref)
                 for e in evs]
        assets = self._ensure_assets(specs)
        count = 0
        for ev in evs:
            d = ev.data
            atype, value = d.get("type"), d.get("value")
            if not atype or not value:
                continue
            count += 1
            asset = assets.get(dedupe.dedupe_key(atype, value))
            if asset is None:
                continue
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
        return count

    def _ingest_services(self, evs: list[Event]) -> int:
        rows = []   # (ev, asset_dedupe_key, port, proto)
        specs = []
        for ev in evs:
            d = ev.data
            host, port = d.get("host"), d.get("port")
            if not host or port is None:
                continue
            atype = "ip" if _is_ip(host) else "subdomain"
            specs.append((atype, host, ev.tool, None))
            rows.append((ev, dedupe.dedupe_key(atype, host), int(port),
                         d.get("protocol", "tcp")))
        if not rows:
            return 0
        assets = self._ensure_assets(specs)
        asset_ids = {assets[k].id for (_, k, _, _) in rows if k in assets}
        existing: dict[tuple, Service] = {}
        if asset_ids:
            for svc in self.s.execute(
                select(Service).where(Service.asset_id.in_(asset_ids))
            ).scalars():
                existing[(svc.asset_id, svc.port, svc.protocol)] = svc
        count = 0
        for ev, akey, port, proto in rows:
            asset = assets.get(akey)
            if asset is None:
                continue
            d = ev.data
            sig = (asset.id, port, proto)
            svc = existing.get(sig)
            if svc is None:
                svc = Service(asset_id=asset.id, port=port, protocol=proto,
                              service_name=_cap(d.get("service_name"), _NAME_MAX),
                              product=_cap(d.get("product"), _PRODUCT_MAX),
                              version=_cap(d.get("version"), _NAME_MAX),
                              banner=d.get("banner"), tls=d.get("tls"))
                self.s.add(svc)
                existing[sig] = svc
                count += 1
            else:
                _caps = {"service_name": _NAME_MAX, "product": _PRODUCT_MAX,
                         "version": _NAME_MAX}
                for f in ("service_name", "product", "version", "banner"):
                    if d.get(f):
                        setattr(svc, f, _cap(d[f], _caps[f]) if f in _caps else d[f])
        return count

    def _ingest_endpoints(self, evs: list[Event]) -> int:
        rows = []   # (ev, asset_dedupe_key, url, endpoint_key)
        specs = []
        for ev in evs:
            url = ev.data.get("url")
            if not url:
                continue
            host = _host_of(url)
            atype = "ip" if _is_ip(host) else "subdomain"
            specs.append((atype, host, ev.tool, None))
            rows.append((ev, dedupe.dedupe_key(atype, host), url, dedupe.endpoint_key(url)))
        if not rows:
            return 0
        assets = self._ensure_assets(specs)
        asset_ids = {assets[k].id for (_, k, _, _) in rows if k in assets}
        ekeys = {ek for (_, _, _, ek) in rows}
        existing: dict[tuple, Endpoint] = {}
        if asset_ids:
            # Bound the lookup to THIS batch's dedupe_keys (indexed) — NOT all
            # endpoints for the host, which would be O(n^2) as a host accumulates
            # hundreds of thousands of URLs.
            for ep in self.s.execute(
                select(Endpoint).where(
                    Endpoint.asset_id.in_(asset_ids),
                    Endpoint.dedupe_key.in_(ekeys))
            ).scalars():
                existing[(ep.asset_id, ep.dedupe_key)] = ep
        count = 0
        new_rows: list[dict] = []
        seen: set[tuple] = set()
        for ev, akey, url, ekey in rows:
            asset = assets.get(akey)
            if asset is None:
                continue
            d = ev.data
            sig = (asset.id, ekey)
            ep = existing.get(sig)
            if ep is not None:
                if d.get("status") is not None:
                    ep.status_code = d["status"]
                if d.get("title"):
                    ep.title = d["title"][:512]
                if d.get("params"):
                    ep.params = sorted(set((ep.params or []) + list(d["params"])))
                continue
            if sig in seen:
                continue  # dedupe within this batch before the insert
            seen.add(sig)
            new_rows.append(dict(
                asset_id=asset.id, url=url[:2048], status_code=d.get("status"),
                title=(d.get("title") or "")[:512] or None, source=d.get("source"),
                params=sorted(set(d.get("params") or [])),
                risk_class=_risk_class(url), dedupe_key=ekey))
            count += 1
        # Atomic insert-or-ignore: concurrent workers inserting the same endpoint
        # no longer raise a UniqueViolation (it was caught by the resilience layer
        # but triggered a costly per-event chunk retry + a scary PG error log).
        _insert_ignore(self.s, Endpoint, new_rows)
        return count

    def _ingest_findings(self, evs: list[Event]) -> int:
        keyed = []
        for ev in evs:
            d = ev.data
            detector = d.get("detector", ev.tool)
            sig = d.get("title", "") + str((d.get("evidence_redacted") or {}).get("sha1", ""))
            keyed.append((ev, detector, dedupe.finding_key(d.get("asset_value", ""), detector, sig)))
        if not keyed:
            return 0
        keys = {k for (_, _, k) in keyed}
        existing: dict[str, Finding] = {}
        for f in self.s.execute(
            select(Finding).where(Finding.scan_id == self.scan_id, Finding.dedupe_key.in_(keys))
        ).scalars():
            existing[f.dedupe_key] = f
        count = 0
        for ev, detector, key in keyed:
            f = existing.get(key)
            if f is None:
                d = ev.data
                f = Finding(
                    scan_id=self.scan_id, asset_value=_cap(d.get("asset_value"), _FINDING_ASSET_MAX),
                    kind=d.get("kind", "exposure"), title=d.get("title", "")[:512],
                    cve_id=d.get("cve_id"), severity=d.get("severity", "info"),
                    confidence=source_weight(ev.tool), detector=detector,
                    evidence_ref=d.get("evidence_ref"),
                    evidence_redacted=d.get("evidence_redacted"), dedupe_key=key)
                self.s.add(f)
                existing[key] = f
                count += 1
            else:
                f.confidence = min(1.0, f.confidence + 0.1)
        return count

    def _ingest_edges(self, evs: list[Event]) -> int:
        triples = []
        for ev in evs:
            d = ev.data
            src, dst, rel = d.get("src"), d.get("dst"), d.get("rel")
            if src and dst and rel:
                triples.append((ev, src, dst, rel))
        if not triples:
            return 0
        srcs = {s for (_, s, _, _) in triples}
        existing: set[tuple[str, str, str]] = set()
        for e in self.s.execute(select(Edge).where(Edge.src.in_(srcs))).scalars():
            existing.add((e.src, e.dst, e.rel))
        count = 0
        for ev, src, dst, rel in triples:
            sig = (src, dst, rel)
            if sig in existing:
                continue
            existing.add(sig)
            self.s.add(Edge(scan_id=self.scan_id, src=src[:1024], dst=dst[:1024],
                            rel=rel, attributes=ev.data.get("attributes", {})))
            count += 1
        return count


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
