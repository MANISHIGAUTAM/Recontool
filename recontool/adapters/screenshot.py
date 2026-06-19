"""Screenshot adapters — alternative/redundant headless screenshotters that
mirror the existing gowitness adapter (file-output pattern).

Both are ACTIVE (they fetch the live host with a headless browser) and reachable
only in p5_deep, after the active-authorization gate. Each re-checks scope before
egress and writes into its OWN subdir under ``ctx.artifacts.root`` so it never
collides with gowitness's ``screenshots/`` directory.

These are FILE-output tools: we parse the output DIRECTORY (the new PNGs that
appeared), not stdout.

Grounding (invocation taken verbatim from each official README):
  - aquatone  — https://github.com/michenriksen/aquatone
      Reads URLs/hosts from STDIN, ``-out <dir>``; writes ``screenshots/`` +
      ``aquatone_report.html`` + ``aquatone_session.json``.
        $ cat targets.txt | aquatone -out ~/aquatone/example.com
  - EyeWitness — https://github.com/RedSiege/EyeWitness
      ``eyewitness --web -f urls.txt -d <outdir> --no-prompt``; writes
      ``screens/`` + ``report.html``.

Both default OFF (gowitness already covers screenshots). EyeWitness adds page
categorization; aquatone clusters pages by visual similarity.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

from recontool.adapters.base import Adapter, AdapterContext, Event
from recontool.adapters.registry import register
from recontool.config import settings

from recontool.adapters.base import log_tool_io

# Cap per scan so a huge live-host set can't fan out into thousands of headless
# browser launches; mirrors the gowitness cap.
_MAX_TARGETS = 50
# Headless browsers are slow; give the whole batch a generous wall-clock budget.
_TIMEOUT_S = 600
# Image extensions the file-output tools may emit.
_IMG_EXTS = (".png", ".jpg", ".jpeg")


def _scoped_targets(ctx: AdapterContext) -> list[str]:
    """In-scope, de-duplicated live hosts, capped at _MAX_TARGETS."""
    return [
        u
        for u in sorted(set(ctx.seeds_of("live_host")))
        if ctx.scope.contains("live_host", u)
    ][:_MAX_TARGETS]


def _images(root: Path) -> set[Path]:
    """All screenshot images currently under ``root`` (recursive)."""
    if not root.exists():
        return set()
    return {p for p in root.rglob("*") if p.suffix.lower() in _IMG_EXTS and p.is_file()}


def _events(name: str, new_shots: set[Path]) -> list[Event]:
    return [
        Event.asset(name, "screenshot", str(img.relative_to(settings.artifact_dir)))
        for img in sorted(new_shots)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# aquatone — STDIN-fed, writes screenshots/ under -out <dir>
# https://github.com/michenriksen/aquatone
# ─────────────────────────────────────────────────────────────────────────────
@register("p5_deep")
class Aquatone(Adapter):
    name = "aquatone"
    category = "CAT-5"
    is_active = True
    default_on = False
    consumes = ("live_host",)
    produces = ("screenshot",)

    def available(self, ctx: AdapterContext) -> bool:
        return shutil.which("aquatone") is not None

    async def run(self, ctx: AdapterContext) -> list[Event]:
        targets = _scoped_targets(ctx)
        if not targets:
            return []

        shotdir = ctx.artifacts.root / "aquatone"
        shotdir.mkdir(parents=True, exist_ok=True)
        before = _images(shotdir)

        # aquatone reads its target list from STDIN; -out points at our subdir.
        # README: `cat targets.txt | aquatone -out <dir>`.
        argv = ["aquatone", "-out", str(shotdir)]
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            payload = ("\n".join(targets) + "\n").encode()
            await asyncio.wait_for(proc.communicate(input=payload), timeout=_TIMEOUT_S)
        except (asyncio.TimeoutError, Exception):
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass

        new_shots = _images(shotdir) - before
        log_tool_io(
            "aquatone",
            f"{len(targets)} hosts",
            argv,
            note=f"wrote {len(new_shots)} screenshots",
        )
        return _events(self.name, new_shots)


# ─────────────────────────────────────────────────────────────────────────────
# EyeWitness — file-fed (-f), writes screens/ under -d <outdir>
# https://github.com/RedSiege/EyeWitness
# ─────────────────────────────────────────────────────────────────────────────
@register("p5_deep")
class EyeWitness(Adapter):
    name = "eyewitness"
    category = "CAT-5"
    is_active = True
    default_on = False
    consumes = ("live_host",)
    produces = ("screenshot",)

    def available(self, ctx: AdapterContext) -> bool:
        return shutil.which("eyewitness") is not None

    async def run(self, ctx: AdapterContext) -> list[Event]:
        targets = _scoped_targets(ctx)
        if not targets:
            return []

        shotdir = ctx.artifacts.root / "eyewitness"
        shotdir.mkdir(parents=True, exist_ok=True)
        before = _images(shotdir)

        # EyeWitness takes a file of URLs (-f) and an output dir (-d).
        # README: `eyewitness --web -f urls.txt -d <outdir> --no-prompt`.
        fd, list_path = tempfile.mkstemp(prefix="eyewitness_", suffix=".txt")
        proc = None
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write("\n".join(targets) + "\n")

            argv = [
                "eyewitness",
                "--web",
                "-f",
                list_path,
                "-d",
                str(shotdir),
                "--no-prompt",
            ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT_S)
            except (asyncio.TimeoutError, Exception):
                if proc is not None and proc.returncode is None:
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
        finally:
            try:
                os.unlink(list_path)
            except OSError:
                pass

        new_shots = _images(shotdir) - before
        log_tool_io(
            "eyewitness",
            f"{len(targets)} hosts",
            argv,
            note=f"wrote {len(new_shots)} screenshots",
        )
        return _events(self.name, new_shots)
