# Osintgram

> Provenance: extracted_from_spreadsheet · canonical slug `osintgram` · 1 source row(s).

**Purpose.** Instagram investigations. Popular social OSINT tool.

| Field | Value |
|-------|-------|
| Category(s) | Instagram OSINT |
| Classification | **passive** (source: Passive) |
| Integration | cli |
| Cost | free (Free) |
| Scale | Medium |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | Medium |
| Pipeline position | Frameworks & automation (orchestration) |
| Required input | `domain (scope)` |

## Invocation

```bash
osintgram <target>   # exact flags: define in config/tools.yaml
```
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain (scope)` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`High` (score 0.8). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **If it returns nothing:** treat as empty (valid); do not block chain.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 14 | Instagram OSINT | Passive | Free | CLI | Instagram investigations | High | Popular social OSINT tool |
