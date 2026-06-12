"""Single canonical loader for the FULL tool catalog (nothing eliminated).

This is the one place that merges the two tool sources into a uniform record:

  1. data/flow_plan.json   — 532 extracted spreadsheet tools (incl. web-only /
     no-integration tools, which are KEPT and flagged, never removed).
  2. recontool.inventory.suggested_tools.TOOLS — 32 architecture-review gap
     closers (marked source="suggested").

Both the DB seeder (`seed_matrix.py`) and the Excel generator (`build_matrix.py`)
consume `load_all_tools()`, so the database matrix and the spreadsheet matrix can
never drift apart. Pure: stdlib + json, no network, no DB.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLOW = ROOT / "data" / "flow_plan.json"
CONFIG = ROOT / "config"
ADAPTERS = ROOT / "recontool" / "adapters"


def _norm(slug: str) -> str:
    """Match key so crt-sh == crtsh == crt_sh across sources."""
    return re.sub(r"[^a-z0-9]", "", str(slug).lower())


def contracted_slugs() -> set[str]:
    """Normalized slugs that have a REAL executable contract today: a curated
    entry in config/tools.yaml or config/tools_generic.yaml, or a hand-written
    adapter (`name = "..."`). This is the honest source for `runnable` — it grows
    the moment a spec is added, instead of a stale static flag."""
    out: set[str] = set()
    ty = CONFIG / "tools.yaml"
    if ty.exists():
        in_tools = False
        for line in ty.read_text().splitlines():
            if re.match(r"^tools:\s*$", line):
                in_tools = True
                continue
            if in_tools:
                if line and not line[0].isspace() and not line.startswith("#"):
                    in_tools = False
                    continue
                m = re.match(r"^  ([A-Za-z0-9_\-]+):\s*$", line)
                if m:
                    out.add(_norm(m.group(1)))
    tg = CONFIG / "tools_generic.yaml"
    if tg.exists():
        for m in re.finditer(r"^\s*-\s*name:\s*([A-Za-z0-9_\-]+)", tg.read_text(), re.M):
            out.add(_norm(m.group(1)))
    if ADAPTERS.is_dir():
        for py in ADAPTERS.glob("*.py"):
            for m in re.finditer(r'^\s+name\s*=\s*["\']([A-Za-z0-9_\-]+)["\']',
                                 py.read_text(), re.M):
                out.add(_norm(m.group(1)))
    return out

# Canonical entity vocabulary (the WorkQueue key types).
CANON = [
    "domain", "subdomain", "live_host", "url", "endpoint", "ip", "cidr", "asn",
    "service", "host_port", "cert", "tech", "js_file", "secret", "bucket",
    "repo", "email", "username", "org", "keyword", "coords", "cpe", "file",
    "finding", "screenshot", "tag", "seed",
]

# Raw token -> canonical type(s). Compound forms (domain_or_email,
# ip_domain_service) expand to several canonical types.
TOKEN = {
    "domain": ["domain"], "subdomain": ["subdomain"], "live": ["live_host"],
    "host": ["live_host"], "url": ["url"], "endpoint": ["endpoint"],
    "ip": ["ip"], "cidr": ["cidr"], "asn": ["asn"], "service": ["service"],
    "cert": ["cert"], "tech": ["tech"], "js": ["js_file"], "secret": ["secret"],
    "bucket": ["bucket"], "repo": ["repo"], "email": ["email"],
    "username": ["username"], "org": ["org"], "keyword": ["keyword"],
    "coords": ["coords"], "cpe": ["cpe"], "file": ["file"],
    "finding": ["finding"], "screenshot": ["screenshot"], "tag": ["tag"],
    "any": ["any"], "none": ["seed"], "resolver": [],
}

# flow_plan `method` -> integration method tag (nothing dropped; web/manual kept).
METHOD_MAP = {
    "binary": "cli", "API": "api", "python": "python", "dataset": "dataset",
    "web/manual": "web", "unspecified": "web",
}

# Tools that ship enabled by default beyond the currently-wired set (the
# recommended profile, canonical spec §7a). Everything else stays available but
# off-by-default; the later UI flips these. Kept tiny + honest on purpose.
RECOMMENDED = {
    "subfinder", "amass", "crt-sh", "uncover", "httpx", "dnsx", "naabu",
    "katana", "nuclei", "waymore", "gowitness", "alterx",
}

# EXACT-output duplicates: kept AVAILABLE but forced OFF by default because a
# superset tool produces the same data. Demote ONLY when certain the output is
# identical — overlapping-but-different sources (crt-sh vs certspotter, subfinder
# vs amass, dnsx vs massdns) corroborate each other and stay on. slug -> superset.
EXACT_OVERLAP = {
    "gauplus": "gau",  # unmaintained fork of gau; identical Wayback/CC/OTX/URLScan sources
}


def normalize(raw: str) -> list[str]:
    """Turn a raw consumes/produces string into canonical types."""
    if not raw:
        return []
    out: list[str] = []
    parts = raw.replace("/", "_").replace("_or_", "_").split("_")
    i = 0
    while i < len(parts):
        p = parts[i]
        if p == "js" and i + 1 < len(parts) and parts[i + 1] == "file":
            out.append("js_file")
            i += 2
            continue
        if p == "host" and i + 1 < len(parts) and parts[i + 1] == "port":
            out.append("host_port")
            i += 2
            continue
        if p == "live" and i + 1 < len(parts) and parts[i + 1] == "host":
            out.append("live_host")
            i += 2
            continue
        out += TOKEN.get(p, [])
        i += 1
    seen, res = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            res.append(t)
    return res


@dataclass
class ToolRecord:
    slug: str
    name: str
    category: str
    classification: str          # passive | active | hybrid
    integration: list[str]       # cli | api | python | dataset | web (>=1; never empty)
    consumes: list[str]          # canonical types
    produces: list[str]          # canonical types
    runnable: bool               # has a real executable contract today
    web_only: bool               # no programmatic integration (kept, not removed)
    default_on: bool             # in the recommended profile
    source: str                  # extracted | suggested
    feeds: str = ""
    store_db: str = ""
    modes: list[str] = field(default_factory=list)


def _from_flow(t: dict) -> ToolRecord:
    method = t.get("method", "web")
    integration = [METHOD_MAP.get(method, "web")]
    web_only = bool(t.get("web_only")) or integration == ["web"]
    runnable = bool(t.get("real_contract"))
    slug = t.get("slug", "")
    return ToolRecord(
        slug=slug, name=t.get("name", slug),
        category=str(t.get("primary_section", "")),
        classification=t.get("classification", "passive"),
        integration=integration,
        consumes=normalize(t.get("consumes", "")),
        produces=normalize(t.get("produces", "")),
        runnable=runnable, web_only=web_only,
        default_on=(runnable or slug in RECOMMENDED) and slug not in EXACT_OVERLAP,
        source="extracted", feeds=t.get("feeds", ""),
        store_db=t.get("store_db", ""),
    )


def _from_suggested(s) -> ToolRecord:
    return ToolRecord(
        slug=s.slug, name=s.name, category=s.group,
        classification=s.klass, integration=[s.integration],
        consumes=normalize(s.consumes), produces=normalize(s.produces),
        runnable=False, web_only=False,
        default_on=s.slug in RECOMMENDED and s.slug not in EXACT_OVERLAP,
        source="suggested", feeds="", store_db="", modes=list(s.modes),
    )


def load_all_tools() -> list[ToolRecord]:
    """The complete catalog: 532 extracted + 32 suggested, nothing dropped.

    On a slug collision the extracted record wins and is marked runnable if
    either source says so (curated contract beats a suggestion)."""
    from recontool.inventory.suggested_tools import TOOLS as SUGGESTED

    by_slug: dict[str, ToolRecord] = {}
    for t in json.loads(FLOW.read_text())["tools"]:
        rec = _from_flow(t)
        by_slug[rec.slug] = rec
    for s in SUGGESTED:
        rec = _from_suggested(s)
        if rec.slug in by_slug:
            # keep extracted record; inherit suggested modes/integration info
            existing = by_slug[rec.slug]
            existing.modes = existing.modes or rec.modes
            continue
        by_slug[rec.slug] = rec

    # Honest, live runnable: a tool is runnable if it has an actual contract
    # (curated yaml or adapter), regardless of the stale flow_plan flag. As specs
    # are added the count climbs truthfully. default_on follows runnable.
    contracts = contracted_slugs()
    for rec in by_slug.values():
        if _norm(rec.slug) in contracts:
            rec.runnable = True
            if rec.slug not in EXACT_OVERLAP:
                rec.default_on = True
    return sorted(by_slug.values(), key=lambda r: (r.source != "extracted", r.name.lower()))


if __name__ == "__main__":
    recs = load_all_tools()
    runnable = sum(r.runnable for r in recs)
    web = sum(r.web_only for r in recs)
    print(f"catalog: {len(recs)} tools | runnable={runnable} | "
          f"web-only(kept)={web} | default_on={sum(r.default_on for r in recs)} | "
          f"suggested={sum(r.source=='suggested' for r in recs)}")
