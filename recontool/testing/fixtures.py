"""Recorded provider fixtures — loader + lookup.

Provider mock fixtures live under ``tests/fixtures/providers/`` (referenced by the
``mock_fixture`` field of each provider in ``config/providers.yaml``). They are
deterministic recorded responses used by:
  * demo/test mode (so adapters never call a real provider),
  * the ``recontool replay-fixtures`` command,
  * regression tests.

A fixture is either JSON (``.json``) or text (``.txt``/other).
"""
from __future__ import annotations

import json
from pathlib import Path

# tests/fixtures/providers relative to repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures"


def fixture_path(rel: str) -> Path:
    return FIXTURE_ROOT / rel


def load_fixture(rel: str):
    """Load a fixture by its relative path (e.g. 'providers/crtsh.json').

    Returns parsed JSON for .json files, else the raw text. Raises FileNotFoundError
    if missing, ValueError if a .json file is malformed."""
    p = fixture_path(rel)
    if not p.exists():
        raise FileNotFoundError(f"fixture not found: {rel} (looked in {p})")
    text = p.read_text()
    if p.suffix == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed JSON fixture {rel}: {exc}") from exc
    return text


def list_fixtures() -> list[str]:
    """All fixture files on disk, as relative paths under tests/fixtures/."""
    if not FIXTURE_ROOT.exists():
        return []
    return sorted(str(p.relative_to(FIXTURE_ROOT)) for p in FIXTURE_ROOT.rglob("*")
                  if p.is_file())
