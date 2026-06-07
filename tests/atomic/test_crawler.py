"""Atomic checks for the pure-Python web crawler (network-free).

Validates link extraction, relative->absolute resolution, junk-scheme filtering,
JS detection, and host parsing — the pure functions the crawler is built on.
"""
from __future__ import annotations

from recontool.adapters.crawler import _JS_RE, extract_links, host_of

HTML = """
<html><head>
  <link rel="stylesheet" href="/css/site.css">
  <script src="/static/app.min.js"></script>
  <script src="https://cdn.example.com/lib.js"></script>
</head><body>
  <a href="/about">About</a>
  <a href="https://api.example.com/v1/login">API</a>
  <a href="mailto:x@example.com">mail</a>
  <a href="javascript:void(0)">js</a>
  <form action="/submit" method="post"></form>
  <img src="https://example.com/img/logo.png">
  <a href="https://evil.attacker.com/x">offsite</a>
</body></html>
"""


def test_extract_links_resolves_and_filters():
    links = extract_links("https://example.com/page", HTML)
    # relative resolved to absolute
    assert "https://example.com/about" in links
    assert "https://example.com/submit" in links
    assert "https://example.com/static/app.min.js" in links
    # absolute kept
    assert "https://api.example.com/v1/login" in links
    assert "https://cdn.example.com/lib.js" in links
    # junk schemes dropped
    assert not any(u.startswith(("mailto:", "javascript:")) for u in links)
    assert all(u.startswith(("http://", "https://")) for u in links)


def test_js_detection_and_host():
    links = extract_links("https://example.com/", HTML)
    js = [u for u in links if _JS_RE.search(u)]
    assert "https://example.com/static/app.min.js" in js
    assert "https://cdn.example.com/lib.js" in js
    assert host_of("https://api.example.com/v1?x=1") == "api.example.com"
    assert host_of("not-a-url") == ""


def test_malformed_html_does_not_raise():
    # must never break a crawl
    assert isinstance(extract_links("https://x.com/", "<a href=<<>broken"), set)
    assert extract_links("https://x.com/", "") == set()
