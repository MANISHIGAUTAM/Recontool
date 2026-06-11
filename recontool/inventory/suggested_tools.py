"""Generate capability docs for SUGGESTED tool additions (gap-closing tools).

These are NOT in the extracted spreadsheet inventory (data/tool_inventory.json),
so they are kept strictly separate to preserve that file's provenance rule
(`extracted_from_spreadsheet`, never altered). Every doc this writes is marked
`suggested_addition` and is the authoritative home for the tools the
architecture review recommends adding.

Run:  python -m recontool.inventory.suggested_tools
Writes: docs/tools/<slug>.md for each tool below + docs/tools/SUGGESTED-ADDITIONS.md

Pure: stdlib only, no network. Re-running overwrites the suggested docs in place
(it never touches the 532 extracted docs, which have different slugs/provenance).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "docs" / "tools"


@dataclass
class Suggested:
    slug: str
    name: str
    klass: str           # passive | active | hybrid
    group: str           # which gap it closes
    consumes: str
    produces: str
    purpose: str
    invocation: str
    why: str             # why it's needed / what it dedupes
    integration: str = "cli"
    modes: list[str] = field(default_factory=list)  # multi-capability note


# Ordered by the gap groups from docs/pipeline/01-gap-analysis.md + the
# architecture review. Each closes a concrete hole in the recursive engine.
TOOLS: list[Suggested] = [
    # ── Noise control & DNS hygiene (HIGHEST priority for a recursive engine) ──
    Suggested("cdncheck", "cdncheck", "passive", "Noise control / CDN exclusion",
              "ip, domain", "tag",
              "Flags whether a host/IP is behind a CDN/WAF/cloud so the engine "
              "does not waste active scans on shared edge infrastructure.",
              "cdncheck -i <ip> -resp -json",
              "Without CDN exclusion, recursion port-scans Cloudflare edge ranges "
              "and treats shared IPs as pivots — a major false-lead amplifier."),
    Suggested("alterx", "alterx", "passive", "Subdomain permutation",
              "subdomain", "subdomain",
              "Pattern-based subdomain permutation engine (modern AltDNS) to "
              "generate candidate names for resolution.",
              "alterx -l subs.txt -enrich | dnsx -silent",
              "Replaces AltDNS/dnsgen for cleaner, template-driven permutations; "
              "feeds the resolver, gated by wildcard filtering."),
    Suggested("dnsgen", "dnsgen", "passive", "Subdomain permutation",
              "subdomain", "subdomain",
              "Generates permutations/word-mutations of known subdomains.",
              "dnsgen subs.txt | massdns -r resolvers.txt",
              "Overlaps alterx/gotator — wire ONE permutation engine, not all "
              "three, to avoid redundant candidate explosion."),
    Suggested("gotator", "gotator", "passive", "Subdomain permutation",
              "subdomain", "subdomain",
              "Permutation generator with depth/number controls.",
              "gotator -sub subs.txt -perm words.txt -depth 1",
              "Same role as alterx/dnsgen — keep as an alternative, not a parallel."),
    Suggested("cero", "cero", "passive", "Cert-to-host pivot",
              "ip, cidr", "subdomain",
              "Scrapes domain names from TLS certificates of an IP/CIDR range.",
              "cero <cidr-or-ip>",
              "Turns network ranges back into hostnames — a real pivot CT logs "
              "miss (live cert SANs, not just logged issuance)."),
    Suggested("mapcidr", "mapcidr", "passive", "CIDR utility",
              "cidr, ip", "ip, cidr",
              "Expand/aggregate CIDR ranges; pairs with asnmap to turn an ASN "
              "into scannable IPs.",
              "echo <cidr> | mapcidr -silent",
              "The asn -> cidr -> ip expansion glue; without it ASN pivots dead-end."),
    Suggested("smap", "smap", "passive", "Passive port scan",
              "ip, domain", "service",
              "Returns ports/services from Shodan's free InternetDB data — port "
              "intel WITHOUT sending packets.",
              "smap -iL hosts.txt",
              "Cheap passive 'nmap' for the passive phase; defer real naabu/nmap "
              "to confirmed-live hosts only."),
    # ── Glue / plumbing (makes output->input chaining actually work) ──────────
    Suggested("anew", "anew", "passive", "Glue / dedupe",
              "any", "any",
              "Append-only dedupe: adds only lines not already present in a file "
              "and prints them — the incremental delta primitive.",
              "cat new.txt | anew all_subs.txt",
              "The single most important plumbing tool: gives you 'only the NEW "
              "keys this round' for free, which IS the recursion delta."),
    Suggested("gf", "gf", "passive", "Glue / pattern grep",
              "url", "url",
              "Tomnomnom grep wrapper with curated patterns (ssrf, xss, redirect, "
              "idor) to surface interesting URLs from a large set.",
              "cat urls.txt | gf ssrf",
              "Turns raw URL dumps into prioritized, classified leads."),
    Suggested("unfurl", "unfurl", "passive", "Glue / URL parsing",
              "url", "domain, endpoint",
              "Extracts/format parts of URLs (domains, paths, params, keys) at scale.",
              "cat urls.txt | unfurl -u domains",
              "Decomposes URLs into typed keys — the bridge from url back to "
              "subdomain/endpoint/param entities."),
    Suggested("qsreplace", "qsreplace", "passive", "Glue / fuzz prep",
              "url", "url",
              "Swaps query-string values across a URL set (fuzzing prep).",
              "cat urls.txt | qsreplace FUZZ",
              "Normalizes parameterized URLs for dedupe and prepares fuzz targets."),
    Suggested("dsieve", "dsieve", "passive", "Glue / domain filter",
              "subdomain", "subdomain",
              "Filter/sort subdomains by level and extract the most relevant.",
              "cat subs.txt | dsieve -f 3",
              "Keeps the frontier focused on meaningful host levels."),
    # ── Active content / directory & API discovery ───────────────────────────
    Suggested("ffuf", "ffuf", "active", "Content & directory discovery",
              "live_host, url", "url",
              "Fast web fuzzer for directories, files, vhosts, and parameters.",
              "ffuf -u https://<host>/FUZZ -w wordlist.txt -mc 200,301,403",
              "Core active recon gap. MULTI-MODE: dir mode -> url file, vhost "
              "mode -> subdomain file, param mode -> param file (typed outputs).",
              modes=["dir->url", "vhost->subdomain", "param->param"]),
    Suggested("feroxbuster", "feroxbuster", "active", "Content & directory discovery",
              "live_host, url", "url",
              "Recursive content discovery (Rust) with auto-recursion into found dirs.",
              "feroxbuster -u https://<host> -w wordlist.txt --json",
              "Recursive-by-design dir brute force — pairs naturally with the "
              "engine's own recursion; pick ffuf OR feroxbuster as primary."),
    Suggested("kiterunner", "kiterunner", "active", "API & GraphQL recon",
              "live_host, url", "endpoint",
              "API route discovery using Assetnote route-based wordlists.",
              "kr scan https://<host> -w routes.kite",
              "Modern apps are API-first; directory brute force misses API routes."),
    Suggested("graphw00f", "graphw00f", "active", "API & GraphQL recon",
              "live_host, url", "tech",
              "Fingerprints GraphQL engines and detects introspection exposure.",
              "graphw00f -d -t https://<host>/graphql",
              "Identifies GraphQL surface for follow-up introspection."),
    Suggested("clairvoyance", "clairvoyance", "active", "API & GraphQL recon",
              "url", "endpoint",
              "Recovers a GraphQL schema when introspection is disabled.",
              "clairvoyance https://<host>/graphql -o schema.json",
              "Extracts the hidden API surface that feeds further testing."),
    Suggested("x8", "x8", "active", "Parameter discovery",
              "url", "param",
              "Hidden HTTP parameter discovery by response-diffing.",
              "x8 -u https://<host>/ -w params.txt",
              "Complements Arjun; finds undocumented params that become fuzz inputs."),
    # ── TLS / fingerprinting ─────────────────────────────────────────────────
    Suggested("tlsx", "tlsx", "passive", "TLS/SSL analysis",
              "live_host, ip", "subdomain, cert, tech",
              "TLS grabber: SANs, JARM, cipher, cert details from live endpoints.",
              "tlsx -l hosts.txt -san -cn -json",
              "Live cert SANs are a subdomain SOURCE and a fingerprint input — a "
              "pivot CT-log search alone misses. MULTI-MODE: -san -> subdomain, "
              "-jarm -> tech.",
              modes=["san->subdomain", "jarm/cipher->tech"]),
    Suggested("fingerprintx", "fingerprintx", "active", "Service fingerprinting",
              "host_port, service", "service, tech",
              "Fingerprints non-HTTP services (databases, RDP, SSH, etc.).",
              "fingerprintx -l host_ports.txt --json",
              "Port scan gives open ports; fingerprintx says WHAT they are for "
              "non-web services httpx can't fingerprint."),
    # ── JS analysis & crawling ───────────────────────────────────────────────
    Suggested("jsluice", "jsluice", "passive", "JavaScript analysis",
              "js_file, url", "url, secret, endpoint",
              "BishopFox JS analyzer: extracts URLs, endpoints, and secrets via AST.",
              "jsluice urls -i app.js ; jsluice secrets -i app.js",
              "AST-based, more accurate than regex LinkFinder/SecretFinder; "
              "MULTI-MODE: urls -> endpoint, secrets -> secret.",
              modes=["urls->endpoint", "secrets->secret"]),
    Suggested("mantra", "mantra", "passive", "JavaScript analysis",
              "js_file, url", "secret",
              "Hunts API keys/secrets in JS files and pages.",
              "cat urls.txt | mantra",
              "Secret-focused JS miner; overlaps jsluice secrets — keep one primary."),
    Suggested("gospider", "gospider", "active", "Crawling",
              "live_host, url", "url",
              "Fast web spider (alternative to katana/hakrawler).",
              "gospider -s https://<host> -o out -c 10 -d 3",
              "Alternative crawler; wire katana as primary, gospider as fallback."),
    # ── Favicon correlation ──────────────────────────────────────────────────
    Suggested("favfreak", "FavFreak", "passive", "Favicon pivot",
              "live_host, url", "tag",
              "Hashes favicons (mmh3) to fingerprint tech and find related hosts "
              "via Shodan/ZoomEye.",
              "cat hosts.txt | favfreak",
              "Underused correlation: a favicon hash pivots to an org's other "
              "assets across the internet — a real recursion multiplier."),
    Suggested("fav-up", "fav-up", "passive", "Favicon pivot",
              "live_host, url", "ip",
              "Maps favicon hashes to real IPs via Shodan (origin-IP discovery).",
              "python3 favUp.py -w <host> -sc",
              "Helps de-cloak origin IPs behind a CDN via favicon hash search."),
    # ── Active vuln (distinct from CVE intel) ────────────────────────────────
    Suggested("dalfox", "dalfox", "active", "Active vuln detection",
              "url, param", "finding",
              "Fast XSS scanner/parameter analyzer.",
              "dalfox file urls.txt --format json",
              "Turns discovered params into validated findings; pairs with nuclei."),
    # ── Subdomains from code platforms ───────────────────────────────────────
    Suggested("github-subdomains", "github-subdomains", "passive",
              "Subdomain enum (code)",
              "domain", "subdomain",
              "Harvests subdomains referenced in public GitHub code/issues.",
              "github-subdomains -d <domain> -t $GITHUB_TOKEN",
              "Code platforms leak internal hostnames passive DNS never sees."),
    Suggested("gitlab-subdomains", "gitlab-subdomains", "passive",
              "Subdomain enum (code)",
              "domain", "subdomain",
              "Subdomains referenced across public GitLab projects.",
              "gitlab-subdomains -d <domain> -t $GITLAB_TOKEN",
              "Same as github-subdomains for the GitLab ecosystem."),
    # ── Real, well-known tools that were wired but undocumented (orphans) ─────
    Suggested("nmap", "Nmap", "active", "Port scanning & service detection",
              "ip, live_host", "service",
              "The reference port scanner + NSE service/version detection.",
              "nmap -sV -Pn -oX out.xml <ip>",
              "Run on confirmed-live hosts only; naabu for fast sweep, nmap for "
              "depth/NSE on interesting ports."),
    Suggested("masscan", "masscan", "active", "Port scanning",
              "ip, cidr", "host_port",
              "Internet-scale asynchronous port sweeper.",
              "masscan <cidr> -p1-65535 --rate 1000 -oJ out.json",
              "Fast wide sweep feeding nmap/fingerprintx; rate-limit aware."),
    Suggested("metabigor", "metabigor", "passive", "ASN/IP/org OSINT",
              "org, asn, ip", "cidr, ip, asn",
              "OSINT ASN/IP/org discovery WITHOUT API keys.",
              "echo '<org>' | metabigor net --org",
              "Free org -> netblock pivot; great unauthenticated ASN expansion."),
    Suggested("sslyze", "SSLyze", "active", "TLS/SSL analysis",
              "live_host, host_port", "finding, tech",
              "Deep TLS configuration and vulnerability analyzer.",
              "sslyze --json_out out.json <host>:443",
              "Config-level TLS findings (weak ciphers, cert issues) tlsx skips."),
]


TEMPLATE = """# {name}

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `{slug}` · NOT in extracted inventory.

**Purpose.** {purpose}

| Field | Value |
|-------|-------|
| Closes gap | {group} |
| Classification | **{klass}** |
| Integration | {integration} |
| Consumes (canonical) | `{consumes}` |
| Produces (canonical) | `{produces}` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

{why}

## Invocation

```bash
{invocation}
```
> Confirm exact flags against the installed version before wiring.
{modes_block}
## Inputs / outputs

- **Consumes:** `{consumes}`
- **Produces:** `{produces}` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** {output_files}
- **Raw output:** `artifacts/<scan_id>/raw/{slug}/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `{first_consume}` key.
"""


def _modes_block(t: Suggested) -> str:
    if not t.modes:
        return ""
    rows = "\n".join(f"- `{m}`" for m in t.modes)
    return (
        "\n**Multi-mode tool.** Each mode produces a different entity type and "
        "writes a separate typed output file:\n" + rows + "\n"
    )


def _output_files(t: Suggested) -> str:
    prods = [p.strip() for p in t.produces.split(",") if p.strip() not in ("any", "")]
    if not prods:
        return f"`raw/{t.slug}/`"
    return ", ".join(f"`{t.slug}.{p}.jsonl`" for p in prods)


def build() -> None:
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for t in TOOLS:
        doc = TEMPLATE.format(
            name=t.name, slug=t.slug, purpose=t.purpose, group=t.group,
            klass=t.klass, integration=t.integration, consumes=t.consumes,
            produces=t.produces, why=t.why, invocation=t.invocation,
            modes_block=_modes_block(t), output_files=_output_files(t),
            first_consume=t.consumes.split(",")[0].strip(),
        )
        (TOOLS_DIR / f"{t.slug}.md").write_text(doc)
        written.append(t)

    # Index
    by_group: dict[str, list[Suggested]] = {}
    for t in written:
        by_group.setdefault(t.group, []).append(t)
    lines = [
        "# Suggested Tool Additions (gap closers)",
        "",
        "These tools are **not** in the extracted spreadsheet inventory "
        "(`data/tool_inventory.json` stays untouched). They are the additions the "
        "architecture review recommends to close the active-recon, glue, and "
        "noise-control gaps. Each has a capability doc in this folder marked "
        "`suggested_addition`. Wire them via `config/tools_generic.yaml`.",
        "",
        f"**Total suggested: {len(written)}**",
        "",
    ]
    for group in sorted(by_group):
        lines.append(f"## {group}")
        lines.append("")
        lines.append("| Tool | Class | Consumes | Produces | Why |")
        lines.append("|------|-------|----------|----------|-----|")
        for t in by_group[group]:
            lines.append(
                f"| [{t.name}]({t.slug}.md) | {t.klass} | `{t.consumes}` | "
                f"`{t.produces}` | {t.why.split('.')[0]}. |"
            )
        lines.append("")
    (TOOLS_DIR / "SUGGESTED-ADDITIONS.md").write_text("\n".join(lines))
    print(f"wrote {len(written)} suggested tool docs + SUGGESTED-ADDITIONS.md "
          f"to {TOOLS_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
