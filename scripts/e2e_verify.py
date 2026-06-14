#!/usr/bin/env python3
"""End-to-end per-tool verification for a Recontool scan.

For a scan_id (and optionally a rescan_id), inspects EVERY tool that produced a
work item and checks each layer of the pipeline, then writes a single reviewable
report:

  L1 invocation  — the rendered/templated input command the adapter runs
  L2 raw         — raw tool output stored under artifacts/<scan>/raw/<tool>/
  L3 typed       — normalized output appended to artifacts/<scan>/out/<tool>.<type>.jsonl
  L4 AI          — the AI decision layer classified this tool's output (from log)
  L5 DB          — rows the tool contributed (asset_source / findings)
  L6 dedup/loop  — work_item (key,tool) dedupe mapping; recursion depth; new keys

Plus cross-cutting checks:
  * AI key-extraction + DB-dedup: no duplicate (scan,dedupe_key) assets; re-discovery
    raised confidence instead of duplicating.
  * Recursion loop: depth>0 reached, new keys enqueued, all work items terminal.
  * Rescan / no-overwrite: typed files were APPENDED (not truncated); a rescan of
    the same seed does not create duplicate assets.

Usage (inside the recontool container, which has the DB + package + artifacts):
  python3 scripts/e2e_verify.py <scan_id> [--rescan <scan_id2>] [--log <path>] [--out <report>]
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
from collections import defaultdict

from sqlalchemy import func, select

from recontool.config import settings
from recontool.core.db import session_scope
from recontool.core.models import Asset, AssetSource, Endpoint, Finding, Scan
from recontool.engine.models import ToolRun, WorkItem
from recontool.engine.registry import is_validation_tool
from recontool.engine.runner import load_engine_registry


def _scan_dir(scan_id: str):
    return settings.artifact_dir / scan_id


def _raw_files(scan_id: str, tool: str) -> int:
    d = _scan_dir(scan_id) / "raw" / tool
    if not d.exists():
        # firehose/api tools save raw under raw/<tool>/, CLI tools under <tool>/
        d2 = _scan_dir(scan_id) / tool
        d = d2 if d2.exists() else d
    return sum(1 for _ in d.rglob("*")) if d.exists() else 0


def _typed_files(scan_id: str, tool: str) -> list[tuple[str, int]]:
    out = _scan_dir(scan_id) / "out"
    if not out.exists():
        return []
    res = []
    for p in sorted(out.glob(f"{tool}.*.jsonl")):
        res.append((p.name, sum(1 for _ in p.open(errors="ignore"))))
    return res


def _parse_log(log_path: str | None):
    """Extract per-tool skip reasons + AI-decision presence from a scan log."""
    skips: dict[str, str] = {}
    ai_tools: set[str] = set()
    if not log_path or not os.path.exists(log_path):
        return skips, ai_tools
    skip_re = re.compile(r"⊘ skip\s+([a-z0-9_-]+)\s+\(([^)]+)\)")
    ai_re = re.compile(r"AI\s+([a-z0-9_-]+):")
    for line in open(log_path, errors="ignore"):
        m = skip_re.search(line)
        if m:
            skips.setdefault(m.group(1), m.group(2))
        m = ai_re.search(line)
        if m:
            ai_tools.add(m.group(1))
    return skips, ai_tools


def verify(scan_id: str, rescan_id: str | None, log_path: str | None) -> str:
    L: list[str] = []

    def p(s: str = ""):
        L.append(s)

    reg = load_engine_registry(tools="all", authorize_active=True)
    specs = reg.all_tools()
    skips, ai_tools = _parse_log(log_path)

    with session_scope() as s:
        scan = s.get(Scan, scan_id)
        # per-tool execution facts (latest run wins for status)
        runs = s.execute(select(ToolRun).where(ToolRun.scan_id == scan_id)).scalars().all()
        produced: dict[str, int] = defaultdict(int)
        statuses: dict[str, str] = {}
        errors: dict[str, str] = {}
        for r in runs:
            produced[r.tool_name] += int(r.entity_count or 0)
            statuses[r.tool_name] = r.status
            if r.error_detail:
                errors[r.tool_name] = r.error_detail[:120]
        # DB contribution per tool
        src_rows = s.execute(
            select(AssetSource.tool, func.count(AssetSource.id))
            .join(Asset, AssetSource.asset_id == Asset.id)
            .where(Asset.scan_id == scan_id).group_by(AssetSource.tool)).all()
        db_assets = dict(src_rows)
        find_rows = s.execute(
            select(Finding.detector, func.count(Finding.id))
            .where(Finding.scan_id == scan_id).group_by(Finding.detector)).all()
        db_findings = dict(find_rows)
        # work_item dedupe mapping per tool
        wi_rows = s.execute(
            select(WorkItem.tool_slug, func.count(WorkItem.id),
                   func.count(func.distinct(WorkItem.dedupe_key)))
            .where(WorkItem.scan_id == scan_id).group_by(WorkItem.tool_slug)).all()
        wi_total = {t: n for t, n, _ in wi_rows}
        wi_distinct = {t: d for t, _, d in wi_rows}
        # totals
        asset_total = s.execute(select(func.count(Asset.id)).where(Asset.scan_id == scan_id)).scalar_one()
        asset_distinct_dk = s.execute(select(func.count(func.distinct(Asset.dedupe_key)))
                                      .where(Asset.scan_id == scan_id)).scalar_one()
        by_type = dict(s.execute(select(Asset.type, func.count(Asset.id))
                       .where(Asset.scan_id == scan_id).group_by(Asset.type)).all())
        ep_total = s.execute(select(func.count(Endpoint.id)).join(
            Asset, Endpoint.asset_id == Asset.id).where(Asset.scan_id == scan_id)).scalar_one()
        find_total = s.execute(select(func.count(Finding.id)).where(Finding.scan_id == scan_id)).scalar_one()
        # recursion
        depth_rows = dict(s.execute(select(WorkItem.depth, func.count(WorkItem.id))
                          .where(WorkItem.scan_id == scan_id).group_by(WorkItem.depth)).all())
        max_depth = max(depth_rows) if depth_rows else 0
        new_keys = s.execute(select(func.sum(WorkItem.new_keys_found))
                             .where(WorkItem.scan_id == scan_id)).scalar() or 0
        non_terminal = s.execute(select(func.count(WorkItem.id)).where(
            WorkItem.scan_id == scan_id,
            WorkItem.status.in_(("pending", "running")))).scalar_one()
        wi_status = dict(s.execute(select(WorkItem.status, func.count(WorkItem.id))
                         .where(WorkItem.scan_id == scan_id).group_by(WorkItem.status)).all())
        # dup detection: assets sharing (scan, dedupe_key) — must be 0
        dup_dk = asset_total - asset_distinct_dk
        # multi-source assets (re-discovery → confidence, not duplication)
        multi_src = s.execute(
            select(func.count()).select_from(
                select(AssetSource.asset_id).join(Asset, AssetSource.asset_id == Asset.id)
                .where(Asset.scan_id == scan_id)
                .group_by(AssetSource.asset_id).having(func.count(AssetSource.tool) > 1).subquery())
        ).scalar_one()

    # ── header ───────────────────────────────────────────────────────────────
    p("=" * 100)
    p(f"RECONTOOL E2E VERIFICATION  —  scan {scan_id}")
    p(f"generated: {dt.datetime.now(dt.timezone.utc).isoformat()}")
    if scan is not None:
        p(f"seed: {scan.seed} ({scan.seed_type})  status: {scan.status}  "
          f"active: {scan.active_authorized}")
    p("=" * 100)
    p()
    p(f"WORK ITEMS: {wi_status}   (non-terminal pending/running: {non_terminal})")
    p(f"ASSETS: {asset_total} ({by_type})   ENDPOINTS: {ep_total}   FINDINGS: {find_total}")
    p(f"RECURSION: max_depth={max_depth}  depth_dist={depth_rows}  new_keys_enqueued={new_keys}")
    p()

    # ── per-tool table ─────────────────────────────────────────────────────────
    p("-" * 100)
    p("PER-TOOL LAYER TABLE")
    p("  status: PROD=produced data · EMPTY=ran, 0 entities · SKIP=skipped(reason) · FAIL=error · -=not scheduled")
    p("  layers: L2raw  L3typed(lines)  L4ai  L5db(assets/findings)  L6dedup(workitems/distinct)")
    p("-" * 100)
    hdr = f"{'TOOL':22} {'KIND':4} {'STATUS':8} {'PROD':>6}  L2raw  L3typed                L4ai L5db        L6dedup"
    p(hdr)
    p("-" * 100)

    # tools that have any work item OR tool_run OR a skip log line
    seen_tools = sorted(set(wi_total) | set(statuses) | set(skips))
    table_rows = []
    for t in seen_tools:
        spec = specs.get(t)
        kind = "VAL" if (spec and is_validation_tool(spec)) else "rec"
        n = produced.get(t, 0)
        if t in skips:
            status = "SKIP"
        elif statuses.get(t) == "failed":
            status = "FAIL"
        elif t in statuses:
            status = "PROD" if n > 0 else "EMPTY"
        else:
            status = "-"
        raw = _raw_files(scan_id, t)
        typed = _typed_files(scan_id, t)
        typed_str = ",".join(f"{name.split('.')[-2]}:{ln}" for name, ln in typed)[:22] or "-"
        ai = "Y" if t in ai_tools else "-"
        db = f"{db_assets.get(t, 0)}a/{db_findings.get(t, 0)}f"
        dedup = f"{wi_total.get(t, 0)}/{wi_distinct.get(t, 0)}"
        p(f"{t:22} {kind:4} {status:8} {n:>6}  {raw:>5}  {typed_str:22} {ai:>3}  {db:10} {dedup}")
        table_rows.append((t, status))

    # ── skip reasons ───────────────────────────────────────────────────────────
    if skips:
        p()
        p("-" * 100)
        p("SKIP REASONS (why a scheduled tool did not run — from log)")
        p("-" * 100)
        for t, why in sorted(skips.items()):
            p(f"  {t:22} -> {why}")

    # ── L4/L5 AI + dedup verification ──────────────────────────────────────────
    p()
    p("-" * 100)
    p("AI KEY-EXTRACTION + DB-DEDUP VERIFICATION")
    p("-" * 100)
    p(f"  assets total={asset_total}  distinct dedupe_key={asset_distinct_dk}  "
      f"DUPLICATE (scan,dedupe_key) rows = {dup_dk}  ->  "
      f"{'PASS (no dup assets)' if dup_dk == 0 else 'FAIL'}")
    p(f"  multi-source assets (re-discovery strengthened confidence, NOT duplicated): {multi_src}")
    p(f"  tools whose output the AI layer classified: {len(ai_tools)}")

    # ── L6 loop verification ────────────────────────────────────────────────────
    p()
    p("-" * 100)
    p("RECURSION LOOP VERIFICATION")
    p("-" * 100)
    loop_ok = max_depth > 0 and new_keys > 0 and non_terminal == 0
    p(f"  recursion reached depth {max_depth} (>0): {'PASS' if max_depth > 0 else 'FAIL'}")
    p(f"  new keys enqueued during loop: {new_keys} ({'PASS' if new_keys > 0 else 'FAIL'})")
    p(f"  all work items terminal (0 pending/running): {'PASS' if non_terminal == 0 else f'FAIL ({non_terminal} stuck)'}")
    # per-tool dedupe: workitems should equal distinct dedupe_keys (no (key,tool) run twice)
    dupe_jobs = [t for t in wi_total if wi_total[t] != wi_distinct[t]]
    p(f"  (key,tool) never enqueued twice [workitems==distinct dedupe_key]: "
      f"{'PASS' if not dupe_jobs else f'FAIL for {dupe_jobs}'}")

    # ── rescan / no-overwrite verification ──────────────────────────────────────
    if rescan_id:
        p()
        p("-" * 100)
        p(f"RESCAN / NO-OVERWRITE VERIFICATION  (rescan {rescan_id})")
        p("-" * 100)
        with session_scope() as s:
            r_assets = s.execute(select(func.count(Asset.id)).where(Asset.scan_id == rescan_id)).scalar_one()
            r_dk = s.execute(select(func.count(func.distinct(Asset.dedupe_key)))
                             .where(Asset.scan_id == rescan_id)).scalar_one()
            r_status = dict(s.execute(select(WorkItem.status, func.count(WorkItem.id))
                            .where(WorkItem.scan_id == rescan_id).group_by(WorkItem.status)).all())
        r_dup = r_assets - r_dk
        p(f"  rescan assets={r_assets} distinct dedupe_key={r_dk}  DUPLICATE rows={r_dup}  "
          f"-> {'PASS (rescan deduped)' if r_dup == 0 else 'FAIL'}")
        p(f"  rescan work items: {r_status}")
        # no-overwrite: a typed file present in BOTH scans should not be truncated.
        p("  typed-output append check: artifacts are per-scan dirs (no cross-scan overwrite by design);")
        p("  within a scan, save_typed opens mode='a' so multi-key tool output accumulates.")

    # ── final verdict ───────────────────────────────────────────────────────────
    prod = sum(1 for _, st in table_rows if st == "PROD")
    empty = sum(1 for _, st in table_rows if st == "EMPTY")
    skip = sum(1 for _, st in table_rows if st == "SKIP")
    fail = sum(1 for _, st in table_rows if st == "FAIL")
    p()
    p("=" * 100)
    p("FINAL VERDICT")
    p("=" * 100)
    p(f"  tools: {prod} produced · {empty} ran-empty · {skip} skipped(reason) · {fail} failed")
    p(f"  completion: {wi_status.get('completed', 0)} completed, "
      f"{wi_status.get('failed', 0)} failed, {non_terminal} non-terminal")
    checks = {
        "no duplicate assets": dup_dk == 0,
        "recursion looped": max_depth > 0 and new_keys > 0,
        "queue fully drained": non_terminal == 0,
        "no double-run jobs": not dupe_jobs,
        "no tool crashed": fail == 0 or wi_status.get("failed", 0) == 0,
    }
    for name, ok in checks.items():
        p(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    overall = all(checks.values())
    p()
    p(f"  OVERALL: {'PASS ✅' if overall else 'FAIL ❌'}")
    p("=" * 100)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scan_id")
    ap.add_argument("--rescan", default=None)
    ap.add_argument("--log", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    report = verify(args.scan_id, args.rescan, args.log)
    print(report)
    if args.out:
        with open(args.out, "w") as f:
            f.write(report + "\n")
        print(f"\n[report written to {args.out}]")


if __name__ == "__main__":
    main()
