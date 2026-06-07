"""Frontier manager — entity-level recursion control.

The pipeline is *frontier-driven*: instead of re-running everything each pass, the
frontier manager tracks which canonical entities have already been EXPANDED
(re-queried against the source planner) and surfaces only the NEW, in-scope
entities discovered since the last pass. Discovery recurses only on that delta.

This implements the spec rules:
  * "The frontier manager must recurse only on new in-scope entities."
  * "Re-feed new subdomains, URLs, JS files, cert SANs, endpoints, params,
     buckets, handles, repos, and file paths back into the frontier."

It is intentionally storage-light and pure-logic: the canonical store (DB) is the
source of truth for what exists; the frontier only remembers which dedupe_keys it
has already handed out for expansion. That makes the pipeline idempotent and
resumable — a resumed scan rebuilds the frontier from what's already persisted.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select

from recontool.core.db import session_scope
from recontool.core.models import Asset, Endpoint
from recontool.core.scope import Scope

# Entity types that, when newly discovered, justify another expansion pass.
EXPANDABLE_TYPES = (
    "domain", "subdomain", "ip", "cidr", "asn", "url", "cert", "bucket",
    "email", "username", "repo",
)


@dataclass
class FrontierState:
    """Tracks which entity dedupe-keys have already been expanded."""

    expanded: set[str] = field(default_factory=set)

    def mark(self, keys) -> None:
        self.expanded.update(keys)

    def __len__(self) -> int:
        return len(self.expanded)


class FrontierManager:
    """Computes the new-in-scope-entity delta for the next recursion pass."""

    def __init__(self, scan_id: str, scope: Scope):
        self.scan_id = scan_id
        self.scope = scope
        self.state = FrontierState()

    def seed_from_store(self) -> None:
        """Mark everything currently persisted as already-known (used on resume so
        we don't re-expand the whole store)."""
        for atype, value, key in self._iter_assets():
            self.state.mark([key])

    def new_in_scope(self) -> dict[str, list[str]]:
        """Return {entity_type: [values]} of in-scope entities discovered since the
        last call. Marks them as expanded so the next call only sees newer ones."""
        delta: dict[str, list[str]] = {}
        newly: list[str] = []
        for atype, value, key in self._iter_assets():
            if key in self.state.expanded:
                continue
            if atype not in EXPANDABLE_TYPES:
                continue
            if not self.scope.contains(atype, value):
                continue
            delta.setdefault(atype, []).append(value)
            newly.append(key)
        # also surface newly discovered endpoints as 'url' frontier entries
        for url, key in self._iter_endpoints():
            if key in self.state.expanded:
                continue
            if not self.scope.contains("url", url):
                continue
            delta.setdefault("url", []).append(url)
            newly.append(key)
        self.state.mark(newly)
        return {k: sorted(set(v)) for k, v in delta.items()}

    def has_new(self) -> bool:
        """Cheap check: is there any unexpanded, in-scope entity?"""
        for atype, value, key in self._iter_assets():
            if key not in self.state.expanded and atype in EXPANDABLE_TYPES \
                    and self.scope.contains(atype, value):
                return True
        return False

    def stats(self) -> dict:
        return {"expanded": len(self.state)}

    # ── store access ─────────────────────────────────────────────────────────
    def _iter_assets(self):
        with session_scope() as s:
            rows = s.execute(
                select(Asset.type, Asset.value, Asset.dedupe_key)
                .where(Asset.scan_id == self.scan_id)
            ).all()
        for atype, value, key in rows:
            yield atype, value, f"a:{key}"

    def _iter_endpoints(self):
        with session_scope() as s:
            rows = s.execute(
                select(Endpoint.url, Endpoint.dedupe_key).where(
                    Endpoint.asset_id.in_(
                        select(Asset.id).where(Asset.scan_id == self.scan_id))
                )
            ).all()
        for url, key in rows:
            yield url, f"e:{key}"
