"""Input/output fingerprinting for incremental scans.

Uses SHA-256 hashing of sorted, deterministic representations to detect
whether inputs, outputs, or configs have changed between runs.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from recontool.engine.registry import ToolSpec


def _canonical(obj: Any) -> str:
    """Produce a canonical string representation for hashing."""
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))


def fingerprint_inputs(tool_name: str, inputs: dict[str, Any]) -> str:
    """Compute a SHA-256 fingerprint of a tool's inputs."""
    payload = _canonical({"tool": tool_name, "inputs": inputs})
    return hashlib.sha256(payload.encode()).hexdigest()


def fingerprint_output(tool_name: str, output: Any) -> str:
    """Compute a SHA-256 fingerprint of a tool's output."""
    payload = _canonical({"tool": tool_name, "output": output})
    return hashlib.sha256(payload.encode()).hexdigest()


def fingerprint_config(tool_spec: ToolSpec) -> str:
    """Compute a SHA-256 fingerprint of a tool's configuration.

    Captures fields that affect execution behavior: version, invocation,
    timeout, retry_policy, and rate_limit_constraints.
    """
    config_data = {
        "name": tool_spec.name,
        "version": tool_spec.version,
        "invocation": tool_spec.invocation,
        "timeout": tool_spec.timeout,
        "retry_max": tool_spec.retry_policy.max_retries,
        "retry_backoff": tool_spec.retry_policy.backoff_factor,
        "rate_limit": tool_spec.rate_limit_constraints,
    }
    payload = _canonical(config_data)
    return hashlib.sha256(payload.encode()).hexdigest()


def has_changed(old_fp: str, new_fp: str) -> bool:
    """Return True if fingerprints differ (i.e., something changed)."""
    return old_fp != new_fp
