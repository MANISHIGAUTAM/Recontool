"""SQLAlchemy ORM models — the canonical system-of-record.

Mirrors docs/D3-data-schema.md. SQLite-friendly (no PG-only types) but works on
PostgreSQL unchanged. Every entity carries a deterministic `dedupe_key` so
re-discovery upserts instead of duplicating.

Note: uses ``Optional[...]`` (not ``X | None``) so SQLAlchemy can de-stringify the
``Mapped[...]`` annotations on Python 3.9+ as well as 3.10+.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Scan(Base):
    __tablename__ = "scan"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    seed: Mapped[str] = mapped_column(String(512))
    seed_type: Mapped[str] = mapped_column(String(32))           # domain|ip|cidr|asn|...
    profile: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(16), default="oneshot")
    status: Mapped[str] = mapped_column(String(16), default="queued")
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    active_authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    assets: Mapped[list["Asset"]] = relationship(back_populates="scan")


class Asset(Base):
    __tablename__ = "asset"
    __table_args__ = (UniqueConstraint("scan_id", "dedupe_key", name="uq_asset_dedupe"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scan.id"), index=True)
    type: Mapped[str] = mapped_column(String(24), index=True)    # domain|subdomain|ip|cidr|asn|url|cert|bucket|email|service
    value: Mapped[str] = mapped_column(String(1024), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), index=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tech: Mapped[list[Any]] = mapped_column(JSON, default=list)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_live: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    in_scope: Mapped[bool] = mapped_column(Boolean, default=True)
    first_seen: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    scan: Mapped["Scan"] = relationship(back_populates="assets")
    sources: Mapped[list["AssetSource"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )


class AssetSource(Base):
    """One row per (asset, tool) sighting — the basis of confidence scoring."""

    __tablename__ = "asset_source"
    __table_args__ = (UniqueConstraint("asset_id", "tool", name="uq_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("asset.id"), index=True)
    tool: Mapped[str] = mapped_column(String(64))
    source_confidence: Mapped[float] = mapped_column(Float, default=0.5)
    raw_ref: Mapped[Optional[str]] = mapped_column(String(512))
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    asset: Mapped["Asset"] = relationship(back_populates="sources")


class Service(Base):
    __tablename__ = "service"
    __table_args__ = (UniqueConstraint("asset_id", "port", "protocol", name="uq_service"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("asset.id"), index=True)
    port: Mapped[int] = mapped_column(Integer)
    protocol: Mapped[str] = mapped_column(String(8), default="tcp")
    service_name: Mapped[Optional[str]] = mapped_column(String(64))
    product: Mapped[Optional[str]] = mapped_column(String(128))
    version: Mapped[Optional[str]] = mapped_column(String(64))
    banner: Mapped[Optional[str]] = mapped_column(Text)
    tls: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    first_seen: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Endpoint(Base):
    __tablename__ = "endpoint"
    __table_args__ = (UniqueConstraint("asset_id", "dedupe_key", name="uq_endpoint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("asset.id"), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    method: Mapped[str] = mapped_column(String(8), default="GET")
    status_code: Mapped[Optional[int]] = mapped_column(Integer)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64))
    title: Mapped[Optional[str]] = mapped_column(String(512))
    params: Mapped[list[str]] = mapped_column(JSON, default=list)
    risk_class: Mapped[Optional[str]] = mapped_column(String(32))
    source: Mapped[Optional[str]] = mapped_column(String(64))
    dedupe_key: Mapped[str] = mapped_column(String(64), index=True)
    first_seen: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Finding(Base):
    __tablename__ = "finding"
    __table_args__ = (UniqueConstraint("scan_id", "dedupe_key", name="uq_finding"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scan.id"), index=True)
    asset_value: Mapped[Optional[str]] = mapped_column(String(1024))
    kind: Mapped[str] = mapped_column(String(24))               # cve|takeover|exposure|misconfig|secret|tls|cloud
    title: Mapped[str] = mapped_column(String(512))
    cve_id: Mapped[Optional[str]] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(12), default="info")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    priority_rank: Mapped[Optional[float]] = mapped_column(Float)
    detector: Mapped[str] = mapped_column(String(128))
    evidence_ref: Mapped[Optional[str]] = mapped_column(String(512))
    evidence_redacted: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="open")
    dedupe_key: Mapped[str] = mapped_column(String(64), index=True)
    first_seen: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Edge(Base):
    """Relationship between two assets (mirrored to a graph DB in prod)."""

    __tablename__ = "asset_edge"
    __table_args__ = (UniqueConstraint("src", "dst", "rel", name="uq_edge"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scan.id"), index=True)
    src: Mapped[str] = mapped_column(String(1024))              # asset value
    dst: Mapped[str] = mapped_column(String(1024))
    rel: Mapped[str] = mapped_column(String(32))               # resolves_to|in_cidr|subdomain_of|cname_to|...
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    first_seen: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[Optional[str]] = mapped_column(String(36), index=True)
    actor: Mapped[str] = mapped_column(String(64), default="system")
    action: Mapped[str] = mapped_column(String(64))
    tool: Mapped[Optional[str]] = mapped_column(String(64))
    target: Mapped[Optional[str]] = mapped_column(String(1024))
    egress_ip: Mapped[Optional[str]] = mapped_column(String(64))
    profile: Mapped[Optional[str]] = mapped_column(String(32))
    detail: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
