"""Pure-Python web crawler (no external binary required).

A self-contained, scope-aware, rate-limited crawler built on the platform's own
async HttpClient (proxy rotation + token-bucket limiting + retries) and stdlib
HTML parsing. Complements the optional `katana` CLI adapter: this one always works,
even where no Go binaries are installed.

Active phase p5_deep (gated behind --authorize-active):
  * BFS-crawls live in-scope hosts up to a bounded depth / page budget,
  * extracts links (a/href, script/src, form/action, link/href, img/src),
  * downloads .js files to local storage (artifacts/<scan>/js/<host>/),
  * extracts endpoints + secrets from inline JS and crawled JS,
  * discovers NEW in-scope subdomains from links -> feeds the recursive loop,
  * re-checks scope before every fetch (out-of-scope hosts are never requested).
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from recontool.adapters.active import _ENDPOINT_RE, _SECRET_PATTERNS, _mask
from recontool.adapters.base import Adapter, AdapterContext, Event
from recontool.adapters.registry import register
from recontool.adapters.params import extract_forms
from recontool.core.scope import is_subdomain_of

_JS_RE = re.compile(r"\.js(\?|$)", re.I)
_PAGE_BUDGET = {"stealth": 25, "normal": 400, "aggressive": 400}
_MAX_DEPTH = {"stealth": 2, "normal": 3, "aggressive": 4}
_MAX_JS = 60


class _LinkExtractor(HTMLParser):
    """Collect URL-bearing attributes from HTML using only the stdlib."""

    _ATTRS = {
        "a": "href", "link": "href", "area": "href",
        "script": "src", "img": "src", "iframe": "src", "source": "src",
        "form": "action",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls: set[str] = set()

    def handle_starttag(self, tag, attrs):
        attr = self._ATTRS.get(tag)
        if not attr:
            return
        for k, v in attrs:
            if k == attr and v:
                self.urls.add(v.strip())


def extract_links(base_url: str, html: str) -> set[str]:
    """Return absolute http(s) URLs referenced by an HTML document."""
    p = _LinkExtractor()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 - malformed HTML must never break a crawl
        pass
    out: set[str] = set()
    for raw in p.urls:
        if raw.startswith(("mailto:", "tel:", "javascript:", "data:", "#")):
            continue
        absu = urljoin(base_url, raw)
        if absu.startswith(("http://", "https://")):
            out.add(absu.split("#")[0])
    return out


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


@register("p5_deep")
class PyCrawler(Adapter):
    name = "pycrawl"
    category = "CAT-22"
    is_active = True
    consumes = ("subdomain", "domain", "url")
    produces = ("url", "subdomain", "finding")

    def available(self, ctx: AdapterContext) -> bool:
        return True  # pure python - always available

    async def run(self, ctx: AdapterContext) -> list[Event]:
        profile = ctx.profile
        budget = _PAGE_BUDGET.get(profile.name, 120)
        max_depth = _MAX_DEPTH.get(profile.name, 3)
        concurrency = max(2, profile.per_host_concurrency * 4)
        seed_dom = _seed_domain(ctx)

        seeds: list[str] = []
        for h in ctx.seeds_of("subdomain") + ctx.seeds_of("domain"):
            if ctx.scope.contains("subdomain", h):
                seeds.append(f"https://{h}/")
        seeds.extend(u for u in ctx.seeds_of("url") if ctx.scope.contains("url", u))

        # ── CDN dedup: hash root page content, skip clones ──────────────────
        # Fetch GET / for each seed host, compute sha256, group by hash.
        # Only crawl one representative per content-hash group.
        sem = asyncio.Semaphore(concurrency)

        async def _fetch_root_hash(url: str) -> tuple[str, str | None]:
            """Return (url, content_hash or None).

            Uses a structural fingerprint rather than raw byte hash:
            - Only hashes the first 4KB of the body (reduces sensitivity to
              footer/pagination changes).
            - Strips common dynamic elements (CSRF tokens, nonces, timestamps)
              before hashing.
            """
            try:
                async with sem:
                    resp = await asyncio.wait_for(
                        ctx.http.get(url, bucket=f"crawl_dedup:{host_of(url)}"),
                        timeout=5.0,
                    )
                if resp.content:
                    # Take only first 4KB for fingerprinting
                    chunk = resp.content[:4096]
                    # Strip common dynamic elements before hashing
                    text = chunk.decode(errors="ignore")
                    text = re.sub(
                        r'<meta[^>]*name=["\']csrf[^>]*>', '', text, flags=re.I
                    )
                    text = re.sub(
                        r'(nonce|csrf[-_]?token|timestamp)=["\'][^"\']*["\']',
                        '', text, flags=re.I
                    )
                    text = re.sub(
                        r'<!--\s*generated.*?-->', '', text, flags=re.I | re.S
                    )
                    return (url, hashlib.sha256(text.encode()).hexdigest())
            except Exception:  # noqa: BLE001
                pass
            return (url, None)

        hash_results = await asyncio.gather(*(_fetch_root_hash(u) for u in seeds))

        # Group by content hash
        hash_to_urls: dict[str, list[str]] = {}
        no_hash_urls: list[str] = []
        for url, content_hash in hash_results:
            if content_hash:
                hash_to_urls.setdefault(content_hash, []).append(url)
            else:
                no_hash_urls.append(url)

        # Pick one representative per hash group; track clones for result fan-out
        deduped_seeds: list[str] = list(no_hash_urls)
        clone_map: dict[str, list[str]] = {}  # representative -> list of clones
        for _hash, urls in hash_to_urls.items():
            rep = urls[0]
            deduped_seeds.append(rep)
            if len(urls) > 1:
                clone_map[rep] = urls[1:]

        events: list[Event] = []
        visited: set[str] = set()
        seen_hosts: set[str] = set()
        js_done = 0
        frontier = [(u, 0) for u in dict.fromkeys(deduped_seeds)]

        async def fetch(url: str) -> str | None:
            host = host_of(url)
            if not (ctx.scope.contains("subdomain", host) or ctx.scope.contains("ip", host)):
                return None
            async with sem:
                try:
                    resp = await ctx.http.get(url, bucket=f"crawl:{host}")
                except Exception:  # noqa: BLE001
                    return None
            events.append(Event.endpoint(self.name, resp.url, status=resp.status, source="pycrawl"))
            return resp.text

        async def grab_js(url: str):
            nonlocal js_done
            if js_done >= _MAX_JS:
                return
            host = host_of(url)
            if not ctx.scope.contains("subdomain", host):
                return
            async with sem:
                try:
                    resp = await ctx.http.get(url, bucket=f"crawljs:{host}")
                except Exception:  # noqa: BLE001
                    return
            if resp.status != 200 or not resp.content:
                return
            js_done += 1
            fname = urlsplit(url).path.rsplit("/", 1)[-1] or "index.js"
            ref = ctx.artifacts.save_js(host, fname, resp.content)
            events.append(Event.endpoint(self.name, url, source="pycrawl", js_artifact=ref))
            events.extend(self._mine_js(host, resp.text, ref, seed_dom=seed_dom))

        while frontier and len(visited) < budget:
            level = [(u, d) for (u, d) in frontier if u not in visited][:concurrency]
            frontier = frontier[len(level):]
            if not level:
                break
            htmls = await asyncio.gather(*(fetch(u) for u, _ in level))
            for (url, depth), html in zip(level, htmls):
                visited.add(url)
                if not html:
                    continue
                events.extend(self._mine_js(host_of(url), html, ref=None, seed_dom=seed_dom))
                # form parameters -> feed fuzz prep (scope-filtered)
                for form in extract_forms(url, html):
                    if form["params"] and is_subdomain_of(host_of(form["action"]), seed_dom or ""):
                        events.append(Event.endpoint(self.name, form["action"],
                                                     params=form["params"],
                                                     source=f"pycrawl-form:{form['method']}"))
                for link in extract_links(url, html):
                    lhost = host_of(link)
                    if lhost and lhost not in seen_hosts and is_subdomain_of(lhost, seed_dom or ""):
                        seen_hosts.add(lhost)
                        events.append(Event.asset(self.name, "subdomain", lhost))
                    if _JS_RE.search(link):
                        await grab_js(link)
                    elif (ctx.scope.contains("subdomain", lhost) and link not in visited
                          and depth + 1 <= max_depth
                          and len(visited) + len(frontier) < budget):
                        frontier.append((link, depth + 1))
                    elif ctx.scope.contains("subdomain", lhost):
                        events.append(Event.endpoint(self.name, link, source="pycrawl"))

        # ── Fan out crawl results to CDN clones ─────────────────────────────
        # For each representative that had clones, replicate endpoint events
        # with the clone's host substituted.
        for rep_url, clones in clone_map.items():
            rep_host = host_of(rep_url)
            for clone_url in clones:
                clone_host = host_of(clone_url)
                if not clone_host or clone_host == rep_host:
                    continue
                events.append(
                    Event.endpoint(self.name, clone_url, source="pycrawl-cdn-clone")
                )
                events.append(
                    Event.asset(self.name, "subdomain", clone_host, is_live=True)
                )

        return events

    def _mine_js(self, host: str, text: str, ref: str | None,
                 seed_dom: str | None = None) -> list[Event]:
        out: list[Event] = []
        for m in set(_ENDPOINT_RE.findall(text or "")):
            if m.startswith("http"):
                # only keep absolute URLs that are in-scope (avoid offsite noise)
                if seed_dom and not is_subdomain_of(host_of(m), seed_dom):
                    continue
                out.append(Event.endpoint(self.name, m, source="pycrawl-js"))
            elif m.startswith("/"):
                out.append(Event.endpoint(self.name, f"https://{host}{m}", source="pycrawl-js"))
        for kind, pat in _SECRET_PATTERNS.items():
            for match in pat.findall(text or ""):
                secret = match if isinstance(match, str) else match[0]
                out.append(Event.finding(
                    self.name, "secret", f"Possible {kind} in crawled JS",
                    severity="high", detector=f"pycrawl:{kind}", asset_value=host,
                    evidence_redacted={"type": kind, "preview": _mask(secret),
                                       "sha1": hashlib.sha1(secret.encode()).hexdigest(),
                                       "ref": ref}))
        return out


def _seed_domain(ctx: AdapterContext) -> str | None:
    doms = ctx.seeds_of("domain")
    if doms:
        return doms[0]
    if ctx.scope and ctx.scope.allow_domains:
        return sorted(ctx.scope.allow_domains)[0]
    return None
