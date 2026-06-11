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
    export: Path = typer.Option(None, "--export", "-o", help="Write full JSON results here."),
):
    """Run a recon scan on SEED."""
    if profile not in PROFILES:
        console.print(f"[red]Unknown profile {profile!r}. Choose: {list(PROFILES)}[/red]")
        raise typer.Exit(1)

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
    max_iterations: int = typer.Option(50, "--max-iterations",
                                       help="hard cap on scheduling iterations (convergence guard)."),
    max_depth: int = typer.Option(3, "--max-depth", help="max recursion depth from the seed."),
    export: Path = typer.Option(None, "--export", "-o", help="Write full JSON results here."),
):
    """Run the EVENT-DRIVEN recursive engine (parallel, convergence-based).

    Unlike `scan` (linear P1→P6), tools fire as soon as their inputs exist and
    every discovery re-feeds the frontier until no eligible tools remain.
    """
    if profile not in PROFILES:
        console.print(f"[red]Unknown profile {profile!r}. Choose: {list(PROFILES)}[/red]")
        raise typer.Exit(1)

    from recontool.engine.runner import run_engine_scan

    console.print(Panel.fit(
        f"[bold]Recontool engine[/bold]  seed=[cyan]{seed}[/cyan]  "
        f"type=[cyan]{seed_type}[/cyan]  profile=[yellow]{profile}[/yellow]  "
        f"depth≤{max_depth}  iters≤{max_iterations}",
        title="engine", border_style="blue",
    ))

    with console.status("[bold]running event-driven scan…[/bold]"):
        result = asyncio.run(run_engine_scan(
            seed, seed_type=seed_type, profile_name=profile,
            max_iterations=max_iterations, max_depth=max_depth,
        ))

    # Persist a Scan row so the run shows up in `recontool scans` / `report`.
    create_all()
    with session_scope() as s:
        if not s.get(Scan, result.scan_id):
            s.add(Scan(id=result.scan_id, seed=seed, seed_type=seed_type,
                       profile=profile, status=result.status, scope_json="{}",
                       active_authorized=False))

    console.print(
        f"\n[bold]tools run:[/bold] {result.total_tools_run}   "
        f"[bold]entities:[/bold] {result.total_entities}   "
        f"[bold]status:[/bold] {result.status}   "
        f"[bold]elapsed:[/bold] {result.duration_ms} ms"
    )
    if result.errors:
        console.print(f"[dim]{len(result.errors)} tool errors (first 3): "
                      f"{'; '.join(result.errors[:3])}[/dim]")

    _print_summary(result.scan_id)
    _print_findings(result.scan_id)

    if export:
        path = rpt.export_json(result.scan_id, export)
        console.print(f"\n[green]Exported[/green] full results → {path}")
    console.print(f"\nScan id: [bold cyan]{result.scan_id}[/bold cyan] "
                  f"(artifacts in {settings.artifact_dir}/{result.scan_id})")


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
