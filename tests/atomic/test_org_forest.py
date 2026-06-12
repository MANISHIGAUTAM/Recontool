"""Atomic tests for org-forest fingerprint extraction (research doc §2d).

Pure extraction (no network): analytics ids, copyright org, favicon hash, plus a
check that the adapter is bridged into the engine and routable + active-gated.
"""
from __future__ import annotations

import importlib.util

import pytest

from recontool.adapters.org_forest import (
    extract_analytics_ids,
    extract_org_strings,
    favicon_hash,
)


def test_extract_analytics_ids_covers_ga_ga4_gtm_adsense():
    html = """
      gtag('config', 'UA-123456-1');
      <script src="https://www.googletagmanager.com/gtag/js?id=G-ABC123DEF4"></script>
      (function(w,d){w.dataLayer=w.dataLayer||[];})(window,'GTM-ABCD12');
      <ins class="adsbygoogle" data-ad-client="ca-pub-1234567890123456"></ins>
    """
    ids = set(extract_analytics_ids(html))
    assert {"UA-123456-1", "G-ABC123DEF4", "GTM-ABCD12", "ca-pub-1234567890123456"} <= ids


def test_extract_analytics_ids_empty():
    assert extract_analytics_ids("") == []
    assert extract_analytics_ids("<html>no ids here</html>") == []


def test_extract_org_strings_from_copyright_footer():
    html = "<footer>© 2024 Acme Corporation. All rights reserved.</footer>"
    orgs = extract_org_strings(html)
    assert any("Acme Corporation" in o for o in orgs)


def test_favicon_hash_is_graceful_without_content():
    assert favicon_hash(b"") is None


def test_favicon_hash_is_shodan_int_when_mmh3_present():
    if importlib.util.find_spec("mmh3") is None:
        pytest.skip("mmh3 not installed (favicon pivot degrades cleanly)")
    h = favicon_hash(b"<svg>fake favicon bytes</svg>")
    assert isinstance(h, int)


def test_org_fingerprint_is_bridged_routable_and_active_gated():
    from recontool.engine.adapters_bridge import register_python_adapters
    from recontool.engine.execution import plan_execution
    from recontool.engine.registry import ToolRegistry
    from recontool.engine.selection import apply_selection

    reg = ToolRegistry(tools={})
    register_python_adapters(reg)
    spec = reg.get("org_fingerprint")
    assert spec is not None and spec.integration == "python"
    assert spec.is_active is True
    assert set(spec.produces) >= {"favicon", "analytics_id", "org"}
    assert plan_execution(spec).runnable
    # routable from a discovered subdomain
    assert "org_fingerprint" in {s.name for s in reg.by_input_type("subdomain")}
    # active -> off without authorization, on with it
    apply_selection(reg, "default", authorize_active=False)
    assert reg.get("org_fingerprint").enabled is False
    apply_selection(reg, "default", authorize_active=True)
    assert reg.get("org_fingerprint").enabled is True
