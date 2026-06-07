# Category-by-Category Milestones

Status of every category's implementation, with the atomic-check gate each must pass
before it's considered "done". Two implementation paths now exist:

- **Hand-written adapter** (`recontool/adapters/*.py`) — richer logic, used for the
  highest-value / most complex tools.
- **Generic spec** (`config/tools_generic.yaml`, executed by `recontool/adapters/generic.py`)
  — declarative, no Python; how the long tail is wired.

**Atomic-check gate (per tool):** C1 available · C2 live invocation · C3 parse (fixture)
· C4 normalize/dedupe · C5 scope · C6 chain (see `02-plan-of-action.md`).

Legend: ✅ runnable & tested · 🟡 partially wired · ⬜ templated (spec to be added)

---

## Executable coverage today

| # | Category | Stage | Hand-written adapters | Generic specs | Status |
|---|----------|-------|-----------------------|---------------|--------|
| 1 | Internet-wide search | S1 seed | uncover, shodan, internetdb, censys, netlas, leakix, fullhunt, urlscan, greynoise, criminalip, alienvault_otx | — | ✅ core wired |
| 2 | Passive DNS / subdomain | S1→S2 | crtsh, hackertarget, subfinder, dns_resolve | certspotter, assetfinder, findomain | ✅ core wired |
| 3 | WHOIS / ASN / BGP | S4 | — | asnmap, bgpview, ripestat | ✅ wired (asnmap→cidr; ripestat live-validated) |
| 4 | Dorking / URL recon | S3/S5 | — | gau, gauplus, waybackurls | 🟡 url harvest wired; dorking ⬜ |
| 5 | Web fingerprint / probe | S2/S5 | httpx_probe | — | ✅ probe wired; whatweb/wafw00f ⬜ |
| 6 | Historical / archive | S3 | wayback | waybackurls, gau | ✅ wired |
| 21 | Port scan / services | S4 | naabu (PortScan) | — | ✅ naabu + fallback; nmap deep ⬜ |
| 22 | JS analysis | S5 | js_analyze | katana | ✅ crawl + JS-secret wired |
| 24 | TLS / cert pivots | S4 | — | tlsx, cero | 🟡 wired (need a live cert host to validate) |
| 27 | Active vuln detection | S6 | nuclei | — | ✅ nuclei wired |
| 12 | Malware/IOC/CVE | S6 | internetdb (CVE hints) | — | 🟡 EPSS/NVD correlation ⬜ |
| 7 | Email / identity | overlay | — | — | ⬜ templated |
| 8 | Social media | overlay | — | — | ⬜ templated |
| 9 | Source-code / secrets | overlay | — | — | ⬜ templated (gitleaks/trufflehog next) |
| 10 | Cloud & storage | overlay | — | — | ⬜ templated (cloud_enum/s3scanner next) |
| 11 | Metadata / documents | overlay | — | — | ⬜ templated |
| 13 | Visual / screenshots | S5 | — | — | ⬜ templated (gowitness next) |
| 14 | Frameworks (engines) | engine | (the orchestrator itself) | — | ✅ n/a — we are the engine |
| 15 | Geo / wireless | overlay | — | — | ⬜ scope-dependent |
| 16 | Dark web | overlay | — | — | ⬜ templated |
| 17 | API intel feeds | enrich | (used across stages) | — | 🟡 providers wired in cat 1/3 |
| 18 | Reference indexes | — | — | — | n/a — not executed |
| 19 | Workflow presets | engine | (composite) | — | ✅ n/a — preset of S1-S6 |

**Live-validated this round:** certspotter (17 events on example.com), ripestat
(1394 CIDRs on AS15169), plus the existing Cat-1/2 hand-written adapters. bgpview is
correct but unreachable from the build sandbox (DNS) — degrades gracefully.

---

## Rollout order (do NOT integrate everything before each gate passes)

1. **Cat 2 (done)** — subdomain discovery is the root; everything depends on it. ✅
2. **Cat 1 + 3 (done)** — internet search + ASN expansion feed the IP/host set. ✅
3. **Cat 5 + 21 (done)** — httpx live-validation + port scan gate the active flow. ✅
4. **Cat 6 + 4 + 22 (mostly done)** — archive/url/JS harvest per live host. 🟡
5. **Cat 24 + 27 (wired)** — TLS pivots + nuclei findings. 🟡/✅
6. **Cat 12** — NVD/EPSS CVE correlation enrichment. ⬜ next
7. **Cat 9 + 10** — secrets (gitleaks/trufflehog) + cloud (cloud_enum/s3scanner). ⬜
8. **Cat 13** — gowitness screenshots. ⬜
9. **Cat 7/8/11/15/16** — OSINT/identity/geo/dark-web overlays (PII-gated). ⬜

Each step: add hand-written adapter or generic spec → add a C3 fixture test →
live C2 smoke → confirm C6 chaining → then advance.

---

## How to wire a remaining tool (the whole job is now a YAML block)

```yaml
# config/tools_generic.yaml
- name: rapiddns
  phase: p1_seed
  category: 2
  integration: api
  consumes: [domain]
  produces: [subdomain]
  endpoint: "https://rapiddns.io/subdomain/{domain}?full=1"
  parse:
    format: text
    line_regex: "<td>(?P<host>[a-z0-9._-]+)</td>"
    emit:
      - {entity: asset, value: "{host}", type: subdomain, scope_filter: subdomain}
```

Add a fixture test in `tests/atomic/test_generic_engine.py` and it's done — no Python.
The autoloader registers it into the pipeline automatically on next run.
