# Creepy

> Provenance: extracted_from_spreadsheet · canonical slug `creepy` · 3 source row(s).

**Purpose.** Geotag intelligence. Niche geolocation use.

| Field | Value |
|-------|-------|
| Category(s) | Geolocation OSINT |
| Classification | **passive** (source: Passive) |
| Integration | cli, gui |
| Cost | free (Free) |
| Scale | Medium |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | High, Medium |
| Pipeline position | Email / username / identity recon; Physical / geo / wireless recon; Social media recon |
| Required input | `bssid / coords / org \| domain / email / person / username \| username / handle / org` |

## Invocation

```bash
creepy <target>   # exact flags: define in config/tools.yaml
```
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `bssid / coords / org \| domain / email / person / username \| username / handle / org` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`High` (score 0.8). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **If it returns nothing:** treat as empty (valid); do not block chain.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Marked deprecated/aging/niche in source notes - keep but verify.
- Appears in 3 rows across 3 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 7 | Geolocation OSINT | Passive | Free | GUI | Geotag intelligence | Medium | Niche geolocation use |
| 8 | Geolocation OSINT | Passive | Free | CLI/GUI | Aggregating geotagged social posts | High | Excellent geo-OSINT utility |
| 15 | Geolocation OSINT | Passive | Free | GUI | Social media geolocation | Medium | Older OSINT utility |
