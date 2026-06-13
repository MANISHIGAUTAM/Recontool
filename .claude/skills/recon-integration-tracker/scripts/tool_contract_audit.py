#!/usr/bin/env python3
"""Per-tool contract auditor — checks every RUNNABLE tool across the dimensions
that have repeatedly hidden silent breakage, derived fresh from the repo:

  INPUT   every {token} in the invocation/endpoint is fillable by the generic
          adapter (consumes-type aliases + value/domain/ip/host[/asn/key]).
          Catches the {infile}/{outfile}/{resolvers}/{wordlist}/{key} class:
          tokens that render to "" -> malformed argv -> 0 results, no error.
  NOEXEC  integration=python but no handwritten adapter class exists -> the
          tool has no real executor.
  OUTPUT  a non-handwritten tool with no parse.emit falls back to _default_parse,
          which only maps subdomain/domain/live_host (text) + url/endpoint; any
          other produced type becomes one garbage asset.

This is intentionally static (no network/subprocess) and reproducible: run it
after any tools.yaml / adapter change. A clean tool is invoked correctly, has a
real executor, and maps its output to canonical entities. It does NOT prove the
tool is reachable in a given scan (that depends on the producer chain) — use the
live work_item queue for that.

Usage:  python3 .claude/skills/recon-integration-tracker/scripts/tool_contract_audit.py [--all|--default]
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict

from recontool.engine import adapters_bridge
from recontool.engine.execution import plan_execution, to_generic_spec
from recontool.engine.runner import load_engine_registry

TOKEN = re.compile(r"\{([a-zA-Z0-9_.]+)\}")
DEFAULT_PARSE_OK = {"subdomain", "domain", "live_host", "url", "endpoint"}


def audit(mode: str = "all") -> dict[str, list]:
    reg = load_engine_registry(tools=mode, authorize_active=True)
    tools = {n: s for n, s in reg.all_tools().items() if plan_execution(s).runnable}
    handwritten = set(adapters_bridge.python_adapter_classes().keys())
    issues: dict[str, list] = defaultdict(list)
    clean = 0

    for name, s in sorted(tools.items()):
        integ = getattr(s, "integration", "")
        gs = to_generic_spec(s) or {}
        consumes = set(gs.get("consumes") or ())
        produces = tuple(gs.get("produces") or getattr(s, "produces", ()) or ())
        probs: list[tuple[str, str]] = []

        if name in handwritten:
            clean += 1
            continue

        tmpl = gs.get("endpoint") if integ == "api" else gs.get("invocation")
        if tmpl:
            base = {"value", "domain", "ip", "host"}
            if integ == "api":
                base |= {"asn", "key"}
            fillable = consumes | base
            bad = sorted({t for t in TOKEN.findall(tmpl) if t not in fillable})
            if bad:
                probs.append(("INPUT", f"unfillable {bad} in: {tmpl[:62]}"))

        if integ == "python":
            probs.append(("NOEXEC", "integration=python but no handwritten adapter"))
        else:
            has_parse = "parse" in gs and (gs["parse"] or {}).get("emit")
            if not has_parse:
                mishandled = [p for p in produces if p not in DEFAULT_PARSE_OK]
                if mishandled or not produces:
                    probs.append(("OUTPUT", f"no parse; produces {produces or '()'} -> _default_parse"))

        if probs:
            for kind, msg in probs:
                issues[kind].append((name, integ, msg))
        else:
            clean += 1

    issues["_meta"] = [("total", "", str(len(tools))), ("clean", "", str(clean))]
    return issues


def main() -> int:
    mode = "default" if "--default" in sys.argv else "all"
    issues = audit(mode)
    total = next(v for k, _, v in issues["_meta"] if k == "total")
    clean = next(v for k, _, v in issues["_meta"] if k == "clean")
    bad = int(total) - int(clean)
    print(f"=== tool contract audit ({mode}) — runnable {total}, clean {clean}, issues {bad} ===\n")
    for kind in ("INPUT", "NOEXEC", "OUTPUT"):
        rows = issues.get(kind, [])
        print(f"### {kind}: {len(rows)}")
        for name, integ, msg in rows:
            print(f"   [{integ:6}] {name:22} {msg}")
        print()
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
