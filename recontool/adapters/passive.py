"""Passive adapters — no direct target contact.

These query third-party indexes/archives. They are safe to run before the
active-authorization gate. Each is keyless/free unless noted.
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
from typing import Any
from urllib.parse import urlsplit

from recontool.adapters.base import Adapter, AdapterContext, Event
from recontool.adapters.registry import register
from recontool.core.scope import is_subdomain_of

_JS_RE = re.compile(r"\.js(\?|$)", re.I)


# ─────────────────────────────────────────────────────────────────────────────
# CAT-2 / Certificate Transparency — crt.sh
# ─────────────────────────────────────────────────────────────────────────────
@register("p1_seed")
class CrtSh(Adapter):
    """Certificate Transparency adapter using crt.sh API.

    This adapter serves as the reference implementation for the full
    adapter contract. All contract methods are implemented below while
    the existing run() method remains unchanged for backward compatibility.
    """

    name = "crtsh"
    category = "CAT-2"
    is_active = False
    consumes = ("domain",)
    produces = ("subdomain", "cert")

    # ------------------------------------------------------------------
    # Extended contract implementation (event-driven engine)
    # ------------------------------------------------------------------

    def install_check(self) -> bool:
        """Always True for API-based adapters (no binary required)."""
        return True

    def prepare(self, ctx: AdapterContext) -> None:
        """No preparation needed for API adapters."""

    def validate_inputs(self, inputs: dict[str, Any]) -> list[str]:
        """Validate that at least one domain seed is provided."""
        errors: list[str] = []
        domains = inputs.get("domain", [])
        if not domains:
            errors.append("At least one domain seed is required")
        for d in domains:
            if not isinstance(d, str) or not d.strip():
                errors.append(f"Invalid domain value: {d!r}")
        return errors

    def build_command(self, ctx: AdapterContext) -> str | None:
        """Returns None - crt.sh is an API adapter, not a CLI tool."""
        return None

    def parse_stdout(self, stdout: str) -> dict[str, Any]:
        """Parse crt.sh JSON response into structured output."""
        if not stdout.strip():
            return {"subdomains": [], "certificates": []}
        try:
            rows = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            return {"raw": stdout, "subdomains": [], "certificates": []}
        if not isinstance(rows, list):
            return {"raw": stdout, "subdomains": [], "certificates": []}
        subdomains: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for name in str(row.get("name_value", "")).splitlines():
                name = name.strip().lstrip("*.").lower()
                if name and name not in seen:
                    seen.add(name)
                    subdomains.append(name)
        return {
            "subdomains": subdomains,
            "certificates": [
                {
                    "id": row.get("id"),
                    "issuer": row.get("issuer_name"),
                    "not_before": row.get("not_before"),
                    "not_after": row.get("not_after"),
                }
                for row in rows[:100]  # cap to avoid huge payloads
            ],
        }

    def emit_normalized_events(self, parsed: dict[str, Any]) -> list[Event]:
        """Convert parsed crt.sh output into normalized Event objects."""
        events: list[Event] = []
        for subdomain in parsed.get("subdomains", []):
            events.append(Event.asset(self.name, "subdomain", subdomain))
        return events

    def map_outputs_to_entities(self, parsed: dict[str, Any]) -> list[Event]:
        """Map parsed outputs to entity discovery events.

        Delegates to emit_normalized_events to avoid logic duplication.
        """
        return self.emit_normalized_events(parsed)

    def resolve_pending_keys(self, parsed: dict[str, Any]) -> list[str]:
        """Return subdomain pending key values this output resolves."""
        return parsed.get("subdomains", [])

    def can_run_in_parallel(self) -> bool:
        """crt.sh is safe to run concurrently."""
        return True

    def dependencies(self) -> list[str]:
        """No dependencies - crt.sh runs from seed domains only."""
        return []

    def timeout_seconds(self) -> int:
        """30 second timeout for API requests."""
        return 30

    def retry_policy(self) -> dict[str, Any]:
        """Retry on transient HTTP errors."""
        return {
            "max_retries": 2,
            "backoff_factor": 1.5,
            "retryable_errors": ["timeout", "connection_error", "502", "503"],
        }

    # ------------------------------------------------------------------
    # Original run() method (unchanged)
    # ------------------------------------------------------------------

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        for domain in ctx.seeds_of("domain"):
            try:
                resp = await ctx.http.get(
                    "https://crt.sh/", params={"q": f"%.{domain}", "output": "json"},
                    bucket="crtsh",
                )
            except Exception:
                continue
            if not resp.json_ok:
                continue
            ctx.artifacts.save_raw("crtsh", resp.json())
            seen: set[str] = set()
            for row in resp.json():
                for name in str(row.get("name_value", "")).splitlines():
                    name = name.strip().lstrip("*.").lower()
                    if name and name not in seen and is_subdomain_of(name, domain):
                        seen.add(name)
                        events.append(Event.asset(self.name, "subdomain", name))
                        events.append(Event.edge(self.name, name, domain, "subdomain_of"))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# CAT-2 — HackerTarget hostsearch (gives subdomain -> IP pairs)
# ─────────────────────────────────────────────────────────────────────────────
@register("p1_seed")
class HackerTarget(Adapter):
    name = "hackertarget"
    category = "CAT-2"
    is_active = False
    consumes = ("domain",)
    produces = ("subdomain", "ip")

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        for domain in ctx.seeds_of("domain"):
            try:
                resp = await ctx.http.get(
                    "https://api.hackertarget.com/hostsearch/",
                    params={"q": domain}, bucket="hackertarget",
                )
            except Exception:
                continue
            text = resp.text or ""
            if "API count exceeded" in text or "error" in text.lower():
                continue
            ctx.artifacts.save_text("hackertarget", f"{domain}.txt", text)
            for line in text.splitlines():
                if "," not in line:
                    continue
                host, ip = line.split(",", 1)
                host, ip = host.strip().lower(), ip.strip()
                if is_subdomain_of(host, domain):
                    events.append(Event.asset(self.name, "subdomain", host))
                    events.append(Event.asset(self.name, "ip", ip))
                    events.append(Event.edge(self.name, host, ip, "resolves_to"))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# CAT-1 — AlienVault OTX passive DNS (keyless basic access)
# ─────────────────────────────────────────────────────────────────────────────
@register("p1_seed")
class AlienVaultOTX(Adapter):
    name = "alienvault_otx"
    category = "CAT-1"
    is_active = False
    consumes = ("domain",)
    produces = ("subdomain", "ip")

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        for domain in ctx.seeds_of("domain"):
            url = f"https://otx.alienvault.com/api/v1/indicators/domain/{domain}/passive_dns"
            try:
                resp = await ctx.http.get(url, bucket="otx")
            except Exception:
                continue
            if not resp.json_ok:
                continue
            data = resp.json()
            ctx.artifacts.save_raw("otx", data)
            for rec in data.get("passive_dns", []):
                host = str(rec.get("hostname", "")).strip().lower()
                ip = str(rec.get("address", "")).strip()
                if host and is_subdomain_of(host, domain):
                    events.append(Event.asset(self.name, "subdomain", host))
                    if ip and _looks_ip(ip):
                        events.append(Event.asset(self.name, "ip", ip))
                        events.append(Event.edge(self.name, host, ip, "resolves_to"))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# CAT-2 — subfinder CLI wrapper (graceful: only runs if binary present)
# ─────────────────────────────────────────────────────────────────────────────
@register("p2_expansion")
class Subfinder(Adapter):
    name = "subfinder"
    category = "CAT-2"
    is_active = False
    consumes = ("domain",)
    produces = ("subdomain",)

    def available(self, ctx: AdapterContext) -> bool:
        return shutil.which("subfinder") is not None

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        for domain in ctx.seeds_of("domain"):
            proc = await asyncio.create_subprocess_exec(
                "subfinder", "-d", domain, "-all", "-silent", "-json",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await proc.communicate()
            raw_lines = out.decode(errors="ignore").splitlines()
            ctx.artifacts.save_text("subfinder", f"{domain}.jsonl", "\n".join(raw_lines))
            for line in raw_lines:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                host = str(rec.get("host", "")).strip().lower()
                if host:
                    events.append(Event.asset(self.name, "subdomain", host))
                    events.append(Event.edge(self.name, host, domain, "subdomain_of"))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# CAT-4/6 — Wayback Machine URL harvest + JS file download to filesystem
# ─────────────────────────────────────────────────────────────────────────────
@register("p3_enrichment")
class Wayback(Adapter):
    name = "wayback"
    category = "CAT-6"
    is_active = False
    consumes = ("domain",)
    produces = ("url",)
    MAX_URLS = 3000
    MAX_JS = 40  # cap JS downloads per scan to stay polite / bounded

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        js_downloaded = 0
        for domain in ctx.seeds_of("domain"):
            cdx = (
                "http://web.archive.org/cdx/search/cdx"
                f"?url=*.{domain}/*&output=json&fl=original&collapse=urlkey&limit={self.MAX_URLS}"
            )
            try:
                resp = await ctx.http.get(cdx, bucket="wayback")
            except Exception:
                continue
            if not resp.json_ok:
                continue
            rows = resp.json()
            ctx.artifacts.save_raw("wayback", rows)
            urls = [r[0] for r in rows[1:]] if rows and isinstance(rows[0], list) else []
            for url in urls:
                events.append(Event.endpoint(self.name, url, source="wayback"))
                # Download JS files to the filesystem (chaining input for JS mining).
                if js_downloaded < self.MAX_JS and _JS_RE.search(url):
                    ref = await self._fetch_js(ctx, url)
                    if ref:
                        js_downloaded += 1
                        events.append(
                            Event.endpoint(self.name, url, source="wayback", js_artifact=ref)
                        )
        return events

    async def _fetch_js(self, ctx: AdapterContext, url: str) -> str | None:
        try:
            resp = await ctx.http.get(url, bucket="wayback_js")
        except Exception:
            return None
        if resp.status != 200 or not resp.content:
            return None
        host = urlsplit(url).hostname or "unknown"
        fname = (urlsplit(url).path.rsplit("/", 1)[-1] or "index") + ""
        return ctx.artifacts.save_js(host, fname, resp.content)


def _looks_ip(s: str) -> bool:
    import ipaddress

    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False
