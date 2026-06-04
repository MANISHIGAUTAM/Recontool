"""Deterministic dedupe keys + idempotent upserts.

The heart of normalization: re-discovery of the same real-world thing produces
the SAME key, so we UPDATE (strengthen confidence, refresh last_seen) instead of
INSERTing a duplicate. See docs/D3-data-schema.md §3-4.
"""
from __future__ import annotations

import hashlib
import ipaddress
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


def _sha(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def canonical_value(asset_type: str, value: str) -> str:
    """Normalize a value so equivalent representations collapse together."""
    v = value.strip()
    if asset_type in ("domain", "subdomain"):
        return v.lower().rstrip(".")
    if asset_type == "ip":
        try:
            return str(ipaddress.ip_address(v))
        except ValueError:
            return v
    if asset_type == "cidr":
        try:
            return str(ipaddress.ip_network(v, strict=False))
        except ValueError:
            return v
    if asset_type == "asn":
        n = v.upper().replace("AS", "").strip()
        return f"AS{n}"
    if asset_type == "url":
        return _canonical_url(v)
    if asset_type == "email":
        return v.lower()
    return v


def _canonical_url(url: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme.lower() or "http"
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    # sort query params, drop fragment
    query = urlencode(sorted(parse_qsl(parts.query)))
    return urlunsplit((scheme, netloc, path, query, ""))


def dedupe_key(asset_type: str, value: str) -> str:
    return _sha(f"{asset_type}:{canonical_value(asset_type, value)}")


def endpoint_key(url: str) -> str:
    return _sha(f"endpoint:{_canonical_url(url)}")


def finding_key(asset_value: str, detector: str, signature: str) -> str:
    return _sha(f"finding:{asset_value}:{detector}:{signature}")
