"""Atomic checks for the generic, registry-driven adapter engine.

Unit: the pure parse engine (render_template, parse_records, emit_events) against
fixtures for every format + feature — this validates each declarative tool spec's
output mapping without network or subprocess.
Integration: the YAML specs load, build into Adapter subclasses with correct
contracts, and register into the pipeline phases.
"""
from __future__ import annotations

from recontool.adapters.generic import (
    _expandable_cidr,
    _input_values,
    build_adapter_class,
    emit_events,
    parse_records,
    render_template,
)


def _ev(events, entity):
    return [e for e in events if e.entity == entity]


# ── render_template ──────────────────────────────────────────────────────────
def test_render_template_dotted_and_extra():
    assert render_template("{a.b}", {"a": {"b": "x"}}) == "x"
    assert render_template("AS{n}", {}, {"n": "13335"}) == "AS13335"
    assert render_template("literal", {}) == "literal"           # no braces -> literal
    assert render_template("{missing}", {}) == ""                # unknown -> empty


# ── parse_records: formats ────────────────────────────────────────────────────
def test_parse_json_list_path():
    spec = {"format": "json", "list_path": "data.ipv4_prefixes"}
    data = {"data": {"ipv4_prefixes": [{"prefix": "1.2.3.0/24"}, {"prefix": "5.6.7.0/24"}]}}
    recs = parse_records(spec, None, json_obj=data)
    assert [r["prefix"] for r in recs] == ["1.2.3.0/24", "5.6.7.0/24"]


def test_parse_json_top_level_array_of_strings():
    spec = {"format": "json"}
    recs = parse_records(spec, None, json_obj=["a.example.com", "b.example.com"])
    assert recs == [{"_value": "a.example.com"}, {"_value": "b.example.com"}]


def test_parse_jsonl():
    raw = '{"as_number":"13335","as_range":["1.1.1.0/24"]}\nbad line\n{"as_number":"15169"}'
    recs = parse_records({"format": "jsonl"}, raw)
    assert len(recs) == 2 and recs[0]["as_number"] == "13335"


def test_parse_text_lines_and_regex():
    assert parse_records({"format": "text"}, "a.com\n\n# c\nb.com") == \
        [{"_value": "a.com"}, {"_value": "b.com"}]
    recs = parse_records({"format": "text", "line_regex": r"^(?P<host>[^,]+),(?P<ip>.+)$"},
                         "api.example.com,1.2.3.4")
    assert recs == [{"host": "api.example.com", "ip": "1.2.3.4"}]


# ── emit_events: the declarative mappings ─────────────────────────────────────
def test_emit_value_each_with_scope_filter():
    # certspotter-style: each issuance has a dns_names list
    spec = {"format": "json", "emit": [
        {"entity": "asset", "value_each": "dns_names", "type": "subdomain",
         "scope_filter": "subdomain"}]}
    recs = [{"dns_names": ["api.example.com", "*.example.com", "evil.attacker.com"]}]
    ev = emit_events(spec, recs, "certspotter", "example.com")
    vals = [e.data["value"] for e in _ev(ev, "asset")]
    assert "api.example.com" in vals
    assert "example.com" in vals               # wildcard stripped to apex
    assert "evil.attacker.com" not in vals     # out-of-scope dropped


def test_emit_drops_tool_banner_lines_and_out_of_scope_hosts():
    """Emit-layer shape+scope gate: a text-parsed tool's banner/usage lines must
    NOT become assets (paramspider regression), and a value typed `subdomain`
    that isn't under the seed must be dropped (out-of-scope host regression),
    even with NO explicit scope_filter on the rule."""
    # paramspider-style: stdout banner parsed as text -> emitted as url
    url_spec = {"format": "text", "emit": [
        {"entity": "asset", "value": "{_value}", "type": "url"}]}
    banner = parse_records(url_spec, "_    __\nwith <3 by @0xasm0d3us\nhttps://groww.in/?q=1")
    vals = [e.data["value"] for e in _ev(emit_events(url_spec, banner, "paramspider", "groww.in"), "asset")]
    assert vals == ["https://groww.in/?q=1"]     # banner art dropped, real url kept

    # subdomain emit with no scope_filter: out-of-scope host dropped, apex+real kept
    sub_spec = {"format": "text", "emit": [
        {"entity": "asset", "value": "{_value}", "type": "subdomain"}]}
    recs = parse_records(sub_spec, "app.groww.in\napps.apple.com\nbit.ly\ngroww.in")
    got = [e.data["value"] for e in _ev(emit_events(sub_spec, recs, "crawler", "groww.in"), "asset")]
    assert "app.groww.in" in got and "groww.in" in got
    assert "apps.apple.com" not in got and "bit.ly" not in got


def test_emit_bgpview_cidr():
    spec = {"format": "json", "list_path": "data.ipv4_prefixes",
            "emit": [{"entity": "asset", "value": "{prefix}", "type": "cidr"}]}
    recs = parse_records(spec, None, json_obj={"data": {"ipv4_prefixes": [{"prefix": "1.2.3.0/24"}]}})
    ev = emit_events(spec, recs, "bgpview", None)
    assert _ev(ev, "asset")[0].data == {"type": "cidr", "value": "1.2.3.0/24"}


def test_emit_cidr_size_scope_filter_drops_oversized_blocks():
    # ASN-level lookups (ripestat/bgpview) on a shared ASN like Cloudflare's
    # AS13335 return the provider's entire prefix list -- cidr_size keeps
    # only blocks small enough to plausibly be a dedicated allocation.
    spec = {"format": "json", "list_path": "data.prefixes", "emit": [
        {"entity": "asset", "value": "{prefix}", "type": "cidr", "scope_filter": "cidr_size"}]}
    recs = parse_records(spec, None, json_obj={"data": {"prefixes": [
        {"prefix": "104.22.42.0/24"},      # /24 -> kept
        {"prefix": "104.16.0.0/12"},       # CDN-wide supernet -> dropped
        {"prefix": "2400:cb00:768::/48"},  # IPv6 supernet -> dropped
    ]}})
    ev = emit_events(spec, recs, "ripestat", "groww.in")
    assert {e.data["value"] for e in _ev(ev, "asset")} == {"104.22.42.0/24"}


# ── _input_values: cidr fan-out guard ─────────────────────────────────────────
def test_expandable_cidr_size_guard():
    assert _expandable_cidr("1.2.3.0/24") is True
    assert _expandable_cidr("10.0.0.0/8") is False         # too large to expand per-IP
    assert _expandable_cidr("2400:cb00:768::/48") is False  # IPv6 supernet
    assert _expandable_cidr("not-a-cidr") is False


def test_input_values_filters_oversized_cidrs_for_mapcidr():
    class _Ctx:
        def seeds_of(self, atype):
            return {"cidr": ["1.2.3.0/24", "10.0.0.0/8", "2400:cb00:768::/48"]}.get(atype, [])

    assert _input_values(_Ctx(), ("cidr",), cap=50) == ["1.2.3.0/24"]


def test_emit_edge_service_endpoint_finding():
    spec = {"emit": [
        {"entity": "edge", "src": "{host}", "dst": "{ip}", "rel": "resolves_to"},
        {"entity": "service", "host": "{ip}", "port": "{port}"},
        {"entity": "endpoint", "url": "{url}"},
        {"entity": "finding", "kind": "cve", "title": "{name}", "severity": "high",
         "cve_id": "{cve}", "asset_value": "{host}"},
    ]}
    rec = {"host": "api.example.com", "ip": "1.2.3.4", "port": "443",
           "url": "https://api.example.com/x", "name": "thing", "cve": "CVE-2021-1"}
    ev = emit_events(spec, [rec], "t", None)
    assert _ev(ev, "edge")[0].data["rel"] == "resolves_to"
    assert _ev(ev, "service")[0].data["port"] == 443
    assert _ev(ev, "endpoint")[0].data["url"] == "https://api.example.com/x"
    f = _ev(ev, "finding")[0].data
    assert f["cve_id"] == "CVE-2021-1" and f["severity"] == "high"


def test_emit_asn_value():
    spec = {"format": "jsonl", "emit": [
        {"entity": "asset", "value": "{as_number}", "type": "asn"},
        {"entity": "asset", "value_each": "as_range", "type": "cidr"}]}
    recs = parse_records(spec, '{"as_number":"15133","as_range":["1.2.3.0/24","5.6.0.0/16"]}')
    ev = emit_events(spec, recs, "asnmap", None)
    assert _ev(ev, "asset")[0].data == {"type": "asn", "value": "15133"}
    assert {e.data["value"] for e in _ev(ev, "asset")[1:]} == {"1.2.3.0/24", "5.6.0.0/16"}


# ── integration: specs -> adapter classes -> registry ─────────────────────────
def test_generic_specs_load_and_build():
    from recontool.adapters.autoload import load_generic_specs
    specs = load_generic_specs()
    assert len(specs) >= 12
    names = {s["name"] for s in specs}
    for expected in ("certspotter", "bgpview", "asnmap", "assetfinder", "tlsx", "katana"):
        assert expected in names

    spec = next(s for s in specs if s["name"] == "bgpview")
    cls = build_adapter_class(spec)
    assert cls.name == "bgpview"
    assert cls.consumes == ("asn",) and "cidr" in cls.produces
    assert cls.is_active is False


def test_generic_adapters_register_into_phases():
    from recontool.adapters.registry import all_adapters, load_builtin
    load_builtin()
    ad = all_adapters()
    gen = {n for n, c in ad.items() if c.__name__.startswith("Generic_")}
    assert {"certspotter", "asnmap", "katana", "tlsx", "assetfinder"} <= gen
    # hand-written adapters are never overridden by generic specs
    assert ad["nuclei"].__name__ != "Generic_nuclei"
