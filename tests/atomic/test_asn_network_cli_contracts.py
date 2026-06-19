"""Atomic contract checks for the asn-network-cli family.

Pure (no network/subprocess): validates the wired declarative spec(s) in
config/tools_generic.d/asn-network-cli.yaml against the real parse engine.

Grounding: asnlookup (https://github.com/yassineaboukir/Asnlookup) prints a red
header line ("IP addresses owned by <org> are the following:") followed by one
CIDR per line (asnlookup.py: `for i in ip_addresses: print(colored(i,"yellow"))`,
i == "104.244.42.0/24" — both IPv4 and IPv6). The sample below reproduces that
stdout; the header / any banner line carries no CIDR and must be dropped by the
line_regex, so only real prefixes emit.

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

_YAML = REPO_ROOT / "config" / "tools_generic.d" / "asn-network-cli.yaml"
_SPECS = {t["name"]: t for t in (yaml.safe_load(_YAML.read_text())["tools"] or [])}

# Reproduces asnlookup.py stdout: red header, then one CIDR per line (v4 + v6).
# The header line and a stray non-CIDR banner line MUST be dropped (no CIDR match).
_SAMPLE = """IP addresses owned by acme are the following:

104.244.42.0/24
199.16.156.0/22
2606:4700::/32
   192.0.2.0/24
no ip ranges found for this organization"""


def test_asnlookup_emits_cidrs_only():
    spec = _SPECS["asnlookup"]
    events = emit_events(
        spec["parse"], parse_records(spec["parse"], _SAMPLE), "asnlookup", "acme"
    )
    cidrs = {
        e.data["value"]
        for e in events
        if e.entity == "asset" and e.data.get("type") == "cidr"
    }
    # the four real prefixes parse (header / banner line dropped)
    assert cidrs == {
        "104.244.42.0/24",
        "199.16.156.0/22",
        "2606:4700::/32",
        "192.0.2.0/24",
    }, cidrs
    # the non-CIDR header / banner lines never become assets
    assert "IP addresses owned by acme are the following:" not in cidrs
    assert "no ip ranges found for this organization" not in cidrs


def test_off_by_default_and_passive():
    for name, spec in _SPECS.items():
        assert spec.get("default_on", False) is False, f"{name}: default_on must be false"
        assert spec.get("is_active", False) is False, f"{name}: is_active must be false"
        cls = build_adapter_class(spec)
        assert cls.is_active is False, f"{name}: built adapter must be inactive"


def test_contract_shape():
    spec = _SPECS["asnlookup"]
    cls = build_adapter_class(spec)
    # narrowest canonical consume type (org), producing an existing canonical type (cidr)
    assert cls.consumes == ("org",), cls.consumes
    assert cls.produces == ("cidr",), cls.produces
