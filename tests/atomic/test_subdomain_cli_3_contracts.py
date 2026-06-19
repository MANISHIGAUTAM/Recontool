"""Pure fixture tests for the `subdomain-cli-3` generic adapter family.

Exercises ONLY the pure parse engine (parse_records + emit_events) against the
declarative contract in config/tools_generic.d/subdomain-cli-3.yaml, using
realistic sample stdout. No registry, no network, no subprocess.

This family adds the net-new github-subdomains source (assetfinder/findomain are
already wired in config/tools.yaml / config/tools_generic.yaml and are NOT
re-wired here; sublist3r/dnscan are deferred for ANSI/decorated stdout).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from recontool.adapters.generic import emit_events, parse_records

_YAML = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "tools_generic.d"
    / "subdomain-cli-3.yaml"
)

SEED = "example.com"


def _tools() -> dict[str, dict]:
    spec = yaml.safe_load(_YAML.read_text())
    return {t["name"]: t for t in spec["tools"]}


def _emit_values(tool_spec: dict, raw: str) -> list[str]:
    recs = parse_records(tool_spec["parse"], raw)
    events = emit_events(tool_spec["parse"], recs, tool_spec["name"], SEED)
    return [e.data["value"] for e in events if e.entity == "asset"]


# Realistic github-subdomains -raw stdout: one host per line, plus a decorated
# line, an out-of-scope sibling, and a sibling-suffix collision that must drop.
SAMPLE_STDOUT = "\n".join(
    [
        "[info] enumerating example.com",   # decorated noise -> dropped
        "api.example.com",                  # in scope
        "WWW.Example.com",                  # case-folded, in scope
        "mail.example.com",                 # in scope
        "evil.attacker.com",                # out of scope -> dropped
        "m.testexample.com",                # sibling-suffix -> dropped
        "",                                 # blank -> skipped
    ]
)

WIRED = ("github-subdomains",)


def test_all_wired_tools_present_and_opt_in():
    tools = _tools()
    for name in WIRED:
        t = tools[name]
        assert t["default_on"] is False, f"{name} must be default_on:false"
        assert t["is_active"] is False, f"{name} must be is_active:false (passive)"
        assert t["integration"] == "cli"
        assert t["consumes"] == ["domain"]
        assert t["produces"] == ["subdomain"]
        assert t["binary"] == name
        rule = t["parse"]["emit"][0]
        assert rule["type"] == "subdomain"
        assert rule["scope_filter"] == "subdomain"
        assert rule["value"] == "{_value}"


def test_each_wired_tool_emits_only_in_scope_subdomains():
    tools = _tools()
    for name in WIRED:
        vals = _emit_values(tools[name], SAMPLE_STDOUT)
        assert "api.example.com" in vals, name
        assert "www.example.com" in vals, name        # case-folded
        assert "mail.example.com" in vals, name
        assert "evil.attacker.com" not in vals, name
        assert "m.testexample.com" not in vals, name
        for v in vals:
            assert v == SEED or v.endswith("." + SEED), f"{name}: leaked {v!r}"


def test_github_subdomains_uses_raw_and_token():
    """github-subdomains needs -raw for plain stdout and gates on GITHUB_TOKEN."""
    t = _tools()["github-subdomains"]
    assert "-raw" in t["invocation"].split()
    assert "-d" in t["invocation"]
    assert "{domain}" in t["invocation"]
    assert t["requires_key"] == "GITHUB_TOKEN"


def test_deferred_and_already_wired_not_duplicated():
    """sublist3r/dnscan deferred; assetfinder/findomain owned by tools.yaml."""
    names = set(_tools())
    assert "sublist3r" not in names
    assert "dnscan" not in names
    assert "assetfinder" not in names   # already wired elsewhere
    assert "findomain" not in names     # already wired elsewhere
