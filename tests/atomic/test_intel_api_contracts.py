"""Atomic contract tests for the "intel-api" tool family.

Pure fixture tests: feed a realistic sample of each API's REAL JSON response
(grounded against official docs + a real parser source — see config comments) to
the generic parse engine and assert the expected normalized entities. No network.

Also asserts the integration invariants required of every passive intel lookup:
default_on is False, is_active is False, integration is api, and a key is required.

WIRED:    abuseipdb (GET /api/v2/check, header "Key"), threatfox (POST + JSON
          body + Auth-Key), urlhaus (POST + form body + Auth-Key). The generic
          adapter now supports POST (JSON or form body).
DEFERRED: bufferover (Results entries are CSV strings the generic value_each
          cannot field-extract). See intel-api.yaml for the rationale.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from recontool.adapters.generic import (
    build_adapter_class,
    emit_events,
    parse_records,
    render_template,
)

INTEL_YAML = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "tools_generic.d"
    / "intel-api.yaml"
)

# Tools we DELIBERATELY did not wire (real API still can't be expressed by the
# generic adapter — bufferover returns CSV strings). Guards against silent re-add.
DEFERRED = {"bufferover"}


def _load_specs() -> dict[str, dict]:
    data = yaml.safe_load(INTEL_YAML.read_text()) or {}
    return {t["name"]: t for t in (data.get("tools") or [])}


def _ev(events, entity):
    return [e for e in events if e.entity == entity]


# ── the YAML is well-formed and only wires what we can ground ─────────────────
def test_intel_yaml_loads_and_wires_only_supported_tools():
    specs = _load_specs()
    for wired in ("abuseipdb", "threatfox", "urlhaus"):
        assert wired in specs, f"{wired} must be wired"
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


# ── ThreatFox: real search_ioc response -> tag + reputation finding ───────────
# Sample matches the verbatim example at https://threatfox.abuse.ch/api/ .
THREATFOX_SAMPLE = {
    "query_status": "ok",
    "data": [
        {
            "id": "12",
            "ioc": "139.180.203.104:443",
            "threat_type": "botnet_cc",
            "ioc_type": "ip:port",
            "malware_printable": "Cobalt Strike",
            "confidence_level": 75,
            "first_seen": "2020-12-06 09:10:23 UTC",
        }
    ],
}
# no-match responses carry no data[] -> list_path resolves to nothing -> 0 records
THREATFOX_EMPTY = {"query_status": "no_result"}


def test_threatfox_emits_tag_and_finding():
    spec = _load_specs()["threatfox"]
    recs = parse_records(spec["parse"], None, json_obj=THREATFOX_SAMPLE)
    assert len(recs) == 1
    events = emit_events(spec["parse"], recs, "threatfox", seed_domain=None)

    tags = _ev(events, "asset")
    assert tags and tags[0].data["type"] == "tag"
    assert tags[0].data["value"] == "threatfox:Cobalt Strike (botnet_cc)"

    findings = _ev(events, "finding")
    assert findings
    f = findings[0].data
    assert f["detector"] == "threatfox"
    assert f["asset_value"] == "139.180.203.104:443"
    assert "Cobalt Strike" in f["title"] and "75" in f["title"]


def test_threatfox_no_match_emits_nothing():
    spec = _load_specs()["threatfox"]
    recs = parse_records(spec["parse"], None, json_obj=THREATFOX_EMPTY)
    assert recs == []
    assert emit_events(spec["parse"], recs, "threatfox", seed_domain=None) == []


# ── URLhaus: real host response -> tag + malware-hosting finding ──────────────
# Sample matches the verbatim example at https://urlhaus-api.abuse.ch/ (host).
URLHAUS_SAMPLE = {
    "query_status": "ok",
    "host": "vektorex.com",
    "url_count": "120",
    "blacklists": {"spamhaus_dbl": "abused_legit_malware", "surbl": "not listed"},
    "urls": [
        {
            "id": "121319",
            "url": "http://vektorex.com/source/Z/5016223.exe",
            "url_status": "online",
            "date_added": "2019-02-11 07:45:05 UTC",
            "threat": "malware_download",
            "tags": ["AZORult", "exe"],
        }
    ],
}
URLHAUS_EMPTY = {"query_status": "no_results", "urls": []}


def test_urlhaus_emits_tag_and_finding():
    spec = _load_specs()["urlhaus"]
    recs = parse_records(spec["parse"], None, json_obj=URLHAUS_SAMPLE)
    assert len(recs) == 1
    events = emit_events(spec["parse"], recs, "urlhaus", seed_domain=None)

    tags = _ev(events, "asset")
    assert tags and tags[0].data["type"] == "tag"
    assert tags[0].data["value"] == "urlhaus:malware_download (online)"

    findings = _ev(events, "finding")
    assert findings
    f = findings[0].data
    assert f["detector"] == "urlhaus"
    assert f["asset_value"] == "http://vektorex.com/source/Z/5016223.exe"
    assert "malware_download" in f["title"]


def test_urlhaus_no_results_emits_nothing():
    spec = _load_specs()["urlhaus"]
    recs = parse_records(spec["parse"], None, json_obj=URLHAUS_EMPTY)
    assert emit_events(spec["parse"], recs, "urlhaus", seed_domain=None) == []


# ── POST-body wiring: the mechanism the adapter relies on at run() time ───────
def test_threatfox_post_body_json_bool_passthrough():
    spec = _load_specs()["threatfox"]
    assert spec["method"] == "POST"
    assert spec.get("body_format") in (None, "json")   # default JSON body
    extra = {"value": "1.2.3.4"}
    body = {k: render_template(bv, {}, extra) for k, bv in spec["body"].items()}
    assert body["query"] == "search_ioc"
    assert body["search_term"] == "1.2.3.4"            # {value} substituted
    assert body["exact_match"] is True                 # bool passes through (not "True")


def test_urlhaus_post_body_is_form_encoded():
    spec = _load_specs()["urlhaus"]
    assert spec["method"] == "POST"
    assert spec["body_format"] == "form"               # host=<value>, not JSON
    extra = {"value": "evil.example.com"}
    body = {k: render_template(bv, {}, extra) for k, bv in spec["body"].items()}
    assert body == {"host": "evil.example.com"}
