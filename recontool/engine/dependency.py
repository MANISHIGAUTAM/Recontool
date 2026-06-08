"""Installation and dependency detection for tools.

DependencyChecker inspects the environment to determine whether a tool is
ready to execute: binary present, version compatible, env vars set, file
permissions correct, API keys available.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field

from recontool.engine.registry import ToolSpec


@dataclass
class ReadinessResult:
    """Result of a dependency check for a tool."""

    ready: bool
    blocked_reason: str | None = None
    missing_deps: list[str] = field(default_factory=list)


class DependencyChecker:
    """Check whether a tool's runtime dependencies are satisfied."""

    def check_tool_ready(self, tool_spec: ToolSpec) -> ReadinessResult:
        """Run all checks for a tool and return a composite ReadinessResult.

        Handles three classes of tool without ever raising:
          * non-executable (web/gui/dataset-only, reference indexes, presets) ->
            blocked with the recorded reason; nothing to install.
          * inventory-derived stubs (api/cli mode but no full contract yet) ->
            blocked with a "promote to full adapter" reason, plus any missing
            binary/key surfaced so operators know what to provision.
          * fully-contracted tools -> the usual binary/dependency/key checks.
        """
        # Non-executable tools can never run; report the documented reason.
        if tool_spec.non_executable:
            reason = tool_spec.non_executable_reason or "non_executable: no programmatic interface"
            return ReadinessResult(ready=False, blocked_reason=reason, missing_deps=[])

        missing: list[str] = []
        reasons: list[str] = []

        # Check binary availability
        if tool_spec.binary and not self.check_binary_available(tool_spec.binary):
            missing.append(tool_spec.binary)
            reasons.append(f"binary not found: {tool_spec.binary}")

        # Check runtime dependencies
        for dep in tool_spec.runtime_dependencies:
            if not self.check_binary_available(dep):
                missing.append(dep)
                reasons.append(f"dependency not found: {dep}")

        # Check API key requirement
        if tool_spec.requires_key:
            key_env = tool_spec.requires_key if isinstance(tool_spec.requires_key, str) else ""
            if key_env and not self.check_api_key_available(key_env):
                missing.append(key_env)
                reasons.append(f"API key not set: {key_env}")

        # Inventory-derived stubs have no concrete invocation/endpoint contract.
        # They are selectable by the scheduler but cannot execute until promoted
        # to a full adapter spec (config/tools_generic.yaml) — report that clearly
        # rather than silently "succeeding".
        if tool_spec.is_inventory_derived and not self._has_execution_contract(tool_spec):
            contract = "API endpoint" if tool_spec.integration == "api" else "invocation"
            reasons.append(
                f"inventory_stub: no {contract} contract for "
                f"'{tool_spec.slug or tool_spec.name}'; "
                "promote to a generic adapter spec to execute"
            )
            return ReadinessResult(
                ready=False,
                blocked_reason="; ".join(reasons),
                missing_deps=missing,
            )

        if missing:
            return ReadinessResult(
                ready=False,
                blocked_reason="; ".join(reasons),
                missing_deps=missing,
            )
        return ReadinessResult(ready=True)

    @staticmethod
    def _has_execution_contract(tool_spec: ToolSpec) -> bool:
        """True if the tool has enough to route through a generic adapter.

        CLI tools can be driven by their binary + a (curated or synthesised)
        invocation template, so a known binary is sufficient. API tools need a
        concrete endpoint, which bare inventory stubs do not carry.
        """
        if tool_spec.integration == "api":
            return bool(tool_spec.endpoint)
        if tool_spec.integration == "cli":
            return bool(tool_spec.binary or tool_spec.invocation)
        return False

    def check_binary_available(self, name: str) -> bool:
        """Check if a binary is available on PATH."""
        return shutil.which(name) is not None

    def check_version_compatible(self, binary: str, required_version: str) -> bool:
        """Check if a binary version meets the requirement.

        Attempts to run `binary --version` and check if required_version
        appears in the output. Returns True if the binary is not found
        (version check is best-effort).
        """
        if not self.check_binary_available(binary):
            return False
        try:
            result = subprocess.run(
                [binary, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = result.stdout + result.stderr
            return required_version in output
        except (subprocess.TimeoutExpired, OSError):
            return False

    def check_env_vars(self, required_vars: list[str]) -> list[str]:
        """Return list of missing environment variables."""
        return [var for var in required_vars if not os.environ.get(var)]

    def check_file_permissions(self, paths: list[str]) -> list[str]:
        """Return list of paths that are not readable."""
        return [p for p in paths if not os.access(p, os.R_OK)]

    def check_api_key_available(self, key_env: str) -> bool:
        """Check if an API key environment variable is set and non-empty."""
        return bool(os.environ.get(key_env))
