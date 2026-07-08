# Tool Coverage — why only some of the "500+" run (evidence-based)

Branch `arch/event-driven-engine-v2`. Answers "the artifact dir doesn't have a
directory for every tool → not all are running." Backed by `scripts/install_
audit.py`, a registry-vs-`tool_run` cross-reference, and a live groww.in scan.

## The headline: 586 registry entries ≠ 586 runnable tools
| Count | Category | Runs? | Why |
|---|---|---|---|
| **27** | RAN: produced | ✅ | real output (subdomains/ips/urls/findings/services) |
| **48** | RAN: empty | ✅ ran | rc=0, 0 results **for this target** (crt.sh/amass/gf-* etc. — legit, not a bug) |
| **102** | disabled — `non_executable` | ❌ can't | **not CLI tools**: awesome-list/reference pages (`Awesome Bug Bounty`, `Archive.today`), web/GUI tools, and utilities that aren't entity-producers (`anew`, `notify`, `alterx`, `cdncheck`) |
| **216** | disabled — inventory, no contract | ❌ can't | documented stub with **no invocation/parse** — never integrated |
| **153** | NOT RUN — inventory stub, no binary | ❌ | synthesized binary name, **not installed**; pruned at routing |
| **26** | NOT RUN — unavailable curated | ❌ | missing binary (feroxbuster/findomain…) or **missing API key** (shodan/censys/…) |
| **14** | NOT RUN — available, chain-orphaned | ⚠️ | wired + installed but **no input key was produced** for them |

So **~75 tools actually run**; the rest are non-tools (~100+), un-integrated
documented stubs (~370), key/binary-gated (26), or chain-orphaned (14). "Make all
500+ run" is not meaningful — most aren't runnable tools, and the rest need
per-tool integration (install + invocation + parse), which the agreed build order
(see `recontool-architecture-advice`) says to do by **high-value vertical slice**,
not breadth.

## Is recursion / data completeness broken? No (with one fixed exception)
- **Recursion works**: dnsx/httpx/tlsx/massdns/puredns/DNSRecon/js-render each
  produced **~81 per-key output files** = ran on every discovered subdomain.
- **No empty typed files** in the post-fix scan (empties were pre-fix:
  paramspider banner, ffuf usage — already fixed).
- **Append-not-overwrite** holds (`save_typed` mode `a`; e.g. `dns_resolve.
  subdomain.jsonl` accumulates across keys).

## The 14 chain-orphaned tools — root cause = missing input KEY type
Work items only ever had `subdomain`/`url`/`domain` keys. These tool families
never fired because **nothing produced their input key**:
| Family | consumes | Why no key | Verdict |
|---|---|---|---|
| jsluice / linkfinder / secretfinder | `js_file` | crawler harvested 56 JS files but **never emitted a js_file asset** | **REAL BUG — FIXED** (crawler now emits js_file; jsluice activates) |
| masscan / naabu(port) / cero / greynoise / internetdb / mapcidr | `ip` / `cidr` | the target's resolved IPs are **all `in_scope=0`** (a domain seed has no CIDR scope) → dropped from recursion | **Scope-correct for a CDN target** (groww.in's IPs are Cloudflare's — scanning them = scanning the CDN, not the target). Would fire for an IP/CIDR seed. Activating for direct-IP targets needs cdncheck-gated IP-scoping. |
| bgpview / ripestat | `asn` | asnmap emits `cidr`, not `asn` | enrich-only; low value for a CDN target (returns the CDN's ASN) |
| github_org_repos / metabigor / gitleaks | `org` / `repo` | no `org` seed produced from the domain | needs org-seeding (whois/asn org → org key); github also key-gated |
| epss | `cve` | no `cve` key emitted from vuln findings | needs nuclei/vuln to emit cve keys |
| s3scanner | `bucket` | no `bucket` key produced | needs cloud-enum to emit bucket keys |
| interactsh | `none` | no-input tool, never seeded | needs explicit OOB seeding |

## Fixes applied this round
- **js_file chain (real bug)**: `crawler.py::grab_js` now emits each harvested JS
  as a recursable `js_file` asset (absolute path) → jsluice runs on real JS;
  linkfinder/secretfinder activate once installed. (commit + test.)

## Recommended remediation (priority, honest)
1. **DONE** — js_file chain (activates JS analysis on real harvested data).
2. *Medium, safe:* org-seeding (seed domain → org via whois/asnmap org field) to
   activate metabigor/github_org_repos (passive/key-gated).
3. *Medium:* asnmap emit `asn` → bgpview/ripestat (passive enrichment).
4. *Design decision (active/safety):* cdncheck-gated IP-scoping — treat the
   target's **non-CDN** resolved IPs as in-scope so masscan/naabu/ip-enrichment
   run, while never scanning CDN ranges. Needed for direct-IP targets; for CDN
   targets the current skip is correct.
5. *Large, per-tool:* the 153 inventory stubs need install + invocation + parse
   each — most are **redundant** (many subdomain/bucket/JS tools), **heavy
   frameworks** (BBOT/Osmedeus/SpiderFoot/ReconFTW are full suites, not single
   tools), **key/account-gated** (social OSINT, GitHub dorks), or **not tools**
   (awesome-lists). Integrate by value, not breadth.
6. *Cleanup:* the inventory ingested ~dozens of "Awesome *" reference pages as
   "tools" — they should be excluded from the tool count to stop overstating the
   universe.

## Verification
- `scripts/install_audit.py` (readiness) · registry-vs-tool_run cross-ref (above)
  · `scripts/e2e_verify.py` (per-tool layer table) · `tests/atomic/test_pipeline_
  layers.py` (append/AI/dedup invariants).
