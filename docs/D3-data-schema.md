# D3 — Data Schema Design

Three stores, one truth. **PostgreSQL** is the system-of-record (canonical assets &
findings). **Neo4j** mirrors *relationships only* for graph queries/viz. **OpenSearch**
indexes assets/findings/endpoints for fast faceted search. **MinIO** holds raw blobs;
the DB stores *pointers* to them.

The two ideas that make dedupe work:
1. **`dedupe_key`** — a deterministic, content-derived key per entity. Re-discovery
   produces the *same* key → upsert, not insert.
2. **Source attribution as a separate table** — an asset is found by *N* tools; we
   record each sighting in `asset_source`, and confidence is a function of that set.

---

## 1. Entity Overview

```
 Workspace 1───* Scan 1───* AssetSource *───1 Asset 1───* Endpoint
                              │                  │
                              │                  ├──* Service (host:port)
                              │                  ├──* Finding *───1 Vuln(CVE)
                              │                  └──* AssetState (time-series)
                              └───1 Tool
 Asset *───* Asset  (relationship edges, mirrored to Neo4j)
```

---

## 2. PostgreSQL — Canonical Schema (pseudo-DDL)

```sql
-- ────────────────────────────────────────────────────────────────
-- TENANCY & RUN CONTEXT
-- ────────────────────────────────────────────────────────────────
CREATE TABLE workspace (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE scope_policy (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID NOT NULL REFERENCES workspace(id),
    allow         JSONB NOT NULL,   -- [{type:'domain',value:'*.acme.com'},{type:'cidr',value:'1.2.3.0/24'},{type:'asn',value:'AS123'}]
    deny          JSONB NOT NULL DEFAULT '[]',
    wildcard_rules JSONB NOT NULL DEFAULT '{}',
    active_authorized BOOLEAN NOT NULL DEFAULT FALSE,  -- HARD gate for active phases
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE scan (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID NOT NULL REFERENCES workspace(id),
    scope_id      UUID NOT NULL REFERENCES scope_policy(id),
    seed          JSONB NOT NULL,            -- normalized seeds + input type
    profile       TEXT NOT NULL,             -- 'stealth'|'normal'|'aggressive'|'passive_only'
    mode          TEXT NOT NULL,             -- 'oneshot'|'continuous'
    status        TEXT NOT NULL,             -- queued|running|paused|done|failed
    temporal_workflow_id TEXT,               -- link to orchestrator run
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ
);

CREATE TABLE tool (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT UNIQUE NOT NULL,      -- 'subfinder','httpx','nuclei',...
    category      TEXT NOT NULL,             -- CAT-1..CAT-10
    is_active     BOOLEAN NOT NULL,          -- does it touch target?
    version       TEXT
);

-- ────────────────────────────────────────────────────────────────
-- ASSET (the core entity) — one row per unique real-world thing
-- ────────────────────────────────────────────────────────────────
CREATE TABLE asset (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID NOT NULL REFERENCES workspace(id),
    type          TEXT NOT NULL,             -- 'domain'|'subdomain'|'ip'|'cidr'|'asn'|'url'|'service'|'cert'|'bucket'|'email'
    value         TEXT NOT NULL,             -- 'api.acme.com' | '1.2.3.4' | 'AS13335' | 'https://...'
    dedupe_key    TEXT NOT NULL,             -- deterministic: e.g. sha1(lower(type||':'||canonical_value))
    attributes    JSONB NOT NULL DEFAULT '{}',-- type-specific: {ip_version, cdn, cloud_provider, registrar...}
    tech          JSONB NOT NULL DEFAULT '[]',-- [{name:'nginx',version:'1.18',cpe:'...'}]
    tags          TEXT[] NOT NULL DEFAULT '{}',-- ['cdn','waf','cloud','honeypot','login','api','admin','high_value']
    confidence    NUMERIC(4,3) NOT NULL DEFAULT 0.0,  -- 0..1, derived from source count/quality
    is_live       BOOLEAN,                   -- NULL=unknown (passive only), true/false after active verify
    first_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, dedupe_key)        -- upsert target
);
CREATE INDEX ON asset USING gin (tags);
CREATE INDEX ON asset USING gin (attributes);
CREATE INDEX ON asset USING gin (value gin_trgm_ops);  -- fuzzy match for correlation

-- SERVICE: a host:port with protocol (subset/child of an IP/host asset)
CREATE TABLE service (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id      UUID NOT NULL REFERENCES asset(id) ON DELETE CASCADE, -- the host/IP
    port          INT NOT NULL,
    protocol      TEXT NOT NULL,             -- tcp|udp
    service_name  TEXT,                       -- 'http','https','ssh'...
    product       TEXT,                       -- 'nginx','OpenSSH'
    version       TEXT,
    banner        TEXT,
    tls           JSONB,                      -- {cert_cn, san[], issuer, expiry, ja3s, weak_ciphers[]}
    dedupe_key    TEXT NOT NULL,              -- sha1(asset_id||port||protocol)
    first_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (asset_id, port, protocol)
);

-- ENDPOINT: a URL/path discovered on a web service
CREATE TABLE endpoint (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id      UUID NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    url           TEXT NOT NULL,
    method        TEXT NOT NULL DEFAULT 'GET',
    status_code   INT,
    content_hash  TEXT,                       -- to detect change over time
    title         TEXT,
    params        JSONB NOT NULL DEFAULT '[]',-- discovered parameters
    risk_class    TEXT,                       -- AI/rules: 'admin'|'auth'|'api'|'upload'|'debug'|'static'
    source        TEXT,                       -- 'katana'|'gau'|'wayback'|'js'
    dedupe_key    TEXT NOT NULL,
    first_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (asset_id, dedupe_key)
);
CREATE INDEX ON endpoint USING gin (url gin_trgm_ops);

-- ────────────────────────────────────────────────────────────────
-- SOURCE ATTRIBUTION — every time a tool sees an asset
-- ────────────────────────────────────────────────────────────────
CREATE TABLE asset_source (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id      UUID NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    scan_id       UUID NOT NULL REFERENCES scan(id),
    tool_id       UUID NOT NULL REFERENCES tool(id),
    raw_ref       TEXT,                       -- s3://minio/raw/<scan>/<tool>/<obj>.json
    source_confidence NUMERIC(4,3) NOT NULL DEFAULT 0.5, -- per-tool trust weight
    observed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (asset_id, scan_id, tool_id)
);

-- ────────────────────────────────────────────────────────────────
-- FINDINGS (vuln / exposure / misconfig)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE vuln_ref (                       -- CVE catalog cache
    cve_id        TEXT PRIMARY KEY,           -- 'CVE-2024-1234'
    cvss_v3       NUMERIC(3,1),
    cvss_vector   TEXT,
    epss_score    NUMERIC(5,4),               -- exploit probability 0..1
    epss_percentile NUMERIC(5,4),
    cpe           TEXT[],
    has_public_exploit BOOLEAN,
    summary       TEXT,
    refreshed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE finding (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID NOT NULL REFERENCES workspace(id),
    asset_id      UUID REFERENCES asset(id),
    endpoint_id   UUID REFERENCES endpoint(id),
    service_id    UUID REFERENCES service(id),
    kind          TEXT NOT NULL,              -- 'cve'|'takeover'|'exposure'|'misconfig'|'secret'|'tls'|'cloud'
    title         TEXT NOT NULL,
    cve_id        TEXT REFERENCES vuln_ref(cve_id),
    severity      TEXT NOT NULL,              -- info|low|medium|high|critical
    confidence    NUMERIC(4,3) NOT NULL,      -- corroboration-based
    priority_rank NUMERIC(6,3),               -- f(CVSS, EPSS, exposure, asset_value)
    detector      TEXT NOT NULL,              -- 'nuclei:template-id'|'subjack'|'sslyze'
    evidence_ref  TEXT,                        -- s3 pointer to proof (response, screenshot)
    evidence_redacted JSONB,                   -- safe-to-store summary (secrets HASHED, never raw)
    status        TEXT NOT NULL DEFAULT 'open',-- open|triaged|false_positive|fixed|accepted
    dedupe_key    TEXT NOT NULL,
    first_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, dedupe_key)
);
CREATE INDEX ON finding (severity, priority_rank DESC);

-- ────────────────────────────────────────────────────────────────
-- TIME-SERIES STATE (TimescaleDB hypertable) — "what changed"
-- ────────────────────────────────────────────────────────────────
CREATE TABLE asset_state (
    asset_id      UUID NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    observed_at   TIMESTAMPTZ NOT NULL,
    is_live       BOOLEAN,
    snapshot      JSONB NOT NULL,             -- {ports[], tech[], status, ip, tags[]}
    change_type   TEXT,                       -- 'new'|'modified'|'gone'|'unchanged'
    PRIMARY KEY (asset_id, observed_at)
);
-- SELECT create_hypertable('asset_state','observed_at');  -- TimescaleDB

-- ────────────────────────────────────────────────────────────────
-- RELATIONSHIP EDGES (mirrored to Neo4j; kept here as source-of-truth)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE asset_edge (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    src_asset_id  UUID NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    dst_asset_id  UUID NOT NULL REFERENCES asset(id) ON DELETE CASCADE,
    rel           TEXT NOT NULL,              -- 'resolves_to'|'in_cidr'|'announced_by'|'owned_by'|'subdomain_of'|'cname_to'|'serves_cert'|'hosts'
    attributes    JSONB NOT NULL DEFAULT '{}',
    first_seen    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (src_asset_id, dst_asset_id, rel)
);

-- ────────────────────────────────────────────────────────────────
-- AUDIT (OPSEC requirement: every action logged)
-- ────────────────────────────────────────────────────────────────
CREATE TABLE audit_log (
    id            BIGSERIAL PRIMARY KEY,
    scan_id       UUID REFERENCES scan(id),
    actor         TEXT NOT NULL,              -- user id or 'system'/'worker'
    action        TEXT NOT NULL,              -- 'tool.exec'|'scope.deny'|'export'|'auth.gate'
    tool_id       UUID REFERENCES tool(id),
    target        TEXT,
    egress_ip     TEXT,                        -- which proxy/IP made the request
    rate_profile  TEXT,
    detail        JSONB,
    ts            TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## 3. Dedupe Key Strategy (the heart of normalization)

```
asset.dedupe_key:
  domain/subdomain → sha1( 'domain:' || lower(fqdn_without_trailing_dot) )
  ip               → sha1( 'ip:' || normalized_ip )            -- v6 canonicalized
  asn              → sha1( 'asn:' || 'AS' || number )
  url              → sha1( 'url:' || canonicalized_url )        -- sort query params, drop fragment
  cert             → sha1( 'cert:' || sha256_fingerprint )
  bucket           → sha1( 'bucket:' || provider || ':' || name )

service.dedupe_key  → sha1( asset_id || ':' || port || '/' || protocol )

finding.dedupe_key  → sha1( asset_or_endpoint_id || ':' || detector || ':' || cve_or_signature )
  -- so the SAME nuclei template on the SAME endpoint dedupes,
  --    even across re-scans and across tools that detect it.
```

**Upsert pattern:** every normalized record does
`INSERT ... ON CONFLICT (workspace_id, dedupe_key) DO UPDATE SET last_seen=now(), ...`
and appends to `asset_source`. Re-discovery never creates duplicates; it strengthens
confidence and refreshes `last_seen`.

---

## 4. Confidence Scoring Model

```
confidence(asset) = 1 - Π (1 - source_confidence_i)        for each distinct source i
```
- One source at 0.5 → 0.50. Two independent 0.5 sources → 0.75. Three → 0.875.
- `source_confidence` is a per-tool trust weight (e.g., crt.sh CT log = 0.9 since it's
  authoritative; a scraping tool = 0.4). Live verification (httpx 200 OK) sets a
  near-certain corroboration (0.95).
- This is the classic "noisy-OR" combination — more independent corroboration → higher
  confidence, with diminishing returns. Cheap to compute, intuitive to explain in
  reports.

---

## 5. Neo4j Graph Model (relationships mirror)

Nodes carry only `id` (= Postgres `asset.id`), `type`, `value`, `tags`. Heavy
attributes stay in Postgres. Neo4j is for *traversal*, not storage of truth.

```cypher
// Node labels: :Domain :Subdomain :IP :CIDR :ASN :Org :URL :Cert :Service :Bucket
// Example edges
(:Subdomain {value:'api.acme.com'})-[:RESOLVES_TO]->(:IP {value:'1.2.3.4'})
(:IP)-[:IN_CIDR]->(:CIDR {value:'1.2.3.0/24'})
(:CIDR)-[:ANNOUNCED_BY]->(:ASN {value:'AS13335'})
(:ASN)-[:OWNED_BY]->(:Org {value:'Acme Inc'})
(:Subdomain)-[:SUBDOMAIN_OF]->(:Domain {value:'acme.com'})
(:Subdomain)-[:CNAME_TO]->(:Subdomain)            // takeover-chain detection
(:Cert)-[:COVERS]->(:Subdomain)                   // CT pivot

// High-value queries this enables:
// 1) "All assets reachable from this ASN" (attack-surface blast radius)
MATCH (a:ASN {value:$asn})<-[:ANNOUNCED_BY]-(c)-[:IN_CIDR*0..1]-(ip)<-[:RESOLVES_TO]-(h)
RETURN h;
// 2) Dangling-CNAME takeover candidates
MATCH (s:Subdomain)-[:CNAME_TO]->(t) WHERE NOT (t)-[:RESOLVES_TO]->() RETURN s,t;
// 3) Shared-cert pivot to forgotten infra
MATCH (cert:Cert)-[:COVERS]->(s) WITH cert, count(s) AS n WHERE n>1 RETURN cert, n;
```

**Sync:** the normalization engine writes Postgres first (truth), then projects edges
to Neo4j in the same transaction boundary (outbox pattern → async projector). If Neo4j
is down, the graph is rebuildable from `asset` + `asset_edge`.

---

## 6. OpenSearch Index (search/facets)

```jsonc
// index: assets-{workspace}
{
  "asset_id": "uuid", "type": "subdomain", "value": "api.acme.com",
  "tags": ["api","cloud","waf"], "tech": ["nginx","react"],
  "ports": [443,8443], "is_live": true, "confidence": 0.875,
  "asn": "AS13335", "ip": ["1.2.3.4"], "title": "Acme API",
  "first_seen": "...", "last_seen": "..."
}
// Enables: free-text "admin", facet by tag/tech/port/asn/live,
//          sort by confidence, "show me all login panels behind no WAF".
```

---

## 7. Raw Artifact Layout (MinIO/S3)

```
s3://observatory-raw/
  {workspace_id}/{scan_id}/{tool_name}/{timestamp}_{uuid}.json   # raw tool output
  {workspace_id}/{scan_id}/screenshots/{asset_id}.png            # gowitness
  {workspace_id}/{scan_id}/responses/{endpoint_id}.http          # nuclei/httpx evidence
```
DB columns (`raw_ref`, `evidence_ref`) store these keys. **Secrets are never stored
raw** — `finding.evidence_redacted` keeps a hash + masked preview + file/line location
only (see D6/D10).

---

## 8. Retention & Archival Policy

| Data | Hot (fast store) | Warm | Cold / archive | Delete |
|------|------------------|------|----------------|--------|
| Canonical assets/findings | Postgres, indefinite while workspace active | — | export to JSON on workspace close | on workspace delete |
| `asset_state` time-series | Timescale, 90 days full granularity | downsample to daily after 90d | Parquet to S3 after 1yr | per policy |
| Raw tool output | MinIO 30 days | lifecycle → infrequent-access | Glacier-class after 90d | 1yr default (configurable) |
| Screenshots | MinIO 90 days | — | archive | 1yr |
| Breach/PII data (CAT-8) | **minimized**, 7–30 days max, encrypted | — | **do not archive** | aggressive auto-purge (GDPR) |
| Audit log | Postgres 1yr | Loki/S3 | 7yr (compliance option) | per legal hold |

PII/breach data gets the **shortest** retention and **never** lands in cold archive —
this is a deliberate legal/risk control, expanded in D6 and D10.
