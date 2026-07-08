"""FastAPI read API + SSE + auth-gated scan control for the UI layer.

Thin HTTP wiring over the pure helpers in :mod:`recontool.api.data`. Serves:

  GET  /health                      open liveness check
  GET  /scans                       list scans
  POST /scans                       start a scan (auth; active requires authorize_active)
  GET  /scans/{id}                  overview (counts + queue/recursion stats)
  GET  /scans/{id}/assets           assets (filter by ?type=, paginated)
  GET  /scans/{id}/findings         findings
  GET  /scans/{id}/queue            WorkQueue / recursion-depth view
  GET  /scans/{id}/graph            nodes + edges for the graph front-end
  GET  /scans/{id}/events           Server-Sent Events: live queue progress

SECURITY: every route except /health requires a bearer token
(``Authorization: Bearer <RECON_API_TOKEN>``). If no token is configured the API
refuses (503) rather than exposing data. The server binds to 127.0.0.1 by default
— do not expose it publicly without a token and a TLS-terminating reverse proxy.
This is an authorized-recon control surface; treat access as privileged.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import threading
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from recontool.api import data
from recontool.config import settings


class ScanRequest(BaseModel):
    seed: str
    seed_type: str = "domain"
    profile: str = "normal"
    tools: str = "default"
    authorize_active: bool = False
    max_depth: int = 3
    workers: int = 8
    noise_control: bool = False
    wildcard_filter: bool = False


def _require_auth(authorization: str = Header(default="")) -> None:
    """Constant-time bearer-token check. Default-deny if no token configured."""
    token = settings.api_token
    if not token:
        raise HTTPException(
            status_code=503,
            detail="API disabled: set RECON_API_TOKEN to enable authenticated access.",
        )
    if not hmac.compare_digest(authorization or "", f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="missing or invalid bearer token")


def _start_scan_thread(req: ScanRequest, scan_id: str) -> None:
    """Run a scan in its own thread+event loop so the API stays responsive."""
    from recontool.engine.worker import run_queue_scan

    def _run() -> None:
        asyncio.run(run_queue_scan(
            req.seed, seed_type=req.seed_type, profile_name=req.profile,
            tools=req.tools, workers=req.workers,
            authorize_active=req.authorize_active,
            noise_control=req.noise_control, wildcard_filter=req.wildcard_filter,
            max_depth=req.max_depth, scan_id=scan_id,
        ))

    threading.Thread(target=_run, name=f"scan-{scan_id}", daemon=True).start()


def create_app() -> FastAPI:
    app = FastAPI(title="Recontool API", version="1.0", docs_url="/docs")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "auth_required": True,
                "auth_configured": bool(settings.api_token)}

    @app.get("/scans")
    def scans(_: None = Depends(_require_auth), limit: int = Query(50, le=500)) -> list:
        return data.list_scans(limit=limit)

    @app.post("/scans", status_code=202)
    def start_scan(req: ScanRequest, _: None = Depends(_require_auth)) -> dict:
        scan_id = uuid.uuid4().hex[:16]
        _start_scan_thread(req, scan_id)
        return {"scan_id": scan_id, "status": "started",
                "active": req.authorize_active, "events": f"/scans/{scan_id}/events"}

    @app.get("/scans/{scan_id}")
    def overview(scan_id: str, _: None = Depends(_require_auth)) -> dict:
        out = data.scan_overview(scan_id)
        if out is None:
            raise HTTPException(status_code=404, detail="scan not found")
        return out

    @app.get("/scans/{scan_id}/assets")
    def assets(scan_id: str, _: None = Depends(_require_auth),
               type: str | None = Query(None), limit: int = Query(500, le=5000),
               offset: int = Query(0, ge=0)) -> list:
        return data.list_assets(scan_id, atype=type, limit=limit, offset=offset)

    @app.get("/scans/{scan_id}/findings")
    def findings(scan_id: str, _: None = Depends(_require_auth)) -> list:
        return data.list_findings(scan_id)

    @app.get("/scans/{scan_id}/queue")
    def queue(scan_id: str, _: None = Depends(_require_auth)) -> dict:
        return data.queue_stats(scan_id)

    @app.get("/scans/{scan_id}/graph")
    def graph(scan_id: str, _: None = Depends(_require_auth),
              limit: int = Query(2000, le=20000)) -> dict:
        return data.graph(scan_id, limit=limit)

    @app.get("/tools")
    def tools(_: None = Depends(_require_auth),
              runnable_only: bool = Query(False)) -> list:
        """Capability matrix — every tool, what's runnable, what's in `default`."""
        return data.list_tools(runnable_only=runnable_only)

    @app.get("/tools/summary")
    def tools_summary(_: None = Depends(_require_auth)) -> dict:
        return data.tools_summary()

    @app.get("/scans/{scan_id}/events")
    def events(scan_id: str, _: None = Depends(_require_auth)) -> StreamingResponse:
        async def _stream():
            # Poll the WorkQueue and push progress until the scan converges.
            for _i in range(3600):  # ~1h safety cap
                stats = data.queue_stats(scan_id)
                yield f"data: {json.dumps(stats)}\n\n"
                if stats["total_items"] > 0 and not stats["active"]:
                    yield f"event: done\ndata: {json.dumps(stats)}\n\n"
                    return
                await asyncio.sleep(1.0)

        return StreamingResponse(_stream(), media_type="text/event-stream")

    # ── UI front-end ─────────────────────────────────────────────────────────
    # Single self-contained SPA (no CDN / external calls — this is a privileged
    # control surface). The page itself is public; every data route it calls is
    # bearer-gated, and the user pastes the token into the UI.
    _ui = Path(__file__).parent / "static" / "index.html"

    @app.get("/", include_in_schema=False)
    @app.get("/ui", include_in_schema=False)
    def ui() -> FileResponse:
        if not _ui.exists():  # pragma: no cover - UI always bundled in repo
            raise HTTPException(status_code=404, detail="UI not bundled")
        return FileResponse(_ui, media_type="text/html")

    return app
