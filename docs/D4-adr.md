# D4 — Architecture Decision Records (ADRs)

Format per ADR: **Context → Options → Decision → Rationale → Trade-offs**. These are
the load-bearing decisions; reverse them only with a new ADR.

---

## ADR-001 — Wrap existing tools; do not reimplement scanners

- **Context:** subfinder, httpx, naabu, katana, nuclei, puredns, etc. are mature, fast,
  and maintained. We need breadth (200+ tools) fast.
- **Options:** (a) Reimplement core scanning in our own code; (b) Wrap CLI/API tools as
  orchestrated activities; (c) Fork and embed tool source.
- **Decision:** **(b) Wrap.** Tools run as containerized "activity" adapters; the
  platform owns orchestration/normalization/correlation, not scanning internals.
- **Rationale:** Reimplementing loses years of edge-case handling and falls behind
  upstream. Our value is the *layer above*. Wrapping lets us add a tool in hours.
- **Trade-offs:** We inherit upstream bugs and version drift (mitigate: pin tool
  versions in images, CI smoke tests per tool). Parsing CLI output is brittle (mitigate:
  prefer JSON output modes; per-tool parser with schema tests).

---

## ADR-002 — Temporal.io for orchestration (not Airflow/Celery/n8n)

- **Context:** Recon flows are long-running, dynamic (fan-out depends on discoveries),
  must pause/resume/replay, survive worker crashes, and enforce per-API rate limits.
- **Options:** Airflow, Prefect, Luigi, Celery+Redis, n8n, Temporal.
- **Decision:** **Temporal.io.**
- **Rationale:**
  - *Durable execution*: workflow state is persisted; a crash resumes exactly where it
    left off — critical for hour-long scans.
  - *Dynamic DAGs*: fan-out is decided at runtime from discovered assets (Airflow's
    static DAGs fight this).
  - *Built-in retries/timeouts/heartbeats* per activity — exactly the per-tool
    reliability we need.
  - *Signals/queries*: pause, resume, cancel, and inspect a running scan natively.
  - Subsumes the message broker → fewer moving parts than Celery+Redis+broker.
- **Trade-offs:** Operational weight (Temporal server + its own DB) and a learning
  curve. n8n/Airflow are easier to start but wrong for dynamic, resumable, scoped
  workloads. Mitigation: Temporal has a solid self-host Helm chart / docker-compose and
  managed Temporal Cloud as escape hatch.

---

## ADR-003 — Hybrid Go + Python (not single-language)

- **Context:** ~80% of wrapped tools are Go; AI/normalization wants Python's ecosystem.
- **Options:** Pure Go, Pure Python, Hybrid.
- **Decision:** **Hybrid.** Go = tool adapters + CLI; Python = API, orchestration glue,
  normalization, AI.
- **Rationale:** Right tool per layer. Go's concurrency and static binaries fit the
  fan-out hot path and distributable CLI; Python's libraries fit ML/parsing/glue.
  Temporal has first-class SDKs for *both*, so a Go worker and a Python worker coexist
  on the same task queues.
- **Trade-offs:** Two toolchains, two CI lanes, shared-type duplication (mitigate:
  generate shared models from one JSON-Schema/Protobuf source of truth).

---

## ADR-004 — PostgreSQL as single system-of-record (single-writer)

- **Context:** Dedupe requires one authoritative writer and deterministic keys.
- **Options:** Mongo (schemaless), Postgres, "write everywhere" multi-store.
- **Decision:** **Postgres is the only canonical writer**; Neo4j/OpenSearch are
  *projections* derived from it.
- **Rationale:** ACID upserts on `dedupe_key` make dedupe correct under concurrency.
  JSONB gives schema flexibility for tool-specific attributes without losing relational
  integrity. `pg_trgm` powers fuzzy correlation. TimescaleDB extension adds time-series
  in the same DB.
- **Trade-offs:** Postgres isn't a graph/search engine → we run projections (eventual
  consistency for graph/search). Mitigation: outbox pattern + idempotent projectors;
  graph/search are rebuildable from Postgres at any time.

---

## ADR-005 — Neo4j for relationships (projection, not truth)

- **Context:** Pivot queries (ASN blast radius, CNAME-takeover chains, shared-cert
  pivots) are painful in SQL, natural in a graph.
- **Options:** Postgres recursive CTEs + `ltree`, Neo4j, ArangoDB, Amazon Neptune.
- **Decision:** **Neo4j Community** as a derived projection of `asset_edge`.
- **Rationale:** Cypher expresses multi-hop pivots clearly; visualization tooling is
  mature; analysts think in graphs. Keeping it a *projection* avoids dual-source-of-
  truth problems.
- **Trade-offs:** Community edition lacks clustering/HA (fine until very large scale;
  Enterprise or Neptune if needed). Extra service to operate. Mitigation: graph is
  rebuildable, so its availability is non-critical to data integrity.

---

## ADR-006 — OpenSearch for search (not Elasticsearch, not Meili at scale)

- **Context:** Operators need free-text + faceted search over millions of URLs/assets.
- **Options:** Elasticsearch, OpenSearch, MeiliSearch, Postgres FTS.
- **Decision:** **OpenSearch.**
- **Rationale:** Apache-2.0 (no Elastic SSPL licensing risk for a product we may
  distribute), strong aggregations/faceting at scale, k-NN plugin available for future
  embedding search (semantic dedupe).
- **Trade-offs:** Heavier than MeiliSearch (which has lovely DX but weaker aggregations/
  scale). Postgres FTS alone won't handle the facet/scale needs. Mitigation: start with
  a single OpenSearch node; scale later.

---

## ADR-007 — MinIO/S3 for raw artifacts; DB stores pointers

- **Context:** Raw tool JSON, screenshots, and response bodies are large and rarely
  queried directly.
- **Decision:** **MinIO (S3-compatible)** for blobs; DB rows hold object keys.
- **Rationale:** Keeps Postgres lean and fast; lifecycle policies move cold data
  cheaply; identical API to AWS S3 means zero code change to go cloud.
- **Trade-offs:** Another stateful service on-prem. Mitigation: MinIO is a single binary;
  swap for real S3 in cloud.

---

## ADR-008 — Two-layer scope enforcement (gateway + worker)

- **Context:** Touching out-of-scope hosts is a legal and reputational catastrophe.
- **Options:** Enforce at API only; enforce at worker only; enforce at both.
- **Decision:** **Both.** Gateway validates scan requests; **every worker
  independently re-checks** each target against the scope policy before any active call,
  and refuses + audits on violation.
- **Rationale:** Defense in depth. A bug or a malicious internal call shouldn't be able
  to bypass scope. The worker is the *last line* before packets leave.
- **Trade-offs:** Slight per-activity overhead (a scope check). Worth it. Mitigation:
  scope compiled to a fast matcher (CIDR trie + domain suffix set) cached in Redis.

---

## ADR-009 — Hard authorization gate between passive and active

- **Context:** Passive recon is broadly legal; active recon needs authorization.
- **Decision:** Active phases (4–6) are **physically unreachable** in the workflow until
  `scope_policy.active_authorized = TRUE` and the profile permits it. Default profile is
  `passive_only`.
- **Rationale:** Makes "accidentally scanning without authorization" structurally
  impossible, not just policy. Aligns with the platform's stated non-exploitation scope.
- **Trade-offs:** One more explicit step for operators. That friction is intentional.

---

## ADR-010 — Token-bucket rate limiting in Redis, per (tool, API, egress-IP)

- **Context:** 20+ external APIs each have different limits; bans hurt everyone sharing
  the key.
- **Options:** Naive sleeps; Temporal-side concurrency limits; centralized Redis token
  buckets.
- **Decision:** **Centralized Redis token buckets**, keyed per API *and* per egress IP,
  combined with Temporal activity concurrency caps.
- **Rationale:** Many workers share one API key — only a centralized limiter prevents
  collective overrun. Per-egress-IP buckets support proxy rotation without exceeding
  per-IP limits.
- **Trade-offs:** Redis becomes a critical dependency for active scanning (mitigate:
  Redis HA / graceful degradation to conservative local limits if Redis unreachable).

---

## ADR-011 — Adapters are pure; correlation lives only in the normalization engine

- **Context:** If each adapter does its own dedupe/correlation, logic fragments and
  dedupe breaks.
- **Decision:** Adapters do `run → capture raw → emit normalized events`. **No**
  cross-asset logic in adapters. The normalization engine is the sole place that
  upserts canonical records, resolves entities, and scores confidence.
- **Rationale:** One place to reason about correctness; adapters become trivial and
  uniform; adding a tool can't corrupt the dedupe model.
- **Trade-offs:** Normalization engine is a hotspot/bottleneck candidate (mitigate:
  it's horizontally scalable and stateless except for DB upserts; partition by
  workspace).

---

## ADR-012 — Containerized tool images, versions pinned

- **Context:** Tools have conflicting runtimes; reproducibility and supply-chain matter.
- **Decision:** Each tool ships in its **own pinned container image**; workers invoke
  them via a thin runtime contract (stdin args, stdout JSON, exit codes).
- **Rationale:** Isolation, reproducibility, easy upgrades, supply-chain pinning (digest
  pinning + image signing). A bad tool update can't break others.
- **Trade-offs:** Image sprawl and build maintenance (mitigate: shared base images,
  automated nightly rebuild + smoke test pipeline).

---

## ADR-013 — Self-host first, cloud-portable via Terraform

- **Context:** Recon egress-IP reputation is an OPSEC concern; target data is sensitive.
- **Decision:** Default deployment is **self-hosted (VPS/bare-metal)**; everything is
  IaC (Terraform + Compose/Helm) so it lifts to AWS/GCP/Azure unchanged.
- **Rationale:** Control over egress IPs and data residency; predictable cost; no
  surprise cloud egress bills from large scans. Cloud-portable preserves optionality.
- **Trade-offs:** You operate more yourself. Mitigation: Compose for solo, Helm for
  scale; managed escape hatches (Temporal Cloud, RDS, OpenSearch Service) documented.

---

## ADR-014 — OAuth2/OIDC for humans, signed API keys for machines, RBAC throughout

- **Context:** Multi-user teams + automation + multi-tenant workspaces.
- **Decision:** Humans authenticate via **OIDC SSO**; machines use **HMAC-signed API
  keys** scoped to a workspace+permission set; the gateway authorizer enforces **RBAC**
  on every route.
- **Rationale:** SSO is table stakes for teams; signed keys are revocable and scoped;
  one authorizer keeps policy in one place. Plain JWT works for MVP but RBAC + key
  scoping is needed for real multi-tenant use.
- **Trade-offs:** More setup than a single shared key. Mitigation: ship a sensible
  default single-admin mode for solo users; SSO optional.

---

## ADR-015 — AI layer is additive and non-blocking; self-hosted models default for sensitive data

- **Context:** ML can mislabel; target data can be contractual/regulated.
- **Decision:** AI **annotates**, never gates the deterministic pipeline; LLM defaults
  to **self-hosted** models, API models opt-in per workspace; the LLM may only
  summarize/prioritize existing records (never invent assets).
- **Rationale:** ML false-negatives must not hide assets; sensitive data must not leak
  to third-party model providers by default; reports must be reproducible/auditable.
- **Trade-offs:** Self-hosted models need GPU/infra and are weaker than frontier API
  models. Mitigation: tiered — small self-hosted model default, API model opt-in with
  explicit data-classification acknowledgement.

---

## ADR-016 — Diff engine / continuous monitoring as a first-class feature

- **Context:** The product differentiator is "what changed," not "what exists."
- **Decision:** Every scan writes `asset_state`; a diff engine compares latest vs prior
  and emits `new|modified|gone` events that drive alerts.
- **Rationale:** EASM value is continuous change detection (new subdomain, new open
  port, new CVE). Building time-awareness in from day one is far cheaper than retrofit.
- **Trade-offs:** Storage/compute for historical state (mitigate: TimescaleDB downsample
  + retention policy from D3).
