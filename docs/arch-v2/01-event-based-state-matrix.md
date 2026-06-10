# Event-Based Architecture v2 — the Entity × Tool State Matrix

> Branch: `arch/event-based-arch-v2`. This document turns the "Excel that represents a
> database" idea into a concrete, build-ready design and shows how it maps onto the
> components that **already exist** in the repo (frontier, policy engine, dedupe, generic
> adapters, AI supervisor). The spreadsheet projection lives in
> [`data/recontool_state_matrix.xlsx`](../../data/recontool_state_matrix.xlsx).

---

## 1. The core idea (your model, made precise)

A single table is the brain of the system. Call it the **work-item table** (the "Excel"):

```
PRIMARY KEY (a discovered entity)        ×        TOOL        =        STATE
   domain:grow.in                                 subfinder            completed
   domain:api.grow.in                             dnsx                 pending
   ip:203.0.113.10                                naabu                in_progress
   livehost:https://app.grow.in:443               ffuf(dir)            pending
   ep:app.grow.in:GET:/admin                      arjun                pending
```

- **Rows are primary keys.** A key is a discovered entity with a deterministic dedupe id:
  `domain:`, `subdomain:` (stored as `domain:`), `livehost:`, `ip:`, `cidr:`, `asn:`,
  `cert:`, `url:`, `ep:` (endpoint = subdomain+path), `bucket:`, `repo:`, `email:`.
  These dedupe forms already exist in `config/categories.yaml → meta.dedupe_forms`.
- **Columns are tools** (532 extracted + 11 added = **543**).
- **Cells are states:** `n/a` (tool doesn't consume this key's type) → `pending` →
  `in_progress` → `completed` (or `skipped`, `failed`, `dead_letter`).

The "which cells start as `pending`" decision is **pure routing**: a key's *type* selects
the tools that consume that type. That mapping is the `03_Routing_Matrix` sheet and is
backed by `categories.meta.seed_routing` + each tool's `consumes`.

> **Wide vs long.** The wide matrix (key rows × 543 tool columns) is the *human view*
> (sheet `07_Entity_Tool_Matrix`). The database stores it **long** — one row per
> `(key, tool)` work-item (sheet `06_Entity_State_DB`) — which is exactly a typed,
> prioritized queue. The wide grid is a pivot/export of the long table.

---

## 2. The loop (one full cycle)

```
        ┌──────────────────────────────────────────────────────────────┐
        │                      DISCOVERY DB (work-item table)            │
        │   keys × tools × state   +   typed corpus (by-type/*.txt)      │
        └───────┬───────────────────────────────────────────▲──────────┘
                │ (1) pop highest-priority PENDING (key,tool)│ (5) upsert new keys,
                ▼                                            │     set their pending cells
        ┌───────────────┐   (2) run tool on key      ┌───────┴────────┐
        │  WORKER POOL  │ ─────────────────────────► │  TYPED OUTPUT   │
        │ mark in_prog. │                            │  subdomains.txt │
        │ → completed   │ ◄───── (3) write files ─── │  ips.txt paths… │
        └───────────────┘                            └───────┬────────┘
                                                             │ (4) AI / normalizer
                                                             ▼  extracts keys, dedupes
                                                   ┌────────────────────┐
                                                   │  KEY EXTRACTION     │
                                                   │  (primary keys)     │
                                                   └────────────────────┘
```

1. **Schedule.** A worker pops the highest-priority `pending (key, tool)` item. Priority
   comes from the entity type (cheap/high-signal first) — already encoded in
   `FrontierManager.DEFAULT_PRIORITY` and category `priority`.
2. **Execute.** Runs the tool against the key (the generic adapter engine already knows the
   invocation from `config/tools.yaml`). State → `in_progress`.
3. **Write typed output.** The tool writes `by-type/<type>.txt` files (the output-file
   contract, doc 03). State → `completed`. The raw output is also kept for provenance.
4. **Extract keys.** The normalizer (deterministic) + AI supervisor (for messy/freeform
   sources) read the *typed* files, pull out new entities, and dedupe them against the DB.
5. **Re-seed.** Each genuinely-new key is upserted as a row; the routing matrix sets its
   applicable tool cells to `pending`. The loop repeats until no new keys appear
   (**convergence**) or a depth/budget bound is hit.

This is a **fixpoint over a typed asset graph** — the exact model already documented in
`docs/pipeline/06-recursive-flow.md` and implemented (as a queue) in
`orchestrator/frontier.py`. The state matrix makes that loop **observable and resumable
per (key, tool)** instead of per phase.

---

## 3. Where AI sits (decisioning, not plumbing)

The AI is used at three decision points and **never** invents assets:

| Decision | Input | Output | Why AI (not just rules) |
|----------|-------|--------|--------------------------|
| **Key extraction from messy output** | typed files + raw for freeform sources (dorks, JS, docs, social) | candidate keys + type + confidence | regex misses context; LLM extracts hostnames/paths from prose/JS reliably |
| **Re-scan worthiness** | a new key + its provenance + what already covers it | which tool cells to set `pending` vs `skip` | avoids re-running the whole 300-tool fan-out on every near-duplicate; e.g. "this subdomain resolves to an already-scanned IP → skip IP/port tools, still run web tools" |
| **Prioritization / triage** | queue snapshot + findings so far | re-order pending items, flag high-value (login/admin/exposed API) | spends budget where signal is |

Deterministic heuristics run with **zero tokens** by default (the existing `ai/router.py`
light/heavy routing + hard call budget). AI only escalates when heuristics are uncertain.

**Worked example (your `grow.in`):** subfinder/crt.sh/census write `subdomains.txt`. The
AI/normalizer extracts `api.grow.in` as a `subdomain` key. Routing marks DNS/resolution
(`dnsx`, `puredns`), web (`httpx`, then `ffuf`, `katana`, `gau`), TLS (`tlsx`), archive
(`wayback`), and Shodan/Censys cells as `pending`. The "re-scan worthiness" step notices
`api.grow.in` resolves to a *new* IP → it also marks IP/port/network tools (`naabu`,
`asnmap`, `internetdb`) `pending` for the new `ip:` key. If two subdomains share one IP,
the IP work-items run **once** (the IP is its own key).

---

## 4. Mapping to existing code (what to reuse, what to add)

| v2 concept | Already in repo | Gap to build |
|------------|-----------------|--------------|
| Primary keys + dedupe ids | `categories.meta.dedupe_forms`, `core/dedupe.py`, `Asset.dedupe_key` | — |
| Priority scheduling / convergence | `orchestrator/frontier.py` (priority queue, seen-set, depth/budget) | drive it from the **work-item table**, not a phase loop |
| Routing (type → tools) | `categories.route_seed`, each tool's `consumes` | materialize as the persisted `03_Routing_Matrix` |
| Tool execution (500+ tools) | `adapters/generic.py` + `config/tools.yaml` | add typed-output writing (doc 03) |
| Dedup + confidence + sources | `core/dedupe.py`, `core/confidence.py`, `AssetSource` (per-tool sighting) | — (this *is* the per-tool history) |
| Resume / failure capture | `Checkpoint`, `DeadLetter` (`orchestrator/frontier.py`) | persist per (key,tool) state |
| AI decisioning | `ai/router.py`, `ai/supervisor.py` | wire the 3 decision points in §3 |
| Scope / active gate | `core/policy.py`, `core/scope.py` | per-item re-check before egress (already designed) |

The new piece is one table + the worker loop that consumes it:

```sql
CREATE TABLE work_item (
  scan_id      TEXT,
  key          TEXT,          -- dedupe id, e.g. 'ip:203.0.113.10'  (FK → asset.dedupe_key)
  entity_type  TEXT,          -- domain|subdomain|live_host|ip|...
  tool         TEXT,          -- slug
  capability   TEXT,          -- mode for multi-mode tools (ffuf:dir)
  status       TEXT,          -- pending|in_progress|completed|skipped|failed|dead_letter
  priority     INTEGER,
  depth        INTEGER,
  output_file  TEXT,
  scheduled_at TIMESTAMP, started_at TIMESTAMP, completed_at TIMESTAMP,
  attempts     INTEGER DEFAULT 0,
  PRIMARY KEY (scan_id, key, tool, capability)
);
```

Everything else (entities, edges, findings) already has a table in `core/models.py`.

---

## 5. Answering "pre-build the Excel, or generate it at runtime?"

**Both — split by what changes.**

- **Pre-built / static (ships in the repo, regenerated by the builder):** the tool
  registry, the **routing matrix** (type → tools), the **output-file map**, the category
  contracts, and the **root-domain seed list**. This is knowledge about *tools*, not about
  any target. Sheets `01–05`, `08`. You need exactly this to bootstrap a fresh root domain.
- **Dynamic / per-scan (generated at runtime, persisted in the DB):** the actual
  **work-item rows** — they only exist once keys are discovered. The wide `key × tool`
  grid is an **export view** of that table at any moment (sheets `06`, `07` are a seeded
  demo of it).

So: ship the static matrix, generate the live one. The workbook here contains both — the
static sheets are authoritative; the two dynamic sheets are a worked `grow.in` example so
the shape is unambiguous.

---

## 6. Is this architecture good? (honest assessment)

**Yes — and it's largely already here.** The fixpoint/frontier model is the right shape
for recursive recon, the repo already implements convergence, dedupe, confidence, a
declarative 500-tool engine, policy gating, checkpoint/replay, and a token-frugal AI
supervisor. The v2 contribution is mostly **making state explicit and per-item**:

**Strengths of the model**
- Idempotent + resumable: every unit of work is a row with a state; a crash resumes exactly.
- Naturally parallel: workers pop disjoint items; the IP-shared-by-many-subdomains case is
  deduped for free because the IP is its own key.
- Observable: the matrix *is* the dashboard (what's pending/running/done per key per tool).
- Convergence is provable (monotonic seen-set over a finite in-scope key space).

**Risks to manage (call these out now)**
- **Fan-out explosion.** 543 tools × thousands of keys = millions of cells. Mitigate by
  storing the table **long** (only materialize `pending`+ rows, never the `n/a` majority),
  capping `max_new_per_iter`, and per-category quota/budget (already in `categories.yaml`).
- **Wildcard / CDN noise** can flood the frontier — keep the `dnsx`/`puredns` wildcard
  filter and CDN tag *before* enqueuing web tools.
- **Re-scan worthiness must be conservative** or you loop forever on near-duplicates; the
  AI decision in §3 plus the seen-set guards this.
- **Budget/credits** for paid sources — the budget ledger must gate `pending → in_progress`
  for metered tools, not just runtime.

Net: good architecture; the work is integration (drive the existing frontier from the
work-item table + typed outputs + the 3 AI decisions), not a rewrite. IP rotation is
deliberately deferred (handled later by `net/proxy_pool.py`).
