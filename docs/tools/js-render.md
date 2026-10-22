# js-render

> Provenance: **novel built-in** (next-gen live data source) · slug `js-render` · runnable.

**Purpose.** Render a live host/URL in a headless browser and capture the
application surface a *static* crawl cannot see: the XHR/fetch/GraphQL requests the
page actually makes, routes injected by client-side JS, and secrets in dynamically
loaded bundles. Feeds real endpoints + new subdomains + secret findings back into
the recursive engine.

| Field | Value |
|-------|-------|
| Classification | **active** (renders the target) |
| Integration | cli (`python -m recontool.tools.jsrender <url>`) |
| Consumes (canonical) | `live_host, url, subdomain` |
| Produces (canonical) | `url, subdomain, finding` (secrets emitted as findings) |
| Status | **wired** — `config/tools_generic.yaml` (`js-render`) |
| Engine | works in both the event engine and the multi-worker queue |

## Why it's the differentiator

Classic recon maps hosts/ports/static URLs. Modern apps build their real surface
in the browser — API calls, GraphQL, SPA routes, tokens in JS bundles. `js-render`
captures that dynamic layer and recurses on it, turning "list of live hosts" into
"map of the actual application."

## Invocation

```bash
python -m recontool.tools.jsrender https://app.example.com/
# JSONL: {"type":"url"|"subdomain"|"secret","value":...}
```

Renders with **Playwright** (`pip install playwright && playwright install chromium`)
when available; **degrades gracefully** to a static fetch (loses dynamic-only
signals) so the pipeline never hard-fails without a browser.

## Inputs / outputs

- **Consumes:** `live_host, url, subdomain`
- **Produces:** `url` → endpoints, `subdomain` → assets (scope-filtered),
  `secret` → high-severity findings. Normalized per [`../D3-data-schema.md`](../D3-data-schema.md).
- **Typed output files:** `js-render.url.jsonl`, `js-render.subdomain.jsonl`, `js-render.finding.jsonl`
- **Raw output:** `artifacts/<scan_id>/raw/js-render/`.

## Notes

The extraction (`recontool.tools.jsrender.analyze`) is pure and unit-tested
(`tests/atomic/test_jsrender.py`); only the render step touches a browser/network.
The spec uses conditional `when:` emit so one tool maps its mixed JSONL output to
three entity types.
