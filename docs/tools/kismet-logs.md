# Kismet Logs

> Provenance: extracted_from_spreadsheet · canonical slug `kismet-logs` · 1 source row(s).

**Purpose.** Wireless packet analysis. Requires capture infrastructure.

| Field | Value |
|-------|-------|
| Category(s) | Wireless Capture |
| Classification | **active** (source: Active) |
| Integration | cli |
| Cost | free (Free) |
| Scale | Large |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | High |
| Pipeline position | Physical / geo / wireless recon |
| Required input | `bssid / coords / org` |

## Invocation

```bash
kismet-logs <target>   # exact flags: define in config/tools.yaml
```
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `bssid / coords / org` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`High` (score 0.8). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **If it returns nothing:** treat as empty (valid); do not block chain.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 15 | Wireless Capture | Active | Free | CLI | Wireless packet analysis | High | Requires capture infrastructure |
