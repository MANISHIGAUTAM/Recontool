# 04 — Scheduler, Frontier Recursion & Deep Loops

## 7. Scheduler design (parallelism, recursion, retries, budgets)

The scheduler runs adapter jobs concurrently **within provider-aware limits**. No evasion:
limits are honored, not circumvented. Five coordinated controls:

```
        ┌──────────────────────────────────────────────────────────────┐
 JOB ─► │ 1. SCOPE+QUOTA ADMISSION   2. CONCURRENCY CAPS                 │
        │ 3. PROVIDER RATE BUCKET    4. CIRCUIT BREAKER   5. BUDGET LEDGER│
        └──────────────────────────────────────────────────────────────┘
```

### 1. Budget ledger (per run, per provider)
Each run starts with a quota budget per provider (`quota_policy.budget_per_run`). Every
admitted job decrements the ledger by its `quota_cost`. When a provider's budget hits 0,
its jobs are **deferred** (not failed) and the planner substitutes an alternate source for
that frontier type. Prevents surprise bills and respects plan limits.

### 2. Concurrency caps (three levels)
```
global_concurrency        # whole-run cap (profile)
per_provider_concurrency  # e.g. github=1, censys=2, brave=2 (from quota_policy)
per_host_concurrency      # for live crawl/validate: be polite to one host
```
Implemented via `asyncio.Semaphore`s; the orchestrator already does L1 (tools/phase) and
L2 (inputs/tool) parallelism (`docs/flow/01-PARALLEL-RECURSIVE-ARCHITECTURE.md`).

### 3. Provider rate buckets (token bucket, per provider)
`net/rate_limiter.py` token buckets keyed by provider enforce `per_minute`/`requests_per_second`.
This is **politeness/quota compliance**, not stealth (no jitter-to-evade, no rotation-to-dodge).

### 4. Circuit breaker (per provider) — **new in `net/circuit.py`**
```
states:  CLOSED ──(failures ≥ threshold in window)──► OPEN ──(cooldown)──► HALF_OPEN
         HALF_OPEN ──(probe ok)──► CLOSED ;  HALF_OPEN ──(probe fail)──► OPEN
while OPEN: fail fast (no calls) -> planner substitutes/declares source unavailable
counts: timeouts, 5xx, repeated 429 after backoff, auth errors
```
Protects the run from a flapping/throttling provider and frees budget for healthy sources.
The AI **recovery advisor** is consulted when a breaker opens (suggest alternate family).

### 5. Retries / backoff
```
retry_on: [429, 5xx, timeout, github_secondary_403]
backoff:  exponential + jitter   # jitter here = thundering-herd avoidance, NOT evasion
max_attempts per adapter (e.g. wayback 4, github 5-long, brave 3)
429 honored: respect Retry-After header when present
```

### Idempotence, resumability, checkpoints
- **Idempotent reads:** `cache_key` — a repeated query returns the cached artifact, no network.
- **Idempotent writes:** `dedupe_key` upserts — re-running converges, never duplicates.
- **Checkpoints:** after each stage, persist `{frontier queue, seen set, budget ledger,
  breaker states, cursor positions}`; a killed run resumes from the last checkpoint.
- **Replay:** re-run normalization over stored raw artifacts without touching the network.

### Job lifecycle
```
plan -> admit(scope,quota,breaker) -> acquire(concurrency,rate) -> fetch
     -> persist raw -> normalize -> upsert graph -> emit frontier delta -> checkpoint
on failure: classify -> retry(backoff) | open breaker | defer(quota) | mark failed+audit
```

---

## Recursion design (Frontier Manager)

A **typed work queue** drives convergence. Re-feed only entities that are **new**,
**in-scope**, and of an **expandable** type.

```
frontier = typed queue ; seen = set(dedupe_key) ; depth per entity ; budget ledger
loop:
  item = frontier.pop()            # prioritized: live_host > subdomain > js_file > url > endpoint
  if item.dedupe_key in seen: continue
  if not scope.contains(item):   continue        # out-of-scope: stored, never expanded
  if depth[item] > MAX_DEPTH or budget_exhausted(): continue
  run the re-feed rule for item.type  -> emits new entities (via corpus builder)
  seen.add(item.dedupe_key)
converge when: frontier empty OR budget exhausted OR depth cap hit
```
Termination is **guaranteed**: dedupe makes `seen` monotonic over a finite in-scope entity
space; depth/budget are hard caps.

### Re-feed rules (the pipeline rules, made executable)

| New entity | Re-checked against → producing | Frontier emits |
|------------|--------------------------------|----------------|
| `subdomain` (new) | CT (CertSpotter/Censys), DNS history (SecurityTrails), passive host indexes (Shodan/urlscan) | `cert`, `ip`, more `subdomain` |
| `cert` SAN (new) | live validation + historical data | `subdomain` (covered names) |
| `live_host` (new) | archive (CDX/CC), live crawl+render, robots/sitemap/manifest, favicon pivot | `url`, `js_file`, `service`, `tech`, `favicon` |
| `url` (new) | live recheck (httpx) + archive presence | `live_host`, `endpoint` |
| `js_file` (new) | endpoints + frames + source_maps + secret-like strings | `endpoint`, `frame`, `websocket`, `source_map`, `finding` |
| `endpoint` (new) | live hosts + archives (does it still respond? historically present?) | `param`, `url` |
| `param`/path pattern (new) | smart-wordlist expansion + param discovery | `endpoint` |
| `favicon` (new) | favicon-hash pivot (Shodan/ZoomEye `http.favicon.hash`) | new `live_host`/`ip` (scope-checked) |

Prioritization keeps the loop **breadth-first on cheap high-signal** (resolve/validate
hosts) before expensive per-URL work, matching "validate live before expensive enrichment".

---

## 8. Crawl / JS / API / parameter-discovery loops

### Crawl loop (live + rendered)
```
for live_host:
  fetch / (HTML); if JS-heavy -> headless render (Playwright)
  parse robots.txt, sitemap.xml, manifest.json   -> seed urls
  extract: a/href, script/src, iframe(frame), websocket(ws/wss), source_map (//# sourceMappingURL)
  CDN/WAF tag -> LOWER concurrency/RPS for this host (tuning, not bypass)
  emit: url, js_file, frame, websocket, source_map  -> frontier
  depth/budget bounded BFS; respect robots; identifiable UA
```

### JS loop
```
for js_file:
  if source_map present -> fetch map -> recover original sources (richer endpoints)
  extract endpoints (path/URL regex + AST where possible)
  extract secret-like strings -> finding (REDACTED: hash+mask+location, never raw)
  emit endpoints -> frontier (live recheck) ; emit frames/websockets discovered in JS
```

### API loop (OpenAPI / Swagger / GraphQL)
```
probe common spec locations: /openapi.json /swagger.json /v3/api-docs /.well-known/...
GraphQL: detect engine (graphw00f-style) -> if introspection enabled, read schema (no mutation/exploit)
parse spec -> endpoints + params + methods -> frontier
findings: exposed spec / introspection-enabled (informational, no exploitation)
```

### Parameter-discovery loop
```
sources of params: query strings (param_miner), forms (input/select names), JS, specs, archives
smart wordlist selection:
  base = harvested paths/params from THIS target
        + tech-specific lists chosen by detected tech (WordPress->wp lists, Java->servlet, etc.)
content discovery (pydirb): wordlist brute with 404/soft-404 CALIBRATION (no bypass)
emit: endpoint, param -> frontier  (feeds back until convergence)
```

### Favicon-hash pivot + archive/search feedback
```
favicon: compute mmh3 hash of live_host favicon -> query Shodan/ZoomEye http.favicon.hash
         -> sibling hosts (same app/org) -> scope-check -> new frontier
archive/search feedback: each NEW host re-queries Wayback/CC + search engines for its OWN
         urls/js (per-host expansion, not just apex) -> deeper corpus each iteration
```

All loops write through the corpus builder → graph → frontier; none pipe directly. Each is
bounded by depth + budget + circuit breakers, and every fetched byte is stored as an
artifact with provenance.
