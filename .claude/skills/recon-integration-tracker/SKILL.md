---
name: recon-integration-tracker
description: Track and drive tool integration AND architecture conformance for the Recontool recon engine so no tool gets half-wired or forgotten and no work drifts from the vision. Use when integrating tools, wiring adapters/contracts, designing or reviewing engine architecture, auditing which tools are runnable vs documented-only, deciding what to integrate next, regenerating the tool matrix or suggested-tool docs, or whenever the user asks "what's left", "what's missing", "am I done with tool X", "is this on track", or worries that some tools got integrated and others were skipped.
---

# Recon Integration Tracker

A discipline layer for building Recontool the right way. The recurring failure
mode across AI sessions is: integrate a handful of tools, lose the thread, miss
the rest, drift from the architecture, and never re-derive a complete picture.
This skill makes the work **stateless and reproducible** — status is computed
from the repo every time, so no session has to remember what a previous one did.

## Read the canonical spec FIRST

The single source of truth for the engine is
[`docs/00-FINAL-ARCHITECTURE.md`](../../../docs/00-FINAL-ARCHITECTURE.md). Read it
before any architecture or integration work. It fixes the decisions that keep
getting re-litigated; do not invent a different model. Non-negotiables from it:

- **Two-table state, not a wide matrix.** Runtime = `Tools` (static capability
  registry) + `WorkQueue` (dynamic `(key, tool)` jobs). The 532-column grid is a
  *report*, never the database.
- **Routing is a deterministic join**, not an AI call. `key_type → tools whose
  consumes includes it`. AI is reserved for exactly 4 functions: entity
  extraction from unstructured output, prioritization, recurse/converge decision,
  canonicalization — each with a deterministic fallback.
- **Typed output per mode.** Every run writes `raw/<slug>/` AND
  `out/<key>/<slug>.<produced_type>.jsonl`. Multi-mode tools (a brute-forcer used
  for subdomains AND paths) write one typed file per produced type.
- **Noise control is load-bearing.** Wildcard-DNS, CDN exclusion (`cdncheck`), and
  cross-scan dedupe sit between "new keys found" and "re-feed". Without them
  recursion amplifies false leads.
- **One engine.** Wire the event-driven engine; do not add a third orchestrator.

## Regenerate the planning artifacts when the tool set changes

```bash
python -m recontool.inventory.seed_matrix        # seed/refresh the tool_row DB registry (all 563 tools)
python -m recontool.inventory.build_matrix       # data/recon_matrix.xlsx (Tools/Routing/WorkQueue views)
python -m recontool.inventory.suggested_tools    # docs/tools/*.md + SUGGESTED-ADDITIONS.md for gap closers
```

The runtime matrix lives in two tables: `tool_row` (registry, `engine/models.py`,
seeded above) and `work_item` (WorkQueue). Routing + dedupe-on-enqueue are in
`engine/router.py` (`tools_for_key_type`, `enqueue`); `catalog.load_all_tools()`
is the single source both the seeder and the Excel read.

## The one rule

**Never claim a tool is integrated from memory. Always derive it from the repo.**
Run the status script. It reads the sources of truth (`docs/tools/`,
`config/tools.yaml`, `config/tools_generic.yaml`, `recontool/adapters/`,
`tests/`) and tells you exactly what is wired, what is a documented stub, and the
next incomplete step per tool.

## Start every integration session with the status report

```bash
python3 .claude/skills/recon-integration-tracker/scripts/integration_status.py
python3 .claude/skills/recon-integration-tracker/scripts/integration_status.py --missing
```

This prints: documented universe, WIRED count + %, contracted vs adapter,
tested, and the list of documented-but-unwired tools. Treat the `--missing`
list as the backlog. Treat any "⚠ wired but undocumented" orphan as a bug —
either add the doc or remove the dead contract.

For a single tool's definition-of-done checklist:

```bash
python3 .claude/skills/recon-integration-tracker/scripts/integration_status.py --tool <slug>
```

(The `tested` column is a best-effort substring match — trust `contracted`/
`adapter` as hard signals, and confirm a real test exists when it matters.)

## Definition of done for a tool (do not mark integrated until all hold)

1. **Capability doc** exists in `docs/tools/<slug>.md`.
2. **Runnable contract** — either:
   - declarative in `config/tools_generic.yaml`: `integration` (api|cli),
     `consumes[]`, `produces[]`, `endpoint`/`headers` or `binary`/`invocation`,
     `bucket`, and a `parse.emit` that maps output to canonical entity types
     **with `scope_filter` on host-producing tools**; OR
   - a hand-written adapter in `recontool/adapters/*.py` with `name`,
     `available(ctx)`, and `run(ctx)` — reserve this for high-value/complex tools.
3. **Entity contract is correct** — `consumes`/`produces` use the canonical
   types from `config/categories.yaml` `meta.dedupe_forms` (domain, subdomain,
   ip, cidr, asn, url, service, js_file, endpoint, param, finding, …) so the
   scheduler can chain it and the normalizer can dedupe it.
4. **Parser test** against a captured fixture under `tests/` (no network, no
   subprocess) — the emit mapping is validated.
5. **Reachable** — the scheduler can select it: at least one of its `consumes`
   types is produced by an upstream tool or is the seed type. A tool that
   consumes a type nothing produces is dead weight; wire the producer or drop it.
6. **Active/passive flag** set correctly. Active tools must be gated behind the
   policy/authorization path, never default-on.
7. **Typed output** — emits to `out/<key>/<slug>.<produced_type>.jsonl`, one file
   per produced type. If the tool is multi-mode, every mode's type has its own
   file and its own `produces` entry. Raw still goes to `raw/<slug>/`.
8. **Default vs available** — set `default_on` correctly. All tools get wired
   (overlap is free via idempotent keys, canonical spec §1); only the
   recommended-profile tools (§7a) are `default_on: true`. Redundant tools are
   tagged as available alternatives, never dropped — the user picks them in the UI.

## Integrate in vertical slices, not breadth-first

Wiring 478 stubs one field at a time is how tools get half-done. Instead pick a
**category pipeline** (see `docs/pipeline/03-category-pipelines.md`) and take it
end-to-end: producer tool → its output type → the consumer tools that chain off
it → convergence. A complete Cat-2 (subdomain) chain that actually recurses is
worth more than 50 disconnected stubs. After each slice, re-run the status
script and record the delta.

## Before you say "done" with a batch

- Re-run the status script; the WIRED count must have gone **up** by exactly the
  tools you intended, with **no new orphans**.
- Run the test suite (`pytest -q`) — parser/emit tests must pass.
- Spot-check one newly wired tool with `--tool <slug>`: every box ticked.
- If you added a tool that produces a **new entity type**, confirm at least one
  downstream tool consumes it — otherwise the recursion dead-ends there.

## Guardrails specific to a recursive engine

A self-expanding engine amplifies noise as fast as signal. When wiring discovery
tools, make sure these exist (or flag them as gaps) so feedback loops stay clean:
wildcard-DNS detection, CDN exclusion (`cdncheck`), and cross-scan dedupe. A
false subdomain fed back as a "new lead" multiplies into wasted branches.
