# Aquatone

> Provenance: extracted_from_spreadsheet · canonical slug `aquatone` · 3 source row(s).

**Purpose.** Visual recon & screenshots. Deprecated but still useful.

| Field | Value |
|-------|-------|
| Category(s) | Screenshot Recon, Visual Recon |
| Classification | **active** (source: Active) |
| Integration | cli |
| Cost | free (Free) |
| Scale | Large |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | High |
| Pipeline position | Subdomain discovery & DNS resolution; Visual recon & screenshotting; Web tech fingerprinting & probing |
| Required input | `domain / subdomain \| live_host / url` |

## Invocation

```bash
aquatone <target>   # exact flags: define in config/tools.yaml
```
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain / subdomain \| live_host / url` (per pipeline position).
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
| 2 | Screenshot Recon | Active | Free | CLI | Visual recon & screenshots | High | Deprecated but still useful |
| 5 | Visual Recon | Active | Free | CLI | Screenshot reconnaissance | High | Deprecated but still widely used |
| 13 | Visual Recon | Active | Free | CLI | Screenshot clustering & recon | High | Deprecated but still popular |
