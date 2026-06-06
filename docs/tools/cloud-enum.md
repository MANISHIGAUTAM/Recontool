# cloud_enum

> Provenance: extracted_from_spreadsheet · canonical slug `cloud-enum` · 2 source row(s).

**Purpose.** AWS/Azure/GCP asset discovery. Strong general-purpose cloud recon tool.

| Field | Value |
|-------|-------|
| Category(s) | Multi-Cloud Recon, Cloud Enumeration |
| Classification | **hybrid** (source: Hybrid) |
| Integration | cli |
| Cost | free (Free) |
| Scale | Large |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | High |
| Pipeline position | Cloud & storage recon; Common recon workflow preset |
| Required input | `domain (scope) \| org / domain / keyword` |

## Invocation

```bash
cloud-enum <target>   # exact flags: define in config/tools.yaml
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
| 10 | Multi-Cloud Recon | Hybrid | Free | CLI | AWS/Azure/GCP asset discovery | Very High | Strong general-purpose cloud recon tool |
| 19 | Cloud Enumeration | Hybrid | Free | CLI | Multi-cloud exposure discovery | Very High | Excellent for AWS/Azure/GCP recon |
