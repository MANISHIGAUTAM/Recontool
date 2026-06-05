# Feature Advancements

Concrete enhancements beyond the current design, ranked by **value ÷ effort**. Each entry:
what it is, why it matters, how it plugs into the existing architecture, and rough effort
(S/M/L). Items marked ⭐ are the ones I'd build first.

---

## Tier 1 — High value, low/medium effort (build first)

### ⭐ A1. Continuous monitoring + change diffing (EASM core)
- **What:** schedule a scope to re-run passive recon on an interval; compute the delta vs
  the previous run; alert on **new** subdomains / **new** open ports / **new** findings.
- **Why:** the single biggest product differentiator. "What changed since yesterday" is
  what turns a one-shot scanner into an attack-surface-management platform.
- **How:** we already write `asset_state` snapshots. Add a `diff(scan_a, scan_b)` that
  emits `new|modified|gone` events → `notify` sink. Cron/`certspotter` webhook triggers a
  passive re-run. Schema already supports it (`asset.first_seen/last_seen`).
- **Effort:** M.

### ⭐ A2. Live-status streaming to console/UI (incremental display)
- **What:** stream subdomain/live-host/finding rows to the operator **as they're
  discovered**, not just a summary at the end (the mockup in `06-recursive-flow.md` §6).
- **Why:** long scans feel dead without progress; operators want to triage early.
- **How:** an event bus (the normalizer already emits events) → Rich live table in CLI;
  Server-Sent Events / WebSocket for the web UI. No schema change.
- **Effort:** S–M.

### ⭐ A3. Resume / checkpoint / replay
- **What:** a crashed or cancelled scan resumes from the last converged depth; any scan
  can be replayed deterministically.
- **Why:** scans run for minutes–hours; losing progress is painful and wastes API quota.
- **How:** the frontier/`seen`/`depth` state is already DB-derivable; persist
  `scan.frontier_state`; on restart, rebuild frontier from `asset` where not-yet-expanded.
  (Temporal, per `D4-adr.md`, gives this natively if/when adopted.)
- **Effort:** M.

### ⭐ A4. Favicon-hash pivoting
- **What:** hash each live host's favicon (mmh3), then query Shodan/ZoomEye/FOFA
  `http.favicon.hash:<h>` to find *other* hosts sharing it (often same org/app).
- **Why:** cheap, high-signal correlation that finds infra the subdomain sources miss —
  a classic bug-bounty force-multiplier.
- **How:** httpx already can emit favicon hash (`-favicon`); add a Cat-1 enrichment
  adapter that pivots the hash via `uncover`. New hosts → ⟳ frontier.
- **Effort:** S.

### A5. CDN/WAF-aware scan tuning
- **What:** when `cdncheck`/`wafw00f` flag a host as CDN/WAF-fronted, automatically lower
  rate, skip port-scanning CDN edge ranges, and tag for origin-IP hunting (`cloudfail`).
- **Why:** avoids wasted scans on CDN edges and reduces blocking/ban risk.
- **How:** tags already exist (`asset.tags += [cdn, waf]`); the scheduler reads tags to
  pick a per-host rate sub-profile.
- **Effort:** S–M.

### A6. Smart wordlist selection for content discovery
- **What:** choose ffuf/feroxbuster wordlists based on detected tech (WordPress →
  wp-list; Java → servlet paths) and seed with paths harvested from JS/archives (Cat 11/22).
- **Why:** dramatically higher hit-rate than a generic list; fewer requests for more results.
- **How:** map `asset.tech` → wordlist set; merge with discovered paths before fuzzing.
- **Effort:** M.

---

## Tier 2 — High value, medium/large effort

### A7. AI/ML enrichment layer (additive, per `README` §5 and ADR-015)
- **Endpoint risk classification:** rules → small classifier tags endpoints
  (admin/auth/api/upload/debug) → `endpoint.risk_class`, surfaces high-value targets.
- **LLM report narrative:** turn findings into an exec summary + prioritized next-actions
  (self-hosted model default for sensitive data; never invents assets).
- **Anomaly detection:** Isolation Forest over host feature-vectors (odd port/ASN/tech)
  flags outliers worth manual review.
- **Semantic dedup:** embedding similarity collapses findings that describe the same issue
  across different tools (second pass after deterministic dedup).
- **Effort:** L (but incremental; the heuristic fallback already ships).

### A8. Graph-native pivoting UI (Neo4j projection)
- **What:** interactive attack-surface graph — click an ASN to see its blast radius,
  trace dangling-CNAME takeover chains, find shared-cert clusters.
- **Why:** analysts think in graphs; this is where non-obvious relationships surface.
- **How:** `edge` table → Neo4j projector (ADR-005) → Cytoscape/D3 frontend with saved
  Cypher pivots.
- **Effort:** L.

### A9. Origin-IP discovery behind CDN/WAF
- **What:** combine `cloudfail`, historical DNS (SecurityTrails), cert-SAN pivots, and
  favicon-hash matches to find the real origin behind Cloudflare/Akamai.
- **Why:** the origin is often the real attack surface; CDN-fronted recon misses it.
- **How:** a dedicated enrichment chain triggered on `tags=[cdn]` hosts.
- **Effort:** M–L.

### A10. Differential scope & multi-target campaigns
- **What:** run one campaign across many apexes (a whole org / acquisition list), with
  per-apex scope and a unified inventory + cross-apex correlation.
- **Why:** real engagements target organizations, not single domains.
- **How:** `workspace` already in schema; add a campaign layer over multiple `scan`s.
- **Effort:** M.

---

## Tier 3 — Strategic / platform maturity

### A11. Distributed worker pool + scan egress fleet
- **What:** horizontally scale workers; route active traffic through a managed pool of
  egress IPs/proxies (the rate-limit/threading design in `05-flow-architecture.md` §6).
- **Why:** scale to hundreds of targets; control egress reputation (OPSEC, `D6`).
- **How:** Temporal task queues (ADR-002) + the existing `proxy_pool`/`rate_limiter`.
- **Effort:** L.

### A12. Plugin SDK + community adapter registry
- **What:** let users drop in a new tool via a YAML contract (`tools.yaml`) + a tiny
  adapter, with versioned, signed tool images.
- **Why:** the recon ecosystem moves fast; extensibility is survival.
- **How:** the adapter contract (`adapters/base.py`) + registry already make this ~80%
  there; formalize a plugin entry-point and a `recontool plugins add` command.
- **Effort:** M.

### A13. Findings triage workflow + integrations
- **What:** finding states (open/triaged/false-positive/fixed), assignment, comments, and
  push to Jira / GitHub Issues / DefectDojo; import URLs to Burp; export Nmap XML.
- **Why:** recon output must flow into the team's existing workflow to be actioned.
- **How:** `finding.status` exists; add a notes/assignee table + export adapters.
- **Effort:** M.

### A14. Compliance & evidence pack
- **What:** per-scan signed evidence bundle (what was scanned, when, from which egress IP,
  under what authorization) + auto-redacted client report.
- **Why:** professional engagements need defensible audit trails (`D6`, `D10`).
- **How:** `audit_log` already captures the trace; add a bundler + report templater.
- **Effort:** M.

---

## Tier 4 — Nice-to-have / niche

| Feature | One-liner | Effort |
|--------|-----------|--------|
| A15. Slack/Discord bot | run scans + get alerts from chat | S |
| A16. Scheduled retests of fixed findings | confirm a finding stays fixed | S |
| A17. Passive-only "stealth recon" preset | zero target contact, OSINT report | S |
| A18. Screenshot perceptual-diff | flag visual change on a host over time | M |
| A19. Mobile/APK recon category (Cat 26) | apkleaks/MobSF endpoints+secrets | M |
| A20. Cost dashboard | per-provider API spend + budget alarms | S |
| A21. "Explain this asset" | LLM traces how/why an asset was discovered | M |

---

## Recommended build order (the short list)

```
1. A1  Continuous monitoring + diff      ← the EASM differentiator
2. A2  Live streaming display            ← UX, makes long scans usable
3. A4  Favicon-hash pivoting             ← cheap, finds hidden infra
4. A3  Resume/checkpoint                  ← reliability for long scans
5. A6  Smart wordlists                    ← better active recon hit-rate
6. A7  AI enrichment (incremental)        ← prioritization + reporting
7. A8/A11 Graph UI + distributed scale    ← platform maturity
```

These extend the **existing** architecture (engine, schema, adapter contract, rate/proxy
layer) without redesign — each is an additive module or a new adapter, consistent with
the recursive engine in `06-recursive-flow.md`.
