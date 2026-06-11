"""Generate the recon execution matrix workbook from data/flow_plan.json.

This is the *planning* representation of the architecture, not a runtime DB.
It produces data/recon_matrix.xlsx with sheets:

  Legend       — how to read the workbook + the corrected data model
  Tools        — capability registry: one row per canonical tool (532),
                 with normalized consumes/produces, wired flag, storage,
                 and the typed-output-file convention
  EntityTypes  — canonical entity vocabulary + how the messy compound
                 `consumes` strings normalize onto it
  Routing      — entity_type -> tools that accept it (the DETERMINISTIC
                 router that replaces "AI sets a flag per key")
  WorkQueue    — the runtime task-table SCHEMA + a worked grow.in example
                 (this, not a 532-column sheet, is the live database shape)

Run:  python -m recontool.inventory.build_matrix
Pure: reads data/flow_plan.json, writes data/recon_matrix.xlsx. No network.
"""
from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[2]
FLOW = ROOT / "data" / "flow_plan.json"
OUT = ROOT / "data" / "recon_matrix.xlsx"

# Canonical entity vocabulary (the keys that can appear in the work queue).
CANON = [
    "domain", "subdomain", "live_host", "url", "endpoint", "ip", "cidr", "asn",
    "service", "host_port", "cert", "tech", "js_file", "secret", "bucket",
    "repo", "email", "username", "org", "keyword", "coords", "cpe", "file",
    "finding", "screenshot", "tag", "seed",
]

# Map a raw consumes/produces token onto canonical types. Compound forms like
# "domain_or_email" or "ip_domain_service" expand to several canonical types.
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


def normalize(raw: str) -> list[str]:
    """Turn a raw consumes/produces string into canonical types."""
    if not raw:
        return []
    out: list[str] = []
    # split compound separators: _or_, _, /
    parts = raw.replace("/", "_").replace("_or_", "_").split("_")
    i = 0
    while i < len(parts):
        p = parts[i]
        # "js_file" / "host_port" two-token forms
        if p == "js" and i + 1 < len(parts) and parts[i + 1] == "file":
            out.append("js_file"); i += 2; continue
        if p == "host" and i + 1 < len(parts) and parts[i + 1] == "port":
            out.append("host_port"); i += 2; continue
        if p == "live" and i + 1 < len(parts) and parts[i + 1] == "host":
            out.append("live_host"); i += 2; continue
        out += TOKEN.get(p, [])
        i += 1
    # dedupe, keep order
    seen, res = set(), []
    for t in out:
        if t not in seen:
            seen.add(t); res.append(t)
    return res


# ── styling helpers ──────────────────────────────────────────────────────────
HEAD = Font(bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="1F4E79")
WIRED_FILL = PatternFill("solid", fgColor="C6EFCE")
STUB_FILL = PatternFill("solid", fgColor="FFF2CC")
WRAP = Alignment(vertical="top", wrap_text=True)


def style_header(ws, ncols: int) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = HEAD
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"


def autowidth(ws, widths: dict[int, int]) -> None:
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = w


def build() -> None:
    tools = json.loads(FLOW.read_text())["tools"]
    wb = Workbook()

    # ── Legend ───────────────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Legend"
    legend = [
        ["Recon Execution Matrix", ""],
        ["Generated from", "data/flow_plan.json (source of truth: data/tool_inventory.json)"],
        ["", ""],
        ["READ THIS FIRST", ""],
        ["This workbook is the PLANNING view, not the runtime database.",
         "A 532-column 'keys x tools' sheet is the wrong shape for a live DB "
         "(wide, sparse, mostly N/A). The runtime store is TWO normalized tables:"],
        ["  1. Tools (capability registry)",
         "static: tool -> input types it consumes -> output types it produces. "
         "Defines the recursion GRAPH. See the 'Tools' sheet."],
        ["  2. WorkQueue (entity x tool jobs)",
         "dynamic: one row per (key, tool) job with a status. Grows at runtime. "
         "See the 'WorkQueue' sheet for the schema + a worked example."],
        ["", ""],
        ["Routing is deterministic, not AI.",
         "Which tools apply to a new subdomain is a JOIN: entity_type -> tools "
         "whose consumes includes that type (see 'Routing' sheet). AI is for "
         "EXTRACTING/classifying entities from messy tool output and for "
         "prioritization, NOT for re-deriving routing per key."],
        ["Wired vs stub",
         "Green rows in 'Tools' have a real runnable contract today (53). "
         "Yellow rows are documented stubs (479) needing a contract."],
        ["Typed output files",
         "Every run writes raw/<slug>/ AND one typed file per produced type: "
         "out/<key>/<slug>.<produced_type>.jsonl. A multi-mode tool (e.g. a "
         "brute-forcer used for subdomains AND paths) writes to BOTH "
         "<slug>.subdomain.jsonl and <slug>.url.jsonl."],
    ]
    for r in legend:
        ws.append(r)
    ws["A1"].font = Font(bold=True, size=14)
    for row in ws.iter_rows(min_row=4, max_row=ws.max_row, min_col=1, max_col=1):
        row[0].font = Font(bold=True)
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=2, max_col=2):
        row[0].alignment = WRAP
    autowidth(ws, {1: 34, 2: 95})

    # ── Tools ────────────────────────────────────────────────────────────────
    ws = wb.create_sheet("Tools")
    headers = ["#", "name", "slug", "category", "class", "method",
               "consumes (raw)", "consumes (canonical)", "produces (canonical)",
               "wired?", "web_only", "feeds_next", "store_db",
               "output_files (convention)"]
    ws.append(headers)
    for i, t in enumerate(tools, 1):
        cons_canon = normalize(t.get("consumes", ""))
        prod_canon = normalize(t.get("produces", ""))
        out_files = ", ".join(f"{t['slug']}.{p}.jsonl" for p in prod_canon if p not in ("none", "seed", "any")) or "raw/<slug>/"
        wired = "yes" if t.get("real_contract") else "stub"
        ws.append([
            i, t.get("name", ""), t.get("slug", ""),
            t.get("primary_section", ""), t.get("classification", ""),
            t.get("method", ""), t.get("consumes", ""),
            ", ".join(cons_canon), ", ".join(prod_canon),
            wired, "yes" if t.get("web_only") else "",
            t.get("feeds", ""), t.get("store_db", ""), out_files,
        ])
        fill = WIRED_FILL if t.get("real_contract") else STUB_FILL
        ws.cell(row=i + 1, column=10).fill = fill
    style_header(ws, len(headers))
    autowidth(ws, {1: 5, 2: 22, 3: 22, 4: 9, 5: 8, 6: 11, 7: 20,
                   8: 22, 9: 20, 10: 8, 11: 9, 12: 26, 13: 24, 14: 40})

    # ── EntityTypes ──────────────────────────────────────────────────────────
    ws = wb.create_sheet("EntityTypes")
    ws.append(["canonical entity type", "is a primary key?", "notes"])
    notes = {
        "domain": "apex/root domain — the usual seed",
        "subdomain": "rescan target; resolve -> ip, probe -> live_host",
        "live_host": "confirmed-live host:port; gate for active/web tools",
        "url": "page/endpoint; crawl + param mine",
        "endpoint": "API route; feeds fuzzing",
        "ip": "resolve target; port scan, reverse DNS, shodan",
        "cidr": "expand to ips",
        "asn": "expand to cidrs",
        "subdomain+path": "COMPOSITE key — a site living under a path; "
                           "worth its own recursive rescan (your grow.in/<path> case)",
    }
    pk = {"domain", "subdomain", "live_host", "url", "ip", "cidr", "asn"}
    for t in CANON + ["subdomain+path"]:
        ws.append([t, "yes" if t in pk or t == "subdomain+path" else "",
                   notes.get(t, "")])
    style_header(ws, 3)
    autowidth(ws, {1: 22, 2: 16, 3: 70})

    # ── Routing ──────────────────────────────────────────────────────────────
    ws = wb.create_sheet("Routing")
    ws.append(["entity_type", "# tools", "wired tools (run now)", "all tools (incl. stubs)"])
    route: dict[str, list[tuple[str, bool]]] = {}
    for t in tools:
        for ct in normalize(t.get("consumes", "")):
            route.setdefault(ct, []).append((t["slug"], bool(t.get("real_contract"))))
    for et in sorted(route):
        entries = route[et]
        wired = [s for s, w in entries if w]
        allt = [s for s, _ in entries]
        ws.append([et, len(allt), ", ".join(sorted(wired)),
                   ", ".join(sorted(allt))])
    style_header(ws, 4)
    autowidth(ws, {1: 14, 2: 8, 3: 60, 4: 90})
    for row in ws.iter_rows(min_row=2, min_col=3, max_col=4):
        for c in row:
            c.alignment = WRAP

    # ── WorkQueue (schema + example) ─────────────────────────────────────────
    ws = wb.create_sheet("WorkQueue")
    cols = ["job_id", "key", "key_type", "parent_key", "depth", "tool",
            "status", "output_path", "started_at", "finished_at", "new_keys_found"]
    ws.append(cols)
    example = [
        ["1", "grow.in", "domain", "", 0, "subfinder", "completed",
         "out/grow.in/subfinder.subdomain.jsonl", "10:00:01", "10:00:14", "37"],
        ["2", "grow.in", "domain", "", 0, "crtsh", "completed",
         "out/grow.in/crtsh.subdomain.jsonl", "10:00:01", "10:00:09", "12"],
        ["3", "api.grow.in", "subdomain", "grow.in", 1, "dns_resolve", "in_progress",
         "out/api.grow.in/dns_resolve.ip.jsonl", "10:00:20", "", ""],
        ["4", "api.grow.in", "subdomain", "grow.in", 1, "httpx_probe", "pending",
         "", "", "", ""],
        ["5", "api.grow.in", "subdomain", "grow.in", 1, "katana", "pending",
         "", "", "", ""],
        ["6", "20.40.11.7", "ip", "api.grow.in", 2, "naabu", "pending",
         "", "", "", ""],
        ["7", "api.grow.in/admin", "subdomain+path", "api.grow.in", 2, "pydirb",
         "pending", "", "", "", ""],
    ]
    for r in example:
        ws.append(r)
    style_header(ws, len(cols))
    autowidth(ws, {1: 7, 2: 22, 3: 14, 4: 16, 5: 6, 6: 14, 7: 12,
                   8: 40, 9: 11, 10: 11, 11: 14})
    note = ws.cell(row=len(example) + 3, column=1,
                   value="Status lifecycle: pending -> in_progress -> completed | failed. "
                         "A worker pulls the next 'pending' row, sets in_progress, runs the "
                         "tool, writes the typed output file, sets completed, and emits any "
                         "new_keys back as fresh rows (the recursion). 'pending' rows are "
                         "created by the deterministic Router (see Routing sheet) the moment "
                         "a key is discovered.")
    note.alignment = WRAP
    ws.merge_cells(start_row=len(example) + 3, start_column=1,
                   end_row=len(example) + 3, end_column=11)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"wrote {OUT.relative_to(ROOT)}  "
          f"({len(tools)} tools, "
          f"{sum(1 for t in tools if t.get('real_contract'))} wired)")


if __name__ == "__main__":
    build()
