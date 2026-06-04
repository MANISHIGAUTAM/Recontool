# D10 — Risk Register

Risks rated **Likelihood (L)** × **Impact (I)** on Low/Med/High, with a derived
**Severity** and concrete mitigations wired into the architecture. Ordered by severity.
Owners are roles, not people.

| # | Risk | L | I | Severity | Mitigation (and where it's enforced) | Owner |
|---|------|---|---|----------|--------------------------------------|-------|
| R1 | **Out-of-scope scanning** (legal + reputational catastrophe) | Med | High | 🔴 Critical | Two-layer scope enforcement (ADR-008): gateway + per-activity worker re-check; deny-list overrides allow; passive→active hard gate (ADR-009); kill switch; every decision audited (D6). | Platform |
| R2 | **Active recon without authorization** | Med | High | 🔴 Critical | `active_authorized=false` by default; active workflows physically unreachable until set; default profile `passive_only`; authorization crossing audited with actor+scope. | Platform |
| R3 | **Storing raw secrets/credentials** found by scanners | High | High | 🔴 Critical | Secrets persisted as **hash + mask + location only**; raw never in DB/logs/cold storage (D3 §7, D5 #28). Redaction enforced in normalize layer, not adapters. | Normalize |
| R4 | **PII / breach-data mishandling** (GDPR/CCPA exposure) | Med | High | 🔴 Critical | Legal gate on CAT-8 modules; data-minimization; encrypted separate store; shortest TTL; **excluded from cold archive**; every access audited; region-aware defaults (D6 §7). | Legal/Platform |
| R5 | **API costs spiral** (paid credits, cloud egress, LLM tokens) | High | Med | 🟠 High | Freemium-first wiring (D1 default set); aggressive caching (CT/WHOIS/NVD TTLs, D5); per-provider budget caps + alerts; cost guard on bulk/continuous scans; self-hosted LLM default (ADR-015); self-host egress (no surprise cloud egress, ADR-013). | Platform |
| R6 | **API key bans from rate-limit overrun** (shared keys) | High | Med | 🟠 High | Centralized Redis token buckets per (provider, egress-IP) (ADR-010); key rotation pools; exp backoff on 429/403-secondary; GitHub token rotation; auto-bench failing keys (D6 §3). | Platform |
| R7 | **Target-side detection/blocking during active phases** (IDS/WAF, IP ban) | High | Med | 🟠 High | Rate profiles incl. stealth w/ jitter/randomization (D6 §4); dedicated rotating egress pool (never corp IP); sticky-egress option for whitelisted scanners; WAF detection informs throttling. | Operator |
| R8 | **Upstream tool format drift** breaks parsing | High | Med | 🟠 High | Prefer JSON output modes; per-tool parser with **golden-file tests**; pinned tool image digests (ADR-012); CI per-tool smoke lane catches drift before deploy. | Platform |
| R9 | **Duplicate/garbage data** undermines trust in inventory | Med | High | 🟠 High | Deterministic `dedupe_key` + single-writer upsert (ADR-004/011); wildcard filtering (puredns) before downstream; confidence scoring surfaces weak/single-source assets; idempotent replay. | Normalize |
| R10 | **Storage growth** (raw artifacts, screenshots, time-series) | High | Med | 🟠 High | MinIO lifecycle tiering + retention (D3 §8); TimescaleDB downsampling after 90d; raw 30d default; screenshots 90d; Parquet cold archive. Cost dashboards. | Platform |
| R11 | **Legal exposure from breach/exploit framing** | Low | High | 🟠 High | No exploitation tooling (Pacu excluded, Metasploit metadata-only, D1 CAT-7/10); nuclei detection-only; platform scope documented; authorization required and audited. | Legal/Platform |
| R12 | **URLScan/public-submission leaks target** to third parties | Med | Med | 🟡 Medium | Force unlisted/private submissions during engagements (D6 §1); operator warning before public submit. | Operator |
| R13 | **Single point of failure** in normalize engine (bottleneck) | Med | Med | 🟡 Medium | Stateless except DB upserts; horizontally scalable; partition by workspace; backpressure via Temporal; queue buffers raw events (ADR-011). | Platform |
| R14 | **Graph/search projection drift** from canonical store | Med | Low | 🟡 Medium | Outbox pattern + idempotent projectors; projections fully rebuildable from Postgres `asset`+`asset_edge` (ADR-005/006); reconcile job. | Platform |
| R15 | **Temporal/infra operational complexity** | Med | Med | 🟡 Medium | Compose for solo/team; managed escape hatches (Temporal Cloud, RDS, OpenSearch Service) documented; runbooks; defer K8s to P5 (ADR-002/013). | DevOps |
| R16 | **Secret/key leakage from the platform itself** | Low | High | 🟡 Medium | Vault storage; adapters get key *references*; keys never logged; per-workspace key isolation; scoped + individually revocable keys (D6 §3). | Platform |
| R17 | **AI hallucination** introduces phantom assets/findings | Med | Med | 🟡 Medium | AI annotates only; LLM may summarize/prioritize existing records, **never source assets** (ADR-015); deterministic pipeline unaffected; semantic dedupe is human-confirmable. | AI |
| R18 | **Over-reliance on a single data provider** (vendor lock/outage) | Med | Med | 🟡 Medium | Multiple sources per category (D1); subfinder fans out to many; graceful degradation if one provider down; cache cushions outages. | Platform |
| R19 | **Continuous mode silently goes active** without standing authorization | Low | High | 🟡 Medium | Continuous mode re-runs **passive by default**; active continuous requires explicit standing authorization tied to scope; audited (D6 §8). | Platform |
| R20 | **Multi-tenant data bleed** (workspace A sees B) | Low | High | 🟡 Medium | `workspace_id` on every row; RBAC at gateway (ADR-014); per-workspace key isolation; query scoping enforced in `store/`. | Platform |
| R21 | **Wildcard DNS poisons inventory** with infinite junk subdomains | High | Low | 🟢 Low | puredns wildcard detection before persistence (D2 P4.1); dnsvalidator resolver hygiene; confidence down-weights. | Normalize |
| R22 | **Supply-chain compromise of a tool image** | Low | High | 🟢 Low | Digest pinning + image signing; SBOM per image; nightly rebuild + smoke test; minimal base images (ADR-012). | DevOps |

---

## Top-5 "Stop-the-Line" Controls

If these aren't working, **do not run active scans**:

1. **Worker-side scope re-check** (R1) — last line before egress.
2. **Passive→active auth gate defaulting closed** (R2).
3. **Secret redaction in normalize** (R3).
4. **Dedicated egress pool, never corp IP** (R7) + **kill switch**.
5. **PII/breach legal gate + short TTL** (R4).

## Cost Risk — Quick Model

| Driver | Lean start | At scale (100s of targets, continuous) | Lever |
|--------|-----------|-----------------------------------------|-------|
| Paid recon APIs (Shodan/Censys/SecurityTrails) | $0–low (free tiers) | $$$ monthly credits | caching, dedupe before paid calls, budget caps |
| Breach data (HIBP/Dehashed) | per-use | $$ | gate + minimize + only-on-demand |
| LLM | $0 (self-host) | GPU infra OR API tokens | self-host default, batch summaries |
| Storage (MinIO/S3) | low | $$ raw+screenshots+timeseries | lifecycle tiering, retention, downsampling |
| Compute (workers) | 1 VPS | K8s autoscale | profile-based concurrency, fair scheduling |
| Cloud egress | $0 (self-host) | $$ if in cloud | self-host active egress (ADR-013) |

**The single biggest cost lever is dedupe + caching *before* paid API calls** — never
pay twice for the same asset, and never call a paid API for something a free source or a
cached result already answered.
