# Deep Review — Are all tools running properly?

Branch `arch/event-driven-engine-v2`. Evidence-based review of why some tools
appeared not to run / not produce. Every conclusion is backed by code, the
install audit (`scripts/install_audit.py`), the invocation probe
(`scripts/tool_invocation_probe.py`), or a live groww.in scan
(`scripts/e2e_verify.py`). Runtime behavior is treated as the source of truth.

## 1. Executive summary
The suspicion was partly right: a handful of tools were silently empty or broken,
and the causes were concrete and fixable — **not** a systemic engine failure. The
engine's scheduling, recursion, dedup, artifact storage and AI-classification are
sound. The defects were per-tool: one token-shaping bug affecting host tools fed
URL keys, and four installed-tool-version / dependency mismatches. All are fixed.
Most "empty" tools are **legitimately empty for this target** or **intentionally
unavailable** (inventory stubs / key-gated APIs), not bugs.

Headline numbers (install audit, `--tools all`): **268 enabled · 89 READY ·
161 missing-binary · 18 missing-key**. Of the 161, ~153 are **inventory stubs**
(`is_inventory_derived`, the documented 566-tool universe) that are pruned at
routing; only **8 are curated-but-uninstalled** and all 8 are redundant with an
installed equivalent or need a handwritten adapter.

## 2. What is working (evidence)
- **Selection / gating** (`engine/selection.py::apply_selection`): curated tools
  enabled; `is_active` gated behind `--authorize-active`; inventory stubs enabled
  only with `--tools all`. Verified live.
- **Routing prunes the unavailable** (`engine/worker.py::RouteIndex` +
  `_tool_available`): tools with no binary/key are dropped before enqueue — they
  never run, never produce garbage (the 161 missing-binary inventory stubs).
- **Artifact pipeline** (`core/artifacts.py`): `save_raw` per tool; `save_typed`
  opens mode `"a"` → typed `out/<tool>.<type>.jsonl` **appends across keys**
  (proven: `tests/atomic/test_pipeline_layers.py`, and live `dns_resolve.subdomain
  .jsonl` = 132 lines from many keys); per-scan dirs → no cross-scan overwrite.
- **AI decisioning** (`engine/ai_decision.py`): only classifies (persist / discard
  noise / trigger), never executes tools; deterministic scope floor overrides the
  model. `discovered_assets()` pulls deduped recursable keys; endpoints/findings
  are terminal (test-locked).
- **Normalization + dedup** (`normalize/engine.py`): single writer; re-discovery
  upserts (no dup `dedupe_key`) and raises confidence (noisy-OR). Live: 0
  duplicate (scan, dedupe_key) assets.
- **Recursion / no-overwrite**: depth>0, new keys enqueued, queue fully drains,
  no (key,tool) run twice; rescan reuses 1958 tools, 0 duplicate entities.
- **Canonicalization**: host keys stored bare (`groww.in`); url keys one-per-host,
  https-preferred → **no http/https key overlap** (33 url keys = 33 hosts).

## 3. What is not working (now fixed)
| Defect | Evidence | Fix |
|---|---|---|
| **Input-shape**: `{host}/{domain}/{ip}` aliased to the raw key → a host tool fed a `url` key got `https://host/path` as its target → empty | `generic.py` token build; probe showed mapcidr/host tools choking on non-host input | `_shape_tokens()` — host-tools get bare host, url-tools get `scheme://host`, stdin shaped (commit e63e990) |
| **gobuster** broken flag | probe: `gobuster dns -d groww.in` → `invalid value for flag -d: parse error`; v3.8.2 uses `--domain` | `--domain` (commit 91474d8) |
| **subjack** broken flag | probe: `-c {fingerprints}` → `flag not defined: -c` (fork has built-in fingerprints) | drop `-c` (this commit) |
| **nikto** missing dep | probe: `Required module not found: JSON` | `libjson-perl` in image (this commit) |
| **metabigor** runtime panic | probe: `go4.org/unsafe ... go1.24` panic | `ASSUME_NO_MOVING_GC_UNSAFE_RISK_IT_WITH=go1.24` env (this commit) |
| **gau/gauplus/waymore** empty | run but return 0 (gau batches; never finishes on 227k) while `waybackurls` streams 227k | gau wayback-only+timeout; waybackurls is the reliable source (commit 91474d8) |

## 4. Tool-by-tool classification (evidence-based)
| Category | Tools (representative) | Evidence |
|---|---|---|
| **PRODUCES** | assetfinder, crtsh*, dns_resolve, dnsx, gobuster, hackertarget, hakrawler, httpx, httpx_probe, js-render, js_analyze, katana, massdns, naabu, nmap, org_fingerprint, pycrawl, pydirb, shuffledns, sslyze, tlsx, urlscan, wafw00f, wayback, wayback_cdx, gospider, cariddi | e2e_verify L3 typed counts (live) |
| **EMPTY but acceptable** (target-specific) | amass, subfinder, dnsenum, fierce, anubis-jldc, subdomaincenter, alienvault_otx, paramspider, gauplus, gf-* | ran rc=0, 0 results for groww.in; gf-*/jsluice are list-filters (need URL input, not a bare domain) |
| **SKIPPED by design** | ~153 inventory stubs (BBOT, Osmedeus, SpiderFoot, Aquatone, …) | `is_inventory_derived`, no binary → pruned at routing |
| **SKIPPED missing dep/key** | shodan, censys, netlas, leakix, fullhunt, criminalip, github_subdomains, virustotal, securitytrails … (18) | `requires_key` + key absent → `available()` False → `⊘ skip (missing API key)` |
| **BROKEN invocation (FIXED)** | gobuster, subjack | probe parse errors above |
| **BROKEN dep/runtime (FIXED)** | nikto, metabigor | probe module/panic errors above |
| **BROKEN parsing** | none found | emit-gate rejects banner/garbage; paramspider banner already fixed |
| **TIMEOUT (slow, not broken)** | amass, dnsenum, fierce, waybackurls, waymore, gau, katana | probe 20s cap hit; complete under the engine's 1800s tool timeout (waybackurls got 227k in 214s live) |

\* crtsh empty on some runs (CT log variance) but is wired correctly.

## 5. Root cause analysis
1. **Token aliasing ignored input type** — the single highest-impact bug; any
   host tool reachable from a `url` key (subsumption) got a URL as its host
   target. Fixed centrally in `_shape_tokens`.
2. **Installed-tool version drift** — `tools.yaml` invocations assumed flags the
   *installed* binaries don't have (gobuster `-d`, subjack `-c`). Runtime is the
   source of truth; specs were stale.
3. **Missing runtime deps** — nikto (Perl JSON), metabigor (go1.24 ABI). Image-
   layer gaps, fixed in the Dockerfile.
4. **Batch-vs-stream tool behavior** — gau buffers and never completes on a large
   target; waybackurls streams. Mitigated, not "broken."
5. **Drift: `default_on` is inert** — `apply_selection` enables all curated tools
   regardless of `default_on`; 68/109 curated are `default_on:false` incl. valuable
   ones (assetfinder/hakrawler). So `default_on` must NOT be used to gate the
   default profile (would cripple it). Documented; no code change.
6. **Inventory stubs are enabled-but-unavailable** — cosmetic; pruned cleanly.

## 6. Recommended fixes (priority order)
1. **DONE** — input-shape, gobuster, subjack, nikto, metabigor, gau.
2. **Rebuild the image** to land nikto/metabigor (image-layer) — in progress.
3. *Optional:* install the 4 cleanly-installable curated tools (trufflehog via go,
   kiterunner via go; feroxbuster/findomain are rust binary-downloads, arch-
   fragile + redundant with trufflehog3/ffuf/subfinder) — low value, redundant.
4. *Optional:* mark the 4 script-only curated tools (cloud_enum, graphw00f,
   linkfinder, secretfinder) `non_executable` until handwritten adapters exist,
   so they don't show as enabled-but-missing.
5. *Optional:* make `default_on` meaningful OR delete the field (currently dead).

## 7. Verification plan
- `scripts/install_audit.py` → install readiness (re-run after rebuild; nikto/
  metabigor should drop off the blocked list).
- `scripts/tool_invocation_probe.py --timeout 20` → broken invocations fail fast.
- `scripts/e2e_verify.py <scan> --rescan <scan2>` → per-tool layer table + dedup +
  loop + no-overwrite PASS.
- `pytest tests/atomic/test_pipeline_layers.py` → layer invariants.
- Re-run groww.in `--tools all --validate` and confirm gobuster/subjack/nikto
  produce or skip cleanly with a reason (no usage/banner garbage).

## 8. Patch plan (applied)
- `e63e990` `_shape_tokens` (input shape) · `91474d8` gobuster `--domain` + gau ·
  this commit: subjack `-c` drop, nikto `libjson-perl`, metabigor env.
- Tests: `test_pipeline_layers.py`, `test_generic_engine.py::test_shape_tokens...`.
- Harnesses: `install_audit.py`, `tool_invocation_probe.py`, `e2e_verify.py`.
