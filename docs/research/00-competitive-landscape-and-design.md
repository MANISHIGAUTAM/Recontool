# Recontool — Competitive Research & Next-Gen Design

> In-depth research into the best tools of this kind (features, tool selection,
> integration, capabilities), mapped onto the owner's vision: a red-team-grade,
> total-coverage recon engine driven by a dynamic matrix + parallel worker nodes,
> that misses nothing for a target and recursively rescans every key it extracts.
>
> Companion to the single-source spec [`../00-FINAL-ARCHITECTURE.md`](../00-FINAL-ARCHITECTURE.md).
> Knowledge cutoff Jan 2026; web search was rate-limited at authoring time, so the
> competitive analysis is from first-hand knowledge of these tools' architectures.

---

## 1. The landscape — who's best, and why

| Tool | Lang / model | What it nails | Where it stops |
|------|--------------|---------------|----------------|
| **BBOT** | Python, **recursive event-driven** | Everything is an *event* (DNS_NAME, URL, EMAIL, IP, …); modules subscribe to event types and emit new events → automatic recursion. ~100 modules, scope-aware, presets. The closest architectural cousin to Recontool. | Single-process; no persistent resumable queue; no real UI; OSINT/people depth is shallow; no anti-bot/browser layer. |
| **reconFTW** | Bash orchestrator | Chains ~100 best-of-breed CLIs (subfinder, amass, httpx, katana, nuclei, gau, …) through sensible phases; great defaults; **Axiom** integration for distributed fan-out. | Sequential phase loop, not entity-recursive; no DB/graph; output is files; no OSINT/people; not programmable. |
| **Osmedeus** | Go, **workflow/YAML** | Declarative workflows; **web UI**; spins up **cloud instances** to distribute; notifications; clean reporting. | Workflow ≠ recursion; coverage depends on the YAML you write; OSINT-light. |
| **SpiderFoot** | Python, **typed-data correlation** | 200+ modules, **strong OSINT/people/breach/social**; event/data-type graph; web UI; correlation rules. | Not built for active web-attack-surface depth (crawl/JS/params/fuzz); slower; not a pipeline for bug-bounty-style chaining. |
| **Amass** | Go, **graph** | Best-in-class subdomain/DNS/ASN intel; org/ASN "intel" mode; passive+active; graph output. | Scope is DNS/network; no web/JS/people; not a general engine. |
| **theHarvester** | Python | Emails / names / hosts from **search engines** + some breach sources. | Narrow; one-shot; no recursion. |
| **Trickest / Axiom / Fleex** | Cloud fleets | **Distributed execution** — visual workflows (Trickest) or many cloud boxes splitting the target list (Axiom/Fleex). Directly relevant to "worker nodes". | Infra, not intelligence; you still bring the recon logic. |
| **Maltego** | GUI graph | Human-driven **link analysis / pivoting**; transforms. | Manual; not automated mass recon. |

**Takeaway.** No single tool combines (a) BBOT's recursive entity engine, (b)
reconFTW's curated active-web toolchain, (c) SpiderFoot's OSINT/people breadth, (d)
Axiom/Trickest's distributed execution, and (e) a real product UI. **That union is
the opening** — and it is exactly the owner's vision. Recontool already has (a) the
recursive engine, the curated toolchain, and an atomic-claim worker queue. The
differentiators still to build are deep OSINT/people + org-forest mapping, a live
browser/JS layer, the anti-blocking stack, and the UI.

---

## 2. The four recon pillars (the owner's "complete red-team" scope)

A target is not just a DNS tree. The engine must expand on **four planes at once**,
all feeding the same recursive frontier:

### 2a. Search-engine & internet-wide asset discovery
Every engine and index, one entry point: `uncover` (wraps Shodan/Censys/FOFA/ZoomEye/
Netlas), plus CT logs (crt.sh, certspotter), passive DNS (SecurityTrails, OTX,
HackerTarget), search dorking (Google/Bing/DuckDuckGo/Yandex via dork packs), and
code search (GitHub, grep.app, Sourcegraph, publicwww). **Goal: if an asset is
indexed anywhere public, we find it.**

### 2b. Passive → live-validate → active web (the kill-chain depth)
subfinder/amass/alterx → dnsx/puredns (resolve, wildcard-filtered) → httpx (live) →
naabu/nmap (ports) → tlsx (cert/SAN pivot) → katana + **live JS-rendering crawler**
→ linkfinder/jsluice (endpoints/secrets) → ffuf/feroxbuster (content) → arjun/x8
(params) → nuclei (templated checks). **Active runs only on confirmed-live hosts.**

### 2c. People / email / identity (the red-team human layer)
theHarvester + hunter.io (emails) → permutate to corporate format → verify
(EmailHippo) → breach correlation (HIBP, DeHashed, IntelX, Snusbase, LeakCheck) →
username pivots (Sherlock/Maigret/holehe) → LinkedIn employee enumeration
(linkedin2username, CrossLinked) → GHunt (Google account). Output: a roster of
people, emails, usernames, and leaked creds for the org — phishing/initial-access
fuel.

### 2d. Org "forest" — sibling sites & related entities
The non-obvious multiplier. Pivot from one seed to the whole estate:
- **Same analytics/ad IDs** (Google Analytics UA/GA4, AdSense) via publicwww/BuiltWith → sibling sites.
- **Favicon hash** (mmh3) → Shodan/ZoomEye → hosts sharing the favicon.
- **WHOIS registrant org / email** → reverse-whois → other domains.
- **TLS cert SAN + org field**, shared **name servers / MX**, shared **ASN/CIDR**.
- **Copyright/trademark footer** + acquisitions (Crunchbase-style) → subsidiaries.
Each discovered sibling domain becomes a **new seed** at the frontier.

---

## 3. Execution model — dynamic matrix + worker loop (what "best" looks like)

The owner's "dynamically building matrix + loop with parallel worker nodes" is the
right model, and it maps 1:1 onto what is now built (see FINAL-ARCHITECTURE §1–2):

```
seed ─► enqueue(work_item: key×tool, deduped)
          │
          ▼  ┌──────────────── worker nodes (N async × M processes/hosts) ───────────────┐
   atomic claim (pending→running CAS, SKIP-LOCKED safe) → run tool → normalize+dedupe
          │                         │ typed out/<tool>.<type>.jsonl + raw/                │
          │                         ▼                                                     │
          │              extract every key component (subdomain, ip, url, email, …)       │
          │                         │ noise gate (wildcard/CDN/scope/dup)                 │
          │                         ▼                                                     │
          └──────────── enqueue downstream work for each NEW key ◄──────────────── loop ──┘
                                    │ converges when no new in-scope keys
                                    ▼
                       graph + evidence lake + report/UI
```

- **Dynamic matrix** = the `tool_row` registry (which tool consumes/produces which
  entity type) × the `work_item` queue (live (key,tool) jobs). The matrix is a
  *view*; the two tables are the truth (never a 560-column sheet).
- **Routing** is a deterministic `RouteIndex` (type→tools dict), not AI.
- **Parallelism** = N async workers per process, scaled across processes/hosts by
  the atomic claim. Performance is sub-linear by design (bounded enqueue, covering
  claim index) — see FINAL-ARCHITECTURE §8a.
- **Total coverage** = `--tools all` runs every runnable tool; nothing is skipped
  because it "looks redundant" (overlap raises confidence; dedupe makes it free).

**"Don't miss a single piece of information."** The guarantees that deliver this:
1. **Every produced type is a key** — subdomain, ip, url, **endpoint**, email,
   username, **secret**, repo, bucket, org, cert, favicon-hash, analytics-id.
2. **Every key is routed** to all consumers (subsumption: a subdomain also feeds
   domain-consumers), so a discovery can never dead-end for lack of a wiring.
3. **Historical sources are first-class** — gau/waymore/wayback CDX pull *dated*
   URLs; those URLs are fetched and mined for secrets/keys (a 2019 `/config.js`
   with an API key is exactly the "dated endpoint containing keys" case).
4. **Idempotent dedupe** means re-discovery strengthens confidence, never rescans.

---

## 4. Total-coverage data harvesting — the specific wins

| "Don't miss" case | How the engine catches it |
|-------------------|---------------------------|
| Dated endpoint w/ keys in Wayback | gau/waymore → URL keys → fetch body → SecretFinder/jsluice/trufflehog → `secret` + `endpoint` entities |
| Secret in old JS | historical JS harvest → AST/regex secret mining → `secret` |
| A person / email | theHarvester/hunter → `email`; breach pivot → leaked creds; username pivot → accounts |
| Sibling/forest site | analytics-id / favicon-hash / reverse-whois → new `domain` seed → full re-expansion |
| Hidden API | katana + browser crawl capture XHR/fetch + GraphQL introspection → `endpoint` |
| Param for fuzzing | arjun/x8/paramspider → `param` → feeds nuclei/dalfox |
| Exposed bucket | cloud_enum/s3scanner + grayhatwarfare → `bucket` |

**The key-extraction-for-rescan loop is the heart**: every tool's output is parsed
into typed entities, each entity is a new key, each new key re-enters the matrix and
triggers its consumers. That recursion is what turns "a domain" into "the entire
estate + its people + its history."

---

## 5. Future vision (researched, with the concrete stack)

### 5a. The anti-blocking / performance stack (so nothing throttles you)
- **Egress IP rotation** — proxy pool (already `net/proxy_pool.py`): round-robin /
  sticky / random, quarantine failing proxies. Add **residential/mobile** pools for
  hard targets; per-provider QPS so each source stays under its ban threshold.
- **Anti-bot / Cloudflare** — a **headless-browser solver** (FlareSolverr-style) for
  challenge pages; `puppeteer-stealth`/`undetected-chromedriver` fingerprint evasion;
  **JA3/TLS fingerprint** randomization (curl-impersonate / utls) so requests look
  like real browsers.
- **CAPTCHA** — pluggable solver API (2captcha/anti-captcha) behind a flag, used only
  where authorized.
- **AWS / cloud distribution** — the atomic-claim queue already makes this trivial:
  package the worker as a container, run it on N Fargate/EC2/Lambda nodes pointed at
  one Postgres `RECON_DB_URL`; each node claims work independently. Add **Axiom-style
  ephemeral fleets** for burst scans. Rate limiting + circuit breakers prevent
  self-inflicted bans.
- **Speed** — async I/O fan-out, per-host concurrency caps, DNS via mass resolvers
  (puredns/massdns), and the sub-linear queue (bounded enqueue + covering index).

### 5b. The UI (control + reflect the data)
- **Live scan control** — start/stop, pick the seed, choose a **tool profile** or
  toggle individual tools over the matrix (`tool_row.default_on` is already the
  backing flag), set depth/concurrency/profile.
- **Live status** — stream the event bus / poll `work_item` (pending/running/
  completed counts, per-tool timing from the structured worker logs) → progress + a
  worker-utilization view.
- **Data views** — an **interactive graph** of the expanding surface (entities +
  `edges`), filterable tables per entity type, and **evidence drill-down** (click any
  finding → raw response + provenance). Diff view across scans ("what changed").
- **Plugins** — a thin plugin API so users add a tool as a declarative spec (the
  generic-adapter contract already supports this) or a custom enrichment, plus
  webhooks/notify integrations (Slack/Discord/Telegram).
- **Stack** — FastAPI over the existing DB + an SSE/WebSocket bridge off the event
  bus; React/graph front-end. The engine is already UI-ready (DB-backed state,
  typed outputs, deterministic registry).

---

## 6. Gap analysis vs. the current build (what's done, what's next)

| Capability | Status | Next |
|------------|--------|------|
| Recursive entity engine | ✅ `engine/runner.py` (live, tested) | — |
| Atomic-claim multi-worker, scalable | ✅ `engine/worker.py` | containerize for AWS fleet |
| All 563 tools, flag-gated profiles | ✅ `engine/selection.py` | keep wiring keyless/binary specs |
| Deterministic routing + dynamic matrix | ✅ `engine/router.py` + `tool_row`/`work_item` | — |
| Typed outputs + dedupe + noise control | ✅ G4/G7 | cross-scan dedupe store |
| Sub-linear performance | ✅ §8a | profile a 10k-entity scan |
| **Live JS-rendering crawler** | ❌ **top priority** | wire a Playwright tool: render, capture XHR/GraphQL, harvest JS → endpoints/secrets/params |
| **People/email/breach OSINT depth** | ⚠️ partial (theHarvester wired) | wire hunter/holehe/maigret/HIBP/DeHashed + email-format permutation |
| **Org-forest pivots** | ❌ | favicon-hash, analytics-id, reverse-whois → sibling `domain` seeds |
| **Anti-bot / browser solver** | ❌ (proxy pool exists) | FlareSolverr-style solver + TLS-impersonation HTTP client |
| **UI / API layer** | ❌ | FastAPI + SSE over the event bus + graph front-end |
| Frontier/checkpoint/policy into live loop (G3/G5) | ⚠️ built, partially wired | finish wiring resume + dead-letter |

**Build order (highest leverage first):**
1. **Live JS-rendering crawler** — the one capability that turns this from "best-in-
   class classic recon" into genuinely novel (captures application data static recon
   can't). Feeds the same loop.
2. **OSINT/people + org-forest pivots** — completes the red-team scope; high
   differentiation vs reconFTW/BBOT.
3. **Anti-blocking stack** (browser solver + TLS impersonation + residential proxies).
4. **UI/API** — makes it a product; unlocks tool selection + plugins + live graph.
5. **AWS fleet packaging** — container + IaC for the worker; the queue already
   supports it.

---

## 7. The one-sentence definition of "next-gen" here

> Point it at a seed and walk away; it expands across search engines, live web +
> rendered JS, people/breach data, and the whole org forest in parallel across
> worker nodes, misses nothing (down to a dated Wayback endpoint leaking a key),
> stores every artifact with provenance, recursively rescans every key it extracts,
> routes around anything that tries to block it, and shows you the entire result as
> a live, navigable graph you can steer.

That is the union no existing tool delivers — and the architecture to reach it is
already in place; sections 6.1–6.5 are the remaining build.
