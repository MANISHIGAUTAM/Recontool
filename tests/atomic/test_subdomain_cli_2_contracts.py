"""Atomic contract checks for the subdomain-cli-2 family.

Pure (no network/subprocess): validates that each wired declarative spec in
config/tools_generic.d/subdomain-cli-2.yaml
  * emits in-scope subdomains and drops out-of-scope hosts (scope_filter), and
  * is OFF by default (default_on is false AND is_active is false), and
  * builds into an Adapter subclass with the correct consumes/produces contract.

Note: this branch (arch/event-driven-engine-v2) has no recontool.engine.runner /
load_engine_registry and the autoloader reads config/tools_generic.yaml (not the
.d/ directory), so the YAML is loaded directly via REPO_ROOT. The pure parse
engine (parse_records/emit_events) and build_adapter_class are the real,
available validators.
"""
from __future__ import annotations

import yaml

from recontool.adapters.generic import build_adapter_class, emit_events, parse_records
from recontool.config import REPO_ROOT

_YAML = REPO_ROOT / "config" / "tools_generic.d" / "subdomain-cli-2.yaml"
_SPECS = {t["name"]: t for t in (yaml.safe_load(_YAML.read_text())["tools"] or [])}


def test_emit_scoped():
    # Empty family is a valid outcome; only assert behaviour for wired tools.
    for name, spec in _SPECS.items():
        sample = "api.example.com\nwww.example.com\ncdn.evil.com"  # last is out of scope
        events = emit_events(
            spec["parse"], parse_records(spec["parse"], sample), name, "example.com"
        )
        subs = {
            e.data["value"]
            for e in events
            if e.entity == "asset" and e.data.get("type") == "subdomain"
        }
        assert "api.example.com" in subs and "www.example.com" in subs
        assert "cdn.evil.com" not in subs


def test_off_by_default():
    for name, spec in _SPECS.items():
        assert spec.get("default_on", False) is False, f"{name}: default_on must be false"
        assert spec.get("is_active", False) is False, f"{name}: is_active must be false"
        cls = build_adapter_class(spec)
        assert cls.is_active is False, f"{name}: built adapter must be inactive"


def test_contract_shape():
    for name, spec in _SPECS.items():
        cls = build_adapter_class(spec)
        assert cls.consumes == ("domain",), f"{name}: must consume only domain"
        assert "subdomain" in cls.produces, f"{name}: must produce subdomain"
        # every emit rule on a subdomain producer must be scope-filtered
        for rule in spec["parse"].get("emit", []):
            if rule.get("type") == "subdomain":
                assert rule.get("scope_filter") == "subdomain", (
                    f"{name}: subdomain emit must set scope_filter: subdomain"
                )
