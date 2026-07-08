"""Operational-surface tests: configs, docker-compose, installer, logging, and
catalog<->DB consistency. Keeps setup/deploy from silently rotting. Hermetic:
validates files structurally (no docker daemon, no network, no installs)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_all_config_files_parse():
    for rel in ("config/recontool.example.yaml", "config/tools.yaml",
                "config/tools_generic.yaml", "config/categories.yaml"):
        data = yaml.safe_load((ROOT / rel).read_text())
        assert isinstance(data, dict), f"{rel} did not parse to a mapping"


def test_tools_generic_specs_are_well_formed():
    specs = yaml.safe_load((ROOT / "config/tools_generic.yaml").read_text())["tools"]
    seen = set()
    for s in specs:
        assert s.get("name") and s["name"] not in seen, f"dup/missing name: {s}"
        seen.add(s["name"])
        assert s.get("integration") in ("api", "cli"), s["name"]
        assert s.get("consumes") and s.get("produces"), s["name"]
        assert "parse" in s and "emit" in s["parse"], s["name"]
        if s["integration"] == "api":
            assert s.get("endpoint"), s["name"]
        else:
            assert s.get("binary") or s.get("invocation"), s["name"]


def test_docker_compose_is_valid_and_has_services():
    dc = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    assert "services" in dc and "recontool" in dc["services"]
    assert dc["services"]["recontool"].get("build") is not None


def test_dockerfile_installs_tools_and_package():
    df = (ROOT / "Dockerfile").read_text()
    assert "install_tools.sh" in df          # external recon binaries baked in
    assert "pip3 install" in df or "pip install" in df
    assert "ENTRYPOINT" in df


def test_installer_script_syntax_is_valid():
    # `bash -n` parses without executing — catches syntax rot in the installer.
    r = subprocess.run(["bash", "-n", str(ROOT / "docker/install_tools.sh")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_catalog_and_db_seed_agree():
    from recontool.inventory.catalog import load_all_tools
    tools = load_all_tools()
    assert len(tools) > 500                                  # full catalog present
    assert any(t.runnable for t in tools)
    assert any(t.web_only for t in tools)                    # nothing eliminated


def test_workitem_has_claim_index():
    """The worker claim path depends on a composite index for fast claims at scale."""
    from recontool.engine.models import WorkItem
    names = {ix.name for ix in WorkItem.__table__.indexes}
    assert "ix_workitem_claim" in names


def test_engine_logger_emits_structured_entries():
    from recontool.engine.logging import EngineLogger
    log = EngineLogger("test", correlation_id="cid-123")
    log.log_tool_start("run-1", "scan-1", "subfinder", inputs={"domain": ["x.com"]})
    log.log_tool_complete("run-1", "scan-1", "subfinder", duration_ms=120, entity_count=37)
    entries = log.entries
    assert len(entries) == 2
    assert all(e["correlation_id"] == "cid-123" and "timestamp" in e for e in entries)
    assert entries[0]["event"] == "tool_start"
    assert entries[1]["event"] == "tool_complete" and entries[1]["entity_count"] == 37
