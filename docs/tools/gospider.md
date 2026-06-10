# gospider

> Provenance: **recommended_addition** · canonical slug `gospider` · not in the source spreadsheet (closes a real gap).

**Purpose.** Fast Go web crawler (links, forms, JS, robots/sitemap, archive sources).

| Field | Value |
|-------|-------|
| Category | 22 — JavaScript Analysis & Secrets |
| Classification | **active** |
| Integration | cli (`gospider`) |
| Requires key | no |
| Consumes | `live_host, url` |
| Produces | `url, js_file` |
| Supersedes | — |

## Why it was added

Crawler redundancy improves coverage; gospider's source aggregation differs from katana.

**Best use.** Alternative/parallel crawler to katana/pycrawl for endpoint + JS harvesting.

## Capabilities → typed output files

  - **crawl** → produces `url` → writes `urls`
  - **js** → produces `js_file` → writes `js_files`

## Inputs / outputs

- **Consumes:** `live_host, url`.
- **Produces:** `url, js_file` → normalized to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Typed output:** each capability writes its own file under `artifacts/<scan_id>/by-type/<type>/` so multi-mode output never mixes (see [`docs/arch-v2/03-output-file-contract.md`](../arch-v2/03-output-file-contract.md)).

## Operational behavior

- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **Scope safety:** active tools re-check scope/liveness before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).
