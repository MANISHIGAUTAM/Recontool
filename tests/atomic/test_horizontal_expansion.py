"""Batch-12 F5: horizontal-expansion family — dnsx-ptr (ip -> in-scope subdomain via PTR)."""
from __future__ import annotations

import json

import yaml

from recontool.adapters.generic import emit_events, parse_records
from recontool.config import REPO_ROOT
from recontool.engine.runner import load_engine_registry

_SPEC = yaml.safe_load(
    (REPO_ROOT / "config" / "tools_generic.d" / "horizontal-expansion.yaml").read_text()
)["tools"][0]


def test_dnsx_ptr_emit_scope_filtered():
    rec = json.dumps({"host": "1.2.3.4", "ptr": ["mail.example.com", "unrelated.other.com"]})
    events = emit_events(_SPEC["parse"], parse_records(_SPEC["parse"], rec), "dnsx-ptr", "example.com")
    subs = [e.data["value"] for e in events
            if e.entity == "asset" and e.data.get("type") == "subdomain"]
    assert "mail.example.com" in subs
    assert "unrelated.other.com" not in subs, "out-of-scope PTR must be dropped"


def test_dnsx_ptr_off_by_default_and_narrow():
    reg = load_engine_registry(tools="all", authorize_active=True)
    spec = reg.get("dnsx-ptr")
    assert spec is not None
    consumes = set(spec.supported_input_types or []) | set(spec.consumes or [])
    assert consumes == {"ip"}
    assert getattr(spec, "default_on", False) is False
