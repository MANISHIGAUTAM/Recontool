# Gaps Found & Advancements

What surfaced while wiring the long tail of tools, what I fixed, and the concrete
improvements made (and proposed). Honest status, not aspirational.

---

## A. Gaps found (and how they were handled)

| Gap | Impact | Resolution |
|-----|--------|------------|
| **Empty auth header crashed httpx** | a keyless API spec with `Authorization: Bearer {key}` rendered `Bearer ` and threw `LocalProtocolError`, killing the adapter | Generic API adapter now **drops empty / scheme-only headers** (so keyless tier works, key tier still authenticates). Validated: certspotter works keyless. |
| **Flaky / blocked free sources** | `jldc.me/anubis` → 403 (Cloudflare), `api.subdomain.center` → read timeout | `anubis` removed; `subdomaincenter` kept but `enabled: false`. Honest over count. |
| **stdin-based CLI tools** | `httprobe`, `anew`, `gf`, `qsreplace`, `subjack -w`, `puredns` read a list on **stdin**, not a single arg — the generic CLI adapter passes one `{value}` arg | Documented as a known limitation; **planned**: a `stdin: true` spec mode that pipes the input set to the tool. Hand-written adapters cover the critical ones (dns_resolve, httpx_probe, naabu) today. |
| **Keyed APIs returning prefix-only lists** | SecurityTrails/Chaos return subdomain *labels* (`www`) not FQDNs; generic `value_each` can't append `.{domain}` | **Planned**: `value_suffix: ".{domain}"` parse option. Left unwired rather than emit wrong data. |
| **No pagination** | some APIs page results; generic adapter fetches page 1 | **Planned**: `paginate:` spec block (cursor/offset). Acceptable for recon breadth now. |
| **Web/GUI-only tools (82)** | no CLI/API — can't automate | Flagged `web_only` in the inventory + per-tool docs; excluded from the automated chain by design. |
| **bgpview unreachable in sandbox** | DNS `Name or service not known` for `api.bgpview.io` here | Not a code bug — adapter **degrades gracefully** (0 events, no crash). Works where DNS resolves. |

---

## B. Advancements implemented this round

1. **Registry-driven generic adapter engine** (`recontool/adapters/generic.py`).
   A tool is now a declarative YAML spec, not a Python class. Two executors
   (API + CLI) run any spec. This is the only scalable way to reach 500+ tools.

2. **Pure, unit-testable parse engine** (`parse_records` + `emit_events`).
   Output→Event mapping is validated against fixtures with no network/subprocess —
   11 new atomic tests cover json/jsonl/text/csv, `list_path`, `value_each`,
   `scope_filter`, and edge/service/endpoint/finding emission.

3. **Auto-registration** (`recontool/adapters/autoload.py`).
   Specs load and register into pipeline phases automatically; hand-written adapters
   are never overridden (they win on name collision).

4. **Scope-safe parsing.** The parser applies `is_subdomain_of` scope filtering at
   emit time, so generic tools can't pollute the inventory with out-of-scope hosts
   (the same bug class fixed earlier for hand-written adapters).

5. **Graceful degradation everywhere.** Missing binary, missing key, network error,
   bad JSON → adapter returns `[]`, never crashes the pipeline.

6. **Flow generator now merges generic specs** — `docs/flow/` shows 53 authoritative
   invocations (was 50), and adding a spec upgrades both the runnable pipeline and
   the flow docs at once.

7. **Pure-Python web crawler** (`recontool/adapters/crawler.py`, `pycrawl`).
   A self-contained, scope-aware, rate-limited BFS crawler built on the platform's
   own async HttpClient + stdlib `html.parser` — **no external binary** (works where
   `katana`/`hakrawler` aren't installed). It extracts links (a/script/form/img/link),
   downloads `.js` to local storage, mines endpoints + secrets from inline/crawled JS,
   discovers new in-scope subdomains (feeding the recursive loop), and re-checks scope
   before every fetch (verified live: crawled `example.com` with zero offsite egress).

8. **Pure-Python content/directory discovery** (`content_discovery.py`, `pydirb`).
   ffuf-style path brute-force over the rate-limited HttpClient with **404 / soft-404
   ("wildcard") calibration** so junk responses are filtered. Built-in high-signal
   wordlist (admin/api/.git/.env/...) extensible via `config` resources. Falls back to
   ffuf/feroxbuster if installed. Verified live against `example.com` (calibrated,
   no false hits, no crash).

9. **Form & parameter extraction** (`params.py`). `params_from_url` mines query-string
   params from the discovered URL corpus (`param_miner` adapter); `extract_forms`
   pulls `<form>` action/method + input/select/textarea names from crawled HTML (wired
   into `pycrawl`). Params persist to `endpoint.params` (merged on re-discovery),
   ready to feed fuzzing — closing the Category-20/25 active-recon gap with zero
   external dependencies.

---

## C. Advancements proposed (ranked, not yet built)

| Idea | Why | Effort |
|------|-----|--------|
| **`stdin: true` CLI mode** | unlocks httprobe/anew/gf/qsreplace/subjack/puredns (a big slice of the CLI long tail) | S |
| **Parse transforms** (`{asn\|num}`, `{v\|lower}`, `value_suffix`) | unlocks SecurityTrails/Chaos prefix lists + cleaner ASN handling | S |
| **API pagination** (`paginate: {cursor\|offset}`) | full results from VirusTotal/SecurityTrails/urlscan | M |
| **Spec linter + auto golden-test scaffold** | every new spec gets a fixture test stub; guards output drift | M |
| **Per-spec rate-limit override** | respect each provider's documented limit from the spec | S |
| **Plugin entrypoint** (`recontool plugins add`) | drop a spec file + fixture and go; community tools | M |
| **Output transforms / enrichers in-spec** | e.g. derive `tag` from a field, map product→CPE | M |
| **`stdin` chunking + concurrency per spec** | large fan-outs (15k urls) without OOM | M |

---

## D. Doubts resolved (decisions taken)

- *"Write a class per tool?"* — **No.** Unmaintainable and untestable at 500+. Chose the
  declarative generic engine; hand-write only the complex/high-value ones.
- *"Wire flaky free APIs to boost the count?"* — **No.** Removed/disabled ones that 403
  or time out; correctness and reliability over raw tool count.
- *"Emit prefix-only subdomains to wire SecurityTrails now?"* — **No.** Would produce
  wrong assets; deferred until `value_suffix` transform exists.
- *"Block the pipeline when a tool/binary/key is missing?"* — **No.** Everything degrades
  gracefully; the scan always completes with whatever sources are available.
