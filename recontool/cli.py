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
import sys
from pathlib import Path

import typer
from rich.console import Console
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


@app.command()
def worker(
    concurrency: int = typer.Option(4, "--concurrency", "-n",
                                    help="Number of concurrent task executors."),
    queue_backend: str = typer.Option("auto", "--queue-backend", "-q",
                                      help="Queue backend: auto | redis | memory"),
):
    """Start a queue worker that pulls and executes adapter tasks."""
    from recontool.config import settings
    from recontool.queue import InMemoryQueue, get_queue
    from recontool.queue.worker import TaskWorker, run_worker

    if queue_backend == "auto":
        redis_url = settings.redis_url
    elif queue_backend == "redis":
        redis_url = settings.redis_url
        if not redis_url:
            console.print("[red]RECON_REDIS_URL not set but redis backend requested.[/red]")
            raise typer.Exit(1)
    else:
        redis_url = None

    queue = get_queue(redis_url)
    backend_name = "redis" if redis_url else "memory"
    console.print(Panel.fit(
        f"[bold]Worker[/bold] concurrency=[cyan]{concurrency}[/cyan] "
        f"backend=[yellow]{backend_name}[/yellow]",
        title="worker", border_style="green",
    ))

    run_worker(queue, concurrency=concurrency)
    console.print("[green]Worker exited cleanly.[/green]")


@app.command()
def scan(
    seed: str = typer.Argument(..., help="domain / ip / cidr / asn (e.g. www.xyz.com)"),
    profile: str = typer.Option(settings.profile_name, "--profile", "-p",
                                help="passive_only | stealth | normal | aggressive"),
    mode: str = typer.Option(settings.mode, "--mode", "-m",
                             help="demo | test | live  (demo/test never touch real targets)"),
    authorize_active: bool = typer.Option(
        False, "--authorize-active",
        help="REQUIRED to run active phases that touch the target."),
    no_ai: bool = typer.Option(False, "--no-ai", help="Disable the AI supervisor."),
    resume: str = typer.Option(None, "--resume", help="Resume an existing scan_id."),
    skip_preflight: bool = typer.Option(False, "--skip-preflight",
                                        help="Skip preflight health checks (not recommended)."),
    category: str = typer.Option(None, "--category", "-c",
                                 help="Comma-separated category numbers to run ONLY (e.g. '2' or '1,2,3')."),
    timeout: int = typer.Option(0, "--timeout", "-t",
                                help="Max total scan wall-time in seconds (0 = unlimited)."),
    engine: str = typer.Option("pipeline", "--engine", "-E",
                               help="Engine: pipeline (phased) | event (event-driven)."),
    export: Path = typer.Option(None, "--export", "-o", help="Write full JSON results here."),
    output_dir: Path = typer.Option(None, "--output-dir", "-O",
                                    help="Directory for structured output files (default: output/)."),
):
    """Run a recon scan on SEED."""
    if profile not in PROFILES:
        console.print(f"[red]Unknown profile {profile!r}. Choose: {list(PROFILES)}[/red]")
        raise typer.Exit(1)

    from recontool.core.mode import RunMode
    run_mode = RunMode.parse(mode)

    # ── preflight ───────────────────────────────────────────────────────────
    if not skip_preflight:
        from recontool.preflight import run_preflight
        pf = run_preflight(seed, mode=run_mode, authorize_active=authorize_active)
        _render_preflight(pf)
        if not pf.ok:
            console.print("[red]Preflight failed. Fix errors above or use --skip-preflight.[/red]")
            raise typer.Exit(2)

    router = ModelRouter() if not no_ai else None
    supervisor = Supervisor(router) if router else None

    console.print(Panel.fit(
        f"[bold]Recontool[/bold]  seed=[cyan]{seed}[/cyan]  profile=[yellow]{profile}[/yellow]  "
        f"mode=[magenta]{run_mode.value}[/magenta]  "
        f"active={'[green]yes[/green]' if authorize_active else '[red]no (passive)[/red]'}  "
        f"AI={'on' if (supervisor and router and router.enabled) else 'heuristic'}",
        title="scan", border_style="blue",
    ))

    def progress(phase, running, skipped):
        line = f"[bold]{phase}[/bold] → run: [green]{', '.join(running) or '-'}[/green]"
        if skipped:
            line += f"  | skipped: [dim]{', '.join(skipped)}[/dim]"
        console.print(line)

    def stream(event, **kw):
        # live per-adapter streaming so long scans show continuous progress
        if event == "scan_start":
            _scan_state["scan_id"] = kw.get("scan_id")
        elif event == "adapter_start":
            tag = "[red]active[/red]" if kw.get("active") else "[green]passive[/green]"
            console.print(f"   [cyan]▶[/cyan] {kw['tool']} [{kw.get('category','')}] {tag} …")
        elif event == "adapter_done":
            n = kw.get("events", 0)
            console.print(f"   [green]✔[/green] {kw['tool']} "
                          f"[dim]{kw.get('duration',0)}s[/dim] → {n} events")
        elif event == "adapter_error":
            console.print(f"   [red]✘ {kw['tool']} ERROR[/red] [dim]{kw.get('error','')}[/dim]")
        elif event == "phase_done":
            c = kw.get("counts", {})
            console.print(f"   [bold green]= {kw['phase']} done[/bold green] "
                          f"[dim]{kw.get('duration',0)}s[/dim] "
                          f"assets={c.get('asset',0)} endpoints={c.get('endpoint',0)} "
                          f"services={c.get('service',0)} findings={c.get('finding',0)}")
            # Write intermediate output files after each phase
            if _scan_state.get("scan_id"):
                try:
                    rpt.write_output_files(_scan_state["scan_id"], seed, _output_path)
                except Exception:  # noqa: BLE001
                    pass
        sys.stdout.flush()

    cats = None
    if category:
        cats = {int(c) for c in category.replace(" ", "").split(",") if c.strip().isdigit()}

    # Resolve output directory (default: output/)
    _output_path = output_dir if output_dir else Path("output")
    # Mutable container to hold scan_id once the pipeline starts
    _scan_state: dict = {}

    if engine == "event":
        # ── EVENT-DRIVEN ENGINE ─────────────────────────────────────────────
        from recontool.engine import create_engine

        eng = create_engine(mode=run_mode, supervisor=supervisor)
        console.print("[bold magenta]Engine:[/bold magenta] event-driven (continuous expansion)")

        async def _run_event_engine():
            return await eng.run(
                seed, profile_name=profile, authorize_active=authorize_active,
                categories=cats, stream=stream, timeout=timeout,
            )

        eng_result = asyncio.run(_run_event_engine())

        # Write output files
        out_path = rpt.write_output_files(eng_result.scan_id, seed, _output_path)
        console.print(f"\n[green]Output files written to[/green] {out_path}")

        # Summary table for event engine
        table = Table(title="Event Engine Results", header_style="bold")
        for c in ("Metric", "Value"):
            table.add_column(c)
        table.add_row("Events processed", str(eng_result.events_processed))
        table.add_row("Adapters dispatched", str(eng_result.adapters_run))
        table.add_row("Total entities", str(eng_result.total_entities))
        table.add_row("Converged", str(eng_result.converged))
        table.add_row("Elapsed", f"{eng_result.elapsed:.1f}s")
        console.print(table)

        _print_summary(eng_result.scan_id)
        _print_findings(eng_result.scan_id)

        if export:
            path = rpt.export_json(eng_result.scan_id, export)
            console.print(f"\n[green]Exported[/green] full results -> {path}")
        console.print(f"\nScan id: [bold cyan]{eng_result.scan_id}[/bold cyan] "
                      f"(artifacts in {settings.artifact_dir}/{eng_result.scan_id})")
    else:
        # ── PIPELINE ENGINE (default) ──────────────────────────────────────
        pipeline = ReconPipeline(supervisor=supervisor, mode=run_mode)

        async def _run_with_timeout():
            coro = pipeline.run(
                seed, profile_name=profile, authorize_active=authorize_active,
                categories=cats, progress=progress, stream=stream, resume_scan_id=resume,
            )
            if timeout > 0:
                try:
                    return await asyncio.wait_for(coro, timeout=timeout)
                except asyncio.TimeoutError:
                    console.print(f"[red]Scan timed out after {timeout}s[/red]")
                    # Write partial output even on timeout
                    if _scan_state.get("scan_id"):
                        try:
                            rpt.write_output_files(_scan_state["scan_id"], seed, _output_path)
                            console.print(f"[yellow]Partial results written to {_output_path / seed}[/yellow]")
                        except Exception:  # noqa: BLE001
                            pass
                    raise typer.Exit(3)
            return await coro

        result = asyncio.run(_run_with_timeout())

        # Write final output files
        out_path = rpt.write_output_files(result.scan_id, seed, _output_path)
        console.print(f"\n[green]Output files written to[/green] {out_path}")

        _render_result(result, supervisor)

        if export:
            path = rpt.export_json(result.scan_id, export)
            console.print(f"\n[green]Exported[/green] full results -> {path}")
        console.print(f"\nScan id: [bold cyan]{result.scan_id}[/bold cyan] "
                      f"(artifacts in {settings.artifact_dir}/{result.scan_id})")


@app.command()
def preflight(
    seed: str = typer.Argument(None, help="optional seed to validate scope for"),
    mode: str = typer.Option(settings.mode, "--mode", "-m", help="demo | test | live"),
):
    """Run preflight health checks (config, credentials, storage, queues, scope)."""
    from recontool.core.mode import RunMode
    from recontool.preflight import run_preflight
    pf = run_preflight(seed, mode=RunMode.parse(mode))
    _render_preflight(pf)
    raise typer.Exit(0 if pf.ok else 2)


@app.command(name="config-validate")
def config_validate(
    env: str = typer.Option("live", "--env", "-e", help="demo | test | live"),
):
    """Validate provider configs (config/providers.yaml) for the given environment.

    Fails (exit 2) if an enabled provider is missing its required secret (live/test)
    or its mock fixture (demo), or if any block is structurally invalid."""
    from recontool.providers import load_providers, validate_providers
    errors = validate_providers(env)
    reg = load_providers()
    table = Table(title=f"Providers ({env})", header_style="bold")
    for c in ("provider", "family", "enabled", "auth", "secret", "fixture"):
        table.add_column(c, overflow="fold")
    for p in reg.providers:
        pe = p.for_env(env)
        secret = "n/a" if pe.auth_method == "none" else (
            "[green]set[/green]" if pe.has_secret() else
            ("[yellow]optional[/yellow]" if pe.key_optional else "[red]missing[/red]"))
        table.add_row(p.name, p.family, "yes" if pe.enabled else "no",
                      pe.auth_method, secret, pe.mock_fixture or "-")
    console.print(table)
    if errors:
        console.print("[red]Provider config INVALID:[/red]")
        for e in errors:
            console.print(f"  [red]- {e}[/red]")
        raise typer.Exit(2)
    console.print(f"[green]Provider config valid for env={env}[/green] "
                  f"({len(reg.enabled())} enabled, {len(reg.providers)} total)")


@app.command()
def demo(
    seed: str = typer.Argument("recontool.local", help="demo apex (default: recontool.local)"),
    profile: str = typer.Option("normal", "--profile", "-p"),
):
    """Run the full pipeline against the built-in MOCK environment (zero network)."""
    from recontool.core.mode import RunMode
    pipeline = ReconPipeline(mode=RunMode.DEMO)
    console.print(Panel.fit(
        f"[bold]DEMO[/bold] (mock env, no network)  seed=[cyan]{seed}[/cyan]  "
        f"profile=[yellow]{profile}[/yellow]", title="demo", border_style="magenta"))
    result = asyncio.run(pipeline.run(seed, profile_name=profile, authorize_active=True))
    _render_result(result, None)
    console.print(f"\nScan id: [bold cyan]{result.scan_id}[/bold cyan]")


@app.command(name="replay-fixtures")
def replay_fixtures(
    provider: str = typer.Option(None, "--provider", help="validate one provider's fixture"),
):
    """Load + validate provider mock fixtures (the recorded-fixture replay command)."""
    from recontool.providers import load_providers
    from recontool.testing.fixtures import list_fixtures, load_fixture
    reg = load_providers()
    table = Table(title="Provider fixtures", header_style="bold")
    for c in ("provider", "fixture", "status"):
        table.add_column(c, overflow="fold")
    targets = [p for p in reg.providers if (not provider or p.name == provider)]
    bad = 0
    for p in targets:
        if not p.mock_fixture:
            table.add_row(p.name, "-", "[yellow]none[/yellow]")
            continue
        try:
            load_fixture(p.mock_fixture)
            table.add_row(p.name, p.mock_fixture, "[green]ok[/green]")
        except Exception as exc:  # noqa: BLE001
            bad += 1
            table.add_row(p.name, p.mock_fixture, f"[red]{exc}[/red]")
    console.print(table)
    console.print(f"available fixtures on disk: {len(list_fixtures())}")
    raise typer.Exit(2 if bad else 0)


@app.command()
def diff(
    seed: str = typer.Argument(..., help="seed whose two latest scans to diff"),
    old: str = typer.Option(None, "--old", help="explicit old scan_id"),
    new: str = typer.Option(None, "--new", help="explicit new scan_id"),
):
    """Diff two scans of a seed (continuous-monitoring change report)."""
    create_all()
    from recontool.diff import diff_scans, latest_two_scans
    if not (old and new):
        old, new = latest_two_scans(seed)
    if not (old and new):
        console.print("[yellow]Need two scans of this seed to diff.[/yellow]")
        raise typer.Exit(1)
    d = diff_scans(old, new)
    console.print(Panel.fit(f"diff {old} → {new}  changed={d.changed}", border_style="blue"))
    for label, delta in (("assets", d.assets), ("endpoints", d.endpoints),
                         ("services", d.services), ("findings", d.findings)):
        if delta.changed:
            console.print(f"[bold]{label}[/bold]: "
                          f"[green]+{len(delta.added)}[/green] "
                          f"[red]-{len(delta.removed)}[/red]")
            for a in delta.added[:10]:
                console.print(f"  [green]+ {a}[/green]")
            for r in delta.removed[:10]:
                console.print(f"  [red]- {r}[/red]")


@app.command()
def replay(scan_id: str = typer.Argument(..., help="scan_id whose dead-letters to inspect")):
    """List dead-lettered units of work for a scan (failed after retries)."""
    create_all()
    from recontool.core.models import DeadLetter
    with session_scope() as s:
        rows = s.query(DeadLetter).filter(DeadLetter.scan_id == scan_id).all()
        if not rows:
            console.print("[green]No dead-letters — clean run.[/green]")
            return
        table = Table(title="Dead-letter queue", header_style="bold")
        for c in ("tool", "phase", "attempts", "status", "error"):
            table.add_column(c, overflow="fold")
        for r in rows:
            table.add_row(r.tool, r.phase or "-", str(r.attempts), r.status, r.error[:80])
        console.print(table)


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


# ── render helpers ───────────────────────────────────────────────────────────
def _render_preflight(pf):
    table = Table(title="Preflight", header_style="bold")
    for c in ("check", "status", "level", "detail"):
        table.add_column(c, overflow="fold")
    for c in pf.checks:
        icon = "[green]PASS[/green]" if c.ok else (
            "[red]FAIL[/red]" if c.level == "error" else "[yellow]WARN[/yellow]")
        table.add_row(c.name, icon, c.level, c.detail)
    console.print(table)


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
