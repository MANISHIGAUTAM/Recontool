"""Org-forest pivots — expand from one seed toward the whole estate.

The "non-obvious multiplier" (research doc §2d): an organisation reuses
fingerprints across its sibling sites — the **same favicon**, the **same Google
Analytics / AdSense IDs**, the **same WHOIS/copyright org**. Extracting those
fingerprints lets keyed lookups pivot to RELATED domains.

This adapter does the keyless EXTRACTION half: it reads a live host's homepage +
favicon and emits typed pivot keys — ``favicon`` (Shodan-format mmh3 hash),
``analytics_id`` (UA / GA4 / GTM / AdSense), and ``org`` (copyright string) —
plus provenance edges (host → fingerprint). The lookups that turn a fingerprint
into sibling domains are **keyed** generic specs (favicon → Shodan
``http.favicon.hash``; analytics_id → publicwww), so they only run when the user
supplies the key.

The extraction helpers (``favicon_hash``, ``extract_analytics_ids``,
``extract_org_strings``) are pure and unit-tested without network.

⚠️ SCOPE SAFETY: sibling domains surfaced by the pivots are recorded as related-
org **intelligence** (``org`` entities + edges), *not* auto-promoted to in-scope
seeds. The platform is authorized-only: expanding an active scan onto a newly
discovered sibling domain is a deliberate operator action (add it to scope and
re-seed), never automatic. So this never silently widens the authorized target.
"""
from __future__ import annotations

import base64
import re

from recontool.adapters.base import Adapter, AdapterContext, Event
from recontool.adapters.crawler import host_of
from recontool.adapters.registry import register

try:  # optional dep — favicon hashing degrades cleanly without it
    import mmh3  # type: ignore
except Exception:  # noqa: BLE001
    mmh3 = None  # type: ignore

# Analytics / ad identifiers shared across an org's sibling sites.
_ANALYTICS_PATTERNS = [
    re.compile(r"UA-\d{4,10}-\d{1,4}"),          # Universal Analytics
    re.compile(r"G-[A-Z0-9]{6,12}"),             # GA4 measurement id
    re.compile(r"GTM-[A-Z0-9]{4,10}"),           # Google Tag Manager
    re.compile(r"ca-pub-\d{10,20}"),             # AdSense publisher id
]
_COPYRIGHT_RE = re.compile(
    r"(?:©|&copy;|copyright)\s*(?:\(c\))?\s*\d{4}\s*[-–]?\s*(?:\d{4})?\s+"
    r"([A-Z][\w&.,'\- ]{2,60}?)(?:\.|<|\||,?\s+all rights|$)",
    re.I,
)


def favicon_hash(content: bytes) -> int | None:
    """Shodan-format favicon hash (mmh3 over base64 with 76-char line wrapping).

    Returns None if the optional ``mmh3`` dependency is absent or content empty,
    so the caller simply skips the favicon pivot rather than failing.
    """
    if not content or mmh3 is None:
        return None
    try:
        b64 = base64.encodebytes(content)  # inserts a newline every 76 chars
        return mmh3.hash(b64)
    except Exception:  # noqa: BLE001
        return None


def extract_analytics_ids(html: str) -> list[str]:
    """Unique Google Analytics / GA4 / GTM / AdSense ids referenced in the page."""
    out: list[str] = []
    seen: set[str] = set()
    for pat in _ANALYTICS_PATTERNS:
        for m in pat.findall(html or ""):
            if m not in seen:
                seen.add(m)
                out.append(m)
    return out


def extract_org_strings(html: str) -> list[str]:
    """Org/registrant names from copyright footers (e.g. '© 2024 Acme Inc')."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _COPYRIGHT_RE.findall(html or ""):
        name = m.strip().rstrip(".,").strip()
        # Drop boilerplate that slips past the boundary.
        if len(name) < 3 or name.lower() in {"all rights reserved", "inc", "ltd"}:
            continue
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


@register("p4_verify")
class OrgFingerprint(Adapter):
    """Extract org-forest fingerprints (favicon hash, analytics ids, copyright).

    Active (fetches the host's homepage + /favicon.ico) and therefore gated
    behind ``--authorize-active``. Scope-checked before every request.
    """

    name = "org_fingerprint"
    category = "CAT-3"
    is_active = True
    consumes = ("subdomain", "live_host", "url")
    produces = ("favicon", "analytics_id", "org")

    async def run(self, ctx: AdapterContext) -> list[Event]:
        hosts: set[str] = set()
        for v in ctx.seeds_of("subdomain") + ctx.seeds_of("live_host"):
            h = (v or "").strip().lower()
            if h:
                hosts.add(h)
        for u in ctx.seeds_of("url"):
            h = host_of(u)
            if h:
                hosts.add(h)

        events: list[Event] = []
        for host in sorted(hosts):
            if not ctx.scope.contains("subdomain", host):
                continue
            events.extend(await self._fingerprint(ctx, host))
        return events

    async def _fingerprint(self, ctx: AdapterContext, host: str) -> list[Event]:
        events: list[Event] = []
        # Homepage -> analytics ids + copyright org.
        try:
            resp = await ctx.http.get(f"https://{host}/", bucket=f"orgfp:{host}")
            html = resp.text or ""
        except Exception:  # noqa: BLE001
            html = ""
        for aid in extract_analytics_ids(html):
            events.append(Event.asset(self.name, "analytics_id", aid))
            events.append(Event.edge(self.name, host, aid, "uses_analytics"))
        for org in extract_org_strings(html):
            events.append(Event.asset(self.name, "org", org))
            events.append(Event.edge(self.name, host, org, "copyright_org"))
        # Favicon -> Shodan-format hash (optional, needs mmh3).
        try:
            fresp = await ctx.http.get(f"https://{host}/favicon.ico", bucket=f"favicon:{host}")
            if fresp.status == 200 and fresp.content:
                fh = favicon_hash(fresp.content)
                if fh is not None:
                    events.append(Event.asset(self.name, "favicon", str(fh)))
                    events.append(Event.edge(self.name, host, str(fh), "has_favicon"))
        except Exception:  # noqa: BLE001
            pass
        return events
