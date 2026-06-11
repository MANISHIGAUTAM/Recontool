"""Generate the recon execution matrix workbook from the full tool catalog.

This is the *planning* mirror of the runtime DB matrix (`tool_row` + `work_item`,
seeded by `seed_matrix.py`). Both read the SAME source — `catalog.load_all_tools()`
— so the spreadsheet and the database can never drift. It produces
data/recon_matrix.xlsx with sheets:

  Legend       — how to read the workbook + the data model
  Tools        — capability registry: one row per canonical tool (ALL of them,
                 incl. web-only / suggested), with integration method, source,
                 runnable / default_on flags, and the typed-output-file convention
  EntityTypes  — canonical entity vocabulary
  Routing      — entity_type -> tools that accept it, using the SAME subsumption
                 as the runtime Router (subdomain also matches domain consumers)
  WorkQueue    — the runtime task-table schema + a worked grow.in example

Run:  python -m recontool.inventory.build_matrix
Pure: reads data/flow_plan.json (via catalog) + suggested_tools, writes the xlsx.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from recontool.engine.router import _eligible_types
from recontool.inventory.catalog import CANON, load_all_tools

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "recon_matrix.xlsx"

HEAD = Font(bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", fgColor="1F4E79")
WIRED_FILL = PatternFill("solid", fgColor="C6EFCE")
STUB_FILL = PatternFill("solid", fgColor="FFF2CC")
WEB_FILL = PatternFill("solid", fgColor="D9D9D9")
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
    tools = load_all_tools()
    wb = Workbook()

    # ── Legend ───────────────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Legend"
    n_run = sum(t.runnable for t in tools)
    n_web = sum(t.web_only for t in tools)
    n_sug = sum(t.source == "suggested" for t in tools)
    legend = [
        ["Recon Execution Matrix", ""],
        ["Generated from", "catalog.load_all_tools() — same source as the DB seeder"],
        ["Totals", f"{len(tools)} tools | {n_run} runnable | {n_web} web-only (kept) | "
                   f"{n_sug} suggested additions"],
        ["", ""],
        ["READ THIS FIRST", ""],
        ["This workbook is the PLANNING mirror of the runtime DB matrix.",
         "The live database is two tables: tool_row (this 'Tools' sheet) + "
         "work_item (the 'WorkQueue' sheet). Seed/query with "
         "`python -m recontool.inventory.seed_matrix`."],
        ["Nothing is eliminated.",
         "Web-only / no-integration tools are KEPT and flagged (grey rows), never "
         "removed — a later UI can still surface them."],
        ["Routing is deterministic, not AI.",
         "entity_type -> tools whose consumes includes it, WITH subsumption: a "
         "subdomain also matches domain-consuming tools (that is how recursion "
         "fans out). See the 'Routing' sheet — it matches the runtime Router."],
        ["Runnable vs available",
         "Green = real runnable contract today. Yellow = documented stub awaiting "
         "a contract. Grey = web-only/manual. All are available; default_on marks "
         "the recommended profile that runs out of the box."],
        ["Typed output files",
         "Every run writes raw/<slug>/ AND out/<key>/<slug>.<produced_type>.jsonl. "
         "Multi-mode tools write one typed file per produced type."],
    ]
    for r in legend:
        ws.append(r)
    ws["A1"].font = Font(bold=True, size=14)
    for row in ws.iter_rows(min_row=5, max_row=ws.max_row, min_col=1, max_col=1):
        row[0].font = Font(bold=True)
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=2, max_col=2):
        row[0].alignment = WRAP
    autowidth(ws, {1: 36, 2: 95})

    # ── Tools ────────────────────────────────────────────────────────────────
    ws = wb.create_sheet("Tools")
    headers = ["#", "name", "slug", "category", "class", "integration", "source",
               "consumes (canonical)", "produces (canonical)", "runnable",
               "default_on", "web_only", "output_files (convention)"]
    ws.append(headers)
    for i, t in enumerate(tools, 1):
        out_files = ", ".join(
            f"{t.slug}.{p}.jsonl" for p in t.produces
            if p not in ("none", "seed", "any")
        ) or "raw/<slug>/"
        ws.append([
            i, t.name, t.slug, t.category, t.classification,
            ", ".join(t.integration), t.source,
            ", ".join(t.consumes), ", ".join(t.produces),
            "yes" if t.runnable else "", "yes" if t.default_on else "",
            "yes" if t.web_only else "", out_files,
        ])
        if t.runnable:
            fill = WIRED_FILL
        elif t.web_only:
            fill = WEB_FILL
        else:
            fill = STUB_FILL
        ws.cell(row=i + 1, column=10).fill = fill
    style_header(ws, len(headers))
    autowidth(ws, {1: 5, 2: 24, 3: 22, 4: 16, 5: 8, 6: 12, 7: 10,
                   8: 24, 9: 22, 10: 9, 11: 10, 12: 9, 13: 40})

    # ── EntityTypes ──────────────────────────────────────────────────────────
    ws = wb.create_sheet("EntityTypes")
    ws.append(["canonical entity type", "is a primary key?", "subsumes (input)"])
    pk = {"domain", "subdomain", "live_host", "url", "ip", "cidr", "asn"}
    from recontool.engine.router import SUBSUMES
    for t in CANON + ["subdomain+path"]:
        ws.append([t, "yes" if t in pk or t == "subdomain+path" else "",
                   ", ".join(SUBSUMES.get(t, []))])
    style_header(ws, 3)
    autowidth(ws, {1: 22, 2: 16, 3: 40})

    # ── Routing (matches the runtime Router, incl. subsumption) ──────────────
    ws = wb.create_sheet("Routing")
    ws.append(["entity_type", "# tools (all)", "# default_on", "# runnable",
               "runnable tools (run now)"])
    for et in [k for k in CANON if k not in ("none", "any", "seed")]:
        wanted = _eligible_types(et)
        elig = [t for t in tools if wanted & set(t.consumes)]
        if not elig:
            continue
        runnable = sorted(t.slug for t in elig if t.runnable)
        ws.append([et, len(elig), sum(t.default_on for t in elig),
                   len(runnable), ", ".join(runnable)])
    style_header(ws, 5)
    autowidth(ws, {1: 14, 2: 12, 3: 12, 4: 11, 5: 90})
    for row in ws.iter_rows(min_row=2, min_col=5, max_col=5):
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
        ["2", "grow.in", "domain", "", 0, "crt-sh", "completed",
         "out/grow.in/crt-sh.subdomain.jsonl", "10:00:01", "10:00:09", "12"],
        ["3", "api.grow.in", "subdomain", "grow.in", 1, "dns_resolve", "in_progress",
         "out/api.grow.in/dns_resolve.ip.jsonl", "10:00:20", "", ""],
        ["4", "api.grow.in", "subdomain", "grow.in", 1, "httpx", "pending",
         "", "", "", ""],
        ["5", "20.40.11.7", "ip", "api.grow.in", 2, "naabu", "pending",
         "", "", "", ""],
        ["6", "api.grow.in/admin", "subdomain+path", "api.grow.in", 2, "ffuf",
         "pending", "", "", "", ""],
    ]
    for r in example:
        ws.append(r)
    style_header(ws, len(cols))
    autowidth(ws, {1: 7, 2: 22, 3: 14, 4: 16, 5: 6, 6: 14, 7: 12,
                   8: 40, 9: 11, 10: 11, 11: 14})
    note = ws.cell(row=len(example) + 3, column=1,
                   value="Lifecycle: pending -> in_progress -> completed | failed. A worker "
                         "pulls the next 'pending' row, runs the tool, writes the typed "
                         "output, sets completed, and emits new keys as fresh rows (the "
                         "recursion). enqueue() dedupes on (scan_id, key, tool), so a "
                         "re-discovered key is never rescanned.")
    note.alignment = WRAP
    ws.merge_cells(start_row=len(example) + 3, start_column=1,
                   end_row=len(example) + 3, end_column=11)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"wrote {OUT.relative_to(ROOT)}  ({len(tools)} tools, "
          f"{n_run} runnable, {n_web} web-only kept, {n_sug} suggested)")


if __name__ == "__main__":
    build()
