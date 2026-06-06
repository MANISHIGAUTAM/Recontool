# RiskIQ PassiveTotal

> Provenance: extracted_from_spreadsheet · canonical slug `riskiq-passivetotal` · 1 source row(s).

**Purpose.** Enterprise infrastructure mapping. Microsoft-owned enterprise-grade intel.

| Field | Value |
|-------|-------|
| Category(s) | Passive DNS / ASM |
| Classification | **passive** (source: Passive) |
| Integration | unspecified |
| Cost | paid (Paid) |
| Scale | Massive |
| Reliability / worth | Very High (score 0.95) |
| Data quality (source) | Excellent |
| Pipeline position | Seed discovery (internet-wide search) |
| Required input | `domain / org / ip / asn` |

## Invocation

Integration mode not specified in source — classify before wiring.

## Inputs / outputs

- **Consumes:** `domain / org / ip / asn` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`Very High` (score 0.95). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If unavailable / empty:** skip gracefully; never block the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Possibly related (not merged)

RiskIQ Passive DNS

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 1 | Passive DNS / ASM | Passive | Paid | Excellent | Enterprise infrastructure mapping | Very High | Microsoft-owned enterprise-grade intel |
