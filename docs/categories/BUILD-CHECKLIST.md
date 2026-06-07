# 28-Category Build Checklist

> Status reflects executable adapters in this repo. ✅ wired · 🟡 partial · ⬜ specced.

## System-wide checklist

- [x] Preserve all 28 categories (registry: `config/categories.yaml`)
- [x] Route seeds to the correct subset (`categories.route_seed`)
- [x] Merge all outputs into one canonical graph (`normalize/engine.py`)
- [x] Store raw artifacts separately (`core/artifacts.py`; content-addressing on roadmap)
- [x] Recurse only on new frontier entities (`orchestrator/pipeline.py`)
- [x] Hand off only validated live assets to active detection (auth gate + is_live filter)
- [x] Diffs/reports/graph view (`report.py`; diff engine on roadmap)
- [x] Provider quotas + backoff + circuit breakers (`net/circuit.py`, `net/rate_limiter.py`)
- [x] Checkpoint/resume + dead-letter handling (`models.Checkpoint/DeadLetter`, CLI `replay`)
- [x] Demo/test mode + mock environment + test-mode egress enforcement (`core/mode.py`, `testing/mock_env.py`)
- [x] Preflight health checks (`preflight.py`, CLI `preflight`)
- [x] Continuous diffing (`diff.py`, CLI `diff`)
- [ ] Tuned wordlists + regex packs from learnings (cat 25/28 — roadmap G3)
- [x] Archive/search/code/crawl loops linked via the graph bus

## Per-category implementation status

| # | Category | Stage | Active | Status | Adapters/notes |
|---|----------|-------|:------:|:------:|----------------|
| 1 | Internet-Wide Search & Asset Discovery | discover | no | ✅ | shodan, censys, netlas, leakix… |
| 2 | Passive DNS & Subdomain Enum | discover | no | ✅ | subfinder, amass_passive, crtsh, certspotter… |
| 3 | WHOIS / ASN / BGP / Network Intel | network | no | ✅ | asnmap, bgpview, ripestat, ipinfo… |
| 4 | Search Engine Dorking & Index | enrich | no | 🟡 | brave_search, mojeek, searxng, google_pse… |
| 5 | Web Technology Fingerprinting | validate | yes | ✅ | httpx, whatweb, webanalyze, wappalyzer… |
| 6 | Historical & Archive Recon | enrich | no | ✅ | wayback_cdx, common_crawl, gau, waybackurls… |
| 7 | Email / Username / Identity | overlay | no | ⬜ | hunter, theharvester, phonebook, hibp… |
| 8 | Social Media Recon | overlay | no | ⬜ | sherlock, maigret, blackbird, instaloader… |
| 9 | GitHub / GitLab / Source Code | enrich | no | ✅ | github_code, gitleaks, trufflehog, gitdorker… |
| 10 | Cloud & Storage Recon | enrich | yes | 🟡 | grayhatwarfare, cloud_enum, s3scanner, gcpbucketbrute… |
| 11 | Metadata & Document Recon | enrich | no | ⬜ | metagoofil, exiftool, tika, oletools… |
| 12 | Malware / IOC / Threat Intel | enrich | no | ✅ | virustotal, otx, threatfox, abuse_ch… |
| 13 | Visual Recon & Screenshotting | validate | yes | ✅ | gowitness, eyewitness, playwright, urlscan_screens… |
| 14 | Frameworks & Automation Suites | engine | no | ⬜ | bbot, amass, reconftw, spiderfoot… |
| 15 | Physical / Geo / Wireless | overlay | no | ⬜ | wigle, opencellid, flightradar24, adsbexchange… |
| 16 | Dark Web & Onion Recon | overlay | no | ⬜ | ahmia, onionsearch, intelx_tor, darksearch… |
| 17 | APIs & Intelligence Feeds | enrich | no | ⬜ | shodan_api, censys_api, securitytrails_api, whoisxml… |
| 18 | Massive Living Indexes | resource | no | ⬜ | osint_framework, awesome_osint, hacktricks, payloadsallthethings… |
| 19 | Common Recon Workflows | engine | no | ⬜ | preset_passive, preset_full, preset_continuous… |
| 20 | Content & Directory Discovery | deep | yes | ✅ | pydirb, ffuf, feroxbuster, dirsearch… |
| 21 | Port Scanning & Service Detect | network | yes | ✅ | naabu, nmap, masscan, rustscan… |
| 22 | JavaScript Analysis & Secrets | deep | no | ✅ | pycrawl, jsluice, linkfinder, secretfinder… |
| 23 | API & GraphQL Recon | deep | yes | 🟡 | graphw00f, clairvoyance, kiterunner, swaggerhole… |
| 24 | TLS/SSL & Certificate Analysis | validate | yes | ✅ | tlsx, sslyze, testssl, cero… |
| 25 | Parameter Discovery & Fuzz Prep | deep | yes | 🟡 | paramspider, arjun, x8, param_miner… |
| 26 | Mobile / APK Recon | deep | no | ⬜ | apkleaks, apkurlgrep, mobsf, apktool… |
| 27 | Active Vulnerability Detection | detect | yes | ✅ | nuclei, subjack, tko_subs, sslyze… |
| 28 | Wordlists & Recon Resources | resource | no | ⬜ | seclists, assetnote_wordlists, commonspeak2, tuned_generator… |

Full per-category contracts: [`CATEGORY-CONTRACTS.md`](CATEGORY-CONTRACTS.md).
Implementation roadmap: [`../blueprint/05-diff-ai-gaps-roadmap.md`](../blueprint/05-diff-ai-gaps-roadmap.md).