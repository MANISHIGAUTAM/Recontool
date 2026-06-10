# clairvoyance

> Provenance: **recommended_addition** · canonical slug `clairvoyance` · not in the source spreadsheet (closes a real gap).

**Purpose.** Recover GraphQL schema even when introspection is disabled (suggestion-based).

| Field | Value |
|-------|-------|
| Category | 23 — API & GraphQL Recon |
| Classification | **active** |
| Integration | cli (`clairvoyance`) |
| Requires key | no |
| Consumes | `live_host, url, endpoint` |
| Produces | `endpoint, finding` |
| Supersedes | — |

## Why it was added

Cat-23 had graphw00f (detection) but no schema-recovery; clairvoyance completes the GraphQL flow.

**Best use.** Map GraphQL attack surface after graphw00f detects an engine.

## Capabilities → typed output files

  - **graphql** → produces `endpoint` → writes `endpoints`
  - **graphql** → produces `finding` → writes `findings`

## Inputs / outputs

- **Consumes:** `live_host, url, endpoint`.
- **Produces:** `endpoint, finding` → normalized to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Typed output:** each capability writes its own file under `artifacts/<scan_id>/by-type/<type>/` so multi-mode output never mixes (see [`docs/arch-v2/03-output-file-contract.md`](../arch-v2/03-output-file-contract.md)).

## Operational behavior

- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **Scope safety:** active tools re-check scope/liveness before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).
