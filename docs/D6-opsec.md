# D6 — OPSEC & Legal Design

> **Disclaimer:** This is engineering guidance for building safety controls into the
> platform, not legal advice. Authorization scope and applicable law must be confirmed
> with counsel and the asset owner for every engagement.

The platform treats OPSEC and legality as **enforced controls**, not documentation.
The two structural guarantees from D4 (two-layer scope enforcement, hard
passive→active authorization gate) are the backbone; everything below builds on them.

---

## 1. Which Phases Leave No Trace on the Target

| Phase | Touches target? | Trace on target | Trace elsewhere |
|-------|-----------------|-----------------|-----------------|
| Seed normalize / scope | No | None | Local only |
| **P1 Seed discovery** | No | **None** — queries third-party indexes (CT, passive DNS, Shodan/Censys) | Your queries logged by those providers |
| **P2 Asset expansion** | No (passive sources) | **None** | Provider logs; CT log queries |
| **P3 Enrichment** | No* | **None*** | Provider logs |
| **AUTH GATE** | — | — | — |
| **P4 Live verify** | **Yes** | DNS resolver logs, **target firewall/IDS sees connections, port-scan signatures, HTTP access logs** | — |
| **P5 Deep enum** | **Yes** | **Heavy** — crawl traffic, param fuzzing, content brute-force in access/WAF logs | — |
| **P6 Vuln surface** | **Yes** | **Heavy** — nuclei probe signatures, repeated requests, scanner UA patterns | — |

\* P3 exceptions that *do* leave traces and are **off by default**:
- **TruffleHog `--only-verified`** actively validates creds against live services.
- **Holehe/Sherlock** probe third-party platforms (not your target, but observable there).
- **URLScan public submissions** expose the target URL to other URLScan users → use
  **unlisted/private** scans during live engagements.

**Design rule:** the UI and reports clearly label every phase Passive/Active and warn
before any step that produces a target-side trace.

---

## 2. Traffic Egress, Proxying & Rotation

```
                         ┌──────────────────────────────────────────┐
   PASSIVE traffic ─────►│ Direct egress OK (it's to third-party     │
   (P1-P3)               │ APIs, not the target). Still rotate to    │
                         │ avoid provider rate-bans on shared keys.  │
                         └──────────────────────────────────────────┘

                         ┌──────────────────────────────────────────┐
   ACTIVE traffic  ─────►│ EGRESS PROXY LAYER (mandatory for active) │
   (P4-P6)               │  • dedicated scan egress IPs (not corp)   │
                         │  • rotation pool (per-IP rate buckets)    │
                         │  • per-engagement source IP attribution   │
                         │  • optional SOCKS/HTTP proxy chains        │
                         └──────────────────────────────────────────┘
```

Rules baked into the platform:
- **Active scanning never egresses from the operator's primary/corporate IP.** Workers
  bind to a configured **scan egress pool**; the chosen `egress_ip` is recorded in
  `audit_log` for every active call.
- **Per-egress-IP rate buckets** (ADR-010) so rotation doesn't trip per-IP limits at
  the target or at API providers.
- **Sticky egress per engagement** when attribution/whitelisting matters (some clients
  whitelist your scanner IP — rotation would break that). Configurable per scope.
- **Proxy health checks** before use; dead proxy → quarantine, don't silently leak to
  direct egress.
- **DNS resolution** during active phases uses a curated trusted-resolver list
  (`dnsvalidator`-vetted) to avoid poisoning and to control which resolvers see queries.

---

## 3. API Key Management & Rotation (20+ services)

| Control | Implementation |
|--------|----------------|
| Storage | **Vault** (self-host) / cloud secrets manager. Never in `.env` outside local dev, never in git, never in logs. |
| Access | Adapters receive a **key reference**, fetch at runtime via short-lived token, drop from memory after use. |
| Rotation pools | Multiple keys per high-limit-pressure provider (GitHub PATs, Shodan, VT). Round-robin with per-key Redis rate buckets; auto-bench a key that returns 401/403. |
| Scheduled rotation | Periodic rotation job; keys carry `created_at`/`expires_at`; alert before expiry. |
| Per-workspace isolation | Tenant A's keys never used for tenant B's scans. Key→workspace binding enforced at gateway. |
| Blast-radius limit | A leaked key is scoped (read-only where the provider supports it) and individually revocable without downtime (pool drains the bad key). |
| Audit | Every key *use* logs (provider, key-id-hash, egress_ip, scan_id) — never the key value. |

---

## 4. Rate-Limit Profiles (stealth / normal / aggressive)

Profiles are first-class objects bound to a scan. They tune **every** active tool's
concurrency, QPS, port breadth, and timing simultaneously.

| Knob | `passive_only` | `stealth` | `normal` | `aggressive` |
|------|----------------|-----------|----------|--------------|
| Active phases | **disabled** | enabled (gated) | enabled | enabled |
| Global concurrency | n/a | very low | medium | high |
| DNS resolution QPS | n/a | throttled | medium | high |
| naabu ports | n/a | top-100 | top-1000 | full/-p- |
| naabu scan rate | n/a | slow | medium | fast |
| Nmap timing | n/a | `-T2` | `-T3` | `-T4` |
| httpx threads | n/a | low | medium | high |
| katana depth/rate | n/a | shallow/slow | medium | deep/fast |
| nuclei rate-limit | n/a | low + info/low/med tags | medium | high + all severities |
| Jitter/randomization | n/a | **high** (randomize order, sleep jitter) | some | none |
| Screenshot concurrency | n/a | low | medium | high |

**Stealth design intent:** spread requests over time, randomize host order, jitter
delays, minimize port breadth, prefer info/low nuclei tags first — to stay under typical
IDS/WAF thresholds. **Aggressive** is for authorized, time-boxed engagements where speed
beats subtlety (and the client expects the noise).

---

## 5. Scope Enforcement (hard blocks)

Two independent enforcement points (ADR-008) plus a kill switch:

```
1) GATEWAY check     — validates the scan request's seeds ⊆ allowed scope at submit time.
2) WORKER check      — EVERY active activity re-validates the exact target against the
                       compiled scope matcher (CIDR trie + domain-suffix set) BEFORE any
                       packet leaves. Violation → refuse + audit_log(action='scope.deny').
3) KILL SWITCH       — operator/API can halt a running scan instantly (Temporal cancel);
                       in-flight activities honor cancellation and stop egress.
```

Scope policy structure (from D3 `scope_policy`):
- `allow`: domains (with wildcard rules), CIDRs, ASNs.
- `deny`: explicit exclusions (these **override** allow — e.g., exclude a shared-host IP,
  a third-party SaaS subdomain, or a CDN range you must not scan).
- `wildcard_rules`: how `*.acme.com` expands and whether newly discovered apexes are
  auto-in-scope or require manual approval (default: **manual approval** for newly
  discovered *apex* domains; auto for subdomains of an approved apex).
- **Out-of-scope discoveries are still recorded** (as `out_of_scope` tagged assets) but
  **never actively touched** — useful intel, zero risk.

---

## 6. Audit Logging (full trace)

Every consequential action writes an `audit_log` row (D3): actor, action, tool, target,
**egress_ip**, rate_profile, timestamp, and detail. Specifically logged:
- Every external tool execution / API call (with egress IP + key-id hash).
- Every scope decision (allow/deny), especially **denials**.
- The passive→active authorization gate crossing (who authorized, when, scope id).
- Every data export and report generation (what left the platform, to whom).
- Every access to PII/breach data (CAT-8).
- AI/LLM report generations (prompt hash, model version, inputs) for reproducibility.

Audit logs are **append-only**, shipped to a separate store (Loki/S3), retained per
compliance (D3), and support legal hold.

---

## 7. Passive vs Active — Legal Framing by Jurisdiction (engineering view)

This drives *defaults*, not legal conclusions. The platform encodes conservative
defaults and surfaces warnings; counsel confirms specifics per engagement.

| Activity | General legal character | Platform default |
|----------|------------------------|------------------|
| Querying third-party indexes (Shodan/Censys/CT/passive-DNS) | Passive; you query *their* data, not the target | Allowed without active authorization |
| Reading public archives (Wayback/CommonCrawl) | Passive | Allowed |
| Scanning public GitHub / OSINT | Passive; respect provider TOS | Allowed; TOS-aware throttling |
| Breach/credential data (HIBP/Dehashed) | **Regulated PII** (GDPR/CCPA and similar) | **Legal gate + minimization + short TTL + audit** |
| DNS resolution / brute-force resolve | Mildly active; generally low-risk | Behind active gate (stealth defaults) |
| Port scanning | **Active**; legality varies by jurisdiction and authorization | **Requires explicit active authorization** |
| HTTP probing / crawling / fuzzing | **Active**; needs authorization | Requires active authorization |
| nuclei detection (non-exploit) | **Active** but non-destructive | Requires active authorization |
| Exploitation | Out of scope | **Not implemented** |

**Jurisdictional notes encoded as warnings (not legal advice):**
- **US:** Unauthorized access/abuse statutes (e.g., computer-fraud laws) make
  authorization paramount; recent guidance has narrowed some interpretations but
  **authorization scope is still the controlling factor** — never scan without it.
- **EU/UK:** Strong data-protection regimes (GDPR / UK GDPR + Data Protection Act) make
  **PII/breach handling** the highest-risk area; computer-misuse statutes govern active
  access. Data-minimization and lawful basis matter even for OSINT PII.
- **APAC:** Varies widely (e.g., national cybersecurity/data laws); some regions are
  stricter on cross-border data and active probing. Treat active scanning of
  APAC-hosted assets as requiring explicit, documented authorization.

**Encoded controls:** breach/PII modules carry a region-aware legal gate and the
shortest retention; the platform always prefers the more conservative default and logs
an explicit acknowledgement when an operator overrides it.

---

## 8. Per-Phase OPSEC Checklist (with severity)

Severity = impact if the control is missing. **CRIT** blocks launch; **HIGH** must ship
in MVP; **MED** before multi-tenant/scale.

### Input / Scope
- [ ] **CRIT** Scope policy defined and compiled before any activity runs.
- [ ] **CRIT** `active_authorized=false` by default; active phases unreachable until set.
- [ ] **HIGH** Deny-list overrides allow-list; third-party/CDN/shared ranges excludable.
- [ ] **MED** Newly discovered apex domains require manual scope approval.

### Passive (P1–P3)
- [ ] **HIGH** No active sub-steps run (TruffleHog verify / Holehe / Sherlock OFF by default).
- [ ] **HIGH** URLScan submissions are **unlisted/private** during engagements.
- [ ] **HIGH** Breach/PII modules behind legal gate + minimization + short TTL.
- [ ] **MED** Provider keys rotated; per-key rate buckets prevent shared-key bans.
- [ ] **MED** Passive results cached to reduce provider footprint and spend.

### Authorization Gate
- [ ] **CRIT** Crossing the gate requires explicit authorization tied to a scope id + actor, fully audited.
- [ ] **HIGH** Rate profile selected; `passive_only` cannot reach active phases.

### Active (P4–P6)
- [ ] **CRIT** Worker re-checks scope on **every** active target before egress.
- [ ] **CRIT** Active egress only via dedicated scan IP pool (never corp/primary IP).
- [ ] **HIGH** Per-egress-IP rate buckets; profile timing respected (stealth = jitter).
- [ ] **HIGH** Kill switch halts all in-flight egress immediately.
- [ ] **HIGH** nuclei runs **detection** templates only; no exploitation modules.
- [ ] **MED** Sticky egress option for client-whitelisted scanner IPs.
- [ ] **MED** Proxy health-checked; dead proxy quarantined, never silent fallback to direct.

### Data Handling / Output
- [ ] **CRIT** Secrets stored as hash + mask + location only; raw secret never persisted/logged.
- [ ] **HIGH** All exports audited (what, to whom, when).
- [ ] **HIGH** PII/breach data encrypted, shortest TTL, excluded from cold archive.
- [ ] **MED** AI/LLM path defaults to self-hosted model for sensitive workspaces; generations reproducible/audited.

### Platform / Continuous mode
- [ ] **HIGH** Continuous mode re-runs **passive** by default; active re-runs require standing authorization.
- [ ] **MED** Audit log append-only, shipped to separate store, supports legal hold.
- [ ] **MED** Alerting on new assets/findings does not leak target data to third-party chat/webhook beyond policy.
