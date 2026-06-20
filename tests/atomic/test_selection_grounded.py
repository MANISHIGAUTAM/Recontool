"""`--tools all` must enable only GROUNDED tools (real contracts), never the
synthesized/guessed inventory tools. This is the overscanning fix: under the old
`all == excessive`, the engine ran inferred `<binary> {value}` invocations like
`binwalk <domain>` / `arjun <domain>` / `strings <domain>` — file/repo analyzers
fed a domain string, burning scan time for zero output. Guessed runs are now
`excessive`-only.
"""
from __future__ import annotations

from recontool.engine.runner import load_engine_registry
from recontool.engine.execution import plan_execution
from recontool.engine.selection import apply_selection, is_excessive, is_all


def _enabled(mode: str) -> set[str]:
    reg = load_engine_registry("default", authorize_active=True)
    apply_selection(reg, mode, authorize_active=True)
    return {n for n, s in reg.all_tools().items() if getattr(s, "enabled", False)}


def test_all_excludes_synthesized_keeps_contracts():
    reg = load_engine_registry("default", authorize_active=True)
    apply_selection(reg, "all", authorize_active=True)
    for name, spec in reg.all_tools().items():
        if not getattr(spec, "enabled", False):
            continue
        # nothing enabled under `all` may be a synthesized (guessed) plan
        assert not plan_execution(spec).synthesized, f"{name} is synthesized but enabled under 'all'"


def test_excessive_is_a_superset_of_all():
    allg, exc = _enabled("all"), _enabled("excessive")
    assert allg <= exc
    # excessive adds the synthesized tools that `all` drops
    assert exc - allg, "excessive must enable strictly more (the synthesized tools)"


def test_known_file_analyzers_are_grounded_out_of_all():
    """The concrete overscanning offenders must not run under `all`."""
    allg, exc = _enabled("all"), _enabled("excessive")
    for offender in ("Binwalk", "ExifTool", "strings", "Arjun", "Trufflehog3"):
        # only assert for tools actually present in the catalog
        if offender in exc:
            assert offender not in allg, f"{offender} (synthesized) must be excluded from 'all'"


def test_mode_helpers():
    assert is_excessive("excessive") and not is_excessive("all")
    assert is_all("all") and is_all("excessive") and not is_all("default")
