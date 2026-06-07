# OBSERVATORY Blueprint — Authorized Recon & Attack-Surface Mapping

A single, domain-driven, frontier-recursive pipeline for assets you **own or are
explicitly authorized to test**. It discovers broadly, picks the cheapest high-signal
source per frontier type, merges everything into a canonical graph, stores every raw
artifact with provenance, recurses only on **new in-scope** entities, and produces
diffs, reports, and a graph-ready inventory.

> This blueprint refines the implemented platform in this repo. The biggest policy
> change vs. earlier docs: **authorized-only, no-evasion.** See §Policy below.

## Index

| Doc | Outputs covered |
|-----|-----------------|
| [`01-architecture-and-flow.md`](01-architecture-and-flow.md) | (1) architecture summary · (2) complete flow diagram · (4) stage-by-stage pipeline |
| [`02-source-matrix.md`](02-source-matrix.md) | (3) source family matrix · adapter tool contract · detailed per-family notes |
| [`03-storage-and-corpus.md`](03-storage-and-corpus.md) | (6) storage model (graph + artifacts) · (5) corpus-builder logic · canonical schema |
| [`04-scheduler-recursion-loops.md`](04-scheduler-recursion-loops.md) | (7) scheduler · recursion/frontier · (8) crawl/JS/API/param loops |
| [`05-diff-ai-gaps-roadmap.md`](05-diff-ai-gaps-roadmap.md) | (9) diffing/monitoring · (10) AI supervisor · (11) gaps · (12) roadmap |

## Policy & hard constraints (binding)

1. **Authorized targets only.** A scope policy is loaded before any request; out-of-scope
   entities are stored as intel but never fetched/validated.
2. **No exploitation.** Detection only (e.g., nuclei-style signatures); never weaponize.
3. **No stealth / proxy rotation / rate-limit bypass / detection evasion.** This is the
   key shift from the earlier OPSEC design. We egress transparently with an honest,
   identifiable User-Agent. We respect provider limits rather than circumvent them.
4. **Provider-aware quotas, backoff, caching, concurrency caps, circuit breakers** replace
   evasion as the way we stay within limits and stay reliable.
5. **AI is planner / validator / triage / recovery advisor only.** It never invents
   evidence: every AI-surfaced entity or finding must reference a stored artifact hash;
   the validator rejects any AI claim lacking provenance.

### What this deprecates in the current codebase
- `net/proxy_pool.py` rotation-for-evasion and the `stealth` jitter profile are **reframed
  and deprecated** under this blueprint. They are replaced by:
  - a single, optional, **declared** egress (e.g., a corporate egress IP for allow-listing),
    not a rotating pool used to dodge limits;
  - **provider quota policies + circuit breakers** (`net/circuit.py`, this PR) instead of
    jitter/randomization meant to evade detection.
- Rate **profiles** stay, but their semantics become "politeness / budget", not "stealth".

See `05-diff-ai-gaps-roadmap.md` §Gaps for the migration checklist.
