# D8 — Build vs Buy vs Integrate

The honest framing: **the scanning is solved; the platform is not.** Don't build what
ProjectDiscovery/OWASP already maintain. Don't buy what you can self-host for free at
your scale. *Do* build the connective tissue that no existing tool gives you.

Legend: ✅ recommended · ⚠️ conditional · ❌ avoid

---

## 1. Component-by-Component Decision

| Component | Build | Use OSS | Buy/Commercial | **Recommendation** |
|-----------|:----:|:------:|:-------------:|--------------------|
| Subdomain enumeration | ❌ | ✅ subfinder/amass | — | **Integrate OSS.** Solved problem; just wire keys. |
| DNS resolution/validation | ❌ | ✅ dnsx/puredns/massdns | — | **Integrate OSS.** |
| HTTP probing | ❌ | ✅ httpx | — | **Integrate OSS.** |
| Port scanning | ❌ | ✅ naabu/Nmap | ⚠️ runZero | **Integrate OSS;** runZero only for enterprise asset-mgmt overlap. |
| Vuln detection | ❌ | ✅ nuclei | — | **Integrate OSS.** Templated = auditable. |
| Crawling/JS | ❌ | ✅ katana | — | **Integrate OSS.** |
| Screenshots | ❌ | ✅ gowitness | — | **Integrate OSS.** |
| **Orchestration engine** | ⚠️ glue only | ✅ Temporal | — | **Use Temporal, build the workflows.** Don't build a workflow engine. |
| **Normalization/dedupe** | ✅ | — | — | **BUILD.** This is core IP; nothing does it the way we need. |
| **Correlation/graph model** | ✅ | ⚠️ Neo4j as engine | — | **BUILD model; use Neo4j engine.** |
| **Confidence scoring** | ✅ | — | — | **BUILD.** Differentiator. |
| **Diff / change detection** | ✅ | — | ⚠️ commercial EASM | **BUILD.** The product's reason to exist. |
| Passive DNS data | ❌ | ⚠️ crt.sh free | ✅ SecurityTrails/DNSDB | **Buy data, integrate access.** Quality data is worth paying for. |
| Internet-scan data | ❌ | ⚠️ InternetDB free | ✅ Shodan/Censys | **Freemium → buy credits at scale.** |
| GeoIP/ASN | ❌ | ✅ MaxMind GeoLite | ⚠️ IPinfo paid | **OSS DB; buy IPinfo if you need accuracy/bulk.** |
| Breach/PII data | ❌ | ❌ | ✅ HIBP/Dehashed | **Buy, gate hard** (legal/PII). |
| CVE/exploit intel | ❌ | ✅ NVD/EPSS/OSV | ⚠️ Vulners/VulDB | **OSS feeds; buy Vulners for aggregation.** |
| Search/index | ⚠️ schema only | ✅ OpenSearch | — | **Use OpenSearch.** |
| Object storage | ❌ | ✅ MinIO | ⚠️ S3 in cloud | **MinIO self-host; S3 in cloud.** |
| Secrets mgmt | ❌ | ✅ Vault | ⚠️ cloud SM | **Vault self-host.** |
| Dashboard/UI | ✅ | — | — | **BUILD.** Tailored triage/diff UX is differentiator. |
| Auth/SSO | ❌ | ✅ OIDC libs/Keycloak | ⚠️ Auth0 | **OSS OIDC; Auth0 only if you hate operating Keycloak.** |
| AI/LLM | ⚠️ glue | ✅ self-host Llama/Mistral | ⚠️ API models | **Self-host default; API opt-in.** (ADR-015) |
| Reporting engine | ✅ | ⚠️ template libs | — | **BUILD on template libs.** |

---

## 2. The Existing Recon Frameworks — Integrate or Reinvent?

These are the platforms people compare you to. Verdict on each:

### Amass (OWASP)
- **What it is:** comprehensive subdomain/asset discovery + graph DB.
- **Strength:** deep enumeration, owns its graph model.
- **Verdict:** ⚠️ **Integrate as a tool adapter (passive mode), don't adopt as the
  platform.** Its graph DB is internal and not built to be *your* multi-tenant,
  time-aware system-of-record. Use it for what it's best at (enumeration); feed results
  into our normalization engine.

### BBOT
- **What it is:** modern, modular, recursive recon framework with 100+ modules.
- **Strength:** excellent module ecosystem, recursive "events" model, active+passive.
- **Verdict:** ⚠️ **The closest thing to "don't build it, extend it."** Genuinely
  consider running BBOT as an *engine* behind specific phases and writing its output into
  our store. **But** BBOT is not a multi-tenant, durable-orchestration, RBAC'd,
  graph-correlated *platform* with diffing and a UI — it's a powerful CLI framework.
  - **Incremental value of building our own:** durable/resumable scans across hundreds of
    scopes (Temporal), multi-tenant RBAC, canonical dedupe across *all* sources (not just
    BBOT's), time-aware diffing/EASM, graph pivots, and a triage UI. That's the 80% BBOT
    doesn't give you.
  - **Recommendation:** **Integrate BBOT as one (powerful) source/engine, build the
    platform around it.** Borrow its recursive-event idea; don't reimplement its modules.

### SpiderFoot
- **What it is:** OSINT automation with a huge connector library + a web UI.
- **Verdict:** ⚠️ **Integrate selectively** (it's strong on OSINT/identity connectors,
  CAT-8). Its UI/correlation aren't built for red-team active recon at scale or
  multi-tenant ops. Use modules; don't adopt its core.

### Recon-ng
- **What it is:** modular OSINT recon framework (Metasploit-style workflow).
- **Verdict:** ⚠️ **Borrow ideas, integrate a few modules.** Aging UX; not an
  orchestration platform.

### ReconFTW / Sudomy (bash orchestrators)
- **What they are:** opinionated shell pipelines chaining the same OSS tools.
- **Verdict:** ❌ **Don't adopt; study them.** They're exactly the "script collection"
  this platform replaces with durable orchestration, dedupe, storage, and a UI. Great
  reference for *which tools chain in what order* (we encoded that in D1/D2).

---

## 3. Commercial EASM — Feature Gap Analysis

What the big EASM products do that informs our build (and what we deliberately won't
match on day one):

| Capability | Censys ASM | CyCognito | Mandiant ASM | runZero | Axonius | **Our MVP** |
|-----------|:----------:|:---------:|:------------:|:-------:|:-------:|:-----------:|
| Internet-scan dataset (owned) | ✅ (own scans) | ✅ | ✅ | ⚠️ active | ❌ (aggregator) | ❌ — we *consume* Shodan/Censys data |
| Continuous discovery/diff | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ **(we build this)** |
| Attribution (asset→org confidence) | ✅ | ✅ (strong ML) | ✅ | ⚠️ | ✅ | ⚠️ (confidence scoring v1; ML later) |
| Risk prioritization | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (EPSS×CVSS×exposure) |
| Graph pivoting | ⚠️ | ⚠️ | ⚠️ | ✅ | ✅ | ✅ **(Neo4j)** |
| Bug-bounty/red-team workflow fit | ⚠️ | ❌ | ❌ | ⚠️ | ❌ | ✅ **(our focus)** |
| Self-hostable / data control | ❌ | ❌ | ❌ | ⚠️ | ❌ | ✅ **(differentiator)** |
| Price | $$$$ | $$$$ | $$$$ | $$$ | $$$ | self-host cost |

**Where we win:** self-hostable, red-team/bug-bounty-native workflow, graph pivots,
operator-controlled egress (OPSEC), and we can run *both* passive OSINT and authorized
active recon in one pipeline. **Where we don't compete (and shouldn't try):** owning a
global internet-scan dataset — that costs tens of millions to build; we *consume* Shodan/
Censys/Netlas instead. **Where we're weakest at MVP:** ML-grade attribution confidence —
commercial vendors have years of labeled data; we start with deterministic
multi-source confidence and add ML in P5.

---

## 4. Net Build List (what we actually write code for)

```
BUILD (core IP):
  • Normalization + deterministic dedupe engine
  • Correlation + confidence scoring + entity resolution
  • Graph model + pivot queries (on Neo4j)
  • Time-aware diff / change-detection / continuous EASM
  • Scope engine (2-layer enforcement) + auth gate
  • Tool-adapter framework + per-tool parsers
  • Workflow definitions (on Temporal)
  • Triage UI + graph explorer + diff view + reporting engine
  • Rate-limit/egress/proxy control plane
  • AI annotation layer (classify/rank/summarize) — additive

INTEGRATE (don't reinvent):
  • All scanners: subfinder, dnsx, puredns, httpx, naabu, Nmap, katana,
    nuclei, gowitness, sslyze, gau, GitLeaks/TruffleHog, cloud_enum, etc.
  • Engines: Temporal, Postgres/Timescale, Neo4j, OpenSearch, MinIO, Redis, Vault
  • Optionally: BBOT as a recursive recon engine behind some phases

BUY (data/quality at scale):
  • SecurityTrails (passive DNS + history)
  • Shodan/Censys credits, Netlas
  • HIBP/Dehashed (gated, PII)
  • Vulners (vuln aggregation), IPinfo (IP enrichment) — as budget allows
```

This keeps the lean-start posture (free/OSS first) while reserving paid APIs for the
two places money actually buys an edge: **data quality** and **breach intelligence**.
