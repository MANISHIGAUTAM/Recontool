# D11 — Testing Strategy

> How Recontool is validated end-to-end: what we test, at which layer, and how to
> run it. Authorized-only, no-evasion platform; **no test ever touches a real
> target** (enforced by run-mode, see `recontool/core/mode.py`).

## 1. Test pyramid

```
            ┌─────────────────────────────┐
            │  E2E (tests/e2e/)           │  full pipeline vs MOCK env, fixture
            │  ~8 tests                   │  regression, egress-block proof
            ├─────────────────────────────┤
            │  Integration (tests/integration/) │  adapter→normalizer→DB chains,
            │  ~9 tests                   │  preflight, frontier, diff
            ├─────────────────────────────┤
            │  Atomic / unit (tests/atomic/)    │  pure parse(), scope, dedupe,
            │  ~70 tests                  │  circuit, mode, generic engine
            └─────────────────────────────┘
```

| Layer | Location | Scope | Network | Speed |
|-------|----------|-------|:-------:|:-----:|
| Atomic/unit | `tests/atomic/` | one function/class in isolation | none | <1ms |
| Integration | `tests/integration/` | one discovery→enrichment chain + DB | mock only | ~100ms |
| E2E | `tests/e2e/` | the whole pipeline (all 6 phases) | mock only | ~1s |

## 2. What each layer guarantees

### Atomic / unit (`tests/atomic/`)
- **Parsers** — every adapter's pure `parse()` against a representative fixture
  (`test_cat01_parsers.py`, `test_generic_engine.py`). Proves output→Event mapping.
- **Canonicalization & dedupe** — `test_scope_and_registry.py`, `test_normalize.py`:
  deterministic dedupe keys, idempotent upsert, noisy-OR confidence.
- **Scope** — allow/deny precedence, CIDR, subdomain false-positive rejection.
- **Planner rules** — `test_categories.py`: 28-category registry integrity, seed
  routing order, chain_to validity, active-flag correctness.
- **Reliability primitives** — `test_circuit.py`: breaker state machine + budget ledger.
- **Run-mode & egress** — `test_mode_and_egress.py`: mode parsing, demo/test egress
  gating, circuit/budget enforcement at the HTTP chokepoint.

### Integration (`tests/integration/`)
- **Discovery→normalize→DB chains** (`test_chains.py`): crt.sh→assets,
  hackertarget→resolves_to edges, internetdb→service+finding — using the **real**
  Normalizer and DB, mock HTTP only.
- **Preflight / frontier / diff** (`test_preflight_frontier_diff.py`): preflight
  passes for a valid setup; frontier surfaces only *new* in-scope entities; diff
  detects added/removed between two scans.

### E2E (`tests/e2e/`)
- **Full demo pipeline** (`test_demo_pipeline.py`): seed → 6 phases → live hosts,
  endpoints, redacted secrets — entirely against `MockEnv`.
- **Resume / checkpoint**: phases checkpoint; resume skips completed phases.
- **Egress enforcement**: `test`-mode without a mock env raises `LiveEgressBlocked`.
- **Fixture regression** (`test_fixture_regression.py`): the deterministic mock
  scan's canonical shape (asset-type counts, live count, finding kinds) is stable
  across runs and meets a minimum-surface floor.

## 3. The mock environment (recorded fixtures)

`recontool/testing/mock_env.py` is the single source of deterministic fixtures.
`MockEnv(apex)` answers any URL the pipeline may request:

- **Third-party providers**: crt.sh, hackertarget, AlienVault OTX, urlscan,
  Shodan InternetDB, Wayback CDX.
- **The demo target hosts**: HTML pages (with in-scope links + a form), `robots.txt`,
  and JS files containing in-scope endpoints, a new host, and **planted fake secrets**
  (so secret-detection + redaction are exercised without any real secret).

All generated hosts are subdomains of the demo apex, so the scope gate keeps the
whole exercise inside the sandbox. The mock is deterministic → it doubles as the
recorded-fixture regression baseline.

## 4. Test-mode enforcement (safety guarantee)

The run mode is the highest safety switch (above scope + active-auth gates):

| Mode | Real egress | Transport |
|------|:-----------:|-----------|
| `demo` | ❌ never | in-process `MockEnv` |
| `test` | ❌ never | mock/fixtures; **hard-fails** if a call escapes the mock |
| `live` | ✅ (authorized) | real HTTP, still scope + auth gated |

In `demo`/`test`, the HTTP chokepoint (`net/http_client.py`) routes every request to
the mock env, or raises `LiveEgressBlocked` if none is wired. This is asserted by
`test_test_mode_blocks_live_egress_without_mock`.

## 5. Preflight (pre-run validation)

`recontool preflight <seed> --mode demo` validates config, category & tool
registries, artifact storage, database, queue, credentials, mode, and scope before
a scan. `scan` runs preflight automatically (exit code 2 on failure unless
`--skip-preflight`).

## 6. Running the tests

```bash
pip install -e ".[dev]"          # pytest, pytest-asyncio, respx, ruff
python -m pytest tests/ -q       # everything (atomic + integration + e2e)
python -m pytest tests/atomic -q         # fast unit layer
python -m pytest tests/integration -q    # chains + preflight + frontier + diff
python -m pytest tests/e2e -q            # full pipeline vs mock
ruff check recontool               # lint
```

CI should run `ruff check` then `python -m pytest tests/`. All layers are
network-free, so CI needs no secrets and no outbound connectivity.

## 7. Adding tests for a new adapter (definition of done)

1. **Unit**: a `parse()`/pure-function test with a representative fixture payload.
2. **Mock**: extend `MockEnv.handle()` with a deterministic response for the
   provider/host the adapter calls.
3. **Integration**: assert the adapter→Normalizer→DB chain produces the expected
   canonical records and edges.
4. **Registry**: confirm it registers in a valid phase and declares `consumes`.
5. Keep it **deterministic** and **network-free**.

## 8. Coverage map (requirement → test)

| Spec requirement | Test(s) |
|------------------|---------|
| unit tests for every adapter/parser/canonicalizer/planner rule | `tests/atomic/*` |
| integration tests for each discovery→enrichment chain | `tests/integration/test_chains.py` |
| E2E tests using a demo/mock environment | `tests/e2e/test_demo_pipeline.py` |
| recorded-fixture regression tests | `tests/e2e/test_fixture_regression.py` + `MockEnv` |
| preflight health checks | `tests/integration/test_preflight_frontier_diff.py` |
| test-mode enforcement (no live target touched) | `test_demo_pipeline.py`, `test_mode_and_egress.py` |
