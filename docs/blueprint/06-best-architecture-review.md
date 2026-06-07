# 06 — Architecture Review: Is This the Best? Gaps, Advancements & What I Implemented

## Verdict

Your diagram is **architecturally correct and close to best-in-class** for an
authorized recon platform: seed → policy gate → planner → 28 category sources → corpus
builder → normalize/dedupe → split graph + raw lake → frontier manager → live-validation
gate → per-host enrichment fan-out → new-frontier re-feed → prepared/controlled active
checks → findings → diff/report, with an AI supervisor and a test harness as
cross-cutting planes. That is the right shape.

It had **three real gaps** — and tellingly, they were the boxes that existed only as
shapes (no code): **C (Policy Engine + Demo/Test mode)**, **I (a true Frontier Manager)**,
and **U (Checkpoint/Resume/Dead-letter/Replay)**. Those are now implemented and tested.

---

## Gaps found (and status)

| # | Gap | Was | Now |
|---|-----|-----|-----|
| **A** | **Frontier Manager** was a phase-loop, not a real work-queue; no priority ordering, no explicit convergence/seen-set, no budget cap | implicit in `pipeline.py` | **`orchestrator/frontier.py`** — typed priority queue, monotonic `seen` set (guaranteed convergence), depth + item-budget caps, scope gating, stats (10 tests) |
| **B** | **Checkpoint / Resume / Dead-letter / Replay** (box U) absent | none | **`Checkpoint`** (atomic save/load), **`DeadLetter`** (capture exhausted/blocked jobs + replay), frontier `snapshot`/`restore` — resumable & idempotent (tests) |
| **C** | **Policy Engine + Demo/Test mode** (box C) — only had a scope check | `core/scope.py` only | **`core/policy.py`** — one decision point: scope + active-authorization attestation + **demo mode** restricted to a sanctioned public test allow-list (scanme.nmap.org, vulnweb, juice-shop, example.com, …) (6 tests) |
| **D** | Circuit breaker + budget ledger existed but weren't wired to the scheduler | `net/circuit.py` (prev PR) | now have a place to plug in: frontier + dead-letter + circuit + budget compose into run-state (wiring is the next pipeline change) |
| **E** | Source planner not registry-driven | heuristic in pipeline | `categories.route_seed` + `plan_order` (prev PR) give the planner real inputs; integration pending |

### Honest remaining gaps (designed, not yet wired into the live `pipeline.run`)
- The new `FrontierManager`/`Checkpoint`/`DeadLetter`/`PolicyEngine` are **standalone,
  tested components**; the running pipeline still uses its phase loop. Wiring them in
  (replace the loop with the frontier; gate with the policy engine; persist checkpoints
  per stage; route failures to the dead-letter) is the next integration step (roadmap P0).
- Content-addressed artifact lake, browser-render crawl, source-map/AST JS, OpenAPI/GraphQL
  discovery, search-family adapters, Common Crawl, Neo4j UI — still roadmap (`05` §Gaps).

---

## Advancements beyond the diagram (recommended)

1. **Convergence as a guarantee, not a hope.** The `seen` set makes the frontier a
   monotonic fixpoint over a finite in-scope entity space ⇒ provably terminates. (Done.)
2. **Demo/Test mode is now safety-enforced**, not just a label: in demo mode only
   published test targets are scannable, so the tool can be exercised without an owned
   asset and without risk. (Done.)
3. **Dead-letter + replay** turns transient provider failures into a recoverable queue
   instead of lost work. (Done.)
4. **Atomic checkpoints** (`os.replace`) mean no half-written state; resume is exact. (Done.)
5. **Priority frontier** expands cheap/high-signal hosts before expensive per-URL work —
   the "validate live before expensive enrichment" principle, enforced by the queue. (Done.)
6. **Future:** bandit-style source-score learning to auto-tune the planner; evidence-pack
   export; per-workspace self-hosted AI for sensitive data. (Roadmap.)

---

## The best architecture (refined diagram)

Same shape as yours, with the three gap-boxes now backed by real, tested components and
the reliability plane (circuit/budget/dead-letter) made explicit.

```
SEED ─► [C PolicyEngine: scope + auth attestation + demo/test gate]   (core/policy.py ✓)
          │
          ▼
        [D Source Planner: route_seed -> plan_order (priority), budget-aware]
          │   (categories.route_seed/plan_order ✓ ; budget/circuit wiring →)
          ▼
   28 CATEGORY SOURCES (search·passive·archive·code·crawl·...)  ──► [E Corpus Builder]
          │                                                            │
   reliability plane (per provider):  rate bucket · circuit breaker ·  │
   budget ledger · retry+backoff   (net/rate_limiter, net/circuit ✓)   │
          ▼                                                            ▼
                                   [F Normalize + Canonicalize + Dedupe]  (✓)
                                          │                 │
                              [G Canonical Graph]   [H Raw Artifact Lake]
                                          │                 │
                                          ▼                 ▼
                              [I FRONTIER MANAGER]  (orchestrator/frontier.py ✓)
                              priority queue · seen-set convergence · depth/budget caps
                                          │
                                          ▼
                              [J Live-Validation Gate] ─► [K Per-host enrichment fan-out
                                M1 crawl/JS/source-maps · M2 dir/content · M3 port/TLS ·
                                M4 API/GraphQL/param · M5 archive/search/code feedback ·
                                M6 identity/social/cloud/threat · M7 visual · M8 mobile]
                                          │ new entities
                                          ▼
                              [N New Frontier Entities] ──(re-feed)──► I   (converge)
                                          │
                                          ▼
                       [O Prepared Active Checks] ─► [P Controlled Active Validation]
                                          │   (gated by PolicyEngine.allow_active)
                                          ▼
                       [Q Findings + Evidence + Severity] ─► [R Diff / Reports / Export / Alerts]

  cross-cutting:  [S AI Supervisor: plan/validate(no-invented-evidence)/triage/recover]
                  [T Test Harness: unit/integration/e2e]   (81 tests ✓)
                  [U Checkpoint/Resume/Dead-letter/Replay]  (orchestrator/frontier.py ✓)
```

---

## What this PR implemented (tested)

| Component | File | Tests |
|-----------|------|-------|
| Frontier Manager (priority, dedupe-convergence, depth/budget, scope, snapshot/restore) | `recontool/orchestrator/frontier.py` | `tests/atomic/test_frontier.py` (10) |
| Dead-letter (capture + replay + persist) | same | included above |
| Checkpoint (atomic save/load/clear) | same | included above |
| Policy Engine (scope + auth attestation + demo/test allow-list) | `recontool/core/policy.py` | `tests/atomic/test_policy.py` (6) |

**Full suite: 81 passed.** Next integration step (roadmap P0): make `pipeline.run` consume
`PolicyEngine` at the gate, drive iteration with `FrontierManager`, checkpoint after each
stage, and route exhausted/broken jobs to `DeadLetter` — turning these tested components
into the live control plane.
