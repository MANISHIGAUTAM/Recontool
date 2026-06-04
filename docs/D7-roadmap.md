# D7 — Phased Build Roadmap

22-week plan, six phases. Effort is in **engineer-weeks (ew)** assuming a small team
(1–2 backend, shared frontend/devops). Each phase ends with a **demoable milestone** and
an **exit criterion** — don't advance until exit criteria pass.

**Critical path:** P0 foundation → P1 passive core → (auth gate) → P2 active core →
P3 intelligence → P4 platform → P5 AI/scale. Frontend can start light in P1 and grow.

```
Week:  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22
P0  ███████
P1        █████████████
P2                    █████████████
P3                                  █████████████
P4                                                █████████████
P5                                                              ███████████
UI        ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░██████████████ (grows)
```

---

## Phase 0 — Foundation (Weeks 1–2) · ~3 ew

**Goal:** a skeleton that can run *one* tool end-to-end through the real architecture.

| Deliverable | Detail | Dep |
|-------------|--------|-----|
| Repo + monorepo layout | Go + Python workspaces, shared schema (D9) | — |
| CI/CD | lint, test, build images, per-tool smoke test lane | repo |
| Docker Compose stack | Postgres(+Timescale), Redis, MinIO, Neo4j, OpenSearch, Temporal | — |
| Config + secrets | Vault (dev mode) + config loader; key-reference pattern | compose |
| Base data models | D3 schema migrations (Postgres); ORM/models in both langs from one source | compose |
| Adapter contract | The pure-adapter interface (ADR-011) + 1 reference adapter (subfinder) | models |
| Scope engine v0 | compiled matcher (CIDR trie + domain suffix), scope tables | models |
| Audit logging v0 | append-only audit writer | models |

- **Milestone:** `observatory scan acme.com` runs subfinder via Temporal, normalizes,
  upserts deduped subdomains to Postgres, logs to audit.
- **Exit criteria:** re-running the same scan creates **zero duplicates**; scope denial
  works; raw output lands in MinIO with a DB pointer.

---

## Phase 1 — Passive Core (Weeks 3–6) · ~6 ew

**Goal:** full passive pipeline (P1–P3 seed + expansion), the lean-budget heart.

| Workstream | Tools/integrations | Notes |
|-----------|--------------------|-------|
| Subdomain enum | subfinder, crt.sh, CertSpotter, Chaos | source attribution + dedupe |
| Passive DNS | SecurityTrails, VirusTotal (throttled) | history → `asset_state` |
| WHOIS/ASN/BGP | BGPView, RIPEstat, ASNmap, IPinfo, Team Cymru | ASN→CIDR expansion + edges |
| Internet search | Shodan(InternetDB free) + Censys + Netlas + GreyNoise | services/certs/CVE candidates |
| Correlation v1 | noisy-OR confidence, entity resolution, edge writing | Postgres + Neo4j projection |
| Bounded recursion | re-feed new in-scope apexes to CT/passive-DNS | depth cap + scope re-check |
| Rate limiting | Redis token buckets per (provider, egress) | + caching layer |
| CLI v1 | `scan`, `status`, `export json` | Cobra |
| UI v0 (light) | asset list + basic graph view | read-only |

- **Milestone:** passive-only scan of a real domain → deduped, scored, enriched asset
  inventory + a Neo4j graph you can pivot, exported as JSON.
- **Exit criteria:** confidence scores reflect multi-source corroboration; ASN→CIDR→IP
  and subdomain→apex edges render in the graph; provider rate limits never tripped in a
  10-domain batch.

---

## Phase 2 — Active Core (Weeks 7–10) · ~6 ew

**Goal:** the authorization gate + Phase-4 live verification.

| Workstream | Tools | Notes |
|-----------|-------|-------|
| **Auth gate (ADR-009)** | scope `active_authorized`, profile binding | CRIT control |
| Egress proxy layer | scan IP pool, per-egress rate buckets, kill switch | OPSEC |
| Resolution | dnsx, puredns(+massdns), dnsvalidator resolvers | wildcard filtering |
| Port scan | naabu → Nmap (`-sV` on found ports) | timing per profile |
| HTTP probe | httpx (status/title/tech/TLS/cdn/hash) | the hub adapter |
| Visual | gowitness | screenshots → MinIO |
| WAF/TLS | wafw00f, sslyze | tags + TLS findings |
| Rate profiles | passive_only/stealth/normal/aggressive wired to all tools | D6 |

- **Milestone:** authorized active scan resolves, port-scans, probes, screenshots, and
  fingerprints live hosts; stealth vs aggressive visibly change behavior.
- **Exit criteria:** worker refuses out-of-scope targets at runtime; `passive_only`
  cannot reach active phases; kill switch halts egress within seconds; egress IP recorded
  per call.

---

## Phase 3 — Intelligence Layer (Weeks 11–14) · ~6 ew

**Goal:** Phase-5 deep enum + Phase-6 vuln surface + correlation depth.

| Workstream | Tools | Notes |
|-----------|-------|-------|
| URL/archive | gau, Wayback CDX | feed httpx verify |
| Crawl | katana (JS-aware) | loop new hosts → P4 |
| Params/JS | ParamSpider, Arjun (active), xnLinkFinder, SecretFinder, Retire.js | |
| Secrets/code | GitHub search, GitLeaks, TruffleHog | redaction enforced |
| Cloud | GrayhatWarfare (passive), cloud_enum, S3Scanner | |
| Detection | nuclei (CVE/misconfig/exposure), Subjack/tko-subs (takeover) | detection-only |
| CVE correlation | NVD + EPSS + Vulners + Shodan CVE → `priority_rank` | the brain |
| Takeover graph | CNAME-dangling detection via Neo4j | |

- **Milestone:** active scan produces severity-tiered, **prioritized** findings
  (takeovers, exposures, known-CVE services) with evidence pointers and dedupe across
  detectors.
- **Exit criteria:** the same finding from two detectors dedupes to one; `priority_rank`
  reflects EPSS×CVSS×exposure; secrets stored redacted only; cloud buckets flagged.

---

## Phase 4 — Platform Layer (Weeks 15–18) · ~6 ew

**Goal:** make it a product: UI, scheduling, reporting, alerts, diffing.

| Workstream | Detail |
|-----------|--------|
| Web dashboard | asset inventory (OpenSearch-backed search/facets), findings triage board, graph explorer (Cytoscape/D3), screenshot gallery |
| **Diff view (ADR-016)** | "what changed since last scan" — new/modified/gone assets & findings |
| Orchestration UX | schedule scans, pause/resume/replay (Temporal signals), job queue visibility |
| Continuous mode | interval re-scan (passive default) + CertSpotter CT webhook trigger |
| Reporting engine | JSON/CSV/Markdown/PDF export; Burp import + Nmap XML output |
| Alerting | new-asset / new-finding → Slack/email/webhook (policy-bounded, D6) |
| AuthN/Z | OIDC SSO + signed API keys + RBAC + multi-workspace (ADR-014) |
| Observability | OpenTelemetry → Prometheus/Grafana/Loki dashboards |

- **Milestone:** a team logs in, schedules continuous monitoring on a scope, and gets
  Slack alerts on newly discovered assets, then exports a client-ready report.
- **Exit criteria:** diff correctly flags a newly added subdomain/port/CVE between two
  runs; RBAC isolates workspaces; report renders cleanly to PDF/Markdown.

---

## Phase 5 — AI + Scale (Weeks 19–22) · ~5 ew

**Goal:** intelligence augmentation + horizontal scale for hundreds of targets.

| Workstream | Detail |
|-----------|--------|
| LLM report generation | self-hosted model default; templated, retrieval over findings; reproducible (prompt/model logged) |
| Risk prioritization model | refine `priority_rank` with learned re-ranker; endpoint risk classifier (rules → DistilBERT) |
| Anomaly detection | Isolation Forest over asset feature vectors (odd port/ASN/tech) |
| Semantic dedupe | embedding similarity second-pass after deterministic dedupe (OpenSearch k-NN) |
| AI-assisted dorking | generate target-specific dorks from discovered tech/naming |
| Scale-out | move from Compose → K8s (HPA on worker pools); partition normalization by workspace; OpenSearch/Neo4j scaling |
| Multi-target / bulk | run flow across hundreds of scopes; fair scheduling; cost guards |
| Team collaboration | finding assignment, comments, status workflow, audit |

- **Milestone:** run continuous monitoring across hundreds of scopes; AI generates an
  exec summary + prioritized list; anomalies auto-flagged; semantic dedupe collapses
  cross-tool duplicate findings.
- **Exit criteria:** AI never introduces assets not in the canonical store; self-hosted
  model path works without external calls; worker pool autoscales under load.

---

## Dependencies & Sequencing Rules

1. **Nothing active before Phase 2's auth gate exists.** Phase 1 ships passive-only.
2. **Correlation/dedupe (P1) precedes detection (P3)** — findings are only as good as the
   asset model under them.
3. **Diff/continuous (P4) depends on `asset_state`** written from P1 onward — so write
   time-series from day one even before the diff UI exists.
4. **AI (P5) depends on a populated canonical store** — it annotates, never sources.
5. **K8s migration is deferred to P5** — don't pay the ops tax before you need scale.

## Effort Summary

| Phase | ew | Cumulative weeks |
|-------|----|------------------|
| P0 Foundation | 3 | 2 |
| P1 Passive core | 6 | 6 |
| P2 Active core | 6 | 10 |
| P3 Intelligence | 6 | 14 |
| P4 Platform | 6 | 18 |
| P5 AI + scale | 5 | 22 |
| **Total** | **~32 ew** | **22 weeks** |

**Earliest useful value:** end of **Phase 1 (week 6)** — a real, deduped, passive asset
inventory with a graph. That alone is shippable for CTI/EASM passive use.
