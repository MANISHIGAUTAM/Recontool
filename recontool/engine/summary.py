"""Final scan summary — the AI (or heuristic) wrap-up of a completed scan.

After the work queue drains, this gathers the canonical facts from the DB
(asset inventory, findings, recursion depth) AND a per-tool execution breakdown
(what ran and produced, what ran empty, what failed and why, what skipped) so
the operator gets one answer to "what happened and what matters". A model writes
the narrative when AI is enabled; otherwise a deterministic template does — the
facts are identical either way, only the prose differs.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import func, select

from recontool.core.db import session_scope
from recontool.core.models import Asset, Finding, Scan, Service
from recontool.engine.models import ToolRun, WorkItem

logger = logging.getLogger(__name__)

_SEV_ORDER = ("critical", "high", "medium", "low", "info")


def build_scan_facts(scan_id: str) -> dict:
    """Collect the structured facts the summary is built from (pure DB read)."""
    with session_scope() as s:
        scan = s.get(Scan, scan_id)
        assets_by_type = dict(s.execute(
            select(Asset.type, func.count(Asset.id))
            .where(Asset.scan_id == scan_id).group_by(Asset.type)).all())
        live = s.execute(select(func.count(Asset.id)).where(
            Asset.scan_id == scan_id, Asset.is_live.is_(True))).scalar() or 0
        services = s.execute(select(func.count(Service.id)).join(
            Asset, Service.asset_id == Asset.id).where(
            Asset.scan_id == scan_id)).scalar() or 0
        findings_by_sev = dict(s.execute(
            select(Finding.severity, func.count(Finding.id))
            .where(Finding.scan_id == scan_id).group_by(Finding.severity)).all())
        top_findings = [
            {"severity": f.severity, "title": f.title, "asset": f.asset_value}
            for f in s.execute(
                select(Finding).where(Finding.scan_id == scan_id)).scalars().all()
        ]
        max_depth = s.execute(select(func.max(WorkItem.depth))
                              .where(WorkItem.scan_id == scan_id)).scalar() or 0

        # Per-tool execution outcome (latest status wins per tool).
        wi_status = dict(s.execute(
            select(WorkItem.status, func.count(WorkItem.id))
            .where(WorkItem.scan_id == scan_id).group_by(WorkItem.status)).all())
        runs = s.execute(
            select(ToolRun.tool_name, ToolRun.status, ToolRun.entity_count,
                   ToolRun.error_detail)
            .where(ToolRun.scan_id == scan_id)).all()

    produced: dict[str, int] = {}
    empty: set[str] = set()
    failed: dict[str, str] = {}
    for tool, status, n, err in runs:
        if status == "failed":
            failed[tool] = (err or "error")[:160]
        elif (n or 0) > 0:
            produced[tool] = produced.get(tool, 0) + int(n)
        else:
            empty.add(tool)
    # a tool that produced in ANY run isn't "empty"
    empty -= set(produced)

    top_findings.sort(key=lambda f: _SEV_ORDER.index(f["severity"])
                      if f["severity"] in _SEV_ORDER else 99)
    return {
        "seed": getattr(scan, "seed", None),
        "seed_type": getattr(scan, "seed_type", None),
        "active_authorized": bool(getattr(scan, "active_authorized", False)),
        "assets_by_type": assets_by_type,
        "assets_total": sum(assets_by_type.values()),
        "live_assets": int(live),
        "services": int(services),
        "findings_by_severity": findings_by_sev,
        "findings_total": sum(findings_by_sev.values()),
        "top_findings": top_findings[:15],
        "max_depth": int(max_depth),
        "work_items": wi_status,
        "tools": {
            "produced": dict(sorted(produced.items(), key=lambda kv: -kv[1])),
            "ran_empty": sorted(empty),
            "failed": failed,
        },
    }


def _heuristic_summary(f: dict) -> str:
    """Deterministic markdown narrative — the floor used when AI is off."""
    abt = ", ".join(f"{c} {t}" for t, c in sorted(
        f["assets_by_type"].items(), key=lambda kv: -kv[1])) or "none"
    sev = f["findings_by_severity"]
    sev_str = ", ".join(f"{sev[k]} {k}" for k in _SEV_ORDER if sev.get(k)) or "no findings"
    tools = f["tools"]
    top_prod = list(tools["produced"].items())[:8]
    lines = [
        f"# Scan summary — {f['seed']} ({f['seed_type']}, "
        f"{'active' if f['active_authorized'] else 'passive'})",
        "",
        f"**Attack surface:** {f['assets_total']} assets ({abt}); "
        f"{f['live_assets']} confirmed live, {f['services']} services. "
        f"Recursion reached depth {f['max_depth']}.",
        "",
        f"**Findings:** {f['findings_total']} ({sev_str}).",
    ]
    if f["top_findings"]:
        lines.append("")
        lines.append("**Notable findings:**")
        for ff in f["top_findings"][:8]:
            lines.append(f"- `{ff['severity']}` {ff['title']} "
                         f"({ff['asset'] or 'n/a'})")
    lines += [
        "",
        "**Tool execution:**",
        f"- {len(tools['produced'])} tools produced data"
        + (": " + ", ".join(f"{t} ({n})" for t, n in top_prod) if top_prod else ""),
        f"- {len(tools['ran_empty'])} ran but found nothing",
        f"- {len(tools['failed'])} failed"
        + (": " + ", ".join(sorted(tools["failed"])[:8]) if tools["failed"] else ""),
    ]
    wi = f["work_items"]
    if wi:
        lines.append("- work items: "
                     + ", ".join(f"{n} {st}" for st, n in sorted(wi.items())))
    return "\n".join(lines)


async def generate_summary(scan_id: str, router=None) -> tuple[str, dict]:
    """Return (markdown_summary, facts). Uses the model when enabled, else the
    deterministic heuristic. Never raises — a summary failure must not fail a
    scan that already succeeded."""
    try:
        facts = build_scan_facts(scan_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("summary: fact-gathering failed: %s", exc)
        return ("# Scan summary\n\n(summary unavailable — see scan_bundle.json)", {})

    heuristic = _heuristic_summary(facts)
    if router is not None and getattr(router, "enabled", False):
        try:
            prose = await router.chat(
                system=("You are a senior offensive-security analyst. Given the "
                        "JSON facts of a completed recon scan, write a concise "
                        "(<200 word) markdown briefing: the attack surface, the "
                        "most security-relevant findings/assets, and the single "
                        "most valuable next action. Be specific; do not invent "
                        "data not present in the facts."),
                user=json.dumps(facts, default=str)[:6000],
                tier="heavy", max_tokens=400)
            if prose:
                return (prose.strip() + "\n\n---\n" + heuristic, facts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("summary: model call failed, using heuristic: %s", exc)
    return (heuristic, facts)
