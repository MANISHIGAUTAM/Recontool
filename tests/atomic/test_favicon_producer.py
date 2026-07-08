"""Batch-12 F3: httpx -favicon emits a `favicon` asset (real httpx mmh3 field).

Unlocks the opt-in favicon pivot (favfreak / fav-up / favicon-shodan). The emit is safe:
a host with no favicon renders empty and is dropped by the emit gate.
"""
from __future__ import annotations

import json

import yaml

from recontool.adapters.generic import emit_events, parse_records
from recontool.config import REPO_ROOT

_SPEC = yaml.safe_load((REPO_ROOT / "config" / "tools.yaml").read_text())["tools"]["httpx"]


def test_httpx_emits_favicon():
    rec = json.dumps({"url": "https://app.example.com", "a": ["1.2.3.4"],
                      "favicon": "-1485257654"})
    events = emit_events(_SPEC["parse"], parse_records(_SPEC["parse"], rec), "httpx", "example.com")
    fav = [e.data["value"] for e in events
           if e.entity == "asset" and e.data.get("type") == "favicon"]
    assert "-1485257654" in fav
    # still emits the live_host gate asset
    assert any(e.entity == "asset" and e.data.get("type") == "live_host" for e in events)


def test_httpx_no_favicon_field_is_safe():
    rec = json.dumps({"url": "https://app.example.com", "a": ["1.2.3.4"]})  # no favicon
    events = emit_events(_SPEC["parse"], parse_records(_SPEC["parse"], rec), "httpx", "example.com")
    fav = [e for e in events if e.entity == "asset" and e.data.get("type") == "favicon"]
    assert fav == [], "absent favicon must not emit a junk asset"
