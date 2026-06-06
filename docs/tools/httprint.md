# httprint

> Provenance: extracted_from_spreadsheet · canonical slug `httprint` · 1 source row(s).

**Purpose.** Web server fingerprinting. Older legacy utility.

| Field | Value |
|-------|-------|
| Category(s) | HTTP Fingerprinting |
| Classification | **active** (source: Active) |
| Integration | cli |
| Cost | free (Free) |
| Scale | Medium |
| Reliability / worth | Medium (score 0.6) |
| Data quality (source) | Medium |
| Pipeline position | Web tech fingerprinting & probing |
| Required input | `live_host / url` |

## Invocation

```bash
httprint <target>   # exact flags: define in config/tools.yaml
```
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `live_host / url` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Medium` (score 0.6). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **If it returns nothing:** treat as empty (valid); do not block chain.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Marked deprecated/aging/niche in source notes - keep but verify.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 5 | HTTP Fingerprinting | Active | Free | CLI | Web server fingerprinting | Medium | Older legacy utility |
