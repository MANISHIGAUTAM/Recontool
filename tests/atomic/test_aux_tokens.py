"""Aux-token resolution for CLI tools — the {resolvers}/{wordlist}/{ports}/
{rate}/{key} layer that lets a declarative invocation reference resource files,
scan-config scalars, and API keys (not just entity inputs).

Without it those tokens render to "" -> malformed argv -> the tool silently
produces nothing (the puredns/massdns/masscan/github-subdomains breakage class).
"""
from __future__ import annotations

from recontool.adapters.generic import _aux_tokens
from recontool.config import PROFILES


class _Ctx:
    profile = PROFILES["normal"]


def test_aux_tokens_resolve_resources_and_config():
    aux = _aux_tokens({}, _Ctx())
    assert aux["resolvers"].endswith("resolvers.txt")
    assert "SecLists" in aux["wordlist"] or aux["wordlist"]            # a path is present
    assert aux["fingerprints"].endswith("fingerprints.json")
    assert aux["ports"] == "1-10000"          # normal profile -> top-1000 mapping
    assert int(aux["rate"]) >= 100            # masscan pps derived from QPS
    assert "key" not in aux                   # no requires_key -> no key token


def test_aux_tokens_injects_api_key(monkeypatch):
    import recontool.adapters.generic as g
    monkeypatch.setattr(g.settings, "api_key", lambda name: "ghp_xxx" if name == "GITHUB_TOKEN" else None)
    aux = _aux_tokens({"requires_key": "GITHUB_TOKEN"}, _Ctx())
    assert aux["key"] == "ghp_xxx"


def test_full_template_render_with_aux():
    # puredns-style invocation fully resolves (no empty tokens left)
    from recontool.adapters.generic import render_template
    aux = dict(_aux_tokens({}, _Ctx()))
    aux.update({"subdomain": "x.example.com", "value": "x.example.com"})
    cmd = render_template("puredns resolve /dev/stdin -r {resolvers} -q", {}, aux)
    assert "{resolvers}" not in cmd and "resolvers.txt" in cmd
