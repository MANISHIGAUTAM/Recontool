"""Handwritten nmap adapter — parses nmap -oX (XML) into one service per open
port with version info. The generic CLI adapter can't do this (no XML format,
and greppable output can't be split into N service records per host line).
"""
from __future__ import annotations

from recontool.adapters.active import NmapServiceScan, _parse_nmap_xml

_XML = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <address addr="93.184.216.34" addrtype="ipv4"/>
    <hostnames><hostname name="example.com" type="user"/></hostnames>
    <ports>
      <port protocol="tcp" portid="443">
        <state state="open"/>
        <service name="https" product="nginx" version="1.25.1"/>
      </port>
      <port protocol="tcp" portid="22">
        <state state="open"/>
        <service name="ssh" product="OpenSSH" version="9.2"/>
      </port>
      <port protocol="tcp" portid="8080">
        <state state="closed"/>
        <service name="http-proxy"/>
      </port>
    </ports>
  </host>
</nmaprun>"""


def test_parse_nmap_xml_open_ports_only_with_version():
    evs = _parse_nmap_xml(_XML, "fallback", "nmap")
    by_port = {e.data["port"]: e for e in evs}
    assert set(by_port) == {443, 22}                 # closed 8080 dropped
    assert all(e.entity == "service" for e in evs)
    assert by_port[443].data["host"] == "example.com"   # hostname preferred over addr
    assert by_port[443].data["service_name"] == "https"
    assert by_port[443].data["product"] == "nginx 1.25.1"
    assert by_port[22].data["product"] == "OpenSSH 9.2"


def test_parse_nmap_xml_malformed_is_safe():
    assert _parse_nmap_xml("not xml at all", "h", "nmap") == []
    assert _parse_nmap_xml("", "h", "nmap") == []


def test_nmap_adapter_contract_and_default_off():
    ad = NmapServiceScan()
    assert ad.name == "nmap" and ad.is_active is True
    assert ad.consumes == ("ip", "subdomain") and ad.produces == ("service",)
    assert ad.default_on is False                     # heavy -> opt-in


def test_nmap_bridges_into_registry_as_handwritten_not_default_on():
    from recontool.engine.runner import load_engine_registry
    from recontool.engine.execution import build_adapter_for
    reg = load_engine_registry(tools="all", authorize_active=True)
    spec = reg.all_tools()["nmap"]
    assert spec.integration == "python"               # handwritten won the collision
    assert spec.default_on is False
    assert build_adapter_for(spec).__name__ == "NmapServiceScan"
