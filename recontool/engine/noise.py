"""Optional noise-control layer for the re-feed path (spec gap G4).

A self-expanding engine amplifies false leads as fast as real ones. The
`NoiseFilter` sits between "a tool discovered an entity" and "re-feed it as a new
lead", dropping entities that should NOT spawn more work:

  * dedupe     — entities already seen this scan (deterministic, no network)
  * scope_gate — out-of-scope hosts / IPs (deterministic, no network)
  * wildcard   — subdomains that are just wildcard-DNS noise (needs a resolver)
  * cdn        — IPs inside CDN ranges, not real origin targets (needs a checker)

**Disabled by default.** `NoiseConfig.enabled=False` (and a `None` filter) means
the engine behaves exactly as before — the feature is opt-in, as required. The
deterministic checks (dedupe, scope_gate) need nothing external; wildcard and cdn
are opt-in and take *injected* async helpers, so the whole layer stays
hermetically testable with stubs and never hard-depends on network or binaries.
"""
from __future__ import annotations

import logging
import secrets
from collections import Counter
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from recontool.core.scope import Scope, apex_domain

logger = logging.getLogger(__name__)

# An async resolver: host -> set of resolved IP strings (empty = NXDOMAIN/no answer).
Resolver = Callable[[str], Awaitable[set]]
# An async CDN check: ip -> True if the IP belongs to a CDN/WAF edge range.
CdnCheck = Callable[[str], Awaitable[bool]]


@dataclass
class NoiseConfig:
    """Which noise filters are active. Everything off unless `enabled`."""

    enabled: bool = False
    dedupe: bool = True        # safe + free
    scope_gate: bool = True    # safe + free
    wildcard: bool = False     # needs a resolver
    cdn: bool = False          # needs a cdn checker


@dataclass
class NoiseFilter:
    """Decide whether a discovered entity should be re-fed as a new lead."""

    scope: Optional[Scope] = None
    config: NoiseConfig = field(default_factory=NoiseConfig)
    resolver: Optional[Resolver] = None
    cdn_check: Optional[CdnCheck] = None

    def __post_init__(self) -> None:
        self._seen: dict[str, set[tuple[str, str]]] = {}
        self._wildcard_ips: dict[str, set] = {}   # apex -> wildcard IP set
        self.stats: Counter = Counter()           # reason -> dropped count

    async def keep(self, scan_id: str, entity_type: str, value: str) -> bool:
        """Return True to re-feed the entity, False to drop it (with a stat)."""
        if not self.config.enabled:
            return True

        if self.config.dedupe:
            seen = self._seen.setdefault(scan_id, set())
            k = (entity_type, value)
            if k in seen:
                return self._drop("duplicate")
            seen.add(k)

        if self.config.scope_gate and self.scope is not None:
            if not self.scope.contains(entity_type, value):
                return self._drop("out_of_scope")

        if (self.config.wildcard and self.resolver is not None
                and entity_type in ("subdomain", "domain")):
            if await self._is_wildcard(value):
                return self._drop("wildcard_dns")

        if self.config.cdn and self.cdn_check is not None and entity_type == "ip":
            try:
                if await self.cdn_check(value):
                    return self._drop("cdn_edge")
            except Exception:  # noqa: BLE001 — a failing checker must not block the scan
                pass

        return True

    def _drop(self, reason: str) -> bool:
        self.stats[reason] += 1
        return False

    @property
    def dropped(self) -> int:
        return sum(self.stats.values())

    async def _is_wildcard(self, host: str) -> bool:
        """A host is wildcard noise if the apex has a wildcard record AND the host
        resolves only to that same wildcard IP set."""
        apex = apex_domain(host)
        if apex not in self._wildcard_ips:
            probe = f"{secrets.token_hex(8)}.{apex}"
            try:
                self._wildcard_ips[apex] = await self.resolver(probe)  # type: ignore[misc]
            except Exception:  # noqa: BLE001
                self._wildcard_ips[apex] = set()
        wc = self._wildcard_ips[apex]
        if not wc:                      # no wildcard on this apex → never noise
            return False
        try:
            ips = await self.resolver(host)  # type: ignore[misc]
        except Exception:  # noqa: BLE001
            return False
        return bool(ips) and ips <= wc


def build_default_resolver(lifetime: float = 5.0) -> Resolver:
    """A real async resolver via dnspython (same stack as adapters/active.py)."""
    async def resolve(host: str) -> set:
        try:
            import dns.asyncresolver
        except Exception:  # noqa: BLE001
            return set()
        r = dns.asyncresolver.Resolver()
        r.lifetime = lifetime
        out: set[str] = set()
        for rtype in ("A", "AAAA"):
            try:
                ans = await r.resolve(host, rtype)
                out.update(str(x) for x in ans)
            except Exception:  # noqa: BLE001
                continue
        return out

    return resolve
