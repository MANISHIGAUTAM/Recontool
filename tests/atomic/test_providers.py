"""Unit tests for the provider-config system: schema validation, fail-fast,
env-var mapping, per-environment overrides, endpoint building, family coverage."""
from __future__ import annotations

import pytest

from recontool.providers import (
    FAMILIES,
    ProviderConfig,
    ProviderRegistry,
    load_providers,
    validate_providers,
)


# ── schema validation ────────────────────────────────────────────────────────
def test_rejects_unknown_family():
    with pytest.raises(Exception):
        ProviderConfig(name="x", family="bogus")


def test_auth_method_requires_env():
    with pytest.raises(Exception):
        ProviderConfig(name="x", family="passive_index", auth_method="api_key")


def test_base_url_must_be_http():
    with pytest.raises(Exception):
        ProviderConfig(name="x", family="archive", base_url="ftp://nope")


def test_endpoint_building():
    p = ProviderConfig(name="x", family="archive", base_url="https://a.io",
                       endpoints={"search": "/q?d={domain}"})
    assert p.endpoint("search") == "https://a.io/q?d={domain}"
    # absolute endpoint passes through
    p2 = ProviderConfig(name="y", family="archive", base_url="https://a.io",
                        endpoints={"x": "https://other.io/z"})
    assert p2.endpoint("x") == "https://other.io/z"


def test_secret_from_env(monkeypatch):
    monkeypatch.setenv("MY_PROVIDER_KEY", "s3cr3t")
    p = ProviderConfig(name="x", family="passive_index", auth_method="api_key",
                       auth_env="MY_PROVIDER_KEY", base_url="https://a.io")
    assert p.has_secret() and p.secret() == "s3cr3t"


def test_per_environment_override():
    p = ProviderConfig(name="x", family="archive", base_url="https://live.io",
                       environments={"demo": {"base_url": "https://mock.io"}})
    assert p.for_env("demo").base_url == "https://mock.io"
    assert p.for_env("live").base_url == "https://live.io"


# ── the shipped config/providers.yaml ────────────────────────────────────────
def test_shipped_config_loads_and_covers_all_families():
    reg = load_providers()
    assert isinstance(reg, ProviderRegistry)
    assert len(reg.providers) >= 20
    covered = {p.family for p in reg.providers}
    assert covered == set(FAMILIES), f"missing families: {set(FAMILIES) - covered}"


def test_shipped_config_valid_in_all_envs():
    for env in ("demo", "test", "live"):
        errors = validate_providers(env)
        assert errors == [], f"env={env} errors: {errors}"


def test_every_enabled_provider_has_a_mock_fixture():
    reg = load_providers()
    for p in reg.providers:
        if p.enabled:
            assert p.mock_fixture, f"{p.name} enabled but no mock_fixture"


def test_fail_fast_when_enabled_keyed_provider_missing_secret(tmp_path):
    yaml_text = """
version: 1
providers:
  - name: needs_key
    family: passive_index
    enabled: true
    auth_method: api_key
    auth_env: DEFINITELY_UNSET_KEY_XYZ
    auth_header: X-Key
    base_url: "https://api.example.com"
    mock_fixture: "providers/x.json"
"""
    f = tmp_path / "providers.yaml"
    f.write_text(yaml_text)
    # live: missing secret -> error
    errs = validate_providers("live", path=f)
    assert any("DEFINITELY_UNSET_KEY_XYZ" in e for e in errs)
    # demo: secret not required (mock fixture present) -> ok
    assert validate_providers("demo", path=f) == []


def test_key_optional_provider_does_not_fail_without_secret(tmp_path):
    yaml_text = """
version: 1
providers:
  - name: keyless_ok
    family: search_engine
    enabled: true
    auth_method: header
    auth_env: OPTIONAL_KEY_XYZ
    key_optional: true
    auth_header: API-Key
    base_url: "https://api.example.com"
    mock_fixture: "providers/x.json"
"""
    f = tmp_path / "providers.yaml"
    f.write_text(yaml_text)
    assert validate_providers("live", path=f) == []


def test_duplicate_provider_names_flagged(tmp_path):
    yaml_text = """
version: 1
providers:
  - {name: dup, family: archive, enabled: false, base_url: "https://a.io"}
  - {name: dup, family: archive, enabled: false, base_url: "https://b.io"}
"""
    f = tmp_path / "providers.yaml"
    f.write_text(yaml_text)
    errs = validate_providers("live", path=f)
    assert any("duplicate" in e for e in errs)
