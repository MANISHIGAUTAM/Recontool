# SpiderFoot

> Provenance: extracted_from_spreadsheet · canonical slug `spiderfoot` · 2 source row(s).

**Purpose.** Automated identity recon. One of best OSINT automation platforms.

| Field | Value |
|-------|-------|
| Category(s) | OSINT Automation |
| Classification | **hybrid** (source: Hybrid, Passive) |
| Integration | api, cli, web |
| Cost | freemium (Freemium) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | High |
| Pipeline position | Email / username / identity recon; Frameworks & automation (orchestration) |
| Required input | `domain (scope) \| domain / email / person / username` |

## Invocation

```bash
spiderfoot <target>   # exact flags: define in config/tools.yaml
```
> Also exposes an API. 
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain (scope) \| domain / email / person / username` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Very High` (score 0.95). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Appears in 2 rows across 2 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 7 | OSINT Automation | Hybrid | Freemium | CLI/API | Automated identity recon | Very High | One of best OSINT automation platforms |
| 14 | OSINT Automation | Passive | Freemium | CLI/API/Web | Automated OSINT investigations | Very High | One of the best OSINT automation platforms |
