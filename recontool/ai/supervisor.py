"""AI agentic supervisor — runtime decisioning over the pipeline.

Consulted by the orchestrator at phase boundaries to:
  - plan_phase:    keep/drop adapters before running (token-cheap, LIGHT model),
  - review_phase:  analyse output and produce a strategic note (LIGHT model),
  - should_recurse: decide whether new surface warrants another passive pass,
  - final_report:  synthesise an exec narrative (HEAVY model, once).

EVERY method has a deterministic heuristic fallback, so the platform behaves
sensibly with no API key and spends zero tokens. The AI only *augments*
decisions; it never sources assets/findings (ADR-015).
"""
from __future__ import annotations

from sqlalchemy import func, select

from recontool.ai.router import ModelRouter
from recontool.core.db import session_scope
from recontool.core.models import Asset, Endpoint, Finding


class Supervisor:
    def __init__(self, router: ModelRouter | None = None):
        self.router = router or ModelRouter()
        self.notes: list[str] = []

    # ── planning: which adapters to run this phase ──────────────────────────
    async def plan_phase(self, phase: str, adapter_names: list[str], scan_id: str):
        """Return the subset of adapters to keep, or None to keep all.
        Heuristic keeps all (availability already filtered). AI may prune when
        a phase is redundant given what we already have."""
        if not self.router.enabled:
            return None
        snap = self._snapshot(scan_id)
        decision = await self.router.decide_json(
            system=(
                "You are a recon strategist. Given current asset counts and the "
                "candidate tools for the next phase, return JSON "
                '{"keep":[tool,...],"reason":"..."}. Keep tools that add NEW signal; '
                "drop clearly redundant ones. Prefer keeping if unsure."
            ),
            payload={"phase": phase, "tools": adapter_names, "have": snap},
            tier="light",
            max_tokens=120,
        )
        if not decision or "keep" not in decision:
            return None
        keep = [t for t in decision["keep"] if t in adapter_names]
        return keep or None

    # ── review: analyse a phase's output ────────────────────────────────────
    async def review_phase(self, phase: str, counts: dict, scan_id: str) -> str:
        heuristic = self._heuristic_note(phase, counts, scan_id)
        if not self.router.enabled:
            self.notes.append(heuristic)
            return heuristic
        snap = self._snapshot(scan_id)
        text = await self.router.chat(
            system=(
                "You are a recon analyst. In ONE concise sentence, state the most "
                "important takeaway and any high-value target to prioritise next. "
                "Be specific, no fluff."
            ),
            user=f"phase={phase} new={counts} totals={snap}",
            tier="light",
            max_tokens=80,
        )
        note = (text or heuristic).strip()
        self.notes.append(note)
        return note

    # ── recursion decision ──────────────────────────────────────────────────
    async def should_recurse(self, scan_id: str, result) -> bool:
        snap = self._snapshot(scan_id)
        # Heuristic: recurse only if the surface is meaningfully large and a
        # previous pass keeps finding new subdomains.
        grew = snap.get("subdomain", 0) >= 25
        if not self.router.enabled:
            return grew
        decision = await self.router.decide_json(
            system=(
                "Decide if another PASSIVE discovery pass is worthwhile. "
                'Return {"recurse":true|false,"reason":"..."}. Recurse only if new '
                "apex/related domains likely remain undiscovered."
            ),
            payload={"have": snap},
            tier="light",
            max_tokens=60,
        )
        if not decision:
            return grew
        return bool(decision.get("recurse", grew))

    # ── final narrative (HEAVY, once) ───────────────────────────────────────
    async def final_report(self, scan_id: str) -> str:
        data = self._report_payload(scan_id)
        heuristic = self._heuristic_report(data)
        if not self.router.enabled:
            return heuristic
        text = await self.router.chat(
            system=(
                "You are a senior offensive-security analyst. Write a brief (<=150 "
                "words) executive summary of this recon result: scope of the attack "
                "surface, the most important exposures, and the top 3 prioritised "
                "next actions. Plain English. Do not invent data."
            ),
            user=str(data),
            tier="heavy",
            max_tokens=320,
        )
        return (text or heuristic).strip()

    # ── data helpers (compact, token-minimising) ────────────────────────────
    def _snapshot(self, scan_id: str) -> dict:
        with session_scope() as s:
            rows = s.execute(
                select(Asset.type, func.count())
                .where(Asset.scan_id == scan_id)
                .group_by(Asset.type)
            ).all()
            return {t: c for t, c in rows}

    def _heuristic_note(self, phase: str, counts: dict, scan_id: str) -> str:
        added = counts.get("asset", 0)
        ep = counts.get("endpoint", 0)
        fn = counts.get("finding", 0)
        bits = [f"{phase}: +{added} assets"]
        if ep:
            bits.append(f"+{ep} endpoints")
        if fn:
            bits.append(f"+{fn} findings")
        return ", ".join(bits)

    def _report_payload(self, scan_id: str) -> dict:
        with session_scope() as s:
            by_type = {t: c for t, c in s.execute(
                select(Asset.type, func.count()).where(Asset.scan_id == scan_id)
                .group_by(Asset.type)
            ).all()}
            live = s.execute(
                select(func.count()).where(Asset.scan_id == scan_id, Asset.is_live.is_(True))
            ).scalar()
            findings = s.execute(
                select(Finding.severity, func.count()).where(Finding.scan_id == scan_id)
                .group_by(Finding.severity)
            ).all()
            high_value = s.execute(
                select(Endpoint.url).where(
                    Endpoint.asset_id.in_(select(Asset.id).where(Asset.scan_id == scan_id)),
                    Endpoint.risk_class.is_not(None),
                ).limit(10)
            ).scalars().all()
        return {
            "assets_by_type": by_type,
            "live_assets": live or 0,
            "findings_by_severity": {sev: c for sev, c in findings},
            "high_value_endpoints": list(high_value),
        }

    def _heuristic_report(self, data: dict) -> str:
        by = data["assets_by_type"]
        subs = by.get("subdomain", 0)
        ips = by.get("ip", 0)
        fs = data["findings_by_severity"]
        hv = data["high_value_endpoints"]
        lines = [
            f"Attack surface: {subs} subdomains, {ips} IPs, {data['live_assets']} live hosts.",
        ]
        if fs:
            lines.append("Findings: " + ", ".join(f"{c} {sev}" for sev, c in fs.items()) + ".")
        if hv:
            lines.append(f"High-value endpoints to review first: {', '.join(hv[:5])}.")
        else:
            lines.append("No high-value endpoints flagged yet; run active phases for depth.")
        return " ".join(lines)
