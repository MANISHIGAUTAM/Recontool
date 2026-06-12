"""Central configuration, rate-limit profiles, and tool-registry loading.

Configuration precedence (highest wins):
    ENV VAR  >  config/recontool.yaml  >  built-in defaults

Rate profiles tune EVERY active tool's concurrency, QPS and timing simultaneously
(see docs/D6-opsec.md). The tool registry (config/tools.yaml) is the machine-readable
contract the orchestrator uses to chain tools (see docs/pipeline/03-category-pipelines.md).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv

load_dotenv()

Profile = Literal["passive_only", "stealth", "normal", "aggressive"]

# Repo root = two levels up from this file (recontool/config.py -> repo/)
REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"


# ─────────────────────────────────────────────────────────────────────────────
# YAML config loading (optional dependency: pyyaml)
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _yaml_config() -> dict[str, Any]:
    """Load config/recontool.yaml if present (falls back to the example file).
    Returns {} if neither exists or PyYAML isn't installed."""
    path = Path(os.getenv("RECON_CONFIG", CONFIG_DIR / "recontool.yaml"))
    if not path.exists():
        example = CONFIG_DIR / "recontool.example.yaml"
        path = example if example.exists() else path
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text()) or {}
    except Exception:  # noqa: BLE001 — missing pyyaml or malformed file
        return {}


def _cfg(*keys: str, default: Any = None) -> Any:
    """Read a nested key from the YAML config, e.g. _cfg('general', 'profile')."""
    node: Any = _yaml_config()
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            return default
        node = node[k]
    return node


def _csv_env(name: str) -> list[str]:
    raw = os.getenv(name, "").strip()
    return [x.strip() for x in raw.split(",") if x.strip()]


# Map provider env-var names -> keys under `api_keys:` in recontool.yaml
_API_KEY_YAML_MAP = {
    "SHODAN_API_KEY": "shodan",
    "CENSYS_API_ID": "censys_id",
    "CENSYS_API_SECRET": "censys_secret",
    "NETLAS_API_KEY": "netlas",
    "GREYNOISE_API_KEY": "greynoise",
    "LEAKIX_API_KEY": "leakix",
    "FULLHUNT_API_KEY": "fullhunt",
    "URLSCAN_API_KEY": "urlscan",
    "CRIMINALIP_API_KEY": "criminalip",
    "BINARYEDGE_API_KEY": "binaryedge",
    "ZOOMEYE_API_KEY": "zoomeye",
    "SECURITYTRAILS_API_KEY": "securitytrails",
    "VIRUSTOTAL_API_KEY": "virustotal",
    "CHAOS_API_KEY": "chaos",
    "CERTSPOTTER_API_KEY": "certspotter",
    "IPINFO_TOKEN": "ipinfo",
    "GITHUB_TOKEN": "github_token",
    "GITLAB_TOKEN": "gitlab_token",
    "GRAYHATWARFARE_API_KEY": "grayhatwarfare",
    "HUNTER_API_KEY": "hunter",
    "HIBP_API_KEY": "hibp",
    "PUBLICWWW_API_KEY": "publicwww",
    "NVD_API_KEY": "nvd",
    "VULNERS_API_KEY": "vulners",
}


@dataclass(frozen=True)
class RateProfile:
    """Behavioural envelope for a scan. The single knob that makes the whole
    pipeline stealthy or fast."""

    name: str
    active_enabled: bool          # are active phases allowed at all?
    global_concurrency: int       # max parallel tasks
    per_host_concurrency: int     # max parallel requests to a single host
    requests_per_second: float    # global active QPS ceiling
    jitter_seconds: float         # random sleep added between requests
    dns_qps: float
    port_set: str                 # 'top-100' | 'top-1000' | 'full'
    nuclei_severities: tuple[str, ...]
    randomize_order: bool


# POLICY NOTE (docs/blueprint/README.md §Policy): under the authorized-only blueprint,
# the "stealth" profile's jitter/randomization is reframed as POLITENESS (thundering-herd
# avoidance + provider-limit compliance), NOT detection evasion. Roadmap G2 renames it to
# "polite". No proxy rotation / rate-limit bypass is used; see net/circuit.py.
PROFILES: dict[str, RateProfile] = {
    "passive_only": RateProfile(
        name="passive_only", active_enabled=False, global_concurrency=20,
        per_host_concurrency=4, requests_per_second=10.0, jitter_seconds=0.0,
        dns_qps=20.0, port_set="top-100", nuclei_severities=(), randomize_order=False,
    ),
    "stealth": RateProfile(
        name="stealth", active_enabled=True, global_concurrency=4,
        per_host_concurrency=1, requests_per_second=2.0, jitter_seconds=1.5,
        dns_qps=5.0, port_set="top-100",
        nuclei_severities=("info", "low", "medium"), randomize_order=True,
    ),
    "normal": RateProfile(
        name="normal", active_enabled=True, global_concurrency=20,
        per_host_concurrency=4, requests_per_second=15.0, jitter_seconds=0.2,
        dns_qps=50.0, port_set="top-1000",
        nuclei_severities=("low", "medium", "high", "critical"), randomize_order=False,
    ),
    "aggressive": RateProfile(
        name="aggressive", active_enabled=True, global_concurrency=60,
        per_host_concurrency=10, requests_per_second=60.0, jitter_seconds=0.0,
        dns_qps=200.0, port_set="full",
        nuclei_severities=("info", "low", "medium", "high", "critical"),
        randomize_order=False,
    ),
}


def _resolve(env_name: str, yaml_keys: tuple[str, ...], default: Any) -> Any:
    """ENV > YAML > default."""
    if os.getenv(env_name) not in (None, ""):
        return os.getenv(env_name)
    val = _cfg(*yaml_keys, default=None)
    return val if val not in (None, "") else default


# Conservative per-provider QPS ceilings so the engine stays UNDER each source's
# published / free-tier limit. This is limit COMPLIANCE (politeness), NOT evasion:
# it throttles us below a provider's threshold so many workers sharing one key can
# never collectively exceed it. Keys are the HttpClient `bucket=` names. Override
# any of them via `network.rate_limits:` in config/recontool.yaml.
DEFAULT_PROVIDER_QPS: dict[str, float] = {
    "hackertarget": 0.2,   # free API is very limited (a few requests/min)
    "crtsh": 1.0,
    "otx": 2.0,
    "wayback": 1.0,
    "wayback_js": 1.0,
    "shodan": 1.0,
    "censys": 1.0,
    "netlas": 1.0,
    "urlscan": 1.0,
    "leakix": 1.0,
    "fullhunt": 1.0,
    "criminalip": 1.0,
    "greynoise": 1.0,
    "internetdb": 1.0,
}


@dataclass
class Settings:
    db_url: str = field(default_factory=lambda: _resolve(
        "RECON_DB_URL", ("general", "db_url"), "sqlite:///recontool.db"))
    artifact_dir: Path = field(default_factory=lambda: Path(_resolve(
        "RECON_ARTIFACT_DIR", ("general", "artifact_dir"), "./artifacts")).resolve())
    redis_url: str | None = field(default_factory=lambda: _resolve(
        "RECON_REDIS_URL", ("general", "redis_url"), "") or None)

    proxy_strategy: str = field(default_factory=lambda: _resolve(
        "RECON_PROXY_STRATEGY", ("network", "proxy_strategy"), "round_robin"))
    profile_name: str = field(default_factory=lambda: _resolve(
        "RECON_PROFILE", ("general", "profile"), "normal"))
    max_concurrency: int = field(default_factory=lambda: int(_resolve(
        "RECON_MAX_CONCURRENCY", ("general", "max_concurrency"), 20)))

    # AI
    ai_base_url: str | None = field(default_factory=lambda: _resolve(
        "RECON_AI_BASE_URL", ("ai", "base_url"), "") or None)
    ai_api_key: str | None = field(default_factory=lambda: _resolve(
        "RECON_AI_API_KEY", ("ai", "api_key"), "") or None)
    ai_model_light: str = field(default_factory=lambda: _resolve(
        "RECON_AI_MODEL_LIGHT", ("ai", "model_light"), "gpt-4o-mini"))
    ai_model_heavy: str = field(default_factory=lambda: _resolve(
        "RECON_AI_MODEL_HEAVY", ("ai", "model_heavy"), "gpt-4o"))
    ai_max_calls: int = field(default_factory=lambda: int(_resolve(
        "RECON_AI_MAX_CALLS", ("ai", "max_calls"), 40)))

    # API / UI server (read API + SSE + scan control). Bind to localhost by
    # default; a bearer token is REQUIRED for every non-health route.
    api_token: str | None = field(default_factory=lambda: _resolve(
        "RECON_API_TOKEN", ("api", "token"), "") or None)
    api_host: str = field(default_factory=lambda: _resolve(
        "RECON_API_HOST", ("api", "host"), "127.0.0.1"))
    api_port: int = field(default_factory=lambda: int(_resolve(
        "RECON_API_PORT", ("api", "port"), 8088)))

    @property
    def proxies(self) -> list[str]:
        env = _csv_env("RECON_PROXIES")
        if env:
            return env
        return list(_cfg("network", "proxies", default=[]) or [])

    def profile(self) -> RateProfile:
        return PROFILES.get(self.profile_name, PROFILES["normal"])

    def provider_rate_limits(self) -> dict[str, float]:
        """Per-provider QPS ceilings (compliance — stay under each source's limit).

        Built-in conservative defaults for rate-sensitive endpoints, overridable
        via ``network.rate_limits:`` in recontool.yaml (provider bucket -> QPS).
        This throttles the engine BELOW a provider's published ceiling; it is not
        a rate-limit-bypass mechanism.
        """
        merged = dict(DEFAULT_PROVIDER_QPS)
        cfg = _cfg("network", "rate_limits", default={}) or {}
        if isinstance(cfg, dict):
            for k, v in cfg.items():
                try:
                    merged[str(k)] = float(v)
                except (TypeError, ValueError):
                    continue
        return merged

    def api_key(self, name: str) -> str | None:
        """Resolve a provider key: ENV var first, then config/recontool.yaml."""
        if os.getenv(name):
            return os.getenv(name)
        yaml_key = _API_KEY_YAML_MAP.get(name)
        if yaml_key:
            val = _cfg("api_keys", yaml_key, default=None)
            return val or None
        return None

    def enabled_categories(self) -> list[int]:
        return list(_cfg("categories", "enabled", default=[1, 2, 3, 6]) or [])

    def resource(self, name: str, default: str) -> str:
        return _cfg("resources", name, default=default)

    @property
    def ai_enabled(self) -> bool:
        return bool(self.ai_api_key and self.ai_base_url)


# ─────────────────────────────────────────────────────────────────────────────
# Tool registry (config/tools.yaml)
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def load_tool_registry() -> dict[str, dict]:
    """Load the machine-readable tool registry. Returns {tool_name: contract}."""
    path = CONFIG_DIR / "tools.yaml"
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text()) or {}
        return data.get("tools", {})
    except Exception:  # noqa: BLE001
        return {}


def tools_for_category(category: int) -> dict[str, dict]:
    return {n: t for n, t in load_tool_registry().items() if t.get("category") == category}


settings = Settings()
