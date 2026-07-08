# jsluice

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `jsluice` · NOT in extracted inventory.

**Purpose.** BishopFox JS analyzer: extracts URLs, endpoints, and secrets via AST.

| Field | Value |
|-------|-------|
| Closes gap | JavaScript analysis |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `js_file, url` |
| Produces (canonical) | `url, secret, endpoint` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

AST-based, more accurate than regex LinkFinder/SecretFinder; MULTI-MODE: urls -> endpoint, secrets -> secret.

## Invocation

```bash
jsluice urls -i app.js ; jsluice secrets -i app.js
```
> Confirm exact flags against the installed version before wiring.

**Multi-mode tool.** Each mode produces a different entity type and writes a separate typed output file:
- `urls->endpoint`
- `secrets->secret`

## Inputs / outputs

- **Consumes:** `js_file, url`
- **Produces:** `url, secret, endpoint` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `jsluice.url.jsonl`, `jsluice.secret.jsonl`, `jsluice.endpoint.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/jsluice/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `js_file` key.
