# gitlab-subdomains

> Provenance: **suggested_addition** (architecture-review gap closer) · slug `gitlab-subdomains` · NOT in extracted inventory.

**Purpose.** Subdomains referenced across public GitLab projects.

| Field | Value |
|-------|-------|
| Closes gap | Subdomain enum (code) |
| Classification | **passive** |
| Integration | cli |
| Consumes (canonical) | `domain` |
| Produces (canonical) | `subdomain` |
| Status | suggested — wire via `config/tools_generic.yaml` |

## Why it's needed

Same as github-subdomains for the GitLab ecosystem.

## Invocation

```bash
gitlab-subdomains -d <domain> -t $GITLAB_TOKEN
```
> Confirm exact flags against the installed version before wiring.

## Inputs / outputs

- **Consumes:** `domain`
- **Produces:** `subdomain` → normalized to the schema in [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `gitlab-subdomains.subdomain.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/gitlab-subdomains/`.

## Integration checklist

See the `recon-integration-tracker` skill. In short: add a `config/tools_generic.yaml`
spec (consumes/produces/parse.emit + scope_filter), add a fixture parser test, and
confirm the scheduler can select it on an available `domain` key.
