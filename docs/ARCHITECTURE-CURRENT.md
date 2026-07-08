# Recontool — Complete System View

Branch: `arch/event-driven-engine-v2`. This documents how the engine actually
behaves today (verified end-to-end on a live groww.in scan: 8,266/8,266 work
items completed, 0 failed, 59 findings, 245k endpoints, 0 OOM/locks/truncation).

---

## 1. The engine (what actually runs)

The live path is a **DB-backed recursive work-queue**, not the older in-process
orchestrator (dead code — no live callers). Entry: `cli.py engine` →
`engine/worker.py::run_queue_scan`.

```
seed ──enqueue──► work_item queue (Postgres) ──claim(CAS)──► N async workers
                       ▲                                          │
                       │ enqueue new in-scope keys                ▼
                       └──────── recursion ◄── normalize ◄── AI classify ◄── tool runs
```

- **Unit of work** = one `(primary_key, tool)` pair = one `work_item` row.
  Status: `pending → running → completed | failed`.
- **Claim** = atomic compare-and-set `UPDATE … WHERE status='pending'`
  (`worker.py::claim_one`) — safe across 128 async workers AND across
  processes/hosts (`recontool worker <scan_id>` attaches more).
- **Resumable** by construction: all state lives in the DB.
- **Two phases**: phase 1 recon (default); phase 2 validation (`--validate`,
  gated on `--authorize-active`).

## 2. Tools — the registry is the source of truth

`config/tools.yaml` (curated) + `tools_generic.yaml` + inventory → `ToolRegistry`
(586 tools). Each `ToolSpec` (`engine/registry.py`) carries input/output types,
`requires_key`, `is_active`, `integration`, `binary`/`endpoint`/`invocation`,
`parse`, plus the **execution-policy fields the engine HONORS**:

| Field | Meaning | Populated by `apply_policy_defaults` |
|---|---|---|
| `incremental_safe` | reuse prior run on rescan? | passive && !active → True (483/586) |
| `concurrency_safety` | safe to run parallel with itself? | False for masscan/naabu/zmap |
| `retry_policy` | retry transient failures | api=2 / passive-cli=1 / active=0 |

Three executors (`adapters/generic.py` + handwritten):
- **GenericApiAdapter** — HTTP GET per input, parse JSON/text.
- **GenericCliAdapter** — `subprocess_exec` in its own process group, parse stdout.
- **Handwritten Python adapters** — dns_resolve, httpx_probe, pycrawl, nmap, sslyze…

## 3. Invocation & availability gating (skip taxonomy)

`runner.py::run_tool_spec` is the single execution funnel. A tool **skips with a
precise reason** instead of running broken:

- `missing binary: <name>` · `missing API key: <ENV>` · `missing data file: <path>`
  (wordlists/resolvers — the ffuf/SecLists case) · `no API endpoint contract` ·
  `unavailable (prerequisite missing)` (handwritten python adapters).
- Pruned-at-routing (no binary/key) never even becomes a work item.
- Per-item timeout → `failed` with reason. Tool crash → `failed`; the pool
  continues (resilience).

## 4. Caps & bounds — TWO kinds, never confused

**Memory/concurrency bounds (rotate, never drop data):**

| Bound | Value | Effect |
|---|---|---|
| `_HEAVY_MAX` | 16 | max concurrent heavy/high-output tools (nmap, crawlers, wayback) |
| `_EVENT_BATCH` | 5000 | per-tool events processed/persisted/recursed in batches |
| `_fan_out` batch | `max_inputs` | ALL inputs processed in rotating batches |
| `item_timeout` | 2400s | no tool pins a worker forever |
| heavy_sem | min(workers//2, 16) | light tools keep the full pool |

**Data-dropping caps — REMOVED** (`max_records`, `max_inputs[:cap]`): everything
is processed. The only emit-side drop is the CIDR guard (a CDN's /48 = 2^80
addresses — physical impossibility; the raw block is still kept in artifacts).

## 5. Recursion & routing

- Router `SUBSUMES`: a `url` key subsumes `live_host/subdomain/domain`.
- **Only `entity=asset` events recurse** (`runner.py::discovered_assets`);
  `endpoint` / `service` / `finding` are terminal.
- **Recursion-explosion fix**: wayback_cdx returned 175k historical URLs as
  *recursable url assets* → 175k × ~69 tools ≈ 12M work items. It now emits
  **endpoints** (terminal — stored+deduped, not re-fed) like its siblings
  (gau/waybackurls/hakrawler/gospider); only httpx_probe's bounded LIVE roots
  recurse. Verified: 11.7M → ~8k.
- Dedupe-on-enqueue (`work_dedupe_key` + `_dedupe_key_type`) collapses
  domain/subdomain duplicates of the same host.

## 6. Database (`core/models.py`; Postgres prod / SQLite dev)

Tables: `scan, asset, asset_source, service, endpoint, finding, asset_edge,
audit_log, work_item, tool_run, scan_state, pending_key, tool_row`.

- **dedupe_key** (hash) is unique per scan on asset/endpoint/finding → idempotent
  upserts; re-discovery strengthens confidence instead of duplicating.
- **Postgres-cutover fixes**:
  - varchar(1024) overflow bounded (full value preserved in `attributes.value_full`);
  - `work_item.key`/`parent_key` widened to **TEXT** (long crawl-URL keys were
    silently dropped — real data loss) + idempotent ALTER migration in `create_all`;
  - **3 concurrent-writer races** fixed via dialect `INSERT … ON CONFLICT DO
    NOTHING` (endpoint, asset_source, asset insert-then-read-back).
- **Ingest resilience**: a failed 1000-event chunk retries per-event so one bad
  row never loses the other 999.

## 7. Artifact lifecycle (raw → normalized → deduped → bundle)

`artifacts/<scan_id>/` (host-bind-mounted):
- `raw/<tool>/…` — raw stdout/JSON, saved pre-parse (always).
- `out/<tool>.<type>.jsonl` — typed evidence, **appended per primary key** (so a
  tool's output across all keys concatenates into one file).
- DB — the deduped canonical store.
- `scan_bundle.json` + `out/scan_summary.md` — final manifest, AI summary, and a
  `tool_execution` breakdown (produced / ran-empty / failed+reasons).

## 8. Dedup layers

Entity (`dedupe_key`) · cross-tool (same key) · cross-rescan (incremental
fingerprint) · job (`work_dedupe_key` at enqueue) · retry (idempotent upsert).

## 9. Normalization (`normalize/engine.py`, sole writer — ADR-011)

Bulk set-based upserts; resolves the host asset for services/endpoints; a
**central host-scope gate** drops out-of-scope/malformed subdomains across ALL
adapters (covers crawler URL host-resolution too); recomputes confidence
(noisy-OR over distinct source tools).

## 10. AI decisioning (`engine/ai_decision.py` + `ai/router.py`)

- Runs **only after** events exist; **only classifies** (persist / discard noise /
  trigger downstream / manual-review). Never executes tools, never invents entities.
- **Deterministic scope floor overrides the model**: an in-scope asset is always
  kept even if the model says drop.
- `engine/summary.py` — final heuristic-or-model narrative + per-tool breakdown.

## 11. Scope (`core/scope.py`)

Domain-suffix + CIDR matcher; deny overrides allow; re-checked before active
calls. `is_subdomain_of` guards sibling-suffix and email false positives.

## 12. Validation phase (`--validate` — the post-recon / exploitation phase)

`is_validation_tool` = vuln/exploitation phase (p6/p7) OR active + findings-only
output (nuclei/nikto/subjack/sslyze/wafw00f). These are **held back from recon**,
then run in a **separate phase 2** against the recon-discovered in-scope LIVE
surface, reusing primary keys at `max_depth=0` (validate, don't expand). Findings
→ Finding table linked to tool + asset + evidence. Requires `--authorize-active`.
(Live: 13 tools × 86 live assets → 366 work items → 43 findings.)

## 13. Rescan / resume / incremental

- Resume: re-attach workers to a scan's queue.
- `--incremental`: reuse a fresh prior run by input fingerprint — **gated on
  `_reuse_eligible`** so active/vuln tools always re-run (no stale nuclei results).
- Rebuild: `recontool/` + `config/` are bind-mounted (code/config live, no
  rebuild); only Dockerfile/`install_tools.sh`/deps changes need an image rebuild.

## 14. Memory & scale (the no-stall story)

Postgres backend (kills the SQLite write-lock deadlock) + pool resilience (one
item's failure can't wedge the pool) + subprocess group-kill (no orphaned
Chromium) + event batching + heavy-cap → engine peaks ~3 GB / 7.75 GB, 0 OOM, on
a 128-worker firehose scan running alongside Postgres.

## 15. Run / rebuild

```
docker compose --profile app run --rm recontool \
  engine <seed> --authorize-active --noise-control [--validate] -v --workers 128
```
Postgres is a separate always-on service (`RECON_DB_URL=postgresql+psycopg://…`).

## 16. Known gaps / follow-ups

- **SecLists wordlists missing** (build-time clone failed) → ffuf/gobuster skip
  cleanly; needs an image rebuild (resilient clone) for content-discovery.
- Handwritten-python-adapter skip reasons are generic (shodan/censys) — would
  need per-adapter self-reporting.
- Rate-limit vs timeout not distinguished as separate skip reasons.
- Validation-phase findings share the scan dir (separated by detector/table, not
  a sub-namespace).
- Per-tool explicit policy overrides in `tools.yaml` (the engine honors them; few
  are set explicitly yet).
