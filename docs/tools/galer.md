# galer

> Provenance: wired via `config/tools_generic.d/url-discovery-cli.yaml` · canonical slug `galer`.

**Purpose.** Active headless crawler (Chrome DevTools Protocol). Fetches a live target and extracts URLs from HTML attributes (`src`, `href`, `url`, `action`) and JavaScript-rendered content.

| Field | Value |
|-------|-------|
| Category(s) | URL Discovery (Cat 22, active crawling) |
| Classification | **active** (drives a headless browser against the live target) |
| Integration | cli |
| Cost | free |
| Scale | Medium (per-URL crawl) |
| Pipeline position | p5_deep — deep/active URL discovery |
| Required input | `url` |

## Invocation

```bash
galer -u <url>
```

- `-u, --url`: target URL (or a file of URLs). Source: [README](https://raw.githubusercontent.com/dwisiswant0/galer/master/README.md).
- `-d, --depth`: crawl depth. `-c, --concurrency`: concurrent requests (default 50). `-e, --extension`: extension filter.

Wired contract: `galer -u {value}` (`config/tools_generic.d/url-discovery-cli.yaml`).

## Inputs / outputs

- **Consumes:** `url`.
- **Produces:** `url` (emitted as `endpoint` events).
- **Output format (raw):** plain text, one URL per line, no ANSI color. Source-confirmed: `fmt.Fprintf(writer, "%s\n", u)` with `writer` defaulting to `os.Stdout` in [`internal/runner/runner.go`](https://raw.githubusercontent.com/dwisiswant0/galer/master/internal/runner/runner.go).

## Operational behavior

- **Active scope safety:** galer fetches the live target, so scope is re-checked before egress; discovered URLs are url-scope-filtered downstream via `Scope.contains("url", …)` (see `docs/D6-opsec.md`). `default_on: false` — opt-in only.
- **If the binary is missing:** adapter reports unavailable (graceful skip).
- **If it returns nothing:** treat as empty (valid); do not block chain.
