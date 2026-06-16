"""Batch-12 F1: dns-records family contract (dnsx record-mode → subdomain + dns_record).

Verifies the declarative emit against dnsx's real JSON record-mode shape (no network):
  - in-scope NS hostnames become subdomains; third-party nameservers are scope-dropped;
  - MX / TXT / CAA become dns_record evidence;
  - the tool ships off by default (the dns-records profile is opt-in).
"""
from __future__ import annotations

import json

import yaml

from recontool.adapters.generic import emit_events, parse_records
from recontool.config import REPO_ROOT
from recontool.engine.runner import load_engine_registry

_SPEC = yaml.safe_load(
    (REPO_ROOT / "config" / "tools_generic.d" / "dns-records.yaml").read_text()
)["tools"][0]

_SAMPLE = json.dumps({
    "host": "example.com",
    "ns": ["ns1.example.com", "ns2.example.com", "ns1.cloudflare.com"],
    "mx": ["10 mail.example.com"],
    "txt": ["v=spf1 include:_spf.google.com ~all"],
    "caa": ["0 issue letsencrypt.org"],
})


def _vals(events, atype):
    return [e.data.get("value") for e in events
            if e.entity == "asset" and e.data.get("type") == atype]


def test_dnsx_records_emit():
    recs = parse_records(_SPEC["parse"], _SAMPLE)
    events = emit_events(_SPEC["parse"], recs, "dnsx-records", "example.com")
    subs = _vals(events, "subdomain")
    assert "ns1.example.com" in subs and "ns2.example.com" in subs
    assert "ns1.cloudflare.com" not in subs, "third-party NS must be scope-dropped"
    dns = _vals(events, "dns_record")
    assert any("mail.example.com" in d for d in dns)          # MX
    assert any(d.startswith("v=spf1") for d in dns)           # TXT/SPF
    assert any("issue letsencrypt.org" in d for d in dns)     # CAA


def test_dnsx_records_is_off_by_default_and_narrow():
    reg = load_engine_registry(tools="all", authorize_active=True)
    spec = reg.get("dnsx-records")
    assert spec is not None, "dnsx-records (dns-records family) must be loaded"
    consumes = set(spec.supported_input_types or []) | set(spec.consumes or [])
    assert consumes == {"subdomain"}, "must consume only subdomain (narrow)"
    assert getattr(spec, "default_on", False) is False, "must ship off by default"
