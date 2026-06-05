# Tool Catalog — Capability, Invocation & Output

This is the human-readable companion to `config/tools.yaml` (the machine-readable
registry the orchestrator actually reads). For each tool: **what it does**, **how it's
invoked**, **what it consumes**, and **what it outputs** (with a sample).

> Categories 1 & 2 (our Wave-1 starting point) are documented in full operational detail.
> Other categories list the key tools; see `config/tools.yaml` for every field and
> `docs/pipeline/03-category-pipelines.md` for how they chain.

**Contract fields** (from `tools.yaml`): `input` / `output` (artifact types),
`integration` (cli/api/python/dataset), `requires_key`, `default_on`, `chains_to`.

---

## CATEGORY 1 — Internet-Wide Search & Asset Discovery `[PASSIVE]`

### uncover ★  (the Cat-1 entrypoint)
- **Capability:** single query across Shodan, Censys, FOFA, ZoomEye, Netlas. One call,
  five engines.
- **Invoke (CLI):** `uncover -q "ssl:example.com" -json` (also `-shodan`, `-censys`, ...)
- **Input:** `domain` / search dork → **Output:** `host:port` (ip+port lines)
- **Sample out:** `{"ip":"93.184.216.34","port":443,"host":"example.com","source":"shodan"}`
- **Keys:** reads `SHODAN_API_KEY`, `CENSYS_*`, `FOFA_*` from env if present.
- **Chains to:** Cat 3 (ASN from IPs), Cat 21 (port verify), Cat 5 (httpx).

### shodan
- **Capability:** exposed services, banners, ports, CVE hints per host — no scanning.
- **Invoke (API):** `GET /shodan/host/search?key=…&query=hostname:{domain}` ; per-IP
  `GET /shodan/host/{ip}`.
- **Input:** `domain`/`ip` → **Output:** `service` (port, product, version, banner, CVE list)
- **Sample out:** `{"ip_str":"…","ports":[80,443],"data":[{"product":"nginx","version":"1.18"}]}`
- **Free tier:** `internetdb` (below) needs no credits.

### internetdb ★  (free Shodan)
- **Capability:** ports + CVEs + hostnames per IP, **no API credits**.
- **Invoke (API):** `GET https://internetdb.shodan.io/{ip}`
- **Input:** `ip` → **Output:** `service` + cve hints
- **Sample out:** `{"ip":"1.2.3.4","ports":[22,443],"vulns":["CVE-2021-1234"],"hostnames":[…]}`

### censys
- **Capability:** best TLS/certificate analytics; SANs reveal new subdomains.
- **Invoke (API):** `POST /api/v2/hosts/search` ; `/certificates/search`
- **Input:** `domain` → **Output:** `cert` (+ SAN→`subdomain`), `service`
- **Chains to:** Cat 2 (SAN subdomains), Cat 24 (cert pivot).

### netlas / leakix / fullhunt / criminalip / urlscan
- **netlas:** modern Shodan/Censys alt — `service`/`dns`. `GET /api/responses/?q={domain}`.
- **leakix:** exposed services + leaks → `finding`. `GET /host/{ip}`.
- **fullhunt:** ASM — `subdomain`/`host`/`tech`. `GET /api/v1/domain/{domain}/details`.
- **criminalip:** exposure intel → `service`. `GET /v1/asset/domain/report?query={domain}`.
- **urlscan ★:** web fingerprint, JS, related infra → `url`. `GET /api/v1/search/?q=domain:{domain}`.
  Use **unlisted/private** submissions during live engagements (OPSEC).

### greynoise ★ (enrichment overlay, not discovery)
- **Capability:** is this IP a mass-internet-scanner? Suppresses noise.
- **Invoke (API):** `GET /v3/community/{ip}`
- **Input:** `ip` → **Output:** `tag` (`mass_scanner`) — **adds no new assets**.

---

## CATEGORY 2 — Passive DNS & Subdomain Enumeration `[PASSIVE → ACTIVE]`

### subfinder ★ (primary passive aggregator)
- **Capability:** subdomains from 30+ passive sources in one tool (uses your provider keys).
- **Invoke (CLI):** `subfinder -d {domain} -silent -all -json`
- **Input:** `domain` → **Output:** `subdomain` (jsonl `{host, source}`)
- **Sample out:** `{"host":"api.example.com","source":"crtsh"}`
- **Keys:** optional, in `~/.config/subfinder/provider-config.yaml`.

### crtsh ★ (certificate transparency)
- **Capability:** subdomains from CT logs — authoritative (confidence 0.9).
- **Invoke (API):** `GET https://crt.sh/?q=%25.{domain}&output=json`
- **Input:** `domain` → **Output:** `subdomain`, `cert`
- **Sample out:** `[{"name_value":"api.example.com\nwww.example.com","issuer_name":"…"}]`
- **Caveat:** flaky uptime → cache 6–24h.

### certspotter ★ / chaos / securitytrails / virustotal
- **certspotter:** CT monitoring (great for **continuous** new-cert alerts).
  `GET /v1/issuances?domain={domain}&include_subdomains=true&expand=dns_names`.
- **chaos:** ProjectDiscovery bug-bounty dataset. `GET /dns/{domain}/subdomains` (key).
- **securitytrails:** best paid passive DNS + history. `GET /v1/domain/{domain}/subdomains` (key).
- **virustotal:** passive DNS subdomains; **free tier 4 req/min** → throttle hard.

### hackertarget ★ / alienvault_otx ★ (keyless)
- **hackertarget:** `GET /hostsearch/?q={domain}` → CSV `subdomain,ip` pairs (daily quota).
- **alienvault_otx:** `GET /api/v1/indicators/domain/{domain}/passive_dns` → `subdomain`+`ip`.

### alterx (permutation)
- **Capability:** generate likely subdomain permutations (modern AltDNS).
- **Invoke (CLI):** `alterx -l subs.txt -o candidates.txt`
- **Input:** `subdomain` → **Output:** `subdomain` *candidates* — **must be resolved next**.

### dnsx ★ (resolve/validate) `[ACTIVE]`
- **Capability:** fast DNS resolution + record probing.
- **Invoke (CLI):** `dnsx -l subs.txt -json -a -aaaa -cname -resp`
- **Input:** `subdomain` → **Output:** `ip` (A/AAAA → `resolves_to`; CNAME → `cname_to`)
- **Sample out:** `{"host":"api.example.com","a":["1.2.3.4"],"cname":["x.cloudfront.net"]}`
- **Chains to:** Cat 21 (port scan), Cat 24 (takeover via dangling cname).

### puredns + massdns + dnsvalidator (mass resolve + wildcard filter) `[ACTIVE]`
- **dnsvalidator:** build a clean resolver list → `config/resolvers.txt`.
- **puredns:** `puredns resolve subs.txt -r resolvers.txt --write live.txt` — orchestrates
  massdns; **wildcard filtering** is the killer feature (kills false positives).
- **Input:** `subdomain` (+candidates) → **Output:** resolving `subdomain` + `ip`.

### tlsx (cert SANs → subdomains) `[ACTIVE]`  *(also Cat 24)*
- **Invoke:** `tlsx -l hosts.txt -json -san -cn -so`
- **Input:** `host:port` → **Output:** `subdomain` (SANs/CN from live certs) — loops to Cat 2.

---

## CATEGORY 3 — WHOIS / ASN / BGP `[PASSIVE]`

| Tool | Invoke | In → Out |
|------|--------|----------|
| **asnmap ★** | `asnmap -d {domain} -json` | domain/org → `cidr` |
| **bgpview** | `GET /asn/{asn}/prefixes` | asn → `cidr` |
| **ripestat** | `GET /data/announced-prefixes/data.json?resource={asn}` | asn → `cidr` |
| **ipinfo** | `GET /{ip}?token={key}` | ip → `asn`/org/geo |
| **metabigor** | `echo {org} \| metabigor net --org` | org → `cidr` (no key!) |
| **mapcidr** | `mapcidr -cidr {cidr}` | cidr → `ip[]` |

---

## CATEGORY 4 — Dorking & URL Recon `[PASSIVE]`

| Tool | Invoke | In → Out |
|------|--------|----------|
| **gau ★** | `gau {domain} --json` | domain → `url` (wayback+cc+otx+urlscan) |
| **waybackurls** | `waybackurls {domain}` | domain → `url` |
| **gf** | `cat urls \| gf ssrf` | url → `url` (pattern-matched) |
| **unfurl** | `cat urls \| unfurl domains` | url → parts |
| **paramspider** | `paramspider -d {domain}` | domain → `url` w/ params |

---

## CATEGORY 5 — Web Tech Fingerprinting + Probing `[ACTIVE]`

### httpx ★ (the active hub)
- **Capability:** liveness + status, title, tech, TLS, CDN, IP, CNAME, content hash, server.
- **Invoke:** `httpx -l hosts.txt -json -sc -title -tech-detect -tls-grab -cdn -ip -cname -hash sha256`
- **Input:** `subdomain` → **Output:** live `url` + `service` + tech tags
- **Sample out:** `{"url":"https://api.example.com","status_code":200,"tech":["nginx","React"],"webserver":"nginx"}`
- **Chains to:** Cat 13 (screenshot), 20 (content disc.), 22 (JS), 27 (nuclei).

Others: **whatweb** (`--log-json`), **wafw00f** (WAF→rate tuning), **cdncheck** (flag CDN).

---

## CATEGORY 6 — Historical & Archive `[PASSIVE]`

| Tool | Invoke | In → Out |
|------|--------|----------|
| **gau ★** | `gau {domain}` | domain → `url` |
| **waymore** | `waymore -i {domain} -mode U` | domain → `url` (+ downloads responses) |
| **wayback_cdx ★** | `GET /cdx/search/cdx?url=*.{domain}/*` | domain → `url` (+ downloads `.js` → `artifacts/js/`) |

---

## CATEGORIES 9–13 (key tools)

| Cat | Tool | Invoke | In → Out |
|-----|------|--------|----------|
| 9 | **gitleaks** | `gitleaks detect --source {repo} --report-format json` | repo → `finding(secret, redacted)` |
| 9 | **trufflehog** | `trufflehog filesystem {repo} --json` | repo → `finding(secret)` |
| 9 | **github_search** | `GET /search/code?q={dork}+org:{org}` | org → `repo` |
| 10 | **grayhatwarfare** | `GET /api/v2/buckets?keywords={kw}` | keyword → `bucket` |
| 10 | **cloud_enum** | `cloud_enum -k {kw}` | keyword → `bucket` |
| 12 | **nvd** | `GET /rest/json/cves/2.0?cpeName={cpe}` | cpe → `finding(cve)` |
| 12 | **epss ★** | `GET /data/v1/epss?cve={cve}` | cve → exploit-prob |
| 13 | **gowitness** | `gowitness scan file -f hosts.txt` | url → `screenshot` |

---

## NEW CATEGORIES 20–25 (active recon additions)

| Cat | Tool | Invoke | In → Out |
|-----|------|--------|----------|
| 20 | **ffuf** | `ffuf -u {url}/FUZZ -w {wl} -of json` | url+wordlist → `url` (paths) |
| 20 | **feroxbuster** | `feroxbuster -u {url} -w {wl} --json` | url → `url` |
| 21 | **naabu ★** | `naabu -list ips.txt -top-ports 1000 -json` | ip → `host:port` |
| 21 | **nmap** | `nmap -sV -sC -p {ports} -oX out.xml {host}` | host:port → `service` |
| 21 | **masscan** | `masscan {cidr} -p{ports} --rate {r} -oJ` | cidr → `host:port` |
| 22 | **katana** | `katana -list urls.txt -jc -js-crawl -json` | url → `url` + `js_file` |
| 22 | **jsluice** | `jsluice urls {js_file}` | js_file → `url`/secret |
| 22 | **secretfinder** | `SecretFinder.py -i {js} -o cli` | js_file → `finding(secret)` |
| 23 | **graphw00f** | `graphw00f -d -f -t {url}` | url → graphql `finding` |
| 23 | **kiterunner** | `kr scan urls.txt -w routes.kite -o json` | url → `url` (api routes) |
| 24 | **tlsx ★** | `tlsx -l hosts.txt -json -san` | host:port → `subdomain`(SAN) |
| 24 | **sslyze** | `sslyze --json_out out.json {host}` | host:port → `finding(tls)` |
| 24 | **cero** | `cero {ips}` | ip → `subdomain` (cert scrape) |
| 27 | **nuclei ★** | `nuclei -l urls.txt -jsonl -severity {sev}` | url → `finding` |
| 27 | **subjack** | `subjack -w subs.txt -ssl` | subdomain → `finding(takeover)` |

---

## UTILITY / GLUE

| Tool | Purpose | Invoke |
|------|---------|--------|
| **anew** | append-only dedupe (incremental pipelines) | `cat new \| anew all.txt` |
| **notify** | alert sink (slack/discord/telegram) | `cat findings \| notify` |
| **interactsh-client** | OOB/OAST infra for blind detection | `interactsh-client -json` |

---

## How adapters use this catalog

For **API** tools, the Python adapter calls the endpoint via the shared `HttpClient`
(rate-limited + proxy-rotated). For **CLI** tools, the adapter shells out using the
`invocation` template, writing `{infile}`/reading stdout, and parses `output_format`.
Either way the adapter emits normalized `Event`s (see `recontool/adapters/base.py`) that
the normalization engine dedupes into the DB. Adding a new tool = add a registry entry +
a thin adapter + a parser + an atomic test (see `docs/pipeline/02-plan-of-action.md` §4).
