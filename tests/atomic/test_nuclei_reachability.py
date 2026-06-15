"""Regression + M3 gate: the active/deep layer is reachable, and ONLY via a
httpx-validated live host.

History: a full active groww.in scan produced 0 work items for nuclei because
httpx_probe emitted discovered URLs as `entity=endpoint`, which `discovered_assets()`
does not re-feed (it only re-enqueues `entity=asset`). httpx_probe was fixed to emit
a recursable root asset for each confirmed-live host.

M3 makes that asset a first-class `live_host` (not a raw `url`) and routes the
active/deep layer (nuclei, whatweb, gowitness, katana) off `live_host`, so it can
only fire on a host httpx confirmed live — never on an unvalidated subdomain.

These tests are registry-level (deterministic), not RouteIndex-level: RouteIndex
prunes tools whose binary is not installed, which would make the assertion depend on
the host environment.
"""
from __future__ import annotations

import json

import yaml

from recontool.adapters.base import Event
from recontool.adapters.generic import emit_events, parse_records
from recontool.config import REPO_ROOT
from recontool.engine.runner import discovered_assets, load_engine_registry


def _io(reg, name):
    spec = reg.get(name)
    consumes = set(spec.supported_input_types or []) | set(spec.consumes or [])
    produces = set(spec.output_types or []) | set(spec.produces or [])
    return consumes, produces


def test_httpx_probe_emits_recursable_live_host():
    # Mirror what HttpProbe.run emits for one live host.
    events = [
        Event.endpoint("httpx_probe", "https://app.groww.in", status=200),
        Event.service("httpx_probe", "app.groww.in", 443, service_name="https"),
        Event.asset("httpx_probe", "subdomain", "app.groww.in", is_live=True),
        Event.asset("httpx_probe", "live_host", "https://app.groww.in", is_live=True),
    ]
    pairs = discovered_assets(events)
    # the live_host asset (not the endpoint) is what re-feeds the queue
    assert ("live_host", "https://app.groww.in") in pairs
    assert ("subdomain", "app.groww.in") in pairs


def test_httpx_generic_emit_produces_live_host():
    """httpx runs via the GENERIC CLI path, so its parse.emit — not the httpx_probe
    adapter — is the real runtime producer of live_host. Pin it so a future emit edit
    can't silently kill the gate (the declared output_type alone would not catch it)."""
    spec = yaml.safe_load((REPO_ROOT / "config" / "tools.yaml").read_text())["tools"]["httpx"]
    rec = json.dumps({"url": "https://app.groww.in", "a": ["1.2.3.4"], "status_code": 200})
    events = emit_events(spec["parse"], parse_records(spec["parse"], rec), "httpx", "groww.in")
    asset_types = {e.data.get("type") for e in events if e.entity == "asset"}
    assert "live_host" in asset_types, f"httpx must emit a live_host asset; got {asset_types}"


def test_active_layer_is_gated_behind_live_host():
    reg = load_engine_registry(tools="all", authorize_active=True)

    # httpx is the validator: it PRODUCES the live_host that gates everything else.
    _, httpx_produces = _io(reg, "httpx")
    assert "live_host" in httpx_produces

    # the active/deep layer CONSUMES live_host (so it only fires post-validation)...
    for tool in ("nuclei", "whatweb", "gowitness", "katana"):
        consumes, _ = _io(reg, tool)
        assert "live_host" in consumes, f"{tool} must consume live_host (M3 gate)"

    # ...and no longer fires on a bare, unvalidated subdomain.
    for tool in ("nuclei", "whatweb", "gowitness", "katana"):
        consumes, _ = _io(reg, tool)
        assert "subdomain" not in consumes, f"{tool} must NOT consume raw subdomain"
