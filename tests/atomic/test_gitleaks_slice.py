"""The gitleaks vertical slice: github_org_repos (org -> repo) producer + the
handwritten GitleaksScan consumer (repo -> redacted secret findings), closing the
loop on the `repo` canonical entity type.
"""
from __future__ import annotations

import json

from recontool.adapters.generic import emit_events, parse_records
from recontool.adapters.passive import GitleaksScan, _mask_secret, _parse_gitleaks


# ── producer: github_org_repos emits repo assets from the API's clone_url ──────
def test_github_org_repos_emits_repo_from_clone_url():
    from recontool.engine.runner import load_engine_registry
    from recontool.engine.execution import to_generic_spec
    reg = load_engine_registry(tools="all", authorize_active=True)
    spec = to_generic_spec(reg.all_tools()["github_org_repos"])
    api_array = [{"clone_url": "https://github.com/acme/web.git", "name": "web"},
                 {"clone_url": "https://github.com/acme/api.git", "name": "api"}]
    recs = parse_records(spec["parse"], None, json_obj=api_array)
    evs = emit_events(spec["parse"], recs, "github_org_repos", None)
    assert {e.data["value"] for e in evs} == {
        "https://github.com/acme/web.git", "https://github.com/acme/api.git"}
    assert all(e.data["type"] == "repo" for e in evs)


# ── consumer: gitleaks parses findings and REDACTS the raw secret ─────────────
def test_gitleaks_parse_redacts_secret():
    raw = json.dumps([{
        "Description": "AWS Access Key", "StartLine": 12, "File": "config/prod.py",
        "Secret": "AKIAIOSFODNN7EXAMPLE", "Match": "key=AKIAIOSFODNN7EXAMPLE",
        "RuleID": "aws-access-token"}])
    evs = _parse_gitleaks(raw, "https://github.com/acme/web.git", "gitleaks")
    assert len(evs) == 1
    ev = evs[0].data
    assert ev["kind"] == "secret" and ev["severity"] == "high"
    assert ev["detector"] == "gitleaks:aws-access-token"
    assert ev["asset_value"] == "https://github.com/acme/web.git"
    # the raw secret must NEVER appear anywhere in the event
    blob = json.dumps(evs[0].data)
    assert "AKIAIOSFODNN7EXAMPLE" not in blob
    assert ev["evidence_redacted"]["preview"] == _mask_secret("AKIAIOSFODNN7EXAMPLE")
    assert ev["evidence_redacted"]["file"] == "config/prod.py"


def test_gitleaks_parse_malformed_safe():
    assert _parse_gitleaks("not json", "u", "gitleaks") == []
    assert _parse_gitleaks("[]", "u", "gitleaks") == []


# ── the loop closes: repo is produced AND consumed (no dead-end) ──────────────
def test_repo_type_is_produced_and_consumed():
    from recontool.engine.runner import load_engine_registry
    reg = load_engine_registry(tools="all", authorize_active=True)
    tools = reg.all_tools()
    producers = [n for n, s in tools.items()
                 if "repo" in (set(getattr(s, "produces", ())) | set(getattr(s, "output_types", ())))]
    consumers = [n for n, s in tools.items()
                 if "repo" in (set(getattr(s, "consumes", ())) | set(getattr(s, "supported_input_types", ())))]
    assert "github_org_repos" in producers
    assert "gitleaks" in consumers
    # gitleaks is the handwritten adapter, not the old broken generic spec
    assert tools["gitleaks"].integration == "python"
    assert tuple(tools["gitleaks"].consumes) == ("repo",)
