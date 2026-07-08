"""Batch-12: bucket-cloud family — gcpbucketbrute (source-verified output)."""
from __future__ import annotations

import yaml

from recontool.adapters.generic import emit_events, parse_records
from recontool.config import REPO_ROOT
from recontool.engine.runner import load_engine_registry

_SPECS = {t["name"]: t for t in yaml.safe_load(
    (REPO_ROOT / "config" / "tools_generic.d" / "bucket-cloud.yaml").read_text())["tools"]}

# Mirrors GCPBucketBrute check_permissions() stdout (leading spaces are stripped by the parser).
_SAMPLE = """UNAUTHENTICATED ACCESS ALLOWED: acme-public-assets
    - UNAUTHENTICATED LISTABLE (storage.objects.list)
EXISTS: acme-prod-backups
AUTHENTICATED ACCESS ALLOWED: acme-internal"""


def test_gcpbucketbrute_emits_buckets_only():
    spec = _SPECS["gcpbucketbrute"]
    events = emit_events(spec["parse"], parse_records(spec["parse"], _SAMPLE), "gcpbucketbrute", "acme")
    buckets = {e.data["value"] for e in events if e.entity == "asset" and e.data.get("type") == "bucket"}
    assert buckets == {"acme-public-assets", "acme-prod-backups", "acme-internal"}, buckets


def test_gcpbucketbrute_off_by_default_and_narrow():
    reg = load_engine_registry(tools="all", authorize_active=True)
    s = reg.get("gcpbucketbrute")
    assert s is not None
    assert getattr(s, "default_on", False) is False
    consumes = set(s.supported_input_types or []) | set(s.consumes or [])
    assert consumes == {"org"}
