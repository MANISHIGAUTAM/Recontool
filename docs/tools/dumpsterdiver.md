# DumpsterDiver

> Provenance: extracted_from_spreadsheet · canonical slug `dumpsterdiver` · 2 source row(s).

**Purpose.** Scraping exposed documents/files. Useful for exposed corporate data.

| Field | Value |
|-------|-------|
| Category(s) | Data Leakage Recon, Secret Discovery |
| Classification | **passive** (source: Passive) |
| Integration | cli |
| Cost | free (Free) |
| Scale | Large |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | Medium |
| Pipeline position | Cloud & storage recon; Source-code & secret recon |
| Required input | `org / domain / keyword` |

## Invocation

```bash
dumpsterdiver <target>   # exact flags: define in config/tools.yaml
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

## Caveats

- Appears in 2 rows across 2 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 9 | Data Leakage Recon | Passive | Free | CLI | Scraping exposed documents/files | High | Useful for exposed corporate data |
| 10 | Secret Discovery | Passive | Free | CLI | Extracting secrets from repos/files | High | Good for exposed credential hunting |
