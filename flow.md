# Recontool — Execution Flow

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              OPERATOR INPUT                                   │
│  recontool scan groww.in --mode live --authorize-active                       │
└─────────────────────┬───────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PREFLIGHT + SCOPE GATE                                │
│  • Validate config (providers.yaml, tools.yaml, categories.yaml)             │
│  • Check mode (demo/test/live) — demo blocks all real egress                 │
│  • Build scope (allow_domains, deny_domains, CIDRs, ASNs)                    │
│  • Verify storage (DB, artifacts dir)                                        │
└─────────────────────┬───────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SOURCE PLANNER                                      │
│  • Load 64 adapters from registry (28 categories)                            │
│  • Filter by: available keys, installed binaries, mode, scope                │
│  • Route by entity type: domain → CAT-1,2,3,4,6,7,8,9,10,16,17             │
│  • Route by entity type: subdomain → CAT-2,5,20,21,22,23,24,25,27          │
│  • Route by entity type: ip → CAT-1,3,12,15,21,24                          │
│  • Route by entity type: url → CAT-5,6,13,20,22,23,25,27                   │
└─────────────────────┬───────────────────────────────────────────────────────┘
                      │
          ┌───────────┴───────────────────────────────────────┐
          │                                                    │
          ▼ (PIPELINE ENGINE)                                  ▼ (EVENT ENGINE)
┌─────────────────────────┐                    ┌──────────────────────────────┐
│  PHASED PIPELINE         │                    │  EVENT-DRIVEN LOOP           │
│  p1_seed (parallel)      │                    │  priority_queue.pop()        │
│  p2_expansion (parallel) │                    │  → dispatch adapters         │
│  p3+p4 (CONCURRENT)      │                    │  → normalize results         │
│  p5_deep (parallel)      │                    │  → emit new events           │
│  p6_vuln (parallel)      │                    │  → loop until convergence    │
└─────────────┬───────────┘                    └──────────────┬───────────────┘
              │                                                │
              └────────────────────┬───────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ADAPTER EXECUTION                                      │
│                                                                              │
│  64 adapters across 28 categories:                                           │
│                                                                              │
│  PASSIVE (no target contact):                                                │
│  ├── CAT-01: alienvault_otx, censys, internetdb, shodan, urlscan + 6 more  │
│  ├── CAT-02: crtsh, subfinder, assetfinder, hackertarget, certspotter + 3  │
│  ├── CAT-03: asnmap, bgpview, ripestat                                      │
│  ├── CAT-04: gau, waybackurls, urlscan_search                              │
│  ├── CAT-06: wayback, waybackurls                                           │
│  ├── CAT-07: email_pattern_enum, hunter_emails                              │
│  ├── CAT-08: social_check, sherlock_social                                  │
│  ├── CAT-09: searchcode_recon, github_code                                  │
│  ├── CAT-10: cloud_bucket_enum, grayhatwarfare                             │
│  ├── CAT-11: http_metadata, doc_metadata                                    │
│  ├── CAT-12: threatfox                                                       │
│  ├── CAT-14: tech_fingerprint, bbot_suite                                   │
│  ├── CAT-15: ip_geo_lookup, wigle_geo                                       │
│  ├── CAT-16: ahmia_onion                                                     │
│  ├── CAT-17: otx_pulse_search, securitytrails_feed                          │
│  ├── CAT-26: app_store_check, apkleaks                                      │
│  └── CAT-28: wordlist_learner                                                │
│                                                                              │
│  ACTIVE (touches target, requires --authorize-active):                       │
│  ├── CAT-02: dns_resolve                                                     │
│  ├── CAT-05: httpx_probe (HTTP fingerprinting + liveness)                   │
│  ├── CAT-13: http_fingerprint (page hash + title)                           │
│  ├── CAT-20: pydirb (directory/content discovery)                           │
│  ├── CAT-21: naabu (port scanning)                                           │
│  ├── CAT-22: pycrawl (web crawling + JS download), katana, js_analyze       │
│  ├── CAT-23: api_endpoint_probe (GraphQL/Swagger detection)                 │
│  ├── CAT-24: tlsx, cero (TLS cert analysis)                                │
│  ├── CAT-25: param_miner                                                    │
│  └── CAT-27: nuclei (vulnerability detection)                               │
└─────────────────────┬───────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NORMALIZE + DEDUPLICATE + STORE                            │
│                                                                              │
│  Normalizer (sole DB writer, batch processing, 2000-event chunks):           │
│  • Canonical value normalization (lowercase, strip dots, normalize IPs)      │
│  • Deterministic dedupe keys (sha1 of canonical form)                        │
│  • Noisy-OR confidence scoring from multiple sources                         │
│  • Provenance tracking (AssetSource per tool sighting)                       │
│                                                                              │
│  Storage destinations:                                                       │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │  DATABASE (recontool.db / PostgreSQL)                               │     │
│  │  • asset (subdomains, IPs, domains — with confidence, provenance)   │     │
│  │  • service (host:port:protocol)                                     │     │
│  │  • endpoint (URLs with status, title, risk_class)                   │     │
│  │  • finding (secrets, vulns — severity, evidence)                    │     │
│  │  • asset_edge (relationships: resolves_to, cname_to, serves)        │     │
│  │  • tool_execution (matrix: entity × tool → status)                  │     │
│  │  • checkpoint, dead_letter, audit_log                               │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │  TEXT FILES (output/<domain>/)                                       │     │
│  │  • subdomains.txt, ips.txt, live_hosts.txt, services.txt            │     │
│  │  • endpoints.txt, findings.txt, edges.txt                           │     │
│  │  • execution_matrix.csv, full_report.json, summary.txt             │     │
│  │  • ai_decisions.txt, ai_summary.txt                                 │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │  RAW ARTIFACTS (artifacts/<scan_id>/)                               │     │
│  │  • raw/<tool>/*.json (provider API responses)                       │     │
│  │  • js/<host>/*.js (downloaded JavaScript files)                     │     │
│  │  • wordlists/tuned-*.txt, regex_packs/tuned-*.json                 │     │
│  └────────────────────────────────────────────────────────────────────┘     │
└─────────────────────┬───────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EXECUTION MATRIX + SCHEDULING                              │
│                                                                              │
│  After normalization, new entities populate the tool_execution matrix:        │
│  ┌───────────────────┬─────────┬───────────┬─────────┬──────────┐          │
│  │ entity            │ crtsh   │ subfinder │ naabu   │ nuclei   │          │
│  ├───────────────────┼─────────┼───────────┼─────────┼──────────┤          │
│  │ groww.in          │ done    │ done      │ done    │ pending  │          │
│  │ api.groww.in      │ -       │ -         │ pending │ pending  │          │
│  │ 104.18.37.214     │ -       │ -         │ done    │ -        │          │
│  └───────────────────┴─────────┴───────────┴─────────┴──────────┘          │
│                                                                              │
│  Status flow: pending → scanning → done/failed/skipped                       │
│  Scheduler picks highest-priority pending → dispatches to worker             │
└─────────────────────┬───────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AI DECISION ENGINE                                         │
│                                                                              │
│  • On adapter error: decides retry/skip/alternative                          │
│  • On phase complete: decides explore_deeper or move_on                      │
│  • Anomaly detection: staging envs, admin endpoints, internal IPs            │
│  • Strategy adjustment: deprioritize failing adapters                        │
│  • Output: ai_decisions.txt + ai_summary.txt                                │
│  • Falls back to deterministic heuristics when no LLM configured             │
└─────────────────────┬───────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    RECURSIVE EXPANSION                                        │
│                                                                              │
│  New discoveries feed back into the pipeline:                                │
│  • New subdomain → DNS resolve → HTTP probe → crawl → JS parse → ...       │
│  • New JS file → download → parse → extract hosts/endpoints → ...           │
│  • New endpoint → fingerprint → param discovery → ...                       │
│  • New IP → port scan → service detect → ...                                │
│  • Continues until convergence (no new unique discoveries)                   │
└─────────────────────────────────────────────────────────────────────────────┘


## Tool Inventory

64 executable adapters (35+ keyless):

| # | Category | Adapters | Type |
|---|----------|----------|------|
| 1 | Internet-Wide Search | alienvault_otx, censys, criminalip, fullhunt, greynoise, internetdb, leakix, netlas, shodan, uncover, urlscan | API |
| 2 | Passive DNS & Subdomain | assetfinder, certspotter, crtsh, dns_resolve, findomain, hackertarget, subdomaincenter, subfinder | CLI+API |
| 3 | WHOIS/ASN/BGP | asnmap, bgpview, ripestat | CLI+API |
| 4 | Search Engine Dorking | gau, gauplus, urlscan_search | CLI+API |
| 5 | Web Tech Fingerprinting | httpx_probe | Python |
| 6 | Historical/Archive | wayback, waybackurls | Python+CLI |
| 7 | Email/Identity | email_pattern_enum, hunter_emails | Python+API |
| 8 | Social Media | social_check, sherlock_social | Python+CLI |
| 9 | Source Code Search | searchcode_recon, github_code | Python+API |
| 10 | Cloud/Storage | cloud_bucket_enum, grayhatwarfare | Python+API |
| 11 | Metadata/Document | http_metadata, doc_metadata | Python+CLI |
| 12 | Threat Intel | threatfox | API |
| 13 | Visual Recon | http_fingerprint, gowitness | Python+CLI |
| 14 | Frameworks | tech_fingerprint, bbot_suite | Python+CLI |
| 15 | Geo/Physical | ip_geo_lookup, wigle_geo | Python+API |
| 16 | Dark Web | ahmia_onion | API |
| 17 | Intel Feeds | otx_pulse_search, securitytrails_feed | Python+API |
| 18 | Living Indexes | osint_index | Local |
| 19 | Workflows | preset_passive | Local |
| 20 | Content Discovery | pydirb | Python |
| 21 | Port Scanning | naabu | CLI |
| 22 | JS Analysis | js_analyze, katana, pycrawl | Python+CLI |
| 23 | API/GraphQL | api_endpoint_probe, graphql_probe | Python+CLI |
| 24 | TLS/Cert | cero, tlsx | CLI |
| 25 | Parameter Discovery | param_miner | Python |
| 26 | Mobile/APK | app_store_check, apkleaks | Python+CLI |
| 27 | Active Vuln Detection | nuclei | CLI |
| 28 | Wordlists/Resources | wordlist_learner | Python |

## Data Flow Per Entity Type

```
DOMAIN (e.g. groww.in):
  → crtsh, subfinder, hackertarget, certspotter → SUBDOMAINS
  → wayback, gau → HISTORICAL URLs
  → asnmap, bgpview → ASN/CIDR
  → email_pattern_enum → EMAILS
  → social_check → SOCIAL PROFILES
  → cloud_bucket_enum → CLOUD BUCKETS
  → searchcode_recon → CODE REFERENCES
  → app_store_check → MOBILE APPS

SUBDOMAIN (e.g. api.groww.in):
  → dns_resolve → IPs
  → httpx_probe → LIVE STATUS + TECH
  → naabu → OPEN PORTS
  → pycrawl → URLs + JS FILES
  → pydirb → HIDDEN PATHS
  → api_endpoint_probe → API ENDPOINTS
  → tlsx → TLS CERTS + SANs
  → nuclei → VULNERABILITIES

IP (e.g. 104.18.37.214):
  → internetdb → PORTS + CVEs
  → ip_geo_lookup → GEOLOCATION
  → greynoise → THREAT CLASSIFICATION
  → naabu → FULL PORT SCAN

URL/ENDPOINT:
  → js_analyze → ENDPOINTS + SECRETS
  → param_miner → PARAMETERS
  → pycrawl → LINKED PAGES + JS
```

## Output Locations

| What | Where | Format |
|------|-------|--------|
| Subdomains | output/<domain>/subdomains.txt | One per line |
| IPs | output/<domain>/ips.txt | One per line |
| Live hosts | output/<domain>/live_hosts.txt | Confirmed alive |
| Services | output/<domain>/services.txt | host:port |
| Endpoints | output/<domain>/endpoints.txt | Full URLs |
| Findings | output/<domain>/findings.txt | [SEVERITY] title |
| Edges | output/<domain>/edges.txt | src → dst (rel) |
| Matrix | output/<domain>/execution_matrix.csv | Entity × Tool status |
| AI decisions | output/<domain>/ai_decisions.txt | Timestamped reasoning |
| AI summary | output/<domain>/ai_summary.txt | Executive summary |
| Full JSON | output/<domain>/full_report.json | Everything structured |
| Raw responses | artifacts/<scan_id>/raw/<tool>/ | Provider JSON |
| JS files | artifacts/<scan_id>/js/<host>/ | Downloaded .js |
| Database | recontool.db | SQLite (all entities) |
