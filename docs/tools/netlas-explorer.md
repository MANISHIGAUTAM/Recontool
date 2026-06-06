# Netlas Explorer

> Provenance: extracted_from_spreadsheet · canonical slug `netlas-explorer` · 1 source row(s).

**Purpose.** Fast internet search. UI-focused Netlas view.

| Field | Value |
|-------|-------|
| Category(s) | Asset Discovery |
| Classification | **passive** (source: Passive) |
| Integration | unspecified |
| Cost | unknown (n/a) |
| Scale | Large |
| Reliability / worth | High (score 0.8) |
| Data quality (source) | High |
| Pipeline position | Seed discovery (internet-wide search) |
| Required input | `domain / org / ip / asn` |

## Invocation

Integration mode not specified in source — classify before wiring.

## Inputs / outputs

- **Consumes:** `domain / org / ip / asn` (per pipeline position).
- **Produces:** normalized records (subdomains / ips / urls / services / findings as applicable) → mapped to the common schema in [`docs/D3-data-schema.md`](../D3-data-schema.md).
- **Output format (raw):** JSON/JSONL/text per tool; raw stored under `artifacts/<scan_id>/raw/`.

## Operational behavior

- **Confidence / false-positive risk:** worth=`High` (score 0.8). Higher-tier source — still corroborated via multi-source confidence scoring.
- **If unavailable / empty:** skip gracefully; never block the pipeline.
- **Scope safety:** active tools re-check scope before egress; out-of-scope targets are stored but never probed (see `docs/D6-opsec.md`).

## Caveats

- Free/Paid not specified in source.

## Possibly related (not merged)

Netlas, Netlas API, Netlas ASN Search, Netlas Hosts

## Source rows (provenance)

| Section | Category | P/A | Free/Paid | CLI/API | Best use | Worth | Notes |
|---------|----------|-----|-----------|---------|----------|-------|-------|
| 1 | Asset Discovery | Passive |  | Excellent | Fast internet search | High | UI-focused Netlas view |
