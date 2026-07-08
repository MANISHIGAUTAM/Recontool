# dnsx-ptr

Reverse-DNS (PTR) sweep variant of [dnsx](dnsx.md) — Batch-12 F5 (opt-in
`horizontal-expansion` family, off by default).

## Purpose
Horizontal expansion: an in-scope IP frequently has a PTR record revealing a hostname —
self-hosted infrastructure or a sibling subdomain not found by forward enumeration.

## Inputs / outputs
- **Input:** `ip` (stdin list, e.g. `1.2.3.4`).
- **Output:** `subdomain` (the PTR hostname, scope-filtered so only in-scope names enter
  the graph). Raw JSONL under `artifacts/<scan_id>/raw/dnsx-ptr/`.

## Invocation
`dnsx -ptr -resp-only -json -silent` (reads IPs from stdin). Binary: `dnsx`.

## Pipeline position
Stage: ip → reverse-DNS enrichment. Passive. Off by default; opt-in via the
`horizontal-expansion` profile. Discovered in-scope hostnames re-enter the subdomain
pipeline (recursion source).
