#!/usr/bin/env python3
"""Per-tool invocation probe: render each CLI tool's command the way the engine
would (shape-correct tokens + aux files), run it IN ISOLATION against a real
target, and report exit code / stdout bytes / stderr snippet — so we can see,
with evidence, which tools produce vs run-empty-due-to-flags/timeout/input.

Usage (in container): python3 scripts/tool_invocation_probe.py [domain] [url] [--only a,b,c]
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import time

from recontool.adapters.generic import _aux_tokens, _shape_tokens, render_template
from recontool.engine.runner import load_engine_registry


class _Ctx:
    """Minimal context exposing just what _aux_tokens reads (profile fields)."""
    class _P:
        port_set = "top-1000"
        requests_per_second = 100
        global_concurrency = 20
    profile = _P()


def _render(spec, value: str) -> str | None:
    inv = spec.invocation or ""
    if not inv or spec.integration != "cli":
        return None
    # _aux_tokens wants a dict-like spec; pass the pydantic dump.
    try:
        sd = spec.model_dump()
    except Exception:  # noqa: BLE001
        sd = dict(spec.__dict__)
    extra = dict(_aux_tokens(sd, _Ctx()))
    extra.update(_shape_tokens(value))
    for t in (spec.consumes or []):
        extra.setdefault(t, value)
    return render_template(inv, {}, extra)


def probe(domain: str, url: str, only: set[str] | None):
    reg = load_engine_registry(tools="all", authorize_active=True)
    rows = []
    for name, spec in sorted(reg.all_tools().items()):
        if spec.integration != "cli" or not spec.enabled:
            continue
        if only and name not in only:
            continue
        binary = spec.binary
        if not binary or shutil.which(binary) is None:
            rows.append((name, "(binary absent)", "-", "-", "skip-binary"))
            continue
        # pick the input form the tool's primary consumed type wants
        primary = (spec.consumes or ["domain"])[0]
        value = url if primary in ("url", "live_host") else domain
        cmd = _render(spec, value)
        if not cmd:
            continue
        use_stdin = bool(spec.get("stdin") if isinstance(spec, dict) else getattr(spec, "stdin", False))
        stdin_val = _shape_tokens(value).get(primary, value) if use_stdin else None
        t0 = time.monotonic()
        try:
            p = subprocess.run(
                cmd.split(), input=(stdin_val + "\n").encode() if stdin_val else None,
                capture_output=True, timeout=90)
            out_b = len(p.stdout)
            err = (p.stderr.decode(errors="ignore").strip().replace("\n", " ")[:80])
            verdict = "PRODUCES" if out_b > 0 else ("empty(rc=%d)" % p.returncode)
        except subprocess.TimeoutExpired:
            out_b, err, verdict = -1, "(90s timeout)", "TIMEOUT"
        except Exception as exc:  # noqa: BLE001
            out_b, err, verdict = -1, str(exc)[:80], "ERROR"
        dur = int((time.monotonic() - t0) * 1000)
        rows.append((name, cmd[:70], f"{out_b}", f"{dur}ms", verdict + ("  " + err if err else "")))

    print(f"{'TOOL':20} {'RENDERED COMMAND':70} {'OUT':>8} {'TIME':>7}  VERDICT")
    print("-" * 140)
    for name, cmd, out, dur, verdict in rows:
        print(f"{name:20} {cmd:70} {out:>8} {dur:>7}  {verdict}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("domain", nargs="?", default="groww.in")
    ap.add_argument("url", nargs="?", default="https://groww.in")
    ap.add_argument("--only", default=None, help="comma-separated tool names")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None
    probe(args.domain, args.url, only)


if __name__ == "__main__":
    main()
