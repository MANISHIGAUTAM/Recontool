# 02 — Source Family Matrix, Adapter Contract & Per-Family Notes

## 3. Source family matrix

Mode: **D**=discovery · **C**=context/enrichment · **V**=live. Cost: ●○○ low … ●●● high.
Frontier = the entity types it best produces. Chain = where its output flows.

| Source | Family | Mode | Auth/Quota | Cost | Freshness | Best frontier (output) | Chain → | Redundancy notes |
|--------|--------|:---:|-----------|:---:|-----------|------------------------|---------|------------------|
| **Brave Search API** | search | D | API key, monthly quota | ●○○ | high | `url`, `subdomain` (from results) | corpus→validate | low overlap w/ Mojeek |
| **Mojeek Search API** | search | D | API key, quota | ●○○ | med | `url`, `subdomain` | corpus | independent index |
| **Mojeek Org Search** | search | D | API key | ●○○ | med | org-scoped `url` | corpus | complements Mojeek |
| **SearXNG instance(s)** | search | D | self-host, polite | ●○○ | med | `url`, `subdomain` (meta) | corpus | aggregates; dedupe heavy |
| **Google PSE / CSE JSON** *(plugin)* | search | D | API key, 100/day free | ●○○ | high | `url` | corpus | plugin-only (ToS/quota) |
| **Bing Search** *(legacy plugin)* | search | D | retiring API | ●○○ | high | `url` | corpus | legacy; do not depend on |
| **Censys** | passive | D+C | API id/secret, credits | ●●○ | high | `cert`→`subdomain`, `ip`, `service` | corpus→validate | best cert/SAN pivots |
| **Shodan** | passive | D+C | API key, credits | ●●○ | high | `service`, `ip`, ports, CVE-hint | network/detect | `internetdb` free tier |
| **SecurityTrails** | passive | D+C | API key, plan quota | ●●○ | high | `subdomain`, DNS history | corpus | best passive DNS+history |
| **Chaos (PD)** | passive | D | API key (free) | ●○○ | med | `subdomain` | corpus | great free bug-bounty set |
| **urlscan** | passive | D+C | API key (freemium) | ●○○ | high | `url`, `ip`, `subdomain`, tech | corpus | submit *unlisted* only |
| **CertSpotter** | passive | D | optional key | ●○○ | high | `cert`→`subdomain` | corpus | great for CT monitoring |
| **GreyNoise** | passive | **C only** | API key (freemium) | ●○○ | high | `tag` on `ip` (noise/context) | enrich | **not discovery** |
| **Wayback CDX** | archive | D | none | ●○○ | hist | `url`, `js_file` | corpus→deep | free, huge recall |
| **Common Crawl index** | archive | D | none (bulk) | ●●● | hist | `url` | corpus | run only for unique coverage |
| **GitHub code search** | code | D+C | token, strict 2nd limits | ●●○ | high | `repo`, `endpoint`, secret-hint | corpus→deep | redact secrets |
| **Sourcegraph** | code | D+C | token (freemium) | ●●○ | high | `repo`, `endpoint` | corpus | cross-repo semantic |
| **Live crawl / render** | crawl | D+V | none (our egress) | ●●○ | live | `url`,`js_file`,`endpoint`,`frame`,`websocket`,`source_map`,`param` | deep→frontier | JS-aware render for SPAs |

**Source scoring** (planner uses this; see `04` §scheduler):
```
score = (yield_estimate × freshness_weight × confidence) / (cost_units × redundancy_penalty)
redundancy_penalty rises as overlap with already-queried sources rises (per frontier type)
```

---

## Adapter tool contract (every adapter implements this)

```yaml
adapter:
  name:            string                # unique
  family:          search|passive|archive|code|crawl|context
  input_types:     [domain|subdomain|ip|cidr|asn|url|js_file|cert|repo|...]
  output_types:    [subdomain|url|ip|cert|service|endpoint|js_file|repo|tag|...]
  query_builder:   fn(entity, scope) -> request spec   # how the frontier item becomes a request
  pagination:      none | cursor | offset | page | cdx_resumekey
  batch_support:   bool                  # can it take N inputs per call?
  cache_key:       template              # e.g. "brave:{q}:{page}"  (idempotent reads)
  dedupe_key:      template              # canonical key for emitted entities
  provenance_fields: [source, fetched_at, request, response_sha256, provider, quota_cost]
  quota_policy:    { unit, budget_per_run, per_minute, per_day, concurrency }
  retry_policy:    { max_attempts, backoff: exp_jitter, retry_on: [429,5xx,timeout] }
  failure_modes:   [auth_error, quota_exhausted, empty, schema_drift, timeout, blocked]
  chain_to:        [next frontier types / stages]
```

### Filled examples

**Brave Search (search / discovery)**
```yaml
name: brave_search
family: search
input_types: [domain]
output_types: [url, subdomain]
query_builder: q = f"site:{domain} OR \"{domain}\""   # plus apex + known subs
pagination: offset            # &offset=, capped pages
batch_support: false
cache_key: "brave:{q}:{offset}"
dedupe_key: "url:{canonical_url}"
provenance_fields: [source=brave, fetched_at, request, response_sha256, quota_cost=1]
quota_policy: { unit: query, budget_per_run: 50, per_minute: 20, concurrency: 2 }
retry_policy: { max_attempts: 3, backoff: exp_jitter, retry_on: [429,500,502,503,timeout] }
failure_modes: [auth_error(401), quota_exhausted(429), empty, schema_drift]
chain_to: [corpus -> normalize -> validate]
```

**Censys hosts/certs (passive / discovery+context)**
```yaml
name: censys
input_types: [domain, ip]
output_types: [cert, subdomain, ip, service]
query_builder: certs: names:{domain} ; hosts: services.tls.certificates ...
pagination: cursor
batch_support: false
cache_key: "censys:{index}:{q}:{cursor}"
dedupe_key: "cert:{sha256}" / "ip:{ip}"
provenance_fields: [source=censys, fetched_at, request, response_sha256, quota_cost=credits]
quota_policy: { unit: credit, budget_per_run: 200, per_minute: 10, concurrency: 2 }
retry_policy: { max_attempts: 3, backoff: exp_jitter, retry_on: [429,5xx,timeout] }
failure_modes: [auth_error, quota_exhausted, empty, partial_page]
chain_to: [SAN -> subdomain frontier; ip -> network stage]
```

**Wayback CDX (archive / discovery)**
```yaml
name: wayback_cdx
input_types: [domain, subdomain]
output_types: [url, js_file]
query_builder: "cdx?url=*.{domain}/*&output=json&fl=original,mimetype&collapse=urlkey"
pagination: cdx_resumekey
batch_support: false
cache_key: "wayback:{domain}:{resumekey}"
dedupe_key: "url:{canonical_url}"
provenance_fields: [source=wayback, fetched_at, request, response_sha256, quota_cost=0]
quota_policy: { unit: request, per_minute: 15, concurrency: 2 }   # polite, no key
retry_policy: { max_attempts: 4, backoff: exp_jitter, retry_on: [429,5xx,timeout] }
failure_modes: [timeout(common), empty, ratelimited]
chain_to: [url -> live recheck; *.js -> js_file -> deep loop]
```

**GitHub code search (code / discovery+context)**
```yaml
name: github_code
input_types: [domain, org, keyword]
output_types: [repo, endpoint, finding]   # secrets stored REDACTED
query_builder: "{domain} org:{org}"  + dork list
pagination: page
batch_support: false
cache_key: "ghcode:{q}:{page}"
dedupe_key: "repo:{full_name}" / "finding:{sha1(redacted)}"
provenance_fields: [source=github, fetched_at, request, response_sha256]
quota_policy: { unit: search, per_minute: 10, concurrency: 1 }   # strict secondary limits
retry_policy: { max_attempts: 5, backoff: exp_jitter_long, retry_on: [403_secondary,429,5xx] }
failure_modes: [secondary_rate_limit(403), auth_error, empty]
chain_to: [repo -> clone+secret scan; endpoint -> live recheck]
```

**Live crawl / render (crawl / discovery+live)**
```yaml
name: render_crawl
input_types: [live_host, url]
output_types: [url, js_file, endpoint, frame, websocket, source_map, param]
query_builder: GET url (HTML) ; headless render if JS-heavy
pagination: none (depth/budget bounded BFS)
batch_support: true (host-parallel)
cache_key: "crawl:{canonical_url}"
dedupe_key: "url:{canonical_url}"
provenance_fields: [source=crawl, fetched_at, status, response_sha256]
quota_policy: { unit: request, per_host_concurrency: profile, requests_per_second: profile }
retry_policy: { max_attempts: 2, backoff: exp, retry_on: [5xx,timeout] }
failure_modes: [timeout, render_fail, robots_disallow(respect), oversize]
chain_to: [js_file -> JS mining; new host -> validate; param -> param loop]
```

---

## Detailed per-family notes

### 1) Search engines / metasearch
- **Best for:** indexed `url`s and forgotten files; cheapest broad signal. Use **first**.
- **Brave / Mojeek / Mojeek-Org:** independent indexes → low mutual overlap → run together,
  dedupe by canonical URL. Brave has the freshest crawl; Mojeek-Org is good for org-scoped queries.
- **SearXNG:** meta-aggregator over many engines; **self-host** an instance you control, query it
  politely (it fans out internally). Heavy dedupe needed. Treat as a coverage booster, not a primary.
- **Google PSE/CSE JSON** — **plugin only**: 100 queries/day free, strict ToS; enable per-workspace.
- **Bing** — **legacy plugin only**: the Bing Search API is retiring; keep an adapter for users with
  remaining access but never make it a default dependency.
- **Quota/caching:** all are query-metered → cache by `(engine,q,page)`; the planner caps pages and
  skips engines whose marginal yield (new canonical URLs) drops below a threshold.

### 2) Passive internet indexes
- **Censys:** strongest **cert/SAN** pivots → new subdomains; also hosts/services. Credit-metered.
- **Shodan:** services/ports/banners/CVE-hints; use the **free `internetdb`** per-IP endpoint for
  cheap enrichment, full search only when budget allows. Network/detect chain.
- **SecurityTrails:** best **passive DNS + history** (DNS-history recheck rule). Plan-quota metered.
- **Chaos:** free, high-recall bug-bounty subdomain dataset — run early.
- **urlscan:** `url`/`ip`/tech + historical DOM; **submit only unlisted/private** for authorized work.
- **CertSpotter:** CT issuances → subdomains; ideal for **continuous monitoring** (alert on new certs).
- **GreyNoise:** **context only** — tags an `ip` as internet-background-noise/scanner; never a discovery
  source. Used to annotate, not to expand the frontier.

### 3) Archives & corpora
- **Wayback CDX:** free, enormous historical `url` recall incl. deleted endpoints & old `js_file`s;
  time-rangeable; flaky uptime → cache aggressively, longer backoff.
- **Common Crawl (CDXJ/URL index):** internet-scale; **expensive** to process → planner runs it
  **only** when the redundancy score says it adds unique coverage Wayback/search didn't.

### 4) Code search
- **GitHub code search:** highest-signal for leaked configs/endpoints; **strict secondary rate limits**
  → low concurrency, long backoff, token rotation pool (rotation for *quota*, not evasion). **Secrets
  stored redacted** (hash + mask + location), never raw.
- **Sourcegraph:** cross-repo semantic search for large estates; complements GitHub for private/org code.

### 5) Live crawl / browser render
- **Plain fetch** for static HTML; **headless render** (Playwright/Chromium) for JS-heavy SPAs.
- **Extract:** links, frames, websockets, `source_map`s, `robots.txt`, `sitemap.xml`, `manifest.json`.
- **Mine JS** for endpoints + secret-like strings (redacted).
- **Respect `robots`** for crawl politeness (this is authorized testing of your own assets, but we still
  behave well and identify ourselves). **CDN/WAF-aware tuning** = lower concurrency/RPS when fronted,
  **never** bypass. Source maps, when present, are gold for endpoint/param discovery.
