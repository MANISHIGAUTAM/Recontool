# Recontool

**Authorized recon & attack-surface mapping in one command.** 53 adapters across 28 recon categories, config-driven, parallel execution, AI-supervised, with result caching and distributed worker support.

---

## Setup (2 lines)

```bash
pip install -e .
recontool scan yourdomain.com --mode live --authorize-active
```

That's it. Zero API keys required for passive recon. Add keys to `.env` to unlock more sources.

---

## Docker Setup (1 command)

```bash
cp .env.example .env && docker compose up --build
```

This builds the image with all recon CLIs bundled, starts Redis (for task queue + caching), a worker, and runs a zero-network demo. Then scan real targets:

```bash
docker compose run --rm recontool scan yourdomain.com --mode live --authorize-active
```

---

## Laptop Setup (macOS / Linux)

Everything you need to go from zero to scanning in under 5 minutes.

### Prerequisites

- Python 3.10+ (check: `python3 --version`)
- pip (`python3 -m pip --version`)
- git

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USER/Recontool.git
cd Recontool
pip install -e .
```

### 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` in your editor. **All keys are optional** -- the tool runs passive recon out-of-the-box using free keyless sources (crt.sh, hackertarget, urlscan, certspotter). Add API keys later to unlock more sources and higher rate limits.

### 3. (Optional) Install Go recon tools

These are external CLI tools that Recontool calls when available. They are not required but add coverage:

```bash
# Install Go first if you don't have it (https://go.dev/dl/)
# Then install recon tools:
go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
go install -v github.com/lc/gau/v2/cmd/gau@latest
go install -v github.com/tomnomnom/assetfinder@latest
go install -v github.com/tomnomnom/waybackurls@latest
go install -v github.com/projectdiscovery/naabu/v2/cmd/naabu@latest
go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
go install -v github.com/projectdiscovery/katana/cmd/katana@latest
```

Make sure `~/go/bin` is in your PATH:

```bash
export PATH="$PATH:$(go env GOPATH)/bin"
# Add this to your ~/.zshrc or ~/.bashrc to make it permanent
```

### 4. Run your first scan

```bash
# Passive-only scan (safe, no direct target contact)
recontool scan example.com --mode live

# Full active scan with a 5-minute timeout
recontool scan example.com --mode live --authorize-active --timeout 300

# Zero-network demo (no keys, no egress, built-in mocks)
recontool demo
```

### 5. Where results go

| Location | Contents |
|----------|----------|
| `output/` | Final scan reports, JSON exports, diffs |
| `artifacts/` | Raw tool output, JS files, response bodies, screenshots |
| `recontool.db` | SQLite database with all discovered entities |

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
