# D9 — Folder & Code Structure

A **monorepo** with clear language boundaries (ADR-003: Go hot path, Python brain).
One source of truth for shared types; every tool adapter follows the same contract
(ADR-011/012). Layout below is the target end-state; P0 ships a thin slice of it.

```
observatory/
├── README.md
├── LICENSE
├── Makefile                      # one-liners: make up / make test / make tool-smoke
├── docker-compose.yml            # dev stack: pg, redis, minio, neo4j, opensearch, temporal, vault
├── .github/workflows/            # CI: lint, test, build+sign images, per-tool smoke lane
│
├── docs/                         # ← THIS DOSSIER (D1..D10, ADRs, README)
│
├── schema/                       # SINGLE SOURCE OF TRUTH for shared types (ADR-003)
│   ├── proto/                    # protobuf/JSON-Schema for Asset, Finding, Edge, Event
│   ├── gen-go/                   # generated Go structs   (do not edit)
│   └── gen-py/                   # generated Pydantic models (do not edit)
│
├── deploy/                       # IaC — self-host first, cloud-portable (ADR-013)
│   ├── terraform/                # VPS/cloud provisioning
│   ├── helm/                     # K8s charts (used in P5 scale-out)
│   └── compose/                  # prod-ish compose overlays
│
├── api/                          # PYTHON — FastAPI gateway (ADR-002/014)
│   ├── app/
│   │   ├── main.py
│   │   ├── routers/              # /scans /assets /findings /reports /scopes /auth
│   │   ├── auth/                 # OIDC + signed API keys + RBAC authorizer
│   │   ├── scope/                # request-time scope validation (gateway layer)
│   │   ├── ratelimit/            # gateway throttle (per workspace/user)
│   │   └── deps.py
│   └── tests/
│
├── orchestrator/                 # PYTHON — Temporal workflows (the flow logic, D2)
│   ├── workflows/
│   │   ├── recon_flow.py         # top-level: input → passive → gate → active → report
│   │   ├── passive/              # P1 seed, P2 expansion, P3 enrichment workflows
│   │   ├── active/               # P4 verify, P5 deep, P6 vuln workflows
│   │   └── diff.py               # continuous-mode diff + alert workflow (ADR-016)
│   ├── activities/               # thin Temporal activities that invoke adapters
│   ├── gates/                    # scope gate + passive→active auth gate (ADR-008/009)
│   └── tests/
│
├── workers/                      # tool execution layer
│   ├── go-worker/                # GO — hot-path adapters (fan-out heavy)
│   │   ├── cmd/worker/main.go
│   │   ├── adapters/             # one pkg per tool: subfinder, httpx, naabu, nuclei...
│   │   │   ├── adapter.go        # the pure-adapter interface (ADR-011)
│   │   │   ├── subfinder/
│   │   │   ├── httpx/
│   │   │   ├── naabu/
│   │   │   ├── nuclei/
│   │   │   ├── katana/
│   │   │   ├── dnsx/
│   │   │   └── gowitness/
│   │   ├── parsers/              # per-tool JSON parsers + golden-file tests
│   │   ├── egress/               # proxy pool + per-egress rate-bucket client (D6)
│   │   └── ratelimit/            # Redis token-bucket client
│   └── py-worker/                # PYTHON — API-integration adapters + AI
│       ├── adapters/             # shodan, censys, securitytrails, hibp, github, nvd...
│       ├── ai/                   # classify / rank / summarize / anomaly / semantic-dedupe
│       └── tests/
│
├── normalize/                    # PYTHON — the BRAIN (core IP, ADR-004/011)
│   ├── ingest.py                 # consume raw events from workers
│   ├── dedupe.py                 # dedupe_key computation + upsert (D3)
│   ├── entity_resolution.py      # ip↔domain↔asn↔org resolution
│   ├── confidence.py             # noisy-OR scoring (D3 §4)
│   ├── correlate.py              # tagging (cdn/waf/cloud/honeypot), high-value flags
│   ├── cve_correlate.py          # CPE→NVD→EPSS→priority_rank (D2 P6)
│   ├── projectors/               # outbox → Neo4j + OpenSearch projections (ADR-005/006)
│   └── tests/
│
├── store/                        # data-access layer (shared contracts)
│   ├── pg/                       # migrations (D3 DDL) + repositories
│   ├── graph/                    # Neo4j Cypher queries (pivots, takeover chains)
│   ├── search/                   # OpenSearch index mgmt + queries
│   ├── blob/                     # MinIO/S3 client (raw artifacts, screenshots)
│   └── cache/                    # Redis (rate buckets, caches, locks)
│
├── cli/                          # GO — Cobra CLI (ADR-003)
│   ├── cmd/                      # scan, status, export, scope, report, schedule
│   └── main.go
│
├── web/                          # NEXT.JS dashboard (ADR-002)
│   ├── app/                      # routes: inventory, findings, graph, diff, reports
│   ├── components/               # graph explorer (Cytoscape), screenshot gallery, triage board
│   └── lib/                      # API client (typed from schema/)
│
├── tooling/                      # tool images & runtime contract (ADR-012)
│   ├── images/                   # one Dockerfile per tool, version/digest pinned
│   ├── tool-registry.yaml        # name→image→category→is_active→version
│   └── smoke/                    # per-tool smoke tests run in CI
│
├── config/
│   ├── profiles/                 # passive_only / stealth / normal / aggressive (D6 §4)
│   ├── resolvers/                # dnsvalidator-vetted resolver lists
│   ├── wordlists/                # ffuf/permutation lists (gitignored large ones)
│   └── subfinder-providers.yaml  # provider key references (refs, not secrets)
│
└── observability/                # OpenTelemetry config, Grafana dashboards, alert rules
```

---

## Module Responsibilities (the important ones)

| Module | Owns | Must NOT |
|--------|------|----------|
| `schema/` | The canonical type definitions; codegen to Go + Py | Contain logic |
| `api/` | AuthN/Z, request validation, **gateway scope check**, REST/OpenAPI | Run tools or write canonical records |
| `orchestrator/` | The *flow* (D2), gates, retries, pause/resume, diff scheduling | Parse tool output or do correlation |
| `workers/*/adapters/` | Run one tool, capture raw → MinIO, emit normalized events (ADR-011) | Any cross-asset/correlation logic |
| `workers/*/egress/` | Proxy pool, egress-IP binding, per-IP rate buckets (D6) | Touch the DB |
| `normalize/` | **Sole writer** of canonical assets/findings; dedupe, confidence, correlation, CVE mapping, projections | Call external tools/APIs directly |
| `store/` | Persistence contracts for pg/graph/search/blob/cache | Business logic |
| `cli/` + `web/` | Operator interfaces | Bypass the API gateway |
| `tooling/` | Pinned, signed tool images + smoke tests | — |
| `config/profiles/` | Rate/timing/scope behavior per profile | Hardcode in adapters |

---

## Adapter Contract (the pattern every tool follows)

```go
// workers/go-worker/adapters/adapter.go  (ADR-011: pure adapters)
type Adapter interface {
    // Name maps to tool registry + DB tool table
    Name() string
    IsActive() bool                       // gate-aware (ADR-009)
    // Run executes the tool for a target set under a profile, writing raw to blob
    // and returning normalized events. NO correlation here.
    Run(ctx context.Context, in AdapterInput) ([]NormalizedEvent, error)
}

type AdapterInput struct {
    Targets   []string
    Scope     CompiledScope   // worker-side re-check (ADR-008)
    Profile   RateProfile     // concurrency/QPS/timing (D6 §4)
    KeyRef    string          // Vault reference, never the raw key
    EgressIP  string          // bound source IP, audited
    ScanID    string
}

type NormalizedEvent struct {
    EntityType string          // asset|service|endpoint|finding|edge
    Payload    map[string]any  // maps to schema/ types
    RawRef     string          // s3://... pointer
    Source     SourceMeta      // tool, confidence weight, observed_at
}
```

Every adapter: **acquire rate token → re-check scope → run → write raw → emit events →
audit**. New tool = implement this interface + a parser + a pinned image + a registry
entry. That's the whole extensibility story (a tool can be added in hours).

---

## Data Flow Through the Code (one request)

```
CLI/UI ──HTTP──► api/ (authz + gateway scope)
                   └─► orchestrator/ (start Temporal workflow: recon_flow)
                         ├─ passive workflows ─► activities ─► workers/*/adapters
                         │                                        │ raw→blob, events↘
                         ├─ GATE (scope + auth)                   │
                         ├─ active workflows ─► activities ─► workers/*/adapters
                         │                                        │ events↘
                         └─ diff workflow (continuous)            ▼
                                                            normalize/ (sole writer)
                                                              ├─ pg (canonical truth)
                                                              ├─ projectors → neo4j + opensearch
                                                              └─ ai/ (annotate, async)
                   ◄──────────────────── api reads from store/ ──┘
```

---

## P0 Thin Slice (what actually exists end of Week 2)

```
schema/ (Asset, Event)         · store/pg + store/blob + store/cache
orchestrator/workflows/recon_flow.py (passive-only, 1 phase)
orchestrator/gates/scope.py    · workers/go-worker/adapters/subfinder + parser
normalize/{ingest,dedupe,confidence}.py
cli/ (scan, status, export)    · docker-compose.yml  · CI lint/test/smoke
```

Everything else slots into these directories phase by phase per D7 — the structure
doesn't change, it fills in.
