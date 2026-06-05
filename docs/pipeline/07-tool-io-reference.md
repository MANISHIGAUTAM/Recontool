# Tool I/O & Storage Reference

For each tool: **invocation command**, **sample output** (real format), and **storage
mapping** — exactly which DB table/fields (see `D3-data-schema.md`) and which filesystem
artifacts the output becomes.

> Sample outputs are representative/abbreviated and based on each tool's documented JSON
> schema; field names match the tools' current output. Verify against the live tool
> version pinned in `config/tools.yaml` before relying on a field. Content was rephrased
> for compliance with licensing restrictions.

**Storage targets** (recap from `D3-data-schema.md`):
- `asset(type,value,dedupe_key,attributes,tech,tags,confidence,is_live,in_scope)`
- `asset_source(asset_id,tool,source_confidence,raw_ref)`
- `service(asset_id,port,protocol,product,version,banner,tls)`
- `endpoint(asset_id,url,status_code,title,content_hash,params,risk_class,source)`
- `finding(scan_id,asset_value,kind,title,cve_id,severity,priority_rank,detector,evidence_redacted)`
- `edge(src,dst,rel)` — `resolves_to | cname_to | subdomain_of | in_cidr | announced_by | serves_cert`
- Filesystem: `artifacts/<scan_id>/{raw/<tool>/, js/<host>/, screenshots/, bodies/}`

Every adapter also writes `asset_source(raw_ref=…)` pointing at the saved raw output, and
an `audit_log` row (tool, egress_ip, profile, ts). Those are implicit below.

---

# CATEGORY 1 — Internet-Wide Search & Asset Discovery  [PASSIVE]

### uncover  (wraps Shodan/Censys/FOFA/ZoomEye/Netlas)
- **Invoke:** `uncover -q "ssl:acme.com" -json -silent`
- **Sample output (JSONL):**
  ```json
  {"timestamp":"2026-06-05T...","ip":"93.184.216.34","port":443,"host":"acme.com","source":"shodan"}
  ```
- **Store:** `asset(ip)`; `service(asset_id=ip, port)`; if `host` is in-scope → `asset(subdomain)` + `edge(host→ip, resolves_to)`. `asset_source.tool=uncover`. Raw → `raw/uncover/`.

### shodan  (key)
- **Invoke (API):** `GET https://api.shodan.io/shodan/host/search?key=$K&query=hostname:acme.com`
- **Sample output:**
  ```json
  {"matches":[{"ip_str":"93.184.216.34","port":443,"product":"nginx","version":"1.18.0",
   "hostnames":["www.acme.com"],"vulns":["CVE-2021-23017"],"data":"HTTP/1.1 200 OK\r\nServer: nginx"}]}
  ```
- **Store:** `asset(ip)`, `service(port,product,version,banner=data[:500])`, `asset(subdomain)` for in-scope hostnames + `edge(resolves_to)`, `finding(kind=cve,cve_id,severity=medium,detector=shodan)`.

### internetdb  (free, no key, per-IP)
- **Invoke (API):** `GET https://internetdb.shodan.io/93.184.216.34`
- **Sample output:**
  ```json
  {"ip":"93.184.216.34","ports":[80,443],"cpes":["cpe:/a:nginx:nginx"],
   "hostnames":["www.acme.com"],"vulns":["CVE-2021-23017"],"tags":["cdn"]}
  ```
- **Store:** `service(port)` per port; `asset(subdomain)`+`edge(resolves_to)` for hostnames; `finding(kind=cve)` per vuln; `cpes`→ feeds CVE correlation; `tags`→`asset.tags`.

### censys  (key id+secret)
- **Invoke (API):** `POST https://search.censys.io/api/v2/hosts/search` (Basic auth), body `{"q":"acme.com","per_page":100}`
- **Sample output:**
  ```json
  {"result":{"hits":[{"ip":"93.184.216.34",
   "services":[{"port":443,"service_name":"HTTP"}],
   "dns":{"names":["www.acme.com","api.acme.com"]}}]}}
  ```
- **Store:** `asset(ip)`, `service(port,service_name)`, in-scope `dns.names`→`asset(subdomain)`+`edge(resolves_to)`. Censys cert SANs are a key **feedback (⟳)** source for new subdomains.

### netlas (key), leakix (key), fullhunt (key), criminalip (key)
- **netlas:** `GET app.netlas.io/api/domains/?q=domain:*.acme.com` → `items[].data.domain` → `asset(subdomain)`.
- **leakix:** `GET leakix.net/domain/acme.com` (header `api-key`) → `Services[]`→`service`; `Leaks[]`→`finding(kind=exposure)`.
- **fullhunt:** `GET fullhunt.io/api/v1/domain/acme.com/subdomains` (header `X-API-KEY`) → `hosts[]`→`asset(subdomain)`.
- **criminalip:** `GET api.criminalip.io/v1/asset/domain/report?query=acme.com` → connected IPs→`asset(ip)`.

### urlscan  (keyless search; on-target filtered)
- **Invoke (API):** `GET https://urlscan.io/api/v1/search/?q=domain:acme.com&size=100`
- **Sample output:**
  ```json
  {"results":[{"page":{"url":"https://www.acme.com/login","domain":"www.acme.com","ip":"93.184.216.34"}}]}
  ```
- **Store:** only **on-target** results → `endpoint(url,source=urlscan)`, `asset(ip)`, `asset(subdomain)`+`edge(resolves_to)`.

### greynoise  (enrichment overlay)
- **Invoke (API):** `GET https://api.greynoise.io/v3/community/8.8.8.8`
- **Sample output:** `{"noise":true,"riot":false,"classification":"malicious"}`
- **Store:** **tags only** on the existing `asset(ip).tags += [mass_scanner, greynoise:malicious]`. Never creates assets.

---

# CATEGORY 2 — Passive DNS & Subdomain Enumeration  [PASSIVE → ACTIVE]

### subfinder  (passive aggregator)
- **Invoke:** `subfinder -d acme.com -all -silent -oJ`
- **Sample output (JSONL):** `{"host":"api.acme.com","input":"acme.com","source":"crtsh"}`
- **Store:** `asset(subdomain=host)`, `asset_source.tool=subfinder` (or the upstream `source`), `edge(host→acme.com, subdomain_of)`. Raw → `raw/subfinder/acme.com.jsonl`.

### crt.sh  (CT logs)
- **Invoke (API):** `GET https://crt.sh/?q=%25.acme.com&output=json`
- **Sample output:** `[{"name_value":"api.acme.com\nwww.acme.com","issuer_name":"C=US, O=Let's Encrypt"}]`
- **Store:** split `name_value` lines → `asset(subdomain)` (scope-filtered, emails dropped), `asset(cert)`, `edge(subdomain_of)`. source_confidence 0.9.

### certspotter  (CT monitoring)
- **Invoke (API):** `GET https://api.certspotter.com/v1/issuances?domain=acme.com&include_subdomains=true&expand=dns_names`
- **Sample output:** `[{"dns_names":["api.acme.com","*.acme.com"],"not_after":"2026-09-01T..."}]`
- **Store:** `dns_names`→`asset(subdomain)` (strip wildcard). Ideal for **continuous** mode (alert on new issuance).

### chaos / securitytrails / virustotal / hackertarget / alienvault_otx
- **chaos:** `GET dns.projectdiscovery.io/dns/acme.com/subdomains` → `subdomains[]`→`asset(subdomain)`.
- **securitytrails:** `GET api.securitytrails.com/v1/domain/acme.com/subdomains` (header `APIKEY`) → `subdomains[]` (prefix+`.acme.com`); also `/history/.../dns/a` → `asset_state` history.
- **virustotal:** `GET .../api/v3/domains/acme.com/subdomains` (header `x-apikey`) → `data[].id`→subdomain. Throttle (free 4/min).
- **hackertarget:** `GET api.hackertarget.com/hostsearch/?q=acme.com` → CSV `host,ip` → `asset(subdomain)`+`asset(ip)`+`edge(resolves_to)`.
- **alienvault_otx:** `GET otx.alienvault.com/.../domain/acme.com/passive_dns` → `passive_dns[].hostname/.address` → subdomain+ip+edge.

### alterx  (permutation generator)
- **Invoke:** `alterx -l subs.txt -silent` → emits candidate hostnames (e.g. `api-dev.acme.com`).
- **Store:** **nothing directly** — candidates are written to a temp file and **must be resolved** by dnsx/puredns; only resolving ones become `asset(subdomain)`.

### dnsx  (resolve + live validation — ACTIVE)
- **Invoke:** `dnsx -l subs.txt -a -aaaa -cname -resp -json -silent`
- **Sample output (JSON):**
  ```json
  {"host":"api.acme.com","a":["93.184.216.34"],"cname":["acme.map.fastly.net"],
   "status_code":"NOERROR","resolver":["1.1.1.1:53"]}
  ```
- **Store:** for each `a`→`asset(ip)`+`edge(host→ip, resolves_to)`; `cname`→`edge(host→cname, cname_to)` (dangling in-scope cname = takeover candidate). Mark `asset(subdomain).is_live` candidate=True (DNS resolves). NXDOMAIN/wildcards dropped (not stored as live).

### puredns (+massdns) / shuffledns  (mass resolve + wildcard filter — ACTIVE)
- **Invoke:** `puredns resolve subs.txt -r resolvers.txt --write live.txt --write-wildcards wildcards.txt`
- **Sample output:** `live.txt` = newline list of resolving, wildcard-filtered hosts.
- **Store:** resolving hosts → confirm `asset(subdomain)`; wildcard hosts dropped from frontier. Resolvers from `dnsvalidator` (`config/resolvers.txt`).

### tlsx  (cert grab — ACTIVE; CAT-24, feedback source)
- **Invoke:** `tlsx -l hosts.txt -san -cn -so -json -silent`
- **Sample output:**
  ```json
  {"host":"acme.com","port":"443","subject_cn":"acme.com",
   "subject_an":["acme.com","www.acme.com","api.acme.com"],"issuer_cn":"R3","not_after":"2026-09-01T..."}
  ```
- **Store:** `asset(cert)`; `subject_an` SANs (in-scope) → `asset(subdomain)` + `edge(serves_cert)` → **⟳ re-enter frontier**. TLS metadata → `service.tls`.

---

# CATEGORY 3 — WHOIS / ASN / BGP / Network Intelligence  [PASSIVE]

### asnmap
- **Invoke:** `asnmap -d acme.com -json -silent` (also `-a AS13335`, `-i 1.2.3.4`, `-org ACME`)
- **Sample output:** `{"as_number":"AS15133","as_name":"EDGECAST","as_country":"US","as_range":["93.184.216.0/24"]}`
- **Store:** `asset(asn)`, `asset(cidr)` per range, `edge(cidr→asn, announced_by)`, `edge(asn→org, owned_by)`. CIDRs feed naabu (Cat 21).

### bgpview / ripestat
- **bgpview:** `GET api.bgpview.io/asn/15133/prefixes` → `data.ipv4_prefixes[].prefix`→`asset(cidr)`.
- **ripestat:** `GET stat.ripe.net/data/announced-prefixes/data.json?resource=AS15133` → `data.prefixes[].prefix`.

### ipinfo / metabigor / mapcidr
- **ipinfo:** `GET ipinfo.io/93.184.216.34?token=$T` → `{"org":"AS15133 EdgeCast","city":"…","hostname":"…"}` → `asset(ip).attributes{asn,org,geo}`.
- **metabigor:** `echo "ACME" | metabigor net --org` → CIDR list (no key) → `asset(cidr)`.
- **mapcidr:** `mapcidr -cidr 93.184.216.0/24 -silent` → expands to IPs → fed to naabu.

---

# CATEGORY 4 — Dorking & URL Recon  [PASSIVE]

### gau
- **Invoke:** `gau acme.com --threads 5 --subs` (or per-host: `echo api.acme.com | gau`)
- **Sample output (text/JSONL):** `https://api.acme.com/v1/login?next=/`
- **Store:** `endpoint(url, source=gau)` (host resolved → parent `asset`). Feeds Cat 22/25.

### waybackurls / gf / unfurl / paramspider
- **waybackurls:** `cat hosts.txt | waybackurls` → urls → `endpoint`.
- **gf:** `cat urls.txt | gf ssrf` → filtered urls → tag `endpoint.risk_class`.
- **unfurl:** `cat urls.txt | unfurl keys` → param names → `endpoint.params`.
- **paramspider:** `paramspider -d acme.com` → urls with `FUZZ` params → `endpoint.params`.

---

# CATEGORY 5 — Web Tech Fingerprinting + Probing  [ACTIVE]

### httpx  (the live-validation hub)
- **Invoke:** `httpx -l resolved.txt -json -sc -title -td -server -tls-grab -cdn -ip -cname -hash sha256 -silent`
- **Sample output (JSON):**
  ```json
  {"url":"https://api.acme.com","input":"api.acme.com","status_code":200,
   "title":"Acme API","webserver":"nginx","tech":["Nginx","React"],
   "a":["93.184.216.34"],"cname":["acme.map.fastly.net"],"cdn":true,"cdn_name":"fastly",
   "host":"93.184.216.34","port":"443","scheme":"https","content_length":5120,
   "hash":{"body_sha256":"ab12…"},"jarm":"2ad…"}
  ```
- **Store:** **set `asset(subdomain).is_live=True`**; `asset.tech=tech`; `asset.tags += [cdn:fastly]` if cdn; `service(port,product=webserver)`; `endpoint(url,status_code,title,content_hash=hash.body_sha256)`; `edge(resolves_to)`. This is what gates Category-3/active enrichment to **live hosts only**.

### whatweb / webanalyze / wafw00f / cdncheck
- **whatweb:** `whatweb --log-json=out.json https://api.acme.com` → plugins → `asset.tech`.
- **wafw00f:** `wafw00f https://api.acme.com -f json -o out.json` → `{"detected":true,"firewall":"Cloudflare"}` → `asset.tags+=[waf:cloudflare]` (informs rate strategy).
- **cdncheck:** `cdncheck -i ips.txt -resp` → flags CDN IPs → `asset.tags+=[cdn]` (skip port-scanning CDN edges).

---

# CATEGORY 6 — Historical & Archive  [PASSIVE]

### wayback CDX  (+ JS download)
- **Invoke (API):** `GET http://web.archive.org/cdx/search/cdx?url=*.acme.com/*&output=json&fl=original&collapse=urlkey`
- **Sample output:** `[["original"],["https://acme.com/app.js"],["https://api.acme.com/v1"]]`
- **Store:** `endpoint(url,source=wayback)`; **`.js` URLs are downloaded** → `artifacts/js/<host>/app.js` and recorded on the endpoint (`js_artifact` ref) → feeds Cat 22.

### waymore / gau (cross-listed)
- **waymore:** `waymore -i acme.com -mode U -oU urls.txt` (aggregates wayback+commoncrawl+otx+urlscan, can download responses to FS).

---

# CATEGORY 9 — GitHub / GitLab / Source-Code  [PASSIVE → ACTIVE]

### github_search → clone → gitleaks/trufflehog
- **github_search (API):** `GET api.github.com/search/code?q=acme.com+org:acme` (header `Authorization: token`) → `items[].repository.full_name` → candidate repos (clone to `artifacts/repos/`).
- **gitleaks:** `gitleaks detect --source repo/ --report-format json --report-path out.json --no-banner`
  - **Sample:** `{"RuleID":"aws-access-key","File":"config.py","StartLine":12,"Secret":"AKIA…","Commit":"abc123"}`
  - **Store:** `finding(kind=secret,detector=gitleaks:aws-access-key, evidence_redacted={type, sha1(secret), preview:"AKIA****…", file, line, commit})`. **Raw secret NEVER stored.**
- **trufflehog:** `trufflehog filesystem repo/ --json` → `{"DetectorName":"AWS","Verified":true,"Raw":"…"}` → verified=true raises `finding.confidence`; verification is active (toggle).

---

# CATEGORY 10 — Cloud & Storage  [PASSIVE → ACTIVE]

### grayhatwarfare / cloud_enum / s3scanner
- **grayhatwarfare (API):** `GET buckets.grayhatwarfare.com/api/v2/buckets?keywords=acme` → `buckets[].bucket`→`asset(bucket)`.
- **cloud_enum:** `cloud_enum -k acme -l out.txt` → open buckets/apps/functions → `asset(bucket)`+`finding(kind=cloud)` if open.
- **s3scanner:** `s3scanner -bucket-file buckets.txt -json` → `{"bucket":"acme-backups","region":"us-east-1","perms":{"AllUsersRead":true}}` → `finding(kind=cloud, severity by perms)`.

---

# CATEGORY 12 — Malware/IOC & CVE Correlation  [PASSIVE]

### nvd + epss + vulners  (the correlation brain)
- **nvd (API):** `GET services.nvd.nist.gov/rest/json/cves/2.0?cpeName=cpe:2.3:a:nginx:nginx:1.18.0` (header `apiKey`) → CVE list + CVSS + CPE.
- **epss (API):** `GET api.first.org/data/v1/epss?cve=CVE-2021-23017` → `{"epss":"0.94","percentile":"0.99"}`.
- **Store:** cache to `vuln_ref(cve_id,cvss_v3,epss_score,cpe)`; `finding.priority_rank = w1·CVSS + w2·EPSS + w3·exposure + w4·asset_value`. Input CPEs come from httpx/nmap/internetdb fingerprints.

---

# CATEGORY 13 — Visual Recon  [ACTIVE]

### gowitness
- **Invoke:** `gowitness scan file -f live_urls.txt --screenshot-path artifacts/<scan>/screenshots/ --write-db`
- **Sample output:** PNG per URL + SQLite row `{url, final_url, title, response_code, technologies}`.
- **Store:** screenshot file → `endpoint.evidence_ref`; title/tech reconcile into `asset`. Feeds visual/AI triage (login/admin panels → `asset.tags+=[high_value]`).

---

# CATEGORY 20 — Content & Directory Discovery  [ACTIVE]

### ffuf / feroxbuster
- **ffuf:** `ffuf -u https://api.acme.com/FUZZ -w wordlist.txt -mc 200,204,301,302,401,403 -of json -o out.json`
  - **Sample:** `{"results":[{"url":"https://api.acme.com/admin","status":403,"length":12,"words":3}]}`
  - **Store:** `endpoint(url,status_code,risk_class=admin)`. Wordlists from Cat 28 (SecLists) + harvested paths (Cat 11).
- **feroxbuster:** `feroxbuster -u https://api.acme.com -w wordlist.txt --json -o out.jsonl` → recursive path discovery → `endpoint`.

---

# CATEGORY 21 — Port Scanning & Service Detection  [ACTIVE]

### naabu → nmap
- **naabu:** `naabu -list ips.txt -top-ports 1000 -json -silent`
  - **Sample:** `{"ip":"93.184.216.34","port":443,"host":"api.acme.com","protocol":"tcp"}`
  - **Store:** `service(asset_id=ip, port, protocol)`. Open web ports feed httpx; all ports feed nmap.
- **nmap:** `nmap -sV -sC -p 443,80,22 -oX out.xml 93.184.216.34`
  - **Sample (XML):** `<service name="http" product="nginx" version="1.18.0"/>`
  - **Store:** enrich `service(product,version,banner)`; product+version → CPE → Cat 12 CVE correlation.

### masscan (huge ranges)
- **Invoke:** `masscan 93.184.216.0/24 -p1-65535 --rate 1000 -oJ out.json` → `{"ip","ports":[{"port","proto"}]}` → `service`. Rate strictly profile-bound (very noisy).

---

# CATEGORY 22 — JavaScript Analysis & Secrets  [PASSIVE/ACTIVE]

### katana  (crawl + JS — feedback source)
- **Invoke:** `katana -list live_urls.txt -jc -js-crawl -json -d 3 -silent`
- **Sample output (JSON):**
  ```json
  {"timestamp":"...","request":{"endpoint":"https://api.acme.com/v2/users","method":"GET"},
   "response":{"status_code":200}}
  ```
- **Store:** `endpoint(url, source=katana)`; discovered `.js` → `artifacts/js/<host>/`; **new in-scope hosts referenced in JS → `asset(subdomain)` → ⟳ frontier**.

### jsluice / linkfinder / secretfinder / getJS / retire.js
- **jsluice:** `jsluice urls app.js` → `{"url":"/api/internal","type":"fetch"}` → `endpoint`; `jsluice secrets app.js` → `finding(secret)`.
- **linkfinder:** `python linkfinder.py -i app.js -o cli` → endpoints → `endpoint`.
- **secretfinder:** `python SecretFinder.py -i app.js -o cli` → `{"AWS API Key":"AKIA…"}` → `finding(secret, redacted)`.
- **retire.js:** `retire --js --outputformat json --jspath ./js` → `{"component":"jquery","version":"1.8.0","vulnerabilities":[…]}` → `finding(kind=cve, asset_value=host)`.

---

# CATEGORY 23 — API & GraphQL Recon  [ACTIVE]

### graphw00f / kiterunner
- **graphw00f:** `python main.py -d -f -t https://api.acme.com/graphql` → `{"engine":"apollo","detected":true}` → `finding(kind=exposure, title="GraphQL apollo + introspection")`.
- **kiterunner:** `kr scan live_urls.txt -w routes-large.kite -o json -O out.json` → `{"url":"https://api.acme.com/v1/admin","status":401}` → `endpoint(url, risk_class=api)`.

---

# CATEGORY 24 — TLS/SSL & Certificate Analysis  [ACTIVE]

### sslyze / cero  (tlsx in Cat 2 above)
- **sslyze:** `sslyze --json_out out.json api.acme.com:443` → cipher/protocol/cert analysis → `finding(kind=tls, title="TLS 1.0 enabled / weak cipher / expired")`.
- **cero:** `cero 93.184.216.0/24` → domains scraped from certs of an IP range → `asset(subdomain)` → ⟳ frontier.

---

# CATEGORY 27 — Active Vulnerability Detection  [ACTIVE]

### nuclei  (detection engine)
- **Invoke:** `nuclei -l live_urls.txt -jsonl -severity low,medium,high,critical -rl 50 -silent`
- **Sample output (JSONL):**
  ```json
  {"template-id":"CVE-2021-23017","matched-at":"https://api.acme.com","type":"http",
   "host":"api.acme.com","info":{"name":"nginx resolver off-by-one","severity":"high",
   "classification":{"cve-id":["CVE-2021-23017"],"cvss-score":8.1}},"curl-command":"curl -X GET …"}
  ```
- **Store:** `finding(kind=cve|exposure, title=info.name, severity=info.severity, cve_id=classification.cve-id[0], detector=nuclei:<template-id>, evidence_redacted={matched-at, curl-command})`. Dedup by (asset, template-id). Runs **only on live hosts**.

### subjack / tko-subs  (takeover)
- **subjack:** `subjack -w subs.txt -ssl -o out.txt` → `{"subdomain":"shop.acme.com","service":"GitHub Pages","vulnerable":true}` → `finding(kind=takeover, severity=high)`. Input = subdomains with dangling `cname_to` (from dnsx).

---

# UTILITY / GLUE

| Tool | Invoke | Output → use |
|------|--------|--------------|
| **anew** | `cat new.txt \| anew all.txt` | append-only dedupe; prints only genuinely new lines (drives the frontier) |
| **notify** | `cat findings.txt \| notify -silent` | push new findings to Slack/Discord/Telegram |
| **interactsh-client** | `interactsh-client -json` | OOB/OAST callbacks for blind detection (nuclei uses it) |
| **mapcidr** | `mapcidr -cidr X -silent` | expand CIDR → IP list (between Cat 3 and 21) |

---

## Storage mapping — one-glance summary

| Output artifact | DB table | Key fields | Filesystem |
|-----------------|----------|-----------|-----------|
| subdomain | `asset` (type=subdomain) | value, is_live, confidence, sources | raw/<tool>/ |
| ip | `asset` (type=ip) | value, attributes{asn,org,geo}, tags | — |
| cidr/asn | `asset` (type=cidr/asn) | value | — |
| cert | `asset` (type=cert) + `service.tls` | SANs→subdomains | — |
| open port | `service` | port, protocol, product, version | — |
| live URL/endpoint | `endpoint` | url, status_code, title, content_hash, risk_class | bodies/ |
| JS file | `endpoint.js_artifact` ptr | — | js/<host>/*.js |
| screenshot | `endpoint.evidence_ref` ptr | — | screenshots/*.png |
| vuln/secret/takeover/tls | `finding` | kind, severity, cve_id, detector, evidence_redacted | raw/<tool>/ |
| relationship | `edge` | src, dst, rel | — |
| every sighting | `asset_source` | tool, source_confidence, raw_ref | raw/<tool>/ |
| state-over-time | `asset_state` | snapshot, change_type | — |

This is the complete contract the adapters implement: **invoke → parse documented output
→ map to these tables/files → emit normalized events → engine dedups & re-queues**.
