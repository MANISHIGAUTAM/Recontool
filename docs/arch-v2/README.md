# Architecture v2 — Event-Based Entity × Tool State Matrix

Design for the "Excel-as-a-database" recursive recon engine, on branch
`arch/event-based-arch-v2`.

| Doc | What it covers |
|-----|----------------|
| [`01-event-based-state-matrix.md`](01-event-based-state-matrix.md) | The model: primary keys × tools × state, the loop, where AI decides, mapping to existing code, pre-built-vs-dynamic, and an honest "is it good?" review. |
| [`02-implementation-steps.md`](02-implementation-steps.md) | Ordered, incremental build plan (typed outputs → work-item table → frontier-driven loop → AI decisions → export/guardrails). |
| [`03-output-file-contract.md`](03-output-file-contract.md) | Every tool produces typed output files; multi-capability tools split by produced type (paths vs subdomains). |

Spreadsheet projection: [`data/recontool_state_matrix.xlsx`](../../data/recontool_state_matrix.xlsx)
— regenerate with `python -m recontool.inventory.build_state_matrix`.

Added tools: [`data/added_tools.json`](../../data/added_tools.json) (+ `docs/tools/*.md`).
