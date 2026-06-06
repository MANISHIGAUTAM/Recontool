# ScoutSuite

> Provenance: extracted_from_spreadsheet · canonical slug `scoutsuite` · 1 source row(s).

**Purpose.** Multi-cloud posture assessment. Excellent reporting and visualization.

| Field | Value |
|-------|-------|
| Category(s) | Cloud Security Auditing |
| Classification | **passive** (source: Passive) |
| Integration | cli |
| Cost | free (Free) |
| Scale | Enterprise |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | Enterprise |
| Pipeline position | Cloud & storage recon |
| Required input | `org / domain / keyword` |

## Invocation

```bash
scoutsuite <target>   # exact flags: define in config/tools.yaml
```
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `org / domain / keyword` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Very High` (score 0.95). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **If it returns nothing:** treat as empty (valid); do not block chain.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 10 | Cloud Security Auditing | Passive | Free | CLI | Multi-cloud posture assessment | Very High | Excellent reporting and visualization |
