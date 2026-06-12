# Recontool

> 📐 **Start here:** [`docs/00-FINAL-ARCHITECTURE.md`](docs/00-FINAL-ARCHITECTURE.md)
> is the single source of truth for the architecture, tools vision, and roadmap.
> It states the real implementation status (not all docs do) and supersedes the
> older scattered roadmaps. Read it before relying on any other design doc.

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
bash docker/install_tools.sh python   # optional: API server + JS-render browser + favicon
                                       #   (fastapi, uvicorn, mmh3, playwright) — degrade cleanly if absent

# 3. (optional) configure API keys / proxies / AI
cp config/recontool.example.yaml config/recontool.yaml   # everything works WITHOUT this

# 4. RUN — the platform is driven by a single scope domain
recontool scan www.xyz.com                               # linear pipeline (passive, default)
recontool scan xyz.com --authorize-active -o results.json # full linear pipeline (authorised)
recontool engine www.xyz.com                             # recursive engine (passive, streams logs+AI)
recontool engine xyz.com --authorize-active -o out.json  # ◆ dive deep: resolve→probe→crawl→vuln loop
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

Two files in `config/` (both optional — passive recon runs with zero config):

| File | Purpose |
|------|---------|
| `config/recontool.yaml` | Main config — profile, network, AI, API server, provider keys, categories, resources. Copy from `recontool.example.yaml`. **Gitignored.** |
| `config/tools.yaml` | Machine-readable **tool registry** — every tool's invocation, input/output, install method. The integration backbone. |

**Precedence:** environment variable → `config/recontool.yaml` → built-in default. Keep
secrets in env vars (CI) or the YAML (local). Starter files:

```bash
cp config/recontool.example.yaml config/recontool.yaml   # everything works WITHOUT this
cp .env.example .env                                      # ...or use env vars instead
```

### Complete config reference

Every key, its environment-variable override, type, and default.

**`general:`**

| YAML key | Env var | Type | Default | Purpose |
|----------|---------|------|---------|---------|
| `general.profile` | `RECON_PROFILE` | `passive_only`\|`stealth`\|`normal`\|`aggressive` | `normal` | concurrency / QPS / jitter / port breadth / nuclei severity envelope |
| `general.max_concurrency` | `RECON_MAX_CONCURRENCY` | int | `20` | global parallel-task cap |
| `general.db_url` | `RECON_DB_URL` | str (DSN) | `sqlite:///recontool.db` | SQLite (default) or `postgresql+psycopg://…` |
| `general.artifact_dir` | `RECON_ARTIFACT_DIR` | path | `./artifacts` | raw + typed + JS + scan-bundle output |
| `general.redis_url` | `RECON_REDIS_URL` | str | _(unset)_ | optional distributed rate-limit buckets |

**`network:`**

| YAML key | Env var | Type | Default | Purpose |
|----------|---------|------|---------|---------|
| `network.proxies` | `RECON_PROXIES` (CSV) | list[str] | `[]` | SINGLE declared egress for allow-listing — **not** rotation-for-evasion |
| `network.proxy_strategy` | `RECON_PROXY_STRATEGY` | `round_robin`\|`random`\|`sticky` | `round_robin` | only meaningful with >1 egress |
| `network.rate_limits` | _(YAML only)_ | map `provider: qps` (float) | built-in conservative defaults | per-provider QPS **compliance** (stay under each source's limit) |

**`ai:`** — optional; empty = zero-token deterministic heuristic decisioning.

| YAML key | Env var | Type | Default | Purpose |
|----------|---------|------|---------|---------|
| `ai.base_url` | `RECON_AI_BASE_URL` | str (URL) | _(unset)_ | OpenAI-compatible endpoint (incl. local Ollama/vLLM/LM Studio) |
| `ai.api_key` | `RECON_AI_API_KEY` | str | _(unset)_ | enables model-backed decisioning + summaries |
| `ai.model_light` | `RECON_AI_MODEL_LIGHT` | str | `gpt-4o-mini` | triage / classification / keep-drop |
| `ai.model_heavy` | `RECON_AI_MODEL_HEAVY` | str | `gpt-4o` | final narrative only |
| `ai.max_calls` | `RECON_AI_MAX_CALLS` | int | `40` | hard per-scan AI call budget (`0` = unlimited) |

**`api:`** — the `recontool serve` API/UI server.

| YAML key | Env var | Type | Default | Purpose |
|----------|---------|------|---------|---------|
| `api.token` | `RECON_API_TOKEN` | str | _(unset → data routes return 503)_ | **required** bearer token to expose any data/control route |
| `api.host` | `RECON_API_HOST` | str | `127.0.0.1` | bind address (keep localhost unless behind a TLS proxy) |
| `api.port` | `RECON_API_PORT` | int | `8088` | bind port |

**`categories:`** and **`resources:`**

| YAML key | Type | Default | Purpose |
|----------|------|---------|---------|
| `categories.enabled` | list[int] | `[1, 2, 3, 6]` | which tool categories run (active ones still need `--authorize-active`) |
| `resources.resolvers` | path | `./config/resolvers.txt` | mass-DNS resolver list (puredns/massdns) |
| `resources.wordlist_dir` | path | `./wordlists` | content-discovery wordlists (SecLists) |
| `resources.default_wordlist` | path | `./wordlists/common.txt` | default wordlist |

### Provider API keys (`api_keys:` — all optional)

Set via the env var **or** under `api_keys:` in the YAML. Passive recon needs none; each
key unlocks its source and/or higher limits.

| Env var | YAML key | Unlocks |
|---------|----------|---------|
| `SHODAN_API_KEY` | `shodan` | Shodan host/search **+ favicon-hash org-forest pivot** |
| `CENSYS_API_ID` / `CENSYS_API_SECRET` | `censys_id` / `censys_secret` | Censys hosts/certs |
| `NETLAS_API_KEY` | `netlas` | Netlas search |
| `GREYNOISE_API_KEY` | `greynoise` | GreyNoise IP context |
| `LEAKIX_API_KEY` | `leakix` | LeakIX exposures |
| `FULLHUNT_API_KEY` | `fullhunt` | FullHunt attack surface |
| `URLSCAN_API_KEY` | `urlscan` | urlscan.io |
| `CRIMINALIP_API_KEY` | `criminalip` | CriminalIP |
| `BINARYEDGE_API_KEY` | `binaryedge` | BinaryEdge |
| `ZOOMEYE_API_KEY` | `zoomeye` | ZoomEye |
| `SECURITYTRAILS_API_KEY` | `securitytrails` | SecurityTrails passive DNS / history |
| `VIRUSTOTAL_API_KEY` | `virustotal` | VirusTotal domains/resolutions |
| `CHAOS_API_KEY` | `chaos` | ProjectDiscovery Chaos subdomains |
| `CERTSPOTTER_API_KEY` | `certspotter` | Cert Spotter (higher limits) |
| `IPINFO_TOKEN` | `ipinfo` | IPinfo ASN/geo |
| `GITHUB_TOKEN` | `github_token` | GitHub code/subdomain search |
| `GITLAB_TOKEN` | `gitlab_token` | GitLab search |
| `GRAYHATWARFARE_API_KEY` | `grayhatwarfare` | open cloud-bucket search |
| `PUBLICWWW_API_KEY` | `publicwww` | **analytics-ID org-forest pivot** |
| `HUNTER_API_KEY` | `hunter` | email discovery (Cat 7, gated) |
| `HIBP_API_KEY` | `hibp` | breach-exposure lookup (Cat 7, gated) |
| `NVD_API_KEY` | `nvd` | CVE enrichment |
| `VULNERS_API_KEY` | `vulners` | vuln intel |

> DeHashed (`dehashed_user`/`dehashed_key`) and FOFA (`fofa_email`/`fofa_key`) are
> YAML-only placeholders for tools that read them directly. **Security:** real keys go in
> `.env` or `config/recontool.yaml` (both gitignored) — never commit them.

---

## Running by category (pipeline model)

The platform is built as **per-category pipelines** that chain tools (A's output → B's
input) through a shared DB. You drive everything with a scope domain:

```bash
recontool scan www.xyz.com                       # default preset (passive categories)
recontool scan www.xyz.com --category 2          # run ONLY the Cat-2 subdomain pipeline
recontool scan www.xyz.com --category 1,2,3      # run several categories
recontool scan www.xyz.com --authorize-active    # unlock active categories
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
- `09-category-milestones.md` — per-category implementation status + rollout gate.
- `10-gaps-and-advancements.md` — gaps found, advancements implemented + proposed.

Full parallel/recursive architecture (all categories, one diagram):
[`docs/flow/01-PARALLEL-RECURSIVE-ARCHITECTURE.md`](docs/flow/01-PARALLEL-RECURSIVE-ARCHITECTURE.md).

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
bash docker/install_tools.sh all         # full set + SecLists wordlists + resolver list + python extras
bash docker/install_tools.sh python      # API server + live JS-render browser + favicon-hash
                                          #   deps: fastapi, uvicorn, mmh3, playwright (+chromium)
bash docker/install_tools.sh resources   # just wordlists + clean DNS resolvers
```

---

## Key capabilities (and where they live)

| Capability | Module |
|------------|--------|
| **Tool chaining** (output → input across phases via the DB) | `orchestrator/pipeline.py` |
| **Parallel execution** (L1 tools-per-phase + L2 inputs-per-tool) | `orchestrator/pipeline.py`, all adapters; see `docs/flow/01-PARALLEL-RECURSIVE-ARCHITECTURE.md` |
| **Generic adapter engine** (wire tools as declarative YAML, no code) | `adapters/generic.py`, `adapters/autoload.py`, `config/tools_generic.yaml` |
| **Pure-Python web crawler** (no binary; JS download + endpoint/secret mining) | `adapters/crawler.py` (`pycrawl`) |
| **Content/directory discovery** (ffuf-style + 404 calibration) | `adapters/content_discovery.py` (`pydirb`) |
| **Param/form extraction** (fuzz prep) | `adapters/params.py` (`param_miner`) |
| **IP / proxy rotation** (avoid blacklisting) | `net/proxy_pool.py` |
| **Rate limiting** (per-provider token buckets) | `net/rate_limiter.py` |
| **DB storage** (subdomains, IPs, params, services, findings) | `core/models.py`, `normalize/engine.py` |
| **Filesystem artifacts** (JS, response bodies, screenshots, raw output) | `core/artifacts.py` |
| **Dedup + confidence scoring** | `core/dedupe.py`, `core/confidence.py` |
| **Scope + passive→active safety gate** | `core/scope.py`, `orchestrator/pipeline.py` |
| **AI agentic supervisor** (light/heavy model routing) | `ai/router.py`, `ai/supervisor.py` |
| **Tool inventory + flow generators** | `recontool/inventory/` → `data/`, `docs/inventory/`, `docs/flow/` |
| **Reporting / export** (JSON/summary) | `report.py`, `cli.py` |

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
  ├── raw/<tool>/*.json        # raw tool/API output (provenance)
  ├── out/<tool>.<type>.jsonl  # normalized, typed, append-only records (one file per output type)
  ├── js/<host>/*.js           # JS files harvested from Wayback / crawler
  ├── bodies/<host>/*          # response bodies
  ├── screenshots/*.png        # gowitness (if installed)
  ├── nuclei_targets.txt
  └── scan_bundle.json         # FINAL per-scan manifest: DB summary + findings + artifact index
```

---

## Event-Driven Engine (recursive)

The platform includes an event-driven orchestration engine that provides parallel,
dependency-aware tool scheduling. Instead of fixed phase ordering (P1-P6), tools
execute as soon as their input dependencies are satisfied, and **every discovery
re-feeds the frontier** until no eligible tools remain (convergence).

```bash
# run the recursive engine (parallel, convergence-based) — PASSIVE by default
recontool engine www.xyz.com                        # default profile (curated tools), passive
recontool engine xyz.com --authorize-active         # ◆ DIVE DEEP: resolve→probe→port→crawl→vuln
recontool engine xyz.com --tools all --authorize-active   # excessive: every runnable tool, deep
recontool engine xyz.com --workers 8                # DB-backed multi-worker queue
recontool engine xyz.com --noise-control            # drop dup / out-of-scope leads
recontool engine xyz.com --wildcard-filter          # also drop wildcard-DNS noise (DNS lookups)
recontool engine xyz.com --authorize-active --profile stealth --max-depth 4 -o out.json

# scale horizontally: point more workers at the same scan + RECON_DB_URL
recontool worker <scan_id> --workers 8              # inherits the scan's active authorization
```

The engine **streams its logs and AI decisions by default** — a plain
`recontool engine <seed>` prints every tool start/finish, each discovered
entity, how many downstream `work_item`s it enqueued (the recursion fan-out),
and the AI keep/drop/triage decision per tool. Add `-v` for per-request DEBUG.

#### Flags to dive deep

| Flag | What it unlocks |
|------|-----------------|
| `--authorize-active` | **The dive-deep gate.** Passive by default (CT logs, passive DNS, archives — no target contact). This unlocks the active chain that touches the target: DNS resolution → HTTP probe → port scan (`naabu`, pure-Python fallback) → live JS-render + crawl (`pycrawl`/`js-render`) → content/param discovery → `nuclei`. **Only use on targets you are authorised to test.** |
| `--tools all` | Run *every* runnable tool, not just the curated default profile (overlap is free via idempotent keys; pair with `--noise-control`). |
| `--max-depth N` | How far discovered keys re-feed (recursion depth from the seed). Default 3. |
| `--workers N` | Concurrent async workers draining the queue (scale across hosts with `recontool worker`). |
| `--noise-control` / `--wildcard-filter` | Drop duplicate / out-of-scope / wildcard-DNS / CDN leads before they re-feed. Recommended with `--tools all`. |
| `--incremental` | Delta-only reruns: skip a tool whose exact input already ran in a recent prior scan, reusing its results (the `tool_run` history powers it). |
| `-v` / `-vv` | `-v` adds per-request DEBUG; `-vv` is maximally verbose. |
| `--profile stealth\|normal\|aggressive` | Tunes concurrency / QPS / jitter / port breadth / nuclei severity. |

> **Deep recursion works with zero external binaries.** The engine runs the
> built-in pure-Python adapters (`dns_resolve`, `httpx_probe`, the `naabu`
> connect-scan fallback, the `pycrawl` crawler, JS analysis) directly — so
> `--authorize-active` gives a full passive→live→active→loop chain even before
> you install `subfinder`/`httpx`/`naabu`/`nuclei`. Installed Go binaries are
> used automatically when present (they win nothing over correctness; they add
> speed/coverage). Hand-written adapters always take precedence over the generic
> spec of the same name.

**Tool profiles (flag-gated, nothing eliminated):** `--tools default` runs the
curated/recommended set (correct parsers); `--tools all` (a.k.a. excessive) runs
*every* tool the engine can execute. Tools with no programmatic interface stay in
the registry and skip cleanly. **Workers:** `--workers 1` uses the in-process
event engine; `--workers N` drains a persisted `work_item` queue with N concurrent
workers that **atomically claim** items — so it's resumable and safe to run across
multiple processes/hosts (`recontool worker <scan_id>`).

Event flow:

```
ScanRequested -> ToolSelected -> ToolRunning -> EntityDiscovered
     -> (noise gate) -> downstream ToolSelected -> ... -> ScanCompleted
```

Key capabilities:
- **Real end-to-end execution** — `engine/runner.py` runs each scheduled tool
  (hand-written Python adapter when one exists, else the generic spec), normalizes
  results into the DB (idempotent dedupe), and re-feeds `EntityDiscovered` so
  discovery recurses (`recontool engine`). The hand-written adapters (DNS resolve,
  HTTP probe, `pycrawl`, `naabu` fallback, JS analysis) are bridged into the engine
  registry so the recursive chain runs with no external binaries.
- **Parallel executor** — layered concurrency control (global, per-tool, per-host
  asyncio semaphores). Recon is I/O-bound, so one node fans out hundreds of
  concurrent lookups without lag; tune with the rate profile.
- **Multi-worker queue** (`engine/worker.py`) — N workers atomically claim pending
  `work_item`s (`pending→running` compare-and-set), so execution is resumable and
  scales across processes/hosts against one DB. Run with `engine --workers N` or
  attach more via `recontool worker <scan_id>`.
- **Tool profiles** (`engine/selection.py`) — `default` (curated) vs `all`
  (everything runnable), gated by `--tools`; every tool stays registered.
- **Live JS-render crawler** (`recontool/tools/jsrender.py`, tool `js-render`) —
  headless-browser render captures the XHR/fetch/GraphQL endpoints, JS-injected
  routes, and secrets a static crawl misses, then recurses on them. Uses Playwright
  if installed, else degrades to a static fetch. This is the dynamic-application
  data layer that sets the engine apart from classic recon.
- **Deterministic router** — `engine/router.py` answers "which tools consume this
  key type?" by a plain query over the persisted tool registry (`tool_row`), with
  type subsumption (a subdomain is also valid input to domain-consuming tools).
- **Idempotent WorkQueue** — `(scan, key, tool)` items are deduped on enqueue, so a
  re-discovered entity never triggers a rescan.
- **Optional noise control** (`--noise-control`) — `engine/noise.py` gates the
  re-feed path: dedupe + scope (free), wildcard-DNS + CDN (opt-in). Off by default.
- **Pending keys** — inter-tool dependency tracking (e.g. confirm a host is live
  before vuln scanning).
- **Incremental scans** — SHA-256 fingerprinting to skip unchanged inputs.

The engine is additive: the existing `ReconPipeline` (`recontool scan`) still runs
linear scans. Full documentation lives in [`docs/engine/`](docs/engine/) and the
single-source design in [`docs/00-FINAL-ARCHITECTURE.md`](docs/00-FINAL-ARCHITECTURE.md):

| Doc | Topic |
|-----|-------|
| [00-architecture-overview.md](docs/engine/00-architecture-overview.md) | High-level diagram and component map |
| [01-event-flow.md](docs/engine/01-event-flow.md) | All events, when they fire, who handles them |
| [02-tool-registry.md](docs/engine/02-tool-registry.md) | Schema reference, querying, adding tools |
| [03-adapter-contract.md](docs/engine/03-adapter-contract.md) | Full contract methods with reference implementation |
| [04-pending-keys.md](docs/engine/04-pending-keys.md) | Lifecycle, rules, database schema |
| [05-parallel-execution.md](docs/engine/05-parallel-execution.md) | Concurrency model and safety rules |
| [06-incremental-scans.md](docs/engine/06-incremental-scans.md) | Fingerprinting, staleness, delta reprocessing |
| [07-ai-decisioning.md](docs/engine/07-ai-decisioning.md) | Interface, heuristics, mocking |
| [08-observability.md](docs/engine/08-observability.md) | Logging format, metrics, correlation IDs |
| [09-adding-new-adapter.md](docs/engine/09-adding-new-adapter.md) | Step-by-step guide with examples |
| [10-troubleshooting.md](docs/engine/10-troubleshooting.md) | Common issues, debugging, FAQ |

---

## API / UI server, scaling & org-forest

### Web UI + live status & control API (`recontool serve`)
A FastAPI service exposes the engine state **and ships a self-contained web UI** —
read endpoints, a live **SSE** progress stream, and an auth-gated scan-control
endpoint. The UI is a single dependency-free page (no CDN / external calls — this
is a privileged surface); you paste the bearer token into it.

```bash
pip install fastapi uvicorn                    # optional extra (in the Docker image already)
export RECON_API_TOKEN=$(openssl rand -hex 16) # REQUIRED — no token => data routes return 503
recontool serve                                # UI at http://127.0.0.1:8088/  (API docs at /docs)
```

Open `http://127.0.0.1:8088/`, paste the token, and you get: a **scan launcher**
(seed/type/profile, tool profile `default`|`all`, depth/workers, noise toggles, and
an explicit *authorize-active* checkbox with a guardrail confirm), **live SSE
progress** (queue status + recursion depth fan-out), an **assets** table (type
filter + search), **findings**, the **relationship graph** (a vanilla
force-directed canvas — color by entity type, live hosts ringed, zoom/pan/pin),
and the read-only **tool matrix** (every tool, what's runnable, what's in `default`).

| Route | Purpose |
|-------|---------|
| `GET /` · `GET /ui` | the bundled web UI (open; calls below are token-gated) |
| `GET /health` | liveness (open) |
| `GET /scans` · `GET /scans/{id}` | list scans · overview (counts + recursion-depth stats) |
| `GET /scans/{id}/assets?type=` · `/findings` | typed asset inventory · findings |
| `GET /scans/{id}/queue` | WorkQueue / recursion view (status, depth fan-out, re-feed) |
| `GET /scans/{id}/graph` | `{nodes, edges}` for the relationship graph |
| `GET /scans/{id}/events` | **SSE** — live queue progress until convergence |
| `GET /tools` · `/tools/summary` | capability matrix — every tool, runnable/default flags |
| `POST /scans` | start a scan (body: seed, profile, `authorize_active`, …) |

> **Security:** every route except `/`, `/ui`, and `/health` requires
> `Authorization: Bearer $RECON_API_TOKEN` (constant-time check; default-deny if
> unset). It binds to localhost by default — only expose it behind a TLS reverse
> proxy with the token set. It's a privileged control surface (it can launch
> active scans). The UI sends the token via `fetch`, including the SSE stream
> (`EventSource` can't set headers), so nothing about it weakens the bearer gate.

### Horizontal worker fleet (AWS distribution)
The atomic-claim `work_item` queue lets N identical workers drain one scan in
parallel against a shared `RECON_DB_URL` (Postgres/RDS) — the unit you replicate
across Fargate/ECS/EC2.

```bash
docker compose up -d postgres                                  # shared queue (RDS in AWS)
docker compose --profile app run --rm recontool engine xyz.com --authorize-active   # seed a scan
SCAN_ID=<id> docker compose --profile fleet up --scale worker=8 worker              # fan out 8 workers
docker compose --profile api up api                            # + the read/SSE API (set RECON_API_TOKEN)
```

### Org-forest pivots (sibling-site discovery)
`org_fingerprint` (active) extracts an org's shared fingerprints from a live host —
**favicon mmh3 hash**, **Google Analytics/GA4/GTM/AdSense IDs**, and **copyright
org** — and the keyed lookups `favicon-shodan` / `analytics-publicwww` pivot those
to related domains. Siblings are recorded as **`org` intelligence + graph edges**,
never auto-promoted to an in-scope active scan (authorized-only: add a sibling to
scope and re-seed to scan it).

### Rate-limit compliance (not evasion)
Per-provider QPS ceilings keep each source under its published limit so many
workers sharing one key never collectively exceed it. Tune in `recontool.yaml`:

```yaml
network:
  rate_limits: { hackertarget: 0.2, crtsh: 1.0, otx: 2.0 }   # requests/second per provider
  proxies: []          # optional SINGLE declared egress for allow-listing (not rotation-for-evasion)
```

---

## Tests

```bash
pip install -r requirements.txt
pytest -q          # full suite: unit/atomic + integration + e2e (318 passing)
                   #   parsers, dedupe/confidence, scope, generic + adapter bridge,
                   #   recursion engine, crawler, content discovery, params, JS storage,
                   #   org-forest, rate-limit compliance, AI decisioning, incremental,
                   #   artifact bundle, and the API/UI data layer
```

See [`docs/00-architecture-overview.md`](docs/00-architecture-overview.md) for the
full design rationale.
