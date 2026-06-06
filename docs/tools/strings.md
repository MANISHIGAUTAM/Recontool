# strings

> Provenance: extracted_from_spreadsheet · canonical slug `strings` · 1 source row(s).

**Purpose.** Extracting readable strings from binaries. Core DFIR/reversing utility.

| Field | Value |
|-------|-------|
| Category(s) | Binary Analysis |
| Classification | **passive** (source: Passive) |
| Integration | cli |
| Cost | free (Free) |
| Scale | Massive |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | Medium |
| Pipeline position | Metadata & document recon |
| Required input | `file / document / url` |

## Invocation

```bash
strings <target>   # exact flags: define in config/tools.yaml
```
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `file / document / url` (per pipeline position).
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
| 11 | Binary Analysis | Passive | Free | CLI | Extracting readable strings from binaries | High | Core DFIR/reversing utility |
