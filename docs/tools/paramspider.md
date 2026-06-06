# ParamSpider

> Provenance: extracted_from_spreadsheet · canonical slug `paramspider` · 2 source row(s).

**Purpose.** Mining parameters from archives. Excellent for XSS/SSRF recon.

| Field | Value |
|-------|-------|
| Category(s) | Parameter Discovery |
| Classification | **passive** (source: Passive) |
| Integration | cli |
| Cost | free (Free) |
| Scale | Large |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | High |
| Pipeline position | Historical & archive harvesting; URL/dork/index harvesting |
| Required input | `domain / live_host \| domain / live_host / url` |

## Invocation

```bash
paramspider <target>   # exact flags: define in config/tools.yaml
```
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain / live_host \| domain / live_host / url` (per pipeline position).
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
| 4 | Parameter Discovery | Passive | Free | CLI | Mining parameters from archives | Very High | Excellent for XSS/SSRF recon |
| 6 | Parameter Discovery | Passive | Free | CLI | Finding historical URL parameters | Very High | Excellent for XSS/SSRF testing prep |
