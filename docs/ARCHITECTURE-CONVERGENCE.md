# ReconTool — Converged Architecture (post-M9 + Batch-11)

> Convergence result. Runtime is the source of truth: every claim here is grounded in
> the live `ToolRegistry`, `recontool/engine/flow_graph.py`, the Batch-11 catalog
> (`docs/e2e-verification/TOOL_CATALOG_FULL.tsv`, real scans), and the M1–M9 code.
> Supersedes nothing — extends `docs/00-FINAL-ARCHITECTURE.md` with the entity/tool
> taxonomy, the exploitation layer, and the validated tool coverage.
> **Tool universe: 565/565 `docs/tools` entries categorized (0 uncovered); 586 registry
> entries total.**

---

## 1. Executive Summary

ReconTool is an **entity-driven, recursive reconnaissance + validation engine**. Entities
(not tools) drive the system: a seed enters, tools that *consume* its type run, their
*typed output* becomes new entities, validation gates them, and the survivors re-enter
routing until a finite in-scope frontier converges. The system is correct and reachable
today for the **core recon flow** (`flow_lint` in-scope reachability = 0). The architecture
spans 7 layers — Recon → Validation → Enrichment → **Exploitation** → Artifact-Analysis →
Reporting, with AI as a bounded sidecar. Six of seven layers are wired; **Exploitation is
defined-but-empty by design** (detection tools are Terminal) and is the primary build-out.

**Confidence: 8.2/10** (see §19) — engine, routing, validation, artifacts, recursion are
production-shaped; exploitation, the AI model-backing, and a handful of enrichment
producers are the remaining work.

---

## 2. Final Architecture (the entity loop)

```
seed(domain/org/ip/asn) ─► Router (deterministic key_type→consumes join)
        │
        ▼
   WorkQueue (key, tool) ──► Worker pool (atomic claim) ──► Adapter executes
        ▲                                                        │
        │                                                  raw + typed artifacts
        │                                                        │
        │                                                  Normalizer (sole writer, idempotent)
        │                                                        │
        │                                              EntityDiscovered events
        │                                                        │
   re-enqueue ◄── Validation gate ◄── AI decisioning ◄──────────┘
   (Router)       (scope · live · noise · dedupe)   (classify/extract, never route)

Converge a branch when: no new in-scope keys (seen-set fixpoint) · depth/budget cap ·
noise filter rejects (wildcard/CDN/dup). Endpoints are recorded but NOT re-fed (M6).
```

**State = two tables** (`engine/models.py`): `ToolRow` (static capability registry) +
`WorkItem` (dynamic `(key, tool)` queue). The 586-tool "matrix" is a *report*, never the
store. **Routing is a deterministic join** (`engine/router.py` / `worker.py:RouteIndex`),
never an AI call. **The Normalizer is the only writer** (`normalize/engine.py`), idempotent
on canonical `dedupe_key`, so overlapping tools cost one record, never a rescan.

### The 7 layers (every tool lands in exactly one)
| Layer | Role | Recursion class | # tools (runnable) | Gate |
|---|---|---|---|---|
| **Recon** | discover/expand entities | Generator, Expander | 327+36 (≈230 wired) | passive default-on |
| **Validation** | confirm reality (live, ports) | Validator | 28 | active (authorized) |
| **Enrichment** | add context (ASN, tech, intel) | Enrichment | 8 | passive |
| **Exploitation** | confirm vulns (NO exploit today) | Terminal (detect) | 79 | active (authorized) |
| **Artifact-Analysis** | mine files (JS, repo, doc, binary) | Artifact-Analyzer | 6 | passive on artifacts |
| **Reporting** | evidence → report | — | `report.py` | terminal |
| **AI** | classify/extract/prioritize | sidecar | 4 functions | never routes |
| **Reference** | tool-discovery lists | non-executable | 102 | never run |

---

## 3. Entity Taxonomy

Canonical vocabulary = `config/categories.yaml meta.dedupe_forms` (M1 completed it; 0
non-canonical types remain). Per-type producer/consumer counts from `flow_graph.build_graph`
over the live registry:

| Entity | dedupe form | Producers | Consumers | Validation | Recurses? | Storage |
|---|---|---|---|---|---|---|
| domain | `domain:{fqdn}` | seed | 326 | scope+ownership | → subdomain | Asset |
| subdomain | `domain:{fqdn}` | 136 | 76 | scope | → live_host (httpx) | Asset |
| live_host | `livehost:{scheme}://{host}:{port}` | httpx (M3) | 64 | **httpx-confirmed** | → url/service/cert | Asset(is_live) |
| url | `url:{canonical}` | 120 | 103 | scope | → js_file/endpoint | Asset/Endpoint |
| endpoint | `ep:{host}:{method}:{path}` | 24 | param/vuln | scope | **terminal (M6)** | Endpoint |
| ip | `ip:{normalized}` | 132 | 132 | scope/CIDR | → service | Asset |
| cidr | `cidr:{normalized}` | 34 | mapcidr | ASN-owned | → ip | Asset |
| asn | `asn:{number}` | 31 | 86 | ownership | → cidr | Asset |
| service | `svc:{host}:{port}/{proto}` | 84 | 28 | reachable | → vuln | Service |
| cert | `cert:{sha256}` | censys/tlsx | (SAN→subdomain) | — | → subdomain | Asset |
| js_file | `js:{body_sha256}` | pycrawl (M5) | jsluice/linkfinder/secretfinder/js_analyze | — | → endpoint/secret | artifact+Asset |
| repo | `repo:{host}/{o}/{n}` | github_search | gitleaks/trufflehog | scope | → finding | Asset |
| bucket | `bucket:{provider}:{name}` | 24 | s3scanner | — | → finding | Asset |
| finding | `finding:{asset}:{detector}:{sig}` | 278 | report | severity | **terminal** | Finding |
| tech/tag/screenshot/ioc | … | many | — | — | **terminal** evidence | Asset/artifact |
| document/binary/apk | `doc:{sha256}` … | **deferred** | exiftool/binwalk/apkleaks | — | → endpoint/secret | artifact |
| email/username/org | … | many | identity tools | PII gate | overlay | Asset |
| cpe/cve/hash/keyword | … | **deferred** | nvd/vulners/code-search | — | enrichment | — |

**Rule satisfied:** every entity has a producer or is a seed; every entity has a consumer
or is terminal — **in-scope = complete** (`flow_lint` = 0). Gaps are deferred (document/
binary/cpe/cve) or off-by-default overlay (coords/bssid/handle/analytics_id/favicon).

---

## 4. Tool Taxonomy (586 entries, 0 uncategorized)

From Batch-11 (`TOOL_CATALOG_FULL.tsv`), recursion class × recommendation:

| Recursion class | count | KEEP_CORE | KEEP_OPTIONAL | other | layer |
|---|---|---|---|---|---|
| Generator | 327 | 19 | 174 | 134 | Recon |
| Reference | 102 | — | — | 102 ref-only | (none) |
| Terminal | 79 | 3 | 68 | 8 | Exploitation/Findings |
| Expander | 36 | 4 | 24 | 8 | Recon |
| Validator | 28 | — | — | 28 | Validation |
| Enrichment | 8 | — | — | 8 | Enrichment |
| Artifact-Analyzer | 6 | — | — | 6 | Artifact-Analysis |

Recommendations: **334 schedulable** (26 KEEP_CORE, 266 KEEP_OPTIONAL, 28 VALIDATION_ONLY,
8 ENRICHMENT_ONLY, 6 ARTIFACT_ONLY) · **150 DEFER** · **102 REFERENCE_ONLY**. Methodology:
exact for runnable tools; approximate for inventory stubs (category-inflated `produces`).

---

## 5. Producer → Consumer Graph (the spine)

```
domain ─[subfinder/crtsh/amass]─► subdomain ─[httpx]─► live_host
live_host ─[katana/ffuf]─► url ─[pycrawl]─► js_file ─[jsluice/secretfinder]─► endpoint+secret
live_host ─[tlsx]─► cert ─(SAN)─► subdomain          live_host ─[gowitness]─► screenshot
asn ─[asnmap]─► cidr ─[mapcidr]─► ip ─[naabu]─► service ─[nmap]─► (version)
ip/cidr ─[naabu/nmap]─► service                       org ─[github_search]─► repo ─[gitleaks]─► finding
live_host/url/service/endpoint ─[nuclei]─► finding ─► report
bucket-finders ─► bucket ─[s3scanner]─► finding
```

Full machine-readable graph: `TOOL_CATALOG_FULL.tsv` (upstream/downstream per tool).

---

## 6. Validation Architecture

Validation gates entities **before re-feed** (the highest-leverage noise control):

1. **Scope** (`core/scope.py`) — every host/url/live_host checked against the authorized
   apex; deny wins. (M3 closed a live_host scope leak.)
2. **Live validation** (M3) — active/deep tools consume `live_host`, which only
   httpx-confirmed hosts get; an unvalidated subdomain never reaches active scanning.
3. **Noise filter** (`engine/noise.py`, opt-in) — wildcard-DNS, CDN/WAF exclusion
   (`cdncheck`), cross-scan dedupe.
4. **AI decisioning gate** (`engine/ai_decision.py`) — classify noise vs signal; scope
   floor: an in-scope asset is NEVER dropped.
5. **Dedupe-on-enqueue** (`router.enqueue`) — a `(key, tool)` pair runs once, ever.

**Active-authorization gate** (`engine/selection.py:46`): every `is_active` tool is
disabled unless `--authorize-active`, independent of `default_on`. Passive by default.

---

## 7. Artifact Architecture (first-class)

| Artifact | Path | Written by | Retention |
|---|---|---|---|
| Raw | `artifacts/<scan>/raw/<slug>/<ts>.json` | adapters (`save_raw`) | full (provenance) |
| Typed (per produced type) | `out/<slug>.<type>.jsonl` | `write_typed_outputs` | append-only |
| Per-key run ledger | `out/<slug>.runs.jsonl` | worker (every run incl. empty) | append-only |
| Raw tool dump (e.g. nuclei) | `out/<slug>.raw.jsonl` | adapter | append-only |
| Bundle manifest | `scan_bundle.json` | `runner.write_scan_bundle` | self-describing export |
| Files (JS/docs/screens) | `js/<host>/`, `documents/<sha>`, `screenshots/<sha>.png` | adapters | content-addressed |

Guarantees (verified): **raw is never discarded**; typed output is **per produced type**
(multi-mode tools get one file per type); **every run leaves a ledger line** even when it
finds nothing. Secrets stored hash+mask+location only, never raw. **Gap:** retention/TTL
policy for PII/breach data is documented but not enforced in code.

---

## 8. AI Architecture (bounded sidecar)

AI is used for **exactly 4 functions, each with a deterministic fallback**, and **never
routes/schedules/replaces evidence**:

| Function | Where | Today | Target |
|---|---|---|---|
| Entity extraction | parsers / `generic.emit_events` | deterministic | + model for unstructured output |
| Prioritization | `ai_decision.should_rescan` | heuristic | model lead-scoring (admin>cdn) |
| Recurse/converge | `noise.py` + `ai_decision` | deterministic | model wildcard/noise judgment |
| Canonicalization | `core/dedupe.py` | pure function | model fuzzy-merge |
| (Reporting/correlation) | `report.py` | deterministic | model narrative + cross-source correlation |

**MUST NOT:** routing (a `WHERE` clause), validation (deterministic), evidence (raw is truth).
Token-frugal: light model triages (budget cap, `ai/router.py`), heavy model only for the
final narrative. Current state: model paths exist but are thin — **mostly heuristic today.**

---

## 9. Exploitation Architecture (NEW — the primary build-out)

Today the "Exploitation" layer is **detection-only** (nuclei/WPScan/nikto are Terminal:
they produce `finding`, never exploit). The converged design adds a **dedicated, strictly
gated exploitation layer** *downstream of Findings* — never mixed with recon:

```
Findings (detect) ──► Exploitation candidate selection (AI prioritization + EPSS/CVSS rank)
        │
        ▼
  Exploitation layer  [HARD-GATED: --authorize-exploit, separate from --authorize-active]
   inputs:  live_host · url · endpoint · service · repository · certificate · finding(cve)
   tools:   (future) dalfox(XSS PoC), sqlmap, nuclei -dast, custom PoC, interactsh(OAST)
   outputs: vulnerability(confirmed) · evidence(request/response, OAST hit) · finding(severity↑)
        │
        ▼
  Post-Processing (de-dupe vulns, attach evidence) ──► Reporting
```

**Rules:** (1) exploitation consumes only **validated** entities (live_host/service that
passed Validation); (2) a NEW entity type `vulnerability` (confirmed) distinct from
`finding` (detected); (3) its own authorization flag + audit log + rate limits; (4)
non-destructive PoC only — the policy boundary (no DoS, no data exfiltration) is enforced
at this layer. **Status: architecture defined; 0 tools wired — the framework is greenfield.**

---

## 10. Scheduling Matrix (which tools run on each entity stage)

From Batch-11 §2 (runnable tools; **core in bold**):

| Stage | Mandatory (core) | Optional | Validation | Exploitation |
|---|---|---|---|---|
| domain | **subfinder, crtsh, certspotter, dnsx** | amass, assetfinder, findomain, chaos… | — | — |
| subdomain | **httpx** (→live_host) | tlsx, sublist3r, shuffledns | dnsx resolve | — |
| live_host | **nuclei** | whatweb, gowitness, katana, ffuf, feroxbuster | naabu, nmap | (future) |
| url | (crawled) | gospider, hakrawler, kiterunner, gf-* | — | (future) sqlmap/dalfox |
| js_file | jsluice, secretfinder | linkfinder, js_analyze | — | — |
| ip/cidr | mapcidr | masscan | **naabu, nmap** | — |
| service | — | — | nmap -sV, sslyze | (future) per-service PoC |
| repository | gitleaks, trufflehog | — | — | — |
| org | **github_search, hunter-emails** | grayhatwarfare, cloud_enum | — | — |
| finding | (→report) | nvd/vulners (EPSS rank) | — | exploitation candidate select |

---

## 11. Storage Architecture

- **Relational (SQLite→Postgres):** `Asset`, `Service`, `Endpoint`, `Finding`, `Edge`
  (graph), `ToolRow`, `WorkItem`, `ToolRun`. Idempotent upsert keyed on `dedupe_key`.
  Covering claim index `ix_workitem_claim (scan_id,status,depth,id)`.
- **Object/file:** content-addressed artifacts (sha256) under `artifacts/<scan>/`.
- **Graph (future):** Neo4j for the relationship/clue graph (visualization ships over SQL
  today via `recontool serve`).
- **Scale:** bounded enqueue (`dedupe_key IN (...)`, indexed — O(eligible tools) not
  O(total keys)); precomputed `RouteIndex`; horizontal multi-worker via atomic claim.

---

## 12. Runtime Execution Flow

`run_engine_scan` (`runner.py`) → build infra (scope/http/profile/keys) + load registry +
apply active gate → seed enqueue → N async workers claim `pending→running` (atomic CAS) →
`run_tool_spec` (adapter) → AI decisioning → Normalizer ingest → typed outputs → publish
`EntityDiscovered` → noise/validation gate → re-enqueue. Resumable (DB-backed), multi-
process/host safe, checkpointed.

---

## 13. Recursion Rules (correctness)

1. **Idempotent keys** — never rescan a `(key, tool)` pair.
2. **No endpoint re-feed (M6)** — endpoints/params/tech/cert are recursion-terminal
   evidence; re-feeding the gau/katana firehose (100k+ URLs) would explode the scan.
3. **Narrowed subsumption (M9)** — `url`/`live_host` subsume nothing; a crawled URL no
   longer re-triggers the ~340-tool domain wave. Only `subdomain→domain` is kept.
4. **Live gate (M3)** — active/deep tools fire only on validated `live_host`.
5. **Convergence** — seen-set fixpoint over a finite in-scope space + depth/budget caps +
   noise rejection. Provably terminates.

---

## 14. Cost Optimization Plan

| Lever | Mechanism |
|---|---|
| No rescans | idempotent keys (overlap is free) |
| No firehose recursion | endpoints terminal (M6), narrowed subsumption (M9) |
| Validate before active | live_host gate (M3) — don't scan dead hosts |
| Profile-gating | `default_on` + `--tools default|all`; active behind authorization |
| API budget | per-provider rate limits + budget ledger; light-model triage cap |
| Dedupe duplicates | 31 duplicate groups → run the superset, others available not default |

---

## 15. Default Profile (KEEP_CORE, 26 tools)

`subfinder, crtsh, certspotter, findomain, anubis-jldc, subdomaincenter` (subdomain) ·
`dnsx` (resolve) · `httpx` (live) · `nuclei` (detect) · `gau, wayback, wayback_cdx`
(archive) · `shodan, censys, netlas, uncover, internetdb, leakix, fullhunt, criminalip,
urlscan, greynoise, alienvault_otx` (intel) · `hunter-emails, hibp-exposure` (identity).
Passive, high-signal, non-wasteful. Active tools (naabu/nuclei/katana) require
`--authorize-active`.

## 16. Deep / specialized profiles
- **Deep:** default + active (naabu, nmap, katana, ffuf, feroxbuster, whatweb, gowitness, tlsx).
- **JS:** pycrawl + jsluice/secretfinder/linkfinder (js_file chain).
- **Repository:** github_search + gitleaks/trufflehog.
- **Cloud:** grayhatwarfare/cloud_enum/s3scanner (bucket chain).
- **Validation:** httpx + naabu + nmap + sslyze.
- **Exploitation:** (future) the §9 layer, separate authorization.

---

## 17. Future Expansion Plan
1. Wire the DEFERRED producers so deferred chains become reachable: `document`/`binary`
   (metagoofil→document, exiftool/binwalk consume) and enrichment (`service→cpe→nvd→cve`,
   `org→keyword→code-search`).
2. Build the **Exploitation layer** (§9) — the single biggest capability gap.
3. Model-back the 4 AI functions (keep deterministic fallbacks).
4. Neo4j graph store + evidence-pack export.
5. New tools auto-categorize: declaring `consumes`/`produces` is the only integration step.

---

## 18. Architecture Gaps Remaining
| Gap | Severity | Fix |
|---|---|---|
| Exploitation layer empty | HIGH (capability) | §9 build-out |
| AI mostly heuristic | MED | model-back the 4 functions |
| Deferred producers unwired (document/binary/cpe/cve/keyword) | MED | wire producers (coverage batch) |
| `host_port` dead-ends under --authorize-active | LOW | align nmap consume type or naabu emit |
| Two routing impls (router.py ToolRow vs worker RouteIndex) | LOW | unify on one (risk-managed) |
| PII/breach retention not code-enforced | MED (compliance) | TTL + minimization in storage |
| ~150 inventory stubs unwired | LOW (by design) | wire on demand; kept available |

---

## 19. Architecture Confidence Score — **8.2 / 10**
| Dimension | Score | Basis |
|---|---|---|
| Executable | 9 | engine alive, 30 tools produced data in real scans |
| Scalable | 8 | bounded enqueue, atomic claim, no firehose; Postgres+Neo4j pending |
| Traceable | 9 | raw+typed+ledger+bundle; flow_lint + catalog reproducible |
| Recursively correct | 9 | M6/M9 + seen-set fixpoint; in-scope reachability = 0 |
| Tool-complete | 9 | 565/565 docs tools categorized; 0 uncovered |
| Validation-complete | 8 | scope+live+noise+dedupe; PII TTL not enforced |
| Artifact-complete | 8 | full chain; retention policy gap |
| Exploitation-complete | 3 | defined, 0 tools wired |
| AI-complete | 5 | bounded + fallbacks, but thin model-backing |

## 20. Recommended Implementation Roadmap
1. **Exploitation layer scaffolding** (§9): new `vulnerability` entity, `--authorize-exploit`
   gate, candidate-selection from Findings (EPSS/CVSS), 1 vertical slice (e.g. nuclei-dast
   or dalfox on validated url) end-to-end with artifacts.
2. **Fix host_port nit** + wire `service→cpe→nvd→cve` (threat-intel enrichment chain).
3. **Wire file-analysis producers** (metagoofil→document; document→exiftool, binary→binwalk).
4. **Model-back AI prioritization + reporting** (deterministic fallback intact).
5. **PII retention enforcement** in storage; then **Postgres + Neo4j** for enterprise scale.

Each step re-runs `flow_lint` (in-scope must stay 0) + regenerates the Batch-11 catalog.
