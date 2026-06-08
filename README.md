# Recontool

**Authorized recon & attack-surface mapping in one command.** 53 adapters across 28 recon categories, config-driven, parallel execution, AI-supervised, with result caching and distributed worker support.

---

## Setup (1 command — Docker)

```bash
cp .env.example .env && docker compose up --build
```

That's it. The Docker image **bundles everything** — Python platform, all 30+ Go/Python recon tools (subfinder, nuclei, naabu, gau, katana, tlsx, ffuf, gowitness...), Redis for task queue + caching, and a worker for parallel execution. Zero manual installs.

Then scan:

```bash
docker compose run --rm recontool scan groww.in --mode live --authorize-active
```

Or use the Makefile:

```bash
make build                    # build the image
make scan T=groww.in          # full active scan
make demo                     # zero-network demo
make push DOCKER_REPO=yourhub/recontool   # push to Docker Hub
```

### Push to Docker Hub

```bash
docker build -t yourdockerhub/recontool:latest .
docker push yourdockerhub/recontool:latest
```

Then on any machine:

```bash
docker pull yourdockerhub/recontool:latest
docker run --rm -v "$PWD/output:/app/output" -v "$PWD/.env:/app/.env" \
  yourdockerhub/recontool:latest scan groww.in --mode live --authorize-active
```

### Alternative: pip install (no Docker)

```bash
pip install -e .              # just the Python platform
recontool scan groww.in --mode live --authorize-active
```

This works but only uses adapters whose binaries are on your PATH. For full coverage, use Docker or install Go tools separately (see below).

---

## Laptop Setup (macOS / Linux)

**Recommended: use Docker** (bundles all 30+ tools automatically). If you prefer native:

### Prerequisites

- Python 3.10+ (`python3 --version`)
- pip (`python3 -m pip --version`)
- (Optional) Go 1.21+ for recon CLI tools
- (Optional) Docker for the all-in-one image

### Option A: Docker (recommended — everything bundled)

```bash
git clone https://github.com/MANISHIGAUTAM/Recontool.git && cd Recontool
cp .env.example .env
docker compose up --build     # builds image with ALL tools, runs demo
# Then:
docker compose run --rm recontool scan yourdomain.com --mode live --authorize-active
```

### Option B: Native pip + Go tools

```bash
git clone https://github.com/MANISHIGAUTAM/Recontool.git && cd Recontool
pip install -e .
cp .env.example .env

# Install Go recon tools (all optional but recommended):
bash docker/install_tools.sh core     # subfinder, nuclei, naabu, gau, httpx, asnmap, uncover
# OR for EVERYTHING:
bash docker/install_tools.sh all      # + katana, tlsx, ffuf, gowitness, waybackurls, massdns...

# Scan:
recontool scan yourdomain.com --mode live --authorize-active
```

### Where results go

| Location | Contents |
|----------|----------|
| `output/<domain>/subdomains.txt` | One subdomain per line |
| `output/<domain>/live_hosts.txt` | Confirmed live hosts |
| `output/<domain>/services.txt` | host:port |
| `output/<domain>/endpoints.txt` | URLs |
| `output/<domain>/findings.txt` | Secrets/vulns detected |
| `output/<domain>/full_report.json` | Complete JSON |
| `recontool.db` | SQLite database (all entities) |
| `artifacts/<scan_id>/` | Raw tool output, JS files |

View results:

```bash
recontool report <scan_id>
recontool export <scan_id> -o results.json
```

### Tips

- Use `--timeout 300` for large targets to avoid runaway scans
- Use `--category 2,21` to focus on specific areas (e.g. subdomain enum + port scan)
- Run `recontool tools` to see all 53 adapters and which Go tools are detected
- No API keys needed for basic scanning -- add them incrementally as you need more coverage
- Use `recontool preflight example.com --mode live` to validate your config before a real scan

---

## Usage Samples

```bash
# Passive recon only (safe, no target contact)
recontool scan groww.in --mode live

# Full active scan (DNS + HTTP probe + port scan + crawl + content discovery)
recontool scan groww.in --mode live --authorize-active

# With timeout (seconds) — useful for large targets
recontool scan groww.in --mode live --authorize-active --timeout 300

# Scan specific categories only (e.g. just subdomain enum + port scan)
recontool scan groww.in --mode live --authorize-active --category 2,21

# Export results to JSON
recontool scan groww.in --mode live --authorize-active -o results.json

# Zero-network demo (built-in mock, no keys needed)
recontool demo

# Resume an interrupted scan
recontool scan groww.in --mode live --resume <scan_id>

# Compare two scans (continuous monitoring)
recontool diff groww.in

# View past results
recontool report <scan_id>
recontool export <scan_id> -o out.json

# List all available adapters
recontool tools

# Validate config before running
recontool preflight groww.in --mode live
recontool config-validate --env live

# Start a distributed worker (pulls tasks from Redis queue)
recontool worker --concurrency 8
```

---

## Sample Output (groww.in)

```
╭──────────────────────────────────── scan ─────────────────────────────────────╮
│ Recontool  seed=groww.in  profile=normal  mode=live  active=yes               │
╰───────────────────────────────────────────────────────────────────────────────╯
p1_seed (5s)     → crtsh, hackertarget, alienvault_otx, urlscan, certspotter
   ✔ hackertarget 0.3s → 117 events
   ✔ urlscan 0.9s → 396 events
p3_enrichment    → wayback, internetdb, greynoise, wordlist_learner
p4_verify (37s)  → dns_resolve, httpx_probe, naabu (port scan)
   ✔ dns_resolve 0.2s → 346 events
   ✔ naabu 36s → 101 services
p5_deep (78s)    → js_analyze, param_miner, pycrawl, pydirb
   ✔ pycrawl 78s → 250,361 events

Asset Inventory: 56 subdomains · 44 IPs · 41 live · 101 services · 3400+ endpoints
Top: delivery.groww.in, app.groww.in, growwsso.groww.in, tech.groww.in...
Ports: 443(30 hosts), 80(29), 8443(21), 8080(21)
```

---

## What it does

```
  seed → scope gate → config → source planner
         │
         ├─► 28 parallel recon lanes (CT, DNS, WHOIS, archive, crawl, ports...)
         │
         ▼
  corpus builder → normalize/dedupe → canonical graph + artifact lake
         │
         ▼
  frontier manager (recurse only on NEW in-scope entities)
         │
         ▼
  live validation → enrichment loops → active detection → findings/reports
```

- **53 adapters** across all 28 OSINT categories
- **No caps** — scans everything it discovers
- **Parallel execution** — all adapters in a phase run simultaneously
- **Result caching** — repeat scans skip fresh data (configurable TTL)
- **Distributed workers** — scale via Redis queue + docker compose workers
- **Provenance tracking** — every entity links back to its source(s)
- **Checkpoint/resume** — interrupted scans continue where they left off

---

## Run Modes

| Mode | Network | Use |
|------|:-------:|-----|
| `demo` | none | Built-in mock env. Safe demo, no keys needed. |
| `test` | none | Recorded fixtures for CI. Hard-blocks egress. |
| `live` | real | Authorized targets. Scope + auth gated. |

---

## Configuration

```bash
cp .env.example .env     # add any API keys (all optional)
```

Key env vars:
```
RECON_MODE=live                          # demo | test | live
RECON_PROFILE=normal                     # passive_only | stealth | normal | aggressive
RECON_REDIS_URL=redis://localhost:6379/0 # enables distributed queue + cache
SHODAN_API_KEY=...                       # optional: unlocks Shodan
GITHUB_TOKEN=...                         # optional: unlocks code search
CENSYS_API_ID=... / CENSYS_API_SECRET=...
```

All 29 provider keys are documented in `.env.example`. The tool works with zero keys (passive sources like crt.sh, hackertarget, urlscan are keyless).

---

## Tests

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q     # 150 tests, all network-free
```

---

## Architecture

| Component | File |
|-----------|------|
| 28-lane pipeline | `orchestrator/pipeline.py` |
| 53 adapters | `adapters/` + `config/tools_generic.yaml` |
| Task queue (Redis/InMemory) | `queue/` |
| Result cache | `cache.py` |
| Normalizer (sole DB writer) | `normalize/engine.py` |
| Frontier manager | `orchestrator/frontier.py` |
| Provider config (validated) | `providers.py` + `config/providers.yaml` |
| Structured logs + trace IDs | `obs.py` |
| AI supervisor | `ai/supervisor.py` |
| Learning engine (cat 28) | `learning.py` |

Full docs: [`docs/`](docs/) (D11-D18 cover testing, demo, runbook, providers, setup, architecture)

---

## Adding a new tool (no Python needed)

Add a YAML spec to `config/tools_generic.yaml`:

```yaml
- name: certspotter
  phase: p1_seed
  category: 2
  integration: api
  consumes: [domain]
  produces: [subdomain]
  endpoint: "https://api.certspotter.com/v1/issuances?domain={domain}&include_subdomains=true"
  parse:
    format: json
    emit:
      - {entity: asset, value_each: dns_names, type: subdomain, scope_filter: subdomain}
```

It auto-registers on next run. No Python code required.

---

## Docs

| Doc | Topic |
|-----|-------|
| `docs/D11-testing-strategy.md` | Test pyramid + how to add tests |
| `docs/D12-demo-e2e-plan.md` | Demo mode acceptance checklist |
| `docs/D13-operator-runbook.md` | Day-to-day operations |
| `docs/D14-architecture-review-and-gaps.md` | Architecture + flow diagram |
| `docs/D16-provider-config.md` | Provider configuration guide |
| `docs/D17-setup-and-docker.md` | Setup, Docker, CI |
| `docs/D18-completion-report.md` | Quality gate report |

---

## License

Authorized use only. See [`docs/D6-opsec.md`](docs/D6-opsec.md) for policy.
