# subfinder

> Provenance: extracted_from_spreadsheet · canonical slug `subfinder` · 3 source row(s).

**Purpose.** Automated passive enumeration. Industry standard for passive recon.

| Field | Value |
|-------|-------|
| Category(s) | Subdomain Enumeration, Passive Enumeration |
| Classification | **passive** (source: Passive) |
| Integration | api, cli |
| Cost | free (Free) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | High |
| Pipeline position | Common recon workflow preset; Frameworks & automation (orchestration); Subdomain discovery & DNS resolution |
| Required input | `domain (scope) \| domain / subdomain` |

## Invocation

```bash
subfinder <target>   # exact flags: define in config/tools.yaml
```
> Also exposes an API. 
> CLI flags are a placeholder — confirm against the installed tool version pinned in `docker/install_tools.sh`.

## Inputs / outputs

- **Consumes:** `domain (scope) \| domain / subdomain` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Very High` (score 0.95). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If it rate-limits / errors:** exponential backoff + retry; rotate API key from pool; on repeated 401/403 disable for the run and audit.
- **If it returns nothing:** record an empty result with provenance (not a failure); continue the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Appears in 3 rows across 3 section(s); all memberships preserved.

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 2 | Subdomain Enumeration | Passive | Free | CLI/API | Automated passive enumeration | Very High | Industry standard for passive recon |
| 14 | Passive Enumeration | Passive | Free | CLI/API | Passive subdomain enum | Very High | Must-have recon tool |
| 19 | Subdomain Enumeration | Passive | Free | CLI/API | Fast passive subdomain discovery | Very High | Industry-standard passive recon tool |
