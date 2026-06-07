# 03 — Storage Model (Graph + Artifacts) & Corpus-Builder Logic

## 6. Storage model

Two stores, linked by hashes + provenance. **Raw bytes** never live in the graph; the
graph holds **normalized entities** that point at artifacts by `sha256`.

```
   adapter output ──┬─► RAW ARTIFACT STORE (content-addressed)
                    │      key = sha256(bytes) ; immutable ; never edited
                    │      meta: source, fetched_at, request, provider, quota_cost, mime
                    │
                    └─► NORMALIZER (single writer) ─► CANONICAL GRAPH (entities + edges)
                                                       each entity links: provenance[] -> artifact sha256
```

### 6a. Raw artifact store (content-addressed)

```
artifacts/<workspace>/<scan_id>/
  raw/<sha256[0:2]>/<sha256>.{json|html|js|bin}     # immutable response bodies
  js/<host>/<sha256>.js                              # harvested JS (also addressed by hash)
  screenshots/<sha256>.png
  source_maps/<sha256>.map
  meta/<sha256>.json     # { source, url, fetched_at, status, request, provider, quota_cost, mime }
```
Properties: **immutable**, **deduplicated by content** (same bytes from two sources = one
blob, two provenance rows), **idempotent** (re-fetch with same `cache_key` skips network),
**replayable** (a run can be re-normalized from raw without re-fetching).

### 6b. Canonical graph — typed entities (nodes)

All 22 required types are first-class nodes. Each node: `id`, `type`, `value`,
`dedupe_key`, `attributes{}`, `tags[]`, `confidence`, `first_seen`, `last_seen`,
`in_scope`, `provenance[] = [{artifact_sha256, source, observed_at, source_confidence}]`.

```
domain        value=apex                       dedupe: domain:{fqdn}
subdomain     value=fqdn                        dedupe: domain:{fqdn}
live_host     value=scheme://host[:port]        dedupe: livehost:{canonical}
ip            value=v4/v6 (canonical)           dedupe: ip:{norm}
cidr          value=prefix                       dedupe: cidr:{norm}
asn           value=AS#                          dedupe: asn:{n}
cert          value=sha256 fingerprint           dedupe: cert:{sha256}
service       value=host:port/proto              dedupe: svc:{host}:{port}/{proto}
url           value=canonical url                dedupe: url:{canon}        (sort params, drop frag)
js_file       value=url + body sha256            dedupe: js:{sha256}
endpoint      value=method+path(+host)           dedupe: ep:{host}:{method}:{path}
param         value=name(+context)               dedupe: param:{ep}:{name}
finding       value=detector+signature           dedupe: finding:{asset}:{detector}:{sig}
tag           value=key:val (e.g. cdn:fastly)    attached to a node, not standalone
artifact      value=sha256                        dedupe: artifact:{sha256}
repo          value=host/owner/name               dedupe: repo:{full}
tech          value=name[:version][:cpe]          dedupe: tech:{name}:{ver}
screenshot    value=sha256(png)                   dedupe: shot:{sha256}
frame         value=parent_url -> child_url        dedupe: frame:{parent}->{child}
websocket     value=ws(s) url                      dedupe: ws:{canon}
source_map    value=js_url -> map sha256            dedupe: smap:{sha256}
favicon       value=mmh3/sha256 hash                dedupe: favicon:{mmh3}
```

### 6c. Canonical graph — edges (relationships, the chaining bus)

```
domain      HAS_SUBDOMAIN     subdomain
subdomain   RESOLVES_TO       ip
subdomain   CNAME_TO          subdomain          (dangling -> takeover candidate)
ip          IN_CIDR           cidr
cidr        ANNOUNCED_BY      asn
subdomain   SERVES_CERT       cert
cert        COVERS            subdomain           (SAN -> new subdomain frontier)
subdomain   IS_LIVE_AS        live_host
live_host   RUNS              service
live_host   USES_TECH         tech
live_host   HAS_FAVICON       favicon
live_host   HOSTS             url
url         LOADS             js_file
url         EMBEDS            frame
url         OPENS             websocket
js_file     REFERENCES        endpoint
js_file     MAPPED_BY         source_map
endpoint    HAS_PARAM         param
repo        MENTIONS          (domain|endpoint|url)
finding     ON                (any entity)
artifact    EVIDENCE_FOR      (any entity)        (provenance backbone)
favicon     PIVOTS_TO         live_host           (favicon-hash pivot)
```

### 6d. Physical backing

- **System of record:** PostgreSQL (existing `asset/service/endpoint/finding/asset_edge/
  asset_source` tables) — single-writer, upsert on `dedupe_key`. The 22 types map onto
  `asset.type` (+ child tables for `service`/`endpoint`/`finding`); edges → `asset_edge.rel`.
- **Graph projection:** Neo4j (optional) rebuilt from `asset_edge` for pivot/visualization.
- **Search:** OpenSearch projection over entities for faceted queries.
- **Time-series:** `asset_state` (snapshot per scan) powers diffing.
- **Artifacts:** filesystem/MinIO content-addressed store; `asset_source.raw_ref` →
  artifact key. (Implemented today via `core/artifacts.py`; this blueprint upgrades it to
  pure content-addressing by sha256 — see roadmap.)

---

## 5. Corpus-builder logic (the single merge stage)

The corpus builder is the **only** place all source families converge. Every adapter, no
matter the family, lands here; nothing chains tool→tool.

```
for each adapter result in a stage:
  1. PERSIST RAW
       sha = sha256(bytes); store raw/<sha>.* + meta/<sha>.json (source, request, fetched_at, quota_cost)
       if sha already stored -> add provenance row only (content dedupe)
  2. NORMALIZE
       parser(family, adapter) -> list[typed entity events] + edge events
       attach provenance = {artifact_sha256: sha, source, observed_at, source_confidence}
  3. SCOPE TAG
       in_scope = scope.contains(entity)   (out-of-scope kept as intel, never expanded)
  4. DEDUPE + UPSERT (single writer)
       key = dedupe_key(entity)
       INSERT ... ON CONFLICT(workspace, dedupe_key) DO UPDATE
         last_seen=now, merge tags/tech/attributes, append provenance
       confidence = noisy_OR(distinct source_confidence over provenance)
  5. EDGE UPSERT
       upsert typed edges (subdomain_of, resolves_to, covers, references, ...)
  6. EMIT FRONTIER DELTA
       only entities that are NEW (first insert) AND in_scope AND of an expandable type
       are pushed to the Frontier Manager (see 04)
```

### Source scoring (computed during ingest, used by the planner)
Per source, per frontier type, maintain rolling stats:
```
yield      = new_entities_emitted / requests          (unique contribution)
redundancy = entities_already_seen / entities_emitted (overlap with corpus)
freshness  = source-declared recency weight
cost       = quota_units consumed
confidence = source trust weight (CT logs ~0.9, scraping ~0.4, live-verified ~0.95)
score      = (yield × freshness × confidence) / (cost × (1 + redundancy))
```
The planner reads these to pick the **cheapest high-signal source first** and to **skip a
source once its marginal yield falls below a threshold** for the current frontier type
(this is how "use archive/search/code pivots only when they add unique coverage" is
enforced quantitatively).

### Confidence (noisy-OR)
```
confidence(entity) = 1 - Π(1 - source_confidence_i)   over distinct corroborating sources
```
More independent sources ⇒ higher confidence, diminishing returns. A live-validated entity
(httpx 200) injects a ~0.95 corroboration. This is already implemented in
`core/confidence.py`.

### Why raw and normalized are separate
- **Provenance & audit:** every entity traces to immutable bytes (what was seen, when, from
  whom) — required for authorized work and for the AI validator (no invented evidence).
- **Replay/idempotence:** re-normalize from raw after a parser fix without re-querying paid APIs.
- **Content dedupe:** identical bytes from Brave and Mojeek = one blob, two provenance rows.
