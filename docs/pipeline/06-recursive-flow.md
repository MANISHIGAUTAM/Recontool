# Recursive Recon Flow — The Convergence Engine

This document specifies the **core engine**: give it a single URL/domain, it runs passive
recon, validates which hosts are **live**, runs active scans **only on live hosts**, and
feeds every newly discovered asset back into the loop until nothing new is found
(convergence) or a budget/depth cap is hit.

It answers the three things you asked for:
1. **Store everything, display the full subdomain inventory** (live *and* dead).
2. **Run active scans on LIVE hosts only.**
3. **Re-use discovered output to rescan recursively** (output of step N = input of step N+1).

> Companion docs: `05-flow-architecture.md` (linear stage view + cardinality),
> `07-tool-io-reference.md` (per-tool invocation/output/storage), `03-category-pipelines.md`.

---

## 1. Mental model: a fixpoint over a typed asset graph

Recon is a **fixpoint computation**. We keep a growing, deduplicated set of assets. Each
iteration applies discovery + enrichment functions to the *newly added* assets and adds
whatever they produce. Because dedup makes the asset set monotonic and the in-scope
universe is finite, the loop **provably terminates** when an iteration adds nothing new.

```
  STATE:  store = deduped assets/edges/findings   (the canonical DB)
          frontier = assets discovered last iteration but not yet "expanded"
          seen = every asset already expanded
          depth = current recursion depth

  CONVERGE when:  frontier == ∅   (no new assets)
             OR   depth >= MAX_DEPTH
             OR   budget exhausted (time / API credits / task count)
```

This is the difference from the old "fixed phases run once" model: here **discoveries
re-enter the pipeline** automatically until the surface stops growing.

---

## 2. The engine loop (pseudocode)

```python
def recon(seed_url, scope, authorize_active, profile):
    store.add(seed_asset(seed_url))            # 1 apex (+ host)
    frontier = {apex_domain(seed_url)}         # things to expand
    seen = set()
    depth = 0

    while frontier and depth < MAX_DEPTH and not budget_exhausted():
        domains = [a for a in frontier if a.type in (domain, subdomain)]

        # ── A. PASSIVE DISCOVERY (no contact) on NEW domains ──────────────
        passive_out = run_parallel(PASSIVE_SOURCES, inputs=domains)
        #   subfinder, crt.sh, certspotter, chaos, securitytrails, otx,
        #   hackertarget, shodan(hostname:), censys(SAN), netlas, urlscan, uncover
        new = store.upsert(passive_out)        # dedup -> only genuinely new assets

        # ── B. LIVE VALIDATION (cheap active) on NEW subdomains ───────────
        #     This is what splits "known" from "live". ALWAYS runs (needed to
        #     decide what is reachable), but is rate/scope gated.
        resolved = dnsx_resolve(new.subdomains)          # drop NXDOMAIN + wildcards
        store.mark(resolved, resolves_to=ips, cname_to=cnames)
        live     = httpx_probe(resolved.subdomains)      # status/title/tech/tls
        store.mark(live, is_live=True, tech=…, service=…)

        # ── C. ACTIVE ENRICHMENT — LIVE HOSTS ONLY, IF AUTHORIZED ─────────
        if authorize_active and profile.active_enabled:
            active_out = run_parallel(ACTIVE_ENRICH, inputs=live.hosts)
            #   per LIVE host: gau, katana(+JS), gowitness, tlsx, ffuf,
            #                  paramspider, nuclei, subjack, sslyze
            #   per IP:        naabu -> nmap, internetdb, greynoise
            new += store.upsert(active_out)

        # ── D. FEED-BACK: which new assets are worth expanding? ───────────
        frontier = {a for a in new
                    if a.type in (domain, subdomain)        # expandable types
                    and scope.contains(a)                    # in-scope only
                    and a not in seen}
        seen |= {a for a in new}
        depth += 1

    return store      # converged inventory + findings
```

Key properties:
- **B always runs** (resolution/probe is how we *know* what's live) but is bounded by the
  rate profile; **C only runs on `live` hosts and only when `authorize_active`**.
- **Dedup before re-queue** → the frontier shrinks to truly-new assets → guaranteed to
  converge.
- Passive-only mode skips C entirely and still produces the full subdomain inventory with
  a live/dead flag from B.

---

## 3. What feeds the recursion (the ⟳ edges)

New in-scope assets that re-enter the loop come from **five sources**. This is the
"use the output as the next input" crux, made concrete:

| ⟳ Feedback source | Tool that produces it | New asset type | Why it finds more |
|-------------------|----------------------|----------------|-------------------|
| **Cert SANs** | `tlsx` on live :443, `censys`, `crt.sh` | `subdomain` | a live host's cert lists sibling hostnames |
| **JS-referenced hosts/URLs** | `katana`, `jsluice`, `linkfinder` | `subdomain`, `url` | apps hardcode API/CDN hostnames in JS |
| **CNAME targets** | `dnsx -cname` | `subdomain` (if in-scope) | chained hostnames reveal infra |
| **Related/sibling apex domains** | reverse-WHOIS, `whoisxml`, `censys` org | `domain` | same org owns other domains (re-run full passive) |
| **Reverse-DNS / ASN sweep** | `asnmap`→`mapcidr`→PTR, `internetdb` | `subdomain`, `ip` | hosts on the org's IP ranges |

Each re-entry is **scope-checked** (out-of-scope discoveries are *stored & displayed* but
**never expanded or actively scanned**) and **depth-bounded**.

```
  apex ─passive─► subA (live) ─tlsx─► subB (SAN) ─passive─► subC ─httpx─► live ─katana─► subD(JS)
        └─ each new in-scope sub re-enters at "passive/resolve" until no new appear ─┘
```

---

## 4. The detailed state diagram

```
                    ┌────────────┐
   single URL ─────►│  SEED/SCOPE│  classify, apex, build scope, scan_id
                    └─────┬──────┘
                          ▼
                 ╔═════════════════════╗   depth++
        ┌───────►║  FRONTIER (new subs)║◄─────────────────────────────┐
        │        ╚═════════╤═══════════╝                              │
        │                  ▼                                          │
        │        ┌────────────────────┐                              │
        │        │ A. PASSIVE DISCOVERY│  parallel API/CLI sources    │
        │        │  -> subdomains,ip,  │                              │
        │        │     cert,url        │                              │
        │        └─────────┬──────────┘                              │
        │                  ▼ normalize+dedupe                         │
        │        ┌────────────────────┐                              │
        │        │ STORE (DB)          │  display: ALL subdomains      │
        │        │  + display update   │  (live? unknown yet)          │
        │        └─────────┬──────────┘                              │
        │                  ▼                                          │
        │        ┌────────────────────┐                              │
        │        │ B. LIVE VALIDATION  │  dnsx (resolve, drop dead/    │
        │        │  dnsx -> httpx      │  wildcard) -> httpx (probe)   │
        │        └─────────┬──────────┘                              │
        │             live │ dead                                     │
        │      ┌───────────┴──────────┐                              │
        │      ▼                      ▼                               │
        │ ┌──────────┐         ┌────────────┐                        │
        │ │ is_live= │         │ is_live=    │  stored + displayed,    │
        │ │  TRUE    │         │  FALSE      │  but NEVER active-scanned│
        │ └────┬─────┘         └────────────┘                        │
        │      ▼                                                      │
        │   ◆ authorize_active ?  ── no ──► (passive report)          │
        │      │ yes                                                  │
        │      ▼                                                      │
        │ ┌────────────────────────────────────────────┐             │
        │ │ C. ACTIVE ENRICHMENT (LIVE HOSTS ONLY)       │             │
        │ │  web:  gau, katana(+JS), gowitness, ffuf,    │             │
        │ │        paramspider, tlsx, nuclei, sslyze     │             │
        │ │  ip :  naabu->nmap, internetdb, greynoise    │             │
        │ │  -> new subs (SAN/JS/CNAME), urls, services, │             │
        │ │     findings                                 │             │
        │ └─────────┬────────────────────────────────────┘             │
        │           ▼ normalize+dedupe                                 │
        │   ┌──────────────────┐                                       │
        │   │ NEW in-scope subs │── yes, and depth<MAX ────────────────┘
        │   │ discovered?       │
        │   └────────┬──────────┘
        │            │ no (frontier empty) / depth==MAX / budget hit
        │            ▼
        │     ┌─────────────┐
        └─────│ CONVERGED   │──► REPORT / EXPORT / GRAPH / DIFF / ALERT
              └─────────────┘
```

---

## 5. Live-only active scanning — the guarantee

Two independent mechanisms ensure active tools touch **only live, in-scope** hosts:

1. **Input filtering:** the active-enrichment stage is fed `store.assets(is_live=True,
   in_scope=True)` — dead/unknown/out-of-scope hosts are never in the input list.
2. **Per-activity re-check (defense in depth):** every active adapter re-validates
   `scope.contains(target)` and `asset.is_live` before egress, and refuses + audits
   otherwise (matches `D6-opsec.md` ADR-008/009).

```
   store.assets ──filter(is_live=True, in_scope=True)──► [katana, nuclei, naabu, …]
                                                          └─ each re-checks before egress
```

So even a bug or a manual call cannot make an active tool hit a dead or out-of-scope host.

---

## 6. What gets stored & displayed at each step

Everything is persisted (DB) and surfaced (console/UI). Full schema in `D3-data-schema.md`.

| Step | Stored (DB) | Filesystem artifact | Console / UI shows |
|------|-------------|---------------------|--------------------|
| Seed | `scan`, seed `asset` | — | scan header (target, profile, scope) |
| A. Passive | `asset(subdomain/ip/cert)`, `asset_source`, `edge` | raw JSON per tool (`artifacts/<scan>/raw/<tool>/`) | live-updating **Subdomains** table (value, sources, confidence, live=?) |
| B. Validate | update `asset.is_live`, `service`, `edge(resolves_to/cname_to)` | dnsx/httpx raw | **Live hosts** panel (status, title, tech, IP); dead count |
| C. Active | `endpoint(url)`, `service(port/product)`, `finding`, new `asset` | JS files (`artifacts/js/`), screenshots (`artifacts/screenshots/`), response bodies | **Endpoints**, **Findings** (severity-sorted), **Screenshots** gallery |
| Converge | `asset_state` snapshot (for diff) | export JSON/CSV/MD | **Summary** + **Diff** (new since last scan) |

### Console display model (what the operator sees)

```
recontool scan acme.com --authorize-active

[scan a1b2] acme.com  profile=normal  active=YES  depth 0→
┌ Subdomains ─────────────────────────────────────────────┐
│ api.acme.com           live ✓  200  nginx     conf 0.98  │   ← updates as found
│ admin.acme.com         live ✓  403  -         conf 0.90  │
│ old.acme.com           dead ✗  -    -          conf 0.90  │   ← stored, shown, NOT scanned
│ … 247 more (120 live / 127 dead)                         │
└──────────────────────────────────────────────────────────┘
[depth 1] tlsx found 6 new SANs, JS found 3 new hosts → re-queued
[active]  katana 120 hosts · nuclei 120 hosts · naabu 95 IPs …
┌ Findings ───────────────────────────────────────────────┐
│ CRITICAL  CVE-2023-… on api.acme.com:443 (nuclei)        │
│ HIGH      subdomain-takeover  shop.acme.com (subjack)    │
└──────────────────────────────────────────────────────────┘
converged at depth 2 · 256 subs · 120 live · 18 findings · report → out.json
```

The UI (web) renders the same data from the API: a sortable/filterable **asset
inventory** (toggle live/dead/in-scope), a **graph** (Neo4j projection), a **findings**
triage board, a **screenshots** gallery, and a **diff** view vs the previous scan.

---

## 7. Termination & safety bounds (so it can't run forever / explode)

| Bound | Default | Purpose |
|-------|---------|---------|
| `MAX_DEPTH` | 3 | cap recursion levels (apex → SAN/JS subs → their subs) |
| `max_new_per_iter` | configurable | stop pathological wildcard/CDN fan-out |
| Budget: time | profile-based | wall-clock ceiling per scan |
| Budget: API credits | per-provider | stop before burning paid quotas (D10) |
| Budget: task count | profile-based | backpressure on huge fan-outs |
| Scope gate | always | out-of-scope assets stored but never expanded/scanned |
| Wildcard filter | `dnsx`/`puredns` | drop `*.acme.com` wildcard noise before it pollutes the frontier |
| Dedup | always | guarantees monotonic convergence |

---

## 8. Worked example — `acme.com` iteration by iteration

```
depth 0  frontier={acme.com}
  A passive   -> 250 subdomains, 40 ip, 12 cert        (store=250)
  B validate  -> 180 resolve, 120 live, 130 dead       (mark is_live)
  C active(120 live): tlsx +6 SANs, katana JS +3 hosts, gau 8k urls, nuclei 11 findings
  D new in-scope subs = 9 (6 SAN + 3 JS)               -> frontier={9}

depth 1  frontier={9 new subs}
  A passive(9)-> 4 more subs                            (store=263)
  B validate  -> 9 of 13 live                           (live=129)
  C active(13): nuclei +2 findings, 1 new SAN host
  D new in-scope subs = 1                                -> frontier={1}

depth 2  frontier={1}
  A/B/C       -> 0 new in-scope subs                    (live=130)
  D frontier = ∅                                        -> CONVERGED

result: 263 subdomains (130 live / 133 dead), 95 IPs, 9.2k urls, 13 findings
```

Notice: **active scans only ever ran on the 130 live hosts**, the full 263 are stored and
displayed, and the loop stopped on its own when depth-2 added nothing new.

---

## 9. How this maps to the implementation (and the gaps to close)

| Engine concept | Code today | Change needed |
|----------------|------------|---------------|
| Frontier/fixpoint loop | phase loop with single passive recursion | generalize to frontier-of-new-assets loop (this doc) |
| `live_host` input type | `is_live` flag only | promote to a gathered input; enrichment consumes it |
| Active-on-live-only | active phase runs on all subs | filter inputs to `is_live=True` + per-adapter re-check |
| ⟳ feedback (SAN/JS/CNAME) | partial (passive re-run) | wire the 5 feedback sources in §3 |
| Live display table | CLI summary at end | stream subdomain/live updates during scan |

These are the concrete next implementation steps after the docs (small, high-value).
