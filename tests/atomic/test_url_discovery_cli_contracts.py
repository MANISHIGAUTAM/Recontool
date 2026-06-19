"""Pure-fixture contract tests for the url-discovery-cli tool family.

Validates the declarative specs in config/tools_generic.d/url-discovery-cli.yaml
through the *pure* parse engine only — no registry, no network, no subprocess.

This family adds the net-new urlfinder (passive) + galer (active crawl); gau,
gauplus and waybackurls are already wired elsewhere and are NOT re-wired here.

Each tool prints one plain URL per line on stdout (source-confirmed in the YAML
comments). The generic engine turns each line into an `endpoint` event via
parse_records(format=text) -> {"_value": line} -> emit_events(entity=endpoint,
url="{_value}"). URL scope is enforced downstream by Scope.contains("url", ...),
so we exercise that real mechanism here to prove an out-of-scope URL is dropped.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from recontool.adapters.generic import emit_events, parse_records
from recontool.core.scope import Scope

_YAML = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "tools_generic.d"
    / "url-discovery-cli.yaml"
)


def _specs() -> dict[str, dict]:
    data = yaml.safe_load(_YAML.read_text()) or {}
    return {t["name"]: t for t in data.get("tools", [])}


# A realistic urlfinder/galer stdout sample: one URL per line, plus blank/comment
# noise the text parser must skip, plus an OUT-OF-SCOPE URL downstream scope drops.
_SAMPLE_STDOUT = """\
https://example.com/
https://example.com/login?next=/admin
http://api.example.com/v1/users

# a comment line the text parser skips
https://cdn.example.com/static/app.js
https://evil.attacker.com/phishing?to=example.com
"""

_IN_SCOPE = {
    "https://example.com/",
    "https://example.com/login?next=/admin",
    "http://api.example.com/v1/users",
    "https://cdn.example.com/static/app.js",
}
_OUT_OF_SCOPE = "https://evil.attacker.com/phishing?to=example.com"


def test_text_lines_become_endpoint_events():
    """Each non-blank, non-comment stdout line maps to one endpoint event whose
    url is the verbatim line (the {_value} the text parser stores)."""
    spec = _specs()["urlfinder"]
    records = parse_records(spec["parse"], _SAMPLE_STDOUT)
    assert {r["_value"] for r in records} == _IN_SCOPE | {_OUT_OF_SCOPE}

    events = emit_events(spec["parse"], records, "urlfinder", "example.com")
    assert events, "expected endpoint events"
    assert all(e.entity == "endpoint" for e in events)
    urls = {e.data["url"] for e in events}
    assert urls == _IN_SCOPE | {_OUT_OF_SCOPE}


def test_all_wired_specs_share_the_endpoint_url_contract():
    specs = _specs()
    assert set(specs) == {"urlfinder", "galer"}
    for name, spec in specs.items():
        events = emit_events(spec["parse"], parse_records(spec["parse"], _SAMPLE_STDOUT),
                             name, "example.com")
        urls = {e.data["url"] for e in events}
        assert _IN_SCOPE <= urls, f"{name} dropped an in-scope URL"
        assert all(e.entity == "endpoint" for e in events), f"{name} emitted non-endpoint"


def test_scope_filter_drops_out_of_scope_url():
    """The contracts declare scope_filter: url; the engine enforces it via
    Scope.contains('url', value). In-scope survive, the attacker host is dropped."""
    spec = _specs()["urlfinder"]
    events = emit_events(spec["parse"], parse_records(spec["parse"], _SAMPLE_STDOUT),
                         "urlfinder", "example.com")
    urls = [e.data["url"] for e in events]

    scope = Scope.from_seed("example.com", "domain")
    kept = [u for u in urls if scope.contains("url", u)]

    assert set(kept) == _IN_SCOPE
    assert _OUT_OF_SCOPE not in kept
    assert all(rule.get("scope_filter") == "url" for rule in spec["parse"]["emit"])


def test_all_tools_default_on_false():
    for name, spec in _specs().items():
        assert spec["default_on"] is False, f"{name} must ship default_on: false"


def test_contract_invariants():
    """integration: cli, binary set, narrow consumes, url produces, and the
    active/passive flag matches the tool's nature (passive source vs live crawl)."""
    specs = _specs()
    for name, spec in specs.items():
        assert spec["integration"] == "cli"
        assert spec["binary"] == name
        assert spec["consumes"] in (["domain"], ["url"]), name
        assert spec["produces"] == ["url"], name

    assert specs["urlfinder"]["is_active"] is False
    assert specs["urlfinder"]["consumes"] == ["domain"]
    # galer drives a live headless browser against the target
    assert specs["galer"]["is_active"] is True
    assert specs["galer"]["consumes"] == ["url"]
