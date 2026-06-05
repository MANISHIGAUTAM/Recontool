"""Category 1 — Internet-Wide Search Engines & Asset Discovery  [PASSIVE].

These query third-party indexes (no target contact) to discover IPs, services,
certs, subdomains and exposures. Each adapter separates a PURE ``parse()`` method
(golden-file testable, offline) from ``run()`` (does HTTP + calls parse), per the
atomic-check methodology in docs/pipeline/02-plan-of-action.md.

Availability:
  - keyless + free  : urlscan, internetdb (run anywhere)
  - keyless CLI     : uncover (if binary present)
  - key-gated       : shodan, censys, netlas, leakix, fullhunt, criminalip
  - enrichment-only : greynoise (tags IPs, adds no new assets)
"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import shutil

from recontool.adapters.base import Adapter, AdapterContext, Event
from recontool.adapters.registry import register
from recontool.core.scope import is_subdomain_of


def _is_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s)
        return True
    except ValueError:
        return False


def _host_of(url: str) -> str:
    from urllib.parse import urlsplit

    if "://" in url:
        return (urlsplit(url).hostname or "").lower()
    return url.split("/")[0].lower()


# ─────────────────────────────────────────────────────────────────────────────
# uncover — wraps Shodan/Censys/FOFA/ZoomEye/Netlas in one CLI (Cat-1 entrypoint)
# ─────────────────────────────────────────────────────────────────────────────
@register("p1_seed")
class Uncover(Adapter):
    name = "uncover"
    category = "CAT-1"
    is_active = False
    consumes = ("domain",)
    produces = ("ip", "service", "subdomain")

    def available(self, ctx: AdapterContext) -> bool:
        return shutil.which("uncover") is not None

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        for domain in ctx.seeds_of("domain"):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "uncover", "-q", domain, "-json", "-silent",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                )
                out, _ = await proc.communicate()
            except Exception:
                continue
            text = out.decode(errors="ignore")
            ctx.artifacts.save_text("uncover", f"{domain}.jsonl", text)
            events.extend(self.parse(text, domain))
        return events

    @staticmethod
    def parse(text: str, domain: str) -> list[Event]:
        events: list[Event] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ip, port, host = rec.get("ip"), rec.get("port"), rec.get("host")
            if ip and _is_ip(ip):
                events.append(Event.asset("uncover", "ip", ip))
                if port:
                    events.append(Event.service("uncover", ip, int(port)))
            if host and host != ip and host.endswith(domain):
                events.append(Event.asset("uncover", "subdomain", host))
                if ip and _is_ip(ip):
                    events.append(Event.edge("uncover", host, ip, "resolves_to"))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# Shodan — host search (key) ; banners, ports, CVE hints, hostnames
# ─────────────────────────────────────────────────────────────────────────────
@register("p1_seed")
class Shodan(Adapter):
    name = "shodan"
    category = "CAT-1"
    is_active = False
    consumes = ("domain",)
    produces = ("ip", "service", "subdomain")
    key_env = "SHODAN_API_KEY"

    async def run(self, ctx: AdapterContext) -> list[Event]:
        key = ctx.api_keys.get("SHODAN_API_KEY")
        events: list[Event] = []
        for domain in ctx.seeds_of("domain"):
            try:
                resp = await ctx.http.get(
                    "https://api.shodan.io/shodan/host/search",
                    params={"key": key, "query": f"hostname:{domain}"}, bucket="shodan",
                )
            except Exception:
                continue
            if resp.json_ok:
                ctx.artifacts.save_raw("shodan", resp.json())
                events.extend(self.parse(resp.json(), domain))
        return events

    @staticmethod
    def parse(data: dict, domain: str) -> list[Event]:
        events: list[Event] = []
        for m in data.get("matches", []):
            ip = m.get("ip_str")
            port = m.get("port")
            if ip and _is_ip(ip):
                events.append(Event.asset("shodan", "ip", ip))
                if port:
                    events.append(Event.service(
                        "shodan", ip, int(port),
                        product=m.get("product"), version=m.get("version"),
                        banner=(m.get("data") or "")[:500],
                    ))
            for h in m.get("hostnames", []) or []:
                h = str(h).lower()
                if is_subdomain_of(h, domain):
                    events.append(Event.asset("shodan", "subdomain", h))
                    if ip and _is_ip(ip):
                        events.append(Event.edge("shodan", h, ip, "resolves_to"))
            for cve in (m.get("vulns") or []):
                if ip:
                    events.append(Event.finding(
                        "shodan", "cve", f"{cve} on {ip}", severity="medium",
                        detector="shodan", asset_value=ip, cve_id=cve,
                    ))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# InternetDB (free Shodan) — ports + CVEs + hostnames per IP, NO key/credits
# ─────────────────────────────────────────────────────────────────────────────
@register("p3_enrichment")
class InternetDB(Adapter):
    name = "internetdb"
    category = "CAT-1"
    is_active = False
    consumes = ("ip",)
    produces = ("service", "finding", "subdomain")
    MAX_IPS = 64

    async def run(self, ctx: AdapterContext) -> list[Event]:
        events: list[Event] = []
        ips = [ip for ip in ctx.seeds_of("ip") if ctx.scope.contains("ip", ip)][: self.MAX_IPS]
        for ip in ips:
            try:
                resp = await ctx.http.get(f"https://internetdb.shodan.io/{ip}", bucket="internetdb")
            except Exception:
                continue
            if resp.status == 200 and resp.json_ok:
                ctx.artifacts.save_raw("internetdb", resp.json())
                events.extend(self.parse(resp.json()))
        return events

    @staticmethod
    def parse(data: dict) -> list[Event]:
        events: list[Event] = []
        ip = data.get("ip")
        if not ip:
            return events
        for p in data.get("ports", []) or []:
            events.append(Event.service("internetdb", ip, int(p)))
        for h in data.get("hostnames", []) or []:
            events.append(Event.asset("internetdb", "subdomain", str(h).lower()))
            events.append(Event.edge("internetdb", str(h).lower(), ip, "resolves_to"))
        for cve in data.get("vulns", []) or []:
            events.append(Event.finding(
                "internetdb", "cve", f"{cve} on {ip}", severity="medium",
                detector="internetdb", asset_value=ip, cve_id=cve,
            ))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# Censys — host search (key id+secret) ; great cert/SAN -> subdomain pivots
# ─────────────────────────────────────────────────────────────────────────────
@register("p1_seed")
class Censys(Adapter):
    name = "censys"
    category = "CAT-1"
    is_active = False
    consumes = ("domain",)
    produces = ("ip", "service", "subdomain")

    def available(self, ctx: AdapterContext) -> bool:
        return bool(ctx.api_keys.get("CENSYS_API_ID") and ctx.api_keys.get("CENSYS_API_SECRET"))

    async def run(self, ctx: AdapterContext) -> list[Event]:
        uid = ctx.api_keys.get("CENSYS_API_ID")
        sec = ctx.api_keys.get("CENSYS_API_SECRET")
        auth = base64.b64encode(f"{uid}:{sec}".encode()).decode()
        events: list[Event] = []
        for domain in ctx.seeds_of("domain"):
            try:
                resp = await ctx.http.request(
                    "POST", "https://search.censys.io/api/v2/hosts/search",
                    headers={"Authorization": f"Basic {auth}", "Accept": "application/json"},
                    params={"q": domain, "per_page": 100}, bucket="censys",
                )
            except Exception:
                continue
            if resp.json_ok:
                ctx.artifacts.save_raw("censys", resp.json())
                events.extend(self.parse(resp.json(), domain))
        return events

    @staticmethod
    def parse(data: dict, domain: str) -> list[Event]:
        events: list[Event] = []
        for h in data.get("result", {}).get("hits", []) or []:
            ip = h.get("ip")
            if ip and _is_ip(ip):
                events.append(Event.asset("censys", "ip", ip))
            for svc in h.get("services", []) or []:
                port = svc.get("port")
                if ip and port:
                    events.append(Event.service(
                        "censys", ip, int(port), service_name=svc.get("service_name"),
                    ))
            dns = h.get("dns") or {}
            names = dns.get("names") or h.get("names") or []
            for name in names:
                name = str(name).lower().lstrip("*.")
                if is_subdomain_of(name, domain):
                    events.append(Event.asset("censys", "subdomain", name))
                    if ip and _is_ip(ip):
                        events.append(Event.edge("censys", name, ip, "resolves_to"))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# Netlas — domain search (key) ; modern Shodan/Censys alternative
# ─────────────────────────────────────────────────────────────────────────────
@register("p1_seed")
class Netlas(Adapter):
    name = "netlas"
    category = "CAT-1"
    is_active = False
    consumes = ("domain",)
    produces = ("subdomain",)
    key_env = "NETLAS_API_KEY"

    async def run(self, ctx: AdapterContext) -> list[Event]:
        key = ctx.api_keys.get("NETLAS_API_KEY")
        events: list[Event] = []
        for domain in ctx.seeds_of("domain"):
            try:
                resp = await ctx.http.get(
                    "https://app.netlas.io/api/domains/",
                    params={"q": f"domain:*.{domain}", "fields": "domain"},
                    headers={"X-API-Key": key}, bucket="netlas",
                )
            except Exception:
                continue
            if resp.json_ok:
                ctx.artifacts.save_raw("netlas", resp.json())
                events.extend(self.parse(resp.json(), domain))
        return events

    @staticmethod
    def parse(data: dict, domain: str) -> list[Event]:
        events: list[Event] = []
        for item in data.get("items", []) or []:
            d = (item.get("data") or {}).get("domain") or item.get("domain")
            if d:
                d = str(d).lower()
                if is_subdomain_of(d, domain):
                    events.append(Event.asset("netlas", "subdomain", d))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# LeakIX — exposed services & leaks for a domain (key)
# ─────────────────────────────────────────────────────────────────────────────
@register("p1_seed")
class LeakIX(Adapter):
    name = "leakix"
    category = "CAT-1"
    is_active = False
    consumes = ("domain",)
    produces = ("service", "finding", "ip")
    key_env = "LEAKIX_API_KEY"

    async def run(self, ctx: AdapterContext) -> list[Event]:
        key = ctx.api_keys.get("LEAKIX_API_KEY")
        events: list[Event] = []
        for domain in ctx.seeds_of("domain"):
            try:
                resp = await ctx.http.get(
                    f"https://leakix.net/domain/{domain}",
                    headers={"api-key": key, "Accept": "application/json"}, bucket="leakix",
                )
            except Exception:
                continue
            if resp.json_ok:
                ctx.artifacts.save_raw("leakix", resp.json())
                events.extend(self.parse(resp.json(), domain))
        return events

    @staticmethod
    def parse(data: dict, domain: str) -> list[Event]:
        events: list[Event] = []
        services = data.get("Services") or data.get("services") or []
        for svc in services:
            ip = svc.get("ip")
            port = svc.get("port")
            if ip and _is_ip(str(ip)):
                events.append(Event.asset("leakix", "ip", str(ip)))
                if port:
                    events.append(Event.service(
                        "leakix", str(ip), int(port), service_name=svc.get("protocol"),
                    ))
        for leak in data.get("Leaks") or data.get("leaks") or []:
            host = leak.get("host") or leak.get("ip") or ""
            events.append(Event.finding(
                "leakix", "exposure", leak.get("summary") or "LeakIX exposure",
                severity=leak.get("severity", "medium"), detector="leakix",
                asset_value=str(host),
            ))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# FullHunt — attack-surface subdomains (key)
# ─────────────────────────────────────────────────────────────────────────────
@register("p1_seed")
class FullHunt(Adapter):
    name = "fullhunt"
    category = "CAT-1"
    is_active = False
    consumes = ("domain",)
    produces = ("subdomain",)
    key_env = "FULLHUNT_API_KEY"

    async def run(self, ctx: AdapterContext) -> list[Event]:
        key = ctx.api_keys.get("FULLHUNT_API_KEY")
        events: list[Event] = []
        for domain in ctx.seeds_of("domain"):
            try:
                resp = await ctx.http.get(
                    f"https://fullhunt.io/api/v1/domain/{domain}/subdomains",
                    headers={"X-API-KEY": key}, bucket="fullhunt",
                )
            except Exception:
                continue
            if resp.json_ok:
                ctx.artifacts.save_raw("fullhunt", resp.json())
                events.extend(self.parse(resp.json(), domain))
        return events

    @staticmethod
    def parse(data: dict, domain: str) -> list[Event]:
        events: list[Event] = []
        for h in data.get("hosts", []) or data.get("subdomains", []) or []:
            host = h if isinstance(h, str) else h.get("host", "")
            host = str(host).lower()
            if is_subdomain_of(host, domain):
                events.append(Event.asset("fullhunt", "subdomain", host))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# urlscan.io — web intelligence search (keyless, lower limits). LIVE-testable.
# ─────────────────────────────────────────────────────────────────────────────
@register("p1_seed")
class UrlScan(Adapter):
    name = "urlscan"
    category = "CAT-1"
    is_active = False
    consumes = ("domain",)
    produces = ("url", "ip", "subdomain")

    async def run(self, ctx: AdapterContext) -> list[Event]:
        key = ctx.api_keys.get("URLSCAN_API_KEY")
        headers = {"API-Key": key} if key else {}
        events: list[Event] = []
        for domain in ctx.seeds_of("domain"):
            try:
                resp = await ctx.http.get(
                    "https://urlscan.io/api/v1/search/",
                    params={"q": f"domain:{domain}", "size": 100},
                    headers=headers, bucket="urlscan",
                )
            except Exception:
                continue
            if resp.json_ok:
                ctx.artifacts.save_raw("urlscan", resp.json())
                events.extend(self.parse(resp.json(), domain))
        return events

    @staticmethod
    def parse(data: dict, domain: str) -> list[Event]:
        events: list[Event] = []
        for r in data.get("results", []) or []:
            page = r.get("page", {}) or {}
            d = page.get("domain")
            url = page.get("url") or (r.get("task", {}) or {}).get("url")
            # urlscan's domain: search also returns pages that merely REFERENCE the
            # target (e.g. phishing hosted elsewhere). Keep only ON-TARGET results so
            # we don't pollute the inventory with unrelated hosts.
            host = (str(d).lower() if d else _host_of(url or ""))
            if not is_subdomain_of(host, domain):
                continue
            if url:
                events.append(Event.endpoint("urlscan", url, source="urlscan"))
            ip = page.get("ip")
            if ip and _is_ip(str(ip)):
                events.append(Event.asset("urlscan", "ip", str(ip)))
            events.append(Event.asset("urlscan", "subdomain", host))
            if ip and _is_ip(str(ip)):
                events.append(Event.edge("urlscan", host, str(ip), "resolves_to"))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# GreyNoise — ENRICHMENT OVERLAY: tag mass-scanner IPs (adds no new assets)
# ─────────────────────────────────────────────────────────────────────────────
@register("p3_enrichment")
class GreyNoise(Adapter):
    name = "greynoise"
    category = "CAT-1"
    is_active = False
    consumes = ("ip",)
    produces = ("tag",)
    MAX_IPS = 64

    async def run(self, ctx: AdapterContext) -> list[Event]:
        key = ctx.api_keys.get("GREYNOISE_API_KEY")
        headers = {"key": key} if key else {}
        events: list[Event] = []
        ips = [ip for ip in ctx.seeds_of("ip") if ctx.scope.contains("ip", ip)][: self.MAX_IPS]
        for ip in ips:
            try:
                resp = await ctx.http.get(
                    f"https://api.greynoise.io/v3/community/{ip}",
                    headers=headers, bucket="greynoise",
                )
            except Exception:
                continue
            if resp.json_ok:
                events.extend(self.parse(resp.json(), ip))
        return events

    @staticmethod
    def parse(data: dict, ip: str) -> list[Event]:
        tags: list[str] = []
        if data.get("noise"):
            tags.append("mass_scanner")
        if data.get("riot"):
            tags.append("common_business_service")
        cls = data.get("classification")
        if cls:
            tags.append(f"greynoise:{cls}")
        if tags:
            return [Event.asset("greynoise", "ip", ip, tags=tags)]
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Criminal IP — exposure intelligence (key)
# ─────────────────────────────────────────────────────────────────────────────
@register("p1_seed")
class CriminalIP(Adapter):
    name = "criminalip"
    category = "CAT-1"
    is_active = False
    consumes = ("domain",)
    produces = ("ip", "service")
    key_env = "CRIMINALIP_API_KEY"

    async def run(self, ctx: AdapterContext) -> list[Event]:
        key = ctx.api_keys.get("CRIMINALIP_API_KEY")
        events: list[Event] = []
        for domain in ctx.seeds_of("domain"):
            try:
                resp = await ctx.http.get(
                    "https://api.criminalip.io/v1/asset/domain/report",
                    params={"query": domain}, headers={"x-api-key": key}, bucket="criminalip",
                )
            except Exception:
                continue
            if resp.json_ok:
                ctx.artifacts.save_raw("criminalip", resp.json())
                events.extend(self.parse(resp.json(), domain))
        return events

    @staticmethod
    def parse(data: dict, domain: str) -> list[Event]:
        events: list[Event] = []
        # CriminalIP nests connected IPs under data.* — parse defensively.
        body = data.get("data", data) or {}
        for item in body.get("connected_ip", []) or body.get("ip_list", []) or []:
            ip = item.get("ip") if isinstance(item, dict) else item
            if ip and _is_ip(str(ip)):
                events.append(Event.asset("criminalip", "ip", str(ip)))
        return events
