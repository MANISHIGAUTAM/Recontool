"""Batch-12 F0: per-family contract directory (config/tools_generic.d/*.yaml).

Two guarantees:
  1. A contract file dropped in the directory is loaded + routable by the registry.
  2. Directory contracts ship OFF by default — even if the file says default_on: true —
     so wiring a whole tool family can never grow the default profile ("not unnecessarily
     triggered"). Enforced structurally in registry.load() AND asserted here over the real dir.
"""
from __future__ import annotations

import pathlib

import yaml

from recontool.config import REPO_ROOT
from recontool.engine.registry import ToolRegistry
from recontool.engine.runner import load_engine_registry

_FAM = """tools:
  - name: testfam_tool
    integration: cli
    is_active: false
    consumes: [subdomain]
    produces: [url]
    default_on: true
    binary: testfam_tool
    invocation: "testfam_tool {value}"
    parse:
      format: text
      emit:
        - {entity: endpoint, url: "{_value}"}
"""


def test_dir_family_file_is_loaded_and_forced_off(tmp_path):
    d = tmp_path / "tools_generic.d"
    d.mkdir()
    (d / "fam.yaml").write_text(_FAM)

    reg = ToolRegistry.load(config_dir=tmp_path, include_inventory=False)
    spec = reg.get("testfam_tool")
    assert spec is not None, "a config/tools_generic.d/*.yaml family file must be loaded"
    # routable on its narrow consume type
    assert "subdomain" in (set(spec.supported_input_types) | set(spec.consumes))
    # forced OFF by default even though the contract declared default_on: true
    assert getattr(spec, "default_on", False) is False, (
        "directory contracts must ship default_on:false (not unnecessarily triggered)"
    )


def test_no_real_family_tool_is_default_on():
    """Every tool in the real config/tools_generic.d/*.yaml must be off by default."""
    gdir = REPO_ROOT / "config" / "tools_generic.d"
    names: set[str] = set()
    if gdir.is_dir():
        for f in gdir.glob("*.yaml"):
            data = yaml.safe_load(f.read_text()) or {}
            for s in data.get("tools") or []:
                if isinstance(s, dict) and s.get("name"):
                    names.add(s["name"])
    if not names:
        return  # no family files yet — nothing to enforce
    reg = load_engine_registry(tools="all", authorize_active=True)
    offenders = [n for n in names if getattr(reg.get(n), "default_on", False)]
    assert not offenders, f"family-dir tools must be default_on:false, got: {offenders}"
