# D15 — Master Implementation & Testing Prompt

> A single, copy-pasteable prompt you can hand to an AI agent (or use as an
> engineering runbook) to (a) exercise the **entire** Recontool setup, config, and
> pipeline with full unit/integration/E2E testing, and (b) finish the remaining work
> to reach **100%** of the architecture spec. Self-contained: it states the repo
> conventions, the exact commands, and acceptance criteria.

---

## ===== BEGIN MASTER PROMPT =====

You are working in the **Recontool** repository: a config-driven, frontier-driven,
authorized-only reconnaissance & attack-surface-mapping platform (Python ≥3.10,
SQLAlchemy, httpx, typer, pytest). **Policy (non-negotiable):** authorized targets
only; no exploitation; **no stealth/proxy-rotation/rate-limit-bypass/evasion** —
reliability comes from quotas, backoff, caching, concurrency caps, and circuit
breakers. Preserve provenance for every entity/edge/artifact. Never store raw
secrets (hash + mask + location only).

### 0. Repo conventions you MUST follow
- Config precedence: **ENV var > `config/recontool.yaml` > built-in default** (use `_resolve`).
- Adapters are **pure**: they emit `Event`s; the **Normalizer is the only DB writer**.
- Every adapter separates a pure `parse()` from `run()` (so parsing is unit-testable offline).
- Graceful degradation: `available()` returns False when a binary/key is missing; never crash.
- Run mode is the top safety switch: `demo|test|live` (`recontool/core/mode.py`). In
  `demo`/`test` the HTTP chokepoint must serve from the mock env or raise `LiveEgressBlocked`.
- Style: ruff, line length 100, target py310. Tests must be **deterministic & network-free**.
- New tools should be added **declaratively** in `config/tools_generic.yaml` whenever
  possible (parsed by `recontool/adapters/generic.py`), not as bespoke Python.

### 1. Environment setup (do this first, verify each step)
```bash
python --version                      # must be >= 3.10 (repo pins 3.12 via .python-version)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"               # typer, httpx, sqlalchemy, pydantic, pytest,
                                      #   pytest-asyncio, respx, ruff, dnspython, pyyaml
cp config/recontool.example.yaml config/recontool.yaml   # optional; everything works without
```
Acceptance: `python -c "import recontool, recontool.cli"` succeeds; `recontool --help` lists
`scan, preflight, diff, replay, scans, report, export, tools`.

### 2. Static checks & full test run (baseline must stay green)
```bash
ruff check recontool                  # lint (fix any NEW violations you introduce)
python -m pytest tests/ -q            # MUST be all-green (currently 85 tests)
python -m pytest tests/atomic -q      # unit layer
python -m pytest tests/integration -q # chain/preflight/frontier/diff layer
python -m pytest tests/e2e -q         # full-pipeline-vs-mock layer
```
Acceptance: 0 failures, 0 errors; no test makes a real network call (enforced by run mode).

### 3. Exercise the FULL system manually (setup → config → working tool)
Run each and confirm the described behavior:
```bash
# 3a. Preflight validates config/registries/storage/db/queue/creds/mode/scope
recontool preflight recontool.local --mode demo            # expect all PASS, exit 0

# 3b. Full pipeline against the built-in MOCK (zero network) — all 6 phases
recontool scan recontool.local --mode demo --profile normal --authorize-active --no-ai
#     expect: p1..p6 run; live hosts > 0; endpoints > 0; secret findings (redacted) > 0

# 3c. Passive-only gating
recontool scan recontool.local --mode demo --profile passive_only
#     expect: active_ran=false; only p1..p3

# 3d. Resume (checkpoints skip completed phases)
recontool scan recontool.local --mode demo --profile passive_only            # note scan_id
recontool scan recontool.local --mode demo --profile passive_only --resume <scan_id>
#     expect: resumed=true; passive phases skipped

# 3e. Continuous-monitoring diff (deterministic mock -> no change)
recontool scan recontool.local --mode demo --profile passive_only
recontool diff recontool.local                                # expect changed=false

# 3f. Dead-letter inspection
recontool replay <scan_id>                                    # expect "No dead-letters"

# 3g. Export + report
recontool scan recontool.local --mode demo --profile normal --authorize-active -o /tmp/out.json
recontool report <scan_id>; test -s /tmp/out.json && python -m json.tool /tmp/out.json >/dev/null
```
Acceptance: every command behaves as annotated; `/tmp/out.json` is valid JSON containing
`assets`, `services`, `endpoints`, `findings`, `edges`.

### 4. Verify the architecture is fully wired (trace these in code/tests)
Confirm (and add a test if any assertion is not already covered):
- **Mode gate** precedes real egress; `demo/test` cannot touch the network
  (`tests/atomic/test_mode_and_egress.py`, `tests/e2e/test_demo_pipeline.py`).
- **Scope gate** merges seed-derived + `config.scope` allowlist; deny overrides allow.
- **Source planner**: `categories.route_seed(seed_type)` returns priority-ordered,
  valid category ids; chain_to targets exist (`tests/atomic/test_categories.py`).
- **28 lanes**: `categories.validate()` returns `[]`; all 28 present.
- **Corpus/normalize/dedupe**: re-discovery upserts (no dupes), confidence rises with
  independent sources (`tests/atomic/test_normalize.py`).
- **Frontier**: `FrontierManager.new_in_scope()` returns only NEW in-scope entities;
  `has_new()` is False after draining (`tests/integration/test_preflight_frontier_diff.py`).
- **Validate-before-enrich**: `p4_verify` sets `is_live` before `p5_deep` runs.
- **Re-feed loops**: links/JS/SANs discovered in `p5_deep` create new in-scope assets
  that the frontier surfaces (extend `MockEnv` HTML/JS to assert a new host appears).
- **Reliability**: `CircuitRegistry`/`BudgetLedger` enforced at the chokepoint
  (`CircuitOpen`/`BudgetExhausted`).
- **Recovery**: per-phase `Checkpoint`; adapter errors → `DeadLetter`.
- **Provenance/redaction**: `AssetSource` per (asset,tool); secret findings store
  `evidence_redacted` (sha1+mask+file), never the raw value.

### 5. Adapter test pattern (apply to EVERY adapter — definition of done)
For each adapter (existing or new):
1. **Unit**: feed a representative fixture to its pure `parse()`; assert the emitted
   `Event`s (types, dedupe-relevant fields, scope filtering, edges).
2. **Mock**: add a deterministic response for its provider/host in `MockEnv.handle()`.
3. **Integration**: run `adapter.run(ctx)` with a mock `HttpClient`, ingest via
   `Normalizer`, assert canonical rows + edges in the DB.
4. **Registry**: assert it registers in a valid phase and declares `consumes`/`produces`.
5. Network-free + deterministic. Add to the relevant `tests/` subfolder.

### 6. REMAINING WORK to reach 100% (implement in this order; keep tests green after each)

**G1 — Policy cleanup: retire proxy rotation.**
`net/proxy_pool.py` is deprecated by policy. Replace the rotating pool with a single
optional declared egress (e.g. a corporate allow-listed IP). Remove UA-randomization
framing that implies evasion; keep one stable, honest User-Agent. Update
`net/http_client.py` and any references. Tests: assert no rotation logic remains; a
single egress is used; existing tests still pass.

**G2 — Adapter breadth for the empty categories (declarative-first).**
Wire executable coverage for categories currently spec-only: **7 (email/identity),
8 (social), 11 (metadata/docs), 15 (geo/wireless), 16 (dark web), 26 (mobile/APK)**.
For each:
- Prefer a `config/tools_generic.yaml` spec (api/cli) mapping output → `emit` rules.
- Add a deterministic `MockEnv` handler for its provider.
- Add a unit test (parse/emit) + an integration test (chain → DB).
- Respect PII/legal gating for cat 7/16 (keep behind config toggles; short retention).
Acceptance: `recontool tools` shows ≥1 available adapter per category in `demo`; the
demo scan exercises them; per-category build checklist flips to ✅.

**G3 — Learned wordlists & regex packs (cat 28 feeds 20/23/25).**
Implement a generator that, from discovered tech (cat 5), paths (cat 6/11), and params
(cat 25), emits a tuned wordlist + regex pack written under `wordlists/` /
`regex_packs/` (content-addressed). Feed them into `content_discovery` (cat 20),
API/GraphQL (cat 23), and param discovery (cat 25). Tests: given a fixture corpus,
the generated wordlist contains learned tokens and dedupes; content discovery consumes it.

**G4 — Native graph DB mirror (optional backend).**
Add an optional Neo4j (or in-memory NetworkX for tests) mirror of the `Edge` table
behind an interface (`graph/store.py`) with `upsert_edge`, `neighbors`, `subgraph`.
Default stays SQL; enable via config. Tests: with the in-memory backend, edges written
by the Normalizer are queryable; traversal returns expected neighbors. Do NOT change
the canonical SQL store contract.

**G5 — Continuous-monitoring scheduler + alert sink.**
Add a `monitor` command/loop that re-scans a seed on an interval, runs `diff_scans`,
and emits changes to an alert sink (stdout/webhook/`notify`-style), with a clean
shutdown. Keep it idempotent and resumable. Tests: simulate two scans with a changed
mock surface; assert the scheduler reports the delta exactly once and is stable when
nothing changed.

### 7. Cross-cutting acceptance for the whole effort
- `python -m pytest tests/ -q` green; coverage added for every new module/adapter.
- `ruff check recontool` clean for all new/modified files.
- `recontool preflight recontool.local --mode demo` all PASS.
- The demo E2E (`docs/D12-demo-e2e-plan.md`) checklist passes end-to-end.
- No real network egress in any test or in `demo`/`test` mode (assert via
  `LiveEgressBlocked` and `MockEnv.calls`).
- Docs updated: regenerate `docs/categories/` (`python -m recontool.inventory.build_categories`),
  update `docs/D14-architecture-review-and-gaps.md` gap statuses, and the README test count.
- Update the per-category build checklist so newly wired categories show ✅.

### 8. Guardrails (do NOT do)
- Do not add exploitation, stealth, proxy rotation, rate-limit bypass, or evasion.
- Do not let the AI supervisor source/invent assets or findings (planner/triage only).
- Do not write raw secrets to disk/DB.
- Do not make tests depend on the network, real targets, or real credentials.
- Do not break the “Normalizer is the only DB writer” invariant.

## ===== END MASTER PROMPT =====

---

### How to use this
- **As an agent prompt:** paste everything between the BEGIN/END markers.
- **As a human runbook:** work sections 1→7 top to bottom; each has explicit acceptance
  criteria. Sections 1–5 validate the *existing* system; section 6 (G1–G5) completes the
  remaining architecture to 100%.
- **Current status reference:** see `docs/D14-architecture-review-and-gaps.md` for which
  items are ✅ done vs 🟡 remaining (G1–G5 above are the remaining set).
