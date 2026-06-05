# Gap Analysis — Missing Tools & Categories

Your 19 categories are strong on **discovery, OSINT, and intelligence**. The gaps are
concentrated in the **active web-recon and content-discovery** half of the kill chain —
the steps that turn "a list of live hosts" into "a list of attackable endpoints and
parameters." Below is what's missing and what I recommend adding.

> Verdict: your list is ~85% complete for an OSINT/ASM platform. The additions below
> close it to a full **bug-bounty / red-team recon** platform.

---

## A. Missing CATEGORIES (recommend adding 6)

| # | New Category | Why it's needed | Key tools |
|---|--------------|-----------------|-----------|
| **20** | **Content & Directory Discovery** | You have subdomain + URL discovery, but nothing that brute-forces hidden paths/files/dirs on a live host. This is core recon. | `ffuf`, `feroxbuster`, `dirsearch`, `gobuster` (dir mode), `dirb`, `kiterunner` |
| **21** | **Port Scanning & Service Detection** | Currently mixed into "Web Tech Fingerprinting" (Cat 5). Port/service discovery deserves its own stage — it feeds everything web. | `nmap`, `masscan`, `naabu`, `RustScan`, `smap`, `nmap NSE` |
| **22** | **JavaScript Analysis & Secret Extraction** | Scattered across Cat 4/9. JS mining (endpoints + secrets from live JS) is a distinct, high-value pipeline stage. | `LinkFinder`, `xnLinkFinder`, `SecretFinder`, `getJS`, `JSluice`, `Mantra`, `Retire.js` |
| **23** | **API & GraphQL Recon** | No coverage of API endpoint discovery, Swagger/OpenAPI hunting, or GraphQL introspection — modern apps are API-first. | `kiterunner`, `graphw00f`, `clairvoyance`, `swaggerhole`, `Arjun` (API params) |
| **24** | **TLS/SSL & Certificate Analysis** | CT logs are covered (Cat 2), but live TLS config/cipher analysis and cert→host pivoting aren't. | `tlsx`, `sslyze`, `testssl.sh`, `cero`, `openssl` |
| **25** | **Parameter Discovery & Fuzzing Prep** | Param mining exists in pieces (ParamSpider in Cat 4) but no dedicated stage feeding fuzzers. | `Arjun`, `ParamSpider`, `x8`, `ffuf` (param mode), `gf`, `qsreplace` |

**Optional / niche additions (lower priority):**
- **Mobile / APK Recon** — `apkleaks`, `MobSF`, `apktool`, `apkurlgrep` (only if mobile is in scope).
- **Vulnerability Scanning** as a distinct category — you have CVE *intel* (Cat 12) but
  `nuclei` (Cat 14) is the active scanner; a dedicated "Active Vuln Detection" stage
  (`nuclei`, `nikto`, `wpscan`, `dalfox`, `jaeles`) clarifies the flow.
- **Wordlists & Recon Resources** — not tools but essential inputs: `SecLists`,
  `Assetnote wordlists`, `commonspeak2`. Worth a managed resource section.

---

## B. Missing TOOLS within your existing categories

### Cat 2 (DNS/Subdomain) — modern ProjectDiscovery + pivots
- **`alterx`** — modern subdomain permutation engine (better AltDNS replacement).
- **`tlsx`** — TLS grabber; extracts SANs from live certs → new subdomains.
- **`cero`** — scrapes domains from TLS certs of an IP range.
- **`github-subdomains` / `gitlab-subdomains`** — subdomains from code platforms.
- **`mapcidr`** — CIDR expansion/aggregation utility (pairs with asnmap).
- **`cdncheck`** — flags which hosts are behind a CDN (avoid scanning CDN edge).
- **`smap`** — passive "nmap" using Shodan data (ports without scanning).
- **`dnsgen` / `gotator`** — permutation generators (you reference these; list them).

### Cat 3 (WHOIS/ASN/BGP)
- **`metabigor`** — OSINT ASN/IP/org discovery **without API keys** (great free pivot).
- **`asnmap`** (ProjectDiscovery) — already implied; ensure it's listed as primary.

### Cat 4 (Dorking/URL/JS)
- **`gf`** (Tomnomnom) — grep patterns to extract interesting URLs (ssrf, xss, redirects).
- **`unfurl`** — pull/format pieces of URLs (domains, paths, params) at scale.
- **`qsreplace`** — swap query-string values (fuzzing prep).
- **`anew`** — append-only dedupe utility; the glue for incremental pipelines.
- **`gospider`** — alternative crawler to katana/hakrawler.
- **`JSluice`** (BishopFox) — modern JS URL/secret extraction (better than LinkFinder).

### Cat 5 (Web Fingerprinting)
- **`tlsx`** — also a fingerprinting input (JARM, cipher, cert).
- **`fingerprintx`** — service fingerprinting for non-HTTP services.

### Cat 10 (Cloud)
- **`cloudlist`** (ProjectDiscovery) — enumerate assets from cloud provider APIs (with creds).
- **`trufflehog`** cloud verifiers — already in Cat 9.

### Cross-cutting utility/glue tools (the "plumbing" that makes pipelines work)
- **`anew`**, **`gf`**, **`unfurl`**, **`qsreplace`**, **`mapcidr`**, **`interactsh`**
  (OOB), **`uncover`** (search-engine wrapper — you have it in Cat 14), **`notify`**
  (alerting — you have it).
- **Favicon pivots:** **`favfreak`**, **`fav-up`** — hash favicons → find related hosts
  via Shodan/ZoomEye. Underrated correlation technique.

---

## C. What you do NOT need to add (already well-covered or redundant)

- Your search-engine list (Cat 1) is exhaustive — don't add more engines; `uncover`
  already wraps Shodan/Censys/FOFA/ZoomEye/Netlas in one CLI.
- Onion search (Cat 16) and people-search (Cat 7) are deeper than most platforms need;
  keep but de-prioritize for the core domain-recon flow.
- Many Cat 7/8 people-search tools overlap heavily — pick 2-3, skip the rest.

---

## D. Summary: the recommended final category set

```
EXISTING (keep all 19)                    ADD (6 core + optional)
 1  Internet-Wide Search & Asset Disc.    20  Content & Directory Discovery   ★
 2  Passive DNS & Subdomain Enum          21  Port Scanning & Service Detect  ★
 3  WHOIS / ASN / BGP / Network Intel     22  JavaScript Analysis & Secrets   ★
 4  Search Engine Dorking & Index         23  API & GraphQL Recon             ★
 5  Web Technology Fingerprinting         24  TLS/SSL & Certificate Analysis  ★
 6  Historical & Archive Recon            25  Parameter Discovery & Fuzz Prep ★
 7  Email / Username / Identity           ── optional ──
 8  Social Media Recon                    26  Mobile / APK Recon
 9  GitHub / GitLab / Source Code         27  Active Vulnerability Detection
10  Cloud & Storage Recon                 28  Wordlists & Recon Resources
11  Metadata & Document Recon
12  Malware / IOC / Threat Intel          ★ = high priority, closes the
13  Visual Recon & Screenshotting             active-recon gap
14  Frameworks & Automation Suites
15  Physical / Geo / Wireless
16  Dark Web & Onion Recon
17  APIs & Intelligence Feeds
18  Massive Living Indexes
19  Common Recon Workflows
```

These additions are reflected in `config/tools.yaml` (the machine-readable registry) and
in the per-category pipeline designs (`03-category-pipelines.md`).
