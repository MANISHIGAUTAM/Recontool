# smap

> Provenance: **recommended_addition** · canonical slug `smap` · not in the source spreadsheet (closes a real gap).

**Purpose.** nmap-compatible output using Shodan InternetDB data — ports WITHOUT scanning.

| Field | Value |
|-------|-------|
| Category | 21 — Port Scanning & Service Detect |
| Classification | **passive** |
| Integration | cli (`smap`) |
| Requires key | no |
| Consumes | `ip, subdomain, cidr` |
| Produces | `service` |
| Supersedes | — |

## Why it was added

Lets the port-scan category produce results in passive-only mode (no target contact).

**Best use.** Passive port/service picture before (or instead of) active naabu/nmap.

## Capabilities → typed output files

  - **passive-ports** → produces `service` → writes `services`

## Inputs / outputs

- **Consumes:** `ip, subdomain, cidr`.
- **Produces:** `service` → normalized to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Typed output:** each capability writes its own file under `artifacts/<scan_id>/by-type/<type>/` so multi-mode output never mixes (see [`docs/arch-v2/03-output-file-contract.md`](../arch-v2/03-output-file-contract.md)).

## Operational behavior

- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **Scope safety:** active tools re-check scope/liveness before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).
