"""Atomic checks for the final scan-summary builder (heuristic path)."""
from __future__ import annotations

import pytest

from recontool.engine.summary import _heuristic_summary, generate_summary

_FACTS = {
    "seed": "groww.in", "seed_type": "domain", "active_authorized": True,
    "assets_by_type": {"subdomain": 255, "url": 8013, "ip": 39},
    "assets_total": 8307, "live_assets": 12, "services": 4,
    "findings_by_severity": {"high": 1, "info": 7}, "findings_total": 8,
    "top_findings": [{"severity": "high", "title": "Exposed secret",
                      "asset": "assets-netstorage.groww.in"}],
    "max_depth": 2,
    "work_items": {"completed": 6900, "failed": 3},
    "tools": {"produced": {"urlscan": 392, "hackertarget": 117},
              "ran_empty": ["amass", "subfinder"],
              "failed": {"nikto": "timeout"}},
}


def test_heuristic_summary_is_grounded_in_facts():
    md = _heuristic_summary(_FACTS)
    assert "groww.in" in md and "active" in md
    assert "8307 assets" in md
    assert "Exposed secret" in md          # notable finding surfaced
    assert "urlscan (392)" in md           # top producer surfaced
    assert "1 failed" in md and "nikto" in md
    assert "12 confirmed live" in md


@pytest.mark.asyncio
async def test_generate_summary_heuristic_when_no_router(monkeypatch):
    # router=None -> deterministic heuristic, no model call, never raises.
    import recontool.engine.summary as summ
    monkeypatch.setattr(summ, "build_scan_facts", lambda scan_id: _FACTS)
    text, facts = await generate_summary("scan123", router=None)
    assert facts is _FACTS
    assert text.startswith("# Scan summary — groww.in")
