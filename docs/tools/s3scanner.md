# S3Scanner

> Provenance: extracted_from_spreadsheet · canonical slug `s3scanner` · 2 source row(s).

**Purpose.** Enumerating open S3 buckets. Fast and reliable.

| Field | Value |
|-------|-------|
| Category(s) | AWS S3 Recon, Cloud Storage Recon |
| Classification | **active** (source: Active) |
| Integration | cli |
| Cost | free (Free) |
| Scale | Large |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | High |
| Pipeline position | Cloud & storage recon; Common recon workflow preset |
| Required input | `domain (scope) \| org / domain / keyword` |

## Invocation

```bash
s3scanner <target>   # exact flags: define in config/tools.yaml
```
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain (scope) \| org / domain / keyword` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Very High` (score 0.95). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **If it returns nothing:** treat as empty (valid); do not block chain.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Appears in 2 rows across 2 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 10 | AWS S3 Recon | Active | Free | CLI | Enumerating open S3 buckets | High | Fast and reliable |
| 19 | Cloud Storage Recon | Active | Free | CLI | Enumerating public S3 buckets | Very High | Fast and practical |
