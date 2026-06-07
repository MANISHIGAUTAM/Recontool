# Recontool

> Modular, AI-supervised **authorized reconnaissance & attack-surface mapping**
> platform. Give it a scope you own or are permitted to test — it chains a
> 500+-tool-class recon catalog into one config-driven, frontier-driven pipeline,
> stores everything in a canonical graph + artifact lake, runs tasks in parallel,
> and uses a tiered AI supervisor to plan, triage, and recover at runtime.

**Authorized-only, no-exploitation, no-evasion.** Recon & attack-surface mapping
only. No exploitation. No stealth, proxy rotation, rate-limit bypass, or detection
evasion — reliability comes from provider quotas, backoff, caching, concurrency
caps, and circuit breakers. Active phases that touch a target are off by default and
require an explicit `--authorize-active`. See [`docs/D6-opsec.md`](docs/D6-opsec.md)
and [`docs/blueprint/`](docs/blueprint/).

---

## What it does

```
  seed: domain / ip / cidr / asn / url
        │
        ▼  PREFLIGHT (config · registries · storage · db · queue · creds · scope)
        ▼  MODE GATE (demo | test | live)   →  SCOPE + AUTH GATE
        │
        ▼  PASSIVE (no target contact — safe, default)
   p1 seed        crt.sh · HackerTarget · OTX · urlscan · certspotter · Shodan/Censys…
   p2 expansion   subfinder/assetfinder (if installed) · recursion
   p3 enrichment  Wayback/gau URLs · InternetDB · ASN/BGP · GreyNoise
        │            ──►  corpus builder → normalize → dedupe → canonical store
        │            ──►  FRONTIER (recurse only on NEW in-scope entities)
        ▼  ◆ ACTIVE GATE (mode=live + active profile + --authorize-active)
   p4 verify      DNS resolve · HTTP probe · port scan  →  LIVE validation
   p5 deep        crawl + JS analysis (endpoints + redacted secrets) · dirs · params · TLS
   p6 vuln        nuclei / takeover (detection only)
        │
        ▼
   Deduplicated, confidence-scored inventory + findings + relationship graph
   + JSON export + AI summary + cross-scan diff
```

Each tool's output becomes the next tool's input (subdomains → resolve → probe →
crawl → analyse → re-feed). Everything is **deduplicated** with deterministic keys,
**confidence-scored** by independent-source corroboration, and **provenance-tracked**.

---

## Quick start

### Try it safely first (demo mode — zero network, zero keys)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Full pipeline against the built-in MOCK environment — never touches the network:
python -m recontool.cli demo recontool.local
```

This runs all six phases against `recontool/testing/mock_env.py`, discovering a
fictional attack surface (subdomains, IPs, live hosts, endpoints, and planted —
redacted — secrets). It's the safest way to see the whole system work.

### Minimal boot with Docker (one command)

```bash
cp .env.example .env          # fill in any API keys you have — ALL optional
docker compose up --build     # builds the image, runs a zero-network demo
```

Then run real (authorized) scans:

```bash
docker compose run --rm recontool scan acme.com --mode live                  # passive
docker compose run --rm recontool scan acme.com --mode live --authorize-active
```

### Real (authorized) targets — local

```bash
pip install -e .                       # provides the `recontool` command
bash docker/install_tools.sh core      # (optional) external CLIs: subfinder/httpx/nuclei/…
cp config/recontool.example.yaml config/recontool.yaml   # (optional) keys/scope/AI

recontool preflight acme.com --mode live          # validate setup
recontool scan acme.com --mode live                # passive (safe, default)
recontool scan acme.com --mode live --authorize-active -o results.json   # full pipeline
```

### Docker (ships with the recon CLIs)

```bash
docker compose build recontool
docker compose run --rm recontool scan acme.com --mode live
```

---

## Run modes (the top-level safety switch)

| Mode | Real egress | Use |
|------|:-----------:|-----|
| `demo` | ❌ never | Full pipeline vs in-process mock. Safe demo anywhere, no keys. |
| `test` | ❌ never | Recorded fixtures / mock for CI & E2E. Hard-fails on egress leak. |
| `live` | ✅ authorized | Real targets, still scope + active-auth gated. |

In `demo`/`test`, the single HTTP egress chokepoint routes every request to the mock
env or raises `LiveEgressBlocked` — a hard guarantee no real target is touched.

---

## CLI

```bash
recontool preflight <seed> --mode <mode>     # health checks (exit 2 on error)
recontool config-validate --env <env>        # validate provider configs (fail-fast)
recontool scan <seed> [-p profile] [-m mode] [--authorize-active]
                       [-c 1,2,3] [--resume <id>] [--skip-preflight] [-o out.json]
recontool demo [seed]                        # full pipeline vs mock (zero network)
recontool scans                              # list past scans
recontool report <scan_id>                   # summary + findings
recontool export <scan_id> -o out.json       # full JSON export
recontool diff <seed>                        # diff the two latest scans (monitoring)
recontool replay <scan_id>                   # inspect dead-lettered (failed) work units
recontool replay-fixtures                    # validate recorded provider fixtures
recontool tools                              # all adapters + current availability
```

Profiles: `passive_only` · `stealth` · `normal` · `aggressive` (one knob tunes
concurrency, QPS, port breadth, jitter, nuclei severity for the whole pipeline).

---

## Configuration

Precedence: **environment variable → `config/recontool.yaml` → built-in default.**
All API keys are **optional** — passive recon runs with zero keys.

| File | Purpose |
|------|---------|
| `config/recontool.yaml` | Main config — mode, profile, **scope allowlist**, API keys, AI, recovery, categories. Copy from `recontool.example.yaml`. **Gitignored.** |
| `config/providers.yaml` | **Provider registry** — one validated block per external source family (auth/base_url/endpoints/quota/retry/pagination/cache/mock fixture). Secrets via env vars only. |
| `config/tools.yaml` | Machine-readable **tool registry** — invocation/IO/install per tool. |
| `config/tools_generic.yaml` | **Declarative adapter specs** — wire tools with no Python. |
| `config/categories.yaml` | The **28-category registry** (contracts, dedupe keys, chain_to, quotas). |

Validate provider config (fails fast on a misconfigured enabled provider):

```bash
recontool config-validate --env live    # checks secrets + base_url for enabled providers
recontool config-validate --env demo     # checks mock fixtures (no secrets needed)
```

```yaml
# config/recontool.yaml (excerpt)
general: { mode: live, profile: normal }
scope:
  allow_domains: ["acme.com"]
  deny_domains: ["status.acme.com"]
recovery: { checkpoint_enabled: true }
api_keys: { shodan: "...", securitytrails: "...", github_token: "..." }
```

---

## Architecture at a glance

| Capability | Module |
|------------|--------|
| **Run mode + test-mode egress enforcement** | `core/mode.py`, `net/http_client.py` |
| **Provider config** (validated, env-mapped, fail-fast) | `providers.py`, `config/providers.yaml` |
| **Structured logs + trace IDs** | `obs.py` |
| **Mock / demo environment** | `testing/mock_env.py`, `testing/fixtures.py` |
| **Preflight health checks** | `preflight.py` |
| **Source planner / 28-category registry** | `categories.py`, `config/categories.yaml` |
| **Tool chaining + parallel phases** | `orchestrator/pipeline.py` |
| **Frontier manager** (recurse only on new in-scope entities) | `orchestrator/frontier.py` |
| **Generic adapter engine** (wire tools as YAML, no code) | `adapters/generic.py`, `adapters/autoload.py` |
| **Pure-Python crawler / content discovery / param mining** | `adapters/{crawler,content_discovery,params}.py` |
| **Normalize / dedupe / confidence** (sole DB writer) | `normalize/engine.py`, `core/{dedupe,confidence}.py` |
| **Canonical store + raw artifact lake** | `core/models.py`, `core/artifacts.py` |
| **Checkpoint / resume / dead-letter / replay** | `core/models.py` (Checkpoint, DeadLetter), pipeline, CLI `replay` |
| **Continuous diffing** | `diff.py`, CLI `diff` |
| **Rate limit · circuit breaker · budget ledger** | `net/{rate_limiter,circuit}.py` |
| **Scope + active gate** | `core/scope.py`, `orchestrator/pipeline.py` |
| **AI supervisor** (light/heavy routing, heuristic fallback) | `ai/{router,supervisor}.py` |
| **Reporting / export** | `report.py`, `cli.py` |

Full design + flow diagram: [`docs/D14-architecture-review-and-gaps.md`](docs/D14-architecture-review-and-gaps.md)
and [`docs/00-architecture-overview.md`](docs/00-architecture-overview.md).

---

## Tests

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q          # 127 tests, all network-free

python -m pytest tests/atomic -q        # unit: parsers, scope, dedupe, circuit, mode,
                                        #       providers, learning, fixtures, obs
python -m pytest tests/integration -q   # chains, preflight, frontier, diff, lanes, CLI,
                                        #       provider fixtures, error handling
python -m pytest tests/e2e -q           # full pipeline vs mock + fixture regression
ruff check recontool tests
```

- **Atomic/unit** — every adapter parser, canonicalizer, planner rule, scope,
  circuit/budget, run-mode + egress gating.
- **Integration** — discovery→normalize→DB chains, preflight, frontier delta, diff.
- **E2E** — the whole pipeline against the deterministic mock; resume/checkpoint;
  fixture regression; **proof that demo/test mode cannot touch a real target**.

See [`docs/D11-testing-strategy.md`](docs/D11-testing-strategy.md),
[`docs/D12-demo-e2e-plan.md`](docs/D12-demo-e2e-plan.md), and
[`docs/D13-operator-runbook.md`](docs/D13-operator-runbook.md).

---

## Tool inventory & execution flow (generated)

The full `ReconTools` catalog is captured exhaustively (every row preserved,
deduplicated to canonical records with provenance), and the end-to-end execution
flow is generated from it.

```bash
python -m recontool.inventory.build_inventory     # data/ + docs/inventory/ + docs/tools/
python -m recontool.inventory.build_flow          # docs/flow/ + data/flow_plan.json
python -m recontool.inventory.build_categories     # docs/categories/ (28-category contracts)
```

| Artifact | What it is |
|----------|-----------|
| [`data/recontools_raw.tsv`](data/recontools_raw.tsv) | Source of truth — 614 rows, 19 sections, verbatim. |
| [`data/tool_inventory.json`](data/tool_inventory.json) | 532 canonical tools + derived tags + provenance. |
| [`docs/inventory/TOOL-INVENTORY.md`](docs/inventory/TOOL-INVENTORY.md) | Human-readable inventory. |
| [`docs/tools/`](docs/tools/) | One capability doc per canonical tool. |
| [`docs/flow/00-MASTER-FLOW.md`](docs/flow/00-MASTER-FLOW.md) | Master execution diagram + per-category tables. |
| [`docs/categories/`](docs/categories/) | 28-category build-ready contracts + checklist. |

**Extracted vs suggested.** Everything in the inventory is `extracted_from_spreadsheet`
and never altered; recommended additions live separately in
[`docs/pipeline/01-gap-analysis.md`](docs/pipeline/01-gap-analysis.md).

---

## Adding a tool at scale (no Python)

Most of the 500+ tools are wired **declaratively** in
[`config/tools_generic.yaml`](config/tools_generic.yaml); a tested generic executor
([`adapters/generic.py`](recontool/adapters/generic.py)) runs and parses them into the
canonical schema. Hand-written adapters exist only for the highest-value tools and
win on name collisions.

```yaml
- name: certspotter
  phase: p1_seed
  category: 2
  integration: api
  consumes: [domain]
  produces: [subdomain]
  endpoint: "https://api.certspotter.com/v1/issuances?domain={domain}&include_subdomains=true&expand=dns_names"
  parse:
    format: json
    emit:
      - {entity: asset, value_each: dns_names, type: subdomain, scope_filter: subdomain}
```

---

## Storage layout

```
recontool.db                 # SQLite (default) — switch to Postgres via RECON_DB_URL
artifacts/<scan_id>/
  ├── raw/<tool>/*.json       # raw tool/API output (provenance)
  ├── js/<host>/*.js          # JS harvested from Wayback / crawler
  ├── bodies/<host>/*         # response bodies
  ├── screenshots/*.png       # gowitness (if installed)
  └── nuclei_targets.txt
```

Canonical entities (assets, services, endpoints, findings, edges), plus
`checkpoint`, `dead_letter`, and `audit_log`, live in the DB. Schema:
[`docs/D3-data-schema.md`](docs/D3-data-schema.md).

---

## Docs index

- Architecture: [`docs/00-architecture-overview.md`](docs/00-architecture-overview.md),
  [`docs/D14-architecture-review-and-gaps.md`](docs/D14-architecture-review-and-gaps.md)
- Flow: [`docs/D2-recon-flow.md`](docs/D2-recon-flow.md), [`docs/flow/`](docs/flow/)
- Data schema: [`docs/D3-data-schema.md`](docs/D3-data-schema.md)
- OPSEC & policy: [`docs/D6-opsec.md`](docs/D6-opsec.md), [`docs/blueprint/`](docs/blueprint/)
- **Testing:** [`docs/D11-testing-strategy.md`](docs/D11-testing-strategy.md)
- **Demo E2E:** [`docs/D12-demo-e2e-plan.md`](docs/D12-demo-e2e-plan.md)
- **Operator runbook:** [`docs/D13-operator-runbook.md`](docs/D13-operator-runbook.md)
- **Provider config:** [`docs/D16-provider-config.md`](docs/D16-provider-config.md)
- **Setup & Docker:** [`docs/D17-setup-and-docker.md`](docs/D17-setup-and-docker.md)
- Pipelines & categories: [`docs/pipeline/`](docs/pipeline/), [`docs/categories/`](docs/categories/)
- Roadmap & risks: [`docs/D7-roadmap.md`](docs/D7-roadmap.md), [`docs/D10-risk-register.md`](docs/D10-risk-register.md)
