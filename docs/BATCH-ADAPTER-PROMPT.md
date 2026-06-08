# Batch Adapter Implementation Prompt

Use this prompt in batches of 20-50 tools. For each tool, it produces a complete YAML spec with REAL endpoints.

## THE PROMPT (copy for each batch):

You are implementing recon tool adapters for Recontool. For each tool below, research its actual API documentation and produce a COMPLETE YAML adapter spec.

FOR EACH TOOL PROVIDE:
1. REAL endpoint URL (not placeholder)
2. Auth method and header/param name
3. Input parameter ({domain}, {ip}, {subdomain}, {url})
4. Response format and JSON path to results
5. Rate limit and free tier info
6. Output entity type
7. Docker install command (if CLI)
8. Whether it can run in parallel

OUTPUT FORMAT:
```yaml
  - name: tool_name
    phase: p1_seed
    category: 2
    integration: api
    is_active: false
    consumes: ["domain"]
    produces: ["subdomain"]
    requires_key: TOOL_API_KEY
    key_optional: true
    endpoint: "https://real-api.com/v1/search?q={domain}"
    headers: {Authorization: "Bearer {key}"}
    bucket: tool_name
    timeout: 20
    parse:
      format: json
      list_path: "data"
      emit:
        - {entity: asset, value: "{hostname}", type: subdomain, scope_filter: subdomain}
```

## BATCHES:

### Batch 1 (50 highest-value API tools):
securitytrails, virustotal, chaos, binaryedge, onyphe, zoomeye, fofa, bufferover, riddler, threatminer, robtex, viewdns, dnsdb, passivetotal, spyse, dnsdumpster, rapiddns, commoncrawl, publicwww, grep_app, sourcegraph, dehashed, leakcheck, intelx, pulsedive, maltiverse, hybrid_analysis, triage, bazaar, urlhaus, phishtank, openphish, ransomwhere, feodotracker, sslmate, facebook_ct, google_ct, entrust_ct, sectigo_ct, buypass_ct, letsencrypt_ct, cloudflare_ct, digicert_ct, trustwave_ct, comodo_ct, whoisxml, domaintools, riskiq, passivedns, dnstwist

### Batch 2 (50 CLI tools):
amass, masscan, rustscan, nikto, whatweb, wappalyzer, eyewitness, fierce, dnsrecon, theHarvester, recon-ng, photon, paramspider, dirsearch, gobuster, feroxbuster, hakrawler, gospider, meg, getallurls, subjs, linkfinder, secretfinder, trufflehog, gitrob, git-secrets, shhgit, detect-secrets, bandit, safety, cloudsplaining, prowler, scoutsuite, cloudfox, pacu, weirdaal, bucket_finder, lazys3, mass3, slurp, gcpbucketbrute, testssl, sslscan, certgraph, ct_exposer, sublister, dnscan, fierce, shuffledns, massdns

### Batches 3-10: Remaining 391 tools grouped by category
