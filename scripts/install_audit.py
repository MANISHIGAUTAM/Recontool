#!/usr/bin/env python3
"""Install + dependency readiness audit for every enabled tool.

For each tool the engine would schedule, check that it can actually run:
  * CLI: binary on PATH + required data files (wordlist/resolvers/...) present
  * API: required key present (or key_optional)
  * Python adapters: their shell-out binary (nuclei/nmap/...) + special deps
    (chromium for browser tools, git for gitleaks, .kite for kiterunner)

Emits a readiness table + a summary so we know exactly which tools are
READY vs blocked and WHY. Run inside the container.
"""
from __future__ import annotations

import os
import shutil

from recontool.adapters.generic import missing_aux_file
from recontool.config import settings
from recontool.engine.runner import load_engine_registry

# Python-adapter shell-out binaries (mirrors worker._PY_ADAPTER_BINARY).
_PY_BIN = {
    "nuclei": "nuclei", "naabu": "naabu", "nmap": "nmap", "sslyze": "sslyze",
    "gitleaks": "gitleaks", "whatweb": "whatweb", "gowitness": "gowitness",
}
# Extra runtime deps beyond the main binary (binary -> needed companion).
_EXTRA_DEP = {
    "gowitness": "chromium",        # screenshots need a chromium
    "gitleaks": "git",              # clones repos
    "kiterunner": "kr",
}


def _chromium_present() -> bool:
    if any(shutil.which(b) for b in ("chromium", "chromium-browser", "google-chrome", "chrome")):
        return True
    # playwright-managed chromium
    cache = os.path.expanduser("~/.cache/ms-playwright")
    return os.path.isdir(cache) and any("chromium" in d for d in os.listdir(cache)) \
        if os.path.isdir(cache) else False


def audit():
    reg = load_engine_registry(tools="all", authorize_active=True)
    rows = []
    counts = {"READY": 0, "missing-binary": 0, "missing-datafile": 0,
              "missing-key": 0, "missing-dep": 0}
    for name, spec in sorted(reg.all_tools().items()):
        if not spec.enabled:
            continue
        integ = spec.integration
        status, detail = "READY", ""
        if integ == "cli":
            binary = spec.binary
            if not binary or shutil.which(binary) is None:
                status, detail = "missing-binary", binary or "(none)"
            else:
                miss = missing_aux_file(spec.invocation or "")
                if miss:
                    status, detail = "missing-datafile", miss
        elif integ == "api":
            ke = spec.requires_key
            if ke and not spec.key_optional and not settings.api_key(ke):
                status, detail = "missing-key", ke
        elif integ == "python":
            pbin = _PY_BIN.get(name)
            if pbin and shutil.which(pbin) is None:
                status, detail = "missing-binary", pbin
        # extra deps (browser/git/kite)
        if status == "READY":
            dep = _EXTRA_DEP.get(name)
            if dep == "chromium" and not _chromium_present():
                status, detail = "missing-dep", "chromium"
            elif dep and dep != "chromium" and shutil.which(dep) is None:
                status, detail = "missing-dep", dep
        counts[status] = counts.get(status, 0) + 1
        rows.append((name, integ, status, detail))

    print(f"{'TOOL':24} {'INTEG':8} {'STATUS':16} DETAIL")
    print("-" * 80)
    for name, integ, status, detail in rows:
        mark = "OK " if status == "READY" else "!! "
        print(f"{mark}{name:21} {integ:8} {status:16} {detail}")
    print("-" * 80)
    print(f"SUMMARY ({len(rows)} enabled tools): " +
          "  ".join(f"{k}={v}" for k, v in counts.items() if v))
    blocked = [r for r in rows if r[2] != "READY" and r[2] != "missing-key"]
    print(f"\nBLOCKED (non-key) — need a fix: {len(blocked)}")
    for name, integ, status, detail in blocked:
        print(f"  {name:24} {status}: {detail}")


if __name__ == "__main__":
    audit()
