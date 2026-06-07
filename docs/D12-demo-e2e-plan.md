# D12 — Demo-Mode E2E Plan

> A repeatable, **network-free** end-to-end demonstration of the full pipeline
> against the built-in mock environment. Safe to run anywhere — no real target,
> no credentials, no outbound traffic.

## 1. Goal

Exercise the entire flow on one command and show every stage producing output:

```
seed → preflight → scope/auth gate → source planner → 28-lane discovery →
corpus/normalize/dedupe → canonical store → frontier → live validation →
enrichment loops → active detection → findings/diff/report
```

## 2. The demo environment

- **Apex:** `recontool.local` (RFC-style sandbox name; never resolvable publicly).
- **Mock:** `recontool/testing/mock_env.py` (`MockEnv`) serves CT logs, passive DNS,
  archives, InternetDB, urlscan, and the demo hosts' HTML/JS/robots/forms.
- **Planted artifacts:** in-scope subdomains, a resolvable mock IP range
  (`192.0.2.0/24`, TEST-NET-1), endpoints in JS, and **fake** AWS/Google keys to
  trigger (redacted) secret findings.

## 3. One-command demo

```bash
# full pipeline incl. active phases — entirely against the mock, zero egress
python -m recontool.cli scan recontool.local \
    --mode demo --profile normal --authorize-active --no-ai
```

Expected (abridged) console flow:

```
Preflight            → all PASS (mode=demo, scope=recontool.local)
p1_seed       → crtsh, hackertarget, alienvault_otx, urlscan, certspotter
p2_expansion  → (subfinder/assetfinder skipped: binaries absent — graceful)
p3_enrichment → wayback, internetdb, greynoise, bgpview, ripestat
p4_verify     → dns_resolve, httpx_probe, naabu      (live hosts marked)
p5_deep       → js_analyze, param_miner, pycrawl, pydirb
p6_vuln       → (nuclei skipped: binary absent — graceful)
Asset inventory: subdomains, ips, live hosts, services, endpoints
Findings: high · secret (redacted AWS/Google keys from mock JS)
Scan id: <hex>
```

## 4. Step-by-step acceptance checklist

| # | Step | Command | Pass criteria |
|---|------|---------|---------------|
| 1 | Preflight | `python -m recontool.cli preflight recontool.local --mode demo` | exit 0, all checks PASS |
| 2 | Passive demo | `... scan recontool.local --mode demo --profile passive_only` | subdomains discovered, `active_ran=false` |
| 3 | Full demo | `... scan recontool.local --mode demo --profile normal --authorize-active` | 6 phases run, live hosts > 0, secret findings > 0 |
| 4 | Resume | re-run `scan ... --resume <scan_id>` | completed phases skipped, `resumed=true` |
| 5 | Diff | run demo scan twice, then `... diff recontool.local` | deterministic → `changed=false` |
| 6 | Dead-letters | `python -m recontool.cli replay <scan_id>` | clean run → "No dead-letters" |
| 7 | Export | `... scan ... --export out.json` | valid JSON with assets/endpoints/findings/edges |
| 8 | Egress proof | `pytest tests/e2e/test_demo_pipeline.py -q` | `LiveEgressBlocked` raised in test mode |

## 5. Automated equivalent (CI)

```bash
python -m pytest tests/e2e -q
```

`tests/e2e/test_demo_pipeline.py` and `test_fixture_regression.py` assert the same
acceptance criteria programmatically: surface discovered, live validation, secret
detection, checkpoints written, resume skips completed phases, deterministic output,
and hard egress-blocking in test mode.

## 6. What the demo proves about the architecture

- **Config-driven**: lanes/tools toggled by config; categories validated at preflight.
- **Frontier-driven recursion**: links found in mock HTML → new in-scope subdomains
  re-enter discovery; frontier surfaces only the *new* delta.
- **Validate-before-enrich**: `p4_verify` marks hosts live before expensive `p5_deep`.
- **Provenance + dedupe**: same host from multiple mock sources → one canonical asset
  with rising confidence.
- **Redacted evidence**: planted secrets are stored as hash+mask+location, never raw.
- **Safety**: nothing leaves the process; `demo` mode cannot touch a real host.

## 7. Extending the demo

To enrich the demo surface, add deterministic responses in `MockEnv.handle()` (new
provider host or new path on a demo host) and, if needed, widen the canonical
`DEMO_SUBDOMAINS`. Re-run `pytest tests/e2e` to update the regression baseline.
