"""Category 28 — learned wordlists & regex packs.

The system continuously improves its own discovery inputs from what it observes:
detected technologies (cat 5), harvested URL paths (cat 4/6/11), and discovered
parameters (cat 23/25) are mined into TUNED wordlists and regex packs that feed
content discovery (cat 20), API/GraphQL (cat 23), and parameter discovery (cat 25).

Pure, deterministic, content-addressed (hash of contents) so the same corpus
always yields the same artifact. No network. Writes under ``<artifact_dir>/
wordlists/`` and ``<artifact_dir>/regex_packs/``.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

# Tech -> high-signal path seeds (merged into the tuned list when tech is detected).
_TECH_PATHS = {
    "wordpress": ["wp-admin", "wp-login.php", "wp-content", "wp-json", "xmlrpc.php"],
    "express": ["api", "api/v1", "api/v2", "graphql", "health", "status"],
    "php": ["index.php", "info.php", "phpinfo.php", "admin.php", "config.php"],
    "nginx": ["nginx_status", "status", ".well-known"],
    "apache": ["server-status", "server-info", ".htaccess"],
    "react": ["static/js", "manifest.json", "asset-manifest.json"],
    "iis": ["web.config", "trace.axd", "elmah.axd"],
}


def _split_path_tokens(url: str) -> list[str]:
    try:
        path = urlsplit(url).path
    except Exception:  # noqa: BLE001
        return []
    return [seg for seg in path.split("/") if seg and not seg.startswith("{")]


@dataclass
class LearnedWordlist:
    words: list[str] = field(default_factory=list)

    @property
    def sha256(self) -> str:
        return hashlib.sha256("\n".join(self.words).encode()).hexdigest()

    def render(self) -> str:
        return "\n".join(self.words) + "\n" if self.words else ""


@dataclass
class RegexPack:
    patterns: dict[str, str] = field(default_factory=dict)

    @property
    def sha256(self) -> str:
        blob = "\n".join(f"{k}={v}" for k, v in sorted(self.patterns.items()))
        return hashlib.sha256(blob.encode()).hexdigest()


def learn_wordlist(
    *,
    tech: list[str] | None = None,
    urls: list[str] | None = None,
    params: list[str] | None = None,
    base: list[str] | None = None,
) -> LearnedWordlist:
    """Build a tuned wordlist from detected tech + harvested URL paths + params."""
    words: set[str] = set(base or [])
    for t in tech or []:
        words.update(_TECH_PATHS.get(t.lower(), []))
    for u in urls or []:
        words.update(_split_path_tokens(u))
    # parameters are valuable as path/word candidates too
    words.update(p for p in (params or []) if p and p.isascii())
    # keep tokens reasonable + deterministic order
    cleaned = sorted({w.strip().lstrip("/").lower() for w in words if 1 <= len(w) <= 64})
    return LearnedWordlist(words=cleaned)


def learn_regex_pack(params: list[str] | None = None) -> RegexPack:
    """Build a regex pack that matches the learned parameters in URLs/bodies."""
    pack: dict[str, str] = {
        # always-on high-signal secret-ish patterns (detection prep, not exploitation)
        "aws_access_key": r"AKIA[0-9A-Z]{16}",
        "google_api_key": r"AIza[0-9A-Za-z\-_]{35}",
        "jwt": r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    }
    seen = set()
    for p in params or []:
        p = p.strip()
        if not p or p in seen or not re.match(r"^[A-Za-z0-9_\-]{1,40}$", p):
            continue
        seen.add(p)
        pack[f"param_{p}"] = rf"[?&]{re.escape(p)}="
    return RegexPack(patterns=pack)


def persist_wordlist(artifact_dir, wl: LearnedWordlist, name: str = "tuned") -> str:
    """Write a content-addressed wordlist; return its relative key."""
    from pathlib import Path
    d = Path(artifact_dir) / "wordlists"
    d.mkdir(parents=True, exist_ok=True)
    fname = f"{name}-{wl.sha256[:12]}.txt"
    (d / fname).write_text(wl.render())
    return f"wordlists/{fname}"


def persist_regex_pack(artifact_dir, pack: RegexPack, name: str = "tuned") -> str:
    from pathlib import Path
    import json
    d = Path(artifact_dir) / "regex_packs"
    d.mkdir(parents=True, exist_ok=True)
    fname = f"{name}-{pack.sha256[:12]}.json"
    (d / fname).write_text(json.dumps(pack.patterns, indent=2, sort_keys=True))
    return f"regex_packs/{fname}"
