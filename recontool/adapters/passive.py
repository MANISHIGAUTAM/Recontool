"""Passive adapters — no direct target contact.

These query third-party indexes/archives. They are safe to run before the
active-authorization gate. Each is keyless/free unless noted.
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
from urllib.parse import urlsplit

from recontool.adapters.base import Adapter, AdapterContext, Event
from recontool.adapters.registry import register

_JS_RE = re.compile(r"\.js(\?|$)", re.I)


# ─────────────────────────────────────────────────────────────────────────────
# CAT-2 / Certificate Transparency — crt.sh
# ─────────────────────────────────────────────────────────────────────────────
@register("p1_seed")
class CrtSh(Adapter):
    name = "crtsh"
    category = "CAT-2"
    is_active = False
    consumes = ("domain",)
    produces = ("subdomain", "cert")

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
                    if name and name.endswith(domain) and name not in seen:
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
                if host.endswith(domain):
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
                if host and host.endswith(domain):
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
                "subfinder", "-d", domain, "-silent", "-json",
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
