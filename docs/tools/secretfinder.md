# SecretFinder

> Provenance: extracted_from_spreadsheet · canonical slug `secretfinder` · 2 source row(s).

**Purpose.** Finding secrets in JS files. Useful JS-focused scanner.

| Field | Value |
|-------|-------|
| Category(s) | Secret Discovery, JS Secret Discovery |
| Classification | **passive** (source: Passive) |
| Integration | cli |
| Cost | free (Free) |
| Scale | Large |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | High |
| Pipeline position | Source-code & secret recon; URL/dork/index harvesting |
| Required input | `domain / live_host / url \| org / domain / keyword` |

## Invocation

```bash
secretfinder <target>   # exact flags: define in config/tools.yaml
```
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain / live_host / url \| org / domain / keyword` (per pipeline position).
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
| 4 | Secret Discovery | Passive | Free | CLI | Finding secrets in JS files | High | Useful JS-focused scanner |
| 9 | JS Secret Discovery | Passive | Free | CLI | API keys in JavaScript files | Very High | Extremely useful web recon utility |
