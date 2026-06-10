# qsreplace

> Provenance: **recommended_addition** · canonical slug `qsreplace` · not in the source spreadsheet (closes a real gap).

**Purpose.** Rewrite query-string values across a URL list (fuzz-prep glue).

| Field | Value |
|-------|-------|
| Category | 25 — Parameter Discovery & Fuzz Prep |
| Classification | **passive** |
| Integration | cli (`qsreplace`) |
| Requires key | no |
| Consumes | `url` |
| Produces | `url` |
| Supersedes | — |

## Why it was added

Core pipeline plumbing referenced in the gap analysis but never listed as a tool; needed to turn harvested URLs into tuned fuzz inputs.

**Best use.** Normalize/seed URL variants for parameter probing; pairs with gf/arjun/x8.

## Capabilities → typed output files

  - **rewrite** → produces `url` → writes `urls`

## Inputs / outputs

- **Consumes:** `url`.
- **Produces:** `url` → normalized to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Typed output:** each capability writes its own file under `artifacts/<scan_id>/by-type/<type>/` so multi-mode output never mixes (see [`docs/arch-v2/03-output-file-contract.md`](../arch-v2/03-output-file-contract.md)).

## Operational behavior

- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **Scope safety:** active tools re-check scope/liveness before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).
