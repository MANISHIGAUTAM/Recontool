"""Registry variant expansion — a multi-mode tool (gf {pattern}, unfurl {mode})
becomes one independently-routable, parseable tool per mode.

Without it the {pattern}/{mode} token renders to "" (the tool runs in no mode)
and a single 'gf'/'unfurl' entry can't carry the different output types each mode
produces (unfurl domains -> subdomain vs keys -> param).
"""
from __future__ import annotations

from recontool.engine.registry import ToolRegistry


def _expand(name, raw):
    return dict(ToolRegistry._expand_variants(name, raw))


def test_no_variants_passthrough():
    raw = {"binary": "x", "invocation": "x {value}"}
    assert _expand("x", raw) == {"x": raw}


def test_gf_pattern_expansion_bakes_invocation():
    raw = {"binary": "gf", "invocation": "gf {pattern}", "stdin": True,
           "variants": {"field": "pattern", "items": ["ssrf", "xss"]}}
    out = _expand("gf", raw)
    assert set(out) == {"gf-ssrf", "gf-xss"}
    assert out["gf-ssrf"]["invocation"] == "gf ssrf"
    assert out["gf-xss"]["invocation"] == "gf xss"
    assert "variants" not in out["gf-ssrf"]          # not carried into the leaf spec
    assert out["gf-ssrf"]["stdin"] is True           # base fields inherited


def test_unfurl_per_variant_output_override():
    raw = {"binary": "unfurl", "invocation": "unfurl -u {mode}",
           "variants": {"field": "mode", "items": [
               {"value": "domains", "output": "subdomain"},
               {"value": "keys", "output": "param"}]}}
    out = _expand("unfurl", raw)
    assert out["unfurl-domains"]["invocation"] == "unfurl -u domains"
    assert out["unfurl-domains"]["output"] == "subdomain"   # per-variant override
    assert out["unfurl-keys"]["output"] == "param"


def test_variants_register_into_real_registry():
    from recontool.engine.runner import load_engine_registry
    reg = load_engine_registry(tools="all", authorize_active=True)
    names = set(reg.all_tools())
    assert "gf" not in names and "unfurl" not in names     # expanded away
    assert {"gf-ssrf", "gf-xss", "unfurl-domains", "unfurl-keys"} <= names
