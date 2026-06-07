# Recontool

> Modular, AI-supervised **reconnaissance & attack-surface mapping** platform.
> Give it a domain — it chains 200+-tool-class recon together, stores everything
> in a database, harvests artifacts (JS, response bodies) to the filesystem,
> rotates egress IPs to dodge rate-limit blacklisting, runs tasks in parallel,
> and uses a tiered AI agent to make better decisions at runtime.

**Scope guardrail:** reconnaissance & attack-surface mapping only — no
exploitation. Active phases that touch a target are disabled by default and
require an explicit `--authorize-active` flag. See [`docs/D6-opsec.md`](docs/D6-opsec.md).

---

## What it does

```
  www.xyz.com
        │
        ▼  PASSIVE (no target contact — safe, default)
   P1 seed        crt.sh · HackerTarget · AlienVault OTX
   P2 expansion   subfinder (if installed) · recursion
   P3 enrichment  Wayback URLs  ──►  downloads .js files to ./artifacts
        │
        ▼  ◆ ACTIVE GATE (requires --authorize-active)
   P4 verify      DNS resolve · HTTP probe · port scan (naabu or fallback)
   P5 deep        JS analysis (endpoints + redacted secrets from harvested JS)
   P6 vuln        nuclei (if installed) · CVE/exposure findings
        │
        ▼
   Deduplicated, confidence-scored asset inventory in the DB
   + findings + relationship graph + JSON export + AI summary
```

Each tool's output becomes the next tool's input (subdomains → resolve → probe →
crawl → analyse). Everything is **deduplicated** with deterministic keys and
**confidence-scored** by how many independent sources corroborate it.

The full architecture lives in [`docs/`](docs/) (D1–D10: tool matrix, flow, data
schema, ADRs, API specs, OPSEC, roadmap, build-vs-buy, code structure, risks).

---

## Quick start

### Option A — Docker (recommended; ships with all recon tools)

```bash
# build the all-in-one image (Python platform + subfinder/httpx/nuclei/naabu/...)
docker compose build recontool

# passive scan — just pass a scope domain
docker compose run --rm recontool scan www.xyz.com

# full pipeline against an AUTHORISED target
docker compose run --rm recontool scan xyz.com --profile stealth --authorize-active
```

### Option B — local (Python 3.10+)

```bash
# 1. install the platform
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .                      # provides the `recontool` command

# 2. (optional) install the external CLI tools (subfinder, httpx, nuclei, ...)
bash docker/install_tools.sh core     # or `all` for the full set

# 3. (optional) configure API keys / proxies / AI
cp config/recontool.example.yaml config/recontool.yaml   # everything works WITHOUT this

# 4. RUN — the platform is driven by a single scope domain
recontool scan www.xyz.com                               # passive (safe, default)
recontool scan xyz.com --authorize-active -o results.json # full pipeline (authorised)
```

If you don't `pip install -e .`, run it as a module: `python -m recontool.cli scan www.xyz.com`.

### Inspect results

```bash
recontool tools              # all adapters + which are available right now
recontool scans              # past scans
recontool report <scan_id>   # summary of a stored scan
recontool export <scan_id> -o out.json
```

---

## Configuration

Two config files live in `config/`:

| File | Purpose |
|------|---------|
| `config/recontool.yaml` | Main config — API keys, profile, proxies, AI, enabled categories. Copy from `recontool.example.yaml`. **Gitignored.** |
| `config/tools.yaml` | Machine-readable **tool registry** — every tool's invocation, input/output, install method. The integration backbone. |

**Precedence:** environment variable → `config/recontool.yaml` → built-in default. So you
can keep secrets in env vars (CI) or in the YAML file (local). All keys are **optional** —
passive recon runs with zero keys; adding keys unlocks more sources and higher limits.

```yaml
# config/recontool.yaml (excerpt)
general: { profile: normal }
network: { proxies: ["http://user:pass@proxy1:8080", "socks5://proxy2:1080"] }
api_keys:
  shodan: "..."
  securitytrails: "..."
  github_token: "..."
```

---

## Running by category (pipeline model)

The platform is built as **per-category pipelines** that chain tools (A's output → B's
input) through a shared DB. You drive everything with a scope domain:

```bash
recontool scan www.xyz.com                  # default preset (passive categories)
recontool scan www.xyz.com --category 2     # run ONLY the Cat-2 subdomain pipeline
recontool scan www.xyz.com --authorize-active   # unlock active categories
```

See the full design in [`docs/pipeline/`](docs/pipeline/):
- `01-gap-analysis.md` — missing tools/categories we added (content discovery, port
  scanning, JS analysis, API/GraphQL, TLS, param discovery).
- `02-plan-of-action.md` — pipeline model, A→B→C chaining, atomic-check methodology.
- `03-category-pipelines.md` — the tool flow for every category.
- `04-tool-catalog.md` — capability / invocation / output per tool.
- `05-flow-architecture.md` — tool-by-tool data handoffs + parallelization map.
- `06-recursive-flow.md` — the convergence engine: passive → validate-live → active on
  live hosts only → feed discoveries back → loop until convergence; console/UI display.
- `07-tool-io-reference.md` — per-tool invocation, sample output, and DB/filesystem storage.
- `08-feature-advancements.md` — ranked roadmap of enhancements beyond the current design.

---

## Tool inventory (every spreadsheet tool, normalized)

The complete `ReconTools` spreadsheet is captured **exhaustively** — every row is
preserved and deduplicated into canonical records, with all category memberships and
raw row references kept.

```bash
# regenerate the inventory + per-tool docs from the source-of-truth TSV
python -m recontool.inventory.build_inventory
```

| Artifact | What it is |
|----------|-----------|
| [`data/recontools_raw.tsv`](data/recontools_raw.tsv) | **Source of truth** — every spreadsheet row, verbatim (614 rows, 19 sections). |
| [`data/tool_rows_raw.json`](data/tool_rows_raw.json) | All raw rows with stable row ids (machine-readable). |
| [`data/tool_inventory.json`](data/tool_inventory.json) | Canonical deduplicated tools (532) + derived tags + provenance. |
| [`docs/inventory/TOOL-INVENTORY.md`](docs/inventory/TOOL-INVENTORY.md) | Human-readable inventory: summary, per-section index, master table, duplicates, aliases. |
| [`docs/tools/`](docs/tools/) | One capability doc per canonical tool (purpose, classification, invocation, I/O, failure modes, confidence, pipeline position). |

**Counts:** 614 raw rows → **532 canonical tools** (82 duplicate rows collapsed),
across 19 sections; 68 tools span multiple categories; 82 are web/GUI-only.

**Extracted vs suggested.** Everything in the inventory is `extracted_from_spreadsheet`
and never altered. Genuinely missing categories/tools we *recommend adding* are kept
separate in [`docs/pipeline/01-gap-analysis.md`](docs/pipeline/01-gap-analysis.md) and
are never merged into the extracted inventory.

### How the inventory maps to the rest of the system

| Spec deliverable | Where it lives |
|------------------|----------------|
| Exhaustive tool inventory | `data/` + `docs/inventory/` + `docs/tools/` (this section) |
| Category taxonomy & gaps | `docs/pipeline/01-gap-analysis.md` |
| Orchestration architecture | `docs/00-architecture-overview.md`, `docs/D2-recon-flow.md`, `docs/D4-adr.md` |
| Category-by-category pipelines | `docs/pipeline/03-category-pipelines.md`, `05-flow-architecture.md` |
| Recursive passive→live→active flow | `docs/pipeline/06-recursive-flow.md` |
| Normalized output contract | `docs/D3-data-schema.md`, `recontool/normalize/` |
| Config system + `.env` | `config/recontool.example.yaml`, `.env.example`, `recontool/config.py` |
| Setup / bootstrap (Docker) | `Dockerfile`, `docker/install_tools.sh`, `docker-compose.yml` |
| First passive pipeline + atomic checks | `recontool/adapters/` (Cat-1) + `tests/atomic/` |
| Rollout plan | `docs/D7-roadmap.md`, `docs/pipeline/02-plan-of-action.md` |
| Advanced improvements | `docs/pipeline/08-feature-advancements.md` |

---

## Execution flow (root domain → every tool)

Want to see exactly how all 532 tools execute from a single root domain, with each
tool's **invocation method (binary/API/web), flags/params, expected output, where it
feeds next, and where it's stored**? That's generated too:

```bash
python -m recontool.inventory.build_flow      # regenerates the flow from inventory + tools.yaml
```

| Artifact | What it is |
|----------|-----------|
| [`docs/flow/00-MASTER-FLOW.md`](docs/flow/00-MASTER-FLOW.md) | Master execution diagram (ASCII + Mermaid), stage pipeline, category→stage map, and a worked `xyz.com` cardinality example. |
| [`docs/flow/by-category/NN.md`](docs/flow/by-category/) | Per-category execution table: **every tool** → method, command/endpoint with flags, consumes, produces, feeds-next, storage (DB table + artifact path). |
| [`data/flow_plan.json`](data/flow_plan.json) | Machine-readable execution plan for all 532 tools. |

Invocations are **authoritative** where a contract exists in `config/tools.yaml` (e.g.
`subfinder -d xyz.com -all -silent -oJ`, `crt.sh/?q=%25.xyz.com&output=json`), and
**templated** (marked `(t)`) for tools not yet wired — clearly distinguished so you know
what's ready vs. what needs a flag confirmed. The flow enforces the core rule: passive
discovery runs on the root, then **active scans run only on live hosts** (see
[`docs/pipeline/06-recursive-flow.md`](docs/pipeline/06-recursive-flow.md)).

---

## Adding tools at scale (generic adapter engine)

Most of the 500+ tools are wired **declaratively** — no Python. A tool is a YAML spec in
[`config/tools_generic.yaml`](config/tools_generic.yaml) that a tested generic executor
([`recontool/adapters/generic.py`](recontool/adapters/generic.py)) runs and parses into
the normalized schema. Hand-written adapters exist only for the highest-value/complex
tools and always win on a name collision.

```yaml
# add a tool in ~10 lines — it auto-registers into the pipeline on next run
- name: certspotter
  phase: p1_seed
  category: 2
  integration: api          # or cli
  consumes: [domain]
  produces: [subdomain]
  endpoint: "https://api.certspotter.com/v1/issuances?domain={domain}&include_subdomains=true&expand=dns_names"
  parse:
    format: json
    emit:
      - {entity: asset, value_each: dns_names, type: subdomain, scope_filter: subdomain}
```

The parse engine (`parse_records` + `emit_events`) is pure and unit-tested against
fixtures, so every spec's output mapping is validated without network/subprocess. See
[`docs/pipeline/09-category-milestones.md`](docs/pipeline/09-category-milestones.md) for
per-category status and [`docs/pipeline/10-gaps-and-advancements.md`](docs/pipeline/10-gaps-and-advancements.md)
for gaps found + advancements.

---

## Setup: external tools & resources

`docker/install_tools.sh` downloads and installs the recon CLIs (graceful — Recontool
works without any of them, adapters just report unavailable):

```bash
bash docker/install_tools.sh core        # default-on set: subfinder, httpx, dnsx, naabu,
                                          #   nuclei, asnmap, uncover, gau (+ templates)
bash docker/install_tools.sh all         # full set + SecLists wordlists + resolver list
bash docker/install_tools.sh resources   # just wordlists + clean DNS resolvers
```

---

## Key capabilities (and where they live)

| Capability | Module |
|------------|--------|
| **Tool chaining** (output → input across phases) | `orchestrator/pipeline.py` |
| **Parallel execution** (adapters fan out per phase) | `orchestrator/pipeline.py` |
| **IP / proxy rotation** (avoid blacklisting) | `net/proxy_pool.py` |
| **Rate limiting** (per-provider token buckets) | `net/rate_limiter.py` |
| **DB storage** (subdomains, IPs, params, services, findings) | `core/models.py`, `normalize/engine.py` |
| **Filesystem artifacts** (JS from Wayback, bodies, raw output) | `core/artifacts.py` |
| **Dedup + confidence scoring** | `core/dedupe.py`, `core/confidence.py` |
| **Scope + passive→active safety gate** | `core/scope.py`, `orchestrator/pipeline.py` |
| **AI agentic supervisor** (light/heavy model routing) | `ai/router.py`, `ai/supervisor.py` |

### IP rotation
Set `RECON_PROXIES` in `.env` to a comma-separated list of proxy URLs
(`http://user:pass@host:port`, `socks5://host:port`). The pool rotates across
them (`round_robin` / `random` / `sticky`), quarantines failing proxies, and
spreads load to avoid per-IP rate-limit bans. With no proxies set, egress is
direct (fine for passive recon).

### Rate-limit profiles
`passive_only` · `stealth` (jitter, low concurrency) · `normal` · `aggressive`.
One profile tunes concurrency, QPS, port breadth, jitter and nuclei severity for
the whole pipeline. Default: `normal`. Active phases are blocked under
`passive_only`.

### AI supervisor (optional, token-frugal)
Works out of the box with **deterministic heuristics and zero tokens**. Add an
OpenAI-compatible endpoint (`RECON_AI_BASE_URL` + `RECON_AI_API_KEY`, including a
**local** Ollama/vLLM server) to enable agentic decisioning: it uses a **light**
model for routine triage/planning and a **heavy** model only for the final
narrative, with a hard per-scan call budget (`RECON_AI_MAX_CALLS`).

---

## Optional external tools

Recontool runs fully on its built-in Python adapters (crt.sh, HackerTarget, OTX,
Wayback, certspotter, DNS resolution, HTTP probing, **a pure-Python web crawler**, JS
analysis). If the Go/CLI binaries are on `PATH`, the matching adapters light up
automatically (graceful detection): `subfinder`, `httpx`, `dnsx`, `naabu`, `nuclei`,
`katana`, `tlsx`, `gau`, `gowitness`, and more.

> **Web crawling works with zero setup** — the built-in `pycrawl` adapter (active
> phase) BFS-crawls in-scope live hosts, downloads JS to local storage, and mines
> endpoints/secrets, without needing `katana`. `katana` is used automatically if
> installed for faster JS-aware crawling.

Install them with `bash docker/install_tools.sh all`, or use the Docker image which
bundles everything. Full list + invocation details in
[`config/tools.yaml`](config/tools.yaml) and [`docs/pipeline/04-tool-catalog.md`](docs/pipeline/04-tool-catalog.md).

---

## Storage layout

```
recontool.db                 # SQLite (default) — switch to Postgres via RECON_DB_URL
artifacts/<scan_id>/
  ├── raw/<tool>/*.json       # raw tool/API output
  ├── js/<host>/*.js          # JS files harvested from Wayback
  ├── bodies/<host>/*         # response bodies
  └── nuclei_targets.txt
```

---

## Tests

```bash
pip install -r requirements.txt
pytest -q
```

See [`docs/00-architecture-overview.md`](docs/00-architecture-overview.md) for the
full design rationale.
