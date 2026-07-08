"""Regression guard for the host-rooted active-tool routing fix.

Finding (2026-07 contract audit): content-discovery / host-scanner / crawler
tools declared `input: url`, but NOTHING in the engine emits a recursable `url`
asset (URL-discovery tools emit `endpoint`, a recursion terminal). So in a
domain-seeded scan these tools were unreachable — never scheduled on discovered
content. Fix: they consume `live_host` (httpx-validated roots), like katana.

This test pins that so a revert to url-only is caught. `url` is kept too so an
explicit URL seed still routes.
"""
from __future__ import annotations

from recontool.engine.runner import load_engine_registry

HOST_ROOTED = [
    "ffuf", "feroxbuster", "nikto", "wafw00f",
    "kiterunner", "cariddi", "gospider", "hakrawler",
]


def _consumes(spec) -> set[str]:
    return set(spec.consumes or []) | set(spec.supported_input_types or [])


def test_host_rooted_tools_consume_live_host():
    reg = load_engine_registry()
    missing = []
    for name in HOST_ROOTED:
        spec = reg._tools.get(name)
        assert spec is not None, f"{name} not in registry"
        if "live_host" not in _consumes(spec):
            missing.append(name)
    assert not missing, (
        f"host-rooted tools no longer consume live_host (unreachable in domain "
        f"scans): {missing}"
    )
