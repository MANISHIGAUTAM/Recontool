"""Regression: the url-only exploitation layer (nuclei/arjun/Cat-10 url scanners)
must be REACHABLE by the recursion.

Bug found during a full active groww.in scan: gau/waybackurls/katana and even the
active httpx_probe emitted discovered URLs as `entity=endpoint`, but the recursion
feeder `discovered_assets()` only re-enqueues `entity=asset`. So no `url` key was
ever created, and `nuclei` (consumes only `url`) never ran — 0 work items, ever.

Fix: httpx_probe now also emits the confirmed-LIVE root URL as a recursable
`url` asset (bounded to live hosts, never the wayback firehose). These two tests
pin both halves of the chain: (1) the url asset survives discovered_assets(), and
(2) the router schedules nuclei for a url key.
"""
from __future__ import annotations

from recontool.adapters.base import Event
from recontool.engine.runner import discovered_assets, load_engine_registry
from recontool.engine.worker import RouteIndex


def test_httpx_probe_live_url_is_recursable():
    # Mirror what HttpProbe.run emits for one live host.
    events = [
        Event.endpoint("httpx_probe", "https://app.groww.in", status=200),
        Event.service("httpx_probe", "app.groww.in", 443, service_name="https"),
        Event.asset("httpx_probe", "subdomain", "app.groww.in", is_live=True),
        Event.asset("httpx_probe", "url", "https://app.groww.in", is_live=True),
    ]
    pairs = discovered_assets(events)
    # the url asset (not the endpoint) is what re-feeds the queue
    assert ("url", "https://app.groww.in") in pairs
    assert ("subdomain", "app.groww.in") in pairs


def test_router_schedules_nuclei_for_url_key():
    reg = load_engine_registry(tools="all", authorize_active=True)
    route = RouteIndex(reg)
    names = {s.name for s in route.for_key_type("url")}
    # the whole point: a url key now reaches the exploitation layer
    assert "nuclei" in names
