# Tool-contract deferrals — ALL RESOLVED

Status from the reproducible auditor
(`python3 .claude/skills/recon-integration-tracker/scripts/tool_contract_audit.py`):
**267 runnable, 267 clean, 0 INPUT / 0 NOEXEC / 0 OUTPUT issues.** Every tool that
was deferred below has been implemented. Kept as a record of what each blocker
was and how it was solved.

Resolution summary:
- **nmap** (`3fc26be`) — handwritten `NmapServiceScan` (XML -> service per port).
- **sslyze** (`029fd84`) — handwritten `SslyzeScan` (nested JSON -> TLS findings).
- **gitleaks** (`f99382d`) — `repo` producer (`github_org_repos`) + handwritten
  `GitleaksScan` (clone + scan + redact). `repo` type now produced AND consumed.
- **whatweb** (`c37f225`) — handwritten `WhatWebScan` (--log-json tempfile ->
  `tech` findings); live-verified. Establishes the "tech as findings" model.
- **gowitness** (`c37f225`) — handwritten `GoWitness` evidence tool (screenshots
  into the artifact dir -> `screenshot` assets; needs chromium to produce images).
- **kiterunner** (`c37f225`) — /dev/stdin + `{kite_wordlist}` aux token; routes-
  small.kite added to install_tools.sh (routes-large ~1GB intentionally not shipped).
- **waymore** (`c37f225`) — `-oU /dev/stdout` + URL line_regex -> endpoints.
- **github_search** (`c37f225`, bonus) — variant-expanded over secret dorks -> repo
  assets that feed gitleaks/trufflehog.

Operational notes: sslyze/gitleaks/kiterunner/gowitness need their binary or data
dep present (a `docker compose build recontool` runs the updated install_tools.sh);
each degrades to a clean skip when absent.

---

The original blocker write-ups follow (for the record).

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

## 3. nmap — ✅ DONE (`3fc26be`)
Implemented as the handwritten `NmapServiceScan` adapter (`adapters/active.py`):
runs `nmap -sV -sC -T4 -Pn --top-ports N -oX -` per host and parses the XML into
one `Event.service` per OPEN port (service_name + product/version). consumes
ip/subdomain, default_on=False (heavy), capped 50 hosts. Live-verified against
scanme.nmap.org. The bridge now honors a `default_on` class attr so heavy
handwritten adapters can be available-but-opt-in.

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
