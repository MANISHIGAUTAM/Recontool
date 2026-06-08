# D19 — 500+ Tool Scaling Architecture

## Current State

- **532 tools** in the inventory (`data/tool_inventory.json`)
- **82 web-only** (GUI/browser, cannot automate)
- **450 automatable** (295 API + 203 CLI)
- **64 currently implemented** as adapters
- **386 remaining** to implement

## The Key Insight

Most tools follow 2 patterns:
1. **API**: HTTP GET with auth header → JSON response → parse into entities
2. **CLI**: subprocess with flags → stdout (JSON/text) → parse into entities

The generic adapter engine handles BOTH with a ~10-line YAML spec. No Python code needed per tool.

## Execution Flow Per Tool

```
1. Entity discovered → 2. Matrix populates "pending" for applicable tools
→ 3. Scheduler picks next → 4. Pre-check (key? binary? scope? budget?)
→ 5. Invoke (API call or CLI subprocess) → 6. Capture + parse output
→ 7. Normalize + store (DB + files + artifacts) → 8. AI reviews results
→ 9. Mark done + populate pending for NEW entities → 10. Loop
```

## Priority: 50 highest-value tools to add next (all API, free/freemium)

securitytrails, virustotal, chaos, binaryedge, onyphe, zoomeye, fofa,
bufferover, riddler, threatminer, robtex, viewdns, dnsdb, passivetotal,
spyse, dnsdumpster, rapiddns, crt_sh_extended, web_archive_extended,
commoncrawl, publicwww, grep_app, sourcegraph, dehashed, leakcheck,
intelx, pulsedive, maltiverse, hybrid_analysis, any_run, triage,
bazaar, urlhaus, phishtank, openphish, ransomwhere, feodotracker,
sslmate, crtsh_postgres, facebook_ct, google_ct, entrust_ct,
sectigo_ct, buypass_ct, letsencrypt_ct, cloudflare_ct,
digicert_ct, trustwave_ct, comodo_ct, symantec_ct

## Parallelism

All tool pools run simultaneously. Within each pool, the scheduler
dispatches by priority. Fast API tools (0.3s) don't wait for slow
CLI tools (30s). The execution matrix tracks it all.

## Docker: Everything bundled

The multi-stage Dockerfile compiles all Go tools and installs all
Python tools at build time. No user installation needed.
`docker compose up --build` gives you everything.
