# 28-Category Build-Ready Contracts

> Generated from `config/categories.yaml` by `recontool.inventory.build_categories`. Authorized-only, no-evasion (see `docs/blueprint/`).

**Provenance fields (every entity):** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

## Seed routing (which categories a seed activates, in planner order)

| Seed type | Categories (priority order) |
|-----------|------------------------------|
| `domain` | 2, 1, 3, 17, 6, 4, 9, 7, 10, 11, 5, 13, 24, 22, 28 |
| `subdomain` | 2, 6, 21, 5, 13, 24, 22, 20, 23, 25, 27 |
| `ip` | 1, 3, 12, 21, 24, 27 |
| `cidr` | 3, 21 |
| `asn` | 1, 3 |
| `email` | 7, 12 |
| `username` | 7, 8 |
| `org` | 1, 3, 9, 7, 10, 18 |
| `url` | 6, 5, 13, 22, 20, 23, 25, 27 |
| `repo` | 9, 22 |
| `apk` | 26 |

## Pipeline priority order (all categories, cheapest high-signal first)

14 → 19 → 2 → 1 → 3 → 17 → 6 → 4 → 9 → 7 → 8 → 10 → 11 → 12 → 16 → 15 → 21 → 5 → 13 → 24 → 22 → 20 → 23 → 25 → 26 → 27 → 28 → 18


---

## 1. Internet-Wide Search & Asset Discovery

`stage=discover` · `active=False` · `priority=14`

**1. Purpose.** Discover exposed assets from third-party internet indexes/search without touching the target.

**2. Input schema (input_types).** `domain, org, ip, asn`

**3. Output schema (output_types).** `subdomain, ip, service, cert, url, tech`

**Canonical dedupe keys.**
- `subdomain` → `domain:{lower_fqdn}`
- `ip` → `ip:{normalized}`
- `service` → `svc:{host}:{port}/{proto}`
- `cert` → `cert:{sha256_fingerprint}`
- `url` → `url:{canonical_sorted_params_no_frag}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `2, 3, 5, 21, 24`

**5. Tool families.** shodan, censys, netlas, leakix, fullhunt, criminalip, urlscan, uncover, fofa, zoomeye, binaryedge, onyphe

**6. Priority order.** `14` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_subdomain, new_ip, new_cert_san

**8. Failure handling.**
- failure_modes: `auth_error, quota_exhausted, empty, schema_drift, timeout`
- retry_policy: `max_attempts=3; backoff=exp_jitter; retry_on=[429, 500, 502, 503, 504, 'timeout']`
- quota_policy: `unit=credit; per_minute=10; concurrency=2; budget_per_run=200`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `asset(ip/subdomain/cert/url)+service` · raw artifacts: `raw/<tool>/`

**10. Operator notes.** Prefer free Shodan internetdb; gate paid credits via budget ledger; uncover wraps several engines.


---

## 2. Passive DNS & Subdomain Enum

`stage=discover` · `active=False` · `priority=10`

**1. Purpose.** Build the subdomain universe (passive), then resolve+validate (active) to live hosts.

**2. Input schema (input_types).** `domain, subdomain`

**3. Output schema (output_types).** `subdomain, ip, cert`

**Canonical dedupe keys.**
- `subdomain` → `domain:{lower_fqdn}`
- `ip` → `ip:{normalized}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `5, 6, 20, 21, 22, 24`

**5. Tool families.** subfinder, amass_passive, crtsh, certspotter, chaos, securitytrails, virustotal, hackertarget, alienvault_otx, assetfinder, findomain, dnsx, puredns, massdns, shuffledns

**6. Priority order.** `10` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_subdomain, new_cname, new_cert_san

**8. Failure handling.**
- failure_modes: `provider_quota, flaky_ct, wildcard_dns, timeout, empty`
- retry_policy: `max_attempts=3; backoff=exp_jitter; retry_on=[429, 500, 502, 503, 504, 'timeout']`
- quota_policy: `unit=query; per_minute=20; concurrency=2; budget_per_run=100`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `asset(subdomain/ip)+edge(resolves_to,cname_to,subdomain_of)` · raw artifacts: `raw/<tool>/`

**10. Operator notes.** Discovery passive; resolution (dnsx/puredns) is ACTIVE -> auth gate. Wildcard-filter before persist.


---

## 3. WHOIS / ASN / BGP / Network Intel

`stage=network` · `active=False` · `priority=16`

**1. Purpose.** Map ownership and network ranges; expand ASN->CIDR->IP and reverse-WHOIS to related domains.

**2. Input schema (input_types).** `domain, ip, asn, org`

**3. Output schema (output_types).** `asn, cidr, ip, org, domain`

**Canonical dedupe keys.**
- `asn` → `asn:{number}`
- `cidr` → `cidr:{normalized}`
- `ip` → `ip:{normalized}`
- `domain` → `domain:{lower_fqdn}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `1, 2, 21`

**5. Tool families.** asnmap, bgpview, ripestat, ipinfo, team_cymru, rir_whois, metabigor, mapcidr, peeringdb, robtex

**6. Priority order.** `16` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_cidr, new_related_domain, new_asn

**8. Failure handling.**
- failure_modes: `empty, schema_drift, timeout, rate_limited`
- retry_policy: `max_attempts=3; backoff=exp_jitter; retry_on=[429, 500, 502, 503, 504, 'timeout']`
- quota_policy: `unit=request; per_minute=30; concurrency=4; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `asset(asn/cidr/ip)+edge(in_cidr,announced_by,owned_by)` · raw artifacts: `raw/<tool>/`

**10. Operator notes.** CIDRs feed port scanning; related apex domains re-enter cat 2. metabigor needs no key.


---

## 4. Search Engine Dorking & Index

`stage=enrich` · `active=False` · `priority=22`

**1. Purpose.** Mine indexed/dorked exposure (files, panels, secrets in code search).

**2. Input schema (input_types).** `domain, live_host`

**3. Output schema (output_types).** `url, repo, finding`

**Canonical dedupe keys.**
- `url` → `url:{canonical_sorted_params_no_frag}`
- `repo` → `repo:{host}/{owner}/{name}`
- `finding` → `finding:{asset}:{detector}:{signature}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `9, 20, 22, 25`

**5. Tool families.** brave_search, mojeek, searxng, google_pse, bing_legacy, github_dorks, pagodo, grep_app

**6. Priority order.** `22` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_url, new_repo

**8. Failure handling.**
- failure_modes: `auth_error, quota_exhausted, captcha, empty, tos_block`
- retry_policy: `max_attempts=3; backoff=exp_jitter; retry_on=[429, 500, 502, 503, 504, 'timeout']`
- quota_policy: `unit=query; per_minute=20; concurrency=2; budget_per_run=100`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `endpoint(url)+finding+repo` · raw artifacts: `raw/<tool>/`

**10. Operator notes.** Google PSE / Bing are plugins only (quota/ToS). Independent indexes -> dedupe by canonical url.


---

## 5. Web Technology Fingerprinting

`stage=validate` · `active=True` · `priority=52`

**1. Purpose.** Fingerprint live web stacks (server/framework/CMS/WAF) and confirm liveness.

**2. Input schema (input_types).** `live_host, url, subdomain`

**3. Output schema (output_types).** `tech, service, tag, finding`

**Canonical dedupe keys.**
- `tech` → `tech:{name}:{version}`
- `service` → `svc:{host}:{port}/{proto}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `12, 20, 23, 27`

**5. Tool families.** httpx, whatweb, webanalyze, wappalyzer, wafw00f, cdncheck, retire_js

**6. Priority order.** `52` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_tech_for_wordlist, cms_detected

**8. Failure handling.**
- failure_modes: `timeout, tls_error, waf_block, render_needed`
- retry_policy: `max_attempts=2; backoff=exp; retry_on=['timeout', 'conn_reset']`
- quota_policy: `unit=request; per_minute=600; concurrency=20; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `asset.tech[]/tags[]+service` · raw artifacts: `raw/<tool>/`

**10. Operator notes.** httpx is the live-validation hub. Detected tech drives smart wordlist selection (cat 25/28). CDN/WAF tag -> tune, never bypass.


---

## 6. Historical & Archive Recon

`stage=enrich` · `active=False` · `priority=20`

**1. Purpose.** Harvest historical URLs/JS (deleted endpoints, old params) from web archives.

**2. Input schema (input_types).** `domain, live_host`

**3. Output schema (output_types).** `url, js_file`

**Canonical dedupe keys.**
- `url` → `url:{canonical_sorted_params_no_frag}`
- `js_file` → `js:{body_sha256}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `5, 22, 25`

**5. Tool families.** wayback_cdx, common_crawl, gau, waybackurls, waymore, urlscan_history

**6. Priority order.** `20` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_url, new_js_file

**8. Failure handling.**
- failure_modes: `timeout, ratelimited, empty, oversize`
- retry_policy: `max_attempts=4; backoff=exp_jitter; retry_on=[429, '5xx', 'timeout']`
- quota_policy: `unit=request; per_minute=30; concurrency=4; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `endpoint(url)+js_file ref` · raw artifacts: `raw/<tool>/; js/<host>/`

**10. Operator notes.** gau aggregates Wayback+CC+OTX+urlscan. Common Crawl run ONLY when redundancy score says it adds unique coverage.


---

## 7. Email / Username / Identity

`stage=overlay` · `active=False` · `priority=30`

**1. Purpose.** Discover org emails, breach exposure, and identity pivots (PII-gated).

**2. Input schema (input_types).** `domain, email, username, org`

**3. Output schema (output_types).** `email, username, finding`

**Canonical dedupe keys.**
- `email` → `email:{lower}`
- `username` → `user:{platform}:{handle}`
- `finding` → `finding:{asset}:{detector}:{signature}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `8, 12`

**5. Tool families.** hunter, theharvester, phonebook, hibp, dehashed, holehe, ghunt, epieos

**6. Priority order.** `30` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_email, new_username

**8. Failure handling.**
- failure_modes: `auth_error, quota_exhausted, pii_legal_gate, empty`
- retry_policy: `max_attempts=3; backoff=exp_jitter; retry_on=[429, 500, 502, 503, 504, 'timeout']`
- quota_policy: `unit=query; per_minute=20; concurrency=2; budget_per_run=100`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `asset(email)+finding(breach,redacted)` · raw artifacts: `raw/<tool>/ (encrypted, short TTL)`

**10. Operator notes.** PII/breach data: legal gate + data minimization + shortest retention; never archive raw breach data.


---

## 8. Social Media Recon

`stage=overlay` · `active=False` · `priority=32`

**1. Purpose.** Map social presence and identity correlation across platforms.

**2. Input schema (input_types).** `username, org, handle`

**3. Output schema (output_types).** `username, url, finding`

**Canonical dedupe keys.**
- `username` → `user:{platform}:{handle}`
- `url` → `url:{canonical_sorted_params_no_frag}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `7`

**5. Tool families.** sherlock, maigret, blackbird, instaloader, social_analyzer, twint, pushshift

**6. Priority order.** `32` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_username, new_handle

**8. Failure handling.**
- failure_modes: `platform_block, login_required, empty, broken_scraper`
- retry_policy: `max_attempts=3; backoff=exp_jitter; retry_on=[429, 500, 502, 503, 504, 'timeout']`
- quota_policy: `unit=request; per_minute=30; concurrency=4; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `intel(username/profile)` · raw artifacts: `raw/<tool>/`

**10. Operator notes.** Active against 3rd-party platforms; scope-dependent, off by default for pure domain recon.


---

## 9. GitHub / GitLab / Source Code

`stage=enrich` · `active=False` · `priority=24`

**1. Purpose.** Discover org repos and leaked secrets/configs/endpoints in source.

**2. Input schema (input_types).** `org, domain, keyword`

**3. Output schema (output_types).** `repo, endpoint, finding`

**Canonical dedupe keys.**
- `repo` → `repo:{host}/{owner}/{name}`
- `endpoint` → `ep:{host}:{method}:{path}`
- `finding` → `finding:{asset}:{detector}:{signature}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `10, 22, 25`

**5. Tool families.** github_code, gitleaks, trufflehog, gitdorker, sourcegraph, semgrep, trivy

**6. Priority order.** `24` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_repo, cloud_key_found, new_endpoint

**8. Failure handling.**
- failure_modes: `secondary_rate_limit, auth_error, empty`
- retry_policy: `max_attempts=5; backoff=exp_jitter_long; retry_on=['403_secondary', 429, '5xx', 'timeout']`
- quota_policy: `unit=search; per_minute=10; concurrency=1; budget_per_run=60`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `repo+finding(secret,REDACTED)+endpoint` · raw artifacts: `repos/<org>/; raw/<tool>/`

**10. Operator notes.** Secrets stored hash+mask+location ONLY, never raw. trufflehog verify (active) is a toggle. Token rotation for QUOTA, not evasion.


---

## 10. Cloud & Storage Recon

`stage=enrich` · `active=True` · `priority=34`

**1. Purpose.** Find exposed cloud buckets/blobs/functions and origin behind CDN.

**2. Input schema (input_types).** `org, domain, keyword`

**3. Output schema (output_types).** `bucket, finding, ip`

**Canonical dedupe keys.**
- `bucket` → `bucket:{provider}:{name}`
- `finding` → `finding:{asset}:{detector}:{signature}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `12, 27`

**5. Tool families.** grayhatwarfare, cloud_enum, s3scanner, gcpbucketbrute, cloudbrute, cloudfail, cloudlist

**6. Priority order.** `34` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_bucket, origin_ip_found

**8. Failure handling.**
- failure_modes: `provider_throttle, access_denied, empty`
- retry_policy: `max_attempts=2; backoff=exp; retry_on=['timeout', 'conn_reset']`
- quota_policy: `unit=request; per_minute=30; concurrency=4; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `asset(bucket)+finding(open_bucket,misconfig)` · raw artifacts: `raw/<tool>/`

**10. Operator notes.** grayhatwarfare passive; cloud_enum/s3scanner active vs cloud provider endpoints (not target app). No credentialed audit unless authorized.


---

## 11. Metadata & Document Recon

`stage=enrich` · `active=False` · `priority=36`

**1. Purpose.** Harvest public documents and extract metadata (users, paths, software).

**2. Input schema (input_types).** `domain, url`

**3. Output schema (output_types).** `document, email, finding, tag`

**Canonical dedupe keys.**
- `document` → `doc:{sha256}`
- `email` → `email:{lower}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `7, 20`

**5. Tool families.** metagoofil, exiftool, tika, oletools, pdfinfo, strings

**6. Priority order.** `36` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_username_from_meta, new_internal_path

**8. Failure handling.**
- failure_modes: `download_fail, parse_error, empty`
- retry_policy: `max_attempts=3; backoff=exp_jitter; retry_on=[429, 500, 502, 503, 504, 'timeout']`
- quota_policy: `unit=request; per_minute=30; concurrency=4; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `document+intel(user/path/software)` · raw artifacts: `documents/<sha256>`

**10. Operator notes.** Harvested paths seed content discovery (cat 20); usernames pivot to cat 7.


---

## 12. Malware / IOC / Threat Intel

`stage=enrich` · `active=False` · `priority=38`

**1. Purpose.** Enrich IPs/domains/services with IOC/threat intel and map CVEs (correlation, no exploit).

**2. Input schema (input_types).** `ip, domain, url, service, cpe, hash`

**3. Output schema (output_types).** `ioc, finding, tag`

**Canonical dedupe keys.**
- `ioc` → `ioc:{type}:{value}`
- `finding` → `finding:{asset}:{detector}:{signature}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `27`

**5. Tool families.** virustotal, otx, threatfox, abuse_ch, pulsedive, nvd, epss, vulners, shodan_cve, greynoise

**6. Priority order.** `38` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** cve_candidate_for_nuclei

**8. Failure handling.**
- failure_modes: `auth_error, quota_exhausted, empty, nvd_throttle`
- retry_policy: `max_attempts=3; backoff=exp_jitter; retry_on=[429, 500, 502, 503, 504, 'timeout']`
- quota_policy: `unit=query; per_minute=20; concurrency=2; budget_per_run=100`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `vuln_ref+finding(cve, priority_rank)+tag(malicious)` · raw artifacts: `raw/<tool>/`

**10. Operator notes.** service+version -> CPE -> NVD -> EPSS rank; nuclei (cat 27) confirms. GreyNoise = context only.


---

## 13. Visual Recon & Screenshotting

`stage=validate` · `active=True` · `priority=54`

**1. Purpose.** Capture screenshots of live hosts for triage and high-value flagging.

**2. Input schema (input_types).** `live_host, url`

**3. Output schema (output_types).** `screenshot, tag, tech`

**Canonical dedupe keys.**
- `screenshot` → `shot:{sha256}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `20, 27`

**5. Tool families.** gowitness, eyewitness, playwright, urlscan_screens

**6. Priority order.** `54` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** login_or_admin_panel_tag

**8. Failure handling.**
- failure_modes: `render_timeout, tls_error, oversize`
- retry_policy: `max_attempts=2; backoff=exp; retry_on=['timeout', 'conn_reset']`
- quota_policy: `unit=request; per_minute=600; concurrency=20; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `endpoint.evidence_ref+asset.tags(login/admin/high_value)` · raw artifacts: `screenshots/<sha256>.png`

**10. Operator notes.** Title/visual cues flag high-value targets for prioritized detection.


---

## 14. Frameworks & Automation Suites

`stage=engine` · `active=False` · `priority=0`

**1. Purpose.** Orchestration engines (we ARE one); integrate selected suites as sources, not as the platform.

**2. Input schema (input_types).** `domain`

**3. Output schema (output_types).** `subdomain, url, finding`

**Canonical dedupe keys.**
- `subdomain` → `domain:{lower_fqdn}`
- `url` → `url:{canonical_sorted_params_no_frag}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `2, 5`

**5. Tool families.** bbot, amass, reconftw, spiderfoot, recon_ng, projectdiscovery_stack, uncover, notify, interactsh

**6. Priority order.** `0` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** any_new_entity

**8. Failure handling.**
- failure_modes: `tool_missing, config_error, empty`
- retry_policy: `max_attempts=3; backoff=exp_jitter; retry_on=[429, 500, 502, 503, 504, 'timeout']`
- quota_policy: `unit=request; per_minute=30; concurrency=4; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `(routed to the proper typed tables)` · raw artifacts: `raw/<tool>/`

**10. Operator notes.** Integrate BBOT/Amass as ONE source feeding the corpus; do not adopt their store. notify=alert sink, interactsh=OAST.


---

## 15. Physical / Geo / Wireless

`stage=overlay` · `active=False` · `priority=42`

**1. Purpose.** Geo/wireless/telecom OSINT (scope-dependent; rarely part of domain recon).

**2. Input schema (input_types).** `org, bssid, coords, ip`

**3. Output schema (output_types).** `finding, tag`

**Canonical dedupe keys.**
- `finding` → `finding:{asset}:{detector}:{signature}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `—`

**5. Tool families.** wigle, opencellid, flightradar24, adsbexchange, marinetraffic, sentinel_hub, openstreetmap

**6. Priority order.** `42` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** —

**8. Failure handling.**
- failure_modes: `auth_error, empty, out_of_scope`
- retry_policy: `max_attempts=3; backoff=exp_jitter; retry_on=[429, 500, 502, 503, 504, 'timeout']`
- quota_policy: `unit=query; per_minute=20; concurrency=2; budget_per_run=100`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `intel(geo/wireless)` · raw artifacts: `raw/<tool>/`

**10. Operator notes.** Enable only when physical/geo is explicitly in scope.


---

## 16. Dark Web & Onion Recon

`stage=overlay` · `active=False` · `priority=40`

**1. Purpose.** Search indexed onion/leak sources for scope mentions (read-only intel).

**2. Input schema (input_types).** `domain, org, keyword`

**3. Output schema (output_types).** `onion, finding, url`

**Canonical dedupe keys.**
- `onion` → `onion:{addr}`
- `finding` → `finding:{asset}:{detector}:{signature}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `12`

**5. Tool families.** ahmia, onionsearch, intelx_tor, darksearch, dark_fail

**6. Priority order.** `40` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_leak_mention

**8. Failure handling.**
- failure_modes: `auth_error, tor_unavailable, empty, noisy`
- retry_policy: `max_attempts=3; backoff=exp_jitter; retry_on=[429, 500, 502, 503, 504, 'timeout']`
- quota_policy: `unit=query; per_minute=20; concurrency=2; budget_per_run=100`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `intel(onion/leak mention)` · raw artifacts: `raw/<tool>/`

**10. Operator notes.** Read-only OSINT; route over Tor only via authorized infra. No interaction with marketplaces.


---

## 17. APIs & Intelligence Feeds

`stage=enrich` · `active=False` · `priority=18`

**1. Purpose.** Key-backed enrichment providers used ACROSS stages (not a standalone pipeline).

**2. Input schema (input_types).** `domain, ip, email, asn`

**3. Output schema (output_types).** `service, subdomain, tag, finding`

**Canonical dedupe keys.**
- `service` → `svc:{host}:{port}/{proto}`
- `subdomain` → `domain:{lower_fqdn}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `1, 2, 3, 12`

**5. Tool families.** shodan_api, censys_api, securitytrails_api, whoisxml, ipinfo_api, hunter_api, greynoise_api, intelx_api

**6. Priority order.** `18` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_entity_from_feed

**8. Failure handling.**
- failure_modes: `auth_error, quota_exhausted, empty`
- retry_policy: `max_attempts=3; backoff=exp_jitter; retry_on=[429, 500, 502, 503, 504, 'timeout']`
- quota_policy: `unit=credit; per_minute=10; concurrency=2; budget_per_run=200`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `(routed to typed tables by output)` · raw artifacts: `raw/<tool>/`

**10. Operator notes.** Provider layer behind cats 1/2/3/12; budget-ledger metered.


---

## 18. Massive Living Indexes

`stage=resource` · `active=False` · `priority=95`

**1. Purpose.** Reference indexes/awesome-lists for tool discovery - NOT executed in a scan.

**2. Input schema (input_types).** `—`

**3. Output schema (output_types).** `—`

**Canonical dedupe keys.**
- (none — resource/engine category)

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `—`

**5. Tool families.** osint_framework, awesome_osint, hacktricks, payloadsallthethings

**6. Priority order.** `95` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** —

**8. Failure handling.**
- failure_modes: `not_applicable`
- retry_policy: `max_attempts=1; backoff=none; retry_on=[]`
- quota_policy: `unit=none; per_minute=0; concurrency=8; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `(none)` · raw artifacts: `(none)`

**10. Operator notes.** Curation/discovery references; surfaced in docs, never network-executed.


---

## 19. Common Recon Workflows

`stage=engine` · `active=False` · `priority=1`

**1. Purpose.** Named presets that compose stages A-F into one-command flows.

**2. Input schema (input_types).** `domain`

**3. Output schema (output_types).** `subdomain, live_host, finding`

**Canonical dedupe keys.**
- (none — resource/engine category)

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `1, 2, 3, 5, 6, 21, 27`

**5. Tool families.** preset_passive, preset_full, preset_continuous

**6. Priority order.** `1` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** —

**8. Failure handling.**
- failure_modes: `config_error`
- retry_policy: `max_attempts=1; backoff=none; retry_on=[]`
- quota_policy: `unit=none; per_minute=0; concurrency=8; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `(composes other categories)` · raw artifacts: `(n/a)`

**10. Operator notes.** Not tools - presets/profiles that select+order categories (maps to CLI profiles + --category).


---

## 20. Content & Directory Discovery

`stage=deep` · `active=True` · `priority=60`

**1. Purpose.** Brute-force hidden paths/files on live hosts with 404/wildcard calibration.

**2. Input schema (input_types).** `live_host, url`

**3. Output schema (output_types).** `url, endpoint`

**Canonical dedupe keys.**
- `url` → `url:{canonical_sorted_params_no_frag}`
- `endpoint` → `ep:{host}:{method}:{path}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `22, 23, 25, 27`

**5. Tool families.** pydirb, ffuf, feroxbuster, dirsearch, kiterunner

**6. Priority order.** `60` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_path, new_endpoint

**8. Failure handling.**
- failure_modes: `soft_404, waf_block, timeout, oversize_wordlist`
- retry_policy: `max_attempts=2; backoff=exp; retry_on=['timeout', 'conn_reset']`
- quota_policy: `unit=request; per_minute=600; concurrency=20; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `endpoint(url,status,risk_class)` · raw artifacts: `raw/<tool>/`

**10. Operator notes.** Wordlist from cat 28 + harvested paths (cat 6/11). Calibrate per host; no bypass.


---

## 21. Port Scanning & Service Detect

`stage=network` · `active=True` · `priority=50`

**1. Purpose.** Discover open ports/services on in-scope IPs (fast sweep -> deep version detect).

**2. Input schema (input_types).** `ip, cidr, subdomain`

**3. Output schema (output_types).** `service, host_port`

**Canonical dedupe keys.**
- `service` → `svc:{host}:{port}/{proto}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `5, 12, 24`

**5. Tool families.** naabu, nmap, masscan, rustscan, fingerprintx

**6. Priority order.** `50` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** web_port_for_httpx

**8. Failure handling.**
- failure_modes: `timeout, host_down, filtered, conn_reset`
- retry_policy: `max_attempts=2; backoff=exp; retry_on=['timeout', 'conn_reset']`
- quota_policy: `unit=request; per_minute=600; concurrency=20; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `service(port,product,version,banner)` · raw artifacts: `raw/<tool>/`

**10. Operator notes.** naabu fast -> nmap -sV on found ports. Skip CDN edge ranges (cat 5 tag). Web ports feed httpx.


---

## 22. JavaScript Analysis & Secrets

`stage=deep` · `active=False` · `priority=58`

**1. Purpose.** Mine JS for endpoints, frames, websockets, source maps, and secret-like strings.

**2. Input schema (input_types).** `js_file, url, live_host`

**3. Output schema (output_types).** `endpoint, finding, frame, websocket, source_map`

**Canonical dedupe keys.**
- `endpoint` → `ep:{host}:{method}:{path}`
- `finding` → `finding:{asset}:{detector}:{signature}`
- `source_map` → `smap:{sha256}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `23, 25, 27`

**5. Tool families.** pycrawl, jsluice, linkfinder, secretfinder, getjs, retire_js

**6. Priority order.** `58` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_endpoint, new_host_in_js, source_map_found

**8. Failure handling.**
- failure_modes: `fetch_fail, parse_error, empty`
- retry_policy: `max_attempts=2; backoff=exp; retry_on=['5xx', 'timeout']`
- quota_policy: `unit=request; per_minute=30; concurrency=4; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `endpoint+finding(secret,REDACTED)+source_map+frame+websocket` · raw artifacts: `js/<host>/`

**10. Operator notes.** Source maps recover original sources -> richer endpoints. Secrets redacted. Operates on harvested JS (cat 6) + crawled JS.


---

## 23. API & GraphQL Recon

`stage=deep` · `active=True` · `priority=62`

**1. Purpose.** Discover API specs (OpenAPI/Swagger), GraphQL engines/introspection, and API routes.

**2. Input schema (input_types).** `live_host, url, endpoint`

**3. Output schema (output_types).** `endpoint, param, finding`

**Canonical dedupe keys.**
- `endpoint` → `ep:{host}:{method}:{path}`
- `param` → `param:{endpoint}:{name}`
- `finding` → `finding:{asset}:{detector}:{signature}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `25, 27`

**5. Tool families.** graphw00f, clairvoyance, kiterunner, swaggerhole, arjun

**6. Priority order.** `62` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_api_endpoint, new_param

**8. Failure handling.**
- failure_modes: `auth_required, introspection_disabled, timeout`
- retry_policy: `max_attempts=2; backoff=exp; retry_on=['timeout', 'conn_reset']`
- quota_policy: `unit=request; per_minute=600; concurrency=20; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `endpoint(api)+param+finding(exposed_spec/introspection)` · raw artifacts: `raw/<tool>/`

**10. Operator notes.** Read specs only; GraphQL introspection read (no mutation/exploit). Probe /openapi.json /graphql /v3/api-docs.


---

## 24. TLS/SSL & Certificate Analysis

`stage=validate` · `active=True` · `priority=56`

**1. Purpose.** Grab live certs (SAN pivots) and audit TLS config; pivot certs->hosts.

**2. Input schema (input_types).** `live_host, ip, service`

**3. Output schema (output_types).** `cert, subdomain, finding`

**Canonical dedupe keys.**
- `cert` → `cert:{sha256_fingerprint}`
- `subdomain` → `domain:{lower_fqdn}`
- `finding` → `finding:{asset}:{detector}:{signature}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `2, 27`

**5. Tool families.** tlsx, sslyze, testssl, cero

**6. Priority order.** `56` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_cert_san, cert_pivot_host

**8. Failure handling.**
- failure_modes: `tls_handshake_fail, timeout, self_signed`
- retry_policy: `max_attempts=2; backoff=exp; retry_on=['timeout', 'conn_reset']`
- quota_policy: `unit=request; per_minute=600; concurrency=20; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `asset(cert)+service.tls+edge(serves_cert,covers)+finding(tls)` · raw artifacts: `raw/<tool>/`

**10. Operator notes.** tlsx SANs + cero (cert scrape of IP ranges) -> NEW subdomains re-enter cat 2 (recursion).


---

## 25. Parameter Discovery & Fuzz Prep

`stage=deep` · `active=True` · `priority=64`

**1. Purpose.** Mine parameters from URLs/forms/JS/specs/archives; prep tuned fuzz inputs.

**2. Input schema (input_types).** `url, endpoint, js_file, live_host`

**3. Output schema (output_types).** `param, endpoint, wordlist`

**Canonical dedupe keys.**
- `param` → `param:{endpoint}:{name}`
- `endpoint` → `ep:{host}:{method}:{path}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `27`

**5. Tool families.** paramspider, arjun, x8, param_miner, gf, qsreplace

**6. Priority order.** `64` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_param, new_path_pattern

**8. Failure handling.**
- failure_modes: `timeout, empty, waf_block`
- retry_policy: `max_attempts=2; backoff=exp; retry_on=['timeout', 'conn_reset']`
- quota_policy: `unit=request; per_minute=600; concurrency=20; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `endpoint.params[]+wordlist(tuned)` · raw artifacts: `raw/<tool>/; wordlists/`

**10. Operator notes.** Emits tuned wordlists + regex packs from learned params/paths (feeds cat 20/28). Recon scope only, no exploitation.


---

## 26. Mobile / APK Recon

`stage=deep` · `active=False` · `priority=66`

**1. Purpose.** Extract endpoints/secrets/hosts from mobile app packages (scope-dependent).

**2. Input schema (input_types).** `apk, package_id, url`

**3. Output schema (output_types).** `endpoint, finding, subdomain`

**Canonical dedupe keys.**
- `endpoint` → `ep:{host}:{method}:{path}`
- `finding` → `finding:{asset}:{detector}:{signature}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `2, 22, 23`

**5. Tool families.** apkleaks, apkurlgrep, mobsf, apktool

**6. Priority order.** `66` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_host_in_apk, new_endpoint

**8. Failure handling.**
- failure_modes: `download_fail, decompile_error, empty`
- retry_policy: `max_attempts=1; backoff=none; retry_on=[]`
- quota_policy: `unit=none; per_minute=0; concurrency=8; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `endpoint+finding(secret,REDACTED)+subdomain` · raw artifacts: `apks/<sha256>/`

**10. Operator notes.** Enable when mobile apps are in scope; discovered hosts re-enter cat 2.


---

## 27. Active Vulnerability Detection

`stage=detect` · `active=True` · `priority=70`

**1. Purpose.** Signature-based detection of CVEs/misconfig/exposure/takeover on VALIDATED live assets (NO exploitation).

**2. Input schema (input_types).** `live_host, url, service, cert, endpoint`

**3. Output schema (output_types).** `finding`

**Canonical dedupe keys.**
- `finding` → `finding:{asset}:{detector}:{signature}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `12`

**5. Tool families.** nuclei, subjack, tko_subs, sslyze, nuclei_templates

**6. Priority order.** `70` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** —

**8. Failure handling.**
- failure_modes: `timeout, waf_block, template_error, false_positive`
- retry_policy: `max_attempts=2; backoff=exp; retry_on=['timeout', 'conn_reset']`
- quota_policy: `unit=request; per_minute=600; concurrency=20; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `finding(severity,detector,cve,evidence_ref)` · raw artifacts: `raw/<tool>/`

**10. Operator notes.** Detection only; runs ONLY on validated live assets. Templated/auditable; correlate with cat 12 (EPSS/CVSS rank).


---

## 28. Wordlists & Recon Resources

`stage=resource` · `active=False` · `priority=90`

**1. Purpose.** Provide/generate wordlists + regex packs (static curated + dynamically tuned from learnings).

**2. Input schema (input_types).** `tech, endpoint, param, path_pattern`

**3. Output schema (output_types).** `wordlist, regex_pack`

**Canonical dedupe keys.**
- `wordlist` → `wl:{name}:{sha256}`
- `regex_pack` → `rx:{name}:{sha256}`

**Provenance fields.** `source, provider, fetched_at, observed_at, request_url, response_sha256, quota_cost, source_confidence`

**4. Chaining rules (chain_to).** → categories `20, 23, 25`

**5. Tool families.** seclists, assetnote_wordlists, commonspeak2, tuned_generator

**6. Priority order.** `90` (lower = earlier; cheapest high-signal first)

**7. Recursion logic (recursion_triggers).** new_tech, new_path_corpus

**8. Failure handling.**
- failure_modes: `missing_wordlist_dir, empty_corpus`
- retry_policy: `max_attempts=1; backoff=none; retry_on=[]`
- quota_policy: `unit=none; per_minute=0; concurrency=8; budget_per_run=0`
- on exhausted quota: **defer** (planner substitutes); on repeated failures: **circuit-breaker OPEN** (fail fast); unresolved → **dead-letter**.

**9. Storage mapping.** entities: `wordlist+regex_pack (hashed)` · raw artifacts: `wordlists/; regex_packs/`

**10. Operator notes.** Selects tech-specific lists from detected tech (cat 5) and MERGES harvested paths/params (cat 6/11/25). Tuned lists feed cat 20/23/25.
