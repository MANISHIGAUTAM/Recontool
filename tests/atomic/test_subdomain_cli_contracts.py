"""Batch-12 F6: subdomain-source CLI family (ctfr, crobat) — verified invocations.

The one-per-line text parser is the universal subdomain-enumerator shape; this proves
banners/out-of-scope lines are dropped and only in-scope subdomains enter the graph, and
that every tool ships off-by-default + narrow (consumes domain only).
"""
from __future__ import annotations

import yaml

from recontool.adapters.generic import emit_events, parse_records
from recontool.config import REPO_ROOT
from recontool.engine.runner import load_engine_registry

_SPECS = {
    t["name"]: t for t in yaml.safe_load(
        (REPO_ROOT / "config" / "tools_generic.d" / "subdomain-cli.yaml").read_text()
    )["tools"]
}

# realistic ctfr/crobat stdout: an ASCII-banner line, in-scope subs, an out-of-scope sub.
_SAMPLE = "\n".join([
    "      ___ _____ _____ ____",   # banner junk
    "api.example.com",
    "www.example.com",
    "mail.example.com",
    "cdn.evil.com",                 # out of scope
])


def test_subdomain_cli_emit_scoped():
    for name, spec in _SPECS.items():
        recs = parse_records(spec["parse"], _SAMPLE)
        events = emit_events(spec["parse"], recs, name, "example.com")
        subs = {e.data["value"] for e in events
                if e.entity == "asset" and e.data.get("type") == "subdomain"}
        assert {"api.example.com", "www.example.com", "mail.example.com"} <= subs, name
        assert "cdn.evil.com" not in subs, f"{name}: out-of-scope must be dropped"
        assert not any(" " in s for s in subs), f"{name}: banner line leaked as subdomain"


def test_subdomain_cli_off_by_default_and_narrow():
    reg = load_engine_registry(tools="all", authorize_active=True)
    for name in _SPECS:
        spec = reg.get(name)
        assert spec is not None, f"{name} not loaded"
        consumes = set(spec.supported_input_types or []) | set(spec.consumes or [])
        assert consumes == {"domain"}, f"{name} must consume only domain"
        assert getattr(spec, "default_on", False) is False, f"{name} must be off by default"
