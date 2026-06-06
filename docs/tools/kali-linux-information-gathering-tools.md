# Kali Linux Information Gathering Tools

> Provenance: extracted_from_spreadsheet · canonical slug `kali-linux-information-gathering-tools` · 1 source row(s).

**Purpose.** Standard pentest recon. Industry standard toolkit.

| Field | Value |
|-------|-------|
| Category(s) | Recon Toolkit |
| Classification | **hybrid** (source: Active/Passive) |
| Integration | cli |
| Cost | free (Free) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | High |
| Pipeline position | Reference index (tool discovery, not executed) |
| Required input | `n/a` |

## Invocation

```bash
kali-linux-information-gathering-tools <target>   # exact flags: define in config/tools.yaml
```
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `n/a` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Very High` (score 0.95). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If the binary is missing:** adapter reports unavailable (graceful skip); install via `docker/install_tools.sh`.
- **If it returns nothing:** treat as empty (valid); do not block chain.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Source rows disagree on passive/active classification; treated as hybrid.
- Reference list/index/framework, not a single executable tool.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 18 | Recon Toolkit | Active/Passive | Free | CLI | Standard pentest recon | Very High | Industry standard toolkit |
