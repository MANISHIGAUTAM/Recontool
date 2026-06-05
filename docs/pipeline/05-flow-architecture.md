# Flow Architecture — Tool-by-Tool Data Handoffs

This is the concrete, end-to-end design of *which tool runs, what it outputs, and
where that output is fed next*. It is written as a **sample walkthrough** on a fictional
target `xyz.com` with realistic numbers so the fan-out is visible.

> Read this with `03-category-pipelines.md` (per-category detail) and `config/tools.yaml`
> (the machine-readable contract). This doc is the **integration spine** that ties them
> together and is the source of truth for the parallelization/threading work that follows.

---

## 0. The three optimisation principles

Everything below follows three rules. They are the answer to "is this the most optimised?"

1. **Discover wide on the apex, then FAN-OUT per host.**
   Subdomain discovery runs once on the apex (`xyz.com`). *Everything after that* runs
   **per discovered host** — wayback, crawling, dorking, screenshots, port scans all
   iterate over the **N** hosts we found, not just the apex. This is the point that was
   missing: enrichment must consume `subdomain`/`live_host`, not `domain`.

2. **Validate LIVE before you spend.**
   Resolve (`dnsx`) → keep resolving → probe (`httpx`) → keep responding. Only the
   **live** subset flows into expensive enrichment (crawl, screenshot, nuclei). Never
   crawl a dead host.

3. **The DB is the chaining bus.**
   No tool pipes directly to another. Each tool reads its **input artifact type** from
   the canonical store and writes its **output artifact type** back. Between stages we
   re-query the DB. This makes the flow resumable, dedup-correct, and order-independent.

---

## 1. Artifact-type vocabulary (the edges of the graph)

Every handoff is typed. A tool "consumes" one type and "produces" others.

| Artifact type | Meaning | Example |
|---------------|---------|---------|
| `domain` | apex / registrable domain | `xyz.com` |
| `subdomain` | any host under the apex (live or not) | `api.xyz.com` |
| `live_host` | a subdomain that resolves **and** responds on HTTP/S | `https://api.xyz.com` |
| `ip` | resolved IPv4/IPv6 | `93.184.216.34` |
| `cidr` | network range | `93.184.216.0/24` |
| `asn` | autonomous system | `AS15133` |
| `host_port` | open service endpoint | `93.184.216.34:443` |
| `service` | identified service (+product/version) | `nginx 1.18 on :443` |
| `cert` | TLS certificate (+SANs) | sha256:… |
| `url` | a known URL/endpoint | `https://api.xyz.com/v1/login` |
| `js_file` | a JavaScript file saved to disk | `artifacts/js/api.xyz.com/app.js` |
| `param` | a request parameter | `?redirect=` |
| `finding` | vuln / exposure / secret / misconfig | `CVE-2021-23017 on …` |
| `tag` | enrichment label on an existing asset | `mass_scanner`, `waf`, `cdn` |

`live_host` is the new first-class type that makes principle #2 work. (Today the code
uses `subdomain` + the `is_live` flag; promoting it to a real input type is part of the
gap list in §5.)

---

## 2. The sample walkthrough — `xyz.com`

Numbers are illustrative but realistic. Watch the cardinality grow then get filtered.

```
                         seed: xyz.com
                            │  (1 domain)
                            ▼
╔════════════════════════ STAGE 1 — PASSIVE SUBDOMAIN DISCOVERY ════════════════════════╗
║ consume: domain (apex, ×1)            run in PARALLEL                                   ║
║                                                                                        ║
║  subfinder ─┐  crtsh ─┐  certspotter ─┐  chaos ─┐  securitytrails ─┐                    ║
║  hackertarget ─┤  alienvault_otx ─┤  fullhunt ─┤                                       ║
║  shodan(hostname:) ─┤  censys(SAN) ─┤  netlas ─┤  urlscan ─┤  uncover ─┘                ║
║                     │                                                                  ║
║  produce: subdomain (×250)  +  ip (×40)  +  cert (×12)  +  url (×900, urlscan)          ║
╚════════════════════════════════════════╤═══════════════════════════════════════════════╝
                                          │  NORMALIZE+DEDUPE → 250 unique subdomains
                                          ▼
╔════════════════════════ STAGE 2 — RESOLVE & LIVE VALIDATION (active) ══════════════════╗
║ consume: subdomain (×250)             [requires --authorize-active]                    ║
║                                                                                        ║
║  dnsx / puredns(+massdns)  ── resolve + wildcard filter ──►  180 resolve, 95 uniq IP   ║
║        │ produce: ip, cname_to(edge)                                                   ║
║        ▼                                                                                ║
║  httpx  ── probe 180 hosts ──►  120 LIVE web hosts (status/title/tech/tls/hash)        ║
║        produce: live_host (×120) + service + url(roots ×120) + tag(waf/cdn)             ║
╚════════════════════════════════════════╤═══════════════════════════════════════════════╝
                  ┌───────────────────────┼────────────────────────────┐
                  │ (fan-out per LIVE host)│ (fan-out per IP)            │
                  ▼                        ▼                            ▼
╔═══ STAGE 3 — PER-HOST WEB ENRICHMENT ═══╗ ╔═══ STAGE 4 — IP / NETWORK ═══╗
║ consume: live_host (×120) + subdomain   ║ ║ consume: ip (×95), asn        ║
║                                         ║ ║                               ║
║  gau/wayback  per host ─► url (×8,000)   ║ ║  asnmap/bgpview ─► cidr (×14) ║
║  katana crawl per host ─► url (×15,000), ║ ║  internetdb     ─► service,   ║
║                           js_file (×300) ║ ║                     finding   ║
║  gowitness    per host ─► screenshot     ║ ║  greynoise      ─► tag        ║
║  google/bing dork per host ─► url        ║ ║  naabu  per ip  ─► host_port  ║
║  tlsx         per host ─► cert→subdomain ║ ║  nmap   per port─► service    ║
╚══════════════════╤══════════════════════╝ ╚════════════╤══════════════════╝
                   │  new subdomains (from tlsx SANs, JS) │ new ip/cidr
                   └───────────────┬──────────────────────┘
                                   ▼  ⟳ LOOP BACK to Stage 2 (resolve new hosts), bounded
╔════════════════════════ STAGE 5 — DEEP (per URL / per JS) ═════════════════════════════╗
║ consume: url (×23,000), js_file (×300)                                                 ║
║  js_analyze/jsluice per js_file ─► url (hidden endpoints) + finding(secret, redacted)  ║
║  paramspider/arjun  per host    ─► param                                               ║
║  gf classify        per url     ─► url (ssrf/xss/redirect buckets)                      ║
╚════════════════════════════════════════╤═══════════════════════════════════════════════╝
                                          ▼
╔════════════════════════ STAGE 6 — VULN SURFACE & CORRELATION ══════════════════════════╗
║ consume: live_host (×120), url, service(+version)                                      ║
║  nuclei      per live_host/url ─► finding (CVE/misconfig/exposure)                      ║
║  subjack/tko per dangling cname─► finding (takeover)                                    ║
║  sslyze      per host_port:443 ─► finding (tls)                                         ║
║  service+version ─► CPE ─► NVD ─► CVE candidates ─► EPSS rank ─► finding.priority_rank  ║
╚════════════════════════════════════════╤═══════════════════════════════════════════════╝
                                          ▼
                         REPORT / EXPORT / GRAPH / DIFF
```

**The shape to notice:** 1 apex → 250 subdomains → (filter) 120 live → fan-out into
~23k URLs + 300 JS + 95 IPs → deep analysis → findings. Cardinality explodes at Stage 3
precisely **because** enrichment fans out per host. That fan-out is the optimisation.

---

## 3. Master data-handoff table (the A→B→C matrix)

Read each row as: *this tool* consumes *these artifacts* and the artifacts it produces
flow to *those tools*.

| Stage | Tool | Consumes (× cardinality) | Produces | Output feeds → |
|------:|------|--------------------------|----------|----------------|
| 1 | subfinder, crtsh, certspotter, chaos, securitytrails, virustotal, hackertarget, otx, fullhunt, netlas | `domain` ×1 (apex) | `subdomain` | → Stage 2 (resolve) |
| 1 | shodan, censys, uncover | `domain` ×1 | `subdomain`, `ip`, `service` | → S2 resolve, S4 ip-enrich |
| 1 | censys, crtsh | `domain` ×1 | `cert` (+SANs) | → S2 (SAN subdomains) |
| 1 | urlscan | `domain` ×1 | `url`, `ip`, `subdomain` | → S2, S5 (urls) |
| 2 | **dnsx / puredns** | `subdomain` ×N | `ip`, `cname_to` | → S4 ip-enrich, S6 takeover |
| 2 | **httpx** | `subdomain` ×N (resolving) | `live_host`, `service`, `url`(roots), `tag` | → **S3 (per-host enrich)**, S6 |
| 3 | **gau / wayback** | `live_host`/`subdomain` ×L | `url` | → S5 (js/param/gf) |
| 3 | **katana** | `live_host` ×L | `url`, `js_file` | → S5, ⟳ S2 (new hosts) |
| 3 | **gowitness** | `live_host` ×L | `screenshot` | → report/triage |
| 3 | google/bing dork | `live_host` ×L | `url` | → S5 |
| 3 | **tlsx** | `host_port:443` ×L | `cert`, `subdomain`(SAN) | → ⟳ S2 (new subs) |
| 4 | asnmap, bgpview, ripestat | `ip`/`asn` | `cidr` | → S4 (mapcidr→ip), naabu |
| 4 | internetdb, shodan(host) | `ip` ×95 | `service`, `finding`, `subdomain` | → S6 CVE-corr |
| 4 | greynoise | `ip` ×95 | `tag` (mass_scanner) | annotates assets |
| 4 | **naabu** | `ip` ×95 | `host_port` | → nmap, S5/S6 web ports |
| 4 | nmap | `host_port` | `service`(+version) | → S6 CVE-corr |
| 5 | **js_analyze / jsluice** | `js_file` ×300 | `url`, `finding`(secret) | → ⟳ S2/S3 (new urls) |
| 5 | paramspider, arjun | `live_host`/`url` | `param` | → fuzz prep (out of recon scope) |
| 5 | gf | `url` ×23k | `url` (classified) | → triage / S6 |
| 6 | **nuclei** | `live_host`/`url` ×L | `finding` | → report, CVE-corr |
| 6 | subjack, tko-subs | `subdomain` + dangling `cname_to` | `finding`(takeover) | → report |
| 6 | sslyze | `host_port:443` | `finding`(tls) | → report |
| 6 | NVD + EPSS + Vulners | `service`+version → CPE | `finding`(cve, ranked) | → report |

---

## 4. Why this ordering is optimal (data-dependency reasoning)

- **Discovery first, on the apex only** — running subfinder/crtsh per-subdomain would be
  pointless (they already enumerate the whole apex). One pass, maximum recall.
- **Resolve before probe before enrich** — each step *shrinks* the working set
  (250 → 180 → 120), so every later, more-expensive tool processes fewer targets.
- **Enrich per live host** — wayback/katana/dorking yield far more on `api.xyz.com`,
  `admin.xyz.com`, etc. than on the apex alone. This is the n-fan-out you asked about.
- **IP track runs in parallel to the web track** — IPs/ASNs don't depend on URLs, so
  Stage 4 can run concurrently with Stage 3 (see §6).
- **Deep & vuln last** — they need the fullest possible URL/host/service set as input.
- **Bounded loops (⟳)** — tlsx SANs and JS-discovered hosts feed back to Stage 2 once
  (depth-capped) to catch assets the passive sources missed, then stop.

---

## 5. Current implementation vs. this target (the honest gap list)

| # | Target behavior | Current code | Action |
|---|-----------------|--------------|--------|
| G1 | Enrichment (wayback/gau/dorking) fans out **per subdomain/live_host** | `wayback` `consumes=("domain",)` → **apex only** | change `consumes` to `("live_host","subdomain")`; gather those inputs |
| G2 | `live_host` is a first-class input type produced by httpx, consumed by enrichment | only `is_live` boolean flag exists; httpx is in active phase | promote `live_host`; have `_gather_inputs` expose live hosts |
| G3 | Resolve+httpx run **before** web enrichment so we enrich only live hosts | resolve/httpx are P4 (active), wayback is P3 (passive) → wrong order | move a lightweight resolve+probe ahead of enrichment, or restructure stages |
| G4 | Per-IP enrichment (internetdb/greynoise/naabu) fans out over **all** discovered IPs | works (consumes `ip`), but capped at 64 | confirm caps / make configurable |
| G5 | tlsx + JS-discovered hosts loop back into resolution (bounded) | recursion exists but only re-runs passive discovery, not new-host resolution | wire ⟳ edges explicitly |
| G6 | Katana/gowitness/tlsx/dorking adapters exist | only in `config/tools.yaml`, not implemented as adapters | implement adapters (Cat 5/6/13/24) |
| G7 | Within-stage, tools share the same input snapshot (parallel-safe) | ✅ already true | keep |

**Bottom line:** the *bus and dedup are correct*; the *fan-out granularity and
live-first ordering are not yet*. G1–G3 are the high-value fixes that make it "most
optimised."

---

## 6. Parallelization map (tees up the threading/rate-limit work)

This marks **what can run concurrently** vs **what is serialized by a data dependency**.
The actual thread/async + rate-limit design is the *next* document.

```
LEGEND:  ∥ = safe to run in parallel    → = must wait for (data dependency)
```

| Group | Members | Parallel within group? | Depends on |
|-------|---------|--------------------------|------------|
| **PG-1 Discovery** | all Stage-1 passive sources | ✅ fully parallel (independent APIs) | seed |
| **PG-2 Resolve** | dnsx/puredns over N subs | ✅ parallel across hosts (bounded by `dns_qps`) | → PG-1 |
| **PG-3 Probe** | httpx over resolving subs | ✅ parallel across hosts (bounded by `per_host_concurrency`) | → PG-2 |
| **PG-4a Web enrich** | gau, katana, gowitness, dork, tlsx | ✅ parallel across **hosts** AND across **tools** | → PG-3 (live hosts) |
| **PG-4b IP/Net** | asnmap, internetdb, greynoise, naabu→nmap | ✅ parallel; **independent of PG-4a** (runs concurrently) | → PG-2 (IPs) |
| **PG-5 Deep** | js_analyze, paramspider, arjun, gf | ✅ parallel across files/hosts | → PG-4a (urls/js) |
| **PG-6 Vuln** | nuclei, subjack, sslyze, CVE-corr | ✅ parallel across hosts | → PG-3/PG-4b |

**Key concurrency facts for the next design:**
- The **web track (PG-4a)** and the **IP track (PG-4b)** are independent → run them as
  two concurrent sub-pipelines after PG-3.
- The real parallelism is **per-host fan-out**: e.g. `gau` over 120 hosts = 120 tasks.
  This is where a **worker pool + per-target & per-API rate limiting** matters most.
- Cross-cutting limits that the threading design must respect (already have primitives):
  - per-API token bucket (`net/rate_limiter.py`) — shared API keys can't be overrun,
  - per-egress-IP bucket + proxy rotation (`net/proxy_pool.py`) — avoid blacklisting,
  - `RateProfile` (stealth/normal/aggressive) caps global + per-host concurrency, QPS,
    jitter.

**Open questions to resolve in the threading design (next step):**
1. Worker model: asyncio task pool (current) vs. process pool for CPU-bound parsers vs.
   hybrid? (Go adapters are subprocesses; Python parsing is light.)
2. Scheduling unit: per-(tool, host) task with a global semaphore + per-bucket limiter?
3. Backpressure: cap in-flight tasks per stage so a 15k-URL fan-out doesn't OOM.
4. Fairness: round-robin hosts across tools so one slow host doesn't stall the batch.

---

## 7. Next steps (in order)

1. **(this doc)** lock the flow + handoffs. ✅
2. Close **G1–G3**: introduce `live_host`, make enrichment fan out per host, enforce
   resolve→probe→enrich ordering. *(small, high-value)*
3. Implement the missing Stage-3/4/6 adapters (katana, gau, gowitness, tlsx, naabu/nmap,
   nuclei) with atomic checks, category by category.
4. Design & implement the **threading + rate-limiting** layer using the parallelization
   map in §6 (worker pool, per-host fan-out scheduler, backpressure).
5. Load-test with profiles; tune caps.
