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

```bash
# 1. install (Python 3.10+)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .                      # provides the `recontool` command

# 2. (optional) configure keys / proxies / AI
cp .env.example .env                  # everything works WITHOUT this

# 3. run a PASSIVE scan (safe, no target contact)
recontool scan www.example.com

# 4. run the FULL pipeline against an AUTHORISED target
recontool scan example.com --profile stealth --authorize-active -o results.json

# inspect
recontool tools           # what adapters exist + which are available now
recontool scans           # past scans
recontool report <id>     # summary of a stored scan
recontool export <id> -o out.json
```

If you don't `pip install -e .`, run it as a module: `python -m recontool.cli scan www.example.com`.

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

Recontool runs fully on its built-in Python adapters. If these Go binaries are on
`PATH`, the matching adapters light up automatically (graceful detection):
`subfinder`, `naabu`, `nuclei`. Install via
[ProjectDiscovery](https://github.com/projectdiscovery).

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
