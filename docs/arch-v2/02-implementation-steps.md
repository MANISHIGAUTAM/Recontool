# Implementation Steps — wiring the state matrix into the live pipeline

Ordered, incremental, each step shippable + testable. Builds on the components that
already exist (frontier, policy, dedupe, generic adapters, AI router). No rewrite.

> Legend: **[new]** new file/table · **[edit]** change existing · **[test]** add atomic test.

---

## Phase 0 — Static knowledge (DONE in this branch)

- [x] `data/added_tools.json` — 11 gap-closing tools (param fuzzing, GraphQL schema
      recovery, non-HTTP fingerprinting, favicon pivots, DNS permutation, passive ports).
- [x] `docs/tools/*.md` for the 11 added tools.
- [x] `recontool/inventory/build_state_matrix.py` → `data/recontool_state_matrix.xlsx`
      (categories, tools master, routing matrix, root-domain seed, output-file map,
      long+wide state demo, eliminate list).
- [x] `docs/arch-v2/03-output-file-contract.md` (typed output files + multi-capability split).

## Phase 1 — Typed output files  *(highest value, lowest risk)*
1. **[edit]** `core/artifacts.py`: add `append_typed(scan_id, tool, type, values)` and
   `append_unique(path, values)` (set-dedupe, append-only).
2. **[edit]** `adapters/generic.py`: after `emit_events(...)`, route each `Event` to its
   typed file by `event.type`; for multi-mode CLI tools pass the mode → file from the
   `MULTI_CAPABILITY` map (shared with the workbook builder — factor it into
   `recontool/inventory/io_map.py` **[new]** so code + spreadsheet use one source of truth).
3. **[test]** feed fixture events → assert `by-type/subdomains.txt`, `paths.txt`, etc. and
   the per-tool partition both contain the right (deduped) values.

*Outcome:* every tool now leaves a per-type, per-tool, append-only trail = "new live things
detected while keeping all previously detected, per tool."

## Phase 2 — The work-item table
4. **[new]** `core/models.py`: `WorkItem` model (schema in doc 01 §4) + Alembic/`create_all`.
5. **[new]** `orchestrator/router.py`: `pending_tools_for(key, entity_type)` → reads the
   routing map (the same `consumes` data) and returns `(tool, capability, priority)` list.
6. **[edit]** `core/dedupe.py`/normalizer: on upsert of a new asset, call the router and
   insert `pending` `WorkItem` rows (skip types a tool doesn't consume → never stored).
7. **[test]** upserting `subdomain:api.grow.in` creates pending items for dnsx/httpx/…,
   and re-upserting the same key creates **no** duplicates.

## Phase 3 — Drive the frontier from the table
8. **[edit]** `orchestrator/pipeline.py`: replace the phase loop with a loop that pops
   `pending` `WorkItem`s via `FrontierManager` priority, marks `in_progress`, runs the
   adapter, writes typed output, marks `completed`; route exhausted/blocked to `DeadLetter`.
9. **[edit]** persist `WorkItem` state inside the existing `Checkpoint` snapshot so a
   killed scan resumes per-item.
10. **[test]** end-to-end on a fixture: seed `grow.in` → items transition
    pending→in_progress→completed; convergence empties the queue; resume from a mid-run
    checkpoint reproduces the same final state.

## Phase 4 — AI decision points  *(token-frugal)*
11. **[edit]** `ai/supervisor.py`:
    - `extract_keys(typed_files, raw)` — keys from freeform sources (dorks/JS/docs/social);
      deterministic regex first, LLM only on low-confidence.
    - `rescan_worthiness(new_key, provenance, coverage)` → which pending cells to keep vs
      `skip` (e.g. subdomain on an already-scanned IP → skip IP/port tools, keep web tools).
    - `prioritize(queue_snapshot, findings)` → re-rank + flag high-value hosts.
12. **[edit]** `ai/router.py`: enforce the per-scan call budget across these (already exists).
13. **[test]** golden tests with the LLM stubbed: messy input → expected keys; duplicate-IP
    subdomain → IP tools skipped.

## Phase 5 — Observability & export
14. **[edit]** `cli.py`: `recontool matrix <scan_id> -o out.xlsx` → export the live
    work-item table as the wide grid (reuse `build_state_matrix` sheet writers).
15. **[edit]** streaming console view: per-key pending/running/done counts (the matrix
    *is* the dashboard).

## Phase 6 — Guardrails (do not skip)
16. Wildcard/CDN filter **before** enqueuing web work-items (reuse `dnsx`/`puredns` + `cdncheck`).
17. `max_new_per_iter`, per-category quota/budget gate on `pending → in_progress` for
    metered/paid tools (budget ledger).
18. Conservative `rescan_worthiness` + the monotonic `seen` set to prevent loops.

## Later (explicitly deferred)
- IP / egress rotation (`net/proxy_pool.py`) — wire after the matrix loop is stable.
- Neo4j graph projection + web UI for the matrix.

---

## Tool-coverage decisions captured here

- **Added (11):** see `data/added_tools.json` — closes param-fuzzing (`x8`), GraphQL
  schema recovery (`clairvoyance`), non-HTTP fingerprinting (`fingerprintx`), favicon
  pivots (`favfreak`, `fav-up`), permutation (`dnsgen`, `gotator`), passive ports (`smap`),
  alt content discovery (`dirsearch`), fuzz-prep glue (`qsreplace`), extra crawler (`gospider`).
- **Eliminate / deprecate (11):** sheet `08_Eliminate_Redundant` — `altdns`, `sublist3r`,
  `dirb`/`dirbuster`, `waybackurls`, `aquatone`, `linkfinder`, etc. are fully covered by a
  better, maintained tool. Keep `massdns` only as the engine behind `puredns`.
- **Already covered — do not add more:** the search-engine family (Cat 1) is exhaustive and
  `uncover` wraps Shodan/Censys/FOFA/ZoomEye/Netlas; the gap tools from the original
  analysis (`alterx`, `gf`, `anew`, `unfurl`, `mapcidr`, `cdncheck`, `metabigor`, `jsluice`,
  `cero`, `kiterunner`, `graphw00f`, `tlsx`, `ffuf`, `feroxbuster`) are already wired in
  `config/tools.yaml` (categories 20–28).
