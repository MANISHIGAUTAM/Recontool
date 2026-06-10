# dnsgen

> Provenance: **recommended_addition** · canonical slug `dnsgen` · not in the source spreadsheet (closes a real gap).

**Purpose.** Generate subdomain permutation/mutation candidates from known names.

| Field | Value |
|-------|-------|
| Category | 2 — Passive DNS & Subdomain Enum |
| Classification | **passive** |
| Integration | cli (`dnsgen`) |
| Requires key | no |
| Consumes | `domain, subdomain` |
| Produces | `subdomain` |
| Supersedes | altdns |

## Why it was added

Referenced in gap analysis but unlisted; candidates feed active resolution, not the asset store directly.

**Best use.** Feed puredns/shuffledns/dnsx resolution (candidates, not confirmed assets).

## Capabilities → typed output files

  - **permute** → produces `subdomain` → writes `subdomain_candidates`

## Inputs / outputs

- **Consumes:** `domain, subdomain`.
- **Produces:** `subdomain` → normalized to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Typed output:** each capability writes its own file under `artifacts/<scan_id>/by-type/<type>/` so multi-mode output never mixes (see [`docs/arch-v2/03-output-file-contract.md`](../arch-v2/03-output-file-contract.md)).

## Operational behavior

- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **Scope safety:** active tools re-check scope/liveness before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).
