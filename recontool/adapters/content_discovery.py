"""Content & directory discovery (Category 20) — pure Python, no ffuf binary.

Active (p5_deep): for each in-scope live host, brute-forces a wordlist of common
paths over the platform's rate-limited/proxied HttpClient, with 404 / soft-404
("wildcard") CALIBRATION so junk responses are filtered. Emits endpoint hits with
status + risk_class. Falls back to ffuf/feroxbuster automatically if you prefer
those — this one always works.
"""
from __future__ import annotations

import asyncio
import random
import string

from recontool.adapters.base import Adapter, AdapterContext, Event
from recontool.adapters.registry import register
from recontool.config import settings

# Interesting statuses that indicate a path likely exists / is protected.
HIT_STATUSES = {200, 201, 204, 301, 302, 307, 308, 401, 403, 405, 500}

# Compact, high-signal built-in wordlist (extend via config resources.default_wordlist).
BUILTIN_WORDLIST = [
    "admin", "administrator", "login", "logout", "dashboard", "api", "api/v1",
    "api/v2", "graphql", "swagger", "swagger.json", "openapi.json", "robots.txt",
    "sitemap.xml", ".git/config", ".git/HEAD", ".env", ".env.local", "config",
    "config.json", "config.php", "backup", "backups", "backup.zip", "db.sql",
    "dump.sql", "test", "dev", "staging", "uploads", "upload", "files", "static",
    "assets", "js", "css", "images", "img", "tmp", "temp", "old", "new", "beta",
    "internal", "private", "secret", "secrets", "debug", "status", "health",
    "healthz", "metrics", "actuator", "actuator/health", "server-status",
    "phpinfo.php", "info.php", "wp-admin", "wp-login.php", "wp-config.php",
    "user", "users", "account", "settings", "console", "portal", ".well-known/security.txt",
    "cgi-bin", "server-info", "web.config", "crossdomain.xml", "readme.md",
]

_PAGE_BUDGET = {"stealth": 40, "normal": 600, "aggressive": 600}
_MAX_HOSTS = {"stealth": 5, "normal": 100, "aggressive": 100}


def is_hit(status: int, length: int, baseline: tuple[int, int] | None) -> bool:
    """Decide whether a response is a real hit vs calibrated not-found/wildcard.

    baseline = (status, content_length) observed for a known-bad random path.
    """
    if status not in HIT_STATUSES:
        return False
    if baseline is None:
        return True
    b_status, b_len = baseline
    # soft-404 / wildcard: server answers everything with the same status -> require
    # a meaningfully different body length to count as a real hit.
    if status == b_status:
        return abs(length - b_len) > 64
    return True


def load_wordlist() -> list[str]:
    words = list(BUILTIN_WORDLIST)
    path = settings.resource("default_wordlist", "")
    try:
        if path:
            from pathlib import Path
            p = Path(path)
            if p.exists():
                extra = [w.strip().lstrip("/") for w in p.read_text().splitlines()
                         if w.strip() and not w.startswith("#")]
                words = sorted(set(words + extra))
    except Exception:  # noqa: BLE001
        pass
    return words


def _rand_path() -> str:
    return "zz" + "".join(random.choices(string.ascii_lowercase + string.digits, k=16))


@register("p5_deep")
class ContentDiscovery(Adapter):
    name = "pydirb"
    category = "CAT-20"
    is_active = True
    consumes = ("subdomain", "domain")
    produces = ("url",)

    def available(self, ctx: AdapterContext) -> bool:
        return True  # pure python

    async def run(self, ctx: AdapterContext) -> list[Event]:
        profile = ctx.profile
        max_hosts = _MAX_HOSTS.get(profile.name, 25)
        budget = _PAGE_BUDGET.get(profile.name, 150)
        concurrency = max(2, profile.per_host_concurrency * 4)
        words = load_wordlist()[:budget]

        hosts = [h for h in (ctx.seeds_of("subdomain") + ctx.seeds_of("domain"))
                 if ctx.scope.contains("subdomain", h)][:max_hosts]
        events: list[Event] = []
        sem = asyncio.Semaphore(concurrency)

        async def probe(base: str, path: str, baseline):
            url = f"{base}/{path}"
            async with sem:
                try:
                    resp = await ctx.http.get(url, bucket=f"dirb:{base}")
                except Exception:  # noqa: BLE001
                    return
            length = len(resp.content or b"")
            if is_hit(resp.status, length, baseline):
                events.append(Event.endpoint(self.name, resp.url, status=resp.status,
                                             source="pydirb"))

        for host in hosts:
            base = f"https://{host}"
            # calibrate against a known-bad random path
            baseline = None
            try:
                cal = await ctx.http.get(f"{base}/{_rand_path()}", bucket=f"dirb:{base}")
                baseline = (cal.status, len(cal.content or b""))
            except Exception:  # noqa: BLE001
                continue  # host unreachable -> skip
            await asyncio.gather(*(probe(base, w, baseline) for w in words))
        return events
