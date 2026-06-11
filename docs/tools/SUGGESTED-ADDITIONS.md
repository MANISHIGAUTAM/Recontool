# Suggested Tool Additions (gap closers)

These tools are **not** in the extracted spreadsheet inventory (`data/tool_inventory.json` stays untouched). They are the additions the architecture review recommends to close the active-recon, glue, and noise-control gaps. Each has a capability doc in this folder marked `suggested_addition`. Wire them via `config/tools_generic.yaml`.

**Total suggested: 32**

## API & GraphQL recon

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [kiterunner](kiterunner.md) | active | `live_host, url` | `endpoint` | Modern apps are API-first; directory brute force misses API routes. |
| [graphw00f](graphw00f.md) | active | `live_host, url` | `tech` | Identifies GraphQL surface for follow-up introspection. |
| [clairvoyance](clairvoyance.md) | active | `url` | `endpoint` | Extracts the hidden API surface that feeds further testing. |

## ASN/IP/org OSINT

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [metabigor](metabigor.md) | passive | `org, asn, ip` | `cidr, ip, asn` | Free org -> netblock pivot; great unauthenticated ASN expansion. |

## Active vuln detection

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [dalfox](dalfox.md) | active | `url, param` | `finding` | Turns discovered params into validated findings; pairs with nuclei. |

## CIDR utility

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [mapcidr](mapcidr.md) | passive | `cidr, ip` | `ip, cidr` | The asn -> cidr -> ip expansion glue; without it ASN pivots dead-end. |

## Cert-to-host pivot

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [cero](cero.md) | passive | `ip, cidr` | `subdomain` | Turns network ranges back into hostnames — a real pivot CT logs miss (live cert SANs, not just logged issuance). |

## Content & directory discovery

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [ffuf](ffuf.md) | active | `live_host, url` | `url` | Core active recon gap. |
| [feroxbuster](feroxbuster.md) | active | `live_host, url` | `url` | Recursive-by-design dir brute force — pairs naturally with the engine's own recursion; pick ffuf OR feroxbuster as primary. |

## Crawling

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [gospider](gospider.md) | active | `live_host, url` | `url` | Alternative crawler; wire katana as primary, gospider as fallback. |

## Favicon pivot

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [FavFreak](favfreak.md) | passive | `live_host, url` | `tag` | Underused correlation: a favicon hash pivots to an org's other assets across the internet — a real recursion multiplier. |
| [fav-up](fav-up.md) | passive | `live_host, url` | `ip` | Helps de-cloak origin IPs behind a CDN via favicon hash search. |

## Glue / URL parsing

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [unfurl](unfurl.md) | passive | `url` | `domain, endpoint` | Decomposes URLs into typed keys — the bridge from url back to subdomain/endpoint/param entities. |

## Glue / dedupe

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [anew](anew.md) | passive | `any` | `any` | The single most important plumbing tool: gives you 'only the NEW keys this round' for free, which IS the recursion delta. |

## Glue / domain filter

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [dsieve](dsieve.md) | passive | `subdomain` | `subdomain` | Keeps the frontier focused on meaningful host levels. |

## Glue / fuzz prep

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [qsreplace](qsreplace.md) | passive | `url` | `url` | Normalizes parameterized URLs for dedupe and prepares fuzz targets. |

## Glue / pattern grep

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [gf](gf.md) | passive | `url` | `url` | Turns raw URL dumps into prioritized, classified leads. |

## JavaScript analysis

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [jsluice](jsluice.md) | passive | `js_file, url` | `url, secret, endpoint` | AST-based, more accurate than regex LinkFinder/SecretFinder; MULTI-MODE: urls -> endpoint, secrets -> secret. |
| [mantra](mantra.md) | passive | `js_file, url` | `secret` | Secret-focused JS miner; overlaps jsluice secrets — keep one primary. |

## Noise control / CDN exclusion

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [cdncheck](cdncheck.md) | passive | `ip, domain` | `tag` | Without CDN exclusion, recursion port-scans Cloudflare edge ranges and treats shared IPs as pivots — a major false-lead amplifier. |

## Parameter discovery

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [x8](x8.md) | active | `url` | `param` | Complements Arjun; finds undocumented params that become fuzz inputs. |

## Passive port scan

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [smap](smap.md) | passive | `ip, domain` | `service` | Cheap passive 'nmap' for the passive phase; defer real naabu/nmap to confirmed-live hosts only. |

## Port scanning

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [masscan](masscan.md) | active | `ip, cidr` | `host_port` | Fast wide sweep feeding nmap/fingerprintx; rate-limit aware. |

## Port scanning & service detection

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [Nmap](nmap.md) | active | `ip, live_host` | `service` | Run on confirmed-live hosts only; naabu for fast sweep, nmap for depth/NSE on interesting ports. |

## Service fingerprinting

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [fingerprintx](fingerprintx.md) | active | `host_port, service` | `service, tech` | Port scan gives open ports; fingerprintx says WHAT they are for non-web services httpx can't fingerprint. |

## Subdomain enum (code)

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [github-subdomains](github-subdomains.md) | passive | `domain` | `subdomain` | Code platforms leak internal hostnames passive DNS never sees. |
| [gitlab-subdomains](gitlab-subdomains.md) | passive | `domain` | `subdomain` | Same as github-subdomains for the GitLab ecosystem. |

## Subdomain permutation

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [alterx](alterx.md) | passive | `subdomain` | `subdomain` | Replaces AltDNS/dnsgen for cleaner, template-driven permutations; feeds the resolver, gated by wildcard filtering. |
| [dnsgen](dnsgen.md) | passive | `subdomain` | `subdomain` | Overlaps alterx/gotator — wire ONE permutation engine, not all three, to avoid redundant candidate explosion. |
| [gotator](gotator.md) | passive | `subdomain` | `subdomain` | Same role as alterx/dnsgen — keep as an alternative, not a parallel. |

## TLS/SSL analysis

| Tool | Class | Consumes | Produces | Why |
|------|-------|----------|----------|-----|
| [tlsx](tlsx.md) | passive | `live_host, ip` | `subdomain, cert, tech` | Live cert SANs are a subdomain SOURCE and a fingerprint input — a pivot CT-log search alone misses. |
| [SSLyze](sslyze.md) | active | `live_host, host_port` | `finding, tech` | Config-level TLS findings (weak ciphers, cert issues) tlsx skips. |
