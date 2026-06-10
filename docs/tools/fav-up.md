# fav-up

> Provenance: **recommended_addition** · canonical slug `fav-up` · not in the source spreadsheet (closes a real gap).

**Purpose.** Resolve real origin IP from favicon hash via Shodan (CDN-bypass discovery).

| Field | Value |
|-------|-------|
| Category | 1 — Internet-Wide Search & Asset Discovery |
| Classification | **hybrid** |
| Integration | cli (`fav-up`) |
| Requires key | no |
| Consumes | `live_host, url` |
| Produces | `ip` |
| Supersedes | — |

## Why it was added

Complements favfreak for origin-IP discovery; origin IPs re-enter Cat-21/Cat-3.

**Best use.** Recover origin IPs to re-enter port scanning / network intel.

## Capabilities → typed output files

  - **favicon-realip** → produces `ip` → writes `ips`

## Inputs / outputs

- **Consumes:** `live_host, url`.
- **Produces:** `ip` → normalized to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Typed output:** each capability writes its own file under `artifacts/<scan_id>/by-type/<type>/` so multi-mode output never mixes (see [`docs/arch-v2/03-output-file-contract.md`](../arch-v2/03-output-file-contract.md)).

## Operational behavior

- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **Scope safety:** active tools re-check scope/liveness before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).
