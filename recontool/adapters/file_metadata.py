"""Document/image metadata exposure via exiftool (hand-written adapter).

Placement rationale (ADR-011, pure adapter): metadata extraction only makes
sense on *document/image* assets, never on an HTML page. So this adapter runs in
the deep phase, consumes already-discovered endpoint/url assets, filters to a
fixed set of document/image extensions, fetches the bytes, and shells out to
`exiftool -json -a` to surface embedded author/tooling/GPS metadata that leaks
internal usernames, software stacks, or physical locations.

exiftool output shape (grounding — do NOT invent tag names):
  https://exiftool.org/exiftool_pod.html  (-json option)
  https://exiftool.org/
  `exiftool -json FILE` emits a JSON ARRAY of objects, one object per file.
  Each object's keys are tag names, e.g.:
    "SourceFile", "Author", "Creator", "Producer", "Software",
    "Company", "Title", "Creator-Tool", "GPSLatitude", "GPSLongitude",
    "GPSPosition"
  Tag presence/spelling varies by file type, so every lookup below is defensive
  (`.get()` only) and we never assume a tag exists.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from typing import Any
from urllib.parse import urlsplit

from recontool.adapters.base import Adapter, AdapterContext, Event
from recontool.adapters.registry import register

# Extensions worth running exiftool against. Anything else (e.g. .html) is gated
# out before we ever touch the network or a subprocess.
_DOC_IMAGE_EXTS: frozenset[str] = frozenset(
    {
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".odt", ".ods",
        ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".gif", ".svg",
    }
)

# Tag names we treat as "interesting" (leak-worthy). Defensive .get() only.
_INTERESTING_TAGS: tuple[str, ...] = (
    "Author", "Creator", "Producer", "Software", "Company",
    "Creator-Tool", "CreatorTool", "Title", "LastModifiedBy",
    "Application", "Manufacturer", "Model",
)
_GPS_TAGS: tuple[str, ...] = (
    "GPSPosition", "GPSLatitude", "GPSLongitude", "GPSLatitudeRef",
    "GPSLongitudeRef", "GPSAltitude",
)

_MAX_CANDIDATES = 30          # cap fan-out
_FETCH_TIMEOUT = 30          # per-file exiftool subprocess timeout (seconds)


def _has_doc_image_ext(url: str) -> bool:
    """True iff the URL's path ends in a document/image extension we handle.

    Pure helper (no I/O) so the extension gate is independently testable.
    """
    try:
        path = urlsplit(url).path
    except (ValueError, AttributeError):
        return False
    _, ext = os.path.splitext(path)
    return ext.lower() in _DOC_IMAGE_EXTS


@register("p5_deep")
class FileMetadata(Adapter):
    name = "exiftool"
    category = "CAT-metadata"
    is_active = True
    # Opt-in: fetching + shelling out per document is heavier than passive work.
    default_on = False
    consumes = ("endpoint", "url")
    produces = ("finding",)

    def available(self, ctx: AdapterContext) -> bool:  # noqa: ARG002
        import shutil

        return shutil.which("exiftool") is not None

    # -- candidate selection --------------------------------------------------
    def _candidate_urls(self, ctx: AdapterContext) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for atype in self.consumes:
            for u in ctx.seeds_of(atype):
                if not u or u in seen:
                    continue
                seen.add(u)
                if not _has_doc_image_ext(u):
                    continue
                if not ctx.scope.contains("url", u):
                    continue
                out.append(u)
                if len(out) >= _MAX_CANDIDATES:
                    return out
        return out

    # -- pure JSON -> Events mapping (unit-testable, NO subprocess) -----------
    def _events_from_exiftool(self, raw_json: str, source_url: str) -> list[Event]:
        """Map one `exiftool -json` output string to metadata_exposure findings.

        `exiftool -json` returns a JSON array of per-file objects. We surface a
        finding only when an object carries at least one interesting (or GPS)
        tag, attaching the extracted values to the finding attrs.
        """
        try:
            parsed: Any = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError):
            return []
        if isinstance(parsed, dict):  # tolerate a bare object too
            parsed = [parsed]
        if not isinstance(parsed, list):
            return []

        events: list[Event] = []
        for obj in parsed:
            if not isinstance(obj, dict):
                continue

            meta: dict[str, str] = {}
            for tag in _INTERESTING_TAGS:
                val = obj.get(tag)
                if val not in (None, ""):
                    meta[tag] = str(val)

            gps: dict[str, str] = {}
            for tag in _GPS_TAGS:
                val = obj.get(tag)
                if val not in (None, ""):
                    gps[tag] = str(val)

            if not meta and not gps:
                continue  # nothing leak-worthy in this file

            file_type = obj.get("FileType") or obj.get("MIMEType")
            attrs: dict[str, Any] = {
                "severity": "low",
                "detector": self.name,
                "asset_value": source_url,
                "source_url": source_url,
                "metadata": meta,
            }
            if file_type:
                attrs["file_type"] = str(file_type)
            if gps:
                attrs["gps"] = gps
                attrs["has_gps"] = True

            leaked = ", ".join(f"{k}={v}" for k, v in list(meta.items())[:4]) or "GPS"
            title = f"Document metadata exposure ({leaked}) in {source_url}"
            events.append(
                Event.finding(self.name, "metadata_exposure", title, **attrs)
            )
        return events

    # -- run: fetch each candidate, exiftool it, emit findings ----------------
    async def run(self, ctx: AdapterContext) -> list[Event]:
        candidates = self._candidate_urls(ctx)
        if not candidates:
            return []

        events: list[Event] = []
        for url in candidates:
            try:
                resp = await ctx.http.get(url, bucket=self.name)
            except Exception:  # noqa: BLE001 — never let one bad fetch kill the batch
                continue
            body = getattr(resp, "content", None)
            if not body:
                continue

            raw = await self._run_exiftool(body)
            # Audit trail: persist the raw exiftool output keyed by tool+url.
            try:
                ctx.artifacts.save_text(self.name, f"{urlsplit(url).path}.json", raw or "")
            except Exception:  # noqa: BLE001 — logging must never break the scan
                pass
            if not raw:
                continue
            events.extend(self._events_from_exiftool(raw, url))
        return events

    async def _run_exiftool(self, body: bytes) -> str:
        """Write bytes to a temp file and run `exiftool -json -a`. Returns stdout
        text (empty string on any failure/timeout)."""
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as fh:
                fh.write(body)
                tmp_path = fh.name
            proc = await asyncio.create_subprocess_exec(
                "exiftool", "-json", "-a", tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=_FETCH_TIMEOUT)
            return out.decode(errors="ignore")
        except Exception:  # noqa: BLE001 — timeout / missing binary / bad file
            return ""
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
