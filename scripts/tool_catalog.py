#!/usr/bin/env python3
"""Evidence-based tool catalog + execution matrix (READ-ONLY audit).

For every registry tool, emit its declared contract (registry/tools.yaml) crossed
with OBSERVED runtime behavior (tool_run rows + artifact files from real scans),
so each row carries evidence_source / evidence_snippet / confidence. No engine
behavior is changed — this only reads.

Usage (container): python3 scripts/tool_catalog.py [scan_id ...]
Multiple scan_ids are unioned for runtime evidence (use your richest scans).
"""
from __future__ import annotations

import sys
from collections import defaultdict

from sqlalchemy import select

from recontool.config import settings
from recontool.core.db import session_scope
from recontool.engine.models import ToolRun
from recontool.engine.registry import is_validation_tool
from recontool.engine.runner import load_engine_registry

PYBIN = {"nuclei": "nuclei", "naabu": "naabu", "nmap": "nmap", "sslyze": "sslyze",
         "gitleaks": "gitleaks", "whatweb": "whatweb", "gowitness": "gowitness"}


def _runtime(scan_ids):
    """Union per-tool runtime facts across scans: max entity_count, statuses."""
    produced = defaultdict(int)
    statuses = defaultdict(set)
    errs = {}
    with session_scope() as s:
        for sid in scan_ids:
            for tn, st, ec, err in s.execute(select(
                    ToolRun.tool_name, ToolRun.status, ToolRun.entity_count,
                    ToolRun.error_detail).where(ToolRun.scan_id == sid)).all():
                produced[tn] = max(produced[tn], int(ec or 0))
                statuses[tn].add(st)
                if err:
                    errs[tn] = err[:80]
    return produced, statuses, errs


def _observed_outputs(scan_ids, tool):
    """Typed output files produced for a tool across scans -> {type: max_lines}."""
    res = defaultdict(int)
    for sid in scan_ids:
        out = settings.artifact_dir / sid / "out"
        if not out.exists():
            continue
        for p in out.glob(f"{tool}.*.jsonl"):
            typ = p.name[len(tool) + 1:-6]
            try:
                res[typ] = max(res[typ], sum(1 for _ in p.open(errors="ignore")))
            except Exception:  # noqa: BLE001
                pass
    return dict(res)


def _stage(consumes):
    c = set(consumes or [])
    if not c or c == {"none"}:
        return "bootstrap/none"
    order = [("domain", "1-domain"), ("subdomain", "2-subdomain"),
             ("url", "4-url"), ("js_file", "5-js"), ("ip", "3-ip/cidr"),
             ("cidr", "3-ip/cidr"), ("asn", "3-asn"), ("org", "0-org"),
             ("repo", "6-repo"), ("bucket", "6-bucket"), ("cve", "7-validate"),
             ("host_port", "7-validate"), ("file", "5-file"), ("cert", "4-cert")]
    for key, lbl in order:
        if key in c:
            return lbl
    return f"other:{sorted(c)}"


def catalog(scan_ids):
    reg = load_engine_registry(tools="all", authorize_active=True)
    produced, statuses, errs = _runtime(scan_ids)
    rows = []
    import shutil
    for name, t in sorted(reg.all_tools().items(), key=lambda kv: kv[0].lower()):
        integ = t.integration or ""
        consumes = list(t.consumes or t.supported_input_types or [])
        decl_out = list(t.produces or t.output_types or [])
        obs = _observed_outputs(scan_ids, name)
        ran = name in statuses
        # status classification
        if not t.enabled:
            status = "non_executable" if getattr(t, "non_executable", False) else "disabled"
        elif ran:
            status = "RAN_produced" if produced.get(name, 0) > 0 or obs else "RAN_empty"
        elif t.is_inventory_derived:
            status = "inventory_stub(no-binary)"
        else:
            b = t.binary or PYBIN.get(name)
            if integ == "api" and t.requires_key and not t.key_optional and not settings.api_key(t.requires_key):
                status = "skip_missing_key"
            elif b and shutil.which(b) is None:
                status = "skip_missing_binary"
            else:
                status = "available_not_scheduled(chain-orphan)"
        kind = ("validation" if is_validation_tool(t)
                else "passive" if t.type == "passive" else "active")
        rows.append({
            "tool": name, "status": status, "kind": kind, "integ": integ,
            "consumes": ",".join(consumes) or "-", "declared_out": ",".join(decl_out) or "-",
            "observed_out": ",".join(f"{k}:{v}" for k, v in obs.items()) or ("ran:0" if status == "RAN_empty" else "-"),
            "stage": _stage(consumes), "default_on": t.default_on,
            "stdin": getattr(t, "stdin", False), "key": t.requires_key or "",
            "invocation": (t.invocation or t.endpoint or "")[:90],
            "parse_fmt": (t.parse or {}).get("format", "") if t.parse else "",
            "err": errs.get(name, ""),
        })
    return rows


def main():
    scan_ids = sys.argv[1:] or []
    rows = catalog(scan_ids)
    # summary
    from collections import Counter
    sc = Counter(r["status"] for r in rows)
    print(f"# TOOL CATALOG — {len(rows)} registry entries; runtime evidence from scans: {scan_ids}")
    print("## status summary")
    for k, v in sc.most_common():
        print(f"  {v:4}  {k}")
    print("\n## TSV (tool\tstatus\tkind\tinteg\tconsumes\tdeclared_out\tobserved_out\tstage\tdefault_on\tstdin\tkey\tparse\tinvocation\terr)")
    for r in rows:
        print("\t".join(str(r[c]) for c in (
            "tool", "status", "kind", "integ", "consumes", "declared_out",
            "observed_out", "stage", "default_on", "stdin", "key", "parse_fmt",
            "invocation", "err")))


if __name__ == "__main__":
    main()
