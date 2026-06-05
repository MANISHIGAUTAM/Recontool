"""Atomic check C3 (Parse) for Category 1 adapters.

Each test feeds a representative fixture payload to the adapter's PURE ``parse()``
method and asserts the normalized events are correct. No network, no DB — fast and
deterministic. This is what proves an adapter understands its tool's output.
"""
from __future__ import annotations

from recontool.adapters.internet_search import (
    Censys,
    FullHunt,
    GreyNoise,
    InternetDB,
    LeakIX,
    Netlas,
    Shodan,
    Uncover,
    UrlScan,
)


def _by_entity(events, entity):
    return [e for e in events if e.entity == entity]


def _values(events, entity, atype=None):
    out = []
    for e in _by_entity(events, entity):
        if atype is None or e.data.get("type") == atype:
            out.append(e.data.get("value") or e.data.get("host") or e.data.get("url"))
    return out


def test_shodan_parse():
    data = {
        "matches": [
            {
                "ip_str": "93.184.216.34", "port": 443, "product": "nginx",
                "version": "1.18.0", "data": "HTTP/1.1 200 OK",
                "hostnames": ["www.example.com", "cdn.example.com"],
                "vulns": ["CVE-2021-23017"],
            }
        ]
    }
    ev = Shodan.parse(data, "example.com")
    assert "93.184.216.34" in _values(ev, "asset", "ip")
    assert "www.example.com" in _values(ev, "asset", "subdomain")
    services = _by_entity(ev, "service")
    assert services and services[0].data["port"] == 443
    assert services[0].data["product"] == "nginx"
    findings = _by_entity(ev, "finding")
    assert findings and findings[0].data["cve_id"] == "CVE-2021-23017"
    # CONTRACT: shodan must declare it produces ip/service
    assert "ip" in Shodan.produces and "service" in Shodan.produces


def test_internetdb_parse():
    data = {"ip": "1.2.3.4", "ports": [22, 80, 443],
            "hostnames": ["host.example.com"], "vulns": ["CVE-2020-0001"]}
    ev = InternetDB.parse(data)
    ports = sorted(s.data["port"] for s in _by_entity(ev, "service"))
    assert ports == [22, 80, 443]
    assert "host.example.com" in _values(ev, "asset", "subdomain")
    assert _by_entity(ev, "finding")[0].data["cve_id"] == "CVE-2020-0001"
    # resolves_to edge present
    assert any(e.data["rel"] == "resolves_to" for e in _by_entity(ev, "edge"))


def test_censys_parse():
    data = {"result": {"hits": [
        {"ip": "10.0.0.5",
         "services": [{"port": 443, "service_name": "HTTP"}, {"port": 22, "service_name": "SSH"}],
         "dns": {"names": ["api.example.com", "other.org"]}},
    ]}}
    ev = Censys.parse(data, "example.com")
    assert "10.0.0.5" in _values(ev, "asset", "ip")
    subs = _values(ev, "asset", "subdomain")
    assert "api.example.com" in subs
    assert "other.org" not in subs           # out-of-domain name filtered
    assert {s.data["port"] for s in _by_entity(ev, "service")} == {443, 22}


def test_netlas_parse():
    data = {"items": [
        {"data": {"domain": "shop.example.com"}},
        {"data": {"domain": "mail.example.com"}},
        {"data": {"domain": "evil.attacker.com"}},
    ]}
    ev = Netlas.parse(data, "example.com")
    subs = _values(ev, "asset", "subdomain")
    assert "shop.example.com" in subs and "mail.example.com" in subs
    assert "evil.attacker.com" not in subs


def test_urlscan_parse():
    data = {"results": [
        {"page": {"url": "https://www.example.com/login", "ip": "93.184.216.34",
                  "domain": "www.example.com"}},
        {"task": {"url": "https://api.example.com/v1"}, "page": {"domain": "api.example.com"}},
        # off-target result (page merely references example.com) -> must be dropped
        {"page": {"url": "https://phishing.evil.com/", "domain": "phishing.evil.com"}},
    ]}
    ev = UrlScan.parse(data, "example.com")
    urls = _values(ev, "endpoint")
    assert "https://www.example.com/login" in urls
    assert "93.184.216.34" in _values(ev, "asset", "ip")
    subs = _values(ev, "asset", "subdomain")
    assert "www.example.com" in subs
    assert "phishing.evil.com" not in subs        # off-target dropped
    assert not any("evil.com" in (u or "") for u in urls)


def test_uncover_parse_jsonl():
    text = (
        '{"ip":"1.1.1.1","port":443,"host":"a.example.com"}\n'
        '{"ip":"1.1.1.2","port":80,"host":"1.1.1.2"}\n'
        'garbage-not-json\n'
    )
    ev = Uncover.parse(text, "example.com")
    assert "1.1.1.1" in _values(ev, "asset", "ip")
    assert "a.example.com" in _values(ev, "asset", "subdomain")
    # malformed line ignored, valid lines parsed
    assert {s.data["port"] for s in _by_entity(ev, "service")} == {443, 80}


def test_leakix_parse():
    data = {
        "Services": [{"ip": "5.5.5.5", "port": 9200, "protocol": "elasticsearch"}],
        "Leaks": [{"host": "5.5.5.5", "summary": "Open Elasticsearch", "severity": "high"}],
    }
    ev = LeakIX.parse(data, "example.com")
    assert "5.5.5.5" in _values(ev, "asset", "ip")
    f = _by_entity(ev, "finding")
    assert f and f[0].data["severity"] == "high"


def test_fullhunt_parse():
    assert "dev.example.com" in _values(
        FullHunt.parse({"hosts": ["dev.example.com", "x.other.com"]}, "example.com"),
        "asset", "subdomain",
    )


def test_greynoise_tags_only():
    ev = GreyNoise.parse({"noise": True, "classification": "malicious"}, "8.8.8.8")
    assert len(ev) == 1
    a = ev[0]
    assert a.entity == "asset" and a.data["type"] == "ip"
    assert "mass_scanner" in a.data["tags"]
    # GreyNoise is enrichment-only: produces tags, not new asset types
    assert GreyNoise.produces == ("tag",)
    # benign IP with no signal -> no events
    assert GreyNoise.parse({}, "1.2.3.4") == []
