"""Adapter framework.

Adapters are PURE (docs/D4-adr.md ADR-011): they run one tool/source, capture
raw output, and emit normalized Events. They contain NO cross-asset correlation
logic — that lives in the normalization engine.

Every adapter:
  - declares whether it is passive or active (gate-aware),
  - declares which seed types it accepts,
  - declares what it consumes (chaining input) and produces,
  - re-checks scope before any active egress,
  - emits Events + an audit trail.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Literal

from recontool.config import RateProfile
from recontool.core.artifacts import ArtifactStore
from recontool.core.scope import Scope
from recontool.net.http_client import HttpClient

EntityType = Literal["asset", "service", "endpoint", "finding", "edge"]


@dataclass
class Event:
    """A normalized output record from an adapter."""

    entity: EntityType
    tool: str
    data: dict[str, Any]
    raw_ref: str | None = None

    # convenience constructors -------------------------------------------------
    @staticmethod
    def asset(tool: str, atype: str, value: str, **attrs: Any) -> "Event":
        return Event("asset", tool, {"type": atype, "value": value, **attrs})

    @staticmethod
    def service(tool: str, host: str, port: int, **attrs: Any) -> "Event":
        return Event("service", tool, {"host": host, "port": port, **attrs})

    @staticmethod
    def endpoint(tool: str, url: str, **attrs: Any) -> "Event":
        return Event("endpoint", tool, {"url": url, **attrs})

    @staticmethod
    def finding(tool: str, kind: str, title: str, **attrs: Any) -> "Event":
        return Event("finding", tool, {"kind": kind, "title": title, **attrs})

    @staticmethod
    def edge(tool: str, src: str, dst: str, rel: str, **attrs: Any) -> "Event":
        return Event("edge", tool, {"src": src, "dst": dst, "rel": rel, **attrs})


@dataclass
class AdapterContext:
    """Everything an adapter needs to run one unit of work."""

    scan_id: str
    scope: Scope
    profile: RateProfile
    http: HttpClient
    artifacts: ArtifactStore
    # Chaining input: assets discovered so far, grouped by type.
    inputs: dict[str, list[str]] = field(default_factory=dict)
    api_keys: dict[str, str | None] = field(default_factory=dict)

    def seeds_of(self, atype: str) -> list[str]:
        return self.inputs.get(atype, [])


class Adapter(abc.ABC):
    """Base class for every tool/source integration."""

    name: str = "adapter"
    category: str = "misc"
    is_active: bool = False              # touches the target?
    # Seed types this adapter consumes (chaining): e.g. ["domain", "subdomain"]
    consumes: tuple[str, ...] = ("domain",)
    # Asset types this adapter typically produces (for planning/visibility).
    produces: tuple[str, ...] = ()
    # If True, requires an API key (declared in `key_env`) to do anything.
    key_env: str | None = None

    def available(self, ctx: AdapterContext) -> bool:
        """Can this adapter run given current config/keys/tooling? Override for
        CLI tools (binary present?) or keyed APIs."""
        if self.key_env:
            return bool(ctx.api_keys.get(self.key_env))
        return True

    @abc.abstractmethod
    async def run(self, ctx: AdapterContext) -> list[Event]:
        """Execute and return normalized events. Must be idempotent-safe."""
        raise NotImplementedError
