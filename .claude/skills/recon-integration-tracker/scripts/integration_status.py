#!/usr/bin/env python3
"""Deterministic tool-integration status report for Recontool.

Answers the one question that keeps getting lost across AI sessions:
"Of the 532 canonical tools, which are actually WIRED, which are only
documented, and what is the next incomplete step for each?"

It derives status by scanning the repo's sources of truth — never from
memory — so the picture is reproducible every run:

  documented  : has a docs/tools/<slug>.md capability doc (the universe)
  contracted  : has a runnable contract in config/tools.yaml OR
                config/tools_generic.yaml (endpoint/binary + parse.emit)
  adapter     : has a hand-written adapter (recontool/adapters/*.py: name = "..")
  tested      : referenced by a test under tests/ (fixture or assertion)

A tool is WIRED when it is `contracted`, has an `adapter`, or is an `alias`
of a tool that is (a doc-only sub-feature / mode / rename whose canonical is
itself wired — see _ALIASES). Everything else is a documented stub that the
engine will mark runnable=False.

Usage:
    python3 integration_status.py                # summary + gap counts
    python3 integration_status.py --missing      # list documented-but-unwired
    python3 integration_status.py --tool crt-sh  # full checklist for one tool
    python3 integration_status.py --json         # machine-readable
    python3 integration_status.py --category 2   # filter by category (best-effort)

Run from anywhere; it locates the repo root by walking up to find docs/tools.
Pure stdlib — no pyyaml needed (configs parsed with light structural regex).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def find_root(start: Path) -> Path:
    p = start.resolve()
    for cand in [p, *p.parents]:
        if (cand / "docs" / "tools").is_dir() and (cand / "config").is_dir():
            return cand
    print("ERROR: could not locate repo root (need docs/tools + config/).", file=sys.stderr)
    sys.exit(2)


def norm(slug: str) -> str:
    """Canonical match key: lowercase, strip separators so crt-sh == crtsh."""
    return re.sub(r"[^a-z0-9]", "", slug.lower())


# Doc-slug -> the canonical tool it is a sub-feature / mode / rename of. Every
# canonical below is ALREADY WIRED under its own slug, so these docs describe an
# already-integrated capability (e.g. `shodan-screenshots` is a facet of the wired
# `shodan`; `owasp-amass` is just `amass`). Without this, the same capability is
# double-counted as a "missing" tool. The tracker marks an alias wired (via alias)
# only if its canonical is actually contracted/adaptered — so a typo can't fake
# coverage. Verified 2026-07: each canonical resolves to a live contract/adapter.
_ALIASES = {
    "alienvault-otx-api": "alienvault-otx",
    "alienvault-otx-pulse-archive": "alienvault-otx",
    "alienvault-otx-search": "alienvault-otx",
    "amass-passive-mode": "amass",
    "owasp-amass": "amass",
    "censys-api": "censys",
    "censys-asm": "censys",
    "censys-screenshots": "censys",
    "chaos-dataset": "chaos",
    "criminalip-api": "criminal-ip",
    "criminalip-asm": "criminal-ip",
    "eyewitness-ng": "eyewitness",
    "greynoise-api": "greynoise",
    "ipinfo-api": "ipinfo",
    "katana-screenshots": "katana",
    "leakix-buckets": "leakix",
    "netlas-api": "netlas",
    "netlas-explorer": "netlas",
    "netlas-hosts": "netlas",
    "nuclei-templates": "nuclei",
    "securitytrails-api": "securitytrails",
    "securitytrails-historical-dns": "securitytrails",
    "shodan-api": "shodan",
    "shodan-screenshots": "shodan",
    "uncover-engine": "uncover",
    "urlscan-api": "urlscan",
    "urlscan-history": "urlscan",
    "urlscan-io": "urlscan",
    "urlscan-screenshots": "urlscan",
    "urlscan-search": "urlscan",
    "virustotal-api": "virustotal",
}


def documented_tools(root: Path) -> dict[str, str]:
    """slug-norm -> original doc slug, from docs/tools/*.md (excluding README)."""
    out = {}
    for md in (root / "docs" / "tools").glob("*.md"):
        if md.stem.lower() == "readme":
            continue
        out[norm(md.stem)] = md.stem
    return out


def tools_yaml_names(root: Path) -> set[str]:
    """Top-level tool keys under `tools:` in config/tools.yaml (2-space indent)."""
    path = root / "config" / "tools.yaml"
    if not path.exists():
        return set()
    names, in_tools = set(), False
    for line in path.read_text().splitlines():
        if re.match(r"^tools:\s*$", line):
            in_tools = True
            continue
        if in_tools:
            # a new top-level (col-0, non-space) block ends the tools map
            if line and not line[0].isspace() and not line.startswith("#"):
                in_tools = False
                continue
            m = re.match(r"^  ([A-Za-z0-9_\-]+):\s*$", line)
            if m:
                names.add(norm(m.group(1)))
    return names


def generic_yaml_names(root: Path) -> set[str]:
    """`- name: foo` entries in config/tools_generic.yaml + config/tools_generic.d/*.yaml
    (Batch-12 per-family contract files)."""
    files = []
    main = root / "config" / "tools_generic.yaml"
    if main.exists():
        files.append(main)
    gdir = root / "config" / "tools_generic.d"
    if gdir.is_dir():
        files += sorted(gdir.glob("*.yaml"))
    out: set[str] = set()
    for path in files:
        out |= {
            norm(m.group(1))
            for m in re.finditer(r"^\s*-\s*name:\s*([A-Za-z0-9_\-]+)", path.read_text(), re.M)
        }
    return out


def adapter_names(root: Path) -> set[str]:
    """`name = "foo"` class attributes across recontool/adapters/*.py."""
    out = set()
    adir = root / "recontool" / "adapters"
    if not adir.is_dir():
        return out
    for py in adir.glob("*.py"):
        for m in re.finditer(r'^\s+name\s*=\s*["\']([A-Za-z0-9_\-]+)["\']', py.read_text(), re.M):
            out.add(norm(m.group(1)))
    return out


def tested_names(root: Path, universe: set[str]) -> set[str]:
    """Tools whose normalized slug appears as a token anywhere under tests/."""
    out = set()
    tdir = root / "tests"
    if not tdir.is_dir():
        return out
    blob = " ".join(
        norm(p.read_text(errors="ignore"))
        for p in tdir.rglob("*")
        if p.is_file() and p.suffix in {".py", ".json", ".yaml", ".yml", ".txt"}
    )
    for slug in universe:
        if len(slug) >= 4 and slug in blob:
            out.add(slug)
    return out


def category_of(root: Path, doc_slug: str) -> str:
    """Best-effort category pull from the tool's doc front matter / body."""
    md = root / "docs" / "tools" / f"{doc_slug}.md"
    if not md.exists():
        return ""
    txt = md.read_text(errors="ignore")[:1500]
    m = re.search(r"[Cc]ategor(?:y|ies)[^\n0-9]*([0-9]{1,2})", txt)
    return m.group(1) if m else ""


def build(root: Path) -> dict:
    docs = documented_tools(root)
    contracted = tools_yaml_names(root) | generic_yaml_names(root)
    adapters = adapter_names(root)
    tested = tested_names(root, set(docs))

    live = contracted | adapters
    alias_canon = {norm(k): v for k, v in _ALIASES.items()}   # norm(doc) -> canonical slug

    rows = []
    for key, slug in sorted(docs.items(), key=lambda kv: kv[1]):
        has_contract = key in contracted
        has_adapter = key in adapters
        # alias covered iff its canonical is a live contract/adapter (no fake coverage)
        alias_of = None
        canon = alias_canon.get(key)
        if not (has_contract or has_adapter) and canon and norm(canon) in live:
            alias_of = canon
        wired = has_contract or has_adapter or bool(alias_of)
        rows.append({
            "slug": slug,
            "documented": True,
            "contracted": has_contract,
            "adapter": has_adapter,
            "alias_of": alias_of,
            "tested": key in tested,
            "wired": wired,
        })
    # contracts/adapters that have no doc (orphans worth knowing about)
    orphans = sorted((contracted | adapters) - set(docs))
    return {"rows": rows, "orphans": orphans,
            "counts": {
                "documented": len(rows),
                "wired": sum(r["wired"] for r in rows),
                "contracted": sum(r["contracted"] for r in rows),
                "adapter": sum(r["adapter"] for r in rows),
                "alias": sum(bool(r["alias_of"]) for r in rows),
                "tested": sum(r["tested"] for r in rows),
            }}


def checklist(row: dict) -> list[str]:
    """Definition-of-done for one tool; ✓ done, ✗ todo."""
    def mk(done, label):
        return f"  [{'x' if done else ' '}] {label}"
    wired = row["wired"]
    return [
        mk(row["documented"], "capability doc in docs/tools/"),
        mk(row["contracted"] or row["adapter"],
           "runnable contract (config/tools*.yaml) OR hand-written adapter"),
        mk(row["contracted"], "  - declarative: consumes/produces + parse.emit + scope_filter + bucket"),
        mk(row["adapter"], "  - OR python adapter with available()+run() (high-value/complex only)"),
        mk(row["tested"], "parser/emit test against a captured fixture (no network)"),
        mk(wired, "registered & reachable: scheduler can select it on an available key"),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--missing", action="store_true", help="list documented-but-unwired tools")
    ap.add_argument("--tool", help="full checklist for one tool slug")
    ap.add_argument("--category", help="filter by category number (best-effort from docs)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    root = find_root(Path(__file__).parent)
    data = build(root)
    rows = data["rows"]

    if args.category:
        want = args.category.strip()
        rows = [r for r in rows if category_of(root, r["slug"]) == want]
        data = {**data, "rows": rows}

    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    if args.tool:
        key = norm(args.tool)
        match = next((r for r in rows if norm(r["slug"]) == key), None)
        if not match:
            print(f"No documented tool matches '{args.tool}'.")
            return 1
        status = "WIRED" if match["wired"] else "STUB (documented only)"
        print(f"\n{match['slug']}  —  {status}\n")
        print("Definition of done:")
        print("\n".join(checklist(match)))
        if not match["wired"]:
            print("\nNext step: add a contract in config/tools_generic.yaml "
                  "(api/cli + consumes/produces + parse.emit), then a fixture test.")
        return 0

    c = data["counts"]
    pct = 100 * c["wired"] // max(c["documented"], 1)
    print("\n=== Recontool integration status ===")
    print(f"  documented (universe) : {c['documented']}")
    print(f"  WIRED (runnable)      : {c['wired']}  ({pct}%)")
    print(f"    via contract        : {c['contracted']}")
    print(f"    via python adapter  : {c['adapter']}")
    print(f"    via alias (covered) : {c.get('alias', 0)}  (sub-feature/rename of a wired tool)")
    print(f"  tested                : {c['tested']}")
    print(f"  unwired stubs         : {c['documented'] - c['wired']}")
    if data["orphans"]:
        print(f"  ⚠ wired but undocumented: {len(data['orphans'])} -> {', '.join(data['orphans'][:12])}")
    if args.missing:
        miss = [r["slug"] for r in rows if not r["wired"]]
        print(f"\n--- {len(miss)} documented-but-unwired ---")
        for i in range(0, len(miss), 6):
            print("  " + "  ".join(miss[i:i + 6]))
    else:
        print("\nRun with --missing to list unwired tools, "
              "--tool <slug> for one tool's checklist, --json for data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
