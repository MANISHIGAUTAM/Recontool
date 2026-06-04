# D5 — API Integration Spec (Top 30 Integrations)

For each integration: **auth**, **transport** (REST API / CLI / dataset), **rate
limits** (real-world, verify against current docs before launch), **output format**,
and **normalization notes** (how it maps to the D3 schema). Rate limits change — treat
these as starting defaults and load actual limits from each provider's current
documentation.

**Adapter contract (all 30 follow this):**
```
input:  {seed, scope, profile, api_key_ref}
run:    REST call OR `docker run pinned-image <args>`
output: raw blob → MinIO ; normalized events → normalization engine
emits:  asset_source rows + audit_log row (egress_ip, rate_profile, ts)
```

Legend: **RL** = rate limit; **norm** = normalization target entity.

---

### Group A — Passive DNS / Subdomain / CT (CAT-2)

**1. subfinder** (CLI)
- Auth: none itself; reads provider keys from `provider-config.yaml`.
- Transport: `subfinder -d <domain> -oJ` (JSON lines).
- RL: governed by each upstream source's key; subfinder respects per-source limits.
- Output: JSONL `{host, source}`.
- Norm: → `asset(type=subdomain)`, one `asset_source` per `source` field.

**2. crt.sh** (HTTP / Postgres)
- Auth: none.
- Transport: `https://crt.sh/?q=%25.<domain>&output=json` OR direct Postgres
  (`postgres://guest@crt.sh/certwatch`) for speed/reliability.
- RL: no formal limit but **frequently flaky** — cache 6–24h, retry w/ backoff.
- Output: JSON cert records (`name_value` contains SANs, newline-separated).
- Norm: split SANs → `asset(type=subdomain)`; cert → `asset(type=cert)` +
  `COVERS` edges; source_confidence high (0.9, authoritative CT).

**3. CertSpotter** (REST)
- Auth: optional API token (higher limits).
- Transport: `GET api.certspotter.com/v1/issuances?domain=<d>&include_subdomains=true`.
- RL: free tier limited per hour; token raises it. Ideal for **continuous CT monitoring**.
- Output: JSON issuances with `dns_names[]`.
- Norm: `dns_names` → subdomains; great for diff/alert on *new* certs.

**4. SecurityTrails** (REST, paid)
- Auth: `APIKEY` header.
- Transport: `GET /v1/domain/<d>/subdomains`, `/v1/history/<d>/dns/a`,
  `/v1/domain/<d>/associated` (reverse-whois).
- RL: tier-based monthly query quota; throttle to plan.
- Output: JSON.
- Norm: subdomains + **historical** A records → `asset_state` history; associated →
  related domains. source_confidence 0.8.

**5. VirusTotal** (REST)
- Auth: `x-apikey` header.
- Transport: `GET /api/v3/domains/<d>/subdomains`, `/resolutions`.
- RL: **free = 4 req/min, 500/day** — hard throttle; premium lifts it.
- Output: JSON, paginated cursors.
- Norm: subdomains + passive-DNS resolutions → subdomains + `RESOLVES_TO` edges.

**6. Chaos (ProjectDiscovery)** (REST/CLI)
- Auth: `Authorization` API key (free).
- Transport: `chaos -d <domain>` or REST index.
- RL: generous free; respect documented caps.
- Output: JSON host list.
- Norm: → subdomains; source_confidence 0.7.

**7. dnsx** (CLI) — *active resolution*
- Auth: none.
- Transport: `dnsx -json -a -aaaa -cname -resp` over a host list.
- RL: governed by resolver list + our rate profile (active).
- Output: JSONL with records.
- Norm: A/AAAA → `RESOLVES_TO` IP assets; CNAME → `CNAME_TO` edges (takeover input).

**8. puredns + massdns** (CLI) — *active resolution + wildcard filter*
- Auth: none. Needs validated resolvers (`dnsvalidator`).
- Transport: `puredns resolve hosts.txt -r resolvers.txt`.
- RL: high-throughput; throttle via profile; **stealth profile lowers QPS**.
- Output: resolved host list + wildcard root detection.
- Norm: confirmed-live subdomains (`is_live` candidate), drop wildcard false-positives.

---

### Group B — Internet Search Engines (CAT-1)

**9. Shodan** (REST/CLI)
- Auth: `key` query param / `SHODAN_API_KEY`.
- Transport: `GET /shodan/host/<ip>`, `/shodan/host/search?query=`; **InternetDB**
  `https://internetdb.shodan.io/<ip>` is **free, no credits**.
- RL: 1 req/sec baseline; search consumes **query credits**; InternetDB unmetered.
- Output: JSON (ports, banners, CVEs, hostnames).
- Norm: ports→`service`, CVEs→`finding(kind=cve)` candidates, hostnames→subdomains.
  Use InternetDB for cheap bulk port/CVE enrichment.

**10. Censys** (REST v2)
- Auth: API ID + secret (HTTP basic).
- Transport: `POST /api/v2/hosts/search`, `/certificates/search`.
- RL: monthly query quota by plan; paginate via cursor.
- Output: JSON hosts/services/certs.
- Norm: services→`service`, certs→cert assets + `COVERS` edges. Strong for cert pivots.

**11. Netlas** (REST)
- Auth: `X-API-Key`.
- Transport: `GET /api/responses/?q=`, `/api/domains/`.
- RL: free tier daily request cap.
- Output: JSON.
- Norm: hosts/services/domains; good Shodan/Censys fallback when credits exhausted.

**12. GreyNoise** (REST) — *enrichment overlay*
- Auth: `key` header.
- Transport: `GET /v3/community/<ip>` (community free) / RIOT / context endpoints.
- RL: community endpoint generous; enterprise context paid.
- Output: JSON `{noise, riot, classification}`.
- Norm: **tags only** — `tags+=['mass_scanner']` on IP assets; suppress noise in
  findings. Never creates assets.

**13. LeakIX** (REST)
- Auth: `api-key` header.
- Transport: `GET /host/<ip>`, `/domain/<d>`.
- RL: free tier limited; paid lifts.
- Output: JSON services + leak events.
- Norm: services→`service`; leak events→`finding(kind=exposure)`.

---

### Group C — WHOIS / ASN / BGP / IP (CAT-3)

**14. BGPView** (REST)
- Auth: none.
- Transport: `GET /asn/<n>/prefixes`, `/ip/<ip>`, `/search?query=<org>`.
- RL: be polite (no hard public number) — cache + backoff.
- Output: JSON prefixes/peers/org.
- Norm: ASN→CIDR `asset(type=cidr)` + `ANNOUNCED_BY`/`OWNED_BY` edges.

**15. RIPEstat** (REST)
- Auth: none.
- Transport: `GET /data/announced-prefixes/data.json?resource=AS<n>`,
  `/data/whois/data.json`.
- RL: fair-use; cache.
- Output: JSON data objects.
- Norm: prefixes, holders → CIDR/org assets + edges. source_confidence 0.85.

**16. ASNmap** (CLI)
- Auth: none (ProjectDiscovery).
- Transport: `asnmap -a AS<n> -json` / by org/IP/domain.
- RL: n/a (local + light upstream).
- Output: JSONL CIDRs.
- Norm: CIDRs feed Phase-4 port scanning targets.

**17. IPinfo** (REST)
- Auth: token.
- Transport: `GET /<ip>?token=`, batch endpoint for bulk.
- RL: free 50k/mo; paid scales.
- Output: JSON `{asn, org, geo, company, privacy}`.
- Norm: IP enrichment → `asset.attributes` (asn, org, geo, is_hosting/vpn/proxy tags).

**18. Team Cymru** (DNS/WHOIS bulk)
- Auth: none.
- Transport: bulk `whois -h whois.cymru.com` / DNS TXT origin lookup.
- RL: bulk-friendly (designed for it).
- Output: text `AS | IP | prefix | country | registry | ASname`.
- Norm: fast bulk IP→ASN mapping for large CIDR sets.

---

### Group D — Active Probing / Fingerprint / Visual (CAT-5)

**19. httpx** (CLI) — *active hub*
- Auth: none.
- Transport: `httpx -json -sc -title -tech-detect -tls-grab -cdn -ip -cname -hash`.
- RL: our rate profile (concurrency/QPS).
- Output: JSONL per URL.
- Norm: → live `endpoint`/`service`; sets `is_live=true`; `tech[]`; CDN/WAF tags;
  TLS into `service.tls`; content hash → change detection. **Highest-value adapter.**

**20. naabu** (CLI) — *active port scan*
- Auth: none.
- Transport: `naabu -host <h> -top-ports 1000 -json` (SYN where capable, else CONNECT).
- RL: profile-controlled scan rate (stealth = slow + fewer ports).
- Output: JSONL `{host, port}`.
- Norm: open ports → `service` rows; feeds Nmap.

**21. Nmap** (CLI) — *active deep scan*
- Auth: none.
- Transport: `nmap -sV -sC -p <naabu_ports> -oX` on **only** naabu-found ports.
- RL: timing template tied to profile (`-T2` stealth … `-T4` aggressive).
- Output: XML.
- Norm: product/version/banner → enrich `service`; CPE → CVE-correlation input.

**22. nuclei** (CLI/API) — *active detection*
- Auth: optional template-store auth.
- Transport: `nuclei -l urls.txt -json -severity ... -tags ...`.
- RL: rate-limit flags per profile; template tags scope what runs.
- Output: JSONL findings with template-id, matched-at, severity, evidence.
- Norm: → `finding`; `detector='nuclei:<template-id>'`; evidence → MinIO;
  dedupe by (endpoint, template-id).

**23. gowitness** (CLI) — *active screenshots*
- Auth: none.
- Transport: `gowitness scan file -f urls.txt --write-db` (headless Chrome).
- RL: concurrency by profile.
- Output: PNGs + SQLite/DB metadata.
- Norm: screenshot → MinIO; link to `endpoint.evidence_ref`.

**24. sslyze** (CLI) — *active TLS analysis*
- Auth: none.
- Transport: `sslyze --json_out <host:443>`.
- RL: light, per profile.
- Output: JSON cipher/cert/protocol analysis.
- Norm: weak ciphers/expired/self-signed → `finding(kind=tls)`; cert → cert asset.

---

### Group E — URL / JS / Secrets / Code (CAT-4, CAT-9)

**25. gau** (CLI) — *passive URL aggregation*
- Auth: optional keys for some sources (OTX, URLScan).
- Transport: `gau <domain> --json` (pulls Wayback+CommonCrawl+OTX+URLScan).
- RL: upstream archive limits; cache.
- Output: JSONL URLs.
- Norm: → `endpoint` (unverified; `source='gau'`); later httpx-verified.

**26. katana** (CLI) — *active crawl*
- Auth: none.
- Transport: `katana -u <url> -jc -js-crawl -json -depth N`.
- RL: profile-controlled crawl rate/depth.
- Output: JSONL endpoints + discovered JS.
- Norm: → `endpoint`; new hosts in JS → loop back to httpx (Phase-4 verify).

**27. GitHub Code Search** (REST)
- Auth: GitHub PAT (token rotation pool).
- Transport: `GET /search/code?q=<dork>+org:<org>`.
- RL: **30 req/min authenticated for code search**, strict secondary limits — queue +
  rotate tokens + backoff on 403/secondary-limit.
- Output: JSON code matches (repo, path, fragment).
- Norm: candidate repos → clone → GitLeaks/TruffleHog; matches → `finding(kind=secret)`
  with **redacted** preview.

**28. GitLeaks** (CLI) — *passive secret scan*
- Auth: none (scans local clones).
- Transport: `gitleaks detect --report-format json --source <repo>`.
- RL: n/a (local).
- Output: JSON findings (rule, file, line, commit, **secret**).
- Norm: store **hash + masked preview + location only** → `finding(kind=secret)`.
  **Never persist raw secret.**

**29. TruffleHog** (CLI) — *secret scan + optional active verify*
- Auth: none for scan; verification calls third-party APIs.
- Transport: `trufflehog github --org=<o> --json` / `filesystem`.
- RL: verification hits external services — **gate `--only-verified` behind active flag**.
- Output: JSON `{detector, verified, raw(redacted), source}`.
- Norm: verified=true raises finding confidence; cloud-key hits → feed CAT-7 check.

---

### Group F — Vuln Intelligence (CAT-10)

**30. NVD + EPSS** (REST) — *correlation brain*
- Auth: NVD optional API key (strongly recommended — raises throttle); EPSS none.
- Transport: NVD `GET /rest/json/cves/2.0?cpeName=<cpe>`; EPSS
  `GET api.first.org/data/v1/epss?cve=<id>`.
- RL: NVD without key is harshly throttled (a few req/30s); **get a key**. EPSS
  generous.
- Output: JSON CVE metadata (CVSS, CPE) / EPSS probability + percentile.
- Norm: cache into `vuln_ref`; `priority_rank = w1·CVSS + w2·EPSS + w3·exposure +
  w4·asset_value`; link `finding.cve_id`.

---

## Cross-Cutting Integration Rules

| Concern | Rule |
|--------|------|
| **Keys** | All keys live in Vault; adapters receive a *reference*, fetch at runtime, never log the key. Rotation pools for GitHub/Shodan/VT. |
| **Rate limiting** | Redis token bucket per `(provider, egress_ip)`; adapter must `acquire()` before each external call. |
| **Retries** | Temporal activity retry: exp backoff, max attempts per tool; 429/403-secondary → longer backoff + (for GitHub) token rotate. |
| **Caching** | Passive lookups cached in Redis/Postgres with TTL (CT 6–24h, WHOIS 24h, NVD 24h) to cut spend and flakiness. |
| **Raw retention** | Every call's raw response → MinIO with `scan_id/tool` key; `asset_source.raw_ref` points to it. |
| **Output parsing** | Prefer each tool's JSON mode; one parser module per tool with schema/golden-file tests (guards against upstream format drift). |
| **Versioning** | Tool images digest-pinned; API client versions pinned; per-tool smoke test in CI. |
| **Secrets in findings** | Hash + mask + location only. Raw secret never written to DB, logs, or cold storage. |
| **PII/breach (HIBP/Dehashed)** | Separate encrypted store, shortest TTL, legal gate, audit every access. |
