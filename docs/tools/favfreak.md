# favfreak

> Provenance: **recommended_addition** · canonical slug `favfreak` · not in the source spreadsheet (closes a real gap).

**Purpose.** Compute favicon mmh3 hashes and pivot to related hosts via Shodan/ZoomEye.

| Field | Value |
|-------|-------|
| Category | 1 — Internet-Wide Search & Asset Discovery |
| Classification | **passive** |
| Integration | cli (`favfreak`) |
| Requires key | no |
| Consumes | `live_host, url` |
| Produces | `ip, subdomain` |
| Supersedes | — |

## Why it was added

Underrated correlation pivot called out in the gap analysis; feeds Cat-1/Cat-2 recursion.

**Best use.** Find sibling infrastructure (incl. origin behind CDN) sharing a favicon.

## Capabilities → typed output files

  - **favicon-hash** → produces `ip, subdomain` → writes `ips`

## Inputs / outputs

- **Consumes:** `live_host, url`.
- **Produces:** `ip, subdomain` → normalized to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Typed output:** each capability writes its own file under `artifacts/<scan_id>/by-type/<type>/` so multi-mode output never mixes (see [`docs/arch-v2/03-output-file-contract.md`](../arch-v2/03-output-file-contract.md)).

## Operational behavior

- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **Scope safety:** active tools re-check scope/liveness before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).
