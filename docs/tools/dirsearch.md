# dirsearch

> Provenance: **recommended_addition** · canonical slug `dirsearch` · not in the source spreadsheet (closes a real gap).

**Purpose.** Recursive web path/file brute-forcer with rich extension handling and 404 calibration.

| Field | Value |
|-------|-------|
| Category | 20 — Content & Directory Discovery |
| Classification | **active** |
| Integration | cli (`dirsearch`) |
| Requires key | no |
| Consumes | `live_host, url` |
| Produces | `url, endpoint` |
| Supersedes | — |

## Why it was added

Cat-20 alternative engine; some targets behave differently across fuzzers, dirsearch's extension/recursion model finds paths the others miss.

**Best use.** Content/directory discovery on live hosts; complements ffuf/feroxbuster.

## Capabilities → typed output files

  - **dir** → produces `url, endpoint` → writes `paths`

## Inputs / outputs

- **Consumes:** `live_host, url`.
- **Produces:** `url, endpoint` → normalized to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Typed output:** each capability writes its own file under `artifacts/<scan_id>/by-type/<type>/` so multi-mode output never mixes (see [`docs/arch-v2/03-output-file-contract.md`](../arch-v2/03-output-file-contract.md)).

## Operational behavior

- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **Scope safety:** active tools re-check scope/liveness before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).
