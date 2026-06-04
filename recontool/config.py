"""Central configuration and rate-limit profiles.

Settings load from environment / .env. Rate profiles tune EVERY active tool's
concurrency, QPS and timing simultaneously (see docs/D6-opsec.md).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

Profile = Literal["passive_only", "stealth", "normal", "aggressive"]


def _csv(name: str) -> list[str]:
    raw = os.getenv(name, "").strip()
    return [x.strip() for x in raw.split(",") if x.strip()]


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


@dataclass
class Settings:
    db_url: str = field(default_factory=lambda: os.getenv("RECON_DB_URL", "sqlite:///recontool.db"))
    artifact_dir: Path = field(
        default_factory=lambda: Path(os.getenv("RECON_ARTIFACT_DIR", "./artifacts")).resolve()
    )
    redis_url: str | None = field(default_factory=lambda: os.getenv("RECON_REDIS_URL") or None)

    proxies: list[str] = field(default_factory=lambda: _csv("RECON_PROXIES"))
    proxy_strategy: str = field(default_factory=lambda: os.getenv("RECON_PROXY_STRATEGY", "round_robin"))
    profile_name: str = field(default_factory=lambda: os.getenv("RECON_PROFILE", "normal"))
    max_concurrency: int = field(default_factory=lambda: int(os.getenv("RECON_MAX_CONCURRENCY", "20")))

    # AI
    ai_base_url: str | None = field(default_factory=lambda: os.getenv("RECON_AI_BASE_URL") or None)
    ai_api_key: str | None = field(default_factory=lambda: os.getenv("RECON_AI_API_KEY") or None)
    ai_model_light: str = field(default_factory=lambda: os.getenv("RECON_AI_MODEL_LIGHT", "gpt-4o-mini"))
    ai_model_heavy: str = field(default_factory=lambda: os.getenv("RECON_AI_MODEL_HEAVY", "gpt-4o"))
    ai_max_calls: int = field(default_factory=lambda: int(os.getenv("RECON_AI_MAX_CALLS", "40")))

    def profile(self) -> RateProfile:
        return PROFILES.get(self.profile_name, PROFILES["normal"])

    def api_key(self, name: str) -> str | None:
        return os.getenv(name) or None

    @property
    def ai_enabled(self) -> bool:
        return bool(self.ai_api_key and self.ai_base_url)


settings = Settings()
