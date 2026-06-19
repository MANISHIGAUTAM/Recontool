"""Atomic contract test for the identity-osint generic-adapter family.

Pure fixture test (no network, no subprocess): a realistic sample of the tool's
VERIFIED stdout is fed through the real parse_records -> emit_events engine and we
assert the exact entities that come out, plus the overlay invariants the family
must hold (default_on:false, is_active:false).

Grounding (see config/tools_generic.d/identity-osint.yaml for inline citations):
  holehe `--no-color` per-site line for an EXISTING account is literal ASCII
  `[+] <domain>[ extras]`; not-found/rate-limited/error use `[-]`/`[x]`/`[!]`.
  Source: holehe/core.py print loop (megadose/holehe@master).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from recontool.config import CONFIG_DIR
from recontool.adapters.generic import emit_events, parse_records

FAMILY_YAML = Path(CONFIG_DIR) / "tools_generic.d" / "identity-osint.yaml"


def _load_specs() -> dict[str, dict]:
    data = yaml.safe_load(FAMILY_YAML.read_text()) or {}
    return {t["name"]: t for t in data.get("tools", [])}


# realistic holehe `--no-color` stdout: a banner, mixed result markers, summary.
HOLEHE_STDOUT = """\
*-------------------- holehe megadose --------------------*

[+] twitter.com ex****e@gmail.com / 0*******78
[-] facebook.com
[x] instagram.com
[!] github.com Error message: timeout
[+] spotify.com

121 websites checked in 12.34 seconds
"""


def test_holehe_emits_account_findings_for_registered_sites_only():
    holehe = _load_specs()["holehe"]
    parse = holehe["parse"]

    recs = parse_records(parse, HOLEHE_STDOUT)
    # only the two `[+]` lines survive the line_regex; markers/banner/summary drop
    assert [r["site"] for r in recs] == ["twitter.com", "spotify.com"]

    events = emit_events(parse, recs, "holehe", seed_domain="example.com")
    findings = [e for e in events if e.entity == "finding"]
    assert len(findings) == 2
    f = findings[0].data
    assert f["kind"] == "account"
    assert f["title"] == "twitter.com"
    assert f["asset_value"] == "twitter.com"
    assert f["detector"] == "holehe"
    # no non-finding entities leak from this overlay tool
    assert all(e.entity == "finding" for e in events)


def test_holehe_empty_or_all_negative_emits_nothing():
    holehe = _load_specs()["holehe"]
    parse = holehe["parse"]
    negative = "*-- holehe --*\n[-] facebook.com\n[x] instagram.com\n0 websites checked\n"
    recs = parse_records(parse, negative)
    assert recs == []
    assert emit_events(parse, recs, "holehe", "example.com") == []


def test_holehe_contract_shape():
    holehe = _load_specs()["holehe"]
    assert holehe["integration"] == "cli"
    assert holehe["binary"] == "holehe"
    assert "{value}" in holehe["invocation"] and "--no-color" in holehe["invocation"]
    # narrowest canonical consume; produces existing canonical type only
    assert holehe["consumes"] == ["email"]
    assert holehe["produces"] == ["finding"]


def test_family_overlay_invariants_default_off_and_inactive():
    specs = _load_specs()
    assert specs, "identity-osint family must declare at least one wired tool"
    for name, spec in specs.items():
        # overlay family: never ships on, never probes the in-scope target
        assert spec.get("default_on") is False, f"{name} must be default_on:false"
        assert spec.get("is_active") is False, f"{name} must be is_active:false"
