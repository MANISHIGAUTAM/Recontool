# D1 — Tool Selection Matrix

**How to read this:** For each category I name the **default** (what the platform
ships wired-on), the **best free**, the **best paid/enterprise**, the **best for
automation**, what each tool **chains with**, what is **redundant** (don't wire all of
them — pick the marked default), and the **rate-limit / legal** reality.

**Golden rule of redundancy:** Most categories have 5–20 tools that return *the same
data from the same upstream sources* (CT logs, passive DNS providers). Wiring all of
them multiplies your API spend and gives you near-zero new assets. Pick one strong
aggregator per source-type, then dedupe.

Legend — **P** = Passive (no target contact), **A** = Active (touches target),
**H** = Hybrid.

---

## CAT-1 — Internet-Wide Search Engines & Asset Discovery

| Tool | P/A | Free/Paid | Automation (CLI/API) | Best for | Notes |
|------|-----|-----------|----------------------|----------|-------|
| **Shodan** ⭐default | P | Freemium | Excellent (official API, `shodan` CLI) | Exposed services, banners, ports w/o scanning | Industry standard. `InternetDB` free endpoint gives ports+CVEs per IP with no credits. |
| **Censys** ⭐default | P | Freemium | Excellent (Search API v2) | TLS cert pivots, host intelligence | Best certificate analytics. Pairs with Shodan (low overlap on cert data). |
| **Netlas** | P | Freemium | Excellent | Fast automation, modern Shodan alt | Generous free tier; good when Shodan credits run dry. |
| **FOFA / ZoomEye** | P | Freemium | Good | APAC/China-region assets | Use only if scope includes APAC infra; otherwise redundant w/ Shodan+Censys. |
| **GreyNoise** ⭐default | P | Freemium | Excellent | *Noise filtering* — is this IP a mass-scanner? | Not asset discovery — it's an enrichment overlay. Essential to suppress internet-background-noise findings. |
| **LeakIX** | P | Freemium | API | Open services, exposed DBs, leaks | High signal for misconfig/leak discovery. |
| **FullHunt** | P | Freemium | API | Bug-bounty ASM | Popular w/ hunters; overlaps Censys/Shodan. |
| **IntelX** | P | Paid | API | Leaks, archives, breach data | Broadest OSINT/leak engine; gate behind contract. |
| **URLScan.io** ⭐default | P | Freemium | Excellent | Web fingerprint, JS, phishing infra, historical DOM | Submit + search API; *submit publicly only with care* (see OPSEC). |
| **BinaryEdge / ONYPHE / Criminal IP** | P | Paid/Freemium | API | Exposure telemetry | Strong but overlapping; add only if budget allows. |
| **PublicWWW** | P | Freemium | Limited API | Source-code search (analytics IDs, JS snippets) | Underrated for pivoting on shared tracking IDs / fingerprints. |
| **RiskIQ PassiveTotal (MS Defender TI)** | P | Paid | Excellent | Enterprise infra mapping, passive DNS | Now Microsoft. Premium; enterprise EASM tier. |
| **Project Sonar / Rapid7 Open Data** | P | Free | Bulk download | Research-grade internet-wide datasets | Big-data ingest; not real-time. Backbone for offline correlation. |
| Netcraft, Wigle, Pulsedive, SOCRadar | P | Freemium | Mixed | Niche (phishing, WiFi, IOC, CTI) | Situational; not in default wiring. |

- **Best free:** Shodan (InternetDB) + Censys + Netlas + GreyNoise.
- **Best paid:** Censys Enterprise / MS Defender TI (PassiveTotal).
- **Best for automation:** Shodan & Censys (mature, documented, rate-limited APIs).
- **Chains with:** feeds IPs/certs → **CAT-3** (ASN/BGP) and → Phase-4 active verify.
- **Redundant set:** FOFA/ZoomEye/BinaryEdge/ONYPHE/Criminal IP/FullHunt all overlap
  Shodan+Censys. Pick **two** primaries + GreyNoise overlay; add region-specific ones
  only when scope demands.
- **Rate/legal:** All passive (querying *their* index, not the target). Respect each
  API's TOS + credit limits. URLScan public submissions can *leak* your target to
  others — use **unlisted/private** scans for live engagements.

---

## CAT-2 — Passive DNS & Subdomain Enumeration

| Tool | P/A | Free/Paid | Automation | Best for | Notes |
|------|-----|-----------|------------|----------|-------|
| **subfinder** ⭐default | P | Free | Excellent (CLI/API) | Passive subdomain aggregation | The standard. Fans out to 30+ sources via your API keys in one config. |
| **Amass** ⭐default (passive mode) | H | Free | CLI/API | Comprehensive asset graph | Gold standard but heavier/slower; run passive in core flow, active brute optional. |
| **BBOT** | H | Free | CLI/API | Modular recursive recon | Excellent modern framework; we *integrate selectively*, see D8 (don't fully reinvent it). |
| **crt.sh** ⭐default | P | Free | Web/SQL-ish | CT-log subdomains | Query the public Postgres directly for speed; flaky uptime — cache aggressively. |
| **CertSpotter / CTFR** | P | Freemium | API/CLI | CT-log monitoring & discovery | CertSpotter API is great for *continuous* CT monitoring (EASM mode). |
| **SecurityTrails** ⭐default(paid) | P | Paid/Freemium | API | Best passive DNS dataset + history | Premium quality historical DNS; the one paid DNS API worth it. |
| **VirusTotal** | P | Freemium | API | Passive DNS + malware infra pivots | 4 req/min on free tier — rate-limit hard. |
| **DNSDB (Farsight)** | P | Paid | API | Historical passive DNS, industry std | Enterprise; deep history. |
| **Chaos (ProjectDiscovery)** | P | Free | API | Bug-bounty subdomain dataset | Free, fast, great recall on bug-bounty scopes. |
| **dnsx** ⭐default | A | Free | Excellent CLI | Resolve/validate/probe DNS records | The resolution workhorse downstream of enumeration. |
| **puredns + massdns + shuffledns** ⭐default | A | Free | CLI | Mass resolution + wildcard filtering | The active resolution trio. `puredns` orchestrates `massdns`; wildcard handling is its killer feature. |
| **Findomain / OneForAll / theHarvester / Sudomy / assetfinder** | P/H | Free | CLI | Alt aggregators | Overlap subfinder heavily. theHarvester adds emails. OneForAll strong on CN sources. |
| **AltDNS / dnsgen / gotator** | A | Free | CLI | Permutation generation | Generate candidate subdomains → resolve with puredns. High value for hidden hosts. |
| **dnstwist** | P | Free | CLI/API | Typosquat / brand-impersonation | Phishing-surface, not asset discovery. |
| **haktrails** | P | Free | CLI | SecurityTrails API wrapper | Convenience wrapper; use SecurityTrails directly in platform. |

- **Best free:** subfinder + Chaos + crt.sh (discovery) → puredns/massdns (validate).
- **Best paid:** SecurityTrails (history + recall).
- **Best for automation:** subfinder (sources) → dnsx/puredns (resolution).
- **Chains with:** discovery (subfinder/crt.sh/Chaos) → **permutation** (dnsgen) →
  **resolve+wildcard-filter** (puredns/massdns) → **probe** (httpx, CAT-5).
- **Redundant set:** Findomain, OneForAll, Sudomy, assetfinder, sublist3r, crobat,
  haktrails mostly re-query the *same* upstream sources subfinder already covers. Run
  **subfinder + Chaos + crt.sh + CertSpotter + SecurityTrails**; treat the rest as
  optional source-boosters behind a flag.
- **Rate/legal:** Discovery is passive. **Resolution (dnsx/puredns) is active DNS** —
  it queries resolvers, mildly observable; use trusted resolvers list (`dnsvalidator`)
  and respect rate profiles. Brute-force resolution is "active."

---

## CAT-3 — WHOIS, ASN, BGP & Network Intelligence

| Tool | P/A | Free/Paid | Automation | Best for | Notes |
|------|-----|-----------|------------|----------|-------|
| **bgp.he.net (Hurricane Electric)** ⭐default | P | Free | Web (scrape) | ASN→prefix→org visibility | Legendary coverage; no official API — scrape politely or use BGPView. |
| **BGPView** ⭐default | P | Free | API | ASN relationships & prefixes | Clean free API — use this for automation instead of scraping HE. |
| **RIPEstat** ⭐default | P | Free | Excellent API | ASN/BGP/DNS analytics | One of the best *free* network-intel APIs. |
| **IPinfo** ⭐default | P | Freemium | Excellent API | IP→ASN→geo enrichment | Best DX; generous free tier; bulk enrichment. |
| **ASNmap (ProjectDiscovery)** ⭐default | P | Free | Excellent CLI | ASN→CIDR expansion in pipelines | Purpose-built to feed CIDRs into the rest of the flow. |
| **Team Cymru** | P | Free/Freemium | API (whois/DNS) | Bulk IP→ASN, malware hash | Classic; great for bulk ASN mapping. |
| RIR WHOIS (ARIN/RIPE/APNIC/AFRINIC/LACNIC) | P | Free | API | Authoritative ownership | Source of truth for ownership; region-specific. |
| **AbuseIPDB** | P | Freemium | API | IP reputation / abuse score | Enrichment overlay, not discovery. |
| **MaxMind / IP2Location** | P | Paid/Freemium | API/DB | GeoIP enrichment | MaxMind GeoLite2 free DB is fine for most. |
| **GreyNoise** (cross-listed) | P | Freemium | API | Scanner-vs-target traffic | Suppress noise; tag mass-scanner IPs. |
| **InternetDB (Shodan)** | P | Free | API | Free ports+CVE per IP | Free, no credits — great cheap enrichment. |
| **PeeringDB / RADb / Robtex** | P | Free | API | Peering/route objects/infra pivots | Infra research depth; situational. |
| **RIPE Atlas** | A | Free/Freemium | API | Distributed active measurements | *Active* (probes target paths); research-grade latency/path. |
| IPQualityScore / Spur | P | Paid | API | VPN/proxy/fraud, behavioral | Anti-abuse focus; not core recon. |

- **Best free:** BGPView + RIPEstat + IPinfo (free tier) + ASNmap + GreyNoise.
- **Best paid:** IPinfo paid / MaxMind / MS Defender TI passive DNS.
- **Best for automation:** ASNmap (CIDR expansion) + BGPView/RIPEstat (relationships)
  + IPinfo (per-IP enrichment).
- **Chains with:** ASN (from WHOIS of seed IPs) → **ASNmap** → CIDR ranges → feed
  Phase-4 port/HTTP probing; org name → reverse-WHOIS → related domains.
- **Redundant set:** All five RIRs overlap if you just want ownership — use IPinfo/Team
  Cymru as the abstraction and fall back to specific RIRs only for authoritative checks.
  bgp.he.net and BGPView overlap — automate on BGPView, use HE for manual depth.
- **Rate/legal:** All passive **except RIPE Atlas** (active measurement). Reverse-WHOIS
  bulk queries can hit TOS limits on paid providers.

---

## CAT-4 — Search Engine Dorking, Index & URL Recon

| Tool | P/A | Free/Paid | Automation | Best for | Notes |
|------|-----|-----------|------------|----------|-------|
| **gau / gauplus** ⭐default | P | Free | Excellent CLI | Aggregate historical URLs (Wayback+CommonCrawl+OTX+URLScan) | Single best "give me every known URL" tool. |
| **waybackurls** ⭐default | P | Free | CLI | Wayback CDX URL harvest | Pairs with gau; gau is the superset. |
| **katana** ⭐default | H | Free | Excellent CLI/API | Modern JS-aware crawler | Best active crawler; also has passive source mode. |
| **GitHub code search + GitHub Dorks** ⭐default | P | Free | API | Secrets/config in public repos | Extremely high signal. Token-rate-limited; queue carefully. |
| **GitLeaks / TruffleHog** ⭐default | P | Free | Excellent CLI/API | Verified secret detection in repos/history | TruffleHog *verifies* creds (live check) — that step is active; gate it. |
| **Pagodo (+ GHDB)** | P | Free | CLI | Automated Google dorking | Google aggressively blocks automation — use sparingly, expect CAPTCHAs. |
| **ParamSpider** ⭐default | P | Free | CLI | Mine parameters from archives | Feeds fuzzing/XSS/SSRF recon. |
| **Arjun** | A | Free | CLI | Hidden parameter discovery (active) | Sends requests — active. |
| **LinkFinder / xnLinkFinder / SecretFinder / getJS** ⭐default(LinkFinder+SecretFinder) | P/H | Free | CLI | Endpoints + secrets from JS | xnLinkFinder is the strongest extractor; SecretFinder for keys. |
| **Common Crawl** | P | Free | Dataset/API | Internet-scale URL mining | Big-data; gau already taps it. Direct use for deep digs. |
| **URLScan (search)** | P | Freemium | API | Historical DOM/URL intel | Cross-listed CAT-1. |
| **AlienVault OTX** | P | Freemium | API | URL/IOC infra intel | gau pulls from it; direct for IOC pivots. |

- **Best free:** gau + katana + GitHub search + TruffleHog/GitLeaks + xnLinkFinder.
- **Best paid:** none essential here — this category is overwhelmingly free/OSS.
- **Best for automation:** gau (URLs) → katana (crawl live) → ParamSpider/LinkFinder
  (extract) → SecretFinder (keys).
- **Chains with:** live hosts (httpx) → katana crawl → JS extraction → param discovery
  → feed Phase-6 nuclei/secret scans.
- **Redundant set:** waybackurls ⊂ gau; getJS ⊂ katana/LinkFinder; many dorkers overlap.
  Run **gau + katana + xnLinkFinder + SecretFinder** as the spine.
- **Rate/legal:** Archive harvesting is passive. **Crawling (katana), Arjun, and
  TruffleHog credential verification are active.** Google dorking automation risks IP
  bans/CAPTCHA and arguably TOS issues — prefer Bing API or manual dorks.

---

## CAT-5 — Web Tech Fingerprinting, Probing & Visual Recon

| Tool | P/A | Free/Paid | Automation | Best for | Notes |
|------|-----|-----------|------------|----------|-------|
| **httpx** ⭐default | A | Free | Excellent CLI/API | Live-host probing, status/title/tech/TLS/hash | The single most important active tool in the flow. |
| **naabu** ⭐default | A | Free | Excellent CLI | Fast SYN/CONNECT port discovery | Feeds Nmap for deep scans. |
| **Nmap** ⭐default | A | Free | CLI (+NSE) | Deep service/version detection | Run *after* naabu narrows ports. NSE = controlled enumeration only. |
| **RustScan** | A | Free | CLI | Ultra-fast port sweep → Nmap | Alternative front-end to Nmap; naabu is our default. |
| **nuclei** ⭐default | A | Free | Excellent CLI/API | Templated detection (CVE, misconfig, exposure, takeover) | The vuln/exposure engine. Templated = auditable, scope-safe. |
| **gowitness** ⭐default | A | Free | Excellent CLI/API | Headless screenshots at scale | Modern Aquatone replacement; SQLite/DB output. |
| **EyeWitness / Aquatone** | A | Free | CLI | Screenshots + categorization | Aquatone deprecated; gowitness preferred. |
| **WhatWeb / webanalyze / Wappalyzer** ⭐default(httpx tech + webanalyze) | A/P | Free/Freemium | CLI/API | Tech stack fingerprint | httpx `-tech-detect` covers most; webanalyze for depth. |
| **wafw00f** ⭐default | A | Free | CLI | WAF detection | Quick, informs rate strategy. |
| **WPScan / CMSeeK / droopescan / JoomScan** | A | Freemium/Free | CLI/API | CMS-specific enumeration | Run conditionally when fingerprint = WP/Joomla/Drupal. |
| **Retire.js** | P | Free | CLI/API | Vulnerable JS library detection | Pairs with JS harvesting (CAT-4). |
| **testssl.sh / sslyze** ⭐default(sslyze) | A | Free | CLI | TLS/SSL config analysis | sslyze is scriptable/JSON; testssl for human depth. |
| **Nikto / Arachni / OpenVAS** | A | Free | CLI | Broad web vuln baseline | Noisy; nuclei is the modern, surgical replacement. Skip in default flow. |
| **BuiltWith / SimilarTech / WhatRuns** | P | Paid/Freemium | API | Historical/business tech intel | Passive enrichment; BuiltWith good for *historical* stack + business data. |

- **Best free:** httpx + naabu + Nmap + nuclei + gowitness + sslyze + wafw00f.
- **Best paid:** WPScan API token (CMS CVE feed) / BuiltWith (historical/business).
- **Best for automation:** httpx is the hub; naabu→Nmap; nuclei for detection.
- **Chains with:** resolved hosts → naabu (ports) → httpx (HTTP layer) → gowitness
  (visual) → katana (crawl) → nuclei (detect).
- **Redundant set:** RustScan vs naabu (pick naabu); Aquatone/EyeWitness vs gowitness
  (pick gowitness); Nikto/Arachni/OpenVAS superseded by nuclei for recon scope.
- **Rate/legal:** **Entire category is ACTIVE** (touches target) except BuiltWith/
  SimilarTech/Wappalyzer-API. Requires authorized scope. Port scanning and CMS
  enumeration are the most "noisy/observable" steps — gate behind scope + rate profile.

---

## CAT-6 — Historical & Archive Recon

| Tool | P/A | Free/Paid | Automation | Best for | Notes |
|------|-----|-----------|------------|----------|-------|
| **Wayback Machine (CDX API)** ⭐default | P | Free | Excellent API | Historical URLs, deleted endpoints, old params | Query CDX directly for precise time-ranged URL sets. |
| **Common Crawl Index** | P | Free | Dataset/API | Internet-scale historical URLs | Heavy; use for deep digs gau doesn't surface. |
| **gau** (cross-listed) | P | Free | CLI | One-shot aggregation of all the above | Default front-door to historical URLs. |
| **URLScan historical** | P | Freemium | API | Past DOM/screenshots/tech of a host | Great for "what did this look like before." |
| **SecurityTrails history** | P | Paid | API | Historical DNS/IP/WHOIS records | Best for infra attribution over time. |
| **Censys historical** | P | Paid | API | Historical certs/hosts | Pivot on expired certs → forgotten infra. |
| **AlienVault OTX** | P | Freemium | API | Historical URL/IOC | gau taps it. |
| Google Cache / Archive.ph / CachedView / Memento (timetravel) | P | Free | Web | Manual point-in-time lookups | Manual/triage use; Google Cache is being deprecated. |

- **Best free:** Wayback CDX + gau + Common Crawl.
- **Best paid:** SecurityTrails history + Censys historical (attribution/time-travel).
- **Best for automation:** gau (aggregate) + Wayback CDX (precise time ranges).
- **Chains with:** historical URLs → ParamSpider/LinkFinder → live-check with httpx
  ("does this old endpoint still resolve/respond?"). Historical DNS → re-resolve to
  find forgotten live hosts.
- **Redundant set:** gau already aggregates Wayback+CommonCrawl+OTX+URLScan — call the
  individual APIs only for *time-ranged* or deep queries.
- **Rate/legal:** Fully passive (querying archives). Memento/Archive.ph have polite-use
  expectations; Common Crawl is bulk-friendly.

---

## CAT-7 — Cloud & Infrastructure Recon

| Tool | P/A | Free/Paid | Automation | Best for | Notes |
|------|-----|-----------|------------|----------|-------|
| **GrayhatWarfare** ⭐default | P | Freemium | API | Public S3/Azure/GCS bucket search | Best *passive* exposed-bucket index. |
| **cloud_enum** ⭐default | A | Free | CLI | Enumerate buckets/containers/functions across AWS/Azure/GCP from a keyword | Active (probes cloud endpoints) but not the target's app. |
| **S3Scanner** | A | Free | CLI | S3 bucket discovery + perms check | Active; checks read/write/list perms. |
| **CloudScraper / Bucket Finder** | A | Free | CLI | Bucket brute from domain | Overlaps cloud_enum. |
| **ScoutSuite / Prowler / CloudMapper** | A | Free | CLI | *Credentialed* cloud posture audit | Requires the org's cloud creds — for internal ASM/authorized audits only, not external recon. |
| **Enumerate-IAM / Pacu** | A | Free | CLI | AWS IAM enum / AWS exploitation framework | **Pacu is offensive/exploitation — out of scope** for this platform. Enumerate-IAM only with provided keys. |
| **TruffleHog (cloud)** | A | Free | CLI | Secrets that grant cloud access | Cross-listed; verification step is active. |

- **Best free:** GrayhatWarfare (passive) + cloud_enum (active discovery).
- **Best paid:** GrayhatWarfare paid tier (more buckets/filters).
- **Best for automation:** GrayhatWarfare API (passive) → cloud_enum (active probe).
- **Chains with:** org names + discovered keywords (from subdomains/CT) → bucket
  permutations → cloud_enum/GrayhatWarfare → flag readable buckets as findings.
- **Redundant set:** CloudScraper/Bucket Finder/S3Scanner overlap cloud_enum.
- **Rate/legal:** GrayhatWarfare passive. cloud_enum/S3Scanner are **active against
  cloud provider endpoints** — generally low-risk but must respect scope and provider
  TOS. **ScoutSuite/Prowler/Pacu require credentials and are NOT external recon** —
  exclude Pacu entirely (exploitation), gate ScoutSuite/Prowler to authorized internal
  audits.

---

## CAT-8 — Email, Identity & Social Recon

| Tool | P/A | Free/Paid | Automation | Best for | Notes |
|------|-----|-----------|------------|----------|-------|
| **theHarvester** ⭐default | P | Free | CLI | Emails + subdomains + names from many sources | Solid free baseline. |
| **Hunter.io** ⭐default(paid) | P | Freemium | API | Corporate email patterns/addresses | Best email-pattern API. |
| **HaveIBeenPwned** ⭐default | P | Paid (API key) | API | Breach exposure for a domain/email | Authoritative breach data; API key required. |
| **Dehashed / LeakCheck** | P | Paid | API | Credential/breach lookups | Powerful, sensitive — strict handling + legal gate. |
| **Holehe** | A | Free | CLI | Which sites an email is registered on | Active (probes site password-reset/login). |
| **Sherlock / Maigret** | A | Free | CLI | Username across social platforms | Active (queries each platform). |
| **h8mail** | P/H | Free | CLI | Email breach hunting (chains Dehashed/etc.) | Orchestrates breach APIs. |
| **EmailRep** | P | Freemium | API | Email reputation/profile | Enrichment. |
| **Phonebook.cz / IntelX** | P | Freemium/Paid | Web/API | Domain emails/URLs/subdomains | IntelX cross-listed CAT-1. |
| **SpiderFoot / Recon-ng / Maltego** | H | Free/Paid | CLI/API/GUI | OSINT *frameworks* (aggregators) | These are *meta-platforms*. We borrow ideas, integrate selectively (D8). |

- **Best free:** theHarvester + Holehe + Sherlock + SpiderFoot.
- **Best paid:** Hunter.io + HaveIBeenPwned (+ Dehashed if legally cleared).
- **Best for automation:** Hunter.io + HIBP APIs; theHarvester for breadth.
- **Chains with:** domain → email patterns (Hunter) → breach check (HIBP/Dehashed) →
  identity pivot (Holehe/Sherlock) → phishing-surface (dnstwist).
- **Redundant set:** SpiderFoot/Recon-ng/Maltego overlap *everything* — they are
  competing frameworks, integrate at most one (SpiderFoot HX or modules) rather than
  duplicating its connectors natively.
- **Rate/legal:** **PII-heavy and legally sensitive.** Breach data (Dehashed/HIBP/
  LeakCheck) is regulated (GDPR/CCPA). Holehe/Sherlock are active against third-party
  platforms. **Strong legal gate + data-minimization required** (see D6/D10).

---

## CAT-9 — Code Repository & Secret Scanning

| Tool | P/A | Free/Paid | Automation | Best for | Notes |
|------|-----|-----------|------------|----------|-------|
| **TruffleHog** ⭐default | P/A | Free | Excellent CLI/API | Secret detection **with verification** | Verification (live API check) is active — make it a toggle. |
| **GitLeaks** ⭐default | P | Free | Excellent CLI/API | Fast regex/entropy secret scan (repos + history) | Pure passive scan of cloned code. |
| **GitHub Code Search API** ⭐default | P | Free | API | Org-wide secret/config discovery | Rate-limited; the highest-signal source. |
| **GitDorker / Gitrob** | P | Free | CLI | GitHub dork automation / sensitive files | GitDorker pairs dork lists w/ search API. |
| **Sourcegraph** | P | Freemium | API | Cross-repo semantic code search | Great for large estates; paid for private. |
| **Trivy (secret mode) / Semgrep / detect-secrets / git-secrets** | P | Free | CLI/API | Secrets in repos/containers/CI | Trivy/Semgrep also do SCA/SAST — useful in DevSecOps overlap. |
| **Repo-supervisor / Secret Bridge** | P | Free | CLI/API | Monitoring repos for leaks | Continuous-monitoring utilities. |

- **Best free:** GitHub Code Search + TruffleHog + GitLeaks.
- **Best paid:** Sourcegraph (large private estates).
- **Best for automation:** GitHub search (find repos) → clone → GitLeaks (fast) →
  TruffleHog (verify) → Semgrep (context).
- **Chains with:** org/domain/keyword → GitHub search → repo list → secret scan →
  finding (with the secret *redacted*, never stored raw). Verified cloud secret →
  CAT-7 cloud check.
- **Redundant set:** detect-secrets/git-secrets/Repo-supervisor overlap GitLeaks; pick
  GitLeaks + TruffleHog as the two-tool spine, Semgrep for code context.
- **Rate/legal:** Scanning *public* repos is passive/legal. GitHub API rate limits are
  strict (queue + token rotation). **Never store raw secrets** — store a hash +
  redacted preview + location. Verification calls (TruffleHog) actively hit third-party
  APIs — gate them.

---

## CAT-10 — Vulnerability Intelligence & CVE Correlation

| Tool | P/A | Free/Paid | Automation | Best for | Notes |
|------|-----|-----------|------------|----------|-------|
| **Nuclei** ⭐default | A | Free | Excellent CLI/API | Templated detection of known CVEs/exposures | The active correlation+detection engine. |
| **NVD / NIST API** ⭐default | P | Free | API | Authoritative CVE metadata (CVSS, CPE) | Source of truth for CVE details. Rate-limited (get an API key). |
| **EPSS (FIRST.org)** ⭐default | P | Free | API | Exploit *probability* score per CVE | Critical for prioritization (exploit-likelihood). |
| **Shodan CVE search / InternetDB** | P | Freemium/Free | API | "What CVEs does this IP likely have" | Maps banners→CVEs passively. |
| **Vulners** | P | Freemium | API | Aggregated vuln DB + exploit refs | Good single API for correlation. |
| **OSV.dev** | P | Free | API | Open-source dependency vulns | Pairs with Retire.js/SBOM data. |
| **Exploit-DB / Metasploit module index / Packetstorm / AttackerKB / VulDB** | P | Free/Freemium | Web/API | Exploit availability & context | Enrichment: "is there a public exploit?" — **reference only, no exploitation.** |

- **Best free:** Nuclei (detect) + NVD + EPSS (prioritize) + OSV.
- **Best paid:** Vulners (aggregation) / VulDB (depth).
- **Best for automation:** httpx/nmap fingerprint → CPE mapping → NVD (details) → EPSS
  (priority) → nuclei (confirm) → Shodan CVE (passive corroboration).
- **Chains with:** service+version (CAT-5) → CVE candidates (NVD/Vulners/Shodan) →
  EPSS+CVSS score → nuclei template to confirm → ranked finding.
- **Redundant set:** Exploit-DB/Packetstorm/AttackerKB/Metasploit-index all answer "is
  there an exploit"; pick **one** (Vulners aggregates several) for the platform.
- **Rate/legal:** Correlation is passive. **Nuclei detection is active** but
  non-exploitative (it checks presence, not pops shells). NVD requires an API key to
  avoid harsh throttling. **No exploitation tooling (Metasploit execution) is in scope
  — we index module *metadata* only.**

---

## Master "Default Wiring" Cheat Sheet

The minimal high-signal set the platform ships **on** by default (everything else is a
toggle):

```
Passive seed:     subfinder, crt.sh, CertSpotter, Chaos, SecurityTrails,
                  Shodan(InternetDB), Censys, Netlas, BGPView, RIPEstat,
                  ASNmap, IPinfo, GreyNoise
Passive enrich:   gau, Wayback CDX, GitHub search, GitLeaks, TruffleHog,
                  GrayhatWarfare, theHarvester, Hunter.io, HIBP,
                  NVD, EPSS, Vulners
Active verify:    dnsx, puredns(+massdns), httpx, naabu→Nmap, gowitness, wafw00f
Active deep:      katana, ParamSpider, xnLinkFinder, SecretFinder, sslyze,
                  WPScan/CMSeeK(conditional)
Active detect:    nuclei, Subjack/tko-subs (takeover), cloud_enum/S3Scanner
```

**Everything in this set is open-source/CLI/API and free-to-start**, with paid APIs
(SecurityTrails, Shodan credits, Hunter, HIBP, Vulners) as scale-up upgrades. This is
the lean-start budget posture the constraints asked for.
