"""Live JS-rendering crawler — the next-gen data source.

Static recon sees the HTML the server first returns. Modern apps build their real
surface *in the browser*: routes injected by JS, API calls made via XHR/fetch,
GraphQL operations, tokens in dynamically-loaded bundles. This tool renders a URL
in a headless browser (Playwright), captures the **network requests the page
actually makes**, and mines the rendered DOM + scripts — then emits typed records
that feed straight back into the recursive engine.

It is a normal wired tool: `python -m recontool.tools.jsrender <url>` prints JSONL
(`{"type": "url"|"subdomain"|"secret", "value": ...}`), parsed by the generic
adapter spec `js-render`. Degrades gracefully: if Playwright (or a browser) isn't
installed, it falls back to a static fetch so the pipeline never hard-fails — you
simply lose the dynamic-only signals until a browser is present.

The extraction (`analyze`) is PURE — given the rendered HTML and the captured
request URLs it returns records with no I/O — so it is fully unit-tested without a
browser or network.
"""
from __future__ import annotations

import json
import sys
from urllib.parse import urlsplit

from recontool.adapters.active import _ENDPOINT_RE, _SECRET_PATTERNS, _mask
from recontool.adapters.crawler import extract_links, host_of
from recontool.core.scope import apex_domain, is_subdomain_of


def analyze(
    base_url: str, html: str, request_urls: list[str], *,
    scope_domain: str | None = None,
) -> list[dict]:
    """Pure extraction: rendered HTML + captured network requests -> typed records.

    Records: {"type": "url"|"subdomain"|"secret", "value": ...}. URLs and
    subdomains are scope-filtered (only the target footprint), so re-feeding stays
    clean. Secrets carry the masked preview + kind + source host.
    """
    records: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(rtype: str, value: str, **extra) -> None:
        value = (value or "").strip()
        if not value:
            return
        key = (rtype, value)
        if key in seen:
            return
        seen.add(key)
        records.append({"type": rtype, "value": value, **extra})

    def in_scope(host: str) -> bool:
        return bool(host) and (scope_domain is None or is_subdomain_of(host, scope_domain))

    page_host = host_of(base_url)

    # 1. Network requests the rendered page actually made (XHR/fetch/scripts) —
    #    the signal a static crawl cannot capture. These are real endpoints.
    for req in request_urls:
        req = (req or "").split("#")[0]
        if not req.startswith(("http://", "https://")):
            continue
        rhost = host_of(req)
        if in_scope(rhost):
            add("url", req)
            add("subdomain", rhost)

    # 2. Links present after JS executed (client-side routing, injected nav).
    for link in extract_links(base_url, html or ""):
        lhost = host_of(link)
        if in_scope(lhost):
            add("url", link)
            add("subdomain", lhost)

    # 3. Endpoints referenced inside inline/rendered JS (relative -> absolute).
    for m in set(_ENDPOINT_RE.findall(html or "")):
        if m.startswith("http"):
            if in_scope(host_of(m)):
                add("url", m.split("#")[0])
        elif m.startswith("/") and page_host:
            add("url", f"https://{page_host}{m}")

    # 4. Secrets in the rendered page / bundles.
    for kind, pat in _SECRET_PATTERNS.items():
        for match in pat.findall(html or ""):
            secret = match if isinstance(match, str) else match[0]
            add("secret", _mask(secret), kind=kind, source=page_host)

    return records


def render(url: str, *, timeout_ms: int = 30000) -> tuple[str, list[str]]:
    """Render `url` and return (html, captured_request_urls).

    Uses Playwright if available; otherwise falls back to a static fetch (html
    only, no captured XHR). Never raises — returns ("", []) on total failure.
    """
    try:
        return _render_playwright(url, timeout_ms)
    except Exception:  # noqa: BLE001 — Playwright/browser missing or page error
        return _render_static(url, timeout_ms)


def _render_playwright(url: str, timeout_ms: int) -> tuple[str, list[str]]:
    from playwright.sync_api import sync_playwright  # raises if not installed

    requests: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.on("request", lambda r: requests.append(r.url))
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            html = page.content()
        finally:
            # ALWAYS close the browser — if goto/content raised (nav timeout or
            # error) an unclosed chromium orphans and piles up as leaked
            # headless_shell processes that block interpreter shutdown.
            browser.close()
    return html, requests


def _render_static(url: str, timeout_ms: int) -> tuple[str, list[str]]:
    import urllib.request

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "recontool-jsrender"})
        with urllib.request.urlopen(req, timeout=max(1, timeout_ms // 1000)) as resp:
            return resp.read().decode("utf-8", "ignore"), []
    except Exception:  # noqa: BLE001
        return "", []


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    url = (argv[0] if argv else sys.stdin.read()).strip()
    if not url:
        return 0
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    scope = apex_domain(urlsplit(url).hostname or url)
    html, requests = render(url)
    for rec in analyze(url, html, requests, scope_domain=scope):
        sys.stdout.write(json.dumps(rec) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
