# Tool-contract deferrals — what's left and exactly why

Status from the reproducible auditor
(`python3 .claude/skills/recon-integration-tracker/scripts/tool_contract_audit.py`):
**261 runnable, 253 clean, 8 INPUT issues.** Every issue below is a tool whose
invocation still references a token the generic CLI adapter cannot fill
(`{outfile}`, `{infile}`, `{repo}`, …). None is fixable by the existing mechanisms
(stdin/stdout plumbing, aux-token resolution, variant expansion, `non_executable`);
each needs a specific, separately-scoped change. Listed cheapest → most involved.

The reason these are *documented* rather than force-fixed: a wrong parse spec on a
tool I can't live-verify would look "fixed" in the audit while still producing 0 —
worse than an honest deferral. Each entry says exactly what's needed to unblock it.

---

## 1. waymore — redundant, contract-fixable, low priority
- **Invocation:** `waymore -i {domain} -mode U -oU {outfile}`
- **Blocker:** `{outfile}` (a results file). waymore *can* take `-oU /dev/stdout`,
  but it also writes progress to stdout and needs a `config.yml` (API keys for
  some sources) to do anything beyond the free sources.
- **Why deferred, not fixed:** it overlaps `gau` + `waybackurls`, both already
  wired and working (227k/159k URLs on groww.in). Fixing it adds little new data.
- **To unblock:** `-oU /dev/stdout`, `output_format: text`, emit `endpoint {_value}`,
  and confirm in a live run that progress lines don't pollute stdout (if they do,
  add a `line_regex` that only keeps `^https?://`). ~15 min once verified live.

## 2. whatweb — tech fingerprinting with no entity model
- **Invocation:** `whatweb --log-json={outfile} {url}`
- **Blocker:** two things. (a) `--log-json=/dev/stdout` mixes the JSON with
  whatweb's plain-text summary on stdout — there is no flag that suppresses the
  summary while keeping `--log-json`. (b) The JSON is a top-level **array** whose
  element has a `plugins` **dict** (`{"nginx":[…],"Country":[…]}`); the generic
  emit can iterate a list (`value_each`) but not a dict's keys, so it can't lift
  the detected technologies.
- **Deeper issue:** there is no canonical **`tech`** entity type — tech findings
  aren't modelled anywhere, so even `httpx -tech-detect` (already running) only
  collects the raw signal without surfacing it.
- **To unblock:** model tech as findings/attributes (a small schema decision),
  then a tiny handwritten adapter (or a `plugins`-aware emit) for whatweb. Until
  tech is modelled, this produces nothing useful regardless of the binary.

## 3. nmap — generic parser has no XML, and greppable can't split per-port
- **Invocation:** `nmap -sV -sC -p {ports} -oX {outfile} {host}` (`{ports}` already
  resolves via `_aux_tokens`).
- **Blocker:** `-oX` is XML; `parse_records` only does json/jsonl/text/csv. The
  greppable alternative (`-oG -`) puts **all** of a host's ports on **one line**
  (`Ports: 443/open//https//, 80/open//http//`), and the generic parser emits one
  record per line — it cannot split that into N `service` events.
- **Context:** naabu (handwritten) already covers port discovery; nmap's unique
  value is `-sV` version + `-sC` script output.
- **To unblock:** a handwritten `nmap` adapter that runs `-oX -` and parses the XML
  into one `service` per `<port>` (host/port/product/version). ~1–2h. This is the
  cleanest path and mirrors the existing naabu/PortScan adapter.

## 4. sslyze — deeply nested JSON the generic emit can't navigate
- **Invocation:** `sslyze --json_out {outfile} {host}`
- **Blocker:** `--json_out=/dev/stdout` (with `--quiet`) gives clean JSON, but the
  structure is deep:
  `server_scan_results[].scan_result.{certificate_info,heartbleed,robot,
  ssl_2_0_cipher_suites,…}`. The generic emit does flat/dotted field access on a
  single record — it can't fan a dozen heterogeneous finding types (expired cert,
  weak cipher, Heartbleed, ROBOT, …) out of that tree.
- **To unblock:** a handwritten `sslyze` adapter mapping the nested result to
  `finding`s. Medium effort (~2–3h) and worth it — these are real high-signal TLS
  findings nothing else in the set produces.

## 5. gowitness — evidence tool, output is screenshots not entities
- **Invocation:** `gowitness scan file -f {infile} --write-db --screenshot-path {outdir}`
- **Blocker:** gowitness produces **PNG screenshots + a sqlite DB**, not stdout
  entities. `{infile}` → `/dev/stdin` is easy; `{outdir}` has no token, and the
  tool emits nothing the entity graph consumes.
- **To unblock:** (a) add an `{artifact_dir}` aux token resolving to the scan's
  `ctx.artifacts` path, (b) `-f /dev/stdin --screenshot-path {artifact_dir}`, (c)
  accept zero entity emission — it's an evidence-gatherer (screenshots for manual
  review), optionally emitting a `screenshotted` edge per URL. ~1h. Mainly a
  decision: do we want a non-entity "evidence" tool class?

## 6. kiterunner — needs a large data dependency
- **Invocation:** `kr scan {infile} -w routes-large.kite -o json -O {outfile}`
- **Blocker:** the `routes-large.kite` API-route wordlist (~hundreds of MB) is
  **not installed**, and it's a heavy **active** API-route brute-forcer.
  `{infile}`→`/dev/stdin`, `{outfile}`→`/dev/stdout` are trivial.
- **To unblock:** (a) decide to ship the `.kite` dep (add to
  `docker/install_tools.sh`, sizeable image growth), (b) wire stdin/stdout + a
  jsonl parse emitting `endpoint`. Opt-in (`default_on:false`). The real question
  is whether the image-size cost is wanted.

## 7. gitleaks — needs a new `repo` entity type AND a producer
- **Invocation:** `gitleaks detect --source {repo} --report-format json --report-path {outfile}`
- **Blocker:** the deepest one. `{repo}` is a **git-repository** input that **no
  tool produces** and that **isn't a canonical entity type** (`categories.yaml`
  `dedupe_forms` has no `repo`). So gitleaks is unreachable even with a perfect
  invocation.
- **To unblock (multi-part):**
  1. add `repo` to the canonical types (`config/categories.yaml`);
  2. wire a **producer** — e.g. a `github-org-repos` API tool consuming `org` →
     producing `repo` (org is already produced by org-fingerprinting);
  3. then gitleaks: `--source {repo} --report-path /dev/stdout`, parse the JSONL
     findings → `finding` (secret), redacted.
  This is a vertical slice (entity type + producer + consumer), not a one-liner.

---

## Already resolved this pass (for context)
- **Marked `non_executable`** (not entity producers / deferred): notify (alert
  sink), anew (dedupe utility), dnsvalidator (resource generator), cdncheck (noise
  filter role), alterx (permutation candidates need a `subdomain_candidate` type +
  resolver gate — same shape as gitleaks' new-type need).
- **Wired** off the `{outfile}` path: wafw00f (WAF finding), cloud_enum
  (exposed-bucket finding).

## Recommended order if picking these up
1. **nmap** (handwritten XML adapter) — high value, self-contained, mirrors naabu.
2. **sslyze** (handwritten adapter) — high-signal TLS findings, self-contained.
3. **gitleaks `repo` slice** — unlocks an entire secret-scanning capability and
   the same `repo`/`subdomain_candidate` new-type pattern that also unblocks alterx.
4. **gowitness** (`artifact_dir` token + evidence class) — useful for triage.
5. **waymore** (15-min contract fix) — only if the gau/wayback overlap isn't enough.
6. **whatweb / tech model** — needs the broader "tech as findings" decision first.
7. **kiterunner** — only if the `.kite` image-size cost is acceptable.
