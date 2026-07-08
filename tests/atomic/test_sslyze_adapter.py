"""Handwritten sslyze adapter — maps sslyze's deeply-nested JSON
(server_scan_results[].scan_result.{...}.result) into TLS findings. The generic
emit does flat/dotted field access and can't fan a dozen heterogeneous finding
types out of that tree.
"""
from __future__ import annotations

import json

from recontool.adapters.active import SslyzeScan, _parse_sslyze_json


def _doc(scan_result: dict) -> str:
    doc = {"server_scan_results": [
        {"server_location": {"hostname": "vuln.example.com", "port": 443},
         "scan_result": scan_result}]}
    # sslyze appends trailing content after the JSON -> exercise raw_decode
    return json.dumps(doc) + "\n<trailing noise sslyze sometimes emits>"


def _ok(result: dict) -> dict:
    return {"status": "COMPLETED", "result": result}


def test_parse_detects_the_headline_vulns():
    sr = {
        "heartbleed": _ok({"is_vulnerable_to_heartbleed": True}),
        "openssl_ccs_injection": _ok({"is_vulnerable_to_ccs_injection": True}),
        "robot": _ok({"robot_result": "VULNERABLE_WEAK_ORACLE"}),
        "ssl_3_0_cipher_suites": _ok({"accepted_cipher_suites": [{"x": 1}]}),
        "tls_1_0_cipher_suites": _ok({"accepted_cipher_suites": [{"x": 1}]}),
        "certificate_info": _ok({"certificate_deployments": [{
            "verified_chain_has_sha1_signature": True,
            "path_validation_results": [{"was_validation_successful": False,
                                         "validation_error": "self signed"}]}]}),
    }
    evs = _parse_sslyze_json(_doc(sr), "fallback", "sslyze")
    titles = " | ".join(e.data["title"] for e in evs)
    assert all(e.entity == "finding" for e in evs)
    assert "Heartbleed" in titles
    assert "CCS injection" in titles
    assert "ROBOT" in titles
    assert "SSLv3" in titles and "TLS 1.0" in titles
    assert "SHA-1" in titles
    assert "Certificate validation failed" in titles and "self signed" in titles
    hb = next(e for e in evs if "Heartbleed" in e.data["title"])
    assert hb.data["severity"] == "critical" and hb.data["cve_id"] == "CVE-2014-0160"
    assert all(e.data["asset_value"] == "vuln.example.com:443" for e in evs)


def test_parse_clean_host_yields_no_findings():
    sr = {
        "heartbleed": _ok({"is_vulnerable_to_heartbleed": False}),
        "openssl_ccs_injection": _ok({"is_vulnerable_to_ccs_injection": False}),
        "robot": _ok({"robot_result": "NOT_VULNERABLE_NO_ORACLE"}),
        "ssl_2_0_cipher_suites": _ok({"accepted_cipher_suites": []}),
        "certificate_info": _ok({"certificate_deployments": [{
            "verified_chain_has_sha1_signature": False,
            "path_validation_results": [{"was_validation_successful": True}]}]}),
    }
    assert _parse_sslyze_json(_doc(sr), "h", "sslyze") == []


def test_parse_malformed_is_safe_and_skips_incomplete():
    assert _parse_sslyze_json("not json", "h", "sslyze") == []
    # a scan command that didn't COMPLETE must not be read as a result
    sr = {"heartbleed": {"status": "ERROR", "result": None}}
    assert _parse_sslyze_json(_doc(sr), "h", "sslyze") == []


def test_sslyze_adapter_contract_and_default_off():
    ad = SslyzeScan()
    assert ad.name == "sslyze" and ad.is_active is True
    assert ad.consumes == ("subdomain",) and ad.produces == ("finding",)
    assert ad.default_on is False


def test_sslyze_bridges_into_registry_as_handwritten():
    from recontool.engine.runner import load_engine_registry
    from recontool.engine.execution import build_adapter_for
    reg = load_engine_registry(tools="all", authorize_active=True)
    spec = reg.all_tools()["sslyze"]
    assert spec.integration == "python" and spec.default_on is False
    assert build_adapter_for(spec).__name__ == "SslyzeScan"
