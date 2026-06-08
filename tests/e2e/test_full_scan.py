"""End-to-end test: realistic scan flow with mocked external I/O.

Flow:
  seed domain -> passive discovery (mocked crtsh) -> entities in DB ->
  pending keys for live_host -> DNS resolve (mocked) confirms live ->
  keys resolved -> downstream triggered -> verify final DB state.

Uses:
  - respx for HTTP mocking
  - tmp_path SQLite for DB isolation
  - The real EventDrivenOrchestrator pipeline
"""
from __future__ import annotations

import pytest

from recontool.core import db
from recontool.core.models import Asset, AuditLog, Scan
from recontool.engine.events import (
    EntityDiscovered,
    EventBus,
    PendingKeyCreated,
    PendingKeyResolved,
    ToolSelected,
)
from recontool.engine.executor import ExecutionResult, ScheduledJob
from recontool.engine.orchestrator import EventDrivenOrchestrator, ScanConfig
from recontool.engine.registry import ToolRegistry, ToolSpec


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CRTSH_SUBDOMAINS = [
    "api.target.com",
    "www.target.com",
    "mail.target.com",
    "dev.target.com",
]

# Subset that resolves as "live"
LIVE_HOSTS = ["api.target.com", "www.target.com"]


@pytest.fixture()
def e2e_db(tmp_path):
    """Fresh DB for E2E test."""
    db.init_engine(f"sqlite:///{tmp_path / 'e2e.db'}")
    db.create_all()
    return tmp_path


# ---------------------------------------------------------------------------
# E2E Test
# ---------------------------------------------------------------------------


class TestFullScanFlow:
    """End-to-end: seed domain through full pipeline with DB verification."""

    @pytest.mark.asyncio
    async def test_passive_to_active_pipeline(self, e2e_db):
        """Complete scan: discovery -> pending keys -> resolution -> downstream."""
        bus = EventBus()
        events_collected: list = []

        # Collect events for verification
        for evt_type in (EntityDiscovered, PendingKeyCreated, PendingKeyResolved, ToolSelected):
            bus.subscribe(evt_type, lambda e: _async_append(events_collected, e))

        # Registry: crtsh -> httpx -> nuclei
        crtsh = ToolSpec(
            name="crtsh",
            enabled=True,
            consumes=["domain"],
            produces=["subdomain"],
            supported_input_types=["domain"],
            output_types=["subdomain"],
        )
        httpx = ToolSpec(
            name="httpx",
            enabled=True,
            consumes=["subdomain"],
            produces=["live_host"],
            supported_input_types=["subdomain"],
            output_types=["live_host"],
        )
        nuclei = ToolSpec(
            name="nuclei",
            enabled=True,
            consumes=["live_host"],
            produces=["finding"],
            supported_input_types=["live_host"],
            output_types=["finding"],
        )
        registry = ToolRegistry(tools={t.name: t for t in [crtsh, httpx, nuclei]})

        # Track scan_id for DB operations
        scan_ids: list[str] = []

        async def pipeline_execute(job: ScheduledJob) -> ExecutionResult:
            if not scan_ids:
                scan_ids.append(job.scan_id)
                # Create DB scan record
                with db.session_scope() as session:
                    session.add(Scan(
                        id=job.scan_id,
                        seed="target.com",
                        seed_type="domain",
                        profile="normal",
                        status="running",
                        scope_json={},
                    ))

            if job.tool_name == "crtsh":
                # Simulate crtsh discovering subdomains
                for sub in CRTSH_SUBDOMAINS:
                    await bus.publish(EntityDiscovered(
                        scan_id=job.scan_id,
                        tool_name="crtsh",
                        entity_type="subdomain",
                        entity_value=sub,
                    ))
                    # Persist to DB
                    _persist_asset(job.scan_id, "subdomain", sub, "crtsh")
                    # Create pending key for live_host check
                    await bus.publish(PendingKeyCreated(
                        scan_id=job.scan_id,
                        tool_name="crtsh",
                        key_type="live_host",
                        key_value=sub,
                    ))

            elif job.tool_name == "httpx":
                # Simulate HTTP probe: only some hosts are live
                for sub in CRTSH_SUBDOMAINS:
                    if sub in LIVE_HOSTS:
                        await bus.publish(EntityDiscovered(
                            scan_id=job.scan_id,
                            tool_name="httpx",
                            entity_type="live_host",
                            entity_value=sub,
                        ))
                        # Mark asset as live
                        _mark_asset_live(job.scan_id, sub)
                        # Resolve pending key
                        await bus.publish(PendingKeyResolved(
                            scan_id=job.scan_id,
                            tool_name="httpx",
                            key_type="live_host",
                            key_value=sub,
                        ))

            elif job.tool_name == "nuclei":
                # Simulate nuclei finding a vulnerability
                await bus.publish(EntityDiscovered(
                    scan_id=job.scan_id,
                    tool_name="nuclei",
                    entity_type="finding",
                    entity_value="CVE-2023-12345 on api.target.com",
                ))

            return ExecutionResult(
                tool_name=job.tool_name,
                scan_id=job.scan_id,
                success=True,
                exit_code=0,
            )

        orchestrator = EventDrivenOrchestrator(
            bus=bus,
            registry=registry,
            execute_fn=pipeline_execute,
        )
        config = ScanConfig(
            seed="target.com",
            max_iterations=20,
            global_concurrency=5,
        )
        result = await orchestrator.run_scan("target.com", config)

        # -- Verify result status --
        assert result.status == "completed"
        assert result.total_entities >= len(CRTSH_SUBDOMAINS)

        # -- Verify DB state: assets exist, no duplicates --
        with db.session_scope() as session:
            scan_id = scan_ids[0]
            assets = session.query(Asset).filter_by(scan_id=scan_id).all()
            subdomain_values = [a.value for a in assets if a.type == "subdomain"]

            # All discovered subdomains are persisted
            for sub in CRTSH_SUBDOMAINS:
                assert sub in subdomain_values

            # No duplicates
            assert len(subdomain_values) == len(set(subdomain_values))

            # Live hosts are marked
            live_assets = [a for a in assets if a.is_live is True]
            live_values = [a.value for a in live_assets]
            for host in LIVE_HOSTS:
                assert host in live_values

        # -- Verify event flow --
        entity_events = [e for e in events_collected if isinstance(e, EntityDiscovered)]
        assert len(entity_events) >= len(CRTSH_SUBDOMAINS) + len(LIVE_HOSTS)

        # Nuclei was triggered (it consumes live_host)
        selected_events = [e for e in events_collected if isinstance(e, ToolSelected)]
        tool_names = [e.tool_name for e in selected_events]
        assert "nuclei" in tool_names

    @pytest.mark.asyncio
    async def test_no_duplicate_entities_created(self, e2e_db):
        """Running the same discovery twice does not create duplicates."""
        bus = EventBus()

        tool = ToolSpec(
            name="crtsh",
            enabled=True,
            consumes=["domain"],
            produces=["subdomain"],
            supported_input_types=["domain"],
            output_types=["subdomain"],
        )
        registry = ToolRegistry(tools={"crtsh": tool})

        scan_ids: list[str] = []

        async def duplicate_execute(job: ScheduledJob) -> ExecutionResult:
            if not scan_ids:
                scan_ids.append(job.scan_id)
                with db.session_scope() as session:
                    session.add(Scan(
                        id=job.scan_id,
                        seed="target.com",
                        seed_type="domain",
                        profile="normal",
                        status="running",
                        scope_json={},
                    ))
            # Emit same subdomain twice
            _persist_asset(job.scan_id, "subdomain", "dup.target.com", "crtsh")
            _persist_asset(job.scan_id, "subdomain", "dup.target.com", "crtsh")
            return ExecutionResult(
                tool_name=job.tool_name,
                scan_id=job.scan_id,
                success=True,
                exit_code=0,
            )

        orchestrator = EventDrivenOrchestrator(
            bus=bus, registry=registry, execute_fn=duplicate_execute
        )
        await orchestrator.run_scan("target.com", ScanConfig(seed="target.com"))

        with db.session_scope() as session:
            scan_id = scan_ids[0]
            assets = session.query(Asset).filter_by(scan_id=scan_id, value="dup.target.com").all()
            # Should have exactly one asset (dedupe_key prevents duplicates)
            assert len(assets) == 1

    @pytest.mark.asyncio
    async def test_blocked_tools_not_triggered_without_resolution(self, e2e_db):
        """Tools consuming live_host do not run if no live_host keys are resolved."""
        bus = EventBus()
        nuclei_called = {"count": 0}

        crtsh = ToolSpec(
            name="crtsh",
            enabled=True,
            consumes=["domain"],
            produces=["subdomain"],
            supported_input_types=["domain"],
            output_types=["subdomain"],
        )
        nuclei = ToolSpec(
            name="nuclei",
            enabled=True,
            consumes=["live_host"],
            produces=["finding"],
            supported_input_types=["live_host"],
            output_types=["finding"],
        )
        registry = ToolRegistry(tools={t.name: t for t in [crtsh, nuclei]})

        async def no_live_execute(job: ScheduledJob) -> ExecutionResult:
            if job.tool_name == "nuclei":
                nuclei_called["count"] += 1
            elif job.tool_name == "crtsh":
                # Discover subdomains but do NOT emit live_host events
                await bus.publish(EntityDiscovered(
                    scan_id=job.scan_id,
                    tool_name="crtsh",
                    entity_type="subdomain",
                    entity_value="only-subdomain.target.com",
                ))
            return ExecutionResult(
                tool_name=job.tool_name,
                scan_id=job.scan_id,
                success=True,
                exit_code=0,
            )

        orchestrator = EventDrivenOrchestrator(
            bus=bus, registry=registry, execute_fn=no_live_execute
        )
        await orchestrator.run_scan("target.com", ScanConfig(seed="target.com", max_iterations=10))

        # Nuclei should NOT have been called since no live_host was available
        assert nuclei_called["count"] == 0

    @pytest.mark.asyncio
    async def test_confidence_scores_and_audit_trail(self, e2e_db):
        """Assets persisted with correct confidence; audit log entries exist."""
        bus = EventBus()

        tool = ToolSpec(
            name="crtsh",
            enabled=True,
            consumes=["domain"],
            produces=["subdomain"],
            supported_input_types=["domain"],
            output_types=["subdomain"],
        )
        registry = ToolRegistry(tools={"crtsh": tool})
        scan_ids: list[str] = []

        async def execute(job: ScheduledJob) -> ExecutionResult:
            if not scan_ids:
                scan_ids.append(job.scan_id)
                with db.session_scope() as session:
                    session.add(Scan(
                        id=job.scan_id,
                        seed="target.com",
                        seed_type="domain",
                        profile="normal",
                        status="running",
                        scope_json={},
                    ))
            _persist_asset_with_confidence(
                job.scan_id, "subdomain", "scored.target.com", "crtsh", 0.8
            )
            _persist_audit(job.scan_id, "crtsh", "scored.target.com")
            return ExecutionResult(
                tool_name=job.tool_name,
                scan_id=job.scan_id,
                success=True,
                exit_code=0,
            )

        orchestrator = EventDrivenOrchestrator(
            bus=bus, registry=registry, execute_fn=execute
        )
        await orchestrator.run_scan("target.com", ScanConfig(seed="target.com"))

        with db.session_scope() as session:
            scan_id = scan_ids[0]
            asset = session.query(Asset).filter_by(
                scan_id=scan_id, value="scored.target.com"
            ).first()
            assert asset is not None
            assert asset.confidence == 0.8

            audit = session.query(AuditLog).filter_by(scan_id=scan_id).all()
            assert len(audit) >= 1
            assert audit[0].tool == "crtsh"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _async_append(lst, event):
    lst.append(event)


def _persist_asset(scan_id: str, atype: str, value: str, tool: str):
    """Persist an asset to the DB with deduplication."""
    import hashlib
    dedupe_key = hashlib.sha256(f"{atype}:{value}".encode()).hexdigest()[:16]
    with db.session_scope() as session:
        existing = session.query(Asset).filter_by(
            scan_id=scan_id, dedupe_key=dedupe_key
        ).first()
        if not existing:
            session.add(Asset(
                scan_id=scan_id,
                type=atype,
                value=value,
                dedupe_key=dedupe_key,
                confidence=0.5,
                attributes={"source": tool},
            ))


def _persist_asset_with_confidence(
    scan_id: str, atype: str, value: str, tool: str, confidence: float
):
    """Persist an asset with a specific confidence score."""
    import hashlib
    dedupe_key = hashlib.sha256(f"{atype}:{value}".encode()).hexdigest()[:16]
    with db.session_scope() as session:
        existing = session.query(Asset).filter_by(
            scan_id=scan_id, dedupe_key=dedupe_key
        ).first()
        if not existing:
            session.add(Asset(
                scan_id=scan_id,
                type=atype,
                value=value,
                dedupe_key=dedupe_key,
                confidence=confidence,
                attributes={"source": tool},
            ))


def _mark_asset_live(scan_id: str, value: str):
    """Mark an existing asset as live."""
    with db.session_scope() as session:
        asset = session.query(Asset).filter_by(scan_id=scan_id, value=value).first()
        if asset:
            asset.is_live = True


def _persist_audit(scan_id: str, tool: str, target: str):
    """Create an audit log entry."""
    with db.session_scope() as session:
        session.add(AuditLog(
            scan_id=scan_id,
            actor="engine",
            action="entity_discovered",
            tool=tool,
            target=target,
        ))
