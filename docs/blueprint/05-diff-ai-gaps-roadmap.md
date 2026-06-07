# 05 — Diffing/Monitoring, AI Supervisor, Gaps & Roadmap

## 9. Diffing & monitoring

Time-awareness is a first-class feature, not an afterthought. Every scan writes an
`asset_state` snapshot per entity; the diff engine compares the latest run to the prior.

```
snapshot(entity) = { dedupe_key, type, value, key_attrs(ports/tech/status/ip/tags),
                     confidence, content_hash, observed_at }
diff(prev, curr):
  NEW      = keys in curr not in prev
  GONE     = keys in prev not in curr            (grace window before declaring gone)
  CHANGED  = same key, changed key_attrs/content_hash
            (e.g. new open port, new tech, status flip, new CVE-sig, new SAN, cert rotation)
emit change events -> notify sinks (slack/webhook/email) -> dashboards
```

**Continuous monitoring (EASM mode):**
- Schedule the **passive** pipeline on an interval; a CertSpotter/CT webhook can trigger an
  out-of-cycle pass when a new cert is issued for the scope.
- Active re-runs require standing authorization (the same auth gate), never silent.
- Alert policy is scoped: change events carry provenance (which source/artifact saw it).
- "What changed since last scan" is the headline report; full inventory is the appendix.

**Live progress streaming:** the normalizer emits events as entities land; the CLI renders a
live table (subdomains found / live / findings), and the API exposes SSE/WebSocket so the
Web UI updates in real time during a scan.

---

## 10. AI supervisor design

AI is **advisory only** across four roles. Hard rule: **it never invents evidence.** Every
entity/finding it surfaces must reference a stored `artifact_sha256`; the validator drops
anything without provenance. Tiered models (light for routine, heavy for synthesis) with a
per-run call budget; works with a local model for sensitive data.

```
┌ PLANNER ────────────────────────────────────────────────────────────────┐
│ input : frontier type + source scores (yield/cost/freshness/redundancy)   │
│ output: ranked source plan + page/budget caps   (JSON, validated)         │
│ guard : may only choose among REGISTERED adapters; cannot fabricate one    │
└───────────────────────────────────────────────────────────────────────────┘
┌ VALIDATOR ─────────────────────────────────────────────────────────────────┐
│ input : candidate entities/findings + their provenance                      │
│ output: accept / reject / needs-corroboration                               │
│ guard : REJECT any record lacking an artifact_sha256; never adds new facts.  │
│         Flags schema drift (parser produced unexpected shape).               │
└───────────────────────────────────────────────────────────────────────────┘
┌ TRIAGE ─────────────────────────────────────────────────────────────────────┐
│ input : findings + asset context (exposure, tech, tags)                      │
│ output: priority rank (exploit-likelihood signals × exposure × asset value)  │
│ guard : ranks existing findings only; cannot create findings.                │
└───────────────────────────────────────────────────────────────────────────┘
┌ RECOVERY ADVISOR ───────────────────────────────────────────────────────────┐
│ trigger: circuit breaker OPEN / repeated failures / empty high-value frontier│
│ output : suggest alternate source family, backoff change, or stop condition   │
│ guard : suggestions only; scheduler enforces; all actions audited.            │
└───────────────────────────────────────────────────────────────────────────┘
```

**Enforcement of "no invented evidence":**
1. AI operates only over rows already in the graph/artifact store.
2. Any AI output that names an entity is cross-checked: its `dedupe_key` must already exist
   (or be derivable from a stored artifact). No match ⇒ rejected + logged.
3. Prompts, model version, inputs, and outputs are logged for reproducibility/audit.
4. Heuristic fallback: with no model configured, deterministic rules drive planner/triage
   (zero tokens). AI strictly augments; it never gates the deterministic pipeline.

Implemented today as `ai/router.py` (tiered model router + budget) and `ai/supervisor.py`
(plan/review/recurse/report with heuristic fallback). This blueprint adds the explicit
**validator** role and the **provenance-required** guard.

---

## 11. Gaps & future enhancements

### Policy-migration gaps (from the no-evasion constraint)
| # | Gap | Action |
|---|-----|--------|
| G1 | `net/proxy_pool.py` rotation framed for evasion | Reframe to a single **declared** egress (allow-listing), or remove rotation; keep only honest egress config. |
| G2 | `stealth` profile uses jitter/randomization (evasion semantics) | Rename to `polite`; jitter only for thundering-herd, not detection evasion. Update `config.py` + `D6-opsec.md`. |
| G3 | Circuit breaker missing | **Implemented** in `net/circuit.py` (this PR). |
| G4 | Per-provider budget ledger not enforced | Add a run-level ledger in the scheduler; decrement on admit; defer on exhaustion. |

### Capability gaps (designed here, not yet implemented)
| # | Gap | Value |
|---|-----|-------|
| C1 | Browser-rendered crawl (Playwright) for SPAs | high — `pycrawl` is fetch-only today |
| C2 | source-map recovery + AST-based JS endpoint extraction | high — richer endpoints/params |
| C3 | OpenAPI/Swagger/GraphQL discovery loop | high — modern API surface |
| C4 | Content-addressed (sha256) artifact store | med — upgrade `core/artifacts.py` |
| C5 | Favicon-hash pivot adapter | med — cheap infra correlation |
| C6 | Common Crawl index adapter (gated by redundancy score) | med — unique historical coverage |
| C7 | Brave / Mojeek / SearXNG / Google-PSE / Bing search adapters | med — search family currently thin |
| C8 | Neo4j graph projection + pivot UI | med — analyst ergonomics |
| C9 | L3 concurrent web-track ∥ ip-track; full frontier-convergence loop | med — partially wired today |
| C10 | Recorded-fixture contract tests for **every** adapter | high — drift protection |

### Future enhancements
- Source-score learning (bandit) to auto-tune the planner per target over time.
- Per-workspace data-residency for the AI path (self-hosted model default).
- Evidence-pack export (signed bundle: what was scanned, when, by whom, under what auth).
- Cost dashboard with per-provider spend + budget alarms.

---

## 12. Implementation roadmap

Maps the 12 implementation steps to phased, shippable work. Each phase ends with
contract tests (recorded fixtures) + telemetry.

```
PHASE 0 — Foundations (mostly DONE in repo)
  [✓] canonical schema + relational store (core/models, normalize/engine)
  [✓] adapter contract + registry (adapters/base, registry, generic + autoload)
  [✓] dedupe + confidence (core/dedupe, core/confidence)
  [✓] scope gate + passive→active gate (core/scope, orchestrator/pipeline)
  [ ] G3 circuit breaker + G4 budget ledger  ← circuit breaker landed this PR

PHASE 1 — Corpus + planner hardening
  [ ] source scoring (yield/redundancy/freshness) recorded during ingest
  [ ] source planner consumes scores (cheapest-high-signal, skip-redundant)
  [ ] content-addressed artifact store (C4)
  [ ] contract tests w/ recorded fixtures for existing adapters (C10)

PHASE 2 — Search family (C7)
  [ ] Brave, Mojeek, Mojeek-Org adapters (generic-spec where possible)
  [ ] SearXNG instance adapter ; Google-PSE + Bing as opt-in plugins
  [ ] dedupe/merge tuning across independent indexes

PHASE 3 — Passive + archive depth
  [ ] Censys cert/host, SecurityTrails history, Shodan, urlscan, CertSpotter (hand/generic)
  [ ] Wayback CDX depth + Common Crawl index (C6, redundancy-gated)
  [ ] DNS-history + passive-host recheck rules wired into frontier

PHASE 4 — Live crawl / JS / API / params (C1,C2,C3)
  [ ] Playwright render path ; source-map recovery ; AST JS extraction
  [ ] OpenAPI/Swagger/GraphQL discovery ; param-discovery loop ; smart wordlists
  [ ] favicon-hash pivot (C5)

PHASE 5 — Diff/monitor + AI validator + graph UI
  [ ] continuous schedule + CT-webhook trigger ; change events + alerts
  [ ] AI validator role + provenance-required guard ; live progress streaming
  [ ] Neo4j projection + pivot UI (C8) ; L3 concurrency + full convergence (C9)

PHASE 6 — Telemetry, replay, evidence
  [ ] OpenTelemetry traces/metrics ; structured logs ; checkpoints + replay
  [ ] evidence-pack export ; cost dashboard
```

### Implementation-step → phase map
1. canonical schema + raw store → P0/P1 · 2. source registry + contract → P0 ·
3. source planner → P1 · 4. corpus ingestion → P0/P1 · 5. normalize+dedupe → P0 ·
6. frontier manager → P0/P4 · 7. live validation → P0 · 8. crawl/JS/archive/search
recursion → P3/P4 · 9. diff+monitor → P5 · 10. AI supervisor + recovery → P5 ·
11. contract tests w/ fixtures → every phase (P1 onward) · 12. telemetry/replay → P6.
