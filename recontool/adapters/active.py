"""Active adapters — these TOUCH the target. Only reachable after the
active-authorization gate (docs/D2-recon-flow.md, ADR-009). Each re-checks scope
before egress.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from recontool.adapters.base import Adapter, AdapterContext, Event, log_tool_io
from recontool.adapters.registry import register
from recontool.config import settings

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)

# Top ports for the fallback connect-scanner (used if naabu is absent).
_TOP_PORTS = [80, 443, 8080, 8443, 8000, 8888, 3000, 5000, 22, 21, 25, 3306, 6379, 27017]

# Secret patterns -> store REDACTED only (hash + mask + location), never raw.
_SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "google_api_key": re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    "slack_token": re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}"),
    "generic_api_key": re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"][0-9a-zA-Z\-_]{16,}['\"]"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
}
_ENDPOINT_RE = re.compile(r"""['"](/[A-Za-z0-9_\-/.]{2,}|https?://[^\s'"]+)['"]""")


def _scoped(ctx: AdapterContext, atype: str, value: str) -> bool:
    return ctx.scope.contains(atype, value)


# ─────────────────────────────────────────────────────────────────────────────
# P4 — DNS resolution + liveness (pure-Python via dnspython async resolver)
# ─────────────────────────────────────────────────────────────────────────────
@register("p4_verify")
class DnsResolve(Adapter):
    name = "dns_resolve"
    category = "CAT-2"
    is_active = True
    consumes = ("subdomain", "domain")
    produces = ("ip",)

    async def run(self, ctx: AdapterContext) -> list[Event]:
        import dns.asyncresolver

        resolver = dns.asyncresolver.Resolver()
        resolver.lifetime = 5.0
        hosts = sorted(set(ctx.seeds_of("subdomain") + ctx.seeds_of("domain")))
        sem = asyncio.Semaphore(max(1, int(ctx.profile.dns_qps)))
        events: list[Event] = []

        async def resolve(host: str):
            if not _scoped(ctx, "subdomain", host):
                return
            async with sem:
                for rtype in ("A", "AAAA", "CNAME"):
                    try:
                        ans = await resolver.resolve(host, rtype)
                    except Exception:
                        continue
                    for r in ans:
                        val = r.to_text().rstrip(".")
                        if rtype in ("A", "AAAA"):
                            events.append(Event.asset(self.name, "ip", val))
                            events.append(Event.edge(self.name, host, val, "resolves_to"))
                            events.append(Event.asset(self.name, "subdomain", host, is_live=True))
                        elif rtype == "CNAME":
                            events.append(Event.edge(self.name, host, val, "cname_to"))

        await asyncio.gather(*(resolve(h) for h in hosts))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# P4 — HTTP/S probing (status, title, server, tech hints)
# ─────────────────────────────────────────────────────────────────────────────
@register("p4_verify")
class HttpProbe(Adapter):
    name = "httpx_probe"
    category = "CAT-5"
    is_active = True
    consumes = ("subdomain", "domain")
    produces = ("live_host", "service")

    async def run(self, ctx: AdapterContext) -> list[Event]:
        hosts = sorted(set(ctx.seeds_of("subdomain") + ctx.seeds_of("domain")))
        sem = asyncio.Semaphore(ctx.profile.per_host_concurrency * 4 or 4)
        events: list[Event] = []

        async def probe(host: str):
            if not _scoped(ctx, "subdomain", host):
                return
            for scheme in ("https", "http"):
                url = f"{scheme}://{host}"
                async with sem:
                    try:
                        resp = await ctx.http.get(url, bucket=f"probe:{host}")
                    except Exception:
                        continue
                title = ""
                m = _TITLE_RE.search(resp.text or "")
                if m:
                    title = m.group(1).strip()[:300]
                server = resp.headers.get("server", "")
                tech = _tech_hints(resp.headers, resp.text or "")
                events.append(
                    Event.endpoint(
                        self.name, resp.url, status=resp.status, title=title,
                        server=server, tech=tech, scheme=scheme,
                    )
                )
                events.append(
                    Event.service(
                        self.name, host, 443 if scheme == "https" else 80,
                        service_name=scheme, product=server,
                    )
                )
                events.append(Event.asset(self.name, "subdomain", host, is_live=True, tech=tech))
                # Emit the confirmed-live root as a RECURSABLE `live_host` asset — the
                # validation gate (M3). Only httpx-confirmed hosts get this type, and the
                # active/deep layer (whatweb, gowitness, tlsx, katana, ffuf, feroxbuster,
                # nuclei) consumes `live_host`, so it NEVER fires on an unvalidated
                # subdomain — exactly "validate live, then scan". Bounded to the live set
                # (~tens), never the gau/wayback firehose. discovered_assets() re-feeds
                # entity=asset, so this enqueues the live_host key for the gated tools.
                events.append(Event.asset(self.name, "live_host", url, is_live=True))
                break  # one successful scheme is enough
        await asyncio.gather(*(probe(h) for h in hosts))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# P4 — Port scan (naabu if present, else bounded async connect-scan fallback)
# ─────────────────────────────────────────────────────────────────────────────
@register("p4_verify")
class PortScan(Adapter):
    name = "naabu"
    category = "CAT-5"
    is_active = True
    consumes = ("ip", "subdomain")
    produces = ("service",)

    async def run(self, ctx: AdapterContext) -> list[Event]:
        targets = sorted(set(ctx.seeds_of("ip") + ctx.seeds_of("subdomain")))
        targets = [t for t in targets if _scoped(ctx, "ip", t) or _scoped(ctx, "subdomain", t)]
        if shutil.which("naabu"):
            return await self._naabu(ctx, targets)
        return await self._fallback(ctx, targets)

    async def _naabu(self, ctx: AdapterContext, targets: list[str]) -> list[Event]:
        events: list[Event] = []
        ports = {"top-100": "100", "top-1000": "1000", "full": "-"}.get(ctx.profile.port_set, "100")
        flag = "-top-ports" if ports != "-" else "-p"
        arg = ports if ports != "-" else "-"
        argv = ["naabu", "-host", ",".join(targets), flag, arg, "-silent", "-json"]
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        log_tool_io("naabu", ",".join(targets), argv, out.decode(errors="ignore"))
        for line in out.decode(errors="ignore").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            host, port = rec.get("host") or rec.get("ip"), rec.get("port")
            if host and port:
                events.append(Event.service(self.name, host, int(port)))
        return events

    async def _fallback(self, ctx: AdapterContext, targets: list[str]) -> list[Event]:
        events: list[Event] = []
        ports = _TOP_PORTS if ctx.profile.port_set != "full" else _TOP_PORTS
        sem = asyncio.Semaphore(ctx.profile.global_concurrency or 10)

        async def check(host: str, port: int):
            async with sem:
                try:
                    fut = asyncio.open_connection(host, port)
                    reader, writer = await asyncio.wait_for(fut, timeout=3.0)
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass
                    events.append(Event.service("portscan", host, port))
                except Exception:
                    return

        await asyncio.gather(*(check(h, p) for h in targets for p in ports))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# P5 — nmap service/version scan (handwritten: the generic CLI adapter has no XML
# parser, and nmap's greppable output can't be split into one service-per-port).
# Deep -sV/-sC on top of naabu's fast discovery; opt-in (default_on=False).
# ─────────────────────────────────────────────────────────────────────────────
def _parse_nmap_xml(xml_text: str, fallback_host: str, tool: str) -> list[Event]:
    """One Event.service per OPEN port from nmap -oX output, with version info."""
    import xml.etree.ElementTree as ET

    events: list[Event] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return events
    for host_el in root.findall("host"):
        addr = next((a.get("addr") for a in host_el.findall("address")
                     if a.get("addrtype") in ("ipv4", "ipv6")), None)
        hn = host_el.find("hostnames/hostname")
        host = (hn.get("name") if hn is not None else None) or addr or fallback_host
        for port_el in host_el.findall("ports/port"):
            state = port_el.find("state")
            if state is None or state.get("state") != "open":
                continue
            svc = port_el.find("service")
            attrs: dict = {}
            if svc is not None:
                if svc.get("name"):
                    attrs["service_name"] = svc.get("name")
                product = " ".join(x for x in (svc.get("product"), svc.get("version")) if x)
                if product:
                    attrs["product"] = product
            try:
                events.append(Event.service(tool, host, int(port_el.get("portid")), **attrs))
            except (TypeError, ValueError):
                continue
    return events


@register("p5_deep")
class NmapServiceScan(Adapter):
    name = "nmap"
    category = "CAT-21"
    is_active = True
    default_on = False            # heavy -sV/-sC; available but opt-in
    consumes = ("ip", "subdomain")
    produces = ("service",)

    def available(self, ctx: AdapterContext) -> bool:
        return shutil.which("nmap") is not None

    async def run(self, ctx: AdapterContext) -> list[Event]:
        targets = sorted(set(ctx.seeds_of("ip") + ctx.seeds_of("subdomain")))
        targets = [t for t in targets
                   if _scoped(ctx, "ip", t) or _scoped(ctx, "subdomain", t)][:50]
        if not targets:
            return []
        port_args = {"top-100": ["--top-ports", "100"],
                     "top-1000": ["--top-ports", "1000"],
                     "full": ["-p-"]}.get(ctx.profile.port_set, ["--top-ports", "100"])
        events: list[Event] = []
        sem = asyncio.Semaphore(max(2, (ctx.profile.global_concurrency or 8) // 4))

        async def scan(host: str):
            async with sem:
                proc = None
                try:
                    argv = ["nmap", "-sV", "-sC", "-T4", "-Pn", *port_args, "-oX", "-", host]
                    proc = await asyncio.create_subprocess_exec(
                        *argv,
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    )
                    out, _ = await asyncio.wait_for(proc.communicate(), timeout=600)
                except Exception:  # noqa: BLE001 — timeout/spawn failure: reap + skip
                    if proc is not None and proc.returncode is None:
                        proc.kill()
                        await proc.wait()
                    return
                log_tool_io("nmap", host, argv, out.decode(errors="ignore"))
                events.extend(_parse_nmap_xml(out.decode(errors="ignore"), host, self.name))

        await asyncio.gather(*(scan(h) for h in targets))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# P6 — sslyze TLS audit (handwritten: the generic emit can't navigate sslyze's
# deeply-nested server_scan_results[].scan_result.{...}.result tree to fan out
# the dozen heterogeneous finding types). Maps the result to TLS findings.
# ─────────────────────────────────────────────────────────────────────────────
# protocol-scan key -> (label, severity) when accepted_cipher_suites is non-empty
_DEPRECATED_TLS = {
    "ssl_2_0_cipher_suites": ("SSLv2", "critical"),
    "ssl_3_0_cipher_suites": ("SSLv3", "high"),
    "tls_1_0_cipher_suites": ("TLS 1.0", "medium"),
    "tls_1_1_cipher_suites": ("TLS 1.1", "medium"),
}


def _parse_sslyze_json(text: str, fallback_host: str, tool: str) -> list[Event]:
    """sslyze --json_out -> TLS findings. raw_decode() because sslyze appends
    trailing content after the JSON document."""
    events: list[Event] = []
    try:
        d, _ = json.JSONDecoder().raw_decode(text.lstrip())
    except (ValueError, json.JSONDecodeError):
        return events
    for r in d.get("server_scan_results", []):
        loc = r.get("server_location") or {}
        host = loc.get("hostname") or fallback_host
        target = f"{host}:{loc.get('port', 443)}"
        sr = r.get("scan_result") or {}

        def _res(key: str):
            v = sr.get(key) or {}
            return (v.get("result") or {}) if v.get("status") == "COMPLETED" else {}

        def _add(title: str, kind: str, severity: str, cve: str | None = None):
            events.append(Event.finding(tool, kind, title, severity=severity,
                                        asset_value=target, cve_id=cve, detector=tool))

        if _res("heartbleed").get("is_vulnerable_to_heartbleed"):
            _add(f"Heartbleed on {target}", "tls_vuln", "critical", "CVE-2014-0160")
        if _res("openssl_ccs_injection").get("is_vulnerable_to_ccs_injection"):
            _add(f"OpenSSL CCS injection on {target}", "tls_vuln", "high", "CVE-2014-0224")
        robot = str(_res("robot").get("robot_result", ""))
        if robot.startswith("VULNERABLE"):
            _add(f"ROBOT attack ({robot}) on {target}", "tls_vuln", "high")
        for key, (label, sev) in _DEPRECATED_TLS.items():
            if _res(key).get("accepted_cipher_suites"):
                _add(f"Deprecated protocol {label} enabled on {target}", "weak_tls", sev)
        for dep in _res("certificate_info").get("certificate_deployments", []):
            if dep.get("verified_chain_has_sha1_signature"):
                _add(f"SHA-1 signature in certificate chain on {target}", "weak_tls", "medium")
            for pv in dep.get("path_validation_results", []):
                if pv.get("was_validation_successful") is False:
                    err = pv.get("validation_error") or "validation failed"
                    _add(f"Certificate validation failed on {target}: {err}", "cert_invalid", "high")
                    break
    return events


# ─────────────────────────────────────────────────────────────────────────────
# P5 — whatweb tech fingerprint (handwritten: whatweb's --log-json is a JSON
# ARRAY whose element has a `plugins` DICT — the generic emit can iterate a list
# but not a dict's keys; and the plain-text summary pollutes stdout. Writing
# --log-json to a temp file sidesteps both. Establishes the "tech as findings"
# model the pipeline otherwise lacks.)
# ─────────────────────────────────────────────────────────────────────────────
def _parse_whatweb_json(text: str, target: str, tool: str) -> list[Event]:
    """whatweb --log-json (a JSON array) -> one tech finding per target listing
    the detected technologies (the `plugins` dict keys)."""
    events: list[Event] = []
    try:
        data = json.loads(text or "[]")
    except json.JSONDecodeError:
        return events
    if not isinstance(data, list):
        return events
    for entry in data:
        if not isinstance(entry, dict):
            continue
        plugins = entry.get("plugins") or {}
        techs = sorted(k for k in plugins if isinstance(k, str))
        if not techs:
            continue
        # F2: emit each detected technology as a first-class `tech` asset (recorded
        # evidence — feeds OSINT/forest, reporting, prioritization, and the future
        # CMS->scanner / tech->CPE->CVE flows). Grounded in whatweb's real plugin keys.
        for t in techs:
            events.append(Event.asset(tool, "tech", t))
        events.append(Event.finding(
            tool, "tech", f"Tech stack on {target}: {', '.join(techs[:20])}",
            severity="info", detector=tool, asset_value=target,
            evidence_redacted={"technologies": techs},
        ))
    return events


@register("p5_deep")
class WhatWebScan(Adapter):
    name = "whatweb"
    category = "CAT-5"
    is_active = True
    default_on = False
    consumes = ("live_host",)  # fingerprint only httpx-validated hosts (M3 gate)
    produces = ("tech", "finding")  # F2: first-class tech entities + the summary finding

    def available(self, ctx: AdapterContext) -> bool:
        return shutil.which("whatweb") is not None

    async def run(self, ctx: AdapterContext) -> list[Event]:
        # M3 gate: fingerprint only httpx-validated live hosts (live_host values are
        # full URLs, e.g. "https://app.example.com"); the host is parsed back out for
        # the finding's asset linkage.
        targets = [u for u in sorted(set(ctx.seeds_of("live_host")))
                   if _scoped(ctx, "live_host", u)][:50]
        if not targets:
            return []
        events: list[Event] = []
        sem = asyncio.Semaphore(max(2, (ctx.profile.global_concurrency or 8) // 2))

        async def scan(target: str):
            host = urlsplit(target).hostname or target
            async with sem:
                fd, tmp = tempfile.mkstemp(suffix=".json", prefix="ww_")
                os.close(fd)
                proc = None
                try:
                    argv = ["whatweb", "--no-errors", "--quiet", f"--log-json={tmp}",
                            target]
                    proc = await asyncio.create_subprocess_exec(
                        *argv,
                        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                    await asyncio.wait_for(proc.communicate(), timeout=90)
                    with open(tmp, encoding="utf-8", errors="ignore") as fh:
                        ww_out = fh.read()
                    log_tool_io("whatweb", target, argv, ww_out)
                    events.extend(_parse_whatweb_json(ww_out, host, self.name))
                except Exception:  # noqa: BLE001 — timeout/spawn/read failure: reap + skip
                    if proc is not None and proc.returncode is None:
                        proc.kill()
                        await proc.wait()
                finally:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass

        await asyncio.gather(*(scan(t) for t in targets))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# P5 — gowitness screenshots (handwritten: it's an EVIDENCE tool — output is PNG
# files + a DB, not stdout entities. Runs gowitness into the scan's artifact dir,
# then emits a `screenshot` asset per image it produced, so the visual evidence is
# inventoried/queryable. The CLI form is version-robust: screenshot, then glob.)
# ─────────────────────────────────────────────────────────────────────────────
@register("p5_deep")
class GoWitness(Adapter):
    name = "gowitness"
    category = "CAT-13"
    is_active = True
    default_on = False
    consumes = ("live_host",)  # screenshot only httpx-validated hosts (M3 gate)
    produces = ("screenshot",)

    def available(self, ctx: AdapterContext) -> bool:
        return shutil.which("gowitness") is not None

    async def run(self, ctx: AdapterContext) -> list[Event]:
        # M3 gate: screenshot only httpx-validated live hosts (live_host values are
        # already full URLs, written straight to the target list).
        targets = [u for u in sorted(set(ctx.seeds_of("live_host")))
                   if _scoped(ctx, "live_host", u)][:50]
        if not targets:
            return []
        shotdir = ctx.artifacts.root / "screenshots"
        shotdir.mkdir(parents=True, exist_ok=True)
        before = set(shotdir.glob("*.jpeg")) | set(shotdir.glob("*.png"))
        fd, listfile = tempfile.mkstemp(suffix=".txt", prefix="gw_")
        with os.fdopen(fd, "w") as fh:
            fh.write("\n".join(targets))
        argv = ["gowitness", "scan", "file", "-f", listfile,
                "--screenshot-path", str(shotdir), "--timeout", "15"]
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await asyncio.wait_for(proc.communicate(), timeout=600)
        except Exception:  # noqa: BLE001 — timeout/spawn: reap + continue (glob anyway)
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
        finally:
            try:
                os.unlink(listfile)
            except OSError:
                pass
        new_shots = (set(shotdir.glob("*.jpeg")) | set(shotdir.glob("*.png"))) - before
        log_tool_io("gowitness", f"{len(targets)} hosts", argv,
                    note=f"wrote {len(new_shots)} screenshots → {shotdir.name}/")
        return [Event.asset(self.name, "screenshot",
                            str(img.relative_to(settings.artifact_dir)))
                for img in sorted(new_shots)]


@register("p6_vuln")
class SslyzeScan(Adapter):
    name = "sslyze"
    category = "CAT-24"
    is_active = True
    default_on = False            # deep TLS audit; available but opt-in
    consumes = ("subdomain",)
    produces = ("finding",)

    def available(self, ctx: AdapterContext) -> bool:
        return shutil.which("sslyze") is not None

    async def run(self, ctx: AdapterContext) -> list[Event]:
        targets = [h for h in sorted(set(ctx.seeds_of("subdomain")))
                   if _scoped(ctx, "subdomain", h)][:50]
        if not targets:
            return []
        events: list[Event] = []
        sem = asyncio.Semaphore(max(2, (ctx.profile.global_concurrency or 8) // 4))

        async def scan(host: str):
            async with sem:
                proc = None
                try:
                    argv = ["sslyze", "--quiet", "--json_out=/dev/stdout", f"{host}:443"]
                    proc = await asyncio.create_subprocess_exec(
                        *argv,
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    )
                    out, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
                except Exception:  # noqa: BLE001 — timeout/spawn: reap + skip
                    if proc is not None and proc.returncode is None:
                        proc.kill()
                        await proc.wait()
                    return
                log_tool_io("sslyze", f"{host}:443", argv, out.decode(errors="ignore"))
                events.extend(_parse_sslyze_json(out.decode(errors="ignore"), host, self.name))

        await asyncio.gather(*(scan(h) for h in targets))
        return events


# ─────────────────────────────────────────────────────────────────────────────
# P5 — JS analysis: read JS harvested to the FS, extract endpoints + secrets
# ─────────────────────────────────────────────────────────────────────────────
@register("p5_deep")
class JsAnalyze(Adapter):
    name = "js_analyze"
    category = "CAT-4"
    is_active = False  # operates on already-downloaded files
    consumes = ("js_file",)  # M5: gated to harvested .js files, not every url
    produces = ("url", "finding")

    async def run(self, ctx: AdapterContext) -> list[Event]:
        # M5: process exactly the JS files pycrawl harvested and emitted as js_file
        # assets (absolute paths) — "js scan on js files only", not a blind rescan of
        # the whole js dir on every discovered url.
        events: list[Event] = []
        for js_path in ctx.seeds_of("js_file"):
            path = Path(js_path)
            if not path.exists():
                continue
            try:
                text = path.read_text(errors="ignore")
            except Exception:
                continue
            host = path.parent.name
            for m in set(_ENDPOINT_RE.findall(text)):
                if m.startswith("/") or m.startswith("http"):
                    events.append(Event.endpoint(self.name, _abs(host, m), source="js"))
            for kind, pat in _SECRET_PATTERNS.items():
                for match in pat.findall(text):
                    secret = match if isinstance(match, str) else match[0]
                    events.append(
                        Event.finding(
                            self.name, "secret", f"Possible {kind} in JS",
                            severity="high", detector=f"js_analyze:{kind}",
                            asset_value=host,
                            evidence_redacted={
                                "type": kind,
                                "preview": _mask(secret),
                                "sha1": hashlib.sha1(secret.encode()).hexdigest(),
                                "file": str(path.relative_to(settings.artifact_dir)),
                            },
                        )
                    )
        return events


# ─────────────────────────────────────────────────────────────────────────────
# P6 — nuclei (graceful: only if binary present). Detection-only.
# ─────────────────────────────────────────────────────────────────────────────
@register("p6_vuln")
class Nuclei(Adapter):
    name = "nuclei"
    category = "CAT-10"
    is_active = True
    consumes = ("live_host", "url")  # validated hosts + crawled URLs (M3 gate)
    produces = ("finding",)

    def available(self, ctx: AdapterContext) -> bool:
        return shutil.which("nuclei") is not None

    async def run(self, ctx: AdapterContext) -> list[Event]:
        # M3 gate: scan httpx-validated live hosts AND crawled URLs (both are URL
        # strings). Never fires on a bare, unvalidated subdomain.
        urls = sorted(set(ctx.seeds_of("live_host")) | set(ctx.seeds_of("url")))
        if not urls:
            return []
        list_path = settings.artifact_dir / ctx.scan_id / "nuclei_targets.txt"
        list_path.parent.mkdir(parents=True, exist_ok=True)
        list_path.write_text("\n".join(urls))
        sev = ",".join(ctx.profile.nuclei_severities) or "low,medium,high,critical"
        argv = ["nuclei", "-l", str(list_path), "-jsonl", "-silent", "-severity", sev,
                "-rl", str(int(ctx.profile.requests_per_second))]
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate()
        raw_text = out.decode(errors="ignore")
        log_tool_io("nuclei", urls, argv, raw_text)
        # Always archive nuclei's raw output per primary key (appended, never
        # overwritten) — so even a 0-finding run on a WAF-blocked host leaves a
        # nuclei record on disk (out/nuclei.raw.jsonl) showing exactly which
        # targets were scanned at which severities, and any raw matches.
        ctx.artifacts.append_jsonl("nuclei.raw", [{
            "targets": urls, "severity": sev,
            "matched": len([ln for ln in raw_text.splitlines() if ln.strip()]),
            "stdout": raw_text,
        }])
        events: list[Event] = []
        for line in raw_text.splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            info = rec.get("info", {})
            events.append(
                Event.finding(
                    self.name, "cve" if rec.get("template-id", "").startswith("CVE") else "exposure",
                    info.get("name", rec.get("template-id", "nuclei finding")),
                    severity=info.get("severity", "info"),
                    detector=f"nuclei:{rec.get('template-id')}",
                    asset_value=rec.get("host", ""),
                    cve_id=_first_cve(info),
                    evidence_redacted={"matched_at": rec.get("matched-at")},
                )
            )
        return events


# ── helpers ──────────────────────────────────────────────────────────────────
def _tech_hints(headers: dict, body: str) -> list[str]:
    hints: list[str] = []
    server = headers.get("server", "").lower()
    powered = headers.get("x-powered-by", "").lower()
    for token, label in [
        ("nginx", "nginx"), ("apache", "apache"), ("cloudflare", "cloudflare"),
        ("express", "express"), ("php", "php"), ("iis", "iis"),
    ]:
        if token in server or token in powered:
            hints.append(label)
    if "wp-content" in body:
        hints.append("wordpress")
    if "react" in body.lower():
        hints.append("react")
    return sorted(set(hints))


def _abs(host: str, path: str) -> str:
    if path.startswith("http"):
        return path
    return f"https://{host}{path}"


def _mask(secret: str) -> str:
    if len(secret) <= 8:
        return "*" * len(secret)
    return secret[:4] + "*" * (len(secret) - 8) + secret[-4:]


def _first_cve(info: dict) -> str | None:
    cls = info.get("classification") or {}
    cves = cls.get("cve-id")
    if isinstance(cves, list) and cves:
        return cves[0]
    if isinstance(cves, str):
        return cves
    return None
