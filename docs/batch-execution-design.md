# Batch Execution Design — feed list-capable tools all inputs at once

**Status:** PROPOSED (design only — no engine changes until sign-off)
**Author:** flow audit, 2026-06-22
**Branch:** arch/event-driven-engine-v2

## 1. Problem

The event-driven engine dispatches work **per key**. Each discovered key becomes one
`work_item`, and the worker builds the adapter context with a *single* key:

```python
# recontool/engine/worker.py:424
inputs = {item.key_type: [item.key]}
```

So a tool that is designed to take a *list* of targets in one invocation is instead run
once per key. Evidence from the live scan of `yamunaexpresswayauthority.com`
(`artifacts/<scan>/out/<tool>.runs.jsonl`):

| Tool | Invocations | Should be |
|---|---|---|
| nmap | 26 | 1 (`nmap -iL hosts.txt`) |
| httpx | 26 | 1 (`httpx -l hosts.txt`) |
| dnsx | 26 | 1 (`dnsx -l hosts.txt`) |
| naabu | 26 | 1 (`naabu -list hosts.txt`) |
| tlsx | 26 | 1 (`tlsx -l hosts.txt`) |
| nuclei | 21 | 1 (`nuclei -l hosts.txt`) |
| katana | 21 | a few |

Cost: 26× process spawn + teardown, and — worse — tools that **optimize across a target
set** are crippled. nuclei reloads ~9k templates *per* invocation (21× redundant template
loads); nmap's timing/host-parallelism is per-target instead of global; httpx/dnsx lose
connection reuse and stdin streaming.

This is the "too recursive" cost: per-key fan-out where the tool wanted the whole set.

## 2. Goal & non-goals

**Goal:** tools that accept a list of primary inputs are invoked **once** (or a few times,
in waves) with **all** eligible, in-scope keys fed via their native list mechanism
(`-iL`/`-l`/`-list`/`-dL`/stdin), instead of once per key.

**Non-goals:**
- Per-target tools that fundamentally process ONE target per run stay per-key:
  ffuf, gobuster, feroxbuster (fuzz one base URL), arjun, paramspider, sslyze (per-host),
  most keyed APIs (one query per key). These are correctly per-key — do NOT batch them.
- No change to scope filtering, dedup, recursion semantics, or the AI/normalize layers.
- Not a streaming-vs-batch rewrite; batching is an *opt-in per-tool* optimization.

## 3. Per-tool batch matrix (grounded against installed tools)

List-input flags verified via `--help` in `recontool:latest`. "Adapter today" notes whether
the existing adapter already writes a list-file (just needs more keys) or loops per target
(needs an `-iL`/`-l` switch).

| Tool | List flag (verified) | Input type | Adapter today | Work |
|---|---|---|---|---|
| **nuclei** | `-l <file>` | live_host,url | **already batches** (`-l list`) | coalescing claim only |
| **gowitness** | `scan file -f <file>` | live_host | **already batches** (`-f list`) | coalescing claim only |
| **nmap** | `-iL <file>` | ip,subdomain | **loops per host** | `-iL` switch + claim |
| **httpx** | `-l <file>` | subdomain,domain | audit (PD) | likely `-l` switch + claim |
| **dnsx** | `-l <file>` (file/stdin) | subdomain,domain | audit | `-l`/stdin switch + claim |
| **naabu** | `-list <file>` | ip,subdomain | audit | `-list` switch + claim |
| **tlsx** | `-l <file>` | subdomain | audit | `-l` switch + claim |
| **katana** | `-list <file>` | live_host,url | audit (crawler) | `-list` switch + claim |
| **subfinder** | `-dL <file>` | domain | audit | low benefit (usually 1 root) |
| masscan | `-iL <file>` | ip | generic/hand | `-iL` + claim |
| puredns/shuffledns/massdns | list file | subdomain | hand | already list-oriented |
| mapcidr | `-cl`/stdin | cidr | hand | `-cl`/stdin + claim |
| gau/waybackurls | stdin list | domain | generic (per-key) | stdin batch-mode |
| subjack | `-w <file>` | subdomain | generic | `-w` + claim |
| cero | list/stdin | subdomain | generic | stdin + claim |

**Priority tranche (biggest win, smallest blast radius):** nuclei, gowitness (free — claim
only), then nmap, httpx, dnsx, naabu, tlsx, katana.

## 4. Design

### 4.1 Contract flag

Add an optional declaration to a tool's contract (tools.yaml / tools_generic.d / adapter
class attr):

```yaml
batch:
  enabled: true
  mode: list_file        # list_file | stdin
  arg: "-iL {file}"      # how the list path is passed (list_file mode); ignored for stdin
  max_batch: 500         # cap per invocation (split into multiple runs above this)
```

Defaults: absent ⇒ `enabled:false` (current per-key behavior — **100% backward compatible**).
Hand adapters that already batch (nuclei, gowitness) set `batch.enabled=true` as a class attr;
their `run()` is unchanged (it already writes a list-file).

### 4.2 Coalescing claim (the core change)

Today: `claim_one` does a single-row compare-and-set (`pending -> running`,
`ORDER BY depth, id LIMIT 1`). Add a sibling for batch tools:

```
claim_batch(session, scan_id, tool_slug, key_type, depth, cap):
  # select up to `cap` pending rows for THIS (tool_slug, key_type) at the lowest depth
  ids = SELECT id WHERE scan_id, status='pending', tool_slug=?, key_type=?, depth=?
        ORDER BY id LIMIT cap
  # atomic multi-row CAS — only rows still 'pending' flip; rows another worker grabbed are skipped
  UPDATE work_item SET status='running' WHERE id IN ids AND status='pending'
  return [keys of rows this worker actually flipped]
```

Same compare-and-set safety as `claim_one`, just N rows. A worker that wins K of the cap rows
runs the tool once on those K keys; rows lost to a racing worker are simply that worker's batch.

### 4.3 Context + dispatch

```python
# worker dispatch, for a batch-enabled tool:
keys = claim_batch(... tool, key_type, depth, cap=batch.max_batch)
inputs = {key_type: keys}          # <-- the whole set, not [item.key]
# adapter runs once; scope_filter + dedup apply per-key exactly as today
# on completion: mark ALL claimed rows done (single status update by id-set)
```

For `list_file` mode the worker (or adapter) writes `keys` to a temp file and substitutes
`{file}`; for `stdin` mode it pipes `"\n".join(keys)`. The generic CLI adapter gains a
`batch` branch mirroring the nuclei/gowitness pattern (write list, run once) instead of
`_fan_out` per value.

### 4.4 Streaming / late arrivals

Keys discovered *after* a batch runs simply create new `pending` work_items and are picked up
by the next `claim_batch` wave. Net effect: a batch tool runs **once per discovery wave**
(roughly once per depth level), not once per key — 26 → ~1–3. No barrier or
depth-completion detection required (that's the heavier alternative we rejected).

## 5. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Double execution / lost rows | Same CAS as `claim_one`, applied to an id-set; only rows a worker flips are its batch. Unit-test the multi-row race. |
| One bad key fails the whole batch | Batch tools already tolerate per-target failures (nuclei/nmap skip dead hosts). Keep per-key result attribution from the tool's own output (host field), not "all keys = the batch's events". |
| Memory (huge key set) | `max_batch` cap → split into multiple invocations; events still processed in the existing bounded `_EVENT_BATCH` chunks. |
| Per-key provenance in runs.jsonl | Write one batched run row with `keys:[...]` + keep the per-key footprint the normalizer already emits. Preserve the visible-artifact ledger. |
| Scope/dedup regressions | `inputs` still flows through the same scope_filter + dedup; only the *count* per invocation changes. Assert identical entity output batched vs per-key in tests. |
| Backward compat | Flag-gated, default off. Tools without `batch` are byte-for-byte unchanged. |

## 6. Test plan

- **Unit:** `claim_batch` multi-row CAS under 2 concurrent workers (no key claimed twice, union = all pending).
- **Unit:** generic adapter `batch` branch writes the list file / pipes stdin and runs once.
- **Equivalence:** for nuclei/nmap on a fixed input set, assert the *entities produced* are
  identical batched-vs-per-key (only invocation count differs).
- **Adapter:** nmap `-iL` path produces the same services as the per-host loop on a 3-host fixture.
- **E2E (docker):** rescan; assert `nmap`/`nuclei`/`httpx` runs.jsonl invocation count drops
  from ~26/21 to single-digit, with entity counts >= the per-key baseline (no data lost).
- **flow_lint** unchanged (routing types are unaffected).

## 7. Rollout

1. Land `claim_batch` + the worker dispatch branch + generic adapter batch-mode (flag-gated, no tool opts in yet) — pure plumbing, no behavior change.
2. Opt in the **free** tranche (nuclei, gowitness — adapters already batch) → verify invocation collapse.
3. Switch nmap to `-iL`, opt in httpx/dnsx/naabu/tlsx/katana one at a time, each with the equivalence test.
4. Leave per-target tools (ffuf/gobuster/arjun/sslyze/APIs) per-key — explicitly documented.

## 8. Open questions for sign-off

- Cap value (`max_batch`) default — 500? per-tool override?
- `claim_batch` grouping: lowest-depth-only (proposed) vs across-depth coalescing?
- Should batch tools also debounce (small wait to accumulate a wider wave) or run as soon as any pending exists (proposed)?
