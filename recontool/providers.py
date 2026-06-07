"""Provider configuration system — validated, env-mapped, fail-fast.

Every external source family (search engines, passive indexes, archives, code
search, threat intel, cloud/storage, identity/social, browser-rendered, mobile/
APK, visual/screenshot) is described by a dedicated provider block in
``config/providers.yaml``. Each block declares:

  enabled, family, auth (method + env var), base_url, endpoints, query limits,
  rate limit / quota, timeout, retry policy, pagination, cache policy, mock
  fixture source, error-handling behavior, and per-environment overrides.

This module loads + VALIDATES those blocks with pydantic and fails fast when a
provider is ``enabled: true`` but its required secret (env var) is missing, or
its config is structurally invalid. Secrets NEVER live in the YAML — only the
NAME of the environment variable that supplies them (constraint 17).

Used by:
  * the generic adapter engine (endpoint/base_url/auth/pagination/timeout),
  * preflight (provider reachability + config validity),
  * the ``recontool config-validate`` command,
  * provider config unit tests + mock-fixture loading.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from recontool.config import CONFIG_DIR

PROVIDERS_YAML = CONFIG_DIR / "providers.yaml"

# The external source families the architecture requires (PROVIDER CONFIG REQUIREMENTS).
FAMILIES = (
    "search_engine",       # search engines / metasearch
    "passive_index",       # passive internet indexes
    "archive",             # web archives
    "code_search",         # source-code search
    "threat_intel",        # malware / IOC / threat intel
    "cloud_storage",       # cloud / storage
    "identity_social",     # identity / social
    "browser_rendered",    # browser-rendered sources
    "mobile_apk",          # mobile / APK sources
    "visual",              # visual / screenshot sources
    "dns_cert",            # passive DNS / certificate transparency
    "network_intel",       # whois / asn / bgp
)

AuthMethod = Literal["none", "api_key", "bearer", "basic", "header", "query", "cookie"]


class RetryPolicy(BaseModel):
    max_attempts: int = Field(3, ge=1, le=10)
    backoff: Literal["none", "exp", "exp_jitter", "exp_jitter_long"] = "exp_jitter"
    retry_on: list[Any] = Field(default_factory=lambda: [429, 500, 502, 503, 504, "timeout"])


class QuotaPolicy(BaseModel):
    unit: Literal["request", "query", "credit", "search", "none"] = "request"
    per_minute: int = Field(30, ge=0)
    concurrency: int = Field(4, ge=1, le=100)
    budget_per_run: int = Field(0, ge=0)  # 0 = unbounded (free/keyless)


class Pagination(BaseModel):
    style: Literal["none", "page", "offset", "cursor"] = "none"
    page_param: Optional[str] = None
    size_param: Optional[str] = None
    page_size: int = Field(100, ge=1, le=10000)
    max_pages: int = Field(1, ge=1, le=1000)
    cursor_path: Optional[str] = None  # JSON path to next-cursor in the response


class CachePolicy(BaseModel):
    enabled: bool = True
    ttl_seconds: int = Field(3600, ge=0)


class ProviderConfig(BaseModel):
    name: str
    family: str
    enabled: bool = False
    auth_method: AuthMethod = "none"
    # NAME of the env var holding the secret (never the secret itself).
    auth_env: Optional[str] = None
    # If True, the provider works WITHOUT the secret (lower limits); a present key
    # only raises limits. Such providers do NOT fail validation when the key is unset.
    key_optional: bool = False
    auth_header: Optional[str] = None   # header name for method=header/bearer/api_key
    auth_query_param: Optional[str] = None  # query param name for method=query
    base_url: str = ""
    endpoints: dict[str, str] = Field(default_factory=dict)
    query_limit: int = Field(100, ge=1)
    timeout: float = Field(20.0, gt=0)
    rate_limit: QuotaPolicy = Field(default_factory=QuotaPolicy)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    pagination: Pagination = Field(default_factory=Pagination)
    cache: CachePolicy = Field(default_factory=CachePolicy)
    # Path (under tests/fixtures/providers/) to a recorded response for demo/test.
    mock_fixture: Optional[str] = None
    # Behavior on unrecoverable error: skip the provider, or fail the scan.
    on_error: Literal["skip", "fail"] = "skip"
    # Per-environment overrides: {demo: {...}, test: {...}, live: {...}}
    environments: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @field_validator("family")
    @classmethod
    def _family_known(cls, v: str) -> str:
        if v not in FAMILIES:
            raise ValueError(f"unknown family {v!r}; valid: {FAMILIES}")
        return v

    @model_validator(mode="after")
    def _auth_consistency(self) -> "ProviderConfig":
        if self.auth_method != "none" and not self.auth_env:
            raise ValueError(
                f"provider {self.name!r}: auth_method={self.auth_method} requires 'auth_env' "
                "(the NAME of the env var supplying the secret)")
        if self.base_url and not self.base_url.startswith(("http://", "https://")):
            raise ValueError(f"provider {self.name!r}: base_url must be http(s)://")
        return self

    # ── runtime helpers ──────────────────────────────────────────────────────
    def for_env(self, env: str) -> "ProviderConfig":
        """Return a copy with per-environment overrides applied."""
        override = self.environments.get(env)
        if not override:
            return self
        data = self.model_dump()
        data.update({k: v for k, v in override.items() if k != "environments"})
        return ProviderConfig(**data)

    def secret(self) -> Optional[str]:
        """Resolve the secret from the environment (never stored in YAML)."""
        if self.auth_env:
            return os.getenv(self.auth_env)
        return None

    def has_secret(self) -> bool:
        return bool(self.secret())

    def endpoint(self, name: str) -> str:
        """Full URL for a named endpoint (base_url + endpoint path)."""
        path = self.endpoints.get(name, "")
        if path.startswith(("http://", "https://")):
            return path
        return self.base_url.rstrip("/") + "/" + path.lstrip("/")


class ProviderRegistry(BaseModel):
    version: int = 1
    providers: list[ProviderConfig] = Field(default_factory=list)

    def by_name(self, name: str) -> Optional[ProviderConfig]:
        for p in self.providers:
            if p.name == name:
                return p
        return None

    def enabled(self) -> list[ProviderConfig]:
        return [p for p in self.providers if p.enabled]

    def by_family(self, family: str) -> list[ProviderConfig]:
        return [p for p in self.providers if p.family == family]


class ProviderValidationError(Exception):
    """Raised when an enabled provider's config is missing/invalid (fail fast)."""


def load_providers(path: Path | None = None) -> ProviderRegistry:
    """Load + structurally validate config/providers.yaml. Does NOT check secrets."""
    path = path or PROVIDERS_YAML
    if not path.exists():
        return ProviderRegistry()
    import yaml

    raw = yaml.safe_load(path.read_text()) or {}
    try:
        return ProviderRegistry(**raw)
    except ValidationError as exc:
        raise ProviderValidationError(f"providers.yaml invalid:\n{exc}") from exc


def validate_providers(env: str = "live", path: Path | None = None) -> list[str]:
    """Full validation. Returns a list of error strings (empty = OK).

    Fail-fast rule: an ENABLED provider that needs a secret but whose env var is
    unset (in live/test env) is an error. In demo env, secrets are NOT required
    because providers must be served from mock fixtures.
    """
    errors: list[str] = []
    try:
        reg = load_providers(path)
    except ProviderValidationError as exc:
        return [str(exc)]

    seen: set[str] = set()
    for p in reg.providers:
        if p.name in seen:
            errors.append(f"duplicate provider name {p.name!r}")
        seen.add(p.name)
        pe = p.for_env(env)
        if not pe.enabled:
            continue
        # demo never needs real secrets (mock only); it DOES need a fixture.
        if env == "demo":
            if not pe.mock_fixture:
                errors.append(f"provider {p.name!r} enabled in demo but has no mock_fixture")
            continue
        if pe.auth_method != "none" and not pe.key_optional and not pe.has_secret():
            errors.append(
                f"provider {p.name!r} enabled but secret env var {pe.auth_env!r} is unset")
        if not pe.base_url:
            errors.append(f"provider {p.name!r} enabled but base_url is empty")
    return errors


@lru_cache(maxsize=1)
def provider_registry() -> ProviderRegistry:
    return load_providers()


def env_var_map() -> dict[str, str]:
    """{provider_name: env_var_name} for every provider that needs a secret."""
    reg = load_providers()
    return {p.name: p.auth_env for p in reg.providers if p.auth_env}
