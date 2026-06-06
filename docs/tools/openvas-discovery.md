# OpenVAS Discovery

> Provenance: extracted_from_spreadsheet · canonical slug `openvas-discovery` · 1 source row(s).

**Purpose.** Enterprise vulnerability discovery. Heavy infrastructure requirement.

| Field | Value |
|-------|-------|
| Category(s) | Vulnerability Discovery |
| Classification | **active** (source: Active) |
| Integration | api, cli |
| Cost | free (Free) |
| Scale | Massive |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | Enterprise |
| Pipeline position | Web tech fingerprinting & probing |
| Required input | `live_host / url` |

## Invocation

```bash
openvas-discovery <target>   # exact flags: define in config/tools.yaml
```
> Also exposes an API. 
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `live_host / url` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`High` (score 0.8). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 5 | Vulnerability Discovery | Active | Free | CLI/API | Enterprise vulnerability discovery | High | Heavy infrastructure requirement |
