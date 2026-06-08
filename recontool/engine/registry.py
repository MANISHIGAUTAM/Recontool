"""Enhanced tool registry with Pydantic-validated ToolSpec models.

Loads tools from config/tools.yaml (detailed registry) and config/tools_generic.yaml
(generic adapter specs) into a unified, queryable registry.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from recontool.config import CONFIG_DIR


# ---------------------------------------------------------------------------
# ToolSpec schema
# ---------------------------------------------------------------------------


class RetryPolicy(BaseModel):
    """Retry configuration for a tool."""

    max_retries: int = 0
    backoff_factor: float = 1.0
    retryable_errors: list[str] = Field(default_factory=list)


class ToolSpec(BaseModel):
    """Full specification for a tool in the registry."""

    name: str
    category: int = 0
    purpose: str = ""
    version: str = ""
    phase: str = ""
    type: str = "passive"
    install_method: str = ""
    runtime_dependencies: list[str] = Field(default_factory=list)
    invocation_strategy: str = ""
    integration: str = ""
    binary: str = ""
    invocation: str = ""
    supported_input_types: list[str] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    optional_inputs: list[str] = Field(default_factory=list)
    output_types: list[str] = Field(default_factory=list)
    output_file_paths: list[str] = Field(default_factory=list)
    stdout_semantics: str = ""
    json_schema: Optional[dict[str, Any]] = None
    output_format: str = ""
    concurrency_safety: bool = True
    idempotency: bool = True
    timeout: int = 300
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    rate_limit_constraints: dict[str, Any] = Field(default_factory=dict)
    parallel_safe: bool = True
    incremental_safe: bool = False
    produces_entities: list[str] = Field(default_factory=list)
    unlocks_pending_keys: list[str] = Field(default_factory=list)
    triggers_downstream: list[Any] = Field(default_factory=list)
    validation_status: str = ""
    test_coverage_status: str = ""
    documentation_status: str = ""
    requires_key: Any = None
    default_on: bool = True
    chains_to: list[Any] = Field(default_factory=list)
    notes: str = ""
    # Generic spec fields
    consumes: list[str] = Field(default_factory=list)
    produces: list[str] = Field(default_factory=list)
    endpoint: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    bucket: str = ""
    max_inputs: Optional[int] = None
    is_active: bool = False
    parse: Optional[dict[str, Any]] = None
    enabled: bool = True
    key_optional: bool = False

    # Computed convenience properties
    @property
    def input_type(self) -> str:
        """Primary input type (from 'input' field or first consumes entry)."""
        if self.supported_input_types:
            return self.supported_input_types[0]
        if self.consumes:
            return self.consumes[0]
        return ""

    @property
    def output_type(self) -> str:
        """Primary output type (from 'output' field or first produces/output_types)."""
        if self.output_types:
            return self.output_types[0]
        if self.produces:
            return self.produces[0]
        return ""


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Unified registry loading tools from config/tools.yaml and config/tools_generic.yaml.

    Provides lookup by name, category, phase, input_type, and output_type.
    """

    def __init__(self, tools: dict[str, ToolSpec] | None = None) -> None:
        self._tools: dict[str, ToolSpec] = tools or {}

    @classmethod
    def load(cls, config_dir: Path | None = None) -> "ToolRegistry":
        """Load tools from both YAML files and return a populated registry."""
        config_dir = config_dir or CONFIG_DIR
        tools: dict[str, ToolSpec] = {}

        # Load tools.yaml (dict-based)
        tools_yaml = config_dir / "tools.yaml"
        if tools_yaml.exists():
            try:
                import yaml

                data = yaml.safe_load(tools_yaml.read_text()) or {}
                raw_tools = data.get("tools", {})
                for name, spec in raw_tools.items():
                    if not isinstance(spec, dict):
                        continue
                    spec_data = cls._normalize_tools_yaml(name, spec)
                    tools[name] = ToolSpec(**spec_data)
            except Exception:  # noqa: BLE001
                pass

        # Load tools_generic.yaml (list-based)
        generic_yaml = config_dir / "tools_generic.yaml"
        if generic_yaml.exists():
            try:
                import yaml

                data = yaml.safe_load(generic_yaml.read_text()) or {}
                raw_list = data.get("tools", [])
                if isinstance(raw_list, list):
                    for spec in raw_list:
                        if not isinstance(spec, dict):
                            continue
                        name = spec.get("name", "")
                        if not name:
                            continue
                        # Do not override tools.yaml entries
                        if name in tools:
                            continue
                        spec_data = cls._normalize_generic_yaml(spec)
                        tools[name] = ToolSpec(**spec_data)
            except Exception:  # noqa: BLE001
                pass

        return cls(tools)

    @staticmethod
    def _normalize_tools_yaml(name: str, raw: dict[str, Any]) -> dict[str, Any]:
        """Map tools.yaml fields to ToolSpec fields."""
        result: dict[str, Any] = {"name": name}
        # Direct mappings
        for key in (
            "category", "phase", "type", "integration", "binary",
            "invocation", "output_format", "requires_key", "default_on",
            "chains_to", "notes",
        ):
            if key in raw:
                result[key] = raw[key]

        # install -> install_method
        install = raw.get("install")
        if isinstance(install, dict):
            result["install_method"] = install.get("method", "")
        elif isinstance(install, str):
            result["install_method"] = install

        # input/output -> supported_input_types / output_types
        inp = raw.get("input")
        if isinstance(inp, str):
            result["supported_input_types"] = [inp]
        elif isinstance(inp, list):
            result["supported_input_types"] = inp

        out = raw.get("output")
        if isinstance(out, str):
            result["output_types"] = [out]
        elif isinstance(out, list):
            result["output_types"] = out

        return result

    @staticmethod
    def _normalize_generic_yaml(raw: dict[str, Any]) -> dict[str, Any]:
        """Map tools_generic.yaml fields to ToolSpec fields."""
        result: dict[str, Any] = {}
        for key in (
            "name", "phase", "category", "integration", "is_active",
            "consumes", "produces", "requires_key", "key_optional",
            "endpoint", "headers", "bucket", "max_inputs", "timeout",
            "binary", "invocation", "parse", "enabled",
        ):
            if key in raw:
                result[key] = raw[key]

        # map consumes -> supported_input_types, produces -> output_types
        if "consumes" in raw:
            result["supported_input_types"] = raw["consumes"]
        if "produces" in raw:
            result["output_types"] = raw["produces"]

        return result

    # --- Query methods --------------------------------------------------------

    def get(self, name: str) -> ToolSpec | None:
        """Get a tool spec by name."""
        return self._tools.get(name)

    def all_tools(self) -> dict[str, ToolSpec]:
        """Return all registered tool specs."""
        return dict(self._tools)

    def by_category(self, category: int) -> list[ToolSpec]:
        """Return all tools in a given category."""
        return [t for t in self._tools.values() if t.category == category]

    def by_phase(self, phase: str) -> list[ToolSpec]:
        """Return all tools in a given phase."""
        return [t for t in self._tools.values() if t.phase == phase]

    def by_input_type(self, input_type: str) -> list[ToolSpec]:
        """Return tools that accept a given input type."""
        return [
            t for t in self._tools.values()
            if input_type in t.supported_input_types or input_type in t.consumes
        ]

    def by_output_type(self, output_type: str) -> list[ToolSpec]:
        """Return tools that produce a given output type."""
        return [
            t for t in self._tools.values()
            if output_type in t.output_types or output_type in t.produces
        ]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
