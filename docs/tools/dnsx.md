# dnsx

> Provenance: extracted_from_spreadsheet · canonical slug `dnsx` · 2 source row(s).

**Purpose.** Fast DNS probing, resolution, validation. One of the best modern ProjectDiscovery tools.

| Field | Value |
|-------|-------|
| Category(s) | DNS Toolkit / Validation, DNS Toolkit |
| Classification | **active** (source: Active) |
| Integration | api, cli |
| Cost | free (Free) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | High |
| Pipeline position | Frameworks & automation (orchestration); Subdomain discovery & DNS resolution |
| Required input | `domain (scope) \| domain / subdomain` |

## Invocation

```bash
dnsx <target>   # exact flags: define in config/tools.yaml
```
> Also exposes an API. 
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain (scope) \| domain / subdomain` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Very High` (score 0.95). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Reference list/index/framework, not a single executable tool.
- Appears in 2 rows across 2 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 2 | DNS Toolkit / Validation | Active | Free | CLI/API | Fast DNS probing, resolution, validation | Very High | One of the best modern ProjectDiscovery tools |
| 14 | DNS Toolkit | Active | Free | CLI/API | DNS probing & validation | Very High | Fast and reliable |
