# Recontool — Final Architecture, Tools Vision & Tech Roadmap

> **This is the single source of truth.** Every other doc is subsidiary and
> indexed at the bottom. If another doc disagrees with this one, this one wins
> and the other should be updated. Last revised for the event-driven engine v2.

---

## 0. The vision in one paragraph

Recontool is a **self-directing, recursive reconnaissance engine**. You give it a
seed (a root domain), and it fans out across hundreds of passive and active
sources, and — this is the core — **every new discovery immediately becomes a new
lead**. A discovered subdomain is resolved, probed, crawled, fingerprinted, and
its IP is reverse-looked-up, port-scanned, and pivoted on, each result feeding the
next, until a branch stops yielding new in-scope information. It preserves all raw
evidence and the derived graph, runs independent work in parallel, prioritizes the
most promising leads, suppresses noise, and resumes cleanly after interruption.
The shape is a **frontier/convergence engine**, not a linear scanner.

---

## 1. Core data model (the thing to get right first)

The engine's state is **two normalized tables**, not a wide spreadsheet. The
"matrix" view (entities × tools) is a *report* generated from these — never the
storage. See [`../data/recon_matrix.xlsx`](../data/recon_matrix.xlsx) (regenerate
with `python -m recontool.inventory.build_matrix`).

### Tools — static capability registry (defines the recursion graph)
One row per canonical tool: `name`, `category`, `consumes[]`, `produces[]`,
`classification` (passive/active/hybrid), `integration`, runnable contract.
This is fixed at build time and seeded from `data/flow_plan.json`.

### WorkQueue — dynamic job table (the live database)
One row per `(key, tool)` job:

| col | meaning |
|-----|---------|
| `key` | the discovered entity (e.g. `api.grow.in`) |
| `key_type` | `domain` \| `subdomain` \| `live_host` \| `url` \| `ip` \| `cidr` \| `asn` \| `subdomain+path` \| … |
| `parent_key`, `depth` | provenance + recursion depth (for budget caps) |
| `tool` | which tool runs against this key |
| `status` | `pending → in_progress → completed \| failed` |
| `output_path` | the typed output file produced |
| `new_keys_found` | entities emitted (the recursion delta) |

**Why not a 532-column sheet:** it would be wide, sparse, and mostly N/A (a
subdomain row has nothing for the 90 people-search columns). The normalized form
is the same information without the waste, and it's what the existing
`engine/pending_keys.py` + `frontier.py` already model.

### Idempotent keys — never rescan the same thing (already implemented)
Every entity has a deterministic **canonical `dedupe_key`** (`core/dedupe.py`):
equivalent representations collapse (`API.Grow.in.`, `api.grow.in`,
`https://api.grow.in/` → one key). On insert, the normalizer
(`normalize/engine.py`, the sole writer) checks the key: **if it already exists it
UPDATEs** (strengthens confidence, refreshes `last_seen`); only a genuinely new
key is inserted. The same rule governs the WorkQueue — a `(key, tool)` job is
created only if that pair is new, so **no endpoint is ever rescanned**. This is the
"check if it exists, push only if new" behavior, and it already works at the
normalization layer; the WorkQueue must reuse the same canonical keys.

### The canonical entity vocabulary (primary keys)
`domain, subdomain, live_host, url, endpoint, ip, cidr, asn, service, host_port,
cert, tech, js_file, secret, bucket, repo, email, username, org, finding`.
The composite key **`subdomain+path`** is first-class: a single host can serve
multiple apps under different paths, each worth its own recursive rescan.

---

## 2. Where AI is used — and where it must NOT be

This is the most common design mistake, so it's stated explicitly.

**AI IS used for (4 bounded functions, each with a deterministic fallback):**
1. **Entity extraction** — turn a tool's *unstructured* output into typed keys.
   Only for tools that don't already emit structured JSON; structured tools are
   parsed deterministically.
2. **Prioritization** — score leads (a `dev.`/`admin.` host > a CDN edge).
3. **Recurse / converge decision** — "these 400 new hosts are wildcard noise, stop."
4. **Canonicalization** — decide `api.grow.in`, `api.grow.in.`, and
   `https://api.grow.in/` are one key.

**AI is NOT used for routing.** "Which tools accept a subdomain" is a deterministic
**join** over the Tools registry (`key_type → tools whose consumes includes it`),
computed once. Putting AI in that loop costs tokens and adds nondeterminism for
something a `WHERE` clause does perfectly. The routing map is precomputed in the
`Routing` sheet of `recon_matrix.xlsx` (e.g. `domain → 324 tools`, `ip → 89`,
`live_host → 80`).

---

## 3. Output discipline — typed files per tool, per mode

Every tool run writes raw provenance **and** one typed file per produced type:

```
artifacts/<scan_id>/raw/<slug>/...            # raw, untouched (provenance)
out/<key>/<slug>.<produced_type>.jsonl        # normalized, typed, append-only
```

A **multi-mode tool** writes to multiple typed files. Example: `ffuf` in
directory mode → `ffuf.url.jsonl`; in vhost mode → `ffuf.subdomain.jsonl`; in
param mode → `ffuf.param.jsonl`. Same for `tlsx` (`.subdomain` from SANs,
`.tech` from JARM) and `jsluice` (`.endpoint` from urls, `.secret` from secrets).
Append-only typed files give you a replayable, auditable, dedupe-friendly record —
this is how "maintain everything previously detected" is satisfied.

---

## 4. The recursion loop (and how it terminates)

```
seed ─► Router marks applicable tools `pending`
          │
          ▼
   Workers pull `pending` ─► in_progress ─► run tool ─► typed output files
          │
          ▼
   Extractor emits new keys ─► NOISE FILTER ─► dedupe (seen-set)
          │  (survivors only)
          ▼
   New keys ─► Router marks their applicable tools `pending`  ──┐
          │                                                     │
          └──────────────── repeat ◄────────────────────────────┘

Converge a branch when ANY holds:
  • it yields no new in-scope keys (seen-set fixpoint), OR
  • depth / per-scan budget cap reached, OR
  • the noise filter rejects the output (wildcard / CDN / duplicate).
```

The `seen`-set makes the frontier a **monotonic fixpoint over a finite in-scope
entity space**, so it provably terminates — already implemented in
`orchestrator/frontier.py`.

---

## 5. Noise control — load-bearing, not optional

A recursive engine amplifies false leads as fast as real ones. These sit between
"new keys found" and "Router marks pending", and are the **highest-priority gap**:

- **Wildcard-DNS detection** — reject `*.target.com` catch-alls before they
  spawn thousands of fake subdomains.
- **CDN/WAF exclusion** (`cdncheck`) — don't port-scan shared edge IPs or treat
  them as pivots.
- **Cross-scan + in-scan dedupe** (`anew`-style seen-set) — never re-queue a key.

Without this layer, the engine drowns in its own output. Treat it as a first-class
component, not a filter bolted on later.

---

## 6. Architecture gaps (current state → target)

| # | Gap | Current state | Target |
|---|-----|---------------|--------|
| **G1** | **Two disconnected orchestrators** | CLI runs the linear `ReconPipeline`; the recursive `engine/` ran a no-op `_default_execute` | ✅ **engine now alive** — `engine/runner.py` (`make_execute_fn` / `run_engine_scan`) runs real generic adapters, normalizes to the DB, and re-feeds `EntityDiscovered` to recurse; proven end-to-end in `tests/integration/test_engine_runner.py`. Remaining: expose via CLI + retire the linear loop |
| **G2** | **runnable count** | `runnable` now reads **actual contracts** (not a stale flag) → **72** runnable & climbing; all 563 persisted to `tool_row` (88 web-only kept & flagged). `stdin: true` spec support added → unlocks the stdin-driven CLI class (metabigor, dnsgen, …) | Keep wiring toward the **honest ceiling** (see §7b): ~200–250 keyless+binary tools are runnable unattended; ~146 need user keys; ~100 are GUI/manual/reference and stay available-but-not-runnable. Track with the `recon-integration-tracker` skill |
| **G3** | **Recursion is shallow** | `ReconPipeline.max_recursion=1`, passive-only, `_has_unprobed_growth` is a stub returning True | Frontier-driven convergence (already built in `frontier.py`) backing the live loop |
| **G4** | **No noise control** | no wildcard/CDN/scope filtering on re-feed | ✅ **done (optional)** — `engine/noise.py` `NoiseFilter` gates the re-feed path: dedupe + scope (free, deterministic), wildcard-DNS + CDN (opt-in, injected helpers). Off by default; enable with `recontool engine … --noise-control [--wildcard-filter]`. Tested in `tests/atomic/test_noise_filter.py` + an out-of-scope recursion-stop case in `tests/integration/test_engine_runner.py` |
| **G5** | **Frontier/checkpoint/policy built but unwired** | `frontier.py`, `core/policy.py` tested standalone | consumed by the live `run_scan` (gate, iterate, checkpoint, dead-letter) |
| **G6** | **Routing not registry-driven at runtime** | eligibility computed ad hoc | ✅ **done** — deterministic Router (`engine/router.py`) over `tool_row` with type subsumption (subdomain → domain consumers) + dedupe-on-enqueue; tested in `tests/atomic/test_matrix_router.py` |
| **G7** | **Output files not typed per mode** | raw under `raw/<tool>/` only | ✅ **done** — `ArtifactStore.save_typed` + runner write an append-only `out/<tool>.<type>.jsonl` per output type (multi-mode tools get one file per type); raw still under `raw/<tool>/`. Tested in `tests/integration/test_engine_runner.py` |
| **G8** | **Doc sprawl** | 600+ md files, overlapping roadmaps | this doc is the single source; others are subsidiary (Section 10) |

---

## 7. Tools vision — wire them all; overlap is a feature, not a bug

**Discovery breadth is essentially complete** — DNS, CT logs, passive DNS,
Wayback/archive across timelines, Shodan/Censys/FOFA/ZoomEye/Netlas, ASN/BGP,
search dorking, cloud buckets, code/secrets, people/identity, dark web.

**Design decision: keep every tool available.** A later UI lets each user pick
their own tool set; the platform ships a **recommended-default profile** (below)
that we vouch for as "this covers everything," and the user can opt into more.
Overlap is intentional redundancy — different sources corroborate each other and
raise confidence — and it is *free* at runtime because **idempotent keys mean
overlapping tools that rediscover the same entity cost one stored record, not a
rescan** (see §1). So we do **not** prune; we *rank*.

### 7a. The recommended-default profile (the "on" set we vouch for)
These are flagged `default_on` so a fresh scan runs a high-signal, non-wasteful
set out of the box. Everything else stays one toggle away in the UI.
| Cluster | Recommended default | Also available (user toggle) |
|---|---|---|
| Subdomain enum | `subfinder`, `amass` (passive), `crtsh` | sublist3r, assetfinder, findomain, oneforall, ctfr, knockpy, sudomy |
| Search-engine asset disc. | `uncover` (wraps Shodan/Censys/FOFA/ZoomEye/Netlas) | the per-engine adapters |
| Archive/URL harvest | `waymore` (superset) | waybackurls, gau, gauplus |
| Screenshots | `gowitness` | eyewitness, aquatone, webscreenshot |
| Crawl/JS | `katana` + `pycrawl` | hakrawler, gospider, photon |
| People search | top 2–3 by reliability | the other ~15 |
| Subdomain permutation | `alterx` | dnsgen, gotator |

The default vs available split is a **column in the Tools registry**
(`default_on: true|false`), not a deletion. Changing it is a config/UI concern,
never a code change.

**Demotion rule (strict):** a tool is moved off `default_on` only when it is an
**exact-output duplicate** of a superset tool — i.e. we are certain it returns the
same data. That tool stays *available*, just off by default. Overlapping-but-
different sources (crt-sh vs certspotter, subfinder vs amass, dnsx vs massdns) are
**kept on** because they corroborate each other and raise confidence. The current
exact-overlap demotions live in `catalog.EXACT_OVERLAP` (e.g. `gauplus → gau`, an
unmaintained fork querying the identical Wayback/CommonCrawl/OTX/URLScan sources).

### 7b. The gaps to ADD (now documented)
All 32 are documented in [`tools/SUGGESTED-ADDITIONS.md`](tools/SUGGESTED-ADDITIONS.md),
each with a `suggested_addition` capability doc. They are kept **separate from the
extracted inventory** to preserve its provenance. Highlights:

- **Noise control (do first):** `cdncheck`, wildcard filtering, cross-scan dedupe.
- **Glue/plumbing:** `anew`, `gf`, `unfurl`, `qsreplace`, `mapcidr`, `dsieve`.
- **Active web/content:** `ffuf`, `feroxbuster`, `kiterunner`.
- **TLS/fingerprint:** `tlsx`, `fingerprintx`, `sslyze`.
- **Param/API/GraphQL:** `x8`, `graphw00f`, `clairvoyance`.
- **JS:** `jsluice`, `mantra`. **Crawl:** `gospider`.
- **Favicon pivot:** `favfreak`, `fav-up`. **Cert pivot:** `cero`.
- **Active vuln:** `dalfox`. **Port:** `nmap`, `masscan`. **ASN OSINT:** `metabigor`.
- **Code-platform subdomains:** `github-subdomains`, `gitlab-subdomains`.

### 7b. The honest integration ceiling (why it is not "all 500 runnable")

"Runnable unattended" is bounded by what the tools physically are — measured from
`data/flow_plan.json`:

| Bucket | Count | Runs E2E without user action? |
|--------|------:|-------------------------------|
| `web/manual` (GUI portals, browser-only) | **81** | No — no programmatic interface |
| Reference indexes + workflow presets (§18/§19) | **20** | No — they are *lists of tools*, not tools |
| API requiring a **key per config** (Shodan, Censys, IntelX, BinaryEdge…) | **146** | Only when the user supplies the (often paid) key |
| **Keyless** APIs | **107** | Yes ✅ |
| Installable **binaries** | **199** | Yes once installed ✅ (overlaps keyless) |

So **~100 tools cannot be runnable** (GUI/manual/reference) and **~146 only run with
the user's keys**. The achievable unattended universe is the keyless + binary set
(~200–250). They are all **kept available** in `tool_row` (nothing eliminated); the
non-runnable ones simply carry `runnable=false` and a reason, and a future UI can
still surface them (manual/assisted, or "enter a key to enable"). Each remaining
wire-up is genuine per-tool work (real endpoint/flags + correct parse), which is
why honest progress is incremental — the `runnable` metric now reflects real
contracts and climbs as specs land.

---

## 8. Core capabilities (the definition of "done" for the final version)

1. **Recursive entity-driven discovery** — frontier + seen-set convergence.
2. **Deterministic routing** — `key_type → tools` join; AI only for the 4 functions.
3. **Parallel, layered concurrency** — global / per-tool / per-host semaphores.
4. **Typed evidence preservation** — raw + `out/<key>/<slug>.<type>.jsonl`, replayable.
5. **Noise control** — wildcard, CDN, cross-scan dedupe before re-feed.
6. **Dedupe + confidence** — canonical keys, multi-source corroboration scoring.
7. **Resume / checkpoint / dead-letter** — exact resume after interruption.
8. **Scope + active-authorization gate** — passive by default; active gated.
9. **AI supervisor (token-frugal)** — light model for triage, heavy for narrative.
10. **IP rotation** (deferred) — proxy pool to avoid rate-limit bans.
11. **Incremental scans** — SHA-256 fingerprinting to skip unchanged inputs.

---

## 9. Single tech roadmap (one list, smallest slice first)

> Phases are ordered so each builds on the last; do not jump ahead.

**P0 — Make the engine alive (unblocks everything)**
1. ✅ **done** — `ToolRow` + `WorkItem` tables (`engine/models.py`); seeded from the full catalog (`inventory/seed_matrix.py`, all 563 tools).
2. ✅ **done** — deterministic **Router** with subsumption + dedupe-on-enqueue (`engine/router.py`); tested (`tests/atomic/test_matrix_router.py`).
3. ✅ **done** — `EventDrivenOrchestrator.execute_fn` wired to real generic adapters (`engine/runner.py`); runs, normalizes, and recurses on `EntityDiscovered`. Tested end-to-end.
4. One vertical slice with real tools installed: `domain → subfinder/crt-sh → subdomain → dns_resolve → ip → naabu → live_host → katana → url → converge`. ← **next** (expose `run_engine_scan` via the CLI).

**P1 — Make recursion safe**
5. Typed output writer + extractor (Section 3).
6. Noise-control layer (Section 5): wildcard, `cdncheck`, cross-scan dedupe.
7. Frontier-driven convergence backing the live loop; checkpoint after each stage.

**P2 — Close the active-recon gap & give users tool choice**
8. Wire the suggested tools (Section 7b) by group, starting with noise + glue, then content/TLS/API.
9. Add the `default_on` flag to the Tools registry + a per-scan tool-selection
   config (the recommended profile, §7a). The later UI reads this; idempotent keys
   (§1) make running extra/overlapping tools cheap, so nothing is pruned.

**P3 — Intelligence & scale**
10. AI as the 4 bounded functions, each with deterministic fallback.
11. Graph store (Neo4j) for the relationship/clue graph + evidence-pack export.
12. IP rotation + per-provider rate/circuit wiring; bandit-style source scoring.

**Cross-cutting:** keep `recon-integration-tracker` green every session;
regenerate `recon_matrix.xlsx` and the suggested docs when the tool set changes.

---

## 10. Subsidiary document index (everything else)

This doc supersedes the roadmap/vision content scattered below; consult these for
detail only.

| Area | Docs |
|------|------|
| Tool capability docs (532 extracted) | [`tools/`](tools/) · [`tools/README.md`](tools/README.md) |
| **Suggested additions (32)** | [`tools/SUGGESTED-ADDITIONS.md`](tools/SUGGESTED-ADDITIONS.md) |
| Execution matrix (planning view) | [`../data/recon_matrix.xlsx`](../data/recon_matrix.xlsx) (gen: `build_matrix.py`) |
| Event-driven engine internals | [`engine/`](engine/) (00–10) |
| Category pipelines & flow | [`pipeline/`](pipeline/), [`flow/`](flow/) |
| Gap analysis (categories) | [`pipeline/01-gap-analysis.md`](pipeline/01-gap-analysis.md) |
| Architecture review | [`blueprint/06-best-architecture-review.md`](blueprint/06-best-architecture-review.md) |
| Data schema | [`D3-data-schema.md`](D3-data-schema.md) |
| OPSEC / scope policy | [`D6-opsec.md`](D6-opsec.md) |
| Older roadmap (superseded by §9) | [`D7-roadmap.md`](D7-roadmap.md), [`pipeline/08-feature-advancements.md`](pipeline/08-feature-advancements.md) |

> Integration progress is tracked by the `recon-integration-tracker` skill, not by
> hand. Run its status script to see wired-vs-stub at any time.
