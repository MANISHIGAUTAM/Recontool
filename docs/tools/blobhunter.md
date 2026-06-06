# BlobHunter

> Provenance: extracted_from_spreadsheet · canonical slug `blobhunter` · 1 source row(s).

**Purpose.** Azure blob storage discovery. Specialized Azure blob hunting.

| Field | Value |
|-------|-------|
| Category(s) | Azure Blob Recon |
| Classification | **active** (source: Active) |
| Integration | cli |
| Cost | free (Free) |
| Scale | Large |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | High |
| Pipeline position | Cloud & storage recon |
| Required input | `org / domain / keyword` |

## Invocation

```bash
blobhunter <target>   # exact flags: define in config/tools.yaml
```
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `org / domain / keyword` (per pipeline position).
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
| 10 | Azure Blob Recon | Active | Free | CLI | Azure blob storage discovery | High | Specialized Azure blob hunting |
