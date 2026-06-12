"""Recontool CLI.

    recontool scan www.xyz.com                  # passive recon (safe, default)
    recontool scan acme.com --profile stealth --authorize-active   # full pipeline
    recontool tools                              # show available tools/adapters
    recontool scans                              # list past scans
    recontool report <scan_id>                   # show a stored scan summary
    recontool export <scan_id> -o out.json       # export full results
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

from recontool import report as rpt
from recontool.adapters.registry import all_adapters, load_builtin
from recontool.ai.router import ModelRouter
from recontool.ai.supervisor import Supervisor
from recontool.config import PROFILES, settings
from recontool.core.db import create_all, session_scope
from recontool.core.models import Scan
from recontool.orchestrator.pipeline import ReconPipeline

app = typer.Typer(add_completion=False, help="Recontool — AI-supervised recon platform")
console = Console()


def _configure_logging(verbose: int = 0, log_level: str | None = None,
                       *, quiet_level: int = logging.WARNING) -> None:
    """Wire stdlib logging to a Rich handler so engine logs actually print.

    Without this the engine's structured logs (tool start/complete, entity
    discovery, AI decisions) go to a root logger with no handler and vanish.
    Precedence: explicit ``--log-level`` > ``-v`` count > ``quiet_level`` default.
      (no flag) → quiet_level   -v → INFO   -vv → DEBUG
    The ``engine`` command raises ``quiet_level`` to INFO so a plain
    ``recontool engine <seed>`` streams tool/recursion/AI logs by default.
    """
    if log_level:
        level = getattr(logging, log_level.upper(), logging.INFO)
    elif verbose >= 2:
        level = logging.DEBUG
    elif verbose == 1:
        level = logging.INFO
    else:
        level = quiet_level
    handler = RichHandler(console=console, show_time=True, show_path=False,
                          rich_tracebacks=True, markup=False)
    logging.basicConfig(level=level, format="%(message)s",
                        datefmt="[%H:%M:%S]", handlers=[handler], force=True)
    # httpx is chatty at INFO; keep it at WARNING unless DEBUG was asked for.
    if level > logging.DEBUG:
        logging.getLogger("httpx").setLevel(logging.WARNING)


@app.command()
def scan(
    seed: str = typer.Argument(..., help="domain / ip / cidr / asn (e.g. www.xyz.com)"),
    profile: str = typer.Option(settings.profile_name, "--profile", "-p",
                                help="passive_only | stealth | normal | aggressive"),
    authorize_active: bool = typer.Option(
        False, "--authorize-active",
        help="REQUIRED to run active phases that touch the target."),
    no_ai: bool = typer.Option(False, "--no-ai", help="Disable the AI supervisor."),
    category: str = typer.Option(None, "--category", "-c",
                                 help="Comma-separated category numbers to run ONLY (e.g. '2' or '1,2,3')."),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True,
                                help="-v streams per-phase/adapter logs (INFO); -vv adds DEBUG (per HTTP request)."),
    log_level: str = typer.Option(None, "--log-level",
                                  help="explicit log level (DEBUG|INFO|WARNING|ERROR); overrides -v."),
    export: Path = typer.Option(None, "--export", "-o", help="Write full JSON results here."),
):
    """Run a recon scan on SEED."""
    if profile not in PROFILES:
        console.print(f"[red]Unknown profile {profile!r}. Choose: {list(PROFILES)}[/red]")
        raise typer.Exit(1)

    # Stream pipeline/adapter logs on demand (default WARNING keeps the result
    # tables clean; -v shows per-adapter progress, -vv adds per-request DEBUG).
    _configure_logging(verbose, log_level)

    router = ModelRouter() if not no_ai else None
    supervisor = Supervisor(router) if router else None

    console.print(Panel.fit(
        f"[bold]Recontool[/bold]  seed=[cyan]{seed}[/cyan]  profile=[yellow]{profile}[/yellow]  "
        f"active={'[green]yes[/green]' if authorize_active else '[red]no (passive)[/red]'}  "
        f"AI={'on' if (supervisor and router and router.enabled) else 'heuristic'}",
        title="scan", border_style="blue",
    ))

    def progress(phase, running, skipped):
        line = f"[bold]{phase}[/bold] → run: [green]{', '.join(running) or '-'}[/green]"
        if skipped:
            line += f"  | skipped: [dim]{', '.join(skipped)}[/dim]"
        console.print(line)

    pipeline = ReconPipeline(supervisor=supervisor)
    cats = None
    if category:
        cats = {int(c) for c in category.replace(" ", "").split(",") if c.strip().isdigit()}
    result = asyncio.run(pipeline.run(
        seed, profile_name=profile, authorize_active=authorize_active,
        categories=cats, progress=progress,
    ))

    _render_result(result, supervisor)

    if export:
        path = rpt.export_json(result.scan_id, export)
        console.print(f"\n[green]Exported[/green] full results → {path}")
    console.print(f"\nScan id: [bold cyan]{result.scan_id}[/bold cyan] "
                  f"(artifacts in {settings.artifact_dir}/{result.scan_id})")


@app.command()
def engine(
    seed: str = typer.Argument(..., help="domain / ip / cidr / asn (e.g. www.xyz.com)"),
    seed_type: str = typer.Option("domain", "--type", "-t",
                                  help="seed type: domain | subdomain | ip | cidr | asn"),
    profile: str = typer.Option(settings.profile_name, "--profile", "-p",
                                help="passive_only | stealth | normal | aggressive"),
    max_depth: int = typer.Option(3, "--max-depth", "-d",
                                  help="max recursion depth from the seed (how far keys re-feed)."),
    tools: str = typer.Option("default", "--tools",
                              help="tool profile: 'default' (curated) or 'all'/'excessive' (everything runnable)."),
    authorize_active: bool = typer.Option(
        False, "--authorize-active",
        help="DIVE DEEP: unlock active tools (DNS resolve, HTTP probe, port scan, "
             "crawl, vuln). Required to touch the target; passive-only otherwise."),
    workers: int = typer.Option(8, "--workers", "-w",
                                help="concurrent async workers draining the DB queue (scale out with `recontool worker`)."),
    noise_control: bool = typer.Option(
        False, "--noise-control",
        help="drop duplicate / out-of-scope leads before re-feeding (recommended for --tools all)."),
    wildcard_filter: bool = typer.Option(
        False, "--wildcard-filter",
        help="also drop wildcard-DNS subdomains (implies --noise-control; does DNS lookups)."),
    incremental: bool = typer.Option(
        False, "--incremental",
        help="delta-only reruns: skip tools whose exact input already ran in a recent prior scan."),
    verbose: int = typer.Option(
        0, "--verbose", "-v", count=True,
        help="-v shows per-tool/entity/AI logs (INFO); -vv shows DEBUG."),
    log_level: str = typer.Option(
        None, "--log-level",
        help="explicit log level (DEBUG|INFO|WARNING|ERROR); overrides -v."),
    export: Path = typer.Option(None, "--export", "-o", help="Write full JSON results here."),
):
    """Run the EVENT-DRIVEN recursive engine (DB-backed, parallel, convergence-based).

    Unlike `scan` (linear P1→P6), every tool fires as soon as its input key
    exists and every discovered key re-feeds the matrix until nothing new is
    in scope. State lives in the `work_item` queue (the dynamic matrix), so the
    scan is resumable and you can attach more `recontool worker <scan_id>`
    processes on other hosts. `--tools all` runs every runnable tool; pass
    `-v` to watch tool runs, entity discovery, recursion, and AI decisions live.
    """
    if profile not in PROFILES:
        console.print(f"[red]Unknown profile {profile!r}. Choose: {list(PROFILES)}[/red]")
        raise typer.Exit(1)

    # Engine streams its structured logs by default (quiet_level=INFO) so tool
    # runs, entity discovery, enqueue/recursion and AI decisions are visible
    # without any flag. -v adds DEBUG (per-request detail); --log-level overrides.
    _configure_logging(verbose, log_level, quiet_level=logging.INFO)
    create_all()

    # Seed the static half of the matrix (tool_row registry) if it's empty, so
    # the DB always reflects the full catalog before the dynamic queue fills.
    from recontool.inventory.seed_matrix import seed_if_empty
    seeded = seed_if_empty()

    # Surface the AI decisioning mode (model-backed vs deterministic heuristic).
    router = ModelRouter()
    ai_mode = (f"[green]model[/green]:{router.stats()['light_model']}"
               if router.enabled else "heuristic")

    console.print(Panel.fit(
        f"[bold]Recontool engine[/bold]  seed=[cyan]{seed}[/cyan]  "
        f"type=[cyan]{seed_type}[/cyan]  profile=[yellow]{profile}[/yellow]  "
        f"tools=[magenta]{tools}[/magenta]  workers=[green]{workers}[/green]  depth≤{max_depth}\n"
        f"active={'[green]yes[/green]' if authorize_active else '[red]no (passive)[/red]'}  "
        f"AI={ai_mode}  noise={'on' if (noise_control or wildcard_filter) else 'off'}"
        + (f"  [dim](seeded {seeded} tool rows)[/dim]" if seeded else ""),
        title="engine", border_style="blue",
    ))
    if not authorize_active:
        console.print("[dim]passive mode — pass --authorize-active to dive deep "
                      "(resolve/probe/port/crawl/vuln on an AUTHORISED target).[/dim]")

    from recontool.engine.worker import run_queue_scan
    qr = asyncio.run(run_queue_scan(
        seed, seed_type=seed_type, profile_name=profile, tools=tools,
        workers=max(1, workers), authorize_active=authorize_active,
        noise_control=noise_control or wildcard_filter,
        wildcard_filter=wildcard_filter, max_depth=max_depth,
        incremental=incremental,
    ))
    scan_id = qr.scan_id

    console.print(
        f"\n[bold]items processed:[/bold] {qr.items_processed}   "
        f"[bold]completed:[/bold] {qr.completed}   [bold]failed:[/bold] {qr.failed}   "
        + (f"[bold]skipped(incr):[/bold] {qr.skipped}   " if qr.skipped else "")
        + f"[bold]entities:[/bold] {qr.entities}")
    _print_queue_stats(scan_id)

    _print_summary(scan_id)
    _print_findings(scan_id)
    if export:
        path = rpt.export_json(scan_id, export)
        console.print(f"\n[green]Exported[/green] full results → {path}")
    console.print(f"\nScan id: [bold cyan]{scan_id}[/bold cyan] "
                  f"(artifacts in {settings.artifact_dir}/{scan_id})")
    if qr.bundle_path:
        console.print(f"Final bundle: [cyan]{settings.artifact_dir}/{qr.bundle_path}[/cyan]")
    if verbose == 0 and not log_level:
        console.print("[dim]tip: add -v for per-request DEBUG detail, "
                      "--tools all to run every runnable tool.[/dim]")


@app.command()
def worker(
    scan_id: str = typer.Argument(..., help="scan id whose work_item queue to drain"),
    workers: int = typer.Option(8, "--workers", "-w", help="concurrent workers in this process."),
    profile: str = typer.Option(settings.profile_name, "--profile", "-p"),
    tools: str = typer.Option("default", "--tools", help="'default' or 'all'/'excessive'."),
    authorize_active: bool = typer.Option(
        False, "--authorize-active",
        help="unlock active tools (inherits the scan's setting if not passed)."),
    seed: str = typer.Option("", "--seed", help="scope seed (defaults to the scan's seed if known)."),
    seed_type: str = typer.Option("domain", "--type", "-t"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="-v DEBUG detail."),
):
    """Attach extra workers to an existing scan's queue (multi-process / multi-host).

    Point several `recontool worker <scan_id>` processes at the same RECON_DB_URL
    to scale horizontally — items are claimed atomically, so none is run twice.
    """
    if profile not in PROFILES:
        console.print(f"[red]Unknown profile {profile!r}.[/red]")
        raise typer.Exit(1)
    _configure_logging(verbose, quiet_level=logging.INFO)
    create_all()
    with session_scope() as s:
        sc = s.get(Scan, scan_id)
        seed_val = seed or (sc.seed if sc else "")
        seed_t = (sc.seed_type if sc else seed_type) or seed_type
        # Inherit the scan's active authorization unless explicitly overridden.
        authorize_active = authorize_active or bool(sc.active_authorized if sc else False)
    if not seed_val:
        console.print("[red]Unknown scan; pass --seed to set scope.[/red]")
        raise typer.Exit(1)

    from recontool.engine.runner import build_scan_infra, load_engine_registry
    from recontool.engine.worker import WorkerPool

    profile_obj, scope, http, api_keys = build_scan_infra(seed_val, seed_t, profile)
    registry = load_engine_registry(tools, authorize_active=authorize_active)
    pool = WorkerPool(registry, scope=scope, profile=profile_obj, http=http, api_keys=api_keys)
    console.print(f"[bold]worker[/bold] draining queue for [cyan]{scan_id}[/cyan] "
                  f"with {workers} workers  active={'yes' if authorize_active else 'no'}…")
    asyncio.run(pool.run(scan_id, workers=workers))
    console.print(f"[green]done[/green] — processed {pool.processed} items")


@app.command()
def tools():
    """List registered adapters and which are currently available."""
    load_builtin()
    from recontool.adapters.base import AdapterContext  # noqa
    table = Table(title="Adapters", header_style="bold")
    for col in ("Tool", "Phase", "Category", "Active?", "Consumes", "Produces"):
        table.add_column(col)
    for name, cls in sorted(all_adapters().items(), key=lambda kv: getattr(kv[1], "phase", "")):
        table.add_row(
            name, getattr(cls, "phase", "?"), cls.category,
            "[red]active[/red]" if cls.is_active else "[green]passive[/green]",
            ",".join(cls.consumes), ",".join(cls.produces) or "-",
        )
    console.print(table)


@app.command()
def scans():
    """List past scans."""
    create_all()
    with session_scope() as s:
        rows = s.query(Scan).order_by(Scan.created_at.desc()).limit(50).all()
        if not rows:
            console.print("[dim]No scans yet.[/dim]")
            return
        table = Table(title="Scans", header_style="bold")
        for c in ("scan_id", "seed", "type", "profile", "status", "active_auth", "created"):
            table.add_column(c)
        for r in rows:
            table.add_row(r.id, r.seed, r.seed_type, r.profile, r.status,
                          "yes" if r.active_authorized else "no",
                          r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "-")
        console.print(table)


@app.command()
def report(scan_id: str):
    """Show a summary of a stored scan."""
    create_all()
    _print_summary(scan_id)
    _print_findings(scan_id)


@app.command()
def export(scan_id: str, out: Path = typer.Option("recon_export.json", "-o", "--out")):
    """Export full scan results to JSON."""
    create_all()
    path = rpt.export_json(scan_id, out)
    console.print(f"[green]Exported[/green] → {path}")


@app.command()
def serve(
    host: str = typer.Option(None, "--host", help="bind address (default 127.0.0.1)."),
    port: int = typer.Option(None, "--port", help="bind port (default 8088)."),
):
    """Run the API / UI server (read API + SSE live status + scan control).

    Auth: every route except /health requires `Authorization: Bearer
    $RECON_API_TOKEN`. If the token is unset the API starts but refuses data
    (503) — set RECON_API_TOKEN. Binds to localhost by default; expose publicly
    only behind a TLS reverse proxy with the token set.
    """
    try:
        import uvicorn
    except ImportError:
        console.print("[red]The API needs extra deps:[/red] pip install 'fastapi' 'uvicorn'")
        raise typer.Exit(1) from None
    from recontool.api.app import create_app

    create_all()
    bind_host = host or settings.api_host
    bind_port = port or settings.api_port
    if not settings.api_token:
        console.print("[yellow]⚠ RECON_API_TOKEN is not set — all data routes will "
                      "return 503 until you set it.[/yellow]")
    if bind_host not in ("127.0.0.1", "localhost"):
        console.print(f"[yellow]⚠ binding to {bind_host} (non-local). Ensure a bearer "
                      "token + TLS proxy are in place — this is a privileged surface.[/yellow]")
    console.print(f"[bold]Recontool API[/bold] → http://{bind_host}:{bind_port}  "
                  f"(docs at /docs)  auth={'on' if settings.api_token else 'OFF'}")
    uvicorn.run(create_app(), host=bind_host, port=bind_port)


# ── render helpers ───────────────────────────────────────────────────────────
import contextlib  # noqa: E402


@contextlib.contextmanager
def _nullctx():
    """No-op context manager — used to skip the spinner when logs are streaming."""
    yield


def _print_queue_stats(scan_id: str) -> None:
    """Show the work_item queue breakdown and the deepest recursion level reached.

    This is the visible proof that the DB matrix was driven recursively: a
    max-depth > 1 means discovered keys re-fed the queue and spawned new jobs.
    """
    from sqlalchemy import func, select

    from recontool.engine.models import WorkItem

    with session_scope() as s:
        rows = s.execute(
            select(WorkItem.status, func.count(WorkItem.id))
            .where(WorkItem.scan_id == scan_id)
            .group_by(WorkItem.status)
        ).all()
        max_depth = s.execute(
            select(func.max(WorkItem.depth)).where(WorkItem.scan_id == scan_id)
        ).scalar() or 0
        refeed = s.execute(
            select(func.coalesce(func.sum(WorkItem.new_keys_found), 0))
            .where(WorkItem.scan_id == scan_id)
        ).scalar() or 0
        by_depth = s.execute(
            select(WorkItem.depth, func.count(WorkItem.id))
            .where(WorkItem.scan_id == scan_id)
            .group_by(WorkItem.depth).order_by(WorkItem.depth)
        ).all()
    if not rows:
        return
    table = Table(title="WorkQueue (dynamic matrix)", header_style="bold")
    table.add_column("status")
    table.add_column("items", justify="right")
    for st, n in sorted(rows):
        table.add_row(st, str(n))
    console.print(table)
    depth_str = ", ".join(f"d{d}:{n}" for d, n in by_depth)
    console.print(f"[bold]recursion depth reached:[/bold] {max_depth}   "
                  f"[bold]downstream items enqueued:[/bold] {refeed}   "
                  f"[dim]({depth_str})[/dim]")


def _render_result(result, supervisor):
    table = Table(title="Phases", header_style="bold")
    for c in ("Phase", "Ran", "Skipped", "Assets", "Endpoints", "Findings", "Secs", "Note"):
        table.add_column(c, overflow="fold")
    for p in result.phases:
        table.add_row(
            p.phase, ", ".join(p.adapters_run) or "-", ", ".join(p.adapters_skipped) or "-",
            str(p.counts.get("asset", 0)), str(p.counts.get("endpoint", 0)),
            str(p.counts.get("finding", 0)), str(p.duration), p.note or "",
        )
    console.print(table)
    if not result.active_ran and result.gate_reason:
        console.print(f"[yellow]Active phases skipped:[/yellow] {result.gate_reason}")

    _print_summary(result.scan_id)
    _print_findings(result.scan_id)

    if supervisor:
        narrative = asyncio.run(supervisor.final_report(result.scan_id))
        console.print(Panel(narrative, title="AI summary", border_style="magenta"))


def _print_summary(scan_id):
    summ = rpt.summary(scan_id)
    table = Table(title="Asset inventory", header_style="bold")
    table.add_column("type")
    table.add_column("count", justify="right")
    for t, c in sorted(summ["assets_by_type"].items()):
        table.add_row(t, str(c))
    table.add_row("[bold]live[/bold]", str(summ["live_assets"]))
    table.add_row("[bold]services[/bold]", str(summ["services"]))
    table.add_row("[bold]endpoints[/bold]", str(summ["endpoints"]))
    console.print(table)

    top = rpt.top_assets(scan_id, limit=15)
    if top:
        t2 = Table(title="Top assets by confidence", header_style="bold")
        for c in ("type", "value", "conf", "live", "sources"):
            t2.add_column(c)
        for a in top:
            t2.add_row(a["type"], a["value"], str(a["conf"]),
                       str(a["live"]), str(a["sources"]))
        console.print(t2)


def _print_findings(scan_id):
    fs = rpt.findings_list(scan_id)
    if not fs:
        return
    table = Table(title="Findings", header_style="bold")
    for c in ("severity", "kind", "title", "asset", "detector"):
        table.add_column(c, overflow="fold")
    for f in fs:
        color = {"critical": "red", "high": "red", "medium": "yellow"}.get(f["severity"], "white")
        table.add_row(f"[{color}]{f['severity']}[/{color}]", f["kind"], f["title"],
                      f["asset"] or "-", f["detector"])
    console.print(table)


if __name__ == "__main__":
    app()
