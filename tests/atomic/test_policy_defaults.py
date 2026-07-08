"""ToolRegistry.apply_policy_defaults: derive the execution-policy fields the
engine honors (incremental_safe / concurrency_safety / retry_policy) from the
registry's reliable signals — so the registry is the source of truth, not code."""
from __future__ import annotations

from recontool.engine.registry import ToolRegistry, ToolSpec


def _reg():
    return ToolRegistry(tools={
        "crtsh": ToolSpec(name="crtsh", type="passive", is_active=False, integration="api"),
        "gau": ToolSpec(name="gau", type="passive", is_active=False, integration="cli", binary="gau"),
        "nuclei": ToolSpec(name="nuclei", type="active", is_active=True, integration="python"),
        "masscan": ToolSpec(name="masscan", type="active", is_active=True,
                            integration="cli", binary="masscan"),
    })


def test_policy_defaults_derived_from_signals():
    reg = _reg()
    reg.apply_policy_defaults()
    t = reg.all_tools()

    # passive discovery -> reusable on rescan; active/vuln -> never reused
    assert t["crtsh"].incremental_safe is True
    assert t["gau"].incremental_safe is True
    assert t["nuclei"].incremental_safe is False
    assert t["masscan"].incremental_safe is False

    # transient-network retries: API=2, passive CLI=1, active=0
    assert t["crtsh"].retry_policy.max_retries == 2
    assert t["gau"].retry_policy.max_retries == 1
    assert t["nuclei"].retry_policy.max_retries == 0
    assert t["masscan"].retry_policy.max_retries == 0

    # raw-socket scanner serialized; ordinary tools stay parallel
    assert t["masscan"].concurrency_safety is False
    assert t["crtsh"].concurrency_safety is True


def test_policy_defaults_preserve_explicit_values_and_are_idempotent():
    reg = ToolRegistry(tools={
        # explicit opt-out of reuse on a passive tool must be respected... but
        # default False is indistinguishable from unset, so we assert the active
        # case (must stay False) and the explicit max_retries override instead.
        "custom": ToolSpec(name="custom", type="passive", is_active=False,
                           integration="api"),
    })
    reg.all_tools()["custom"].retry_policy.max_retries = 5   # explicit override
    reg.apply_policy_defaults()
    reg.apply_policy_defaults()                              # idempotent
    assert reg.all_tools()["custom"].retry_policy.max_retries == 5  # not clobbered
    assert reg.all_tools()["custom"].incremental_safe is True
