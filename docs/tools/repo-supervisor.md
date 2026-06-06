# Repo-supervisor

> Provenance: extracted_from_spreadsheet · canonical slug `repo-supervisor` · 2 source row(s).

**Purpose.** Monitoring repo leaks. Niche monitoring utility.

| Field | Value |
|-------|-------|
| Category(s) | Repo Monitoring |
| Classification | **passive** (source: Passive) |
| Integration | api, cli |
| Cost | free (Free) |
| Scale | Large |
| Reliability / worth | Medium (score 0.6) |
| Data quality (source) | Medium |
| Pipeline position | Source-code & secret recon; URL/dork/index harvesting |
| Required input | `domain / live_host / url \| org / domain / keyword` |

## Invocation

```bash
repo-supervisor <target>   # exact flags: define in config/tools.yaml
```
> Also exposes an API. 
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain / live_host / url \| org / domain / keyword` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Medium` (score 0.6). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Marked deprecated/aging/niche in source notes - keep but verify.
- Appears in 2 rows across 2 section(s); all memberships preserved.

## Possibly related (not merged)

repo-analyzer, repo-security-scanner

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 4 | Repo Monitoring | Passive | Free | CLI/API | Monitoring repo leaks | Medium | Niche monitoring utility |
| 9 | Repo Monitoring | Passive | Free | CLI/API | Repo policy monitoring | Medium | More DevSecOps than recon |
