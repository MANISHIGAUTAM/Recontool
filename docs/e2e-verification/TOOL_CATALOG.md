# ReconTool — Full Tool Truth Catalog (Batch 11, post-M9)

Read-only, evidence-based catalog of **all 586 registry entries** — the source of truth
for routing / scheduling / recursion / validation / AI decisioning / future exploitation.
Regenerated against the **post-M9 flow-correctness registry** (live_host gate, js_file
gating, narrowed subsumption, canonical vocabulary, deferred classification), crossed
with **runtime evidence** from real scans (`ToolRun` rows + `out/*.runs.jsonl`).

Nothing here changes engine behavior — pure audit. (Supersedes the earlier groww.in
catalog, which predated the M1–M9 flow work.)

## Deliverables in this directory
| File | What |
|---|---|
| [`TOOL_CATALOG_REPORTS.md`](TOOL_CATALOG_REPORTS.md) | Executive summary + the analysis reports (scheduling matrix, exploitation taxonomy, duplicates, orphans, dead-weight, final taxonomy) |
| [`TOOL_CATALOG_FULL.tsv`](TOOL_CATALOG_FULL.tsv) | Per-tool matrix (586 rows): status, kind, recursion class, stage, consumes, declared/observed output, artifact type, recommendation, up/downstream counts, invocation, confidence |
| [`tool_catalog.tsv`](tool_catalog.tsv) | Raw generator output (`scripts/tool_catalog.py`): registry × runtime evidence |

## How to regenerate (read-only)
```bash
PYTHONPATH=$(pwd) python3 scripts/tool_catalog.py <scan_id> [scan_id ...]   # raw truth table
PYTHONPATH=$(pwd) python3 scripts/flow_lint.py                              # reachability guard
PYTHONPATH=$(pwd) python3 scripts/install_audit.py                         # install evidence
PYTHONPATH=$(pwd) python3 scripts/tool_invocation_probe.py                 # invocation evidence
```
The full matrix + reports are produced by a one-shot analysis over the live registry +
`recontool/engine/flow_graph.py` (the producer/consumer graph). Methodology note: the
recursion class is exact for runnable tools, approximate for inventory stubs whose
`produces` is category-inflated (`category_io`), not tool-specific.

## Headline (full numbers in the reports)
- **586** registry entries: **334** schedulable (26 KEEP_CORE, 266 KEEP_OPTIONAL, 28
  VALIDATION_ONLY, 8 ENRICHMENT_ONLY, 6 ARTIFACT_ONLY), **150** DEFER, **102**
  REFERENCE_ONLY.
- **Ran in evidence scans** (1e453aa1, abae971f, 856f38a7, b57cbcaee): 30 produced data,
  9 empty; 45 installable-not-present, 13 need an API key.
- **Recursion roles:** Generator 327 · Terminal 79 · Expander 36 · Validator 28 ·
  Enrichment 8 · Artifact-Analyzer 6 · Reference 102.
- **Core recon flow in-scope reachability = 0** (agrees with `flow_lint`). Remaining gaps
  are deferred (file-analysis, enrichment producers) or off-by-default overlay.
- **Exploitation / Post-Exploitation layers are empty by design** — detection tools
  (nuclei/WPScan) are Terminal; this is the home for the future exploitation framework.
- **One wiring nit surfaced:** under `--authorize-active`, `host_port` dead-ends
  (naabu/masscan emit it; curated nmap consumes ip/subdomain) — follow-on fix.
