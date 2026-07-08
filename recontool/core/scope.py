"""Scope enforcement — the safety backbone.

Two ideas (docs/D6-opsec.md):
  1. A compiled matcher (domain-suffix set + CIDR list) decides in/out of scope fast.
  2. Deny rules OVERRIDE allow rules.
The worker re-checks scope before any ACTIVE call, independent of the gateway.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field


@dataclass
class Scope:
    allow_domains: set[str] = field(default_factory=set)   # apex/suffixes, e.g. 'acme.com'
    allow_cidrs: list[str] = field(default_factory=list)
    allow_asns: set[str] = field(default_factory=set)
    deny_domains: set[str] = field(default_factory=set)
    deny_cidrs: list[str] = field(default_factory=list)
    # If True, any subdomain of an allowed apex is in scope automatically.
    allow_subdomains: bool = True

    _allow_nets: list = field(default_factory=list, repr=False)
    _deny_nets: list = field(default_factory=list, repr=False)

    def __post_init__(self):
        self._allow_nets = [ipaddress.ip_network(c, strict=False) for c in self.allow_cidrs]
        self._deny_nets = [ipaddress.ip_network(c, strict=False) for c in self.deny_cidrs]

    # ---- constructors -----------------------------------------------------
    @classmethod
    def from_seed(cls, seed: str, seed_type: str) -> "Scope":
        """Build a sensible default scope from a single seed."""
        s = cls()
        if seed_type in ("domain", "subdomain"):
            apex = _apex(seed)
            s.allow_domains.add(apex)
        elif seed_type == "ip":
            s.allow_cidrs.append(f"{seed}/32")
        elif seed_type == "cidr":
            s.allow_cidrs.append(seed)
        elif seed_type == "asn":
            s.allow_asns.add(seed.upper())
        s.__post_init__()
        return s

    # ---- matching ---------------------------------------------------------
    def _domain_allowed(self, host: str) -> bool:
        host = host.lower().rstrip(".")
        for d in self.deny_domains:
            if host == d or host.endswith("." + d):
                return False
        for d in self.allow_domains:
            if host == d:
                return True
            if self.allow_subdomains and host.endswith("." + d):
                return True
        return False

    def _ip_allowed(self, ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if any(addr in n for n in self._deny_nets):
            return False
        return any(addr in n for n in self._allow_nets)

    def contains(self, asset_type: str, value: str) -> bool:
        """Is this asset in scope? Deny always wins."""
        if asset_type in ("domain", "subdomain", "url", "live_host"):
            host = _host_of(value)
            return self._domain_allowed(host)
        if asset_type == "ip":
            return self._ip_allowed(value)
        if asset_type == "asn":
            return value.upper() in self.allow_asns
        if asset_type == "cidr":
            try:
                net = ipaddress.ip_network(value, strict=False)
                return any(net.subnet_of(n) for n in self._allow_nets)
            except (ValueError, TypeError):
                return False
        # certs/emails/buckets: scoped via their associated host if any
        return True

    def to_json(self) -> dict:
        return {
            "allow_domains": sorted(self.allow_domains),
            "allow_cidrs": self.allow_cidrs,
            "allow_asns": sorted(self.allow_asns),
            "deny_domains": sorted(self.deny_domains),
            "deny_cidrs": self.deny_cidrs,
            "allow_subdomains": self.allow_subdomains,
        }

    @classmethod
    def from_json(cls, d: dict) -> "Scope":
        return cls(
            allow_domains=set(d.get("allow_domains", [])),
            allow_cidrs=list(d.get("allow_cidrs", [])),
            allow_asns=set(d.get("allow_asns", [])),
            deny_domains=set(d.get("deny_domains", [])),
            deny_cidrs=list(d.get("deny_cidrs", [])),
            allow_subdomains=d.get("allow_subdomains", True),
        )


def _host_of(value: str) -> str:
    if "://" in value:
        from urllib.parse import urlsplit

        return urlsplit(value).hostname or value
    return value


def _apex(host: str) -> str:
    """Naive apex extraction (last two labels). Good enough for default scope;
    real deployments should use the public-suffix list."""
    host = _host_of(host).lower().rstrip(".")
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    return ".".join(parts[-2:])


def apex_domain(host: str) -> str:
    """Public apex extractor (last two labels). Handles URLs/emails too."""
    return _apex(host)


def is_subdomain_of(host: str, domain: str) -> bool:
    """True iff `host` is `domain` itself or a real subdomain of it.

    Guards against two common false positives seen in live data:
      - sibling-suffix collisions: 'm.testexample.com' must NOT match 'example.com'
        (loose endswith() would wrongly accept it),
      - email addresses in cert subjects: 'name@example.com' is not a host.
    """
    if not host:
        return False
    host = host.lower().rstrip(".").lstrip("*.")
    if "@" in host or " " in host:
        return False
    domain = domain.lower().rstrip(".")
    return host == domain or host.endswith("." + domain)


def classify_seed(seed: str) -> str:
    """Detect the input type from a raw seed string."""
    s = seed.strip()
    if s.upper().startswith("AS") and s[2:].isdigit():
        return "asn"
    if "/" in s:
        try:
            ipaddress.ip_network(s, strict=False)
            return "cidr"
        except ValueError:
            pass
    try:
        ipaddress.ip_address(s)
        return "ip"
    except ValueError:
        pass
    if s.startswith("http://") or s.startswith("https://"):
        return "url"
    if "@" in s:
        return "email"
    return "domain"
