# D13 — Operator Runbook

> Day-to-day operation of Recontool: setup, authorization, running scans, recovery,
> monitoring, and troubleshooting. **Authorized targets only.**

## 0. Golden rules

1. **Authorization first.** Only scan assets you own or have written permission to test.
2. **Start in `demo`, then `live`.** Validate behavior against the mock before any real target.
3. **Passive by default.** Active phases require `--authorize-active` AND a non-passive profile.
4. **No evasion.** No proxy rotation to dodge limits, no stealth, no rate-limit bypass. Reliability comes from quotas, backoff, caching, and circuit breakers.

## 1. Install

```bash
git clone <repo> && cd Recontool
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # add extras: ".[ai,postgres,redis]"
cp config/recontool.example.yaml config/recontool.yaml   # then edit
```

Optional external CLIs (subfinder, naabu, nuclei, katana, …) are auto-detected;
absent binaries are skipped gracefully. Install via `docker/install_tools.sh`.

## 2. Configure

Precedence: **ENV var > `config/recontool.yaml` > built-in default.**

Key sections (`config/recontool.example.yaml`):
- `general.mode` — `demo | test | live`
- `general.profile` — `passive_only | stealth | normal | aggressive`
- `scope.allow_domains / allow_cidrs / allow_asns / deny_*` — explicit scope
- `api_keys.*` — all optional (passive recon works with none)
- `active_checks.allow` — which active detectors may run (empty = all)
- `recovery.checkpoint_enabled / max_deadletter_retries`
- `ai.base_url / api_key` — leave empty for zero-token heuristic mode

## 3. Preflight (always run first)

```bash
python -m recontool.cli preflight acme.com --mode live
```

Validates config, registries, storage, DB, queue, credentials, mode, and scope.
Exit 0 = ready; exit 2 = errors (fix before scanning). `scan` runs it automatically.

## 4. Run a scan

```bash
# safe passive recon (default)
python -m recontool.cli scan acme.com --mode live

# full pipeline incl. active phases (REQUIRES written authorization)
python -m recontool.cli scan acme.com --mode live --profile normal --authorize-active

# scope a subset of categories
python -m recontool.cli scan acme.com --category 1,2,3

# rehearse anything safely against the mock first
python -m recontool.cli scan recontool.local --mode demo --profile normal --authorize-active
```

Flags: `--profile/-p`, `--mode/-m`, `--authorize-active`, `--category/-c`,
`--no-ai`, `--resume <scan_id>`, `--skip-preflight`, `--export/-o out.json`.

## 5. Review results

```bash
python -m recontool.cli scans               # list past scans
python -m recontool.cli report <scan_id>    # summary + findings
python -m recontool.cli export <scan_id> -o out.json
```

Artifacts (raw JSON, JS files, screenshots) live under
`<artifact_dir>/<scan_id>/`. The canonical inventory + findings live in the DB.

## 6. Recovery: resume, dead-letters, replay

- **Resume an interrupted scan** (skips checkpointed phases):
  ```bash
  python -m recontool.cli scan acme.com --resume <scan_id>
  ```
- **Inspect failed work units** (adapters that errored after retries):
  ```bash
  python -m recontool.cli replay <scan_id>
  ```
  Dead-letters are parked in the `dead_letter` table with the error + payload.
  A clean run prints "No dead-letters".

## 7. Continuous monitoring (diffing)

Re-scan on a schedule (cron/CI), then diff the two latest runs:

```bash
python -m recontool.cli scan acme.com --mode live           # periodic re-scan
python -m recontool.cli diff acme.com                       # newest two scans
python -m recontool.cli diff acme.com --old <id> --new <id> # explicit pair
```

Reports added/removed assets, endpoints, services, and findings — wire the
`changed` flag into your alerting.

## 8. Safety & OPSEC controls

- **Scope gate**: deny overrides allow; re-checked before every active egress.
- **Active gate**: needs `--authorize-active` + non-passive profile + (in demo/test) is impossible to reach a real host.
- **Quota/backoff/circuit breaker**: per-provider budget ledger + breaker fail fast on throttling so the planner substitutes sources (`net/circuit.py`).
- **Audit log**: every adapter run, egress IP, gate decision, and error recorded in `audit_log`.
- **Redacted evidence**: secrets stored as hash + mask + location only.

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `preflight` scope FAIL | no allow_domains/cidrs derivable from seed | pass a domain/ip/cidr/asn seed or set `scope.*` in config |
| Active phases skipped | passive profile or missing `--authorize-active` | use `--profile normal --authorize-active` |
| Adapter "skipped" | external binary or API key absent | install binary (`docker/install_tools.sh`) or set key; otherwise expected |
| `LiveEgressBlocked` | demo/test mode tried real egress | expected safety behavior; use `--mode live` for real targets |
| `CircuitOpen` / `BudgetExhausted` | provider throttled / quota spent | wait for cooldown or raise budget; planner substitutes |
| Empty results in `live` | no keys / target has small surface | add provider API keys; verify scope |
| DB errors | bad `db_url` | check `general.db_url`; SQLite needs a writable path |

## 10. Quick reference

```bash
recontool preflight <seed> --mode <mode>
recontool scan <seed> [-p profile] [-m mode] [--authorize-active] [-c cats] [--resume id] [-o out.json]
recontool scans | report <id> | export <id> -o f.json
recontool diff <seed> | replay <id> | tools
```
