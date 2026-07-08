"""Contract tests for the PEOPLE / IDENTITY (PII) generic specs.

Pure + network-free: a realistic API JSON sample is run through the same parse
engine (parse_records + emit_events) the live adapter uses, and we assert:
  1. the right canonical entity comes out (finding for breach exposure),
  2. NO raw credential (password / hash / sha1) is ever stored in an Event —
     the PII-family redaction invariant (config/categories.yaml id:7),
  3. the family policy holds on every spec (default_on False, is_active False,
     requires_key set, narrowest consumes, canonical produces).

Grounding for the breachdirectory shape (mosint client source, json tags):
  https://raw.githubusercontent.com/alpkeskin/mosint/master/v3/pkg/services/breachdirectory/breachdirectory.go
"""
from __future__ import annotations

from pathlib import Path

import yaml

from recontool.adapters.generic import (
    build_adapter_class,
    emit_events,
    parse_records,
)

# config/tools_generic.d/people-api.yaml relative to repo root
_SPEC_PATH = (
    Path(__file__).resolve().parents[2]
    / "config" / "tools_generic.d" / "people-api.yaml"
)

# canonical types this family is allowed to produce (config/categories.yaml id:7)
_CANONICAL_PRODUCES = {"email", "username", "finding"}


def _load_specs() -> list[dict]:
    data = yaml.safe_load(_SPEC_PATH.read_text()) or {}
    return list(data.get("tools", []))


def _spec(name: str) -> dict:
    return next(s for s in _load_specs() if s["name"] == name)


# ── the file loads and contains the wired tool ───────────────────────────────
def test_people_api_specs_load():
    names = {s["name"] for s in _load_specs()}
    assert "breachdirectory" in names


# ── FAMILY POLICY holds on every spec (PII gate) ─────────────────────────────
def test_family_policy_invariants():
    specs = _load_specs()
    assert specs, "people-api.yaml declares no tools"
    for s in specs:
        nm = s["name"]
        assert s.get("default_on") is False, f"{nm}: default_on must be False (PII)"
        assert s.get("is_active") is False, f"{nm}: is_active must be False"
        assert s.get("requires_key"), f"{nm}: requires_key must be set (keyed API)"
        assert s.get("integration") == "api", f"{nm}: integration must be api"
        # narrowest seed only
        assert set(s.get("consumes", [])) <= {"domain", "email"}, \
            f"{nm}: consumes must be narrowest (domain|email)"
        # produces only existing canonical types
        assert set(s.get("produces", [])) <= _CANONICAL_PRODUCES, \
            f"{nm}: produces must be canonical {_CANONICAL_PRODUCES}"


# ── breachdirectory: realistic sample -> redacted finding, NO credential ─────
# mosint-verified response shape; the sample intentionally carries a raw
# password/sha1/hash so the redaction assertion has something to catch.
_BREACHDIR_SAMPLE = {
    "success": True,
    "found": 2,
    "result": [
        {
            "has_password": True,
            "sources": ["Collection1", "LinkedIn"],
            "password": "hunter2",
            "sha1": "f3bbbd66a63d4bf1747940578ec3d0103530e21d",
            "hash": "5f4dcc3b5aa765d61d8327deb882cf99",
        },
        {"has_password": False, "sources": ["AntiPublic"]},
    ],
}

# every raw-credential token that must NEVER appear in an emitted Event
_SECRET_TOKENS = (
    "hunter2",
    "f3bbbd66a63d4bf1747940578ec3d0103530e21d",
    "5f4dcc3b5aa765d61d8327deb882cf99",
    "has_password",
    "password",
)


def test_breachdirectory_emits_redacted_findings():
    spec = _spec("breachdirectory")
    recs = parse_records(spec["parse"], None, json_obj=_BREACHDIR_SAMPLE)
    assert len(recs) == 2  # list_path: result -> one record per entry

    events = emit_events(spec["parse"], recs, "breachdirectory", None)
    findings = [e for e in events if e.entity == "finding"]

    # one finding per result[] entry, all of the breach-exposure kind
    assert len(findings) == 2
    assert {f.entity for f in events} == {"finding"}  # nothing but findings
    for f in findings:
        assert f.data["kind"] == "breach_exposure"
        assert f.data["detector"] == "breachdirectory"
        assert f.data["severity"] == "medium"

    # the breach SOURCE name is allowed (it is not a credential)
    titles = " ".join(f.data["title"] for f in findings)
    assert "Collection1" in titles and "AntiPublic" in titles


def test_breachdirectory_never_stores_raw_credentials():
    """The core PII invariant: no password / hash / sha1 in any Event."""
    spec = _spec("breachdirectory")
    recs = parse_records(spec["parse"], None, json_obj=_BREACHDIR_SAMPLE)
    events = emit_events(spec["parse"], recs, "breachdirectory", None)

    blob = repr([e.data for e in events])
    for secret in _SECRET_TOKENS:
        assert secret not in blob, f"REDACTION FAIL: raw '{secret}' leaked into an Event"

    # belt-and-suspenders: no emit rule references a credential field at all
    emit_text = repr(spec["parse"]["emit"])
    for field in ("password", "sha1", "hash", "has_password"):
        assert field not in emit_text, f"emit rule references credential field '{field}'"


# ── the wired spec builds into a correct adapter contract ────────────────────
def test_breachdirectory_adapter_contract():
    spec = _spec("breachdirectory")
    cls = build_adapter_class(spec)
    assert cls.name == "breachdirectory"
    assert cls.consumes == ("email",)
    assert cls.produces == ("finding",)
    assert cls.is_active is False
    assert cls.key_env == "BREACHDIRECTORY_API_KEY"
