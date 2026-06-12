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
    stdin: bool = False  # CLI: pipe the input value to the tool's stdin
    # Canonical-inventory ingestion fields (data/tool_inventory.json)
    slug: str = ""
    source: str = "curated"           # "curated" | "inventory"
    classification: str = ""          # passive | active | hybrid
    confidence_score: float = 0.0
    reliability: str = ""
    scale: str = ""
    cost_tier: str = ""
    data_quality: str = ""
    web_only: bool = False
    sections: list[str] = Field(default_factory=list)
    categories_all: list[int] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    provenance: str = ""
    non_executable: bool = False
    non_executable_reason: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

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

    @property
    def is_executable(self) -> bool:
        """True if the engine has a programmatic execution path for this tool.

        Non-executable tools (web/gui/dataset-only, reference indexes, presets)
        are registered for visibility but the orchestrator skips them.
        """
        return not self.non_executable

    @property
    def is_inventory_derived(self) -> bool:
        """True if this spec came from data/tool_inventory.json (no full contract)."""
        return self.source == "inventory"


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Unified registry loading tools from config/tools.yaml and config/tools_generic.yaml.

    Provides lookup by name, category, phase, input_type, and output_type.
    """

    def __init__(self, tools: dict[str, ToolSpec] | None = None) -> None:
        self._tools: dict[str, ToolSpec] = tools or {}
        # canonical slug -> registered tool name (for dedup / override precedence)
        self._by_slug: dict[str, str] = {}
        # the full set of canonical slugs seen in data/tool_inventory.json
        self._inventory_slugs: set[str] = set()
        # input-type -> [tool names] index (keeps scheduler eligibility O(matches))
        self._input_index: dict[str, list[str]] = {}
        self._reindex()

    def _reindex(self) -> None:
        """(Re)build the slug and input-type indexes from ``self._tools``."""
        self._by_slug = {}
        self._input_index = {}
        for name, spec in self._tools.items():
            if spec.slug:
                self._by_slug.setdefault(spec.slug, name)
            for itype in set(spec.supported_input_types) | set(spec.consumes):
                self._input_index.setdefault(itype, []).append(name)

    @classmethod
    def load(cls, config_dir: Path | None = None, *, include_inventory: bool = True) -> "ToolRegistry":
        """Load the unified registry.

        Layering (highest precedence last so curated contracts win):
          1. ``data/tool_inventory.json`` — all 532 canonical tools (base layer).
          2. ``config/tools.yaml`` — hand-curated detailed contracts (authoritative).
          3. ``config/tools_generic.yaml`` — declarative generic adapter specs.

        Tools are deduplicated by canonical slug; a curated entry OVERRIDES the
        inventory-derived stub with the same slug (its richer invocation/IO
        contract is preserved, while still inheriting any inventory-only quality
        metadata such as confidence_score/reliability).
        """
        from recontool.engine.inventory import (
            load_inventory_specs,
            slugify,
        )

        config_dir = config_dir or CONFIG_DIR
        tools: dict[str, ToolSpec] = {}
        by_slug: dict[str, str] = {}        # slug -> registered name
        inventory_slugs: set[str] = set()
        # slug -> inventory dict, kept so curated tools can inherit quality metadata
        inventory_by_slug: dict[str, dict[str, Any]] = {}

        # --- Layer 1: inventory base ----------------------------------------
        if include_inventory:
            inventory_by_slug = load_inventory_specs()
            inventory_slugs = set(inventory_by_slug)

        def _register(name: str, spec_data: dict[str, Any], slug: str) -> None:
            """Add a curated tool, enriching it with inventory metadata if present."""
            inv = inventory_by_slug.get(slug)
            if inv:
                spec_data = cls._merge_inventory_metadata(spec_data, inv)
            spec_data.setdefault("slug", slug)
            spec_data.setdefault("source", "curated")
            tools[name] = ToolSpec(**spec_data)
            by_slug.setdefault(slug, name)

        # --- Layer 2: tools.yaml (curated, authoritative) -------------------
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
                    _register(name, spec_data, slugify(name))
            except Exception:  # noqa: BLE001
                pass

        # --- Layer 3: tools_generic.yaml (declarative generic specs) --------
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
                        if not name or name in tools:
                            # Do not override tools.yaml entries (existing behavior)
                            continue
                        spec_data = cls._normalize_generic_yaml(spec)
                        _register(name, spec_data, slugify(name))
            except Exception:  # noqa: BLE001
                pass

        # --- Layer 1 fill-in: inventory tools NOT covered by a curated slug --
        for slug, inv_spec in inventory_by_slug.items():
            if slug in by_slug:
                continue  # curated contract already covers this canonical tool
            name = inv_spec.get("name") or slug
            # Guard against a curated tool occupying the same display name.
            if name in tools:
                name = f"{name} ({slug})"
            tools[name] = ToolSpec(**inv_spec)
            by_slug[slug] = name

        registry = cls(tools)
        registry._inventory_slugs = inventory_slugs
        return registry

    @staticmethod
    def _merge_inventory_metadata(curated: dict[str, Any], inv: dict[str, Any]) -> dict[str, Any]:
        """Enrich a curated spec with inventory-only quality metadata.

        Curated invocation/IO/contract fields are authoritative and untouched.
        Only fields the curated entry does not already define are filled in.
        """
        result = dict(curated)
        # Quality / provenance metadata that curated YAML never carries.
        for key in (
            "classification", "confidence_score", "reliability", "scale",
            "cost_tier", "data_quality", "web_only", "sections",
            "categories_all", "aliases", "provenance",
        ):
            if key in inv and not result.get(key):
                result[key] = inv[key]
        # Merge inventory free-text into notes without clobbering curated notes.
        inv_notes = inv.get("notes", "")
        if inv_notes:
            existing = result.get("notes", "")
            if existing and inv_notes not in existing:
                result["notes"] = f"{existing} | {inv_notes}"
            elif not existing:
                result["notes"] = inv_notes
        # Stash raw inventory metadata for queryability.
        meta = dict(result.get("metadata", {}) or {})
        meta.update(inv.get("metadata", {}) or {})
        meta["inventory_classification"] = inv.get("classification", "")
        result["metadata"] = meta
        return result

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
            "binary", "invocation", "parse", "enabled", "stdin",
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

    def upsert_many(self, specs: list[ToolSpec]) -> None:
        """Add or replace tool specs by name, then rebuild the indexes once.

        Used by the adapter bridge to register hand-written Python adapters as
        first-class, routable tools (they win on a name collision).
        """
        for spec in specs:
            self._tools[spec.name] = spec
        self._reindex()

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
        """Return tools that accept a given input type (index-backed, O(matches))."""
        names = self._input_index.get(input_type, [])
        return [self._tools[n] for n in names if n in self._tools]

    def tools_for_inputs(self, available: set[str]) -> list[ToolSpec]:
        """Return tools whose consumed types intersect ``available`` (deduped).

        Uses the input-type index so eligibility selection stays proportional to
        the number of matching tools, not the size of the whole registry. This
        keeps the scheduler fast even with the full 532+ tool catalogue.
        """
        seen: set[str] = set()
        result: list[ToolSpec] = []
        for itype in available:
            for name in self._input_index.get(itype, []):
                if name in seen:
                    continue
                seen.add(name)
                spec = self._tools.get(name)
                if spec is not None:
                    result.append(spec)
        return result

    def by_output_type(self, output_type: str) -> list[ToolSpec]:
        """Return tools that produce a given output type."""
        return [
            t for t in self._tools.values()
            if output_type in t.output_types or output_type in t.produces
        ]

    def by_slug(self, slug: str) -> ToolSpec | None:
        """Look up a tool by canonical slug."""
        name = self._by_slug.get(slug)
        return self._tools.get(name) if name else None

    def curated_tools(self) -> list[ToolSpec]:
        """Tools backed by a hand-curated YAML contract."""
        return [t for t in self._tools.values() if t.source == "curated"]

    def inventory_tools(self) -> list[ToolSpec]:
        """Tools materialised from the canonical inventory (no full contract)."""
        return [t for t in self._tools.values() if t.source == "inventory"]

    def executable_tools(self) -> list[ToolSpec]:
        """Tools the orchestrator can attempt to run (api/cli execution path)."""
        return [t for t in self._tools.values() if t.is_executable]

    def non_executable_tools(self) -> list[ToolSpec]:
        """Tools registered for visibility but skipped by the orchestrator."""
        return [t for t in self._tools.values() if t.non_executable]

    def canonical_slugs(self) -> set[str]:
        """All canonical inventory slugs the registry covers (532 when complete)."""
        return set(self._inventory_slugs)

    def covered_slugs(self) -> set[str]:
        """Slugs of every registered tool (curated + inventory)."""
        return {t.slug for t in self._tools.values() if t.slug}

    def stats(self) -> dict[str, int]:
        """Headline counts for observability / docs."""
        curated = self.curated_tools()
        inventory = self.inventory_tools()
        return {
            "total": len(self._tools),
            "curated": len(curated),
            "inventory_derived": len(inventory),
            "executable": len(self.executable_tools()),
            "non_executable": len(self.non_executable_tools()),
            "canonical_slugs": len(self._inventory_slugs),
        }

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
