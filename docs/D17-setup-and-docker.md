# D17 — Setup, Docker & Minimal Boot

> The operator experience is intentionally minimal: drop in API keys (optional),
> run one command, use the platform. This doc covers local and container setup,
> the bootstrap path, CI, and reproducibility.

## 1. Minimal boot (the happy path)

```bash
cp .env.example .env          # fill in any API keys you have — ALL optional
docker compose up --build     # builds the image, runs a zero-network demo
```

The default `recontool` service command is `demo recontool.local`, so a fresh
`up --build` proves the whole stack end-to-end without any keys or network.

Then run real scans:

```bash
docker compose run --rm recontool scan acme.com --mode live                  # passive
docker compose run --rm recontool scan acme.com --mode live --authorize-active
```

## 2. Bootstrap scripts

```bash
bash scripts/bootstrap.sh           # local: pip install + validate + demo
bash scripts/bootstrap.sh docker    # docker: build + demo in-container
bash scripts/compose-smoke.sh       # validate compose + build + zero-network demo
```

## 3. Local (no Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"             # or: pip install -r requirements.lock  (pinned)
bash docker/install_tools.sh core   # optional external CLIs (subfinder/httpx/nuclei/…)
recontool config-validate --env demo
recontool demo recontool.local
```

## 4. docker-compose services

| Service | Profile | Purpose |
|---------|---------|---------|
| `recontool` | (default) | the orchestration app; bundles recon CLIs; default cmd = zero-network demo |
| `postgres` | `full` | optional PostgreSQL canonical store (set `RECON_DB_URL`) |
| `redis` | `full` | optional Redis for distributed rate-limit buckets (set `RECON_REDIS_URL`) |
| `mockserver` | `mock` | optional out-of-process mock for dev |

```bash
docker compose --profile full up -d postgres redis   # bring up backing services
```

SQLite + in-process queue are the zero-config defaults, so none of the optional
services are required for normal use.

## 5. Image build self-test

The `Dockerfile` runs a build-time self-test that **fails the build** if the stack
is broken offline:

```dockerfile
RUN RECON_MODE=demo recontool config-validate --env demo \
 && RECON_MODE=demo RECON_ARTIFACT_DIR=/tmp/build-demo recontool demo recontool.local
HEALTHCHECK ... CMD recontool config-validate --env demo || exit 1
```

## 6. Tool installation

`docker/install_tools.sh` installs the external recon CLIs (idempotent, graceful):

```bash
bash docker/install_tools.sh core        # subfinder, httpx, dnsx, naabu, nuclei, asnmap, uncover, gau
bash docker/install_tools.sh all         # + katana, tlsx, ffuf, gowitness, sherlock, graphw00f,
                                          #   apkleaks, bbot, exiftool, sslyze, gitleaks, SecLists …
```

Adapters whose binary/key is absent report unavailable and are skipped — the
pipeline never crashes on a missing tool.

## 7. Reproducibility

- `requirements.lock` pins exact versions (`pip install -r requirements.lock`).
- `pyproject.toml` declares ranges + extras (`dev`, `full`, `ai`, `postgres`, `redis`).
- The Docker image pins the base (`golang:1.23-bookworm`) and installs from the
  same requirements.

## 8. CI gates (`.github/workflows/ci.yml`)

`lint-and-test` (Python 3.10 + 3.12 matrix):
1. `ruff check recontool tests`
2. `recontool config-validate --env demo` and `--env test`
3. `recontool replay-fixtures`
4. `pytest tests/atomic`, `tests/integration`, `tests/e2e`
5. `recontool preflight recontool.local --mode demo`
6. `recontool demo recontool.local`

`compose-smoke`: `bash scripts/compose-smoke.sh` (validate compose + build + demo).

All gates are network-free (`RECON_MODE=test`), so CI needs no secrets.

## 9. Environment variables

See `.env.example` for the complete list, grouped by family. Key ones:

| Var | Meaning |
|-----|---------|
| `RECON_MODE` | `demo` / `test` / `live` |
| `RECON_DB_URL` | SQLite (default) or PostgreSQL DSN |
| `RECON_ARTIFACT_DIR` | artifact lake path |
| `RECON_PROFILE` | `passive_only` / `stealth` / `normal` / `aggressive` |
| `RECON_LOG_FORMAT` / `RECON_LOG_LEVEL` | structured logging |
| `<PROVIDER>_API_KEY` | per-provider secrets (all optional) |
