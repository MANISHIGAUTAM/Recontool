# Plan of Action — Category Pipelines & Integration

This document is the master plan for turning the tool list into a working, integrated
recon engine. It defines **how a category pipeline works**, **how tools chain
(A → B → C)**, **how categories integrate**, and the **atomic-check methodology** we use
to validate every tool before wiring it in.

---

## 1. Mental Model

```
        SCOPE DOMAIN (e.g. www.xyz.com)
                  │
                  ▼
   ┌──────────────────────────────────────────────────────────┐
   │  A "category pipeline" = an ordered chain of tool stages   │
   │  where each stage CONSUMES a typed artifact and PRODUCES   │
   │  a typed artifact, all writing into the shared DB + FS.    │
   └──────────────────────────────────────────────────────────┘
                  │
                  ▼
   Category 1 pipeline ─┐
   Category 2 pipeline ─┤   each runs independently first (this phase),
   Category 3 pipeline ─┤   then we INTEGRATE them via the shared data bus
   ...                  ─┘   (the canonical DB) later.
```

**Two-phase build strategy (your instruction):**
1. **Now — build each category as a standalone pipeline.** Each category has a clear
   input contract (usually: a domain or a list of assets) and writes normalized records
   to the DB. We validate each in isolation with atomic checks.
2. **Later — integrate categories** by letting one category's DB output become another's
   input (the orchestrator already does this via `_gather_inputs`). The shared canonical
   store (`docs/D3-data-schema.md`) is the integration bus — categories never call each
   other directly; they read/write the DB.

---

## 2. How Tools Chain (A → B → C)

Every tool is described in `config/tools.yaml` by a **contract**:

```
tool:
  input:   <artifact type it consumes>     # domain | subdomain | ip | cidr | url | js_file | host:port
  output:  <artifact type it produces>     # subdomain | ip | url | service | finding | ...
  invocation: <how to run it>              # cli template | api endpoint | python call
  output_format: json | jsonl | text | xml
```

The orchestrator chains tools by **matching output types to input types**:

```
   subfinder            crt.sh             dnsx/puredns         httpx              katana
  ┌──────────┐        ┌──────────┐        ┌────────────┐      ┌──────────┐      ┌──────────┐
  │ in: domain│        │in: domain│        │in: subdomain│      │in:subdom │      │ in: url  │
  │out: subdom│───┐    │out:subdom│───┐    │out: ip      │──┐   │out: url  │──┐   │ out: url │
  └──────────┘   │    └──────────┘   │    │  live flag  │  │   │  service │  │   └──────────┘
                 ▼                   ▼    └────────────┘  │   └──────────┘  │
            ┌─────────── NORMALIZE + DEDUPE (DB) ────────────────────────────┐
            │   merge subdomains, attach sources, score confidence            │
            └─────────────────────────────────────────────────────────────────┘
                 │  the DB is re-queried to feed the NEXT stage's input
                 ▼
            (chaining is data-driven, not hardcoded)
```

**Key principle:** tools don't pipe to each other directly (brittle). Each tool writes
to the DB; the next stage reads the DB. This makes the pipeline **resumable,
deduplicated, and order-independent** — you can add/remove a tool without rewiring.

For raw throughput inside a stage (e.g. `subfinder | anew | dnsx | httpx`), we *also*
support classic Unix-style streaming for the hot path, but the **source of truth is
always the DB**.

---

## 3. The Generic Category Pipeline Shape

Every category pipeline implements the same lifecycle:

```
   1. PLAN     → which tools in this category are available + in budget (AI/heuristic)
   2. FAN-OUT  → run independent discovery tools in PARALLEL on the input
   3. COLLECT  → gather raw outputs to filesystem (artifacts/)
   4. NORMALIZE→ parse each tool's output into typed events
   5. DEDUPE   → upsert into DB with deterministic keys + confidence
   6. CHAIN    → feed enriched output to the next stage (within or across categories)
   7. REPORT   → expose results (CLI table / JSON / DB)
```

This is already implemented generically in `recontool/orchestrator/pipeline.py`; a
"category pipeline" is just the set of adapters registered to that category's phase.

---

## 4. Atomic-Check Methodology (how we validate each tool)

Before a tool is trusted in the pipeline, it passes **atomic checks** — small,
isolated tests proving the adapter works end-to-end. For each tool:

| Check | Question | How |
|-------|----------|-----|
| **C1 Availability** | Is the tool installed / key present? | `adapter.available(ctx)` returns True |
| **C2 Invocation** | Does it run without crashing on a known input? | run against a safe test domain (e.g. `example.com` / `hackerone.com`) |
| **C3 Parse** | Do we parse its output into the right event type? | golden-file test: fixture output → expected events |
| **C4 Normalize** | Do events upsert correctly + dedupe? | run twice → assert zero duplicates, confidence rises |
| **C5 Scope** | Does it respect scope (no out-of-scope egress for active tools)? | scope-deny test asserts refusal + audit row |
| **C6 Chain** | Does its output feed the next stage's input type? | type-match assertion against the registry |

Each adapter ships with a `tests/atomic/test_<tool>.py` covering C3-C4 at minimum
(offline, fixture-based) and an optional live smoke test (C2) behind a network flag.

**Definition of done for a tool:** C1, C3, C4, C6 pass offline; C2 passes in a live
smoke run; active tools additionally pass C5.

---

## 5. Integration Roadmap (category build order)

We build in the order that maximizes downstream value (each unlocks inputs for the next):

```
WAVE 1 — Passive foundation (start HERE, per your instruction)
  Cat 2  Passive DNS & Subdomain Enum     ← produces the asset universe
  Cat 1  Internet-Wide Search & Assets    ← enriches with exposed services
  Cat 3  WHOIS/ASN/BGP                     ← expands to IP ranges/orgs
  Cat 6  Historical & Archive             ← harvests URLs/JS

WAVE 2 — Active verification
  Cat 21 Port Scanning (new)               ← live ports
  Cat 5  Web Tech Fingerprinting + httpx   ← live web + tech
  Cat 24 TLS/Cert Analysis (new)           ← cert pivots + TLS findings
  Cat 13 Visual Recon / Screenshots        ← triage at a glance

WAVE 3 — Deep web recon
  Cat 20 Content & Directory Discovery (new)
  Cat 22 JavaScript Analysis (new)
  Cat 25 Parameter Discovery (new)
  Cat 23 API & GraphQL Recon (new)
  Cat 4  Dorking & Index

WAVE 4 — Intelligence overlays (run anytime, enrich)
  Cat 9  GitHub/GitLab/Source-Code
  Cat 10 Cloud & Storage
  Cat 7  Email/Identity   Cat 8 Social   Cat 11 Metadata
  Cat 12 Malware/IOC/Threat Intel   Cat 17 APIs/Feeds

WAVE 5 — Specialized (scope-dependent)
  Cat 15 Geo/Wireless   Cat 16 Dark Web   Cat 18 Indexes
```

> **Note on Cat 19 (Common Recon Workflows):** this isn't a real category — it's a
> *preset* that stitches Cat 1/2/3/6 + the active waves into a one-command flow. We model
> it as a named pipeline preset, not a tool set.

---

## 6. What "invoked by a scope domain" means

The whole platform is driven by a single entrypoint:

```
recontool scan www.xyz.com                      # runs the default passive preset
recontool scan www.xyz.com --category 2          # run ONLY category 2 pipeline
recontool scan www.xyz.com --category 1,2,3      # run several categories (--wave grouping: planned)
recontool scan www.xyz.com --authorize-active    # unlock active waves
```

The seed domain is normalized once (`core/scope.py`), a scope is built, and every
category pipeline receives the same `AdapterContext`. No per-tool config needed at
runtime — all tool behavior comes from `config/tools.yaml` + the rate profile.

---

## 7. Immediate next step (Category 1, atomic)

Per your plan, after this scaffolding lands we will:
1. Implement/verify each **Category 1** (Internet-Wide Search) adapter:
   `uncover` (wraps Shodan/Censys/FOFA/ZoomEye/Netlas), `shodan`, `censys`, `netlas`,
   `greynoise`, `leakix`, `fullhunt`, `urlscan`, `criminalip`.
2. Write **atomic checks** (C3/C4 offline + C2 live smoke) for each.
3. Validate chaining: Cat 1 output (IPs, services, certs) → feeds Cat 3 (ASN) and Cat 21
   (ports) and Cat 5 (httpx).

The deliverables in this PR set up everything needed to do that cleanly.
