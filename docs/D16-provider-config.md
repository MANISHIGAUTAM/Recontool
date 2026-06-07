# D16 — Provider Configuration

> Every external source family is described by a dedicated, **validated** provider
> block in `config/providers.yaml`. Secrets are never stored in the file — only the
> NAME of the environment variable that supplies them. The config layer **fails
> fast** when an enabled provider is misconfigured.

## 1. Source families

`config/providers.yaml` ships blocks across all required families:

| Family | Examples (shipped) |
|--------|--------------------|
| `dns_cert` | crtsh, certspotter |
| `passive_index` | shodan, internetdb, censys, hackertarget |
| `archive` | wayback |
| `search_engine` | urlscan, brave_search |
| `code_search` | github_code, gitlab_search |
| `threat_intel` | alienvault_otx, greynoise, threatfox, nvd |
| `cloud_storage` | grayhatwarfare |
| `identity_social` | hunter, sherlock |
| `browser_rendered` | urlscan_render |
| `mobile_apk` | apkpure |
| `visual` | urlscan_screens |
| `network_intel` | bgpview, ripestat |

## 2. Provider block schema

Validated by `recontool/providers.py` (pydantic). Every block defines:

```yaml
- name: certspotter
  family: dns_cert
  enabled: true
  auth_method: bearer          # none | api_key | bearer | basic | header | query | cookie
  auth_env: CERTSPOTTER_API_KEY # NAME of env var (NEVER the secret itself)
  key_optional: true           # works keyless at lower limits; key only raises them
  auth_header: Authorization
  base_url: "https://api.certspotter.com"
  endpoints: {issuances: "/v1/issuances?domain={domain}&include_subdomains=true&expand=dns_names"}
  query_limit: 1000
  timeout: 20.0
  rate_limit: {unit: query, per_minute: 20, concurrency: 2, budget_per_run: 100}
  retry: {max_attempts: 3, backoff: exp_jitter, retry_on: [429, 500, 502, 503, 504, timeout]}
  pagination: {style: none}    # none | page | offset | cursor (+ params)
  cache: {enabled: true, ttl_seconds: 43200}
  mock_fixture: "providers/certspotter.json"   # recorded response for demo/test
  on_error: skip               # skip | fail
  environments:                # per-environment overrides
    demo: {base_url: "https://mock.local"}
```

## 3. Secrets handling (constraint 17)

- The YAML stores **only `auth_env`** (the variable name).
- The real secret is read at runtime from the environment (or your secret manager
  exporting env vars). See `.env.example` for the full variable list.
- `ProviderConfig.secret()` resolves it; `has_secret()` checks presence.

## 4. Fail-fast validation

```bash
recontool config-validate --env live    # exit 2 if any enabled provider is broken
recontool config-validate --env demo     # demo requires mock_fixture, not secrets
recontool config-validate --env test
```

Validation rules per environment:

| Env | Enabled provider requires… |
|-----|----------------------------|
| `live` / `test` | its secret env var set (unless `key_optional: true`) **and** a `base_url` |
| `demo` | a `mock_fixture` (real secrets are never needed; mock only) |

Structural errors (unknown family, auth method without `auth_env`, non-http
`base_url`, duplicate names) fail in all environments.

## 5. Mock fixtures (demo/test)

Each provider points at a recorded response under `tests/fixtures/providers/`.
Validate/replay them:

```bash
recontool replay-fixtures                 # validate every provider fixture loads
recontool replay-fixtures --provider crtsh
```

In `demo`/`test` mode the HTTP chokepoint serves the in-process mock environment,
so **no real provider is ever called** (proven by `tests/integration/test_provider_fixtures.py`).

## 6. Adapters ↔ providers

Generic adapters (`config/tools_generic.yaml`, executed by
`recontool/adapters/generic.py`) declare their `endpoint`, `headers`, `bucket`,
and `requires_key`, and reference a provider via the optional `provider:` field.
At runtime the endpoint is called through the mode-gated, rate-limited,
circuit-broken HTTP client; in demo/test it is served from the fixture/mock.

## 7. Adding a provider

1. Add a block to `config/providers.yaml` (pick the right `family`, set `auth_env`).
2. Add `tests/fixtures/providers/<name>.json` (a recorded/representative response).
3. Add the matching adapter spec to `config/tools_generic.yaml` (or a hand-written adapter).
4. Add the env var to `.env.example`.
5. `recontool config-validate --env demo && recontool replay-fixtures`.
