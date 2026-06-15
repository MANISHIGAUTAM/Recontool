"""Generic, registry-driven adapters.

Instead of hand-coding one Python class per tool (unmaintainable at 500+ tools),
a tool becomes a declarative spec (config/tools_generic.yaml) describing how to
invoke it and how to turn its output into normalized Events. Two generic executors
run those specs:

  * GenericApiAdapter - calls an HTTP endpoint per input, parses the response.
  * GenericCliAdapter - shells out to a binary, parses stdout.

The PARSE engine (parse_records + emit_events) is pure and unit-testable with no
network/subprocess, which is how we validate every wired tool's output mapping.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import shutil
import signal
from typing import Any
from urllib.parse import urlsplit

from recontool.adapters.base import Adapter, AdapterContext, Event, log_tool_io
from recontool.config import settings
from recontool.core.scope import is_subdomain_of

_TOKEN = re.compile(r"\{([a-zA-Z0-9_.]+)\}")


# -- templating + record access ----------------------------------------------
def _get(record: Any, dotted: str) -> Any:
    cur = record
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


def render_template(tmpl: Any, record: dict, extra: dict | None = None) -> Any:
    """Replace {field} / {a.b} tokens using record (then extra). Literals pass through."""
    if not isinstance(tmpl, str) or "{" not in tmpl:
        return tmpl

    def sub(m):
        key = m.group(1)
        val = _get(record, key)
        if val is None and extra:
            val = extra.get(key)
        return "" if val is None else str(val)

    return _TOKEN.sub(sub, tmpl)


# -- parsing raw output into a list of record dicts --------------------------
def parse_records(parse_spec: dict, raw: Any, *, json_obj: Any = None) -> list[dict]:
    fmt = parse_spec.get("format", "json")
    if fmt == "jsonl":
        out = []
        for line in (raw or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
    if fmt == "json":
        obj = json_obj if json_obj is not None else _safe_json(raw)
        lp = parse_spec.get("list_path")
        node = _get(obj, lp) if lp else obj
        if isinstance(node, list):
            return [x if isinstance(x, dict) else {"_value": x} for x in node]
        if isinstance(node, dict):
            return [node]
        return []
    if fmt in ("text", "csv"):
        rx = parse_spec.get("line_regex")
        records = []
        for line in (raw or "").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if rx:
                m = re.match(rx, line)
                if m:
                    records.append(m.groupdict() or {"_value": line})
            elif fmt == "csv":
                cols = parse_spec.get("columns", [])
                parts = line.split(",")
                rec = {c: parts[i] for i, c in enumerate(cols) if i < len(parts)}
                records.append(rec or {"_value": line})
            else:
                records.append({"_value": line})
        return records
    return []


def _safe_json(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return {}


# -- records -> normalized Events --------------------------------------------
def emit_events(parse_spec: dict, records: list[dict], tool: str,
                seed_domain: str | None = None) -> list[Event]:
    events: list[Event] = []
    for rec in records:
        for rule in parse_spec.get("emit", []):
            events.extend(_emit_one(rule, rec, tool, seed_domain))
    return events


# A syntactically valid DNS hostname: dot-separated labels, alpha TLD. Underscore
# is allowed (real records like _dmarc.example.com). Crucially this REJECTS tool
# banner/usage lines that text-parsers would otherwise ingest as hosts — e.g.
# paramspider prints an ASCII-art banner ("_  __", "with <3 by @0xasm0d3us")
# whose lines contain spaces / art characters and never match.
_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9_](?:[a-z0-9_-]{0,62})?\.)+[a-z]{2,63}$")


def _valid_emit(etype: str, value: str) -> bool:
    """Shape-check an emitted value against its declared entity type, so a tool's
    banner / help / progress text can't masquerade as a discovered asset."""
    if not value:
        return False
    if etype in ("subdomain", "domain"):
        return bool(_HOST_RE.match(value))
    if etype in ("url", "live_host"):
        return "://" in value and " " not in value
    if etype == "ip":
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False
    return True


def _accept(etype: str, value: str, rule: dict, seed_domain: str | None) -> bool:
    """Full emit gate: valid shape, in-scope for host types, and any explicit
    rule-level scope_filter. A `subdomain`/`domain` must actually be under the
    seed domain — crawlers/wayback surface external links (apps.apple.com,
    bit.ly, …) that must NOT be stored as subdomains of the target."""
    if not _valid_emit(etype, value):
        return False
    if etype in ("subdomain", "domain") and seed_domain and not is_subdomain_of(value, seed_domain):
        return False
    return _scope_ok(rule, value, seed_domain)


def _scope_ok(rule: dict, value: str, seed_domain: str | None) -> bool:
    sf = rule.get("scope_filter")
    if not sf:
        return True
    if sf == "cidr_size":
        # ASN-level enrichment (ripestat/bgpview) returns a provider's *entire*
        # announced prefix list for shared ASNs (e.g. 5438 blocks for
        # Cloudflare AS13335) -- mostly the CDN's network, not this target's.
        # Drop supernets bigger than a /16-equivalent (>65536 addresses) so
        # the asset graph stays target-plausible; the full list is still in
        # the raw artifact for manual pivoting. Independent of seed_domain.
        try:
            net = ipaddress.ip_network(value, strict=False)
        except ValueError:
            return False
        return (net.max_prefixlen - net.prefixlen) <= 16
    if not seed_domain:
        return True
    if sf == "subdomain":
        return is_subdomain_of(value, seed_domain)
    if sf == "ip":
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            return False
    return True


def _emit_one(rule: dict, rec: dict, tool: str, seed_domain: str | None) -> list[Event]:
    # Conditional emit: a rule with `when: {field: value, ...}` fires only for
    # records matching every condition — lets one tool's mixed JSONL output
    # (e.g. {"type":"url"} vs {"type":"secret"}) map to different entity types.
    when = rule.get("when")
    if when and any(str(_get(rec, f)) != str(v) for f, v in when.items()):
        return []

    entity = rule.get("entity")
    out: list[Event] = []

    if "value_each" in rule:
        lst = _get(rec, rule["value_each"]) or []
        if isinstance(lst, str):
            lst = lst.splitlines()
        etype = rule.get("type", "subdomain")
        for item in lst:
            v = str(item).strip().lstrip("*.").lower()
            if v and _accept(etype, v, rule, seed_domain):
                out.append(Event.asset(tool, etype, v))
        return out

    if entity == "asset":
        v = render_template(rule.get("value", ""), rec).strip()
        if not v:
            return out
        etype = rule.get("type", "subdomain")
        if etype in ("subdomain", "domain"):
            v = v.lstrip("*.").lower()
        if _accept(etype, v, rule, seed_domain):
            out.append(Event.asset(tool, etype, v))
    elif entity == "service":
        host = render_template(rule.get("host", ""), rec).strip()
        port = str(render_template(rule.get("port", ""), rec)).strip()
        if host and port.isdigit():
            out.append(Event.service(tool, host, int(port),
                                     product=render_template(rule.get("product", ""), rec) or None))
    elif entity == "endpoint":
        url = render_template(rule.get("url", ""), rec).strip()
        if url and _valid_emit("url", url):
            out.append(Event.endpoint(tool, url, source=tool))
    elif entity == "finding":
        title = render_template(rule.get("title", "finding"), rec)
        out.append(Event.finding(
            tool, rule.get("kind", "exposure"), title,
            severity=render_template(rule.get("severity", "info"), rec) or "info",
            detector=rule.get("detector", tool),
            asset_value=render_template(rule.get("asset_value", ""), rec) or None,
            cve_id=render_template(rule.get("cve_id", ""), rec) or None,
        ))
    elif entity == "edge":
        src = render_template(rule.get("src", ""), rec).strip().lower()
        dst = render_template(rule.get("dst", ""), rec).strip()
        if src and dst:
            out.append(Event.edge(tool, src, dst, rule.get("rel", "related")))
    return out


# -- shared helpers -----------------------------------------------------------
def _seed_domain(ctx: AdapterContext) -> str | None:
    doms = ctx.seeds_of("domain")
    if doms:
        return doms[0]
    if ctx.scope and ctx.scope.allow_domains:
        return sorted(ctx.scope.allow_domains)[0]
    return None


def _expandable_cidr(value: str, max_host_bits: int = 8) -> bool:
    # Tools that consume `cidr` (mapcidr -> one ip per address, masscan -> port
    # scan) fan out per address in the block. A /24 (256 addrs) is already a
    # full subnet sweep; anything larger risks hanging (an IPv6 /48 is ~2^80
    # addresses) or amplifying one ASN-level enrichment hit into millions of
    # downstream `ip` WorkItems. Oversized blocks are skipped here but remain
    # in the raw artifact for manual follow-up.
    try:
        net = ipaddress.ip_network(value, strict=False)
    except ValueError:
        return False
    return (net.max_prefixlen - net.prefixlen) <= max_host_bits


def _is_ip(v: str) -> bool:
    try:
        ipaddress.ip_address(v)
        return True
    except ValueError:
        return False


def _shape_tokens(value: str) -> dict[str, str]:
    """Render each invocation token in the SHAPE its tool expects, regardless of
    which key type triggered the run.

    The recursion routes a `url` key to host/domain-consuming tools (and vice
    versa via subsumption). Without shaping, a host tool (nmap/dnsx/massdns) fed a
    url key would receive the full ``https://host/path`` as its {host}/{domain}
    target — malformed argv → silent empty output. So:
      * {host}/{domain}/{subdomain}/{live_host} -> the BARE hostname
      * {url} -> a full scheme://host URL (built as https://host if the key is bare)
      * {ip} -> the value if it's an IP, else the host
    """
    v = (value or "").strip()
    if "://" in v:
        parts = urlsplit(v)
        host = parts.hostname or v
        url = v
    else:
        host = v.split("/", 1)[0]
        url = v if _is_ip(v) else f"https://{host}"
    return {
        "value": v, "host": host, "domain": host, "subdomain": host,
        "live_host": host, "url": url, "ip": v if _is_ip(v) else host,
    }


def _kill_proc_group(proc) -> None:
    """SIGKILL the subprocess AND its whole process group.

    CLI tools launched with start_new_session=True lead their own group, so a
    tool that spawns grandchildren (e.g. js-render -> headless Chromium) has all
    of them reaped here — killing only the direct child orphans the browser,
    which then blocks event-loop/interpreter shutdown (the leaked-headless_shell
    deadlock). Fire-and-forget: safe to call during task cancellation.
    """
    if proc is None or proc.returncode is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass


def _input_values(ctx: AdapterContext, consumes: tuple[str, ...]) -> list[str]:
    """All distinct input values a tool should run on. NO cap — every input is
    processed (the old out[:cap] silently SKIPPED inputs beyond max_inputs, i.e.
    dropped recon coverage). Fan-out concurrency/memory is bounded by rotating
    batches in `_fan_out`, not by discarding inputs."""
    vals: list[str] = []
    for ctype in consumes:
        seeds = ctx.seeds_of(ctype)
        if ctype == "cidr":
            # Oversized blocks (e.g. a CDN's IPv6 /48 = 2^80 addrs) are skipped at
            # fan-out — not a coverage cap but a physical-impossibility guard; the
            # full block is preserved in the raw artifact for manual pivoting.
            seeds = [v for v in seeds if _expandable_cidr(v)]
        vals.extend(seeds)
    seen, out = set(), []
    for v in vals:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


async def _fan_out(inputs: list[str], one, batch_size: int) -> list[Event]:
    """Run ``one(v)`` over EVERY input, in rotating batches of ``batch_size``.

    Bounds how many calls (and their buffers) are in flight at once WITHOUT
    dropping any input — the batch is the rotation window, processed back-to-back
    until all inputs are done. Replaces the old `out[:cap]` truncation (which just
    skipped the tail) with batch-and-rotate, honoring 'never trade completeness'.
    """
    out: list[Event] = []
    bs = max(1, batch_size)
    for i in range(0, len(inputs), bs):
        for batch in await asyncio.gather(*(one(v) for v in inputs[i:i + bs])):
            out.extend(batch)
    return out


# -- the two generic executors ------------------------------------------------
class GenericApiAdapter(Adapter):
    spec: dict = {}

    def available(self, ctx: AdapterContext) -> bool:
        key_env = self.spec.get("requires_key")
        # key_optional tools run keyless (lower limits) but use a key if present
        if key_env and not self.spec.get("key_optional"):
            return bool(settings.api_key(key_env))
        return True

    async def run(self, ctx: AdapterContext) -> list[Event]:
        spec = self.spec
        key = settings.api_key(spec["requires_key"]) if spec.get("requires_key") else ""
        bucket = spec.get("bucket", spec["name"])
        seed = _seed_domain(ctx)
        inputs = _input_values(ctx, self.consumes)
        sem = asyncio.Semaphore(max(2, ctx.profile.per_host_concurrency * 4))

        async def one(v: str) -> list[Event]:
            iv = re.sub(r"[^0-9]", "", v) if (self.consumes and self.consumes[0] == "asn") else v
            # Shape host/url/ip tokens correctly; non-host consumed types (cve,
            # cpe, keyword, org, …) get the raw value.
            extra = _shape_tokens(iv)
            for t in self.consumes:
                extra.setdefault(t, iv)
            extra.update({"value": iv, "asn": iv, "key": key})
            url = render_template(spec["endpoint"], {}, extra)
            headers = {}
            for k, val in (spec.get("headers") or {}).items():
                rv = str(render_template(val, {}, extra)).strip()
                # drop empty / scheme-only auth headers (e.g. "Bearer " with no key)
                if not rv or rv.lower() in ("bearer", "basic", "token", "apikey"):
                    continue
                headers[k] = rv
            async with sem:
                try:
                    resp = await ctx.http.get(url, headers=headers or None, bucket=bucket)
                except Exception:  # noqa: BLE001
                    return []
            ctx.artifacts.save_raw(spec["name"], resp.json() if resp.json_ok else resp.text)
            recs = parse_records(spec["parse"],
                                 resp.text, json_obj=resp.json() if resp.json_ok else None)
            # No max_records truncation — every record is emitted; downstream
            # memory is bounded by the worker's event batching, not by dropping.
            return emit_events(spec["parse"], recs, spec["name"], seed)

        # Process ALL inputs in rotating batches (no input dropped); per-call
        # concurrency is further bounded by `sem` + the HTTP rate limiter.
        return await _fan_out(inputs, one, spec.get("max_inputs") or 100)


# Aux data-FILE tokens a CLI invocation may reference -> (settings.resource key,
# install-default path). A tool whose invocation needs one of these but whose file
# is ABSENT would run with a bad path and dump usage/help instead of results
# (the ffuf-without-SecLists bug), so it must skip instead — see missing_aux_file.
_AUX_FILE_TOKENS = {
    "wordlist": ("content_wordlist",
                 "/opt/SecLists/Discovery/Web-Content/raft-medium-directories.txt"),
    "dns_wordlist": ("dns_wordlist",
                     "/opt/SecLists/Discovery/DNS/subdomains-top1million-5000.txt"),
    "resolvers": ("resolvers", "config/resolvers.txt"),
    "fingerprints": ("fingerprints", "config/fingerprints.json"),
    "kite_wordlist": ("kite_wordlist", "/opt/kite/routes-small.kite"),
}


def missing_aux_file(invocation: str) -> str | None:
    """If the invocation references an aux data-file token whose resolved file
    does not exist, return that path (so the caller can skip with a reason);
    else None. Resolution matches `_aux_tokens` so available() and the skip-reason
    logic agree."""
    if not invocation:
        return None
    for tok, (key, default) in _AUX_FILE_TOKENS.items():
        if "{" + tok + "}" in invocation:
            path = settings.resource(key, default)
            if not path or not os.path.exists(path):
                return path or f"{{{tok}}}"
    return None


def _aux_tokens(spec: dict, ctx: AdapterContext) -> dict[str, str]:
    """Resolve the non-entity tokens a CLI invocation may reference — resource
    files (wordlists/resolvers/fingerprints), scan-config scalars (ports/rate/
    threads), and an API key for key-gated CLI tools.

    Resource paths come from settings.resource() (config `resources:` section)
    with image-install defaults, so an operator can point them anywhere without
    touching tools.yaml. Without this, tokens like {resolvers}/{wordlist}/{key}
    render to "" -> malformed argv -> the tool silently produces nothing.
    """
    prof = ctx.profile
    # masscan/naabu want a numeric port spec; map the profile's port_set.
    ports = {"top-100": "1-1000", "top-1000": "1-10000",
             "full": "1-65535"}.get(getattr(prof, "port_set", ""), "1-1000")
    rate = str(max(100, int(getattr(prof, "requests_per_second", 100) * 60)))  # pps for masscan
    threads = str(getattr(prof, "global_concurrency", 20) or 20)
    aux = {
        "resolvers": settings.resource("resolvers", "config/resolvers.txt"),
        "wordlist": settings.resource(
            "content_wordlist",
            "/opt/SecLists/Discovery/Web-Content/raft-medium-directories.txt"),
        "dns_wordlist": settings.resource(
            "dns_wordlist",
            "/opt/SecLists/Discovery/DNS/subdomains-top1million-5000.txt"),
        "fingerprints": settings.resource("fingerprints", "config/fingerprints.json"),
        "kite_wordlist": settings.resource("kite_wordlist", "/opt/kite/routes-small.kite"),
        "ports": ports, "rate": rate, "threads": threads,
    }
    key_env = spec.get("requires_key")
    if key_env:
        aux["key"] = settings.api_key(key_env) or ""
    return {k: v for k, v in aux.items() if v}


class GenericCliAdapter(Adapter):
    spec: dict = {}

    def available(self, ctx: AdapterContext) -> bool:
        binary = self.spec.get("binary")
        if not (binary and shutil.which(binary) is not None):
            return False
        # Key-gated CLI tools (e.g. github-subdomains needs a GitHub token) skip
        # cleanly when the key is absent — same contract as the API adapter, so
        # they log `⊘ skip` instead of running a broken keyless invocation.
        key_env = self.spec.get("requires_key")
        if key_env and not self.spec.get("key_optional") and not settings.api_key(key_env):
            return False
        # A required data file (wordlist/resolvers/…) that doesn't exist would
        # make the tool print usage/help instead of results (ffuf without
        # SecLists) — skip cleanly instead of emitting that garbage.
        if missing_aux_file(self.spec.get("invocation", "")):
            return False
        return True

    async def run(self, ctx: AdapterContext) -> list[Event]:
        spec = self.spec
        seed = _seed_domain(ctx)
        inputs = _input_values(ctx, self.consumes)
        sem = asyncio.Semaphore(max(2, ctx.profile.global_concurrency or 10))

        use_stdin = bool(spec.get("stdin"))

        async def one(v: str) -> list[Event]:
            # Aux tokens (resolvers/wordlist/ports/...) + SHAPE-correct host/url/ip
            # tokens (a host tool fed a url key gets the bare host, a url tool fed a
            # bare host gets https://host) + raw value for any other consumed type.
            extra = dict(_aux_tokens(spec, ctx))
            extra.update(_shape_tokens(v))
            for t in self.consumes:
                extra.setdefault(t, v)
            cmd = render_template(spec["invocation"], {}, extra)
            # stdin tools (dnsx/puredns/massdns read hosts; httpx reads urls) must
            # receive the SHAPED form of their primary input — piping a raw url to
            # a host-reading tool yields nothing.
            stdin_val = extra.get(self.consumes[0], v) if self.consumes else v
            async with sem:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd.split(),
                        stdin=asyncio.subprocess.PIPE if use_stdin else None,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                        start_new_session=True,  # own process group: kill children too
                    )
                except Exception:  # noqa: BLE001
                    return []
                try:
                    out, _ = await asyncio.wait_for(
                        proc.communicate(input=stdin_val.encode() if use_stdin else None),
                        timeout=spec.get("timeout", 1800))
                except asyncio.CancelledError:
                    # Pool shutdown: kill the group (incl. any chromium) and let
                    # cancellation propagate so the loop can close cleanly. We do
                    # NOT await proc.wait() here — awaiting in a cancelled context
                    # re-raises immediately; the SIGKILL + child-watcher reaps it.
                    _kill_proc_group(proc)
                    raise
                except Exception:  # noqa: BLE001
                    # Timeout or any other failure leaves the subprocess (and its
                    # children) running under asyncio.wait_for — kill the whole
                    # group + reap so slow CLI tools / browsers never orphan.
                    # Return [] (not raise) so a single slow input doesn't fail
                    # the tool for the other parallel inputs in this gather.
                    _kill_proc_group(proc)
                    try:
                        await proc.wait()
                    except Exception:  # noqa: BLE001
                        pass
                    return []
            text = out.decode(errors="ignore")
            log_tool_io(spec["name"], v, cmd, text)
            ctx.artifacts.save_text(spec["name"], f"{v}.out", text)
            recs = parse_records(spec["parse"], text)
            # No max_records truncation — a firehose tool (gau/waybackurls) emits
            # every line; the worker's event batching bounds memory, not a cap.
            return emit_events(spec["parse"], recs, spec["name"], seed)

        # Process ALL inputs in rotating batches (no input dropped); per-call
        # concurrency is further bounded by `sem`.
        return await _fan_out(inputs, one, spec.get("max_inputs") or 50)


def build_adapter_class(spec: dict) -> type[Adapter]:
    """Create a registrable Adapter subclass from a declarative spec."""
    base = GenericApiAdapter if spec.get("integration") == "api" else GenericCliAdapter
    attrs = {
        "name": spec["name"],
        "category": f"CAT-{spec.get('category', '?')}",
        "is_active": bool(spec.get("is_active", False)),
        "consumes": tuple(spec.get("consumes", ["domain"])),
        "produces": tuple(spec.get("produces", [])),
        "key_env": spec.get("requires_key"),
        "spec": spec,
    }
    return type(f"Generic_{spec['name']}", (base,), attrs)
