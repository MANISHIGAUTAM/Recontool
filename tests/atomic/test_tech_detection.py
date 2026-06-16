"""Batch-12 F2: whatweb emits first-class `tech` entities (grounded in real whatweb JSON).

The placeholder-doc tech tools (webanalyze/wappalyzer/fingerprintx/builtwith) are DEFERRED
— their output schema isn't captured in repo docs, so a correct parser can't be written
without inventing a format. whatweb already parses its real --log-json output, so it is the
grounded tech producer.
"""
from __future__ import annotations

import json

from recontool.adapters.active import WhatWebScan, _parse_whatweb_json

_SAMPLE = json.dumps([
    {"target": "https://example.com",
     "plugins": {"nginx": {}, "WordPress": {}, "jQuery": {}}}
])


def test_whatweb_emits_tech_assets():
    events = _parse_whatweb_json(_SAMPLE, "example.com", "whatweb")
    tech = {e.data.get("value") for e in events
            if e.entity == "asset" and e.data.get("type") == "tech"}
    assert {"nginx", "WordPress", "jQuery"} <= tech
    # the human-readable summary finding is still emitted
    assert any(e.entity == "finding" and e.data.get("kind") == "tech" for e in events)


def test_whatweb_declares_tech():
    assert "tech" in WhatWebScan.produces
