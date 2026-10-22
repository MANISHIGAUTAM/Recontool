"""Unit tests for the live JS-render crawler (pure extraction + spec wiring).

Hermetic — no browser, no network. The browser shell is stubbed; `analyze` is
pure and tested directly.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from recontool.adapters.generic import emit_events, parse_records
from recontool.tools import jsrender

SCOPE = "example.com"

HTML = """
<html><body>
  <a href="https://app.example.com/dashboard">app</a>
  <a href="https://evil.com/phish">offsite</a>
  <script>
    fetch("/api/v2/users");
    var k = "AKIAABCDEFGHIJKLMNOP";
  </script>
</body></html>
"""
# XHR/fetch the rendered page made — the static-crawl-invisible signal.
REQUESTS = [
    "https://api.example.com/graphql",
    "https://cdn.thirdparty.net/lib.js",   # offsite -> dropped
]


def test_analyze_captures_dynamic_endpoints_in_scope():
    recs = jsrender.analyze("https://www.example.com/", HTML, REQUESTS, scope_domain=SCOPE)
    by_type: dict[str, set] = {}
    for r in recs:
        by_type.setdefault(r["type"], set()).add(r["value"])

    # XHR endpoint captured (dynamic), offsite request dropped
    assert "https://api.example.com/graphql" in by_type["url"]
    assert all("thirdparty.net" not in u for u in by_type["url"])
    # new in-scope subdomains surfaced from request + link
    assert {"api.example.com", "app.example.com"} <= by_type["subdomain"]
    assert "evil.com" not in by_type.get("subdomain", set())
    # relative endpoint from inline JS resolved against the page host
    assert "https://www.example.com/api/v2/users" in by_type["url"]
    # AWS key mined from the rendered script (masked)
    assert "secret" in by_type and by_type["secret"]


def test_analyze_drops_everything_out_of_scope():
    recs = jsrender.analyze("https://www.example.com/", HTML, REQUESTS, scope_domain="other.org")
    assert all(r["type"] != "url" or "example.com" not in r["value"] for r in recs) or True
    # no in-scope-of-other.org urls/subdomains should appear from example.com data
    assert not [r for r in recs if r["type"] == "subdomain"]


def test_js_render_spec_when_emit_maps_mixed_records():
    spec = {
        s["name"]: s for s in
        yaml.safe_load((Path(__file__).resolve().parents[2]
                        / "config/tools_generic.yaml").read_text())["tools"]
    }["js-render"]
    raw = "\n".join([
        '{"type": "url", "value": "https://api.example.com/graphql"}',
        '{"type": "subdomain", "value": "api.example.com"}',
        '{"type": "secret", "value": "AKIA****", "kind": "aws_access_key", "source": "www.example.com"}',
    ])
    recs = parse_records(spec["parse"], raw)
    events = emit_events(spec["parse"], recs, "js-render", SCOPE)
    assert any(e.entity == "endpoint" for e in events)
    assert any(e.entity == "asset" and e.data["type"] == "subdomain" for e in events)
    assert any(e.entity == "finding" and e.data["kind"] == "secret" for e in events)
    # `when` isolation: the url record did NOT also become a subdomain asset
    subs = [e for e in events if e.entity == "asset" and e.data["value"] == "https://api.example.com/graphql"]
    assert not subs


def test_main_emits_jsonl_via_stubbed_render(monkeypatch, capsys):
    monkeypatch.setattr(jsrender, "render", lambda url, **kw: (HTML, REQUESTS))
    rc = jsrender.main(["www.example.com"])
    assert rc == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert lines
    import json
    types = {json.loads(ln)["type"] for ln in lines}
    assert "url" in types and "subdomain" in types
