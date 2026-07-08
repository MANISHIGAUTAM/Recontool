"""Adapter framework.

Adapters are PURE (docs/D4-adr.md ADR-011): they run one tool/source, capture
raw output, and emit normalized Events. They contain NO cross-asset correlation
logic — that lives in the normalization engine.

Every adapter:
  - declares whether it is passive or active (gate-aware),
  - declares which seed types it accepts,
  - declares what it consumes (chaining input) and produces,
  - re-checks scope before any active egress,
  - emits Events + an audit trail.
"""
from __future__ import annotations

import abc
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Literal

from recontool.config import RateProfile
from recontool.core.artifacts import ArtifactStore
from recontool.core.scope import Scope
from recontool.net.http_client import HttpClient

EntityType = Literal["asset", "service", "endpoint", "finding", "edge"]

# ── live tool I/O logging ─────────────────────────────────────────────────────
# Emit every tool's command + (bounded) raw output to stdout so `docker logs`
# shows exactly what each tool ran and produced — like running it by hand. On by
# default; set RECON_LOG_TOOL_IO=0 to silence. Output is capped so a firehose tool
# (hakrawler/katana emitting 100k+ lines) logs a preview, not gigabytes.
_TOOL_IO = logging.getLogger("recontool.toolio")
_IO_MAX_LINES = 15
_IO_ENABLED = os.environ.get("RECON_LOG_TOOL_IO", "1") != "0"


def log_tool_io(tool: str, target: Any, cmd: Any, output: str = "", *, note: str = "") -> None:
    """Log one tool execution's command + raw output to docker logs (INFO).

    ``cmd`` may be the argv list or a string; ``output`` is the captured stdout
    (use ``note`` instead for tools that write to a file, e.g. "→ 3 findings").
    """
    if not _IO_ENABLED:
        return
    if isinstance(cmd, (list, tuple)):
        cmd = " ".join(str(c) for c in cmd)
    if isinstance(target, (list, tuple)):
        target = ",".join(str(t) for t in target)
    target = str(target)[:160]
    lines = output.splitlines()
    nbytes = len(output.encode("utf-8", "ignore"))
    if note:
        body = f"  | {note}"
    elif not lines:
        body = "  | (no stdout)"
    else:
        body = "\n".join("  | " + ln[:500] for ln in lines[:_IO_MAX_LINES])
        if len(lines) > _IO_MAX_LINES:
            body += f"\n  | … (+{len(lines) - _IO_MAX_LINES} more lines, {nbytes} bytes total)"
    _TOOL_IO.info("[tool-io] %s  target=%s\n  $ %s\n%s", tool, target, cmd, body)


@dataclass
class Event:
    """A normalized output record from an adapter."""

    entity: EntityType
    tool: str
    data: dict[str, Any]
    raw_ref: str | None = None

    # convenience constructors -------------------------------------------------
    @staticmethod
    def asset(tool: str, atype: str, value: str, **attrs: Any) -> "Event":
        return Event("asset", tool, {"type": atype, "value": value, **attrs})

    @staticmethod
    def service(tool: str, host: str, port: int, **attrs: Any) -> "Event":
        return Event("service", tool, {"host": host, "port": port, **attrs})

    @staticmethod
    def endpoint(tool: str, url: str, **attrs: Any) -> "Event":
        return Event("endpoint", tool, {"url": url, **attrs})

    @staticmethod
    def finding(tool: str, kind: str, title: str, **attrs: Any) -> "Event":
        return Event("finding", tool, {"kind": kind, "title": title, **attrs})

    @staticmethod
    def edge(tool: str, src: str, dst: str, rel: str, **attrs: Any) -> "Event":
        return Event("edge", tool, {"src": src, "dst": dst, "rel": rel, **attrs})


@dataclass
class AdapterContext:
    """Everything an adapter needs to run one unit of work."""

    scan_id: str
    scope: Scope
    profile: RateProfile
    http: HttpClient
    artifacts: ArtifactStore
    # Chaining input: assets discovered so far, grouped by type.
    inputs: dict[str, list[str]] = field(default_factory=dict)
    api_keys: dict[str, str | None] = field(default_factory=dict)

    def seeds_of(self, atype: str) -> list[str]:
        return self.inputs.get(atype, [])


class Adapter(abc.ABC):
    """Base class for every tool/source integration."""

    name: str = "adapter"
    category: str = "misc"
    is_active: bool = False              # touches the target?
    # Seed types this adapter consumes (chaining): e.g. ["domain", "subdomain"]
    consumes: tuple[str, ...] = ("domain",)
    # Asset types this adapter typically produces (for planning/visibility).
    produces: tuple[str, ...] = ()
    # If True, requires an API key (declared in `key_env`) to do anything.
    key_env: str | None = None

    def available(self, ctx: AdapterContext) -> bool:
        """Can this adapter run given current config/keys/tooling? Override for
        CLI tools (binary present?) or keyed APIs."""
        if self.key_env:
            return bool(ctx.api_keys.get(self.key_env))
        return True

    @abc.abstractmethod
    async def run(self, ctx: AdapterContext) -> list[Event]:
        """Execute and return normalized events. Must be idempotent-safe."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Optional extended contract methods (event-driven engine).
    # Existing adapters inherit these no-op defaults and continue working.
    # ------------------------------------------------------------------

    def install_check(self) -> bool:
        """Check if the tool is installed and available. Default: True."""
        return True

    def prepare(self, ctx: AdapterContext) -> None:
        """Pre-execution setup (create temp dirs, validate config). Default: no-op."""

    def validate_inputs(self, inputs: dict[str, Any]) -> list[str]:
        """Validate inputs before execution. Returns list of error strings (empty = valid)."""
        return []

    def build_command(self, ctx: AdapterContext) -> str | None:
        """Build the shell command string for CLI tools. Returns None for API adapters."""
        return None

    def parse_stdout(self, stdout: str) -> dict[str, Any]:
        """Parse raw stdout into a structured dict. Default: wraps in 'raw' key."""
        return {"raw": stdout}

    def parse_files(self, paths: list[str]) -> dict[str, Any]:
        """Parse output files into a structured dict. Default: empty."""
        return {}

    def emit_normalized_events(self, parsed: dict[str, Any]) -> list[Event]:
        """Convert parsed output into normalized Event objects. Default: empty."""
        return []

    def map_outputs_to_entities(self, parsed: dict[str, Any]) -> list[Event]:
        """Map parsed outputs to entity discovery events. Default: empty."""
        return []

    def resolve_pending_keys(self, parsed: dict[str, Any]) -> list[str]:
        """Return list of pending key values this output resolves. Default: empty."""
        return []

    def can_run_in_parallel(self) -> bool:
        """Whether this adapter is safe to run concurrently. Default: True."""
        return True

    def dependencies(self) -> list[str]:
        """Tool names that must complete before this adapter runs. Default: none."""
        return []

    def timeout_seconds(self) -> int:
        """Maximum execution time in seconds. Default: 300."""
        return 300

    def retry_policy(self) -> dict[str, Any]:
        """Retry configuration. Default: no retries."""
        return {"max_retries": 0, "backoff_factor": 1.0, "retryable_errors": []}
