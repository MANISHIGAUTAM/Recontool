"""Output normalization helpers for tool execution results.

Maps raw tool output (stdout, stderr, files, artifacts) into a structured
NormalizedOutput that can be consumed by the scheduling engine and the
existing normalize/engine.py Normalizer.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from recontool.adapters.base import Event


@dataclass
class NormalizedOutput:
    """Structured representation of a tool's execution output."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    raw_files: list[str] = field(default_factory=list)
    parsed_json: dict[str, Any] = field(default_factory=dict)
    generated_artifacts: list[str] = field(default_factory=list)
    discovered_entities: list[Event] = field(default_factory=list)
    confidence_score: float = 1.0
    evidence_links: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    partial_failures: list[str] = field(default_factory=list)


class OutputNormalizer:
    """Normalize raw tool output into structured NormalizedOutput."""

    def normalize_tool_output(
        self,
        tool_name: str,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
        files: list[str] | None = None,
        artifacts: list[str] | None = None,
    ) -> NormalizedOutput:
        """Parse tool output into a NormalizedOutput instance.

        Attempts JSON parsing of stdout. If stdout is valid JSON, it is
        stored in parsed_json and entities are extracted from known patterns.
        """
        files = files or []
        artifacts = artifacts or []
        warnings: list[str] = []
        partial_failures: list[str] = []

        # Attempt JSON parse of stdout
        parsed_json: dict[str, Any] = {}
        if stdout.strip():
            try:
                parsed = json.loads(stdout)
                if isinstance(parsed, dict):
                    parsed_json = parsed
                elif isinstance(parsed, list):
                    parsed_json = {"results": parsed}
            except (json.JSONDecodeError, ValueError):
                pass

        # Check for stderr warnings
        if stderr.strip():
            for line in stderr.strip().splitlines():
                line = line.strip()
                if line:
                    if "error" in line.lower() or "fatal" in line.lower():
                        partial_failures.append(line)
                    else:
                        warnings.append(line)

        # Extract discovered entities from parsed JSON
        discovered = self._extract_entities(tool_name, parsed_json)

        # Determine confidence based on exit code and output quality
        confidence = self._compute_confidence(exit_code, stdout, stderr, discovered)

        return NormalizedOutput(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            raw_files=files,
            parsed_json=parsed_json,
            generated_artifacts=artifacts,
            discovered_entities=discovered,
            confidence_score=confidence,
            evidence_links=[],
            metadata={"tool_name": tool_name},
            warnings=warnings,
            partial_failures=partial_failures,
        )

    def _extract_entities(
        self, tool_name: str, parsed: dict[str, Any]
    ) -> list[Event]:
        """Extract entity Events from parsed JSON output.

        Looks for common patterns: 'hosts', 'domains', 'subdomains',
        'ips', 'urls', 'services', 'endpoints'.
        """
        entities: list[Event] = []

        # Domain/subdomain patterns
        for key in ("domains", "subdomains", "hosts"):
            items = parsed.get(key, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, str):
                        entities.append(
                            Event.asset(tool_name, "domain", item)
                        )
                    elif isinstance(item, dict) and "name" in item:
                        entities.append(
                            Event.asset(tool_name, "domain", item["name"])
                        )

        # IP patterns
        for key in ("ips", "ip_addresses", "addresses"):
            items = parsed.get(key, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, str):
                        entities.append(
                            Event.asset(tool_name, "ip", item)
                        )

        # URL patterns
        for key in ("urls", "endpoints"):
            items = parsed.get(key, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, str):
                        entities.append(
                            Event.endpoint(tool_name, item)
                        )

        # Service patterns
        services = parsed.get("services", [])
        if isinstance(services, list):
            for svc in services:
                if isinstance(svc, dict) and "host" in svc and "port" in svc:
                    entities.append(
                        Event.service(tool_name, svc["host"], int(svc["port"]))
                    )

        return entities

    def _compute_confidence(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        discovered: list[Event],
    ) -> float:
        """Compute a confidence score for the output (0.0 to 1.0)."""
        if exit_code != 0:
            return 0.3
        if not stdout.strip() and not discovered:
            return 0.5
        if discovered:
            return 1.0
        return 0.7
