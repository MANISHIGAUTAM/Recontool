#!/usr/bin/env python3
"""Build the end-to-end EXECUTION flow for a root domain.

Merges:
  data/tool_inventory.json   (all 532 canonical tools, derived tags)
  config/tools.yaml          (REAL invocation contracts for wired tools)

and emits, for a sample root domain (xyz.com):
  data/flow_plan.json                      - machine-readable execution plan
  docs/flow/00-MASTER-FLOW.md              - master diagram + stage ordering + example
  docs/flow/by-category/<NN>.md            - per-category execution table:
        every tool -> invoke method (binary/api/web) + flags/params +
        expected output + how output feeds the next tool + where stored

Where a tool has a real contract in config/tools.yaml, that invocation is used
(authoritative). Otherwise a TEMPLATE invocation is generated from the tool's
integration mode + category stage and clearly marked `(t)`.

Pure stdlib. Run:  python -m recontool.inventory.build_flow
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
INVENTORY = REPO / "data" / "tool_inventory.json"
TOOLS_YAML = REPO / "config" / "tools.yaml"
FLOW_DIR = REPO / "docs" / "flow"
CAT_DIR = FLOW_DIR / "by-category"
SAMPLE = "xyz.com"

# ── per-spreadsheet-section execution mapping ────────────────────────────────
SECTION_FLOW = {
    1:  ("S1 Seed discovery", "passive", "domain", "S2 resolve, S4 ip-track"),
    2:  ("S1->S2 Subdomain discovery + resolution", "passive+active-validate", "domain", "S2 httpx, S4 ports"),
    3:  ("S4 Network intelligence", "enrich", "ip_or_asn", "S4 port-scan, back to S2"),
    4:  ("S3/S5 URL + dork harvesting", "passive", "domain_or_live_host", "S5 js/params, vuln"),
    5:  ("S2/S5 Web fingerprint + probe", "active-validate", "live_host", "S6 vuln, CVE-corr"),
    6:  ("S3 Historical/archive harvest", "passive", "domain_or_live_host", "S5 js/params"),
    7:  ("Enrichment: email/identity", "enrich", "domain_or_email", "report (PII-gated)"),
    8:  ("Enrichment: social media", "enrich", "username_or_org", "report"),
    9:  ("Enrichment: source-code/secrets", "enrich", "org_or_domain", "S1 hosts, cloud check"),
    10: ("Enrichment: cloud & storage", "active-enrich", "org_or_keyword", "findings"),
    11: ("Enrichment: metadata/documents", "enrich", "file_or_url", "S7 usernames, paths"),
    12: ("S6 Malware/IOC/CVE correlation", "enrich", "ip_domain_service", "S6 nuclei confirm"),
    13: ("S5 Visual recon", "active-enrich", "live_host", "report/triage"),
    14: ("Engine: frameworks/orchestration", "engine", "domain", "(wraps other stages)"),
    15: ("Enrichment: geo/wireless", "enrich", "org_or_coords", "report (scope-dependent)"),
    16: ("Enrichment: dark web", "enrich", "keyword_or_domain", "report"),
    17: ("Enrichment: API intel feeds", "enrich", "domain_ip_email", "used across stages"),
    18: ("Reference index (NOT executed)", "ref", "none", "tool discovery only"),
    19: ("Workflow preset (composite)", "engine", "domain", "(chains S1-S6)"),
}

INPUT_EXPR = {
    "domain": f"{SAMPLE}",
    "domain_or_email": f"{SAMPLE} / emails@{SAMPLE}",
    "domain_or_live_host": f"{SAMPLE} + <live hosts from S2>",
    "live_host": "<live hosts from httpx (S2)>",
    "ip_or_asn": "<IPs/ASN from S1/S3 WHOIS>",
    "ip_domain_service": "<IPs/services from S2/S4>",
    "org_or_domain": f"org name + {SAMPLE} (from WHOIS)",
    "org_or_keyword": f"xyz keywords + {SAMPLE}",
    "username_or_org": "<usernames/org from S7>",
    "file_or_url": "<docs/URLs harvested in S3>",
    "org_or_coords": "org name / BSSID / coords",
    "keyword_or_domain": f"xyz keywords + {SAMPLE}",
    "domain_ip_email": f"{SAMPLE} / <IPs> / <emails>",
    "none": "(n/a - reference list)",
}

STORAGE = {
    "subdomain":  ("asset(type=subdomain)", "raw/<tool>/"),
    "ip":         ("asset(type=ip)", "raw/<tool>/"),
    "cidr":       ("asset(type=cidr)", "raw/<tool>/"),
    "asn":        ("asset(type=asn)+edge(announced_by)", "raw/<tool>/"),
    "cert":       ("asset(type=cert)+service.tls", "raw/<tool>/"),
    "service":    ("service(port,product,version)", "raw/<tool>/"),
    "host_port":  ("service(port)", "raw/<tool>/"),
    "url":        ("endpoint(url,status,title)", "raw/<tool>/ , bodies/"),
    "js_file":    ("endpoint.js_artifact ptr", "js/<host>/*.js"),
    "screenshot": ("endpoint.evidence_ref ptr", "screenshots/*.png"),
    "finding":    ("finding(kind,severity,detector)", "raw/<tool>/"),
    "secret":     ("finding(kind=secret,redacted)", "raw/<tool>/ (hashed)"),
    "tag":        ("asset.tags[]", "-"),
    "email":      ("asset(type=email)", "raw/<tool>/"),
    "tech":       ("asset.tech[]", "raw/<tool>/"),
    "repo":       ("asset(type=repo)", "repos/<org>/"),
    "bucket":     ("asset(type=bucket)", "raw/<tool>/"),
    "cpe":        ("vuln_ref(cpe)", "raw/<tool>/"),
    "any":        ("(passthrough)", "raw/<tool>/"),
    "none":       ("-", "-"),
    "resolver_list": ("(config)", "config/resolvers.txt"),
}

SECTION_OUTPUT = {
    1: "ip", 2: "subdomain", 3: "cidr", 4: "url", 5: "tech", 6: "url",
    7: "email", 8: "finding", 9: "secret", 10: "bucket", 11: "finding",
    12: "finding", 13: "screenshot", 14: "any", 15: "finding", 16: "finding",
    17: "service", 18: "none", 19: "subdomain",
}


def alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def sec_num(section: str) -> int:
    m = re.match(r"\s*(\d+)\.", section or "")
    return int(m.group(1)) if m else 0


def load_yaml_contracts() -> dict:
    out = {}
    try:
        import yaml
        data = yaml.safe_load(TOOLS_YAML.read_text()) or {}
    except Exception:
        data = {}
    for name, c in (data.get("tools") or {}).items():
        if isinstance(c, dict):
            out[alnum(name)] = {**c, "_yaml_name": name}
            if c.get("binary"):
                out[alnum(c["binary"])] = {**c, "_yaml_name": name}
    # also merge the declarative generic specs (config/tools_generic.yaml)
    gpath = REPO / "config" / "tools_generic.yaml"
    try:
        import yaml
        gdata = yaml.safe_load(gpath.read_text()) or {}
    except Exception:
        gdata = {}
    for spec in (gdata.get("tools") or []):
        if not isinstance(spec, dict) or not spec.get("name"):
            continue
        norm = {
            "_yaml_name": spec["name"],
            "integration": spec.get("integration", "cli"),
            "invocation": spec.get("invocation") or spec.get("endpoint", ""),
            "binary": spec.get("binary"),
            "input": (spec.get("consumes") or ["domain"])[0],
            "output": (spec.get("produces") or ["any"])[0],
            "requires_key": spec.get("requires_key"),
        }
        out.setdefault(alnum(spec["name"]), norm)
    return out


def contract_for(tool: dict, yaml_map: dict):
    return yaml_map.get(alnum(tool["name"])) or yaml_map.get(alnum(tool["slug"]))


def invocation(tool: dict, contract, section: int) -> dict:
    stage_in = SECTION_FLOW.get(section, ("", "", "domain", ""))[2]
    inp = INPUT_EXPR.get(stage_in, SAMPLE)
    if contract:
        integ = contract.get("integration", "cli")
        method = {"cli": "binary", "api": "API", "python": "python",
                  "dataset": "dataset"}.get(integ, integ)
        cmd = (contract.get("invocation", "") or "")
        cmd = cmd.replace("{domain}", SAMPLE).replace("{infile}", "<input.txt>")
        key = contract.get("requires_key")
        params = f"key: {key}" if key else "no key"
        return {"method": method, "command": cmd, "params": params,
                "output": contract.get("output", SECTION_OUTPUT.get(section, "any")),
                "input": contract.get("input", stage_in), "real": True}
    modes = tool["integration_modes"]
    out = SECTION_OUTPUT.get(section, "any")
    if tool["web_only"]:
        return {"method": "web/manual", "command": f"(web UI - query {inp})",
                "params": "manual / scripted browser", "output": out,
                "input": stage_in, "real": False}
    if "cli" in modes:
        return {"method": "binary", "command": f"{tool['slug']} <{stage_in}>  # flags TBD",
                "params": "-", "output": out, "input": stage_in, "real": False}
    if "api" in modes:
        kw = " (needs API key)" if tool["cost_tier"] in ("paid", "freemium") else ""
        return {"method": "API", "command": f"GET https://<{tool['slug']}-endpoint>/?q={inp}{kw}",
                "params": "key per config" if kw else "no key", "output": out,
                "input": stage_in, "real": False}
    if "dataset" in modes:
        return {"method": "dataset", "command": f"download dataset; query {inp}",
                "params": "bulk", "output": out, "input": stage_in, "real": False}
    return {"method": "unspecified", "command": f"(classify before wiring; input {inp})",
            "params": "-", "output": out, "input": stage_in, "real": False}


def build():
    inv = json.loads(INVENTORY.read_text())
    yaml_map = load_yaml_contracts()
    tools = inv["tools"]

    by_section = {n: [] for n in SECTION_FLOW}
    plan_tools = []
    for t in tools:
        secs = sorted({sec_num(s) for s in t["sections"]})
        primary = secs[0] if secs else 0
        contract = contract_for(t, yaml_map)
        inv_call = invocation(t, contract, primary)
        store = STORAGE.get(inv_call["output"], STORAGE["any"])
        entry = {
            "name": t["name"], "slug": t["slug"],
            "classification": t["classification"],
            "primary_section": primary, "sections": secs,
            "method": inv_call["method"], "command": inv_call["command"],
            "params": inv_call["params"], "consumes": inv_call["input"],
            "produces": inv_call["output"],
            "feeds": SECTION_FLOW.get(primary, ("", "", "", ""))[3],
            "store_db": store[0], "store_fs": store[1],
            "real_contract": inv_call["real"], "web_only": t["web_only"],
        }
        by_section.setdefault(primary, []).append(entry)
        plan_tools.append(entry)

    FLOW_DIR.mkdir(parents=True, exist_ok=True)
    CAT_DIR.mkdir(parents=True, exist_ok=True)

    (REPO / "data" / "flow_plan.json").write_text(json.dumps({
        "sample_domain": SAMPLE,
        "generated_from": ["data/tool_inventory.json", "config/tools.yaml"],
        "stages": {str(k): v[0] for k, v in SECTION_FLOW.items()},
        "tools": plan_tools,
    }, indent=2))

    for n in sorted(k for k in by_section if k):
        (CAT_DIR / f"{n:02d}.md").write_text(_render_category(n, by_section[n]))

    (FLOW_DIR / "00-MASTER-FLOW.md").write_text(_render_master(by_section))

    real = sum(1 for t in plan_tools if t["real_contract"])
    print("flow build complete")
    print(f"  tools planned        : {len(plan_tools)}")
    print(f"  real invocations     : {real}  (from config/tools.yaml)")
    print(f"  templated invocations: {len(plan_tools) - real}")
    print("  outputs              : data/flow_plan.json, docs/flow/00-MASTER-FLOW.md,")
    print("                         docs/flow/by-category/*.md")


def _render_category(n: int, entries: list) -> str:
    stage, kind, input_kind, feeds = SECTION_FLOW[n]
    inp = INPUT_EXPR.get(input_kind, SAMPLE)
    L = [f"# Category {n} - execution flow\n",
         f"**Pipeline stage:** {stage}  ·  **kind:** {kind}  ",
         f"**Input for `{SAMPLE}`:** `{inp}`  ·  **feeds ->** {feeds}\n",
         f"{len(entries)} tools. Invocations marked *(t)* are templates (no exact "
         f"contract in `config/tools.yaml` yet); unmarked are authoritative.\n",
         "| Tool | Method | Command / endpoint (flags) | Consumes | Produces | Feeds -> | Stored |",
         "|------|--------|----------------------------|----------|----------|---------|--------|"]
    for e in sorted(entries, key=lambda x: (not x["real_contract"], x["name"].lower())):
        tag = "" if e["real_contract"] else " *(t)*"
        L.append(f"| [{_esc(e['name'])}](../../tools/{e['slug']}.md){tag} | {e['method']} | "
                 f"`{_esc(e['command'])}` | {_esc(e['consumes'])} | {_esc(e['produces'])} | "
                 f"{_esc(e['feeds'])} | {_esc(e['store_db'])} · `{_esc(e['store_fs'])}` |")
    L.append("")
    if kind == "ref":
        L.append("> These are reference indexes/lists for discovering more tools - "
                 "they are **not executed** in the pipeline.\n")
    return "\n".join(L)


def _render_master(by_section: dict) -> str:
    total = sum(len(v) for v in by_section.values())
    real = sum(1 for v in by_section.values() for t in v if t["real_contract"])
    L = []
    L.append("# Master Execution Flow - root domain `xyz.com`\n")
    L.append("How the full inventory executes end-to-end from a single root domain. "
             "Each spreadsheet category maps to a pipeline stage; every tool's "
             "invocation, output, chaining, and storage is in the per-category files "
             "([`by-category/`](by-category/)) and in "
             "[`../../data/flow_plan.json`](../../data/flow_plan.json).\n")
    L.append(f"- **Tools planned:** {total}")
    L.append(f"- **Authoritative invocations (config/tools.yaml):** {real}")
    L.append(f"- **Templated invocations (to be wired):** {total - real}\n")

    L.append("## Stage pipeline (data handoffs)\n")
    L.append("```")
    L.append("root: xyz.com")
    L.append("   |")
    L.append("   v  S1  SEED DISCOVERY            cat 1,2 (passive)   -> subdomains, ips, certs, urls")
    L.append("   |     subfinder crtsh shodan censys netlas urlscan uncover hackertarget otx ...")
    L.append("   v  S2  RESOLVE + LIVE VALIDATE   cat 2,5 (active)    -> ip, LIVE hosts")
    L.append("   |     dnsx puredns massdns -> httpx (sets is_live)  [filters 250 -> ~120 live]")
    L.append("   +---------------+-----------------------------------------------+")
    L.append("   v S3 WEB ENRICH | (per LIVE host)        v S4 IP/NET (per IP)     | overlays")
    L.append("   |  cat 4,6: gau waybackurls katana       cat 3: asnmap bgpview    | run on")
    L.append("   |  -> urls,js_file  cat 13: gowitness    cat 12: internetdb       | org/emails")
    L.append("   v S5 DEEP (per url/js)                    cat 21: naabu->nmap      | cat 7,8,9,")
    L.append("   |  cat 4: linkfinder secretfinder arjun   -> services,cves         | 10,11,15,16")
    L.append("   v S6 VULN (per live host)                                          |")
    L.append("   |  cat 5,12: nuclei subjack sslyze -> findings  <----CVE corr------+")
    L.append("   v")
    L.append("  REPORT / EXPORT / GRAPH / DIFF   (DB + artifacts/<scan_id>/)")
    L.append("```\n")

    L.append("## Mermaid graph\n")
    L.append("```mermaid")
    L.append("flowchart TD")
    L.append('  ROOT["root: xyz.com"]')
    L.append('  S1["S1 Seed discovery (cat 1,2 passive)"]')
    L.append('  S2["S2 Resolve + live validate (cat 2,5 active)"]')
    L.append('  S3["S3 Web enrich per live host (cat 4,6,13)"]')
    L.append('  S4["S4 IP/Net track per IP (cat 3,12,21)"]')
    L.append('  S5["S5 Deep per url/js (cat 4)"]')
    L.append('  S6["S6 Vuln surface (cat 5,12)"]')
    L.append('  OV["Enrichment overlays (cat 7,8,9,10,11,15,16,17)"]')
    L.append('  REF["cat 18 reference indexes (not executed)"]')
    L.append('  OUT["Report / Graph / Diff (DB + artifacts/)"]')
    L.append("  ROOT --> S1 --> S2")
    L.append("  S2 --> S3")
    L.append("  S2 --> S4")
    L.append("  S3 --> S5 --> S6")
    L.append("  S4 --> S6")
    L.append("  S1 --> OV")
    L.append("  S3 -. new subs/urls .-> S2")
    L.append("  S6 --> OUT")
    L.append("  OV --> OUT")
    L.append("  REF -. discovery only .-> OUT")
    L.append("```\n")

    L.append("## Categories -> stage map\n")
    L.append("| Cat | Stage | Tools | Per-category execution detail |")
    L.append("|-----|-------|-------|-------------------------------|")
    for n in sorted(SECTION_FLOW):
        stage = SECTION_FLOW[n][0]
        cnt = len(by_section.get(n, []))
        L.append(f"| {n} | {_esc(stage)} | {cnt} | "
                 f"[by-category/{n:02d}.md](by-category/{n:02d}.md) |")
    L.append("")

    L.append("## Worked example - cardinality for `xyz.com`\n")
    L.append("```")
    L.append("1 root domain")
    L.append("  +- S1 passive (cat 1,2) ........ 250 subdomains, 40 ips, 12 certs")
    L.append("     +- S2 resolve+httpx ......... 180 resolve -> 120 LIVE (130 stored as dead)")
    L.append("        +- S3 per-live-host ...... gau/katana -> ~23k urls + 300 js + screenshots")
    L.append("        +- S4 per-ip ............. asnmap->14 cidrs, naabu->320 ports, nmap->services")
    L.append("           +- S5/S6 ............. params, JS secrets, nuclei -> findings")
    L.append("active scans run ONLY on the 120 live hosts; all 250 stored & displayed")
    L.append("```\n")
    L.append("Per-tool invocation/flags/output/storage for **every** tool is in the "
             "per-category files above and `data/flow_plan.json`.\n")
    return "\n".join(L)


def _esc(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


if __name__ == "__main__":
    build()
