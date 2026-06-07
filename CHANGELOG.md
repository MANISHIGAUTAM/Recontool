# Changelog

## [Unreleased] — 28-lane hardening + provider config + docker + CI

### Added
- **Full 28-lane coverage.** Every category now has at least one registered adapter
  (53 total). New declarative specs in `config/tools_generic.yaml` for cats
  4,7,8,9,10,11,12,13,14,15,16,17,18,19,23,26; new cat-28 `WordlistLearner`
  (`recontool/adapters/resources.py`) + learning engine (`recontool/learning.py`).
- **Provider configuration system** (`recontool/providers.py` + `config/providers.yaml`):
  23 providers across 12 source families, each with auth/base_url/endpoints/quota/
  retry/pagination/cache/mock-fixture/per-env-override. Pydantic-validated, secrets
  via env vars only, **fail-fast** on misconfiguration.
- **Recorded provider fixtures** (`tests/fixtures/providers/*`, loader in
  `recontool/testing/fixtures.py`) — 1 per provider; demo/test never call real APIs.
- **Structured logging + trace IDs** (`recontool/obs.py`): per-scan trace id bound to
  `scan_id`; JSON log stream; `scan.begin`/`phase.done` events.
- **CLI commands:** `config-validate`, `demo`, `replay-fixtures` (plus existing
  `preflight`, `diff`, `replay`).
- **Minimal-boot Docker:** rewritten `docker-compose.yml` (default zero-network demo,
  optional `full`/`mock` profiles), Dockerfile build-time self-test + HEALTHCHECK,
  `scripts/bootstrap.sh`, `scripts/compose-smoke.sh`.
- **CI** (`.github/workflows/ci.yml`): ruff + config-validate + replay-fixtures +
  unit/integration/e2e + preflight/demo smoke (py3.10/3.12) + compose-smoke job.
- **Dependency lockfile** (`requirements.lock`) + `full` extra in `pyproject.toml`.
- **Docs:** D16 (provider config), D17 (setup & docker), D18 (completion report),
  this CHANGELOG.
- **Tests:** +42 tests (85 → 127): providers, learning, fixtures/obs, new lanes,
  CLI, provider-fixture execution, error-handling paths.

### Changed
- Fixed adapter category labels: `naabu`→CAT-21, `js_analyze`→CAT-22, `nuclei`→CAT-27.
- `autoload` now registers `enabled:false` specs (lane completeness) but their
  `available()` returns False so they never run by default.
- `.env.example` expanded with `RECON_MODE`, all provider keys (grouped by family),
  and logging vars.
- `docker/install_tools.sh` adds sherlock, graphw00f, apkleaks, bbot, exiftool.
- Expanded the chain-completeness terminal-type set in `test_scope_and_registry.py`.

### Security / policy
- Authorized-only, no exploitation, no evasion preserved throughout.
- Secrets never stored in config — only env-var names; demo/test mode hard-blocks
  real egress (`LiveEgressBlocked`).

## [0.1.0] — initial platform
- Phased pipeline, normalizer/dedupe/confidence, scope + active gate, AI supervisor,
  rate limiter + circuit breaker + budget ledger, run modes (demo/test/live), mock
  environment, preflight, frontier manager, checkpoint/resume/dead-letter, diffing.
