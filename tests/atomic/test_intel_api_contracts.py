"""Atomic contract tests for the "intel-api" tool family.

Pure fixture tests: feed a realistic sample of each API's REAL JSON response
(grounded against official docs + a real parser source — see config comments) to
the generic parse engine and assert the expected normalized entities. No network.

Also asserts the integration invariants required of every passive intel lookup:
default_on is False, is_active is False, integration is api, and a key is required.

WIRED:    abuseipdb  (GET /api/v2/check, header "Key" — fits the generic adapter)
DEFERRED: threatfox, urlhaus (POST + mandatory Auth-Key; generic adapter is
          GET-only), bufferover (Results entries are CSV strings the generic
          value_each cannot field-extract). See intel-api.yaml for the rationale.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from recontool.adapters.generic import (
    build_adapter_class,
    emit_events,
    parse_records,
)

INTEL_YAML = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "tools_generic.d"
    / "intel-api.yaml"
)

# Tools we DELIBERATELY did not wire (real API can't be expressed by the
# GET-only / list-or-dict generic adapter). Guards against silent re-add.
DEFERRED = {"threatfox", "urlhaus", "bufferover"}


def _load_specs() -> dict[str, dict]:
    data = yaml.safe_load(INTEL_YAML.read_text()) or {}
    return {t["name"]: t for t in (data.get("tools") or [])}


def _ev(events, entity):
    return [e for e in events if e.entity == entity]


# ── the YAML is well-formed and only wires what we can ground ─────────────────
def test_intel_yaml_loads_and_wires_only_supported_tools():
    specs = _load_specs()
    assert "abuseipdb" in specs, "abuseipdb must be wired"
    # deferred tools must NOT appear as live specs
    assert DEFERRED.isdisjoint(specs), (
        f"deferred tool present in YAML tools list: {DEFERRED & set(specs)}"
    )


# ── integration invariants: every wired intel tool is OFF + passive + keyed ──
def test_every_wired_tool_is_passive_off_and_keyed():
    specs = _load_specs()
    for name, spec in specs.items():
        assert spec.get("default_on") is False, f"{name}: default_on must be False"
        assert spec.get("is_active") is False, f"{name}: is_active must be False"
        assert spec.get("integration") == "api", f"{name}: integration must be api"
        assert spec.get("requires_key"), f"{name}: must require an API key"
        # the built adapter reflects the same contract
        cls = build_adapter_class(spec)
        assert cls.is_active is False
        assert cls.key_env == spec["requires_key"]


# ── abuseipdb: real CHECK response -> tag + reputation finding ────────────────
# Sample is the verbatim example from https://docs.abuseipdb.com/ (CHECK).
ABUSEIPDB_SAMPLE = {
    "data": {
        "ipAddress": "118.25.6.39",
        "isPublic": True,
        "ipVersion": 4,
        "isWhitelisted": False,
        "abuseConfidenceScore": 100,
        "countryCode": "CN",
        "countryName": "China",
        "usageType": "Data Center/Web Hosting/Transit",
        "isp": "Tencent Cloud Computing (Beijing) Co. Ltd",
        "domain": "tencent.com",
        "hostnames": [],
        "isTor": False,
        "totalReports": 1,
        "numDistinctUsers": 1,
        "lastReportedAt": "2018-12-20T20:55:14+00:00",
    }
}


def test_abuseipdb_emits_tag_and_finding():
    spec = _load_specs()["abuseipdb"]
    # data is a single object -> exactly one record
    recs = parse_records(spec["parse"], None, json_obj=ABUSEIPDB_SAMPLE)
    assert len(recs) == 1
    assert recs[0]["ipAddress"] == "118.25.6.39"

    events = emit_events(spec["parse"], recs, "abuseipdb", seed_domain=None)

    tags = _ev(events, "asset")
    assert tags, "expected a reputation tag asset"
    assert tags[0].data["type"] == "tag"
    assert tags[0].data["value"] == "abuseipdb:score=100"

    findings = _ev(events, "finding")
    assert findings, "expected a reputation finding"
    f = findings[0].data
    assert f["kind"] == "reputation"
    assert f["detector"] == "abuseipdb"
    assert f["asset_value"] == "118.25.6.39"          # finding ties back to the IP
    assert "100" in f["title"]                         # confidence score surfaced
    assert "Tencent" in f["title"]                     # isp surfaced


def test_abuseipdb_consumes_ip_produces_intel_types():
    cls = build_adapter_class(_load_specs()["abuseipdb"])
    assert cls.consumes == ("ip",)
    # produces only EXISTING canonical types
    assert set(cls.produces) <= {"tag", "finding", "ioc"}
    assert "tag" in cls.produces and "finding" in cls.produces
