# Photon

> Provenance: extracted_from_spreadsheet · canonical slug `photon` · 3 source row(s).

**Purpose.** Crawling URLs/endpoints. Useful for content discovery.

| Field | Value |
|-------|-------|
| Category(s) | Web Recon, Web Crawling |
| Classification | **active** (source: Active) |
| Integration | cli |
| Cost | free (Free) |
| Scale | Large |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | High, Medium |
| Pipeline position | Frameworks & automation (orchestration); Subdomain discovery & DNS resolution; Web tech fingerprinting & probing |
| Required input | `domain (scope) \| domain / subdomain \| live_host / url` |

## Invocation

```bash
photon <target>   # exact flags: define in config/tools.yaml
```
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain (scope) \| domain / subdomain \| live_host / url` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`High` (score 0.8). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **If it returns nothing:** treat as empty (valid); do not block chain.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Appears in 3 rows across 3 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 2 | Web Recon | Active | Free | CLI | Crawling URLs/endpoints | High | Useful for content discovery |
| 5 | Web Crawling | Active | Free | CLI | Endpoint crawling/discovery | High | Useful content discovery tool |
| 14 | Web Recon | Active | Free | CLI | Web crawling & endpoint discovery | High | Great content discovery tool |
