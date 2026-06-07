"""In-process MOCK recon environment for demo/test mode.

A single ``MockEnv`` answers any URL the pipeline might request with deterministic,
self-consistent data describing a fictional org built around a demo apex domain
(default ``demo.recontool.local``). It covers:

  * third-party passive providers   (crt.sh, hackertarget, OTX, urlscan, internetdb…)
  * the demo target hosts themselves (HTTP probe, crawl pages, robots, JS files)

Everything is pure-Python string/JSON building — no sockets, no real DNS, no files
required. The HttpClient consults ``MockEnv.handle(method, url, ...)`` instead of
making a real request whenever the run mode is demo/test.

Design goals:
  * deterministic  : same input -> same output (fixture-grade, replayable)
  * self-chaining  : subdomains in CT -> resolve to mock IPs -> serve mock pages
                     -> pages link to more subdomains + JS -> JS leaks endpoints +
                     a (fake) secret. Exercises the full discovery->enrich loop.
  * in-scope only  : all generated hosts are subdomains of the demo apex, so the
                     scope gate keeps everything inside the sandbox.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

DEMO_APEX = "recontool.local"

# Canonical fictional attack surface for the demo apex.
DEMO_SUBDOMAINS = [
    "www", "api", "dev", "staging", "admin", "blog", "shop", "mail", "vpn", "git",
]
# Deterministic IP mapping (documentation-range 192.0.2.0/24, RFC 5737 TEST-NET-1).
DEMO_IP_BASE = "192.0.2."


def _ip_for(host: str) -> str:
    """Stable fake IP for a host (last octet from a simple hash, 10..250)."""
    h = sum(ord(c) for c in host)
    return DEMO_IP_BASE + str(10 + (h % 240))


def demo_hosts(apex: str = DEMO_APEX) -> list[str]:
    return [f"{s}.{apex}" for s in DEMO_SUBDOMAINS]


@dataclass
class MockResponse:
    status: int
    body: str
    headers: dict[str, str] = field(default_factory=dict)
    content_type: str = "application/json"

    def as_tuple(self) -> tuple[int, str, dict[str, str]]:
        hdrs = {"content-type": self.content_type, **self.headers}
        return self.status, self.body, hdrs


class MockEnv:
    """Deterministic mock recon environment for a single demo apex."""

    def __init__(self, apex: str = DEMO_APEX):
        self.apex = apex
        self.hosts = demo_hosts(apex)
        self.calls: list[str] = []  # request log (for assertions)

    # ── public entrypoint ───────────────────────────────────────────────────
    def handle(self, method: str, url: str, *, params: dict | None = None) -> MockResponse:
        """Return a deterministic response for any URL the pipeline may request."""
        self.calls.append(url)
        split = urlsplit(url)
        host = (split.hostname or "").lower()
        q = {k: v[0] for k, v in parse_qs(split.query).items()}
        if params:
            q.update({k: str(v) for k, v in params.items()})

        # 1) third-party providers (passive sources)
        if host == "crt.sh":
            return self._crtsh(q)
        if host == "api.hackertarget.com":
            return self._hackertarget(q, split.path)
        if host == "otx.alienvault.com":
            return self._otx(split.path)
        if host == "urlscan.io":
            return self._urlscan(q)
        if host == "internetdb.shodan.io":
            return self._internetdb(split.path)
        if host == "web.archive.org":
            return self._wayback(q)

        # 2) the demo target hosts themselves (live validation + crawl + JS)
        if host == self.apex or host.endswith("." + self.apex):
            return self._target(host, split.path)

        # 3) anything else -> 404 (and definitely never a real call)
        return MockResponse(404, json.dumps({"error": "not found in mock env", "url": url}))

    # ── third-party providers ────────────────────────────────────────────────
    def _crtsh(self, q: dict) -> MockResponse:
        rows = [{"name_value": h} for h in self.hosts]
        rows.append({"name_value": f"*.{self.apex}"})
        return MockResponse(200, json.dumps(rows))

    def _hackertarget(self, q: dict, path: str) -> MockResponse:
        lines = [f"{h},{_ip_for(h)}" for h in self.hosts]
        return MockResponse(200, "\n".join(lines), content_type="text/plain")

    def _otx(self, path: str) -> MockResponse:
        recs = [{"hostname": h, "address": _ip_for(h)} for h in self.hosts[:5]]
        return MockResponse(200, json.dumps({"passive_dns": recs}))

    def _urlscan(self, q: dict) -> MockResponse:
        results = [
            {"page": {"url": f"https://{h}/", "domain": h, "ip": _ip_for(h)}}
            for h in self.hosts[:4]
        ]
        return MockResponse(200, json.dumps({"results": results}))

    def _internetdb(self, path: str) -> MockResponse:
        ip = path.strip("/")
        return MockResponse(200, json.dumps({
            "ip": ip, "ports": [80, 443, 22], "hostnames": [f"www.{self.apex}"],
            "vulns": ["CVE-2021-44228"], "tags": ["cloud"],
        }))

    def _wayback(self, q: dict) -> MockResponse:
        rows = [["original"]]
        for h in self.hosts[:3]:
            rows.append([f"https://{h}/"])
            rows.append([f"https://{h}/app.js"])
            rows.append([f"https://{h}/old/login?redirect=/home"])
        return MockResponse(200, json.dumps(rows))

    # ── the demo target hosts ──────────────────────────────────────────────
    def _target(self, host: str, path: str) -> MockResponse:
        path = path or "/"
        if path == "/robots.txt":
            return MockResponse(200, f"User-agent: *\nDisallow: /admin\nSitemap: https://{host}/sitemap.xml",
                                content_type="text/plain")
        if path.endswith(".js"):
            return MockResponse(200, self._js(host), content_type="application/javascript")
        if path.rstrip("/") == "/admin":
            return MockResponse(403, "<html><title>Forbidden</title></html>",
                                content_type="text/html")
        # default: an HTML page that links to other in-scope hosts + a JS file + a form
        return MockResponse(200, self._html(host), content_type="text/html",
                            headers={"server": "nginx/1.25.0", "x-powered-by": "Express"})

    def _html(self, host: str) -> str:
        links = "".join(
            f'<a href="https://{h}/">{h}</a>' for h in self.hosts[:4]
        )
        return f"""<!doctype html><html><head><title>{host}</title>
<script src="https://{host}/app.js"></script>
<link rel="stylesheet" href="/static/site.css"></head>
<body><h1>{host}</h1>{links}
<a href="https://internal-api.{self.apex}/v1/users">internal api</a>
<form action="/search" method="get"><input name="q"><input name="page"></form>
</body></html>"""

    def _js(self, host: str) -> str:
        # contains in-scope endpoints, a new host, and a FAKE secret (redacted by analyzer)
        return (
            'const API="/api/v2/orders";'
            f'fetch("https://api.{self.apex}/v2/orders");'
            f'const cfg="https://cdn.{self.apex}/config.json";'
            'const awsKey="AKIAIOSFODNN7EXAMPLE";'
            'const gKey="AIzaSyA1234567890abcdefghijklmnopqrstuvz";'
        )
