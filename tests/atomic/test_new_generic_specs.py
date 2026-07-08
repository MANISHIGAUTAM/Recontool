"""Validate the newly wired generic specs parse + emit correctly (no network).

Loads the ACTUAL config/tools_generic.yaml specs and runs the pure parse engine
against representative raw output, so the shipped contracts — not just patterns —
are proven. Catches typos in endpoints/invocations/parse mappings.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from recontool.adapters.generic import emit_events, parse_records

SPECS = {
    s["name"]: s
    for s in yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "config" / "tools_generic.yaml").read_text()
    )["tools"]
}


def test_anubis_jldc_json_array_scope_filtered():
    spec = SPECS["anubis-jldc"]
    recs = parse_records(spec["parse"], None,
                         json_obj=["api.example.com", "vpn.example.com", "evil.com"])
    events = emit_events(spec["parse"], recs, "anubis-jldc", "example.com")
    vals = {e.data["value"] for e in events}
    assert vals == {"api.example.com", "vpn.example.com"}  # evil.com dropped (out of scope)
    assert all(e.data["type"] == "subdomain" for e in events)


def test_mapcidr_text_to_ips():
    spec = SPECS["mapcidr"]
    recs = parse_records(spec["parse"], "1.2.3.0\n1.2.3.1\n# comment\n1.2.3.2")
    events = emit_events(spec["parse"], recs, "mapcidr", None)
    assert {e.data["value"] for e in events} == {"1.2.3.0", "1.2.3.1", "1.2.3.2"}
    assert all(e.data["type"] == "ip" for e in events)


def test_metabigor_is_stdin_and_emits_cidr():
    spec = SPECS["metabigor"]
    assert spec.get("stdin") is True          # reads the ASN from stdin
    recs = parse_records(spec["parse"], "1.2.3.0/24\n5.6.7.0/24")
    events = emit_events(spec["parse"], recs, "metabigor", None)
    assert {e.data["value"] for e in events} == {"1.2.3.0/24", "5.6.7.0/24"}
    assert all(e.data["type"] == "cidr" for e in events)
