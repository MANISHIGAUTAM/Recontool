# Goofuzz

> Provenance: extracted_from_spreadsheet · canonical slug `goofuzz` · 2 source row(s).

**Purpose.** Automated Google fuzzing. Niche usage.

| Field | Value |
|-------|-------|
| Category(s) | Google Dork Fuzzer, Search Engine Fuzzing |
| Classification | **passive** (source: Passive) |
| Integration | cli |
| Cost | free (Free) |
| Scale | Medium |
| Reliability / worth | Medium (score 0.6) |
| Data quality (source) | Medium |
| Pipeline position | URL/dork/index harvesting |
| Required input | `domain / live_host / url` |

## Invocation

```bash
goofuzz <target>   # exact flags: define in config/tools.yaml
```
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain / live_host / url` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Medium` (score 0.6). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **If it returns nothing:** treat as empty (valid); do not block chain.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Marked deprecated/aging/niche in source notes - keep but verify.
- Appears in 2 rows across 1 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 4 | Google Dork Fuzzer | Passive | Free | CLI | Automated Google fuzzing | Medium | Niche usage |
| 4 | Search Engine Fuzzing | Passive | Free | CLI | Query fuzzing | Medium | Lesser-known alternative |
