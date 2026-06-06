# MediaInfo

> Provenance: extracted_from_spreadsheet · canonical slug `mediainfo` · 1 source row(s).

**Purpose.** Audio/video metadata extraction. Industry standard for media inspection.

| Field | Value |
|-------|-------|
| Category(s) | Media Metadata Analysis |
| Classification | **passive** (source: Passive) |
| Integration | api, cli, gui |
| Cost | free (Free) |
| Scale | Large |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | High |
| Pipeline position | Metadata & document recon |
| Required input | `file / document / url` |

## Invocation

```bash
mediainfo <target>   # exact flags: define in config/tools.yaml
```
> Also exposes an API. 
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `file / document / url` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Very High` (score 0.95). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 11 | Media Metadata Analysis | Passive | Free | CLI/API/GUI | Audio/video metadata extraction | Very High | Industry standard for media inspection |
