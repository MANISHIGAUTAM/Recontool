# D2 — Complete Recon Flow (Directed Graph)

This is the canonical end-to-end flow. It is a **directed acyclic graph of phases**;
within a phase, activities fan out in parallel. The hard rule: **no active phase can
start until the scope gate has approved the target set produced by passive phases.**

```
LEGEND
  [P] passive (no target contact)   [A] active (touches target)
  ◆ decision/gate                   ║ parallel fan-out
  → data handoff                    ⟳ feedback loop (re-feed discoveries)
```

---

## 0. INPUT LAYER  →  Normalize the seed

```
┌──────────────────────────────────────────────────────────────────────┐
│ INPUT: domain | IP | CIDR | ASN | company name | email domain |        │
│        github org | keyword                                            │
└───────────────────────────────┬──────────────────────────────────────┘
                                 ▼
                    ┌────────────────────────┐
                    │ SEED NORMALIZER         │
                    │ - classify input type   │
                    │ - expand company→domains │
                    │ - attach SCOPE policy    │
                    │ - assign scan_id         │
                    └────────────┬─────────────┘
                                 ▼
                    ◆ SCOPE GATE #1 (define authorized boundary)
                      in-scope / out-of-scope / wildcard rules loaded
                                 ▼
                         [ PASSIVE PIPELINE ]
```

The seed normalizer turns *any* input into a set of typed seeds and binds a **scope
policy** (allowlist of domains/CIDRs/ASNs, denylist, wildcard rules). Every downstream
record is stamped with `scan_id` + `scope_id`.

---

## PASSIVE PIPELINE (Phases 1–3) — zero target contact

### Phase 1 — Seed Discovery  `[P]`

```
                    ┌─────────────────────────── Phase 1: SEED DISCOVERY ───────────────────────────┐
   seed domains ──► ║ WHOIS/ASN        ║ CERT TRANSPARENCY ║ PASSIVE DNS      ║ INTERNET SEARCH      │
   seed IPs/CIDR ─► ║ • RIR WHOIS      ║ • crt.sh          ║ • SecurityTrails ║ • Shodan/InternetDB  │
   seed ASN ──────► ║ • BGPView        ║ • CertSpotter     ║ • VirusTotal     ║ • Censys             │
   org name ──────► ║ • RIPEstat       ║ • CTFR            ║ • DNSDB          ║ • Netlas             │
                    ║ • IPinfo         ║                   ║ • Chaos          ║ • LeakIX             │
                    └───────┬───────────────────┬──────────────────┬──────────────────┬─────────────┘
                            │                   │                  │                  │
                            └───────────────────┴───────┬──────────┴──────────────────┘
                                                         ▼
                                            RAW EVENTS → object store
                                                         ▼
                                            NORMALIZE → candidate assets
                                            (domains, subdomains, IPs, ASNs, certs)
```

**Output of Phase 1:** an unverified candidate set of subdomains, IPs, ASNs, and certs,
each tagged with its source(s).

### Phase 2 — Asset Expansion  `[P]`  (with feedback loops)

```
        candidate assets
              │
              ▼
   ┌─────────────────────── Phase 2: ASSET EXPANSION ───────────────────────┐
   ║ SUBDOMAIN ENUM      ║ ASN→CIDR→IP        ║ REVERSE WHOIS      ║ IDENTITY  │
   ║ • subfinder         ║ • ASNmap           ║ • org→domains      ║ • Hunter  │
   ║ • Amass (passive)   ║ • BGPView prefixes ║ • SecurityTrails   ║ • Holehe  │
   ║ • permutations      ║                    ║   reverse-whois    ║ • Sherlock│
   ║   (dnsgen/gotator)  ║                    ║                    ║ theHarvest│
   └──────────┬──────────┴─────────┬──────────┴──────────┬─────────┴───────────┘
              │                    │                     │
              ▼                    ▼                     ▼
        new subdomains       new IP ranges        new related domains
              │                    │                     │
              └────────────────────┴──────────⟳──────────┘
                       feed new domains BACK to Phase 1 CT/passive-DNS
                       (bounded recursion: max depth N, scope-checked)
                                     ▼
                          ◆ SCOPE GATE #1b (drop out-of-scope discoveries)
```

**Key mechanic — bounded recursion ⟳:** newly found apex/related domains are re-fed to
Phase 1 (CT logs, passive DNS) to find *their* subdomains, up to a configurable depth.
Every loop iteration re-checks scope so recursion can't wander out of bounds.

### Phase 3 — Intelligence Enrichment  `[P]`

```
        in-scope candidate assets
                  │
                  ▼
   ┌─────────────────────────── Phase 3: ENRICHMENT ───────────────────────────┐
   ║ HISTORICAL URLs   ║ CODE/SECRETS      ║ CLOUD ASSETS    ║ TECH/HISTORY      │
   ║ • gau             ║ • GitHub search   ║ • GrayhatWarfare║ • BuiltWith       │
   ║ • Wayback CDX     ║ • GitLeaks        ║   (passive)     ║ • Wappalyzer API  │
   ║                   ║ • TruffleHog*     ║                 ║ • Shodan tech     │
   ╠═══════════════════╬═══════════════════╬═════════════════╬═══════════════════╣
   ║ CREDS/BREACH      ║ THREAT-INTEL OVERLAY (tags, no new assets)              │
   ║ • HIBP            ║ • GreyNoise (is IP a mass-scanner?)                     │
   ║ • Dehashed**      ║ • AbuseIPDB (reputation)  • OTX (IOC)                   │
   └───────────────────┴─────────────────────────────────────────────────────┘
        *TruffleHog verify = active toggle   **breach data = legal gate
                  ▼
        NORMALIZE + CORRELATE → enriched canonical assets
        (each asset now has: sources[], tech[], history[], tags[], confidence)
```

**Output of passive pipeline:** a deduplicated, enriched, scored **candidate asset
inventory** — still *unverified live*. This is the maximum you can know without touching
the target. For pure-passive engagements (CTI, stealth), the flow can **stop here** and
report.

```
                  ▼
   ◆◆◆ SCOPE + AUTHORIZATION GATE #2 (HARD STOP) ◆◆◆
   Active phases require: explicit authorization flag == TRUE
                          AND target ∈ authorized scope
                          AND selected rate profile
   If not satisfied → STOP. Emit passive-only report.
```

---

## ACTIVE PIPELINE (Phases 4–6) — touches target, scope-gated

### Phase 4 — Live Asset Verification  `[A]`

```
   authorized candidate assets
              │
              ▼
   ┌──────────── Phase 4: LIVE VERIFICATION ────────────┐
   │ STEP 4.1  DNS RESOLVE + WILDCARD FILTER             │
   │   dnsx ──► puredns(+massdns) ──► drop wildcard junk │
   │           (resolvers validated by dnsvalidator)     │
   └───────────────────────┬─────────────────────────────┘
                            ▼  live, resolving hosts
   ┌─────────────────────────────────────────────────────┐
   │ STEP 4.2  PORT DISCOVERY (rate-profile aware)        │
   │   naabu (fast top-ports) ──► open ports              │
   │            │                                          │
   │            ▼                                          │
   │   Nmap -sV (deep, only on naabu-found ports)         │
   └───────────────────────┬─────────────────────────────┘
                            ▼  host:port services
   ┌─────────────────────────────────────────────────────┐
   │ STEP 4.3  HTTP LAYER  ║  STEP 4.4 VISUAL  ║ 4.5 WAF   │
   │   httpx               ║  gowitness         ║ wafw00f  │
   │   (status,title,tech, ║  (screenshots)     ║          │
   │    TLS,hash,CDN,server)                              │
   └───────────────────────┬─────────────────────────────┘
                            ▼
              NORMALIZE → live services + http endpoints
              tag: CDN? WAF? cloud? honeypot? (GreyNoise cross-check)
```

**Why this order:** resolve→filter wildcards *first* (or every later step scans
garbage), then ports (cheap, narrows surface), then HTTP only on responsive web ports,
then screenshots/WAF on confirmed web services. Each step shrinks the work for the next.

### Phase 5 — Deep Enumeration  `[A]`

```
   live web services
         │
         ▼
   ┌──────────────── Phase 5: DEEP ENUMERATION ────────────────┐
   ║ CRAWL             ║ PARAMS            ║ JS MINING          │
   ║ • katana          ║ • ParamSpider     ║ • xnLinkFinder     │
   ║   (JS-aware,      ║   (from archives) ║ • LinkFinder       │
   ║    headless)      ║ • Arjun (active   ║ • SecretFinder     │
   ║                   ║    param fuzz)    ║ • Retire.js        │
   ╠═══════════════════╬═══════════════════╬════════════════════╣
   ║ CONTENT DISCOVERY ║ CMS ENUM (conditional on fingerprint)  │
   ║ • ffuf/feroxbuster║ • WPScan / CMSeeK / droopescan         │
   ║   (wordlist)      ║ • API discovery (kiterunner)           │
   └─────────┬─────────┴────────────────────────────────────────┘
             │   ⟳ new endpoints/hosts discovered here
             │      are re-fed to httpx (Phase 4.3) to verify live
             ▼
   NORMALIZE → endpoints, parameters, JS secrets(redacted), tech versions
```

**Feedback loop ⟳:** crawling and content discovery surface *new* live endpoints and
sometimes new subdomains (from JS) — these loop back through httpx verification, then
re-enter Phase 5, bounded by depth.

### Phase 6 — Vulnerability Surface Mapping  `[A]` (detection only, no exploitation)

```
   verified services + endpoints + tech versions
                     │
                     ▼
   ┌──────────────── Phase 6: VULN SURFACE MAPPING ────────────────┐
   ║ KNOWN-VULN DETECT   ║ TAKEOVER          ║ TLS               │
   ║ • nuclei            ║ • Subjack         ║ • sslyze          │
   ║   (CVE/misconfig/   ║ • tko-subs        ║   (cipher/cert    │
   ║    exposure tmpl)   ║   (dangling CNAME)║    issues)        │
   ╠═════════════════════╬═══════════════════╬═══════════════════╣
   ║ CLOUD MISCONFIG     ║ SECRETS IN SOURCE ║ CVE CORRELATION   │
   ║ • cloud_enum        ║ • SecretFinder    ║ service+ver →     │
   ║ • S3Scanner         ║ • TruffleHog      ║ NVD + EPSS +      │
   ║                     ║   (verify toggle) ║ Vulners + Shodan  │
   └──────────┬──────────┴───────────────────┴───────────────────┘
              ▼
   NORMALIZE → FINDINGS (severity, confidence, evidence ref, EPSS×CVSS rank)
```

**CVE correlation logic (the brain of Phase 6):**
```
   service "nginx 1.18.0"  ─► map to CPE
                            ─► query NVD       → candidate CVEs + CVSS
                            ─► query EPSS       → exploit probability
                            ─► query Shodan CVE → does internet data corroborate?
                            ─► run matching nuclei template → CONFIRM presence
                            ─► emit FINDING with rank = f(CVSS, EPSS, exposure, asset_value)
```
nuclei is what turns a *theoretical* CVE match into a *confirmed* finding — without ever
exploiting it (it checks for the vulnerable condition's signature, not a working exploit).

---

## OUTPUT / REPORTING LAYER

```
   canonical assets + findings (Postgres)   graph (Neo4j)   raw (MinIO)   search (OpenSearch)
                          │
                          ▼
   ┌──────────────────── REPORTING / EXPORT ────────────────────┐
   │ • Deduplicated ASSET INVENTORY (domains/IPs/URLs/endpoints) │
   │ • Severity-tiered FINDINGS report (with evidence links)     │
   │ • Visual ATTACK-SURFACE MAP (graph render)                  │
   │ • DIFF view: what changed since last scan (EASM core)       │
   │ • EXPORTS: JSON / CSV / Markdown / PDF                       │
   │ • INTEGRATIONS: Burp import (URLs), Nmap XML, webhook/Slack  │
   │ • AI SUMMARY (optional): exec narrative + prioritized list   │
   └─────────────────────────────────────────────────────────────┘
                          │
                          ▼  (continuous mode only)
                ◆ DIFF ENGINE: new asset? new finding?
                  └─► ALERT (Slack/email/webhook)
                  └─► re-arm schedule → re-run passive pipeline
```

---

## The Whole Flow on One Page

```
INPUT → [normalize+scope#1]
   │
   ├─ PASSIVE ─────────────────────────────────────────────────────────────┐
   │   P1 Seed Discovery  (WHOIS/ASN, CT, passiveDNS, internet-search)      │
   │        ▼                                                                │
   │   P2 Asset Expansion (subfinder, ASNmap, reverse-whois, identity) ⟳────┤ (recurse→P1)
   │        ▼  scope#1b                                                      │
   │   P3 Enrichment      (gau, github/secrets, cloud, tech, breach, TI)    │
   └────────┬────────────────────────────────────────────────────────────────┘
            ▼
        ◆◆ SCOPE+AUTH GATE #2 (HARD STOP if not authorized) → else passive report
            ▼
   ┌─ ACTIVE ──────────────────────────────────────────────────────────────┐
   │   P4 Live Verify   (dnsx/puredns → naabu→Nmap → httpx → gowitness/waf) │
   │        ▼                                                                │
   │   P5 Deep Enum     (katana, ParamSpider/Arjun, JS-mining, ffuf, CMS) ⟳─┤ (recurse→P4)
   │        ▼                                                                │
   │   P6 Vuln Surface  (nuclei, takeover, sslyze, cloud-misconfig, CVE-corr)│
   └────────┬────────────────────────────────────────────────────────────────┘
            ▼
   NORMALIZE+CORRELATE+SCORE → STORAGE FABRIC
            ▼
   REPORT / EXPORT / GRAPH / DIFF → (continuous) ALERT + reschedule
```

---

## Per-Phase Trace / Observability Summary

| Phase | Contact w/ target? | Observable by target? | Gate before it | Typical duration (1 domain) |
|-------|--------------------|-----------------------|----------------|------------------------------|
| P1 Seed | No | No | Scope #1 | seconds–1 min |
| P2 Expansion | No (passive) | No | Scope #1b | 1–5 min |
| P3 Enrichment | No* | No* | — | 2–10 min |
| **Gate #2** | — | — | **Authorization** | — |
| P4 Live verify | Yes | **Yes** (DNS/ports/HTTP) | Auth + scope | 2–15 min |
| P5 Deep enum | Yes | **Yes** (crawl/fuzz) | Auth + scope | 5–60 min |
| P6 Vuln surface | Yes | **Yes** (nuclei probes) | Auth + scope | 5–60 min |

\* P3 is passive except the **TruffleHog verification toggle** and breach-data lookups
(legally gated), which is why it sits before Gate #2 but those sub-steps are off by
default. See `D6-opsec.md`.
