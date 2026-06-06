# BucketLoot

> Provenance: extracted_from_spreadsheet · canonical slug `bucketloot` · 2 source row(s).

**Purpose.** S3 bucket inspection. Smaller adoption.

| Field | Value |
|-------|-------|
| Category(s) | Bucket Recon, Cloud Bucket Recon |
| Classification | **active** (source: Active) |
| Integration | cli |
| Cost | free (Free) |
| Scale | Medium |
| Reliability / worth | Medium (score 0.6) |
| Data quality (source) | Medium |
| Pipeline position | Cloud & storage recon; Common recon workflow preset |
| Required input | `domain (scope) \| org / domain / keyword` |

## Invocation

```bash
bucketloot <target>   # exact flags: define in config/tools.yaml
```
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain (scope) \| org / domain / keyword` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Medium` (score 0.6). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **If it returns nothing:** treat as empty (valid); do not block chain.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Appears in 2 rows across 2 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 10 | Bucket Recon | Active | Free | CLI | S3 bucket inspection | Medium | Smaller adoption |
| 19 | Cloud Bucket Recon | Active | Free | CLI | Bucket brute forcing | Medium | Less maintained than alternatives |
