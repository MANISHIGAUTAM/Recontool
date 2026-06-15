"""Filesystem artifact store.

Large blobs (JS files harvested from Wayback, response bodies, raw tool output,
screenshots) live on disk, not in the DB. The DB stores pointers (relative keys).
Layout mirrors docs/D3-data-schema.md §7.

    <artifact_dir>/<scan_id>/<tool>/<name>
    <artifact_dir>/<scan_id>/js/<host>/<file>.js
    <artifact_dir>/<scan_id>/raw/<tool>/<ts>.json
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from recontool.config import settings

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe(name: str) -> str:
    return _SAFE.sub("_", name)[:200] or "x"


class ArtifactStore:
    def __init__(self, scan_id: str, root: Path | None = None):
        self.scan_id = scan_id
        self.root = (root or settings.artifact_dir) / scan_id
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, *parts: str) -> Path:
        p = self.root.joinpath(*[_safe(x) for x in parts])
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def abspath(self, rel: str) -> str:
        """Absolute filesystem path for a relative artifact key (from save_*),
        so a downstream tool (jsluice/linkfinder) can open the harvested file
        regardless of cwd."""
        return str((settings.artifact_dir / rel).resolve())

    def save_raw(self, tool: str, data: Any) -> str:
        """Persist raw tool output as JSON; return the relative key."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        p = self._path("raw", tool, f"{ts}.json")
        p.write_text(json.dumps(data, default=str, indent=2))
        return str(p.relative_to(settings.artifact_dir))

    def save_js(self, host: str, filename: str, content: bytes | str) -> str:
        """Persist a JS file harvested from the web; return the relative key."""
        p = self._path("js", host, filename if filename.endswith(".js") else filename + ".js")
        mode = "wb" if isinstance(content, bytes) else "w"
        with open(p, mode) as fh:
            fh.write(content)
        return str(p.relative_to(settings.artifact_dir))

    def save_body(self, host: str, name: str, content: bytes | str) -> str:
        p = self._path("bodies", host, name)
        mode = "wb" if isinstance(content, bytes) else "w"
        with open(p, mode) as fh:
            fh.write(content)
        return str(p.relative_to(settings.artifact_dir))

    def save_text(self, tool: str, name: str, text: str) -> str:
        p = self._path(tool, name)
        p.write_text(text)
        return str(p.relative_to(settings.artifact_dir))

    def append_jsonl(self, name: str, records: list[dict]) -> str:
        """Append dict records to out/<name>.jsonl — append-only, so a later
        primary key never overwrites an earlier one. Used for the per-tool,
        per-primary-key execution ledger (out/<tool>.runs.jsonl), which records
        EVERY run — including runs that found nothing — so every tool leaves a
        per-key footprint in the archive even when it produces no entities."""
        p = self._path("out", f"{name}.jsonl")
        with open(p, "a") as fh:
            for r in records:
                fh.write(json.dumps(r, default=str) + "\n")
        return str(p.relative_to(settings.artifact_dir))

    def save_typed(self, tool: str, entity_type: str, values: list[str]) -> str:
        """Append discovered entities to a typed, append-only output file:
        out/<tool>.<entity_type>.jsonl — one JSON object per line. This is the
        per-tool, per-output-type record (a multi-mode tool gets one file per
        type, e.g. ffuf.subdomain.jsonl and ffuf.url.jsonl)."""
        p = self._path("out", f"{tool}.{entity_type}.jsonl")
        with open(p, "a") as fh:
            for v in values:
                fh.write(json.dumps({"value": v, "type": entity_type, "tool": tool}) + "\n")
        return str(p.relative_to(settings.artifact_dir))
