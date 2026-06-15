# Batch 11 — Tool Catalog: Analysis Reports

Generated read-only from the post-M9 live registry + runtime evidence (scans 1e453aa1, abae971f, 856f38a7, b57cbcaee). 586 registry entries. Companion data: `TOOL_CATALOG_FULL.tsv` (per-tool matrix), `tool_catalog.tsv` (raw).

> Recursion class is exact for runnable tools; approximate for inventory stubs whose `produces` is category-inflated (category_io), not tool-specific.

## 1. Executive Summary

- **Registry size:** 586 entries.
- **Schedulable / worth running:** 334 (KEEP_CORE 26, KEEP_OPTIONAL 266, VALIDATION_ONLY 28, ENRICHMENT_ONLY 8, ARTIFACT_ONLY 6).
- **Deferred:** 150 (stubs / no producer / not scheduled). **Reference-only:** 102 (web/manual, never executed).
- **Ran in evidence scans:** 30 produced data, 9 ran empty; 45 installable-not-present, 13 need an API key.
- **Recursion roles:** Generator 327, Reference 102, Terminal 79, Expander 36, Validator 28, Enrichment 8, Artifact-Analyzer 6.
- **Post-M9 truth verified:** httpx→`live_host`; nuclei/whatweb/gowitness/katana consume `live_host`; js_analyze consumes `js_file`; `flow_lint` in-scope reachability = 0.

## 2. Recommended Scheduling Matrix (runnable tools by stage)

| Stage | # runnable | tools (core in **bold**) |
|---|---|---|
| Seed | 134 | ADSBExchange, AFRINIC, APNIC, ARIN, AbuseIPDB, Ahmia, Apollo.io, BSSID Search, Baidu Search, BeenVerified, BinaryEdge, BinaryEdge Hunt, Bing Search, Botometer, BreachDirectory, BuiltWith Lookup, BuiltWith Trends, CAIDA Tools +116 more |
| Domain | 117 | ANY.RUN, Abuse.ch, AlienVault OTX API, AlienVault OTX Pulse Archive, AlienVault OTX Search, Anomali, Arquivo.pt, BinaryEdge API, BufferOver, BuiltWith API, BuiltWith Historical Lookup, CIRCL CVE Search, CVE Details, Censys API, CertDB, Certificate Transparency Search, Chaos Dataset, Clearbit API +99 more |
| Subdomain | 35 | Appalyzer, Arachni, BlindElephant, BuiltWith, CMSeeK, CMSmap, EyeWitness, FingerprintJS, JoomScan, OpenVAS Discovery, Retire.js, RustScan, SimilarTech, WPScan, Wappalyzer, WebTech, WhatCMS, **dnsx** +17 more |
| Live Host | 10 | Censys screenshots, Playwright, Puppeteer, ScreenshotOne, Shodan screenshots, gowitness, katana, **nuclei**, urlscan screenshots, whatweb |
| URL | 21 | cariddi, feroxbuster, ffuf, gf-debug_logic, gf-idor, gf-interestingparams, gf-lfi, gf-rce, gf-redirect, gf-sqli, gf-ssrf, gf-ssti, gf-xss, gospider, graphw00f, hakrawler, kiterunner, nikto +3 more |
| JS | 4 | js_analyze, jsluice, linkfinder, secretfinder |
| Repository | 2 | gitleaks, trufflehog |
| Validation | 6 | cero, **greynoise**, **internetdb**, ipinfo, mapcidr, masscan |
| Findings | 5 | cloud_enum, **hibp-exposure**, nvd, s3scanner, vulners |

## 3. Future Exploitation-Layer Taxonomy

- **Recon (discover/expand)** (229): AFRINIC, APNIC, ARIN, AbuseIPDB, Ahmia, AlienVault OTX API, AlienVault OTX Pulse Archive, AlienVault OTX Search, Apollo.io, Arquivo.pt, Baidu Search, BeenVerified, BinaryEdge, BinaryEdge API, BinaryEdge Hunt, Bing Search, Botometer, BreachDirectory, BufferOver, BuiltWith API …
- **Validation (confirm)** (28): Appalyzer, Arachni, BlindElephant, BuiltWith, CMSeeK, CMSmap, EyeWitness, FingerprintJS, JoomScan, OpenVAS Discovery, Retire.js, RustScan, SimilarTech, WPScan, Wappalyzer, WebTech, WhatCMS, droopescan, eyewitness-ng, httping …
- **Artifact analysis** (6): gitleaks, js_analyze, jsluice, linkfinder, secretfinder, trufflehog
- **Findings (detect)** (71): ADSBExchange, ANY.RUN, Abuse.ch, Anomali, BSSID Search, CIRCL CVE Search, CVE Details, CellMapper, Censys screenshots, EO Browser, FIRST EPSS, Flashpoint, FlightRadar24, Google Earth, Google Maps, Hybrid Analysis, IOC Bucket, Intel471, Intezer, Joe Sandbox …
- **Exploitation (FUTURE — none today)** (0): 
- **Reporting** (0): 

Exploitation + Post-Exploitation layers are **empty by design today** — nuclei/WPScan etc. are detection-only (Terminal). They are the natural home for the future exploitation framework, fed by the Findings layer.

## 4. Duplicate Tools (same consumes+produces signature)

31 signature-collision groups among runnable tools. Recommend the **default_on / superset** as winner; others stay available (overlap is free via idempotent keys — corroboration, not waste).

| consumes → produces | tools | suggested winner |
|---|---|---|
| domain,org,ip,asn → subdomain,ip,service,cert,url,tech | Ahmia, Baidu Search, BinaryEdge, BinaryEdge Hunt, Bing Search, BuiltWith Lookup, BuiltWith Trends, Criminal IP, CriminalIP ASM, FOFA, FOFA Hunt, Google Search, Hunter Howler, IntelX, LeakIX Exposure Search, Netcraft, Netlas Hosts, ONYPHE, PublicWWW, Pulsedive, Pulsedive Threat Intelligence, Rapid7 Open Data, Reconmap, SOC Radar Search, Searchcode, Thingful, Wappalyzer Lookup, Wigle, Yandex Search, ZoomEye, ZoomEye Cyberspace Search | Ahmia |
| domain,ip,asn,org → asn,cidr,ip,org,domain | AFRINIC, APNIC, ARIN, AbuseIPDB, CAIDA Tools, CIRCL Passive DNS, Censys ASN Search, Cloudflare, CriminalIP IP Search, Cymru Hash Registry, FOFA IP Search, GreyNoise IP Lookup, IP2Location, IPFingerprints, IPGeolocation, IPQualityScore, IPVoid, LACNIC, MaxMind, Netlas ASN Search, PeeringDB, RADb, RIPE Atlas, RIPE NCC, Robtex, Shodan ASN Search, Spur, Spur Context API, Team Cymru, ipapi | AbuseIPDB |
| ip,domain,url,service,cpe,hash → ioc,finding,tag | ANY.RUN, Abuse.ch, Anomali, CIRCL CVE Search, CVE Details, FIRST EPSS, Flashpoint, Hybrid Analysis, IOC Bucket, Intel471, Intezer, Joe Sandbox, MISP, MalShare, MalwareBazaar, OpenCTI, OpenPhish, PhishTank, Recorded Future, ThreatBook, ThreatConnect, ThreatFox, ThreatMiner, URLHaus, YARAify, urlscan.io | Abuse.ch |
| live_host,url,subdomain → tech,service,tag,finding | Appalyzer, Arachni, BlindElephant, BuiltWith, CMSeeK, CMSmap, EyeWitness, FingerprintJS, JoomScan, OpenVAS Discovery, Retire.js, RustScan, SimilarTech, WPScan, Wappalyzer, WebTech, WhatCMS, droopescan, eyewitness-ng, httping, httprint, httprobe, nuclei templates, wafninja, webanalyze | Appalyzer |
| domain,email,username,org → email,username,finding | Apollo.io, BeenVerified, BreachDirectory, Clearbit, DeHashed, EmailHippo, FullContact, Have I Been Pwned, Hibp API, Hunter Domain Search, Hunter.io, Lampyre, LeakCheck, LeakCheck API, LeakPeek, Maltego, Pipl, RocketReach, Snusbase, Social Links, Spokeo, VerifyEmailAddress, Whitepages | Apollo.io |
| domain,ip,email,asn → service,subdomain,tag,finding | AlienVault OTX API, BinaryEdge API, BuiltWith API, Censys API, Clearbit API, CriminalIP API, FOFA API, FullContact API, GreyNoise API, HaveIBeenPwned API, Hunter API, IP2Location API, IPinfo API, IntelX API, Netlas API, Pulsedive API, SecurityTrails API, Shodan API, URLScan API, VirusTotal API, Wappalyzer API, ZoomEye API | AlienVault OTX API |
| domain → subdomain | amass, anubis-jldc, assetfinder, certspotter, chaos, dnsenum, fierce, findomain, fullhunt, github_subdomains, gobuster, netlas, securitytrails, shuffledns, subdomaincenter, subfinder, sublist3r, virustotal | anubis-jldc |
| domain,subdomain → subdomain,ip,cert | BufferOver, CertDB, Certificate Transparency Search, Chaos Dataset, DNS History Lookup, DNSDB, DNSlytics, PassiveTotal, ReverseDNSLookup, ReverseIPLookup, ReverseMXLookup, ReverseNSLookup, Riddler.io, RiskIQ Passive DNS, Spyse, ThreatCrowd, ViewDNS, WhoisXML API | BufferOver |
| org,bssid,coords,ip → finding,tag | ADSBExchange, BSSID Search, CellMapper, EO Browser, FlightRadar24, Google Earth, Google Maps, MarineTraffic, OpenCellID, OpenStreetMap, Sentinel Hub, VesselFinder, WiGLE WiFi Search | ADSBExchange |
| url → finding | gf-debug_logic, gf-idor, gf-interestingparams, gf-lfi, gf-rce, gf-redirect, gf-sqli, gf-ssrf, gf-ssti, gf-xss, graphw00f, nikto, wafw00f | gf-debug_logic |
| username,org,handle → username,url,finding | Botometer, FollowerWonk, GeoSocial Footprint, GeoSpy, Hoaxy, LinkedIn Recon, Pushshift, Reddit Search, Social Bearing, Social Blade, Social Searcher, YouTube Metadata | Botometer |
| domain,live_host → url,js_file | AlienVault OTX Pulse Archive, Arquivo.pt, BuiltWith Historical Lookup, Memento Time Travel, PublicWWW Historical Search, SecurityTrails Historical DNS, URLScan History, Wayback Machine | AlienVault OTX Pulse Archive |
| domain,live_host → url,repo,finding | AlienVault OTX Search, Common Crawl, DorkSearch, GitHub Dorks, URLScan Search, Web Archive Search | AlienVault OTX Search |
| url → url | cariddi, feroxbuster, ffuf, gospider, hakrawler, kiterunner | cariddi |
| live_host,url → screenshot,tag,tech | Censys screenshots, Playwright, Puppeteer, ScreenshotOne, Shodan screenshots, urlscan screenshots | Censys screenshots |

## 5. Orphan & Missing-Stage Report (cross-checked vs flow_lint)

- **Orphan producers (dead-end types — produced, nothing consumes):** in-scope `∅`; overlay/deferred `['document']`.
- **Orphan consumers (dead-weight types — consumed, nothing produces):** in-scope `∅`; overlay/deferred `['analytics_id', 'bssid', 'coords', 'cpe', 'cve', 'favicon', 'handle', 'hash', 'keyword']`.
- **Non-canonical types:** `∅`.
- **Core recon flow in-scope reachability = 0** (matches `scripts/flow_lint.py`, default/passive load). The remaining gaps are deferred (file-analysis: document/binary/apk) or enrichment (cpe/cve/hash/keyword) — real producers not yet wired — or off-by-default overlay (coords/bssid/handle/analytics_id/favicon).
- **NEW finding (active-authorized view):** with `--authorize-active`, dead-ends `['host_port']` and dead-weight `[]` appear. `host_port`: naabu/masscan declare it as output, but the curated `nmap` consumes `ip`/`subdomain` (adapter typing), so host_port has no curated consumer — a wiring nit to fix in a follow-on (align nmap to consume host_port, or naabu to emit service only).

## 6. Dead Weight / DEFER

150 tools recommended DEFER (inventory stub with no binary, available but never scheduled = chain-orphan, or an exact-output duplicate). These are kept in the registry (nothing deleted) but should not ship in a default profile. Top by status:

- **inventory_stub(no-binary)** (141): AltDNS, Aquatone, Arjun, ASM tools, ASNLookup, AttackSurfaceMapper, AWSBucketDump, AzureHound …
- **available_not_scheduled(chain-orphan)** (8): dns_resolve, epss, github_org_repos, httpx_probe, js-render, param_miner, pycrawl, pydirb
- **RAN_produced** (1): gauplus

## 7. Final Tool Taxonomy (recursion class × recommendation)

| recursion class | count | KEEP_CORE | KEEP_OPTIONAL | other |
|---|---|---|---|---|
| Generator | 327 | 19 | 174 | 134 |
| Reference | 102 | 0 | 0 | 102 |
| Terminal | 79 | 3 | 68 | 8 |
| Expander | 36 | 4 | 24 | 8 |
| Validator | 28 | 0 | 0 | 28 |
| Enrichment | 8 | 0 | 0 | 8 |
| Artifact-Analyzer | 6 | 0 | 0 | 6 |

**Core recommended profile (KEEP_CORE):** alienvault_otx, anubis-jldc, censys, certspotter, criminalip, crtsh, dnsx, findomain, fullhunt, gau, greynoise, hackertarget, hibp-exposure, httpx, hunter-emails, internetdb, leakix, netlas, nuclei, shodan, subdomaincenter, subfinder, uncover, urlscan, wayback, wayback_cdx.
