#!/usr/bin/env python3
"""Static contract audit over EVERY wired tool in the live engine registry.

Environment-independent (no binaries/keys/DB needed): loads the SAME ToolRegistry
the live engine uses and validates each tool's declarative contract. Complements
flow_lint, which reads only DECLARED types and therefore cannot see a
declared-vs-emit mismatch (a tool that declares producing a type its parse.emit
never actually emits — the "phantom type" bug class).

Checks, per wired tool:
  * ERROR  consumes / produces / parse.emit reference a NON-canonical entity type
           (not in categories.yaml meta.dedupe_forms, and not a known sentinel).
  * ADVISORY  declared produces but parse.emit emits something else, or vice-versa
           (some of these are INTENTIONAL — e.g. URL-discovery tools declare
           `url` for flow-graph reachability but emit `endpoint`, the recursion
           terminal, on purpose; see docs. Surfaced so NEW drift is noticed).
  * ADVISORY  invocation references a {token} that is not a known entity/aux token.

Exit code: non-zero iff any ERROR (genuinely non-canonical type) is found, so it
can gate CI. Advisories never fail the build.

Usage:  PYTHONPATH=$(pwd) python3 scripts/contract_audit.py [--verbose]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

from recontool.engine.runner import load_engine_registry


def find_root(start: Path) -> Path:
    for cand in [start, *start.parents]:
        if (cand / "config" / "categories.yaml").exists():
            return cand
    raise SystemExit("ERROR: could not locate repo root (need config/categories.yaml)")


# structural emit kinds emit_one can produce that are not entity dedupe_forms
STRUCTURAL = {"edge"}
# sentinel input/output markers used by glue/infra tools (anew/notify/dnsvalidator/
# interactsh): they operate on files/streams, not target entities. Allow-listed so
# the audit stays green in the intended state and only flags NEW non-canonical types.
SENTINEL = {"any", "none", "resolver_list"}

# known invocation tokens the engine resolves (aux files + scan scalars + the
# batch-file plumbing tokens); entity types are added from dedupe_forms below.
AUX = {
    "key", "value", "asn", "wordlist", "dns_wordlist", "resolvers", "fingerprints",
    "kite_wordlist", "ports", "rate", "threads", "host", "scheme", "port", "path",
    "asset", "seed", "infile", "outfile",
}
TOKEN = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def emit_types(parse: dict | None) -> set[str]:
    """Actual entity types a parse.emit block produces (mirrors generic._emit_one)."""
    out: set[str] = set()
    for rule in (parse or {}).get("emit", []):
        ent = rule.get("entity", "asset")
        out.add(rule.get("type", "subdomain") if ent == "asset" else ent)
    return out


def declared_out(s) -> set[str]:
    return set(s.produces or []) | set(s.produces_entities or []) | set(s.output_types or [])


def main() -> int:
    verbose = "--verbose" in sys.argv
    root = find_root(Path(__file__).resolve().parent)
    cats = yaml.safe_load((root / "config" / "categories.yaml").read_text())
    canon = set(cats["meta"]["dedupe_forms"].keys())
    valid = canon | STRUCTURAL | SENTINEL

    reg = load_engine_registry()
    tools = reg._tools

    errors: list[str] = []
    advisories: list[str] = []

    for name, s in sorted(tools.items()):
        consumes = list(s.consumes or []) or list(s.supported_input_types or [])
        produces = declared_out(s)
        et = emit_types(s.parse) if s.parse else set()

        for t in consumes:
            if t not in valid:
                errors.append(f"{name}: non-canonical consumes '{t}'")
        for t in produces | et:
            if t not in valid:
                errors.append(f"{name}: non-canonical type '{t}'")

        if et:
            undeclared = et - produces - {"edge"}
            if undeclared:
                advisories.append(f"{name}: emits {sorted(undeclared)} not in declared produces {sorted(produces)}")
            phantom = produces - et - {"edge"} - SENTINEL
            if phantom and (s.integration or "").lower() != "api":
                advisories.append(f"{name}: declares produces {sorted(phantom)} its parse.emit never emits (phantom)")

        inv = s.invocation or s.endpoint or ""
        unknown = set(TOKEN.findall(inv)) - AUX - canon
        if unknown:
            advisories.append(f"{name}: invocation token(s) {sorted(unknown)} not a known entity/aux token")

    print(f"=== CONTRACT AUDIT — {len(tools)} registry tools ===")
    print(f"ERROR (non-canonical type): {len(errors)}")
    for m in errors:
        print("  ✗ " + m)
    print(f"ADVISORY (declared-vs-emit / tokens): {len(advisories)}")
    if verbose:
        for m in advisories:
            print("  · " + m)
    else:
        print("  (run --verbose to list advisories)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
