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
import re
import shutil
from typing import Any

from recontool.adapters.base import Adapter, AdapterContext, Event
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


def _scope_ok(rule: dict, value: str, seed_domain: str | None) -> bool:
    sf = rule.get("scope_filter")
    if not sf or not seed_domain:
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
        for item in lst:
            v = str(item).strip().lstrip("*.").lower()
            if v and _scope_ok(rule, v, seed_domain):
                out.append(Event.asset(tool, rule.get("type", "subdomain"), v))
        return out

    if entity == "asset":
        v = render_template(rule.get("value", ""), rec).strip()
        if not v:
            return out
        if rule.get("type") in ("subdomain", "domain"):
            v = v.lstrip("*.").lower()
        if _scope_ok(rule, v, seed_domain):
            out.append(Event.asset(tool, rule.get("type", "subdomain"), v))
    elif entity == "service":
        host = render_template(rule.get("host", ""), rec).strip()
        port = str(render_template(rule.get("port", ""), rec)).strip()
        if host and port.isdigit():
            out.append(Event.service(tool, host, int(port),
                                     product=render_template(rule.get("product", ""), rec) or None))
    elif entity == "endpoint":
        url = render_template(rule.get("url", ""), rec).strip()
        if url:
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


def _input_values(ctx: AdapterContext, consumes: tuple[str, ...], cap: int) -> list[str]:
    vals: list[str] = []
    for ctype in consumes:
        vals.extend(ctx.seeds_of(ctype))
    seen, out = set(), []
    for v in vals:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out[:cap]


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
        inputs = _input_values(ctx, self.consumes, cap=spec.get("max_inputs", 100))
        sem = asyncio.Semaphore(max(2, ctx.profile.per_host_concurrency * 4))

        async def one(v: str) -> list[Event]:
            iv = re.sub(r"[^0-9]", "", v) if (self.consumes and self.consumes[0] == "asn") else v
            extra = {"value": iv, "domain": iv, "ip": iv, "asn": iv, "host": iv, "key": key}
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
            cap = spec.get("max_records")
            if cap:
                recs = recs[: int(cap)]   # bound large API result sets
            return emit_events(spec["parse"], recs, spec["name"], seed)

        # PARALLEL fan-out across inputs (bounded by profile concurrency + rate limiter)
        batches = await asyncio.gather(*(one(v) for v in inputs))
        return [e for batch in batches for e in batch]


class GenericCliAdapter(Adapter):
    spec: dict = {}

    def available(self, ctx: AdapterContext) -> bool:
        binary = self.spec.get("binary")
        return bool(binary) and shutil.which(binary) is not None

    async def run(self, ctx: AdapterContext) -> list[Event]:
        spec = self.spec
        seed = _seed_domain(ctx)
        inputs = _input_values(ctx, self.consumes, cap=spec.get("max_inputs", 50))
        sem = asyncio.Semaphore(max(2, ctx.profile.global_concurrency or 10))

        use_stdin = bool(spec.get("stdin"))

        async def one(v: str) -> list[Event]:
            cmd = render_template(spec["invocation"], {},
                                  {"value": v, "domain": v, "ip": v, "host": v})
            async with sem:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd.split(),
                        stdin=asyncio.subprocess.PIPE if use_stdin else None,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    out, _ = await asyncio.wait_for(
                        proc.communicate(input=v.encode() if use_stdin else None),
                        timeout=spec.get("timeout", 120))
                except Exception:  # noqa: BLE001
                    return []
            text = out.decode(errors="ignore")
            ctx.artifacts.save_text(spec["name"], f"{v}.out", text)
            recs = parse_records(spec["parse"], text)
            cap = spec.get("max_records")
            if cap:
                recs = recs[: int(cap)]   # bound firehose tools (gau/waybackurls)
            return emit_events(spec["parse"], recs, spec["name"], seed)

        # PARALLEL fan-out across inputs (bounded by profile concurrency)
        batches = await asyncio.gather(*(one(v) for v in inputs))
        return [e for batch in batches for e in batch]


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
