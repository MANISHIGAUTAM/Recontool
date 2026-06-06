# BlindElephant

> Provenance: extracted_from_spreadsheet · canonical slug `blindelephant` · 1 source row(s).

**Purpose.** Static asset version detection. Older but useful in niche cases.

| Field | Value |
|-------|-------|
| Category(s) | Version Fingerprinting |
| Classification | **active** (source: Active) |
| Integration | cli |
| Cost | free (Free) |
| Scale | Medium |
| Reliability / worth | Niche (score 0.4) |
| Data quality (source) | Medium |
| Pipeline position | Web tech fingerprinting & probing |
| Required input | `live_host / url` |

## Invocation

```bash
blindelephant <target>   # exact flags: define in config/tools.yaml
```
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `live_host / url` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Niche` (score 0.4). Lower-tier source — corroborate with another tool before trusting.
- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **If it returns nothing:** treat as empty (valid); do not block chain.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Marked deprecated/aging/niche in source notes - keep but verify.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 5 | Version Fingerprinting | Active | Free | CLI | Static asset version detection | Niche | Older but useful in niche cases |
