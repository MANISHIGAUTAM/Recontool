# fingerprintx

> Provenance: **recommended_addition** · canonical slug `fingerprintx` · not in the source spreadsheet (closes a real gap).

**Purpose.** Service fingerprinting for NON-HTTP services (databases, RDP, SSH, etc.).

| Field | Value |
|-------|-------|
| Category | 21 — Port Scanning & Service Detect |
| Classification | **active** |
| Integration | cli (`fingerprintx`) |
| Requires key | no |
| Consumes | `service, host_port, ip` |
| Produces | `service, tech` |
| Supersedes | — |

## Why it was added

httpx/whatweb only fingerprint web; non-HTTP services had no dedicated identifier.

**Best use.** Run after naabu/nmap to identify protocol/product on open non-web ports.

## Capabilities → typed output files

  - **fp** → produces `service, tech` → writes `services`

## Inputs / outputs

- **Consumes:** `service, host_port, ip`.
- **Produces:** `service, tech` → normalized to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Typed output:** each capability writes its own file under `artifacts/<scan_id>/by-type/<type>/` so multi-mode output never mixes (see [`docs/arch-v2/03-output-file-contract.md`](../arch-v2/03-output-file-contract.md)).

## Operational behavior

- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **Scope safety:** active tools re-check scope/liveness before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).
