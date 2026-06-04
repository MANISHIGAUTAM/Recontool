# Recon Platform — Architecture & Design Dossier

> Codename: **OBSERVATORY** — a self-hostable, modular, API-first reconnaissance and
> External Attack Surface Management (EASM) platform for Bug Bounty, Red Team,
> Penetration Testing, and Threat Intelligence.
>
> **Scope guardrail:** This platform performs reconnaissance and attack-surface
> mapping only. It does **not** perform exploitation. Every active module is gated
> behind explicit scope authorization and rate-limit profiles.

---

## Document Index

| ID | Document | What it answers |
|----|----------|-----------------|
| —    | `README.md` (this file) | Big picture, tech stack (Section 3), AI layer (Section 6) |
| D1   | `D1-tool-matrix.md` | Best tool per job, chaining, redundancy, rate limits |
| D2   | `D2-recon-flow.md` | End-to-end directed flow, phase by phase |
| D3   | `D3-data-schema.md` | Asset / Finding / Relationship / Source data model |
| D4   | `D4-adr.md` | Architecture Decision Records for every major choice |
| D5   | `D5-api-integration.md` | API specs for the top 30 integrations |
| D6   | `D6-opsec.md` | OPSEC + legal controls per phase |
| D7   | `D7-roadmap.md` | Week-by-week build roadmap |
| D8   | `D8-build-vs-buy.md` | Build vs OSS vs Commercial per component |
| D9   | `D9-code-structure.md` | Repository layout and module descriptions |
| D10  | `D10-risk-register.md` | What goes wrong + mitigations |

---

## 1. The One-Paragraph Thesis

You do **not** build a recon platform by reimplementing `subfinder`, `httpx`, or
`nuclei`. Those tools are battle-tested, fast (Go), and maintained by people who do
nothing else. You build the **orchestration, normalization, correlation, storage,
and intelligence layer** *around* them. The differentiator of OBSERVATORY is not
"another scanner" — it is a **deduplicated, time-aware, graph-correlated asset
inventory** with a deterministic workflow engine that can run the same flow across
one target or ten thousand, in stealth or fast mode, and tell you *what changed
since last time*. That last capability — continuous diffing — is what separates a
script collection from a platform.

---

## 2. High-Level Architecture (C4 Level 2)

```
                          ┌─────────────────────────────────────────────┐
                          │                CLIENTS                       │
                          │   CLI (Go)   •   Web UI (Next.js)   •   API   │
                          └───────────────────────┬─────────────────────┘
                                                  │ HTTPS / gRPC
                          ┌───────────────────────▼─────────────────────┐
                          │              API GATEWAY (FastAPI)           │
                          │  AuthN/Z • scope guard • rate-limit • audit  │
                          └───────────────────────┬─────────────────────┘
                                                  │
                ┌─────────────────────────────────┼─────────────────────────────────┐
                │                                 │                                 │
      ┌─────────▼─────────┐          ┌────────────▼───────────┐          ┌──────────▼─────────┐
      │  ORCHESTRATOR     │          │   NORMALIZATION /       │          │  INTELLIGENCE /    │
      │  (Temporal.io)    │          │   CORRELATION ENGINE    │          │  AI LAYER          │
      │  workflows +      │◄────────►│  dedupe • entity        │◄────────►│  classify • rank • │
      │  activities       │          │  resolution • scoring   │          │  summarize         │
      └─────────┬─────────┘          └────────────┬───────────┘          └────────────────────┘
                │                                 │
   ┌────────────▼─────────────┐                   │
   │   WORKER POOL (Go+Py)     │                   │
   │  tool adapters as         │                   │
   │  containerized activities │                   │
   │  subfinder│httpx│nuclei│… │                   │
   └────────────┬─────────────┘                   │
                │ raw output                       │ structured records
                ▼                                  ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │                          STORAGE FABRIC                                │
   │  PostgreSQL (assets/findings) • Neo4j (graph) • OpenSearch (search)    │
   │  MinIO/S3 (raw artifacts, screenshots) • Redis (cache + rate buckets)  │
   └──────────────────────────────────────────────────────────────────────┘
```

**Why this shape:** the orchestrator never talks to the database directly for
business logic — it emits raw results to the normalization engine, which is the
*only* writer of canonical asset/finding records. This single-writer rule is what
makes deduplication tractable. (See D3 and D4.)

---

## 3. Technology Stack Decision (Section 3 answer)

Every choice below is justified. Full ADR treatment is in `D4-adr.md`; this is the
executive summary.

| Layer | Decision | Why (one-liner) | Runner-up |
|-------|----------|-----------------|-----------|
| **Core language** | **Hybrid: Go + Python** | Go for high-throughput tool adapters & the CLI (native ProjectDiscovery ecosystem); Python for orchestration glue, normalization, and AI. | Pure Go (loses ML ecosystem) |
| **API framework** | **FastAPI (Python)** | Async, Pydantic validation = free schema enforcement, OpenAPI out of the box, fastest path to a typed API. | Gin (Go) — faster but more boilerplate for this app |
| **CLI** | **Cobra (Go)** | Single static binary, no runtime deps, matches the tools we shell out to, trivial to distribute to operators. | Typer (Python) — easier but needs an interpreter on host |
| **Frontend** | **Next.js (React)** | SSR for fast initial dashboard loads, huge component ecosystem, easy graph viz integration (Cytoscape/D3), API routes for BFF. | SvelteKit — leaner but smaller hiring/ecosystem pool |
| **Orchestration** | **Temporal.io** | Durable execution: pause/resume/replay, automatic retries, per-activity timeouts, and *exactly* the "long-running, resumable, observable" semantics recon needs. | Prefect (good 2nd); Airflow (wrong tool — it's for scheduled DAGs, not dynamic per-target workflows) |
| **Worker transport** | **Temporal task queues** (no separate broker needed) | Temporal subsumes the queue; avoids running Celery+Redis+broker separately. | Celery+Redis (if you skip Temporal) |
| **Relational store** | **PostgreSQL 16** | Canonical asset/finding system-of-record; JSONB for flexible tool output; rock solid; `pg_trgm` for fuzzy matching during dedupe. | — |
| **Time-series** | **TimescaleDB extension on the same Postgres** | Asset state over time / "what changed" diffing without a second DB. | Dedicated InfluxDB (overkill) |
| **Graph store** | **Neo4j (Community)** | Relationship queries (domain→IP→ASN→org, takeover chains) are first-class; Cypher is readable; great viz. | ArangoDB (multi-model) / Postgres `ltree`+recursive CTEs (cheaper, less ergonomic) |
| **Search** | **OpenSearch** | Full-text + faceted filtering over millions of URLs/endpoints; Apache-2.0 (no Elastic license trap). | MeiliSearch (great DX, weaker at scale/aggregations) |
| **Object store** | **MinIO (S3-compatible)** | Raw tool JSON, screenshots, response bodies; self-hostable, swap to real S3 in cloud with zero code change. | Plain filesystem (no good for multi-node) |
| **Cache / rate buckets** | **Redis** | Per-API token-bucket rate limiting, dedupe bloom filters, hot caches, distributed locks. | — |
| **Containerization** | **Docker Compose (single-node) → Kubernetes (scale-out)** | Compose for solo/team self-host; K8s only when you need horizontal worker autoscaling. Don't pay the K8s tax on day one. | Nomad (lighter than K8s, smaller community) |
| **Secrets** | **HashiCorp Vault** (self-host) / cloud secrets manager when in cloud | 20+ API keys with rotation, lease, and audit; `.env` is fine *only* for local dev. | SOPS+age (simpler, no dynamic secrets) |
| **Monitoring** | **OpenTelemetry → Prometheus + Grafana + Loki** | Vendor-neutral instrumentation; OTel means you can repoint to Datadog later without re-instrumenting. | Datadog (great, but $$ and lock-in) |
| **AuthN/Z** | **OAuth2/OIDC for humans (web), API keys (HMAC-signed) for machines, RBAC scopes throughout** | Humans use SSO; automation uses scoped keys; both flow through the same gateway authorizer. | Plain JWT (fine MVP, weaker for multi-tenant) |
| **Deployment** | **Self-hosted VPS/bare-metal first; cloud-portable via Terraform** | Recon traffic egress IPs matter (OPSEC) and data is sensitive — start where you control egress; keep it cloud-portable. | Pure cloud (convenient, but egress IP reputation & cost risk) |

### Why "hybrid Go + Python" instead of picking one
- **Pure Go** loses you the ML/NLP ecosystem (transformers, scikit, pandas) and makes
  the AI layer painful. It also makes orchestration glue verbose.
- **Pure Python** makes the high-fan-out tool adapters and the distributable CLI slower
  and heavier, and fights the fact that ~80% of the tools you wrap (subfinder, httpx,
  naabu, katana, nuclei, dnsx) are *already Go*.
- **The split:** Go owns the *hot path* (adapters, CLI, anything I/O-bound at fan-out).
  Python owns the *brain* (orchestration workflows, normalization, correlation, AI,
  API). They communicate through Temporal task queues and the storage fabric, never by
  sharing process memory.

---

## 4. Core Design Principles (non-negotiable)

1. **Single-writer canonical store.** Only the normalization engine writes canonical
   `asset`/`finding` rows. Tools write *raw* artifacts to object storage + a raw event
   stream. This is the foundation of reliable dedupe.
2. **Everything is idempotent and replayable.** Re-running a flow must converge, not
   duplicate. Every record carries a deterministic `dedupe_key`.
3. **Time is a first-class dimension.** Assets have `first_seen` / `last_seen` and
   state history. "What changed since the last scan" is a primary product feature, not
   an afterthought.
4. **Scope is enforced at the gateway and the worker.** Two independent checks. A worker
   refuses to touch a host that isn't in an authorized scope, even if asked.
5. **Passive before active, always.** The flow physically cannot run active modules
   until passive seed discovery has produced an authorized, scoped target set.
6. **Adapters are dumb; the platform is smart.** A tool adapter does exactly one thing:
   run tool, capture output, emit normalized events. No correlation logic lives in
   adapters.
7. **Confidence over certainty.** Every asset/finding has a confidence score derived
   from how many independent sources corroborate it.

---

## 5. AI / ML Enhancement Layer (Section 6 answer)

The AI layer is **optional and additive** — the platform is fully functional without
it. It never gates or blocks the deterministic pipeline; it *annotates* it. This is
deliberate: ML false-negatives must never hide a real asset.

| Capability | Approach | Model / Technique | Where it runs |
|------------|----------|-------------------|---------------|
| **Endpoint risk classification** | Classify URLs/endpoints into risk tiers (admin, auth, API, upload, debug, static) | Start: rules + regex + keyword lexicon. Upgrade: fine-tuned small text classifier (DistilBERT) on labeled endpoint corpus | Async, post-normalization |
| **Anomaly detection** | Flag assets that don't fit the target's normal pattern (odd port, unusual ASN, orphan subdomain) | Isolation Forest / DBSCAN over feature vectors (port set, tech stack, geo, ASN) | Batch, nightly |
| **LLM report generation** | Turn structured findings into a plain-English exec summary + technical narrative | LLM (self-hosted Llama-3.x / Mistral for sensitive data, or API model if data classification allows) with strict templated prompts + retrieval over the findings DB | On-demand at report time |
| **Risk prioritization** | Rank findings by exploitability × exposure × asset value | Weighted scoring: EPSS (exploit probability) × CVSS × internet-exposure × asset criticality tag. ML re-ranker later. | Continuous |
| **Pattern recognition across targets** | "This org repeats the same S3 misconfig pattern across 4 subsidiaries" | Frequent-itemset mining (FP-Growth) over finding fingerprints | Batch |
| **AI-assisted dorking** | Generate target-specific Google/GitHub dork queries from discovered tech stack & naming conventions | LLM prompt templated with discovered tech fingerprints + org naming patterns; output validated against a dork grammar | On-demand |
| **Semantic dedupe** | Merge findings that *describe* the same issue but differ textually across tools | Embedding similarity (sentence-transformers) + threshold + human-confirmable merge | Post-normalization, as a second-pass after deterministic dedupe |

### AI layer guardrails
- **Data residency:** if target data is sensitive/contractual, the LLM path defaults to
  a **self-hosted** model. API models are opt-in per workspace, never default.
- **No hallucinated assets:** the LLM only *summarizes and prioritizes* records that
  already exist in the canonical store. It is never a source of assets/findings.
- **Determinism for audit:** prompts, model version, and inputs are logged so any
  AI-generated report is reproducible.

---

## 6. Operating Modes

| Mode | Trigger | Behavior |
|------|---------|----------|
| **CLI** | `observatory scan acme.com --profile stealth` | Runs a flow locally or against the API; streams progress; exports JSON. |
| **API** | `POST /v1/scans` | Programmatic; returns a `scan_id`; poll or webhook for completion. |
| **Web UI** | Dashboard | Visual asset inventory, graph, findings triage, diff view, report export. |
| **Continuous** | Scheduled / cron / CT-log webhook | Re-runs passive flow on an interval; alerts on **new** assets/findings (diff against last state). This is the EASM mode. |

---

## 7. What "done" looks like (MVP definition)

A user runs `observatory scan acme.com --profile stealth` and within minutes gets:
a deduplicated list of live subdomains with IPs/ASNs, HTTP fingerprints + screenshots,
a graph they can pivot, a severity-tiered findings list (takeovers, exposures,
known-CVE services), and an exportable Markdown/JSON report — with **zero** duplicate
entries across the 15+ tools that contributed, and a confidence score on each asset.

See `D7-roadmap.md` for how we get there in phases.
