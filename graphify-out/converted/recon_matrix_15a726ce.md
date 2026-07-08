<!-- converted from recon_matrix.xlsx -->

## Sheet: Legend
| Recon Execution Matrix |  |
| --- | --- |
| Generated from | catalog.load_all_tools() — same source as the DB seeder |
| Totals | 563 tools | 71 runnable | 88 web-only (kept) | 32 suggested additions |
| READ THIS FIRST |  |
| This workbook is the PLANNING mirror of the runtime DB matrix. | The live database is two tables: tool_row (this 'Tools' sheet) + work_item (the 'WorkQueue' sheet). Seed/query with `python -m recontool.inventory.seed_matrix`. |
| Nothing is eliminated. | Web-only / no-integration tools are KEPT and flagged (grey rows), never removed — a later UI can still surface them. |
| Routing is deterministic, not AI. | entity_type -> tools whose consumes includes it, WITH subsumption: a subdomain also matches domain-consuming tools (that is how recursion fans out). See the 'Routing' sheet — it matches the runtime Router. |
| Runnable vs available | Green = real runnable contract today. Yellow = documented stub awaiting a contract. Grey = web-only/manual. All are available; default_on marks the recommended profile that runs out of the box. |
| Typed output files | Every run writes raw/<slug>/ AND out/<key>/<slug>.<produced_type>.jsonl. Multi-mode tools write one typed file per produced type. |
## Sheet: Tools
| # | name | slug | category | class | integration | source | consumes (canonical) | produces (canonical) | runnable | default_on | web_only | output_files (convention) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Abuse.ch | abuse-ch | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | abuse-ch.finding.jsonl |
| 2 | AbuseIPDB | abuseipdb | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | abuseipdb.cidr.jsonl |
| 3 | ADSBExchange | adsbexchange | 15 | passive | api | extracted | org, coords | finding |  |  |  | adsbexchange.finding.jsonl |
| 4 | AFRINIC | afrinic | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | afrinic.cidr.jsonl |
| 5 | Ahmia | ahmia | 1 | passive | api | extracted | domain | ip |  |  |  | ahmia.ip.jsonl |
| 6 | AlienVault OTX | alienvault-otx | 12 | passive | api | extracted | domain | subdomain | yes | yes |  | alienvault-otx.subdomain.jsonl |
| 7 | AlienVault OTX API | alienvault-otx-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | alienvault-otx-api.service.jsonl |
| 8 | AlienVault OTX Pulse Archive | alienvault-otx-pulse-archive | 6 | passive | api | extracted | domain, live_host | url |  |  |  | alienvault-otx-pulse-archive.url.jsonl |
| 9 | AlienVault OTX Search | alienvault-otx-search | 4 | passive | api | extracted | domain, live_host | url |  |  |  | alienvault-otx-search.url.jsonl |
| 10 | AltDNS | altdns | 2 | active | cli | extracted | domain | subdomain |  |  |  | altdns.subdomain.jsonl |
| 11 | Amass | amass | 2 | hybrid | cli | extracted | domain | subdomain | yes | yes |  | amass.subdomain.jsonl |
| 12 | Amass Passive Mode | amass-passive-mode | 19 | passive | cli | extracted | domain | subdomain |  |  |  | amass-passive-mode.subdomain.jsonl |
| 13 | Anomali | anomali | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | anomali.finding.jsonl |
| 14 | ANY.RUN | any-run | 12 | active | api | extracted | ip, domain, service | finding |  |  |  | any-run.finding.jsonl |
| 15 | APNIC | apnic | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | apnic.cidr.jsonl |
| 16 | Apollo.io | apollo-io | 7 | passive | api | extracted | domain, email | email |  |  |  | apollo-io.email.jsonl |
| 17 | Appalyzer | appalyzer | 5 | passive | api | extracted | live_host | tech |  |  |  | appalyzer.tech.jsonl |
| 18 | Aquatone | aquatone | 2 | active | cli | extracted | domain | subdomain |  |  |  | aquatone.subdomain.jsonl |
| 19 | Arachni | arachni | 5 | active | cli | extracted | live_host | tech |  |  |  | arachni.tech.jsonl |
| 20 | Archive.today | archive-today | 6 | passive | web | extracted | domain, live_host | url |  |  | yes | archive-today.url.jsonl |
| 21 | ARIN | arin | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | arin.cidr.jsonl |
| 22 | Arjun | arjun | 4 | active | cli | extracted | domain, live_host | url |  |  |  | arjun.url.jsonl |
| 23 | Arquivo.pt | arquivo-pt | 6 | passive | api | extracted | domain, live_host | url |  |  |  | arquivo-pt.url.jsonl |
| 24 | ASM tools | asm-tools | 14 | hybrid | cli | extracted | domain | any |  |  |  | raw/<slug>/ |
| 25 | ASNLookup | asnlookup | 2 | passive | cli | extracted | domain | subdomain |  |  |  | asnlookup.subdomain.jsonl |
| 26 | ASNmap | asnmap | 2 | passive | cli | extracted | domain | cidr | yes | yes |  | asnmap.cidr.jsonl |
| 27 | assetfinder | assetfinder | 2 | passive | cli | extracted | domain | subdomain | yes | yes |  | assetfinder.subdomain.jsonl |
| 28 | AttackSurfaceMapper | attacksurfacemapper | 14 | hybrid | cli | extracted | domain | any |  |  |  | raw/<slug>/ |
| 29 | Awesome Bug Bounty | awesome-bug-bounty | 18 | passive | web | extracted | seed | seed |  |  | yes | raw/<slug>/ |
| 30 | Awesome DFIR | awesome-dfir | 18 | passive | web | extracted | seed | seed |  |  | yes | raw/<slug>/ |
| 31 | Awesome Honeypots | awesome-honeypots | 18 | passive | web | extracted | seed | seed |  |  | yes | raw/<slug>/ |
| 32 | Awesome Incident Response | awesome-incident-response | 18 | passive | web | extracted | seed | seed |  |  | yes | raw/<slug>/ |
| 33 | Awesome Malware Analysis | awesome-malware-analysis | 18 | passive | web | extracted | seed | seed |  |  | yes | raw/<slug>/ |
| 34 | Awesome OSINT For Everything | awesome-osint-for-everything | 18 | passive | web | extracted | seed | seed |  |  | yes | raw/<slug>/ |
| 35 | Awesome Pentest | awesome-pentest | 18 | passive | web | extracted | seed | seed |  |  | yes | raw/<slug>/ |
| 36 | Awesome Search Engines | awesome-search-engines | 18 | passive | web | extracted | seed | seed |  |  | yes | raw/<slug>/ |
| 37 | Awesome Threat Intelligence | awesome-threat-intelligence | 18 | passive | web | extracted | seed | seed |  |  | yes | raw/<slug>/ |
| 38 | awesome-osint | awesome-osint | 18 | passive | web | extracted | seed | seed |  |  | yes | raw/<slug>/ |
| 39 | AWSBucketDump | awsbucketdump | 10 | active | cli | extracted | org, keyword | bucket |  |  |  | awsbucketdump.bucket.jsonl |
| 40 | AzureHound | azurehound | 10 | active | cli | extracted | org, keyword | bucket |  |  |  | azurehound.bucket.jsonl |
| 41 | Baidu Search | baidu-search | 1 | passive | api | extracted | domain | ip |  |  |  | baidu-search.ip.jsonl |
| 42 | BBOT | bbot | 2 | hybrid | cli | extracted | domain | subdomain |  |  |  | bbot.subdomain.jsonl |
| 43 | BeenVerified | beenverified | 7 | passive | api | extracted | domain, email | email |  |  |  | beenverified.email.jsonl |
| 44 | bgp.he.net | bgp-he-net | 3 | passive | web | extracted | ip, asn | cidr |  |  | yes | bgp-he-net.cidr.jsonl |
| 45 | BGPView | bgpview | 3 | passive | api | extracted | asn | cidr | yes | yes |  | bgpview.cidr.jsonl |
| 46 | BinaryEdge | binaryedge | 1 | passive | api | extracted | domain | ip |  |  |  | binaryedge.ip.jsonl |
| 47 | BinaryEdge API | binaryedge-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | binaryedge-api.service.jsonl |
| 48 | BinaryEdge Hunt | binaryedge-hunt | 1 | passive | api | extracted | domain | ip |  |  |  | binaryedge-hunt.ip.jsonl |
| 49 | Bing Dorks | bing-dorks | 4 | passive | web | extracted | domain, live_host | url |  |  | yes | bing-dorks.url.jsonl |
| 50 | Bing Search | bing-search | 1 | passive | api | extracted | domain | ip |  |  |  | bing-search.ip.jsonl |
| 51 | Binwalk | binwalk | 11 | passive | cli | extracted | file, url | finding |  |  |  | binwalk.finding.jsonl |
| 52 | Bitbucket | bitbucket | 9 | passive | cli | extracted | org, domain | secret |  |  |  | bitbucket.secret.jsonl |
| 53 | BlackArch Recon Category | blackarch-recon-category | 18 | hybrid | cli | extracted | seed | seed |  |  |  | raw/<slug>/ |
| 54 | Blackbird | blackbird | 7 | passive | cli | extracted | domain, email | email |  |  |  | blackbird.email.jsonl |
| 55 | BlindElephant | blindelephant | 5 | active | cli | extracted | live_host | tech |  |  |  | blindelephant.tech.jsonl |
| 56 | BlobHunter | blobhunter | 10 | active | cli | extracted | org, keyword | bucket |  |  |  | blobhunter.bucket.jsonl |
| 57 | Botometer | botometer | 8 | passive | api | extracted | username, org | finding |  |  |  | botometer.finding.jsonl |
| 58 | BreachDirectory | breachdirectory | 7 | passive | api | extracted | domain, email | email |  |  |  | breachdirectory.email.jsonl |
| 59 | BSSID Search | bssid-search | 15 | passive | api | extracted | org, coords | finding |  |  |  | bssid-search.finding.jsonl |
| 60 | bucket-stream | bucket-stream | 10 | passive | cli | extracted | org, keyword | bucket |  |  |  | bucket-stream.bucket.jsonl |
| 61 | bucket_finder | bucket-finder | 10 | active | cli | extracted | org, keyword | bucket |  |  |  | bucket-finder.bucket.jsonl |
| 62 | BucketLoot | bucketloot | 10 | active | cli | extracted | org, keyword | bucket |  |  |  | bucketloot.bucket.jsonl |
| 63 | BuckHacker | buckhacker | 10 | active | cli | extracted | org, keyword | bucket |  |  |  | buckhacker.bucket.jsonl |
| 64 | BufferOver | bufferover | 2 | passive | api | extracted | domain | subdomain |  |  |  | bufferover.subdomain.jsonl |
| 65 | Bug Bounty Recon Collection | bug-bounty-recon-collection | 18 | passive | web | extracted | seed | seed |  |  | yes | raw/<slug>/ |
| 66 | BuiltWith | builtwith | 5 | passive | api | extracted | live_host | tech |  |  |  | builtwith.tech.jsonl |
| 67 | BuiltWith API | builtwith-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | builtwith-api.service.jsonl |
| 68 | BuiltWith Historical Lookup | builtwith-historical-lookup | 6 | passive | api | extracted | domain, live_host | url |  |  |  | builtwith-historical-lookup.url.jsonl |
| 69 | BuiltWith Lookup | builtwith-lookup | 1 | passive | api | extracted | domain | ip |  |  |  | builtwith-lookup.ip.jsonl |
| 70 | BuiltWith Trends | builtwith-trends | 1 | passive | api | extracted | domain | ip |  |  |  | builtwith-trends.ip.jsonl |
| 71 | bulk_extractor | bulk-extractor | 11 | passive | cli | extracted | file, url | finding |  |  |  | bulk-extractor.finding.jsonl |
| 72 | CachedPages | cachedpages | 6 | passive | web | extracted | domain, live_host | url |  |  | yes | cachedpages.url.jsonl |
| 73 | CachedView | cachedview | 6 | passive | web | extracted | domain, live_host | url |  |  | yes | cachedview.url.jsonl |
| 74 | CAIDA Tools | caida-tools | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | caida-tools.cidr.jsonl |
| 75 | Cariddi | cariddi | 4 | hybrid | cli | extracted | domain, live_host | url |  |  |  | cariddi.url.jsonl |
| 76 | CellMapper | cellmapper | 15 | passive | api | extracted | org, coords | finding |  |  |  | cellmapper.finding.jsonl |
| 77 | Censys | censys | 1 | passive | api | extracted | domain | cert | yes | yes |  | censys.cert.jsonl |
| 78 | Censys API | censys-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | censys-api.service.jsonl |
| 79 | Censys ASM | censys-asm | 1 | passive | web | extracted | domain | ip |  |  | yes | censys-asm.ip.jsonl |
| 80 | Censys ASN Search | censys-asn-search | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | censys-asn-search.cidr.jsonl |
| 81 | Censys screenshots | censys-screenshots | 13 | passive | api | extracted | live_host | screenshot |  |  |  | censys-screenshots.screenshot.jsonl |
| 82 | CertDB | certdb | 2 | passive | api | extracted | domain | subdomain |  |  |  | certdb.subdomain.jsonl |
| 83 | Certificate Transparency Search | certificate-transparency-search | 2 | passive | api | extracted | domain | subdomain |  |  |  | certificate-transparency-search.subdomain.jsonl |
| 84 | CertSpotter | certspotter | 2 | passive | api | extracted | domain | subdomain | yes | yes |  | certspotter.subdomain.jsonl |
| 85 | Chaos | chaos | 2 | passive | api | extracted | domain | subdomain | yes | yes |  | chaos.subdomain.jsonl |
| 86 | Chaos Dataset | chaos-dataset | 2 | passive | api | extracted | domain | subdomain |  |  |  | chaos-dataset.subdomain.jsonl |
| 87 | CIDR Report | cidr-report | 3 | passive | web | extracted | ip, asn | cidr |  |  | yes | cidr-report.cidr.jsonl |
| 88 | CIRCL CVE Search | circl-cve-search | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | circl-cve-search.finding.jsonl |
| 89 | CIRCL Passive DNS | circl-passive-dns | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | circl-passive-dns.cidr.jsonl |
| 90 | Clearbit | clearbit | 7 | passive | api | extracted | domain, email | email |  |  |  | clearbit.email.jsonl |
| 91 | Clearbit API | clearbit-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | clearbit-api.service.jsonl |
| 92 | cloud_enum | cloud-enum | 10 | hybrid | cli | extracted | keyword | bucket | yes | yes |  | cloud-enum.bucket.jsonl |
| 93 | CloudBrute | cloudbrute | 10 | active | cli | extracted | org, keyword | bucket |  |  |  | cloudbrute.bucket.jsonl |
| 94 | CloudFail | cloudfail | 10 | passive | cli | extracted | org, keyword | bucket |  |  |  | cloudfail.bucket.jsonl |
| 95 | Cloudflare | cloudflare | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | cloudflare.cidr.jsonl |
| 96 | cloudfox | cloudfox | 10 | hybrid | cli | extracted | org, keyword | bucket |  |  |  | cloudfox.bucket.jsonl |
| 97 | cloudlist | cloudlist | 10 | passive | cli | extracted | org, keyword | bucket |  |  |  | cloudlist.bucket.jsonl |
| 98 | cloudsplaining | cloudsplaining | 10 | passive | cli | extracted | org, keyword | bucket |  |  |  | cloudsplaining.bucket.jsonl |
| 99 | CMSeeK | cmseek | 5 | active | cli | extracted | live_host | tech |  |  |  | cmseek.tech.jsonl |
| 100 | CMSmap | cmsmap | 5 | active | cli | extracted | live_host | tech |  |  |  | cmsmap.tech.jsonl |
| 101 | Common Crawl | common-crawl | 4 | passive | api | extracted | domain, live_host | url |  |  |  | common-crawl.url.jsonl |
| 102 | Creepy | creepy | 7 | passive | cli | extracted | domain, email | email |  |  |  | creepy.email.jsonl |
| 103 | Criminal IP | criminal-ip | 1 | passive | api | extracted | domain | service | yes | yes |  | criminal-ip.service.jsonl |
| 104 | CriminalIP API | criminalip-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | criminalip-api.service.jsonl |
| 105 | CriminalIP ASM | criminalip-asm | 1 | passive | api | extracted | domain | ip |  |  |  | criminalip-asm.ip.jsonl |
| 106 | CriminalIP IP Search | criminalip-ip-search | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | criminalip-ip-search.cidr.jsonl |
| 107 | crobat | crobat | 2 | passive | cli | extracted | domain | subdomain |  |  |  | crobat.subdomain.jsonl |
| 108 | CrossLinked | crosslinked | 7 | passive | cli | extracted | domain, email | email |  |  |  | crosslinked.email.jsonl |
| 109 | crt.sh | crt-sh | 2 | passive | api | extracted | domain | subdomain | yes | yes | yes | crt-sh.subdomain.jsonl |
| 110 | CTFR | ctfr | 2 | passive | cli | extracted | domain | subdomain |  |  |  | ctfr.subdomain.jsonl |
| 111 | CVE Details | cve-details | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | cve-details.finding.jsonl |
| 112 | Cyber Detective OSINT Tools Collection | cyber-detective-osint-tools-collection | 18 | passive | web | extracted | seed | seed |  |  | yes | raw/<slug>/ |
| 113 | Cymru Hash Registry | cymru-hash-registry | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | cymru-hash-registry.cidr.jsonl |
| 114 | Dark.fail | dark-fail | 16 | passive | web | extracted | keyword, domain | finding |  |  | yes | dark-fail.finding.jsonl |
| 115 | DarkSearch | darksearch | 16 | passive | api | extracted | keyword, domain | finding |  |  |  | darksearch.finding.jsonl |
| 116 | Darkweb Link Lists | darkweb-link-lists | 16 | passive | web | extracted | keyword, domain | finding |  |  | yes | darkweb-link-lists.finding.jsonl |
| 117 | Datasploit | datasploit | 14 | passive | cli | extracted | domain | any |  |  |  | raw/<slug>/ |
| 118 | Datasploit Framework | datasploit-framework | 14 | passive | cli | extracted | domain | any |  |  |  | raw/<slug>/ |
| 119 | Deep Web Search Engines | deep-web-search-engines | 16 | passive | web | extracted | keyword, domain | finding |  |  | yes | deep-web-search-engines.finding.jsonl |
| 120 | DeepSearch | deepsearch | 16 | passive | api | extracted | keyword, domain | finding |  |  |  | deepsearch.finding.jsonl |
| 121 | DeHashed | dehashed | 7 | passive | api | extracted | domain, email | email |  |  |  | dehashed.email.jsonl |
| 122 | detect-secrets | detect-secrets | 9 | passive | cli | extracted | org, domain | secret |  |  |  | detect-secrets.secret.jsonl |
| 123 | Digitorus CT Search | digitorus-ct-search | 2 | passive | web | extracted | domain | subdomain |  |  | yes | digitorus-ct-search.subdomain.jsonl |
| 124 | DNS History Lookup | dns-history-lookup | 2 | passive | api | extracted | domain | subdomain |  |  |  | dns-history-lookup.subdomain.jsonl |
| 125 | DNSDB | dnsdb | 2 | passive | api | extracted | domain | subdomain |  |  |  | dnsdb.subdomain.jsonl |
| 126 | DNSDumpster | dnsdumpster | 2 | passive | web | extracted | domain | subdomain |  |  | yes | dnsdumpster.subdomain.jsonl |
| 127 | DNSenum | dnsenum | 2 | active | cli | extracted | domain | subdomain |  |  |  | dnsenum.subdomain.jsonl |
| 128 | DNSGrep | dnsgrep | 2 | passive | cli | extracted | domain | subdomain |  |  |  | dnsgrep.subdomain.jsonl |
| 129 | DNSlytics | dnslytics | 2 | passive | api | extracted | domain | subdomain |  |  |  | dnslytics.subdomain.jsonl |
| 130 | DNSRecon | dnsrecon | 2 | active | cli | extracted | domain | subdomain |  |  |  | dnsrecon.subdomain.jsonl |
| 131 | dnstwist | dnstwist | 2 | passive | cli | extracted | domain | subdomain |  |  |  | dnstwist.subdomain.jsonl |
| 132 | dnsvalidator | dnsvalidator | 2 | active | cli | extracted | seed |  | yes | yes |  | raw/<slug>/ |
| 133 | dnsx | dnsx | 2 | active | cli | extracted | subdomain | ip | yes | yes |  | dnsx.ip.jsonl |
| 134 | DocFetcher | docfetcher | 11 | passive | web | extracted | file, url | finding |  |  | yes | docfetcher.finding.jsonl |
| 135 | domain-analyzer | domain-analyzer | 2 | passive | cli | extracted | domain | subdomain |  |  |  | domain-analyzer.subdomain.jsonl |
| 136 | domain-profiler | domain-profiler | 2 | passive | cli | extracted | domain | subdomain |  |  |  | domain-profiler.subdomain.jsonl |
| 137 | domain-sleuth | domain-sleuth | 2 | passive | cli | extracted | domain | subdomain |  |  |  | domain-sleuth.subdomain.jsonl |
| 138 | dorks_hunter | dorks-hunter | 4 | passive | cli | extracted | domain, live_host | url |  |  |  | dorks-hunter.url.jsonl |
| 139 | DorkSearch | dorksearch | 4 | passive | api | extracted | domain, live_host | url |  |  |  | dorksearch.url.jsonl |
| 140 | Dradis | dradis | 14 | passive | api | extracted | domain | any |  |  |  | raw/<slug>/ |
| 141 | droopescan | droopescan | 5 | active | cli | extracted | live_host | tech |  |  |  | droopescan.tech.jsonl |
| 142 | DumpsterDiver | dumpsterdiver | 9 | passive | cli | extracted | org, domain | secret |  |  |  | dumpsterdiver.secret.jsonl |
| 143 | EmailHippo | emailhippo | 7 | passive | api | extracted | domain, email | email |  |  |  | emailhippo.email.jsonl |
| 144 | Entrust CT Search | entrust-ct-search | 2 | passive | web | extracted | domain | subdomain |  |  | yes | entrust-ct-search.subdomain.jsonl |
| 145 | enumerator | enumerator | 10 | hybrid | cli | extracted | org, keyword | bucket |  |  |  | enumerator.bucket.jsonl |
| 146 | EO Browser | eo-browser | 15 | passive | api | extracted | org, coords | finding |  |  |  | eo-browser.finding.jsonl |
| 147 | Epieos | epieos | 7 | passive | web | extracted | domain, email | email |  |  | yes | epieos.email.jsonl |
| 148 | Exalead | exalead | 1 | passive | web | extracted | domain | ip |  |  | yes | exalead.ip.jsonl |
| 149 | Exif.tools | exif-tools | 11 | passive | web | extracted | file, url | finding |  |  | yes | exif-tools.finding.jsonl |
| 150 | ExifTool | exiftool | 11 | passive | cli | extracted | file, url | finding |  |  |  | exiftool.finding.jsonl |
| 151 | ExoneraTor | exonerator | 16 | passive | api | extracted | keyword, domain | finding |  |  |  | exonerator.finding.jsonl |
| 152 | EyeWitness | eyewitness | 5 | active | cli | extracted | live_host | tech |  |  |  | eyewitness.tech.jsonl |
| 153 | eyewitness-ng | eyewitness-ng | 5 | active | cli | extracted | live_host | tech |  |  |  | eyewitness-ng.tech.jsonl |
| 154 | Facebook CT Search | facebook-ct-search | 2 | passive | web | extracted | domain | subdomain |  |  | yes | facebook-ct-search.subdomain.jsonl |
| 155 | Facebook Graph Search | facebook-graph-search | 8 | passive | web | extracted | username, org | finding |  |  | yes | facebook-graph-search.finding.jsonl |
| 156 | FastPeopleSearch | fastpeoplesearch | 7 | passive | web | extracted | domain, email | email |  |  | yes | fastpeoplesearch.email.jsonl |
| 157 | Fierce | fierce | 2 | active | cli | extracted | domain | subdomain |  |  |  | fierce.subdomain.jsonl |
| 158 | Findomain | findomain | 2 | hybrid | cli | extracted | domain | subdomain | yes | yes |  | findomain.subdomain.jsonl |
| 159 | FingerprintJS | fingerprintjs | 5 | passive | api | extracted | live_host | tech |  |  |  | fingerprintjs.tech.jsonl |
| 160 | FIRST EPSS | first-epss | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | first-epss.finding.jsonl |
| 161 | Flashpoint | flashpoint | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | flashpoint.finding.jsonl |
| 162 | FlightRadar24 | flightradar24 | 15 | passive | api | extracted | org, coords | finding |  |  |  | flightradar24.finding.jsonl |
| 163 | FOCA | foca | 11 | passive | web | extracted | file, url | finding |  |  | yes | foca.finding.jsonl |
| 164 | FOFA | fofa | 1 | passive | api | extracted | domain | ip |  |  |  | fofa.ip.jsonl |
| 165 | FOFA API | fofa-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | fofa-api.service.jsonl |
| 166 | FOFA Hunt | fofa-hunt | 1 | passive | api | extracted | domain | ip |  |  |  | fofa-hunt.ip.jsonl |
| 167 | FOFA IP Search | fofa-ip-search | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | fofa-ip-search.cidr.jsonl |
| 168 | FollowerWonk | followerwonk | 8 | passive | api | extracted | username, org | finding |  |  |  | followerwonk.finding.jsonl |
| 169 | foremost | foremost | 11 | passive | cli | extracted | file, url | finding |  |  |  | foremost.finding.jsonl |
| 170 | FullContact | fullcontact | 7 | passive | api | extracted | domain, email | email |  |  |  | fullcontact.email.jsonl |
| 171 | FullContact API | fullcontact-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | fullcontact-api.service.jsonl |
| 172 | FullHunt | fullhunt | 1 | passive | api | extracted | domain | subdomain | yes | yes |  | fullhunt.subdomain.jsonl |
| 173 | gau | gau | 4 | passive | cli | extracted | domain | url | yes | yes |  | gau.url.jsonl |
| 174 | gauplus | gauplus | 4 | passive | cli | extracted | domain | url | yes |  |  | gauplus.url.jsonl |
| 175 | GCPBucketBrute | gcpbucketbrute | 10 | active | cli | extracted | org, keyword | bucket |  |  |  | gcpbucketbrute.bucket.jsonl |
| 176 | GeoSocial Footprint | geosocial-footprint | 8 | passive | api | extracted | username, org | finding |  |  |  | geosocial-footprint.finding.jsonl |
| 177 | GeoSpy | geospy | 8 | passive | api | extracted | username, org | finding |  |  |  | geospy.finding.jsonl |
| 178 | getJS | getjs | 4 | passive | cli | extracted | domain, live_host | url |  |  |  | getjs.url.jsonl |
| 179 | GHDB | ghdb | 4 | passive | web | extracted | domain, live_host | url |  |  | yes | ghdb.url.jsonl |
| 180 | ghunt | ghunt | 7 | passive | cli | extracted | domain, email | email |  |  |  | ghunt.email.jsonl |
| 181 | GHunt v2 | ghunt-v2 | 7 | passive | cli | extracted | domain, email | email |  |  |  | ghunt-v2.email.jsonl |
| 182 | git-secrets | git-secrets | 9 | passive | cli | extracted | org, domain | secret |  |  |  | git-secrets.secret.jsonl |
| 183 | GitAllSecrets | gitallsecrets | 9 | passive | cli | extracted | org, domain | secret |  |  |  | gitallsecrets.secret.jsonl |
| 184 | GitDorker | gitdorker | 9 | passive | cli | extracted | org, domain | secret |  |  |  | gitdorker.secret.jsonl |
| 185 | GitHarvester | githarvester | 9 | passive | cli | extracted | org, domain | secret |  |  |  | githarvester.secret.jsonl |
| 186 | GitHound | githound | 9 | passive | cli | extracted | org, domain | secret |  |  |  | githound.secret.jsonl |
| 187 | GitHub | github | 9 | passive | cli | extracted | org, domain | secret |  |  |  | github.secret.jsonl |
| 188 | GitHub Dorks | github-dorks | 4 | passive | api | extracted | domain, live_host | url |  |  |  | github-dorks.url.jsonl |
| 189 | GitLab | gitlab | 9 | passive | cli | extracted | org, domain | secret |  |  |  | gitlab.secret.jsonl |
| 190 | GitLeaks | gitleaks | 4 | hybrid | cli | extracted | repo | finding | yes | yes |  | gitleaks.finding.jsonl |
| 191 | GitMiner | gitminer | 9 | passive | cli | extracted | org, domain | secret |  |  |  | gitminer.secret.jsonl |
| 192 | Gitrob | gitrob | 4 | passive | cli | extracted | domain, live_host | url |  |  |  | gitrob.url.jsonl |
| 193 | Gitxray | gitxray | 9 | passive | cli | extracted | org, domain | secret |  |  |  | gitxray.secret.jsonl |
| 194 | Gobuster | gobuster | 2 | active | cli | extracted | domain | subdomain |  |  |  | gobuster.subdomain.jsonl |
| 195 | Goofuzz | goofuzz | 4 | passive | cli | extracted | domain, live_host | url |  |  |  | goofuzz.url.jsonl |
| 196 | Google Cache | google-cache | 6 | passive | web | extracted | domain, live_host | url |  |  | yes | google-cache.url.jsonl |
| 197 | Google Dorks | google-dorks | 4 | passive | web | extracted | domain, live_host | url |  |  | yes | google-dorks.url.jsonl |
| 198 | Google Earth | google-earth | 15 | passive | api | extracted | org, coords | finding |  |  |  | google-earth.finding.jsonl |
| 199 | Google Maps | google-maps | 15 | passive | api | extracted | org, coords | finding |  |  |  | google-maps.finding.jsonl |
| 200 | Google Search | google-search | 1 | passive | api | extracted | domain | ip |  |  |  | google-search.ip.jsonl |
| 201 | gowitness | gowitness | 5 | active | cli | extracted | url | screenshot | yes | yes |  | gowitness.screenshot.jsonl |
| 202 | GPS Visualizer | gps-visualizer | 15 | passive | web | extracted | org, coords | finding |  |  | yes | gps-visualizer.finding.jsonl |
| 203 | GrayHatWarfare | grayhatwarfare | 10 | passive | api | extracted | keyword | bucket | yes | yes |  | grayhatwarfare.bucket.jsonl |
| 204 | grep.app | grep-app | 9 | passive | api | extracted | org, domain | secret |  |  |  | grep-app.secret.jsonl |
| 205 | GreyNoise | greynoise | 1 | passive | api | extracted | ip | tag | yes | yes |  | greynoise.tag.jsonl |
| 206 | GreyNoise API | greynoise-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | greynoise-api.service.jsonl |
| 207 | GreyNoise IP Lookup | greynoise-ip-lookup | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | greynoise-ip-lookup.cidr.jsonl |
| 208 | hachoir-metadata | hachoir-metadata | 11 | passive | cli | extracted | file, url | finding |  |  |  | hachoir-metadata.finding.jsonl |
| 209 | HackerTarget | hackertarget | 2 | passive | api | extracted | domain | subdomain | yes | yes |  | hackertarget.subdomain.jsonl |
| 210 | HackTricks Recon Lists | hacktricks-recon-lists | 18 | passive | web | extracted | seed | seed |  |  | yes | raw/<slug>/ |
| 211 | hakcheckurl | hakcheckurl | 2 | active | cli | extracted | domain | subdomain |  |  |  | hakcheckurl.subdomain.jsonl |
| 212 | hakrawler | hakrawler | 4 | active | cli | extracted | domain, live_host | url |  |  |  | hakrawler.url.jsonl |
| 213 | haktrails | haktrails | 2 | passive | cli | extracted | domain | subdomain |  |  |  | haktrails.subdomain.jsonl |
| 214 | Have I Been Pwned | have-i-been-pwned | 7 | passive | api | extracted | domain, email | email |  |  |  | have-i-been-pwned.email.jsonl |
| 215 | HaveIBeenPwned API | haveibeenpwned-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | haveibeenpwned-api.service.jsonl |
| 216 | Haystak | haystak | 16 | passive | api | extracted | keyword, domain | finding |  |  |  | haystak.finding.jsonl |
| 217 | Hibp API | hibp-api | 7 | passive | api | extracted | domain, email | email |  |  |  | hibp-api.email.jsonl |
| 218 | Hoaxy | hoaxy | 8 | passive | api | extracted | username, org | finding |  |  |  | hoaxy.finding.jsonl |
| 219 | Holehe | holehe | 7 | passive | cli | extracted | domain, email | email |  |  |  | holehe.email.jsonl |
| 220 | HostHunter | hosthunter | 2 | passive | cli | extracted | domain | subdomain |  |  |  | hosthunter.subdomain.jsonl |
| 221 | httping | httping | 5 | active | cli | extracted | live_host | tech |  |  |  | httping.tech.jsonl |
| 222 | httprint | httprint | 5 | active | cli | extracted | live_host | tech |  |  |  | httprint.tech.jsonl |
| 223 | httprobe | httprobe | 5 | active | cli | extracted | live_host | tech |  |  |  | httprobe.tech.jsonl |
| 224 | httpx | httpx | 5 | active | cli | extracted | subdomain | url | yes | yes |  | httpx.url.jsonl |
| 225 | Hunter API | hunter-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | hunter-api.service.jsonl |
| 226 | Hunter Domain Search | hunter-domain-search | 7 | passive | api | extracted | domain, email | email |  |  |  | hunter-domain-search.email.jsonl |
| 227 | Hunter Howler | hunter-howler | 1 | passive | api | extracted | domain | ip |  |  |  | hunter-howler.ip.jsonl |
| 228 | Hunter.io | hunter-io | 7 | passive | api | extracted | domain, email | email |  |  |  | hunter-io.email.jsonl |
| 229 | Hurricane Electric | hurricane-electric | 3 | passive | web | extracted | ip, asn | cidr |  |  | yes | hurricane-electric.cidr.jsonl |
| 230 | Hybrid Analysis | hybrid-analysis | 12 | active | api | extracted | ip, domain, service | finding |  |  |  | hybrid-analysis.finding.jsonl |
| 231 | Ignorant | ignorant | 7 | passive | cli | extracted | domain, email | email |  |  |  | ignorant.email.jsonl |
| 232 | Instagram Location Search | instagram-location-search | 8 | passive | web | extracted | username, org | finding |  |  | yes | instagram-location-search.finding.jsonl |
| 233 | Instaloader | instaloader | 8 | passive | cli | extracted | username, org | finding |  |  |  | instaloader.finding.jsonl |
| 234 | Intel471 | intel471 | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | intel471.finding.jsonl |
| 235 | IntelX | intelx | 1 | passive | api | extracted | domain | ip |  |  |  | intelx.ip.jsonl |
| 236 | IntelX API | intelx-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | intelx-api.service.jsonl |
| 237 | IntelX Tor Search | intelx-tor-search | 16 | passive | api | extracted | keyword, domain | finding |  |  |  | intelx-tor-search.finding.jsonl |
| 238 | interactsh | interactsh | 14 | active | cli | extracted | seed | finding | yes | yes |  | interactsh.finding.jsonl |
| 239 | InternetDB | internetdb | 3 | passive | api | extracted | ip | service | yes | yes |  | internetdb.service.jsonl |
| 240 | Intezer | intezer | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | intezer.finding.jsonl |
| 241 | IOC Bucket | ioc-bucket | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | ioc-bucket.finding.jsonl |
| 242 | IOC Finder | ioc-finder | 12 | passive | cli | extracted | ip, domain, service | finding |  |  |  | ioc-finder.finding.jsonl |
| 243 | IOC Parser | ioc-parser | 12 | passive | cli | extracted | ip, domain, service | finding |  |  |  | ioc-parser.finding.jsonl |
| 244 | IP2Location | ip2location | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | ip2location.cidr.jsonl |
| 245 | IP2Location API | ip2location-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | ip2location-api.service.jsonl |
| 246 | ipapi | ipapi | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | ipapi.cidr.jsonl |
| 247 | IPFingerprints | ipfingerprints | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | ipfingerprints.cidr.jsonl |
| 248 | IPGeolocation | ipgeolocation | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | ipgeolocation.cidr.jsonl |
| 249 | IPinfo | ipinfo | 3 | passive | api | extracted | ip | asn | yes | yes |  | ipinfo.asn.jsonl |
| 250 | IPinfo API | ipinfo-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | ipinfo-api.service.jsonl |
| 251 | IPQualityScore | ipqualityscore | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | ipqualityscore.cidr.jsonl |
| 252 | IPVoid | ipvoid | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | ipvoid.cidr.jsonl |
| 253 | IVRE | ivre | 1 | hybrid | cli | extracted | domain | ip |  |  |  | ivre.ip.jsonl |
| 254 | Joe Sandbox | joe-sandbox | 12 | active | api | extracted | ip, domain, service | finding |  |  |  | joe-sandbox.finding.jsonl |
| 255 | JoomScan | joomscan | 5 | active | cli | extracted | live_host | tech |  |  |  | joomscan.tech.jsonl |
| 256 | JPEGsnoop | jpegsnoop | 11 | passive | web | extracted | file, url | finding |  |  | yes | jpegsnoop.finding.jsonl |
| 257 | JSFinder | jsfinder | 4 | passive | cli | extracted | domain, live_host | url |  |  |  | jsfinder.url.jsonl |
| 258 | JSLeak | jsleak | 4 | passive | cli | extracted | domain, live_host | url |  |  |  | jsleak.url.jsonl |
| 259 | Kali Linux Information Gathering Tools | kali-linux-information-gathering-tools | 18 | hybrid | cli | extracted | seed | seed |  |  |  | raw/<slug>/ |
| 260 | katana | katana | 4 | hybrid | cli | extracted | url | url | yes | yes |  | katana.url.jsonl |
| 261 | Katana Archive Mode | katana-archive-mode | 6 | hybrid | cli | extracted | domain, live_host | url |  |  |  | katana-archive-mode.url.jsonl |
| 262 | Katana screenshots | katana-screenshots | 13 | active | cli | extracted | live_host | screenshot |  |  |  | katana-screenshots.screenshot.jsonl |
| 263 | Kismet Logs | kismet-logs | 15 | active | cli | extracted | org, coords | finding |  |  |  | kismet-logs.finding.jsonl |
| 264 | Knockpy | knockpy | 2 | active | cli | extracted | domain | subdomain |  |  |  | knockpy.subdomain.jsonl |
| 265 | Kubernetes API Search | kubernetes-api-search | 10 | passive | api | extracted | org, keyword | bucket |  |  |  | kubernetes-api-search.bucket.jsonl |
| 266 | Kubernetes Exposure Search | kubernetes-exposure-search | 10 | passive | api | extracted | org, keyword | bucket |  |  |  | kubernetes-exposure-search.bucket.jsonl |
| 267 | LACNIC | lacnic | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | lacnic.cidr.jsonl |
| 268 | Lampyre | lampyre | 7 | hybrid | api | extracted | domain, email | email |  |  |  | lampyre.email.jsonl |
| 269 | lazys3 | lazys3 | 10 | active | cli | extracted | org, keyword | bucket |  |  |  | lazys3.bucket.jsonl |
| 270 | LeakCheck | leakcheck | 7 | passive | api | extracted | domain, email | email |  |  |  | leakcheck.email.jsonl |
| 271 | LeakCheck API | leakcheck-api | 7 | passive | api | extracted | domain, email | email |  |  |  | leakcheck-api.email.jsonl |
| 272 | LeakIX | leakix | 1 | passive | api | extracted | ip | finding | yes | yes |  | leakix.finding.jsonl |
| 273 | LeakIX Buckets | leakix-buckets | 10 | passive | api | extracted | org, keyword | bucket |  |  |  | leakix-buckets.bucket.jsonl |
| 274 | LeakIX Exposure Search | leakix-exposure-search | 1 | passive | api | extracted | domain | ip |  |  |  | leakix-exposure-search.ip.jsonl |
| 275 | LeakPeek | leakpeek | 7 | passive | api | extracted | domain, email | email |  |  |  | leakpeek.email.jsonl |
| 276 | LinkedIn Recon | linkedin-recon | 8 | passive | api | extracted | username, org | finding |  |  |  | linkedin-recon.finding.jsonl |
| 277 | LinkedIn2Username | linkedin2username | 7 | passive | cli | extracted | domain, email | email |  |  |  | linkedin2username.email.jsonl |
| 278 | LinkedInt | linkedint | 7 | passive | cli | extracted | domain, email | email |  |  |  | linkedint.email.jsonl |
| 279 | LinkFinder | linkfinder | 4 | passive | python | extracted | js_file | url | yes | yes |  | linkfinder.url.jsonl |
| 280 | Maigret | maigret | 7 | passive | cli | extracted | domain, email | email |  |  |  | maigret.email.jsonl |
| 281 | MailTester | mailtester | 7 | passive | web | extracted | domain, email | email |  |  | yes | mailtester.email.jsonl |
| 282 | MalShare | malshare | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | malshare.finding.jsonl |
| 283 | Maltego | maltego | 7 | hybrid | api | extracted | domain, email | email |  |  |  | maltego.email.jsonl |
| 284 | MalwareBazaar | malwarebazaar | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | malwarebazaar.finding.jsonl |
| 285 | MalwareTrafficAnalysis | malwaretrafficanalysis | 12 | passive | web | extracted | ip, domain, service | finding |  |  | yes | malwaretrafficanalysis.finding.jsonl |
| 286 | MarineTraffic | marinetraffic | 15 | passive | api | extracted | org, coords | finding |  |  |  | marinetraffic.finding.jsonl |
| 287 | massdns | massdns | 2 | active | cli | extracted | subdomain | ip | yes | yes |  | massdns.ip.jsonl |
| 288 | mat2 | mat2 | 11 | passive | cli | extracted | file, url | finding |  |  |  | mat2.finding.jsonl |
| 289 | MaxMind | maxmind | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | maxmind.cidr.jsonl |
| 290 | MediaInfo | mediainfo | 11 | passive | cli | extracted | file, url | finding |  |  |  | mediainfo.finding.jsonl |
| 291 | Memento Time Travel | memento-time-travel | 6 | passive | api | extracted | domain, live_host | url |  |  |  | memento-time-travel.url.jsonl |
| 292 | Mentionmapp | mentionmapp | 8 | passive | web | extracted | username, org | finding |  |  | yes | mentionmapp.finding.jsonl |
| 293 | Metadata2Go | metadata2go | 11 | passive | web | extracted | file, url | finding |  |  | yes | metadata2go.finding.jsonl |
| 294 | Metagoofil | metagoofil | 11 | passive | cli | extracted | file, url | finding |  |  |  | metagoofil.finding.jsonl |
| 295 | MicroBurst | microburst | 10 | active | cli | extracted | org, keyword | bucket |  |  |  | microburst.bucket.jsonl |
| 296 | MISP | misp | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | misp.finding.jsonl |
| 297 | Mojeek | mojeek | 1 | passive | web | extracted | domain | ip |  |  | yes | mojeek.ip.jsonl |
| 298 | Naabu | naabu | 5 | active | cli | extracted | ip | host_port | yes | yes |  | naabu.host_port.jsonl |
| 299 | Namecheckup | namecheckup | 7 | passive | web | extracted | domain, email | email |  |  | yes | namecheckup.email.jsonl |
| 300 | Namechk | namechk | 7 | passive | web | extracted | domain, email | email |  |  | yes | namechk.email.jsonl |
| 301 | Netcraft | netcraft | 1 | passive | api | extracted | domain | ip |  |  |  | netcraft.ip.jsonl |
| 302 | Netcraft Toolbar | netcraft-toolbar | 5 | passive | web | extracted | live_host | tech |  |  | yes | netcraft-toolbar.tech.jsonl |
| 303 | Netlas | netlas | 1 | passive | api | extracted | domain | service | yes | yes |  | netlas.service.jsonl |
| 304 | Netlas API | netlas-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | netlas-api.service.jsonl |
| 305 | Netlas ASN Search | netlas-asn-search | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | netlas-asn-search.cidr.jsonl |
| 306 | Netlas Explorer | netlas-explorer | 1 | passive | web | extracted | domain | ip |  |  | yes | netlas-explorer.ip.jsonl |
| 307 | Netlas Hosts | netlas-hosts | 1 | passive | api | extracted | domain | ip |  |  |  | netlas-hosts.ip.jsonl |
| 308 | Nikto | nikto | 5 | active | cli | extracted | live_host | tech |  |  |  | nikto.tech.jsonl |
| 309 | notify | notify | 14 | passive | cli | extracted | any | seed | yes | yes |  | raw/<slug>/ |
| 310 | Nuclei | nuclei | 14 | active | cli | extracted | url | finding | yes | yes |  | nuclei.finding.jsonl |
| 311 | nuclei-templates | nuclei-templates | 14 | passive | api | extracted | domain | any |  |  |  | raw/<slug>/ |
| 312 | NVD | nvd | 12 | passive | api | extracted | cpe | finding | yes | yes |  | nvd.finding.jsonl |
| 313 | OCRmyPDF | ocrmypdf | 11 | passive | cli | extracted | file, url | finding |  |  |  | ocrmypdf.finding.jsonl |
| 314 | oletools | oletools | 11 | passive | cli | extracted | file, url | finding |  |  |  | oletools.finding.jsonl |
| 315 | OneForAll | oneforall | 2 | hybrid | cli | extracted | domain | subdomain |  |  |  | oneforall.subdomain.jsonl |
| 316 | OnionLand | onionland | 16 | passive | web | extracted | keyword, domain | finding |  |  | yes | onionland.finding.jsonl |
| 317 | OnionLand Search | onionland-search | 1 | passive | web | extracted | domain | ip |  |  | yes | onionland-search.ip.jsonl |
| 318 | OnionScan | onionscan | 16 | active | cli | extracted | keyword, domain | finding |  |  |  | onionscan.finding.jsonl |
| 319 | OnionSearch | onionsearch | 16 | passive | cli | extracted | keyword, domain | finding |  |  |  | onionsearch.finding.jsonl |
| 320 | ONYPHE | onyphe | 1 | passive | api | extracted | domain | ip |  |  |  | onyphe.ip.jsonl |
| 321 | OpenCellID | opencellid | 15 | passive | api | extracted | org, coords | finding |  |  |  | opencellid.finding.jsonl |
| 322 | OpenCTI | opencti | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | opencti.finding.jsonl |
| 323 | OpenPhish | openphish | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | openphish.finding.jsonl |
| 324 | OpenStreetMap | openstreetmap | 15 | passive | api | extracted | org, coords | finding |  |  |  | openstreetmap.finding.jsonl |
| 325 | OpenVAS Discovery | openvas-discovery | 5 | active | cli | extracted | live_host | tech |  |  |  | openvas-discovery.tech.jsonl |
| 326 | OSINT Framework | osint-framework | 18 | passive | web | extracted | seed | seed |  |  | yes | raw/<slug>/ |
| 327 | Osintgram | osintgram | 14 | passive | cli | extracted | domain | any |  |  |  | raw/<slug>/ |
| 328 | Osintracker | osintracker | 7 | passive | web | extracted | domain, email | email |  |  | yes | osintracker.email.jsonl |
| 329 | Osmedeus | osmedeus | 14 | hybrid | cli | extracted | domain | any |  |  |  | raw/<slug>/ |
| 330 | OWASP Amass | owasp-amass | 14 | hybrid | cli | extracted | domain | any |  |  |  | raw/<slug>/ |
| 331 | Packet Storm Search | packet-storm-search | 1 | passive | web | extracted | domain | ip |  |  | yes | packet-storm-search.ip.jsonl |
| 332 | pageres | pageres | 13 | active | cli | extracted | live_host | screenshot |  |  |  | pageres.screenshot.jsonl |
| 333 | Pagodo | pagodo | 4 | passive | cli | extracted | domain, live_host | url |  |  |  | pagodo.url.jsonl |
| 334 | Pagodo Dorks | pagodo-dorks | 4 | passive | dataset | extracted | domain, live_host | url |  |  |  | pagodo-dorks.url.jsonl |
| 335 | ParamSpider | paramspider | 4 | passive | cli | extracted | domain | url | yes | yes |  | paramspider.url.jsonl |
| 336 | PassiveTotal | passivetotal | 2 | passive | api | extracted | domain | subdomain |  |  |  | passivetotal.subdomain.jsonl |
| 337 | PayloadsAllTheThings Recon Section | payloadsallthethings-recon-section | 18 | passive | web | extracted | seed | seed |  |  | yes | raw/<slug>/ |
| 338 | PDF Stream Dumper | pdf-stream-dumper | 11 | passive | web | extracted | file, url | finding |  |  | yes | pdf-stream-dumper.finding.jsonl |
| 339 | pdfinfo | pdfinfo | 11 | passive | cli | extracted | file, url | finding |  |  |  | pdfinfo.finding.jsonl |
| 340 | PeekYou | peekyou | 7 | passive | web | extracted | domain, email | email |  |  | yes | peekyou.email.jsonl |
| 341 | peepdf | peepdf | 11 | passive | cli | extracted | file, url | finding |  |  |  | peepdf.finding.jsonl |
| 342 | PeeringDB | peeringdb | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | peeringdb.cidr.jsonl |
| 343 | Pentest-Tools Collections | pentest-tools-collections | 18 | hybrid | web | extracted | seed | seed |  |  | yes | raw/<slug>/ |
| 344 | PhishTank | phishtank | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | phishtank.finding.jsonl |
| 345 | Phonebook.cz | phonebook-cz | 7 | passive | web | extracted | domain, email | email |  |  | yes | phonebook-cz.email.jsonl |
| 346 | PhotoME | photome | 11 | passive | web | extracted | file, url | finding |  |  | yes | photome.finding.jsonl |
| 347 | Photon | photon | 2 | active | cli | extracted | domain | subdomain |  |  |  | photon.subdomain.jsonl |
| 348 | Pipl | pipl | 7 | passive | api | extracted | domain, email | email |  |  |  | pipl.email.jsonl |
| 349 | Playwright | playwright | 13 | active | api | extracted | live_host | screenshot |  |  |  | playwright.screenshot.jsonl |
| 350 | Profil3r | profil3r | 7 | passive | cli | extracted | domain, email | email |  |  |  | profil3r.email.jsonl |
| 351 | Project Sonar | project-sonar | 1 | passive | dataset | extracted | domain | ip |  |  |  | project-sonar.ip.jsonl |
| 352 | ProjectDiscovery stack | projectdiscovery-stack | 14 | hybrid | cli | extracted | domain | any |  |  |  | raw/<slug>/ |
| 353 | prowler | prowler | 10 | passive | cli | extracted | org, keyword | bucket |  |  |  | prowler.bucket.jsonl |
| 354 | PTRArchive | ptrarchive | 2 | passive | web | extracted | domain | subdomain |  |  | yes | ptrarchive.subdomain.jsonl |
| 355 | Public Bucket Search | public-bucket-search | 10 | passive | api | extracted | org, keyword | bucket |  |  |  | public-bucket-search.bucket.jsonl |
| 356 | PublicWWW | publicwww | 1 | passive | api | extracted | domain | ip |  |  |  | publicwww.ip.jsonl |
| 357 | PublicWWW Historical Search | publicwww-historical-search | 6 | passive | api | extracted | domain, live_host | url |  |  |  | publicwww-historical-search.url.jsonl |
| 358 | PublicWWW Source Search | publicwww-source-search | 1 | passive | web | extracted | domain | ip |  |  | yes | publicwww-source-search.ip.jsonl |
| 359 | Pulsedive | pulsedive | 1 | passive | api | extracted | domain | ip |  |  |  | pulsedive.ip.jsonl |
| 360 | Pulsedive API | pulsedive-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | pulsedive-api.service.jsonl |
| 361 | Pulsedive Threat Intelligence | pulsedive-threat-intelligence | 1 | passive | api | extracted | domain | ip |  |  |  | pulsedive-threat-intelligence.ip.jsonl |
| 362 | Puppeteer | puppeteer | 13 | active | api | extracted | live_host | screenshot |  |  |  | puppeteer.screenshot.jsonl |
| 363 | puredns | puredns | 2 | active | cli | extracted | subdomain | subdomain | yes | yes |  | puredns.subdomain.jsonl |
| 364 | Pushshift | pushshift | 8 | passive | api | extracted | username, org | finding |  |  |  | pushshift.finding.jsonl |
| 365 | RADb | radb | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | radb.cidr.jsonl |
| 366 | Rapid7 Open Data | rapid7-open-data | 1 | passive | api | extracted | domain | ip |  |  |  | rapid7-open-data.ip.jsonl |
| 367 | RapidDNS | rapiddns | 2 | passive | web | extracted | domain | subdomain |  |  | yes | rapiddns.subdomain.jsonl |
| 368 | Recon Dark Web Search | recon-dark-web-search | 16 | passive | api | extracted | keyword, domain | finding |  |  |  | recon-dark-web-search.finding.jsonl |
| 369 | Recon-ng | recon-ng | 14 | passive | cli | extracted | domain | any |  |  |  | raw/<slug>/ |
| 370 | ReconDog | recondog | 2 | hybrid | cli | extracted | domain | subdomain |  |  |  | recondog.subdomain.jsonl |
| 371 | ReconFTW | reconftw | 2 | hybrid | cli | extracted | domain | subdomain |  |  |  | reconftw.subdomain.jsonl |
| 372 | Reconmap | reconmap | 1 | hybrid | api | extracted | domain | ip |  |  |  | reconmap.ip.jsonl |
| 373 | reconspider | reconspider | 14 | hybrid | cli | extracted | domain | any |  |  |  | raw/<slug>/ |
| 374 | Recorded Future | recorded-future | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | recorded-future.finding.jsonl |
| 375 | Red Teaming Toolkit Lists | red-teaming-toolkit-lists | 18 | hybrid | web | extracted | seed | seed |  |  | yes | raw/<slug>/ |
| 376 | Reddit Search | reddit-search | 8 | passive | api | extracted | username, org | finding |  |  |  | reddit-search.finding.jsonl |
| 377 | RedditMetis | redditmetis | 8 | passive | web | extracted | username, org | finding |  |  | yes | redditmetis.finding.jsonl |
| 378 | repo-analyzer | repo-analyzer | 9 | passive | cli | extracted | org, domain | secret |  |  |  | repo-analyzer.secret.jsonl |
| 379 | repo-security-scanner | repo-security-scanner | 9 | passive | cli | extracted | org, domain | secret |  |  |  | repo-security-scanner.secret.jsonl |
| 380 | Repo-supervisor | repo-supervisor | 4 | passive | cli | extracted | domain, live_host | url |  |  |  | repo-supervisor.url.jsonl |
| 381 | RepoHunt | repohunt | 9 | passive | cli | extracted | org, domain | secret |  |  |  | repohunt.secret.jsonl |
| 382 | RepoRadar | reporadar | 9 | passive | cli | extracted | org, domain | secret |  |  |  | reporadar.secret.jsonl |
| 383 | RepoSuperScanner | reposuperscanner | 9 | passive | cli | extracted | org, domain | secret |  |  |  | reposuperscanner.secret.jsonl |
| 384 | Retire.js | retire-js | 5 | passive | cli | extracted | live_host | tech |  |  |  | retire-js.tech.jsonl |
| 385 | ReverseDNSLookup | reversednslookup | 2 | passive | api | extracted | domain | subdomain |  |  |  | reversednslookup.subdomain.jsonl |
| 386 | ReverseIPLookup | reverseiplookup | 2 | passive | api | extracted | domain | subdomain |  |  |  | reverseiplookup.subdomain.jsonl |
| 387 | ReverseMXLookup | reversemxlookup | 2 | passive | api | extracted | domain | subdomain |  |  |  | reversemxlookup.subdomain.jsonl |
| 388 | ReverseNSLookup | reversenslookup | 2 | passive | api | extracted | domain | subdomain |  |  |  | reversenslookup.subdomain.jsonl |
| 389 | Riddler.io | riddler-io | 2 | passive | api | extracted | domain | subdomain |  |  |  | riddler-io.subdomain.jsonl |
| 390 | RIPE Atlas | ripe-atlas | 3 | active | api | extracted | ip, asn | cidr |  |  |  | ripe-atlas.cidr.jsonl |
| 391 | RIPE NCC | ripe-ncc | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | ripe-ncc.cidr.jsonl |
| 392 | RIPEstat | ripestat | 3 | passive | api | extracted | asn | cidr | yes | yes |  | ripestat.cidr.jsonl |
| 393 | ripgrep | ripgrep | 9 | passive | cli | extracted | org, domain | secret |  |  |  | ripgrep.secret.jsonl |
| 394 | RiskIQ Passive DNS | riskiq-passive-dns | 2 | passive | api | extracted | domain | subdomain |  |  |  | riskiq-passive-dns.subdomain.jsonl |
| 395 | RiskIQ PassiveTotal | riskiq-passivetotal | 1 | passive | web | extracted | domain | ip |  |  | yes | riskiq-passivetotal.ip.jsonl |
| 396 | Robtex | robtex | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | robtex.cidr.jsonl |
| 397 | RocketReach | rocketreach | 7 | passive | api | extracted | domain, email | email |  |  |  | rocketreach.email.jsonl |
| 398 | RustScan | rustscan | 5 | active | cli | extracted | live_host | tech |  |  |  | rustscan.tech.jsonl |
| 399 | S3recon | s3recon | 10 | hybrid | cli | extracted | org, keyword | bucket |  |  |  | s3recon.bucket.jsonl |
| 400 | S3Scanner | s3scanner | 10 | active | cli | extracted | bucket | finding | yes | yes |  | s3scanner.finding.jsonl |
| 401 | ScoutSuite | scoutsuite | 10 | passive | cli | extracted | org, keyword | bucket |  |  |  | scoutsuite.bucket.jsonl |
| 402 | ScreenshotOne | screenshotone | 13 | active | api | extracted | live_host | screenshot |  |  |  | screenshotone.screenshot.jsonl |
| 403 | Search Engine Map | search-engine-map | 1 | passive | web | extracted | domain | ip |  |  | yes | search-engine-map.ip.jsonl |
| 404 | Searchcode | searchcode | 1 | passive | api | extracted | domain | ip |  |  |  | searchcode.ip.jsonl |
| 405 | SearchDiggity | searchdiggity | 4 | passive | web | extracted | domain, live_host | url |  |  | yes | searchdiggity.url.jsonl |
| 406 | Searx | searx | 1 | passive | web | extracted | domain | ip |  |  | yes | searx.ip.jsonl |
| 407 | SecretFinder | secretfinder | 4 | passive | python | extracted | js_file | finding | yes | yes |  | secretfinder.finding.jsonl |
| 408 | SecurityTrails | securitytrails | 2 | passive | api | extracted | domain | subdomain | yes | yes |  | securitytrails.subdomain.jsonl |
| 409 | SecurityTrails API | securitytrails-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | securitytrails-api.service.jsonl |
| 410 | SecurityTrails Historical DNS | securitytrails-historical-dns | 6 | passive | api | extracted | domain, live_host | url |  |  |  | securitytrails-historical-dns.url.jsonl |
| 411 | Semgrep | semgrep | 9 | passive | cli | extracted | org, domain | secret |  |  |  | semgrep.secret.jsonl |
| 412 | Semgrep Secrets | semgrep-secrets | 9 | passive | cli | extracted | org, domain | secret |  |  |  | semgrep-secrets.secret.jsonl |
| 413 | Sentinel Hub | sentinel-hub | 15 | passive | api | extracted | org, coords | finding |  |  |  | sentinel-hub.finding.jsonl |
| 414 | Sherlock | sherlock | 7 | passive | cli | extracted | domain, email | email |  |  |  | sherlock.email.jsonl |
| 415 | shhgit | shhgit | 9 | passive | cli | extracted | org, domain | secret |  |  |  | shhgit.secret.jsonl |
| 416 | Shodan | shodan | 1 | passive | api | extracted | domain | service | yes | yes |  | shodan.service.jsonl |
| 417 | Shodan API | shodan-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | shodan-api.service.jsonl |
| 418 | Shodan ASN Search | shodan-asn-search | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | shodan-asn-search.cidr.jsonl |
| 419 | Shodan screenshots | shodan-screenshots | 13 | passive | api | extracted | live_host | screenshot |  |  |  | shodan-screenshots.screenshot.jsonl |
| 420 | shuffledns | shuffledns | 2 | active | cli | extracted | domain | subdomain |  |  |  | shuffledns.subdomain.jsonl |
| 421 | SimilarTech | similartech | 5 | passive | api | extracted | live_host | tech |  |  |  | similartech.tech.jsonl |
| 422 | Sitedorks | sitedorks | 4 | passive | web | extracted | domain, live_host | url |  |  | yes | sitedorks.url.jsonl |
| 423 | Sn1per | sn1per | 14 | active | cli | extracted | domain | any |  |  |  | raw/<slug>/ |
| 424 | Snap Map | snap-map | 8 | passive | web | extracted | username, org | finding |  |  | yes | snap-map.finding.jsonl |
| 425 | Snusbase | snusbase | 7 | passive | api | extracted | domain, email | email |  |  |  | snusbase.email.jsonl |
| 426 | SOC Radar Search | soc-radar-search | 1 | passive | api | extracted | domain | ip |  |  |  | soc-radar-search.ip.jsonl |
| 427 | Social Analyzer | social-analyzer | 7 | passive | cli | extracted | domain, email | email |  |  |  | social-analyzer.email.jsonl |
| 428 | Social Bearing | social-bearing | 8 | passive | api | extracted | username, org | finding |  |  |  | social-bearing.finding.jsonl |
| 429 | Social Blade | social-blade | 8 | passive | api | extracted | username, org | finding |  |  |  | social-blade.finding.jsonl |
| 430 | Social Links | social-links | 7 | passive | api | extracted | domain, email | email |  |  |  | social-links.email.jsonl |
| 431 | Social Searcher | social-searcher | 8 | passive | api | extracted | username, org | finding |  |  |  | social-searcher.finding.jsonl |
| 432 | Socid Extractor | socid-extractor | 8 | passive | cli | extracted | username, org | finding |  |  |  | socid-extractor.finding.jsonl |
| 433 | Sonar DNS | sonar-dns | 2 | passive | dataset | extracted | domain | subdomain |  |  |  | sonar-dns.subdomain.jsonl |
| 434 | Sonar FDNS | sonar-fdns | 2 | passive | dataset | extracted | domain | subdomain |  |  |  | sonar-fdns.subdomain.jsonl |
| 435 | Sonar OMNI | sonar-omni | 2 | passive | dataset | extracted | domain | subdomain |  |  |  | sonar-omni.subdomain.jsonl |
| 436 | Sonar RDNS | sonar-rdns | 2 | passive | dataset | extracted | domain | subdomain |  |  |  | sonar-rdns.subdomain.jsonl |
| 437 | Sourcegraph | sourcegraph | 9 | passive | api | extracted | org, domain | secret |  |  |  | sourcegraph.secret.jsonl |
| 438 | SpiderFoot | spiderfoot | 7 | hybrid | cli | extracted | domain, email | email |  |  |  | spiderfoot.email.jsonl |
| 439 | SpiderSuite | spidersuite | 14 | passive | api | extracted | domain | any |  |  |  | raw/<slug>/ |
| 440 | Spokeo | spokeo | 7 | passive | api | extracted | domain, email | email |  |  |  | spokeo.email.jsonl |
| 441 | Spur | spur | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | spur.cidr.jsonl |
| 442 | Spur Context API | spur-context-api | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | spur-context-api.cidr.jsonl |
| 443 | Spyse | spyse | 2 | passive | api | extracted | domain | subdomain |  |  |  | spyse.subdomain.jsonl |
| 444 | strings | strings | 11 | passive | cli | extracted | file, url | finding |  |  |  | strings.finding.jsonl |
| 445 | subfinder | subfinder | 2 | passive | cli | extracted | domain | subdomain | yes | yes |  | subfinder.subdomain.jsonl |
| 446 | Subjack | subjack | 2 | passive | cli | extracted | subdomain | finding | yes | yes |  | subjack.finding.jsonl |
| 447 | sublist3r | sublist3r | 2 | passive | cli | extracted | domain | subdomain |  |  |  | sublist3r.subdomain.jsonl |
| 448 | SubOver | subover | 2 | passive | cli | extracted | domain | subdomain |  |  |  | subover.subdomain.jsonl |
| 449 | Subscraper | subscraper | 2 | passive | cli | extracted | domain | subdomain |  |  |  | subscraper.subdomain.jsonl |
| 450 | Sudomy | sudomy | 2 | hybrid | cli | extracted | domain | subdomain |  |  |  | sudomy.subdomain.jsonl |
| 451 | Swisscows | swisscows | 1 | passive | web | extracted | domain | ip |  |  | yes | swisscows.ip.jsonl |
| 452 | Team Cymru | team-cymru | 3 | passive | api | extracted | ip, asn | cidr |  |  |  | team-cymru.cidr.jsonl |
| 453 | Telegram OSINT | telegram-osint | 8 | passive | cli | extracted | username, org | finding |  |  |  | telegram-osint.finding.jsonl |
| 454 | Telepathy | telepathy | 8 | passive | cli | extracted | username, org | finding |  |  |  | telepathy.finding.jsonl |
| 455 | Telescan | telescan | 8 | passive | cli | extracted | username, org | finding |  |  |  | telescan.finding.jsonl |
| 456 | ThatsThem | thatsthem | 7 | passive | web | extracted | domain, email | email |  |  | yes | thatsthem.email.jsonl |
| 457 | theHarvester | theharvester | 2 | passive | cli | extracted | domain | subdomain |  |  |  | theharvester.subdomain.jsonl |
| 458 | Thingful | thingful | 1 | passive | api | extracted | domain | ip |  |  |  | thingful.ip.jsonl |
| 459 | ThreatBook | threatbook | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | threatbook.finding.jsonl |
| 460 | ThreatConnect | threatconnect | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | threatconnect.finding.jsonl |
| 461 | ThreatCrowd | threatcrowd | 2 | passive | api | extracted | domain | subdomain |  |  |  | threatcrowd.subdomain.jsonl |
| 462 | ThreatFox | threatfox | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | threatfox.finding.jsonl |
| 463 | ThreatMiner | threatminer | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | threatminer.finding.jsonl |
| 464 | Tika | tika | 11 | passive | cli | extracted | file, url | finding |  |  |  | tika.finding.jsonl |
| 465 | TikTokScraper | tiktokscraper | 8 | passive | cli | extracted | username, org | finding |  |  |  | tiktokscraper.finding.jsonl |
| 466 | tko-subs | tko-subs | 2 | passive | cli | extracted | domain | subdomain |  |  |  | tko-subs.subdomain.jsonl |
| 467 | TorBot | torbot | 16 | passive | cli | extracted | keyword, domain | finding |  |  |  | torbot.finding.jsonl |
| 468 | Torch | torch | 16 | passive | web | extracted | keyword, domain | finding |  |  | yes | torch.finding.jsonl |
| 469 | Torch Search | torch-search | 1 | passive | web | extracted | domain | ip |  |  | yes | torch-search.ip.jsonl |
| 470 | Toutatis | toutatis | 8 | passive | cli | extracted | username, org | finding |  |  |  | toutatis.finding.jsonl |
| 471 | Trivy | trivy | 9 | passive | cli | extracted | org, domain | secret |  |  |  | trivy.secret.jsonl |
| 472 | Trivy Secret Scanner | trivy-secret-scanner | 4 | passive | cli | extracted | domain, live_host | url |  |  |  | trivy-secret-scanner.url.jsonl |
| 473 | TruePeopleSearch | truepeoplesearch | 7 | passive | web | extracted | domain, email | email |  |  | yes | truepeoplesearch.email.jsonl |
| 474 | TruffleHog | trufflehog | 4 | hybrid | cli | extracted | repo | finding | yes | yes |  | trufflehog.finding.jsonl |
| 475 | Trufflehog3 | trufflehog3 | 4 | passive | cli | extracted | domain, live_host | url |  |  |  | trufflehog3.url.jsonl |
| 476 | TruthNest | truthnest | 8 | passive | web | extracted | username, org | finding |  |  | yes | truthnest.finding.jsonl |
| 477 | TweetDeck | tweetdeck | 8 | passive | web | extracted | username, org | finding |  |  | yes | tweetdeck.finding.jsonl |
| 478 | Twint | twint | 7 | passive | cli | extracted | domain, email | email |  |  |  | twint.email.jsonl |
| 479 | UK Web Archive | uk-web-archive | 6 | passive | web | extracted | domain, live_host | url |  |  | yes | uk-web-archive.url.jsonl |
| 480 | uncover | uncover | 14 | passive | cli | extracted | domain | host_port | yes | yes |  | uncover.host_port.jsonl |
| 481 | uncover-engine | uncover-engine | 14 | passive | cli | extracted | domain | any |  |  |  | raw/<slug>/ |
| 482 | URLCrazy | urlcrazy | 2 | passive | cli | extracted | domain | subdomain |  |  |  | urlcrazy.subdomain.jsonl |
| 483 | URLFinder | urlfinder | 4 | passive | cli | extracted | domain, live_host | url |  |  |  | urlfinder.url.jsonl |
| 484 | URLHaus | urlhaus | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | urlhaus.finding.jsonl |
| 485 | URLScan | urlscan | 1 | passive | api | extracted | domain | url | yes | yes |  | urlscan.url.jsonl |
| 486 | URLScan API | urlscan-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | urlscan-api.service.jsonl |
| 487 | URLScan History | urlscan-history | 6 | passive | api | extracted | domain, live_host | url |  |  |  | urlscan-history.url.jsonl |
| 488 | urlscan screenshots | urlscan-screenshots | 13 | passive | api | extracted | live_host | screenshot |  |  |  | urlscan-screenshots.screenshot.jsonl |
| 489 | URLScan Search | urlscan-search | 4 | passive | api | extracted | domain, live_host | url |  |  |  | urlscan-search.url.jsonl |
| 490 | urlscan.io | urlscan-io | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | urlscan-io.finding.jsonl |
| 491 | UserRecon | userrecon | 7 | passive | cli | extracted | domain, email | email |  |  |  | userrecon.email.jsonl |
| 492 | UserSearch | usersearch | 7 | passive | web | extracted | domain, email | email |  |  | yes | usersearch.email.jsonl |
| 493 | VerifyEmailAddress | verifyemailaddress | 7 | passive | api | extracted | domain, email | email |  |  |  | verifyemailaddress.email.jsonl |
| 494 | VesselFinder | vesselfinder | 15 | passive | api | extracted | org, coords | finding |  |  |  | vesselfinder.finding.jsonl |
| 495 | ViewDNS | viewdns | 2 | passive | api | extracted | domain | subdomain |  |  |  | viewdns.subdomain.jsonl |
| 496 | VirusTotal | virustotal | 2 | passive | api | extracted | domain | subdomain | yes | yes |  | virustotal.subdomain.jsonl |
| 497 | VirusTotal API | virustotal-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | virustotal-api.service.jsonl |
| 498 | Vulners | vulners | 12 | passive | api | extracted | cpe | finding | yes | yes |  | vulners.finding.jsonl |
| 499 | wafninja | wafninja | 5 | active | cli | extracted | live_host | tech |  |  |  | wafninja.tech.jsonl |
| 500 | wafw00f | wafw00f | 5 | active | cli | extracted | url | tag | yes | yes |  | wafw00f.tag.jsonl |
| 501 | Wappalyzer | wappalyzer | 5 | passive | api | extracted | live_host | tech |  |  |  | wappalyzer.tech.jsonl |
| 502 | Wappalyzer API | wappalyzer-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | wappalyzer-api.service.jsonl |
| 503 | Wappalyzer Lookup | wappalyzer-lookup | 1 | passive | api | extracted | domain | ip |  |  |  | wappalyzer-lookup.ip.jsonl |
| 504 | Wayback Machine | wayback-machine | 6 | passive | api | extracted | domain, live_host | url |  |  |  | wayback-machine.url.jsonl |
| 505 | waybackurls | waybackurls | 4 | passive | cli | extracted | domain | url | yes | yes |  | waybackurls.url.jsonl |
| 506 | Waymore | waymore | 6 | passive | cli | extracted | domain | url | yes | yes |  | waymore.url.jsonl |
| 507 | Web Archive Search | web-archive-search | 4 | passive | api | extracted | domain, live_host | url |  |  |  | web-archive-search.url.jsonl |
| 508 | webanalyze | webanalyze | 5 | passive | cli | extracted | live_host | tech |  |  |  | webanalyze.tech.jsonl |
| 509 | webscreenshot | webscreenshot | 13 | active | cli | extracted | live_host | screenshot |  |  |  | webscreenshot.screenshot.jsonl |
| 510 | WebSniffer | websniffer | 5 | passive | web | extracted | live_host | tech |  |  | yes | websniffer.tech.jsonl |
| 511 | WebTech | webtech | 5 | passive | api | extracted | live_host | tech |  |  |  | webtech.tech.jsonl |
| 512 | WhatCMS | whatcms | 5 | passive | api | extracted | live_host | tech |  |  |  | whatcms.tech.jsonl |
| 513 | WhatRuns | whatruns | 5 | passive | web | extracted | live_host | tech |  |  | yes | whatruns.tech.jsonl |
| 514 | WhatsApp Web Enumeration | whatsapp-web-enumeration | 8 | active | web | extracted | username, org | finding |  |  | yes | whatsapp-web-enumeration.finding.jsonl |
| 515 | WhatsMyName | whatsmyname | 7 | passive | web | extracted | domain, email | email |  |  | yes | whatsmyname.email.jsonl |
| 516 | WhatWeb | whatweb | 5 | active | cli | extracted | url | tech | yes | yes |  | whatweb.tech.jsonl |
| 517 | Whitepages | whitepages | 7 | passive | api | extracted | domain, email | email |  |  |  | whitepages.email.jsonl |
| 518 | WhoisXML API | whoisxml-api | 2 | passive | api | extracted | domain | subdomain |  |  |  | whoisxml-api.subdomain.jsonl |
| 519 | Wigle | wigle | 1 | passive | api | extracted | domain | ip |  |  |  | wigle.ip.jsonl |
| 520 | WiGLE WiFi Search | wigle-wifi-search | 15 | passive | api | extracted | org, coords | finding |  |  |  | wigle-wifi-search.finding.jsonl |
| 521 | WitnessMe | witnessme | 13 | active | cli | extracted | live_host | screenshot |  |  |  | witnessme.screenshot.jsonl |
| 522 | WPScan | wpscan | 5 | active | cli | extracted | live_host | tech |  |  |  | wpscan.tech.jsonl |
| 523 | xnLinkFinder | xnlinkfinder | 4 | passive | cli | extracted | domain, live_host | url |  |  |  | xnlinkfinder.url.jsonl |
| 524 | Yandex Search | yandex-search | 1 | passive | api | extracted | domain | ip |  |  |  | yandex-search.ip.jsonl |
| 525 | YARAify | yaraify | 12 | passive | api | extracted | ip, domain, service | finding |  |  |  | yaraify.finding.jsonl |
| 526 | YouTube Data Viewer | youtube-data-viewer | 8 | passive | web | extracted | username, org | finding |  |  | yes | youtube-data-viewer.finding.jsonl |
| 527 | YouTube Metadata | youtube-metadata | 8 | passive | api | extracted | username, org | finding |  |  |  | youtube-metadata.finding.jsonl |
| 528 | Zoom Earth | zoom-earth | 15 | passive | web | extracted | org, coords | finding |  |  | yes | zoom-earth.finding.jsonl |
| 529 | ZoomEye | zoomeye | 1 | passive | api | extracted | domain | ip |  |  |  | zoomeye.ip.jsonl |
| 530 | ZoomEye API | zoomeye-api | 17 | passive | api | extracted | domain, ip, email | service |  |  |  | zoomeye-api.service.jsonl |
| 531 | ZoomEye Cyberspace Search | zoomeye-cyberspace-search | 1 | passive | api | extracted | domain | ip |  |  |  | zoomeye-cyberspace-search.ip.jsonl |
| 532 | alterx | alterx | Subdomain permutation | passive | cli | suggested | subdomain | subdomain | yes | yes |  | alterx.subdomain.jsonl |
| 533 | anew | anew | Glue / dedupe | passive | cli | suggested | any | any | yes | yes |  | raw/<slug>/ |
| 534 | cdncheck | cdncheck | Noise control / CDN exclusion | passive | cli | suggested |  | tag | yes | yes |  | cdncheck.tag.jsonl |
| 535 | cero | cero | Cert-to-host pivot | passive | cli | suggested |  | subdomain | yes | yes |  | cero.subdomain.jsonl |
| 536 | clairvoyance | clairvoyance | API & GraphQL recon | active | cli | suggested | url | endpoint |  |  |  | clairvoyance.endpoint.jsonl |
| 537 | dalfox | dalfox | Active vuln detection | active | cli | suggested |  | finding |  |  |  | dalfox.finding.jsonl |
| 538 | dnsgen | dnsgen | Subdomain permutation | passive | cli | suggested | subdomain | subdomain |  |  |  | dnsgen.subdomain.jsonl |
| 539 | dsieve | dsieve | Glue / domain filter | passive | cli | suggested | subdomain | subdomain |  |  |  | dsieve.subdomain.jsonl |
| 540 | fav-up | fav-up | Favicon pivot | passive | cli | suggested | live_host | ip |  |  |  | fav-up.ip.jsonl |
| 541 | FavFreak | favfreak | Favicon pivot | passive | cli | suggested | live_host | tag |  |  |  | favfreak.tag.jsonl |
| 542 | feroxbuster | feroxbuster | Content & directory discovery | active | cli | suggested | live_host | url | yes | yes |  | feroxbuster.url.jsonl |
| 543 | ffuf | ffuf | Content & directory discovery | active | cli | suggested | live_host | url | yes | yes |  | ffuf.url.jsonl |
| 544 | fingerprintx | fingerprintx | Service fingerprinting | active | cli | suggested | live_host |  |  |  |  | raw/<slug>/ |
| 545 | gf | gf | Glue / pattern grep | passive | cli | suggested | url | url | yes | yes |  | gf.url.jsonl |
| 546 | github-subdomains | github-subdomains | Subdomain enum (code) | passive | cli | suggested | domain | subdomain | yes | yes |  | github-subdomains.subdomain.jsonl |
| 547 | gitlab-subdomains | gitlab-subdomains | Subdomain enum (code) | passive | cli | suggested | domain | subdomain |  |  |  | gitlab-subdomains.subdomain.jsonl |
| 548 | gospider | gospider | Crawling | active | cli | suggested | live_host | url |  |  |  | gospider.url.jsonl |
| 549 | gotator | gotator | Subdomain permutation | passive | cli | suggested | subdomain | subdomain |  |  |  | gotator.subdomain.jsonl |
| 550 | graphw00f | graphw00f | API & GraphQL recon | active | cli | suggested | live_host | tech | yes | yes |  | graphw00f.tech.jsonl |
| 551 | jsluice | jsluice | JavaScript analysis | passive | cli | suggested | js_file |  | yes | yes |  | raw/<slug>/ |
| 552 | kiterunner | kiterunner | API & GraphQL recon | active | cli | suggested | live_host | endpoint | yes | yes |  | kiterunner.endpoint.jsonl |
| 553 | mantra | mantra | JavaScript analysis | passive | cli | suggested | js_file | secret |  |  |  | mantra.secret.jsonl |
| 554 | mapcidr | mapcidr | CIDR utility | passive | cli | suggested |  |  | yes | yes |  | raw/<slug>/ |
| 555 | masscan | masscan | Port scanning | active | cli | suggested |  | host_port | yes | yes |  | masscan.host_port.jsonl |
| 556 | metabigor | metabigor | ASN/IP/org OSINT | passive | cli | suggested |  |  | yes | yes |  | raw/<slug>/ |
| 557 | Nmap | nmap | Port scanning & service detection | active | cli | suggested | live_host | service | yes | yes |  | nmap.service.jsonl |
| 558 | qsreplace | qsreplace | Glue / fuzz prep | passive | cli | suggested | url | url |  |  |  | qsreplace.url.jsonl |
| 559 | smap | smap | Passive port scan | passive | cli | suggested |  | service |  |  |  | smap.service.jsonl |
| 560 | SSLyze | sslyze | TLS/SSL analysis | active | cli | suggested | live_host |  | yes | yes |  | raw/<slug>/ |
| 561 | tlsx | tlsx | TLS/SSL analysis | passive | cli | suggested | live_host |  | yes | yes |  | raw/<slug>/ |
| 562 | unfurl | unfurl | Glue / URL parsing | passive | cli | suggested | url |  | yes | yes |  | raw/<slug>/ |
| 563 | x8 | x8 | Parameter discovery | active | cli | suggested | url |  |  |  |  | raw/<slug>/ |
## Sheet: EntityTypes
| canonical entity type | is a primary key? | subsumes (input) |
| --- | --- | --- |
| domain | yes |  |
| subdomain | yes | domain |
| live_host | yes | subdomain, domain |
| url | yes | live_host, subdomain, domain |
| endpoint |  |  |
| ip | yes |  |
| cidr | yes | asn |
| asn | yes |  |
| service |  |  |
| host_port |  |  |
| cert |  |  |
| tech |  |  |
| js_file |  |  |
| secret |  |  |
| bucket |  |  |
| repo |  |  |
| email |  |  |
| username |  |  |
| org |  |  |
| keyword |  |  |
| coords |  |  |
| cpe |  |  |
| file |  |  |
| finding |  |  |
| screenshot |  |  |
| tag |  |  |
| seed |  |  |
| subdomain+path | yes |  |
## Sheet: Routing
| entity_type | # tools (all) | # default_on | # runnable | runnable tools (run now) |
| --- | --- | --- | --- | --- |
| domain | 326 | 24 | 25 | alienvault-otx, amass, asnmap, assetfinder, censys, certspotter, chaos, criminal-ip, crt-sh, findomain, fullhunt, gau, gauplus, github-subdomains, hackertarget, netlas, paramspider, securitytrails, shodan, subfinder, uncover, urlscan, virustotal, waybackurls, waymore |
| subdomain | 335 | 30 | 31 | alienvault-otx, alterx, amass, asnmap, assetfinder, censys, certspotter, chaos, criminal-ip, crt-sh, dnsx, findomain, fullhunt, gau, gauplus, github-subdomains, hackertarget, httpx, massdns, netlas, paramspider, puredns, securitytrails, shodan, subfinder, subjack, uncover, urlscan, virustotal, waybackurls, waymore |
| live_host | 384 | 37 | 38 | alienvault-otx, alterx, amass, asnmap, assetfinder, censys, certspotter, chaos, criminal-ip, crt-sh, dnsx, feroxbuster, ffuf, findomain, fullhunt, gau, gauplus, github-subdomains, graphw00f, hackertarget, httpx, kiterunner, massdns, netlas, nmap, paramspider, puredns, securitytrails, shodan, sslyze, subfinder, subjack, tlsx, uncover, urlscan, virustotal, waybackurls, waymore |
| url | 415 | 44 | 45 | alienvault-otx, alterx, amass, asnmap, assetfinder, censys, certspotter, chaos, criminal-ip, crt-sh, dnsx, feroxbuster, ffuf, findomain, fullhunt, gau, gauplus, gf, github-subdomains, gowitness, graphw00f, hackertarget, httpx, katana, kiterunner, massdns, netlas, nmap, nuclei, paramspider, puredns, securitytrails, shodan, sslyze, subfinder, subjack, tlsx, uncover, unfurl, urlscan, virustotal, wafw00f, waybackurls, waymore, whatweb |
| ip | 89 | 5 | 5 | greynoise, internetdb, ipinfo, leakix, naabu |
| cidr | 35 | 2 | 2 | bgpview, ripestat |
| asn | 35 | 2 | 2 | bgpview, ripestat |
| service | 29 | 0 | 0 |  |
| js_file | 4 | 3 | 3 | jsluice, linkfinder, secretfinder |
| bucket | 1 | 1 | 1 | s3scanner |
| repo | 2 | 2 | 2 | gitleaks, trufflehog |
| email | 73 | 0 | 0 |  |
| username | 28 | 0 | 0 |  |
| org | 91 | 0 | 0 |  |
| keyword | 39 | 2 | 2 | cloud-enum, grayhatwarfare |
| coords | 16 | 0 | 0 |  |
| cpe | 2 | 2 | 2 | nvd, vulners |
| file | 21 | 0 | 0 |  |
## Sheet: WorkQueue
| job_id | key | key_type | parent_key | depth | tool | status | output_path | started_at | finished_at | new_keys_found |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | grow.in | domain |  | 0 | subfinder | completed | out/grow.in/subfinder.subdomain.jsonl | 10:00:01 | 10:00:14 | 37 |
| 2 | grow.in | domain |  | 0 | crt-sh | completed | out/grow.in/crt-sh.subdomain.jsonl | 10:00:01 | 10:00:09 | 12 |
| 3 | api.grow.in | subdomain | grow.in | 1 | dns_resolve | in_progress | out/api.grow.in/dns_resolve.ip.jsonl | 10:00:20 |  |  |
| 4 | api.grow.in | subdomain | grow.in | 1 | httpx | pending |  |  |  |  |
| 5 | 20.40.11.7 | ip | api.grow.in | 2 | naabu | pending |  |  |  |  |
| 6 | api.grow.in/admin | subdomain+path | api.grow.in | 2 | ffuf | pending |  |  |  |  |
| Lifecycle: pending -> in_progress -> completed | failed. A worker pulls the next 'pending' row, runs the tool, writes the typed output, sets completed, and emits new keys as fresh rows (the recursion). enqueue() dedupes on (scan_id, key, tool), so a re-discovered key is never rescanned. |  |  |  |  |  |  |  |  |  |  |