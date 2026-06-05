# Per-Category Pipeline Designs

Each category is a standalone pipeline: an ordered chain of stages where each stage
**consumes a typed artifact and produces a typed artifact**, writing normalized records
to the shared DB. Tools within a stage run in **parallel**; stages run in sequence.

Notation:
- `[P]` passive · `[A]` active
- `IN:` input artifact type · `OUT:` output artifact type
- `║` = parallel fan-out · `→` = sequential handoff (via DB)
- `★` = default-on (ships wired); others are toggles

This file specifies **all categories**. Categories 1 & 2 (our Wave-1 starting point) are
specified in the most operational detail.

---

## Category 1 — Internet-Wide Search & Asset Discovery  `[P]`

**Goal:** from a domain/org, discover exposed services, IPs, certs, and tech *without
touching the target* (querying third-party indexes).

```
 IN: domain, org, asn, ip
        │
   STAGE 1.1  SEARCH-ENGINE FAN-OUT  (parallel)
   ║ uncover ★      (wraps shodan/censys/fofa/zoomeye/netlas in one query)
   ║ shodan ★       IN:domain/ip  OUT:ip, service(host:port), cve-hint, hostname
   ║ censys ★       IN:domain     OUT:ip, service, cert, san→subdomain
   ║ netlas ★       IN:domain     OUT:ip, service, dns
   ║ leakix         IN:domain/ip  OUT:service, exposure-finding
   ║ fullhunt       IN:domain     OUT:subdomain, host, tech
   ║ criminalip     IN:domain/ip  OUT:service, exposure
   ║ urlscan ★      IN:domain     OUT:url, ip, tech, related-domain
        │
   STAGE 1.2  ENRICH / FILTER  (parallel overlay)
   ║ greynoise ★    IN:ip         OUT:tag(mass_scanner)  → suppress noise
   ║ internetdb ★   IN:ip         OUT:ports[], cves[]   (free, no credits)
        │
   NORMALIZE → assets(ip, service, cert, subdomain), edges(resolves_to, serves_cert)
        │
   OUT: ip, service(host:port), cert→subdomain, tech hints, exposure findings
        └──► feeds Cat 3 (ASN from IPs), Cat 21 (ports→deep scan), Cat 5 (httpx on hosts)
```

**Chaining contract:** Cat 1 OUT (`ip`, `service`, `cert→subdomain`) becomes IN for
Cat 3 (ASN expansion), Cat 21 (port verification), Cat 24 (cert pivot), Cat 5 (probe).

**Redundancy note:** `uncover` already queries Shodan/Censys/FOFA/ZoomEye/Netlas — run
`uncover` as the primary and the individual APIs only when you need their richer
per-host detail (Shodan banners, Censys certs).

---

## Category 2 — Passive DNS & Subdomain Enumeration  `[P/A]`

**Goal:** build the complete subdomain universe, then resolve + validate to live hosts.
This is the **root** of the whole platform — its output feeds almost everything.

```
 IN: domain
        │
   STAGE 2.1  PASSIVE DISCOVERY  (parallel, [P])
   ║ subfinder ★    IN:domain  OUT:subdomain   (fans to 30+ sources via keys)
   ║ crtsh ★        IN:domain  OUT:subdomain, cert   (CT logs)
   ║ certspotter ★  IN:domain  OUT:subdomain   (CT monitoring)
   ║ chaos          IN:domain  OUT:subdomain   (PD dataset, key)
   ║ securitytrails IN:domain  OUT:subdomain, history (key)
   ║ github-subdomains IN:domain OUT:subdomain (from code, key)
   ║ amass (passive)IN:domain  OUT:subdomain, edge
   ║ tlsx (from Cat1 IPs) IN:ip OUT:subdomain (SANs from live certs)
        │
   STAGE 2.2  PERMUTATION  ([A]-adjacent, generates candidates)
   → alterx / dnsgen / gotator   IN:subdomain  OUT:candidate-subdomain
        │
   STAGE 2.3  RESOLVE + WILDCARD FILTER  ([A])
   → dnsvalidator   → clean resolver list
   → puredns(massdns)/shuffledns  IN:subdomain+candidates  OUT:resolving-subdomain, ip
   → dnsx ★         IN:subdomain  OUT:A/AAAA/CNAME records, ip, cname-edge
        │
   STAGE 2.4  LIVENESS  ([A])
   → httpx ★        IN:subdomain  OUT:live url, status, title, tech, service
        │
   NORMALIZE → assets(subdomain, ip), edges(subdomain_of, resolves_to, cname_to)
        │
   OUT: live subdomains + IPs + cname chains
        ├──► Cat 21 port scan (on IPs)
        ├──► Cat 24 takeover check (dangling cname_to)
        ├──► Cat 5/13 fingerprint + screenshot (on live urls)
        └──► Cat 6 archive harvest (on live hosts)
```

**Stage gating:** 2.1 is passive (safe). 2.2-2.4 are active (DNS queries / HTTP) →
require `--authorize-active`. The atomic checks (`docs/pipeline/02`) validate each tool
here first since this category is the foundation.

---

## Category 3 — WHOIS / ASN / BGP / Network Intelligence  `[P]`

```
 IN: domain, ip (from Cat 1/2)
   STAGE 3.1  OWNERSHIP   ║ whois ║ rir-whois ║ ipinfo(key)   OUT:org, asn, netname
   STAGE 3.2  ASN→CIDR    → asnmap / bgpview / ripestat        IN:asn  OUT:cidr
   STAGE 3.3  CIDR ops    → mapcidr (expand/aggregate)         IN:cidr OUT:ip[]
   STAGE 3.4  PIVOT       ║ metabigor (org→asn, no key) ║ reverse-whois → related domains
   NORMALIZE → assets(asn, cidr, ip), edges(in_cidr, announced_by, owned_by)
   OUT: ip ranges  ──► Cat 21 port scan,  related domains ──► back to Cat 2
```

---

## Category 4 — Search Engine Dorking & Index / URL Recon  `[P]`

```
 IN: domain, live-host
   STAGE 4.1 ARCHIVE URLS   ║ gau ★ ║ waybackurls ║ waymore   IN:domain OUT:url
   STAGE 4.2 CODE/INDEX     ║ github-dorks (key) ║ pagodo(google) ║ grep.app
   STAGE 4.3 EXTRACT        → unfurl (parse) → gf (pattern match: ssrf/xss/redirect)
   STAGE 4.4 PARAMS         → ParamSpider (from archives)      OUT:url-with-params
   NORMALIZE → endpoints(url, params, risk_class), findings(secret in code)
   OUT: url corpus + params  ──► Cat 22 (JS), Cat 25 (param fuzz prep), Cat 5 (probe)
```

---

## Category 5 — Web Technology Fingerprinting  `[A]`

```
 IN: live-host / url (from Cat 2 httpx)
   STAGE 5.1 PROBE         → httpx ★  (status,title,tech,tls,cdn,hash,server)
   STAGE 5.2 TECH DEPTH    ║ whatweb ║ webanalyze ║ wappalyzer-api   OUT:tech[]
   STAGE 5.3 WAF/CDN       ║ wafw00f ║ cdncheck     OUT:tag(waf,cdn)  → tune rate
   STAGE 5.4 CMS (cond.)   if tech∈{wp,joomla,drupal} → wpscan/cmseek/droopescan
   NORMALIZE → asset.tech[], asset.tags[], service.product/version
   OUT: tech fingerprint  ──► Cat 12 (CVE correlation), Cat 27 (nuclei tag selection)
```

---

## Category 6 — Historical & Archive Recon  `[P]`

```
 IN: domain, live-host
   STAGE 6.1 AGGREGATE   → waymore / gau ★  (wayback+commoncrawl+otx+urlscan) OUT:url
   STAGE 6.2 TIME-RANGE  → wayback CDX (precise ranges, deleted endpoints)
   STAGE 6.3 JS HARVEST  → download *.js to filesystem (artifacts/js/)         ★
   NORMALIZE → endpoints(url, source=archive), js_file artifacts (FS pointers)
   OUT: historical urls + JS files  ──► Cat 22 (JS analysis), Cat 25 (params)
```

---

## Category 7 — Email / Username / Identity Recon  `[P]` (PII — legal-gated)

```
 IN: domain, person, username
   STAGE 7.1 EMAILS       ║ hunter(key) ║ theHarvester ║ phonebook   OUT:email, pattern
   STAGE 7.2 BREACH       ║ hibp(key) ║ dehashed(key)   OUT:breach-finding (REDACTED)
   STAGE 7.3 IDENTITY     ║ holehe ║ sherlock/maigret/blackbird      OUT:account
   STAGE 7.4 GOOGLE       → ghunt   OUT:google-account-intel
   NORMALIZE → assets(email), findings(breach — hashed/minimized), audit access
   OUT: emails + identities  (enrichment overlay; PII retention = short TTL)
```
**Legal gate:** breach modules require explicit enable + data-minimization (D6/D10).

---

## Category 8 — Social Media Recon  `[P]`

```
 IN: org, username, handle
   STAGE 8.1 PLATFORM SCRAPE  ║ instaloader ║ tiktok-scraper ║ pushshift(reddit)
   STAGE 8.2 ANALYTICS        ║ socialblade ║ botometer
   STAGE 8.3 GEO              ║ creepy ║ geospy(image-geo)
   NORMALIZE → identity/intel records (overlay, not assets)
   OUT: social footprint  (scope-dependent; off by default for domain recon)
```

---

## Category 9 — GitHub / GitLab / Source-Code Recon  `[P/A]`

```
 IN: org, domain, keyword
   STAGE 9.1 DISCOVER REPOS  ║ github-search(key) ║ gitdorker ║ sourcegraph ║ grep.app
   STAGE 9.2 CLONE           → git clone candidate repos → FS
   STAGE 9.3 SCAN SECRETS    → gitleaks ★ → trufflehog(verify=toggle [A]) → semgrep
   STAGE 9.4 ATTRIBUTION     → gitxray (contributors/org intel)
   NORMALIZE → findings(secret — hash+mask+location ONLY), repos
   OUT: leaked secrets/configs  ──► Cat 10 (cloud keys → bucket check), Cat 1 (hosts)
```

---

## Category 10 — Cloud & Storage Recon  `[P/A]`

```
 IN: org, domain, keyword (+ permutations)
   STAGE 10.1 PASSIVE BUCKETS  → grayhatwarfare(key) ★   OUT:public-bucket
   STAGE 10.2 ACTIVE ENUM [A]  ║ cloud_enum ║ s3scanner ║ cloudbrute ║ gcpbucketbrute
   STAGE 10.3 ASSET ENUM       → cloudlist (provider APIs, creds) ║ cloudfox(creds)
   STAGE 10.4 ORIGIN           → cloudfail (origin IP behind CDN)
   NORMALIZE → assets(bucket), findings(open-bucket, misconfig), edges(hosts)
   OUT: cloud assets + exposures
```

---

## Category 11 — Metadata & Document Recon  `[P]`

```
 IN: domain (+ harvested docs)
   STAGE 11.1 HARVEST DOCS  → metagoofil (pull pdf/docx/xlsx from indexed sources)
   STAGE 11.2 EXTRACT META  ║ exiftool ║ tika ║ oletools ║ pdfinfo   OUT:user, path, sw
   NORMALIZE → intel(usernames, internal paths, software versions, emails)
   OUT: usernames/paths  ──► Cat 7 (username pivot), Cat 20 (path wordlist seed)
```

---

## Category 12 — Malware / IOC / Threat Intel & CVE Correlation  `[P]`

```
 IN: ip, domain, service(product+version), hash
   STAGE 12.1 IOC ENRICH   ║ virustotal(key) ║ otx ║ threatfox ║ pulsedive
   STAGE 12.2 CVE MAP      service→cpe → nvd(key) → candidate CVEs
   STAGE 12.3 PRIORITIZE   → epss (exploit prob) + cvss + vulners → priority_rank
   NORMALIZE → vuln_ref cache, findings(cve with rank), tags(malicious infra)
   OUT: ranked CVE candidates  ──► Cat 27 (nuclei confirm)
```

---

## Category 13 — Visual Recon & Screenshotting  `[A]`

```
 IN: live-url (from Cat 2/5)
   STAGE 13.1 SCREENSHOT  → gowitness ★ (headless chrome)  OUT:png + metadata
   STAGE 13.2 (alt)       ║ eyewitness ║ playwright(custom)
   NORMALIZE → endpoint.evidence_ref (FS pointer), tag(login/admin from title/OCR)
   OUT: screenshots + visual triage  (feeds human/AI prioritization)
```

---

## Category 14 — Frameworks & Automation Suites  `[H]`

These are **engines**, not stages. We integrate selectively:
- `uncover` → used in Cat 1.   `interactsh` → OOB infra for Cat 27.
- `nuclei` → the Cat 27 active detection engine.   `notify` → alerting sink.
- `amass`/`BBOT` → optional alternate engines behind Cat 2 (run as one source).
We do **not** adopt ReconFTW/Osmedeus wholesale (we replace their bash glue with our DB-
driven orchestrator), but we study their tool ordering.

---

## Categories 15-18 (scope-dependent overlays) — summarized

| Cat | Pipeline shape | OUT |
|-----|----------------|-----|
| **15 Geo/Wireless** | wigle/opencellid/flightradar/marinetraffic APIs → geo records | location intel |
| **16 Dark Web** | ahmia/onionsearch/intelx-tor → onion mentions of scope | leak/mention intel |
| **17 APIs & Feeds** | not a pipeline — the *key-backed providers* used across Cat 1/3/7/12 | enrichment |
| **18 Living Indexes** | not tools — curated lists for tool discovery | reference only |

---

## NEW Categories (20-25) — the active-recon additions

### Category 20 — Content & Directory Discovery  `[A]`
```
 IN: live-url
   → ffuf ★ / feroxbuster / dirsearch / gobuster(dir)   IN:url + wordlist  OUT:path
   → kiterunner (API routes from wordlist)
   wordlists from Cat 28 (SecLists) + Cat 11 (harvested paths)
   NORMALIZE → endpoints(url, status, risk_class)
   OUT: hidden endpoints  ──► Cat 25 (params), Cat 27 (nuclei)
```

### Category 21 — Port Scanning & Service Detection  `[A]`
```
 IN: ip (from Cat 1/2/3)
   STAGE 21.1 FAST  → naabu ★ (top-ports per profile)   OUT:open host:port
   STAGE 21.2 DEEP  → nmap -sV -sC (only on naabu ports) OUT:product, version, banner
   STAGE 21.3 (scale) → masscan/rustscan for huge ranges
   STAGE 21.4 svc fp → fingerprintx (non-HTTP services)
   NORMALIZE → service(port, product, version, banner)
   OUT: services  ──► Cat 5 (http on web ports), Cat 12 (CVE map), Cat 24 (TLS on 443)
```

### Category 22 — JavaScript Analysis & Secret Extraction  `[P/A]`
```
 IN: js_file (from Cat 6 harvest) + live-url
   STAGE 22.1 COLLECT  → getJS / katana(-jc)            OUT:js_file (FS)
   STAGE 22.2 ENDPOINTS→ linkfinder / xnlinkfinder / JSluice   OUT:url, api-path
   STAGE 22.3 SECRETS  → secretfinder / mantra / JSluice / trufflehog(fs)  OUT:secret(redacted)
   STAGE 22.4 VULN LIB → retire.js                       OUT:finding(vuln-js-lib)
   NORMALIZE → endpoints(url, source=js), findings(secret/vuln-lib)
   OUT: new endpoints + JS secrets  ──► loop to Cat 5 (probe), Cat 25 (params)
```

### Category 23 — API & GraphQL Recon  `[A]`
```
 IN: live-url, endpoint
   STAGE 23.1 SPEC HUNT → swaggerhole / find /swagger.json /openapi.json /graphql
   STAGE 23.2 GRAPHQL   → graphw00f (detect engine) → clairvoyance (introspect schema)
   STAGE 23.3 ROUTES    → kiterunner (API route brute)
   STAGE 23.4 PARAMS    → arjun (API param discovery)
   NORMALIZE → endpoints(api), findings(introspection-enabled, exposed-spec)
   OUT: API surface  ──► Cat 27 (nuclei api templates)
```

### Category 24 — TLS/SSL & Certificate Analysis  `[A]`
```
 IN: host:443 (from Cat 2/21)
   STAGE 24.1 GRAB   → tlsx ★ (SANs, JARM, issuer, expiry, cipher)  OUT:cert, subdomain(SAN)
   STAGE 24.2 PIVOT  → cero (domains from cert of IP range)         OUT:subdomain
   STAGE 24.3 AUDIT  → sslyze / testssl.sh   OUT:finding(weak-cipher, expired, self-signed)
   NORMALIZE → assets(cert), edges(serves_cert), findings(tls)
   OUT: cert SANs (new subdomains!) ──► back to Cat 2,  TLS findings
```

### Category 25 — Parameter Discovery & Fuzz Prep  `[A]`
```
 IN: url (from Cat 4/6/22)
   STAGE 25.1 MINE   ║ paramspider (archives) ║ arjun (active) ║ x8     OUT:param
   STAGE 25.2 SHAPE  → gf (classify by attack type) → qsreplace (templatize)
   NORMALIZE → endpoints(url, params[], risk_class)
   OUT: parameterized urls ready for fuzzing  (handoff to scanning, out of recon scope)
```

---

## The Integration View (how categories connect)

```
                 ┌───────────────── CANONICAL DB (the integration bus) ─────────────────┐
                 │                                                                       │
 domain ─► Cat2 subdomains ─► Cat24 cert-SANs ─┐                                          │
        ─► Cat1 ips/services ─► Cat3 asn/cidr ─┼─► Cat21 ports ─► Cat5 fingerprint ─┐     │
        ─► Cat6 urls/js ───────────────────────┘                                    │     │
                 │                                                                  ▼     │
                 │   Cat22 js-endpoints ─► Cat4 url-corpus ─► Cat25 params          Cat13 │
                 │   Cat9 secrets ─► Cat10 cloud ─► Cat12 cve ─► Cat27 nuclei ◄──────┘     │
                 └───────────────────────────────────────────────────────────────────────┘
```

No category calls another directly. Each reads its inputs from the DB and writes its
outputs back. This is what lets us **build and test each category in isolation now**, and
**integrate by simply enabling more categories** later.
