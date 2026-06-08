"""Main event loop and priority queue processing for the event-driven engine.

This is the heart of the new architecture. Instead of sequential phases, every
discovery immediately triggers downstream actions via a priority queue. The loop
processes events until the ConvergenceDetector signals that no new unique results
are being found.
"""
from __future__ import annotations

import asyncio
import heapq
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import select

from recontool.adapters.base import Adapter, AdapterContext, Event
from recontool.adapters.registry import adapters_for, all_adapters, load_builtin
from recontool.config import settings
from recontool.core.artifacts import ArtifactStore
from recontool.core.db import create_all, session_scope
from recontool.core.mode import RunMode
from recontool.core.models import Asset, AuditLog, DeadLetter, Scan
from recontool.core.scope import Scope, apex_domain, classify_seed
from recontool.engine.ai_decision import AIDecisionLayer
from recontool.engine.convergence import ConvergenceDetector
from recontool.engine.events import (
    EngineEvent,
    EventType,
    HandlerRegistry,
    build_default_registry,
)
from recontool.engine.log_analyzer import LogAnalyzer
from recontool.engine.priority import PriorityScorer
from recontool.engine.scheduler import Scheduler
from recontool.engine.state import ScanState, ScanStateMachine
from recontool.net.http_client import HttpClient
from recontool.net.proxy_pool import ProxyPool
from recontool.net.rate_limiter import RateLimiter
from recontool.normalize.engine import Normalizer


def _cat_num(category: str) -> int:
    m = re.search(r"(\d+)", category or "")
    return int(m.group(1)) if m else 0


@dataclass(order=True)
class PrioritizedEvent:
    """Wrapper for events in the priority queue (lower score = higher priority)."""

    priority: float
    sequence: int = field(compare=True)
    event: EngineEvent = field(compare=False)


@dataclass
class EngineResult:
    """Result of an event-driven scan."""

    scan_id: str
    seed: str
    seed_type: str
    profile: str
    mode: str = "live"
    events_processed: int = 0
    adapters_run: int = 0
    total_entities: int = 0
    elapsed: float = 0.0
    converged: bool = False
    state_history: list[dict] = field(default_factory=list)


class EventDrivenEngine:
    """Event-driven graph expansion engine.

    Replaces the phased pipeline with a continuous event loop where every
    discovery immediately triggers downstream actions via a priority queue.
    Uses all existing infrastructure (adapters, normalizer, cache, queue, etc.)
    but dispatches them reactively instead of sequentially.
    """

    def __init__(
        self,
        supervisor: Any = None,
        mode: RunMode | None = None,
        mock_env: Any = None,
        convergence_config: dict[str, Any] | None = None,
    ) -> None:
        self.supervisor = supervisor
        self.mode = mode or settings.run_mode
        self.mock_env = mock_env

        # Engine components
        self.scorer = PriorityScorer()
        conv_cfg = convergence_config or {}
        self.convergence = ConvergenceDetector(
            max_dry_runs=conv_cfg.get("max_dry_runs", 10),
            stale_timeout=conv_cfg.get("stale_timeout", 120.0),
            depth_limit=conv_cfg.get("depth_limit", 5),
            max_entities=conv_cfg.get("max_entities", 10000),
        )
        self.log_analyzer = LogAnalyzer()
        self.scheduler = Scheduler()
        self.registry = build_default_registry()
        self.state_machine = ScanStateMachine()
        self.ai_decision = AIDecisionLayer(
            log_analyzer=self.log_analyzer,
            supervisor=supervisor,
        )

        # Priority queue: list of PrioritizedEvent (min-heap, lower = higher priority)
        self._queue: list[PrioritizedEvent] = []
        self._sequence: int = 0
        self._seen_entities: set[str] = set()

        # Pipeline-level cache
        from recontool.cache import ResultCache
        self._cache = ResultCache.create(settings.redis_url)

    async def run(
        self,
        seed: str,
        *,
        profile_name: str | None = None,
        authorize_active: bool = False,
        categories: set[int] | None = None,
        stream: Callable | None = None,
        timeout: float = 0,
    ) -> EngineResult:
        """Run an event-driven scan.

        Args:
            seed: Target domain/IP/CIDR/ASN.
            profile_name: Rate profile name.
            authorize_active: Allow active scanning.
            categories: Category filter (None = all).
            stream: Callback for live events.
            timeout: Max scan time in seconds (0 = unlimited).
        """
        self._categories = categories
        self._emit = stream
        self._authorize_active = authorize_active

        create_all()
        load_builtin()

        profile = settings.profile() if not profile_name else __import__(
            "recontool.config", fromlist=["PROFILES"]
        ).PROFILES.get(profile_name, settings.profile())

        seed_type = classify_seed(seed)
        scope = self._build_scope(seed, seed_type)
        scan_id = uuid.uuid4().hex[:16]

        # Demo/test mode mock environment
        mock_env = self.mock_env
        if self.mode.uses_mock and mock_env is None:
            from recontool.testing.mock_env import MockEnv
            apex = apex_domain(seed) if seed_type in ("domain", "subdomain", "url") else seed
            mock_env = MockEnv(apex=apex)

        # Shared infrastructure
        proxies = ProxyPool(settings.proxies, strategy=settings.proxy_strategy)
        limiter = RateLimiter(default_rate=profile.requests_per_second)
        from recontool.net.circuit import BudgetLedger, CircuitRegistry
        circuits = CircuitRegistry(failure_threshold=5, cooldown=30.0)
        budget = BudgetLedger()
        http = HttpClient(
            profile=profile, proxy_pool=proxies, limiter=limiter,
            mode=self.mode, mock_env=mock_env,
            circuits=circuits, budget=budget,
        )
        artifacts = ArtifactStore(scan_id)

        api_keys = {
            k: settings.api_key(k) for k in
            ("SHODAN_API_KEY", "VIRUSTOTAL_API_KEY", "SECURITYTRAILS_API_KEY",
             "GITHUB_TOKEN", "CENSYS_API_ID", "CENSYS_API_SECRET", "CHAOS_API_KEY",
             "NETLAS_API_KEY", "GREYNOISE_API_KEY", "LEAKIX_API_KEY", "URLSCAN_API_KEY",
             "FULLHUNT_API_KEY", "CRIMINALIP_API_KEY", "CERTSPOTTER_API_KEY", "IPINFO_TOKEN")
        }

        # Create scan record
        with session_scope() as s:
            s.add(Scan(
                id=scan_id, seed=seed, seed_type=seed_type, profile=profile.name,
                status="running", scope_json=scope.to_json(), mode=self.mode.value,
                active_authorized=authorize_active,
            ))
            s.add(AuditLog(
                scan_id=scan_id, action="scan.start",
                target=seed, profile=profile.name,
                detail={"engine": "event_driven", "scope": scope.to_json(),
                        "authorize_active": authorize_active, "mode": self.mode.value},
            ))

        # Emit scan start
        if stream:
            stream("scan_start", scan_id=scan_id, seed=seed)

        # Seed the initial asset
        self._seed_asset(scan_id, seed, seed_type, scope)

        # Build adapter context factory
        def make_ctx(inputs: dict[str, list[str]]) -> AdapterContext:
            return AdapterContext(
                scan_id=scan_id, scope=scope, profile=profile, http=http,
                artifacts=artifacts, inputs=inputs, api_keys=api_keys,
            )

        # Transition to running
        self.state_machine.transition(ScanState.RUNNING)

        # Seed initial events from the seed asset
        self._emit_seed_events(seed, seed_type)

        # Main event loop
        result = EngineResult(
            scan_id=scan_id, seed=seed, seed_type=seed_type,
            profile=profile.name, mode=self.mode.value,
        )

        start_time = time.time()
        deadline = start_time + timeout if timeout > 0 else float("inf")

        while self.state_machine.is_active and self._queue:
            # Check timeout
            if time.time() > deadline:
                break

            # Check convergence
            if self.convergence.is_globally_converged():
                if self.state_machine.state == ScanState.RUNNING:
                    self.state_machine.transition(ScanState.CONVERGING)
                # Give it one more pass then stop
                if not self._queue:
                    break
                self.state_machine.transition(ScanState.DONE)
                result.converged = True
                break

            # Pop highest priority event
            p_event = heapq.heappop(self._queue)
            event = p_event.event

            # Get adapters to dispatch for this event
            candidate_adapters = self.registry.get_adapters_for(event)
            if not candidate_adapters:
                continue

            # Filter by what actually exists in the adapter registry
            available = all_adapters()
            real_adapters = [a for a in candidate_adapters if a in available]
            if not real_adapters:
                # Fall back: dispatch ALL adapters that consume this entity type
                real_adapters = self._find_adapters_for_event(event, available)

            if not real_adapters:
                continue

            # AI decision layer
            decision = await self.ai_decision.decide(event, real_adapters)
            if not decision.should_process:
                continue
            if decision.adapters_to_run:
                real_adapters = [a for a in decision.adapters_to_run if a in available]

            # Filter by category if specified
            if self._categories:
                real_adapters = [
                    a for a in real_adapters
                    if _cat_num(getattr(available[a], "category", "")) in self._categories
                ]

            # Filter active adapters if not authorized
            if not authorize_active:
                real_adapters = [
                    a for a in real_adapters
                    if not getattr(available[a], "is_active", False)
                ]

            if not real_adapters:
                continue

            # Dispatch adapters in parallel via scheduler
            inputs = self._gather_inputs(scan_id, scope)
            # Add the event's specific value to inputs
            inputs = self._enrich_inputs(inputs, event)
            ctx = make_ctx(inputs)

            tasks = []
            for adapter_name in real_adapters:
                if self.log_analyzer.should_skip(adapter_name):
                    continue
                cls = available[adapter_name]
                inst = cls()
                if not inst.available(ctx):
                    continue

                async def _run_adapter(inst=inst, name=adapter_name):
                    return await self._execute_adapter(
                        inst, name, ctx, scan_id, scope, event,
                    )

                tasks.append(
                    self.scheduler.submit(adapter_name, _run_adapter())
                )

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                result.adapters_run += len(tasks)

            result.events_processed += 1

        # Done
        if not self.state_machine.is_done:
            if self.state_machine.state == ScanState.CONVERGING:
                self.state_machine.transition(ScanState.DONE)
            elif self.state_machine.state == ScanState.RUNNING:
                self.state_machine.transition(ScanState.DONE)
            result.converged = self.convergence.is_globally_converged()

        result.elapsed = time.time() - start_time
        result.total_entities = len(self._seen_entities)
        result.state_history = self.state_machine.history()

        # Update scan record
        with session_scope() as s:
            scan = s.get(Scan, scan_id)
            if scan:
                scan.status = "done"
                import datetime as _dt
                scan.finished_at = _dt.datetime.now(_dt.timezone.utc)
            s.add(AuditLog(
                scan_id=scan_id, action="scan.finish",
                detail={
                    "engine": "event_driven",
                    "events_processed": result.events_processed,
                    "adapters_run": result.adapters_run,
                    "converged": result.converged,
                    "convergence": self.convergence.stats(),
                },
            ))

        return result

    async def _execute_adapter(
        self,
        inst: Adapter,
        name: str,
        ctx: AdapterContext,
        scan_id: str,
        scope: Scope,
        source_event: EngineEvent,
    ) -> None:
        """Execute a single adapter and process its output events."""
        t0 = time.time()
        if self._emit:
            self._emit(
                "adapter_start", tool=name,
                category=getattr(inst, "category", ""),
                active=getattr(inst, "is_active", False),
            )

        try:
            adapter_timeout = float(getattr(ctx.profile, "adapter_timeout", 0) or 180)
            events = await asyncio.wait_for(inst.run(ctx), timeout=adapter_timeout)
            duration = round(time.time() - t0, 2)

            if self._emit:
                self._emit(
                    "adapter_done", tool=name,
                    events=len(events), duration=duration,
                )

            self.log_analyzer.record_success(name, len(events), duration)

            # Normalize events into the DB
            new_entities = self._normalize_events(events, scan_id, scope)

            # Record for convergence tracking
            branch_id = source_event.branch_id or "root"
            self.convergence.record_attempt(
                branch_id, new_entities, source_event.depth,
            )

            # Emit new events for each discovery
            self._emit_downstream_events(
                events, new_entities, name, source_event, scope,
            )

        except Exception as exc:  # noqa: BLE001
            duration = round(time.time() - t0, 2)
            self.log_analyzer.record_failure(name, duration)
            if self._emit:
                self._emit(
                    "adapter_error", tool=name,
                    error=str(exc)[:200], duration=duration,
                )
            with session_scope() as s:
                s.add(DeadLetter(
                    scan_id=scan_id, tool=name,
                    error=str(exc)[:2000],
                    payload={"event_type": source_event.type.value},
                ))

    def _normalize_events(
        self, events: list[Event], scan_id: str, scope: Scope
    ) -> list[str]:
        """Normalize adapter events into the DB and return new entity keys."""
        if not events:
            return []

        new_entities: list[str] = []
        BATCH_SIZE = 2000
        for i in range(0, len(events), BATCH_SIZE):
            batch = events[i:i + BATCH_SIZE]
            with session_scope() as s:
                norm = Normalizer(s, scan_id, scope=scope)
                counts = norm.ingest(batch)
                # Track new entities
                for ev in batch:
                    if ev.entity == "asset":
                        key = f"{ev.data.get('type')}:{ev.data.get('value')}"
                        if key not in self._seen_entities:
                            self._seen_entities.add(key)
                            new_entities.append(key)
        return new_entities

    def _emit_downstream_events(
        self,
        adapter_events: list[Event],
        new_entities: list[str],
        source_adapter: str,
        parent_event: EngineEvent,
        scope: Scope,
    ) -> None:
        """Convert adapter output events into engine events for the queue."""
        for ev in adapter_events:
            engine_event = self._classify_adapter_event(ev, source_adapter, parent_event)
            if engine_event is None:
                continue
            # Only enqueue if entity is in scope
            value = engine_event.value
            if value and not scope.contains(
                ev.data.get("type", "subdomain"), value
            ):
                continue
            # Score and enqueue
            score = self.scorer.score(engine_event)
            self._enqueue(engine_event, score.total)

    def _classify_adapter_event(
        self,
        ev: Event,
        source_adapter: str,
        parent_event: EngineEvent,
    ) -> EngineEvent | None:
        """Classify an adapter Event into an EngineEvent type."""
        if ev.entity == "asset":
            atype = ev.data.get("type", "")
            value = ev.data.get("value", "")
            key = f"{atype}:{value}"
            if key in self._seen_entities:
                return None  # Already processed

            if atype in ("domain", "subdomain"):
                if ev.data.get("is_live"):
                    etype = EventType.HOST_VALIDATED_LIVE
                else:
                    etype = EventType.NEW_SUBDOMAIN
            elif atype == "cert":
                etype = EventType.CERT_SAN_DISCOVERED
            else:
                etype = EventType.NEW_SUBDOMAIN

            return EngineEvent(
                type=etype,
                data={"value": value, "type": atype, **ev.data},
                source_adapter=source_adapter,
                depth=parent_event.depth + 1,
                branch_id=parent_event.branch_id or f"branch_{value}",
                timestamp=time.time(),
            )

        elif ev.entity == "endpoint":
            url = ev.data.get("url", "")
            key = f"endpoint:{url}"
            if key in self._seen_entities:
                return None
            self._seen_entities.add(key)
            return EngineEvent(
                type=EventType.NEW_ENDPOINT,
                data={"value": url, **ev.data},
                source_adapter=source_adapter,
                depth=parent_event.depth + 1,
                branch_id=parent_event.branch_id,
                timestamp=time.time(),
            )

        elif ev.entity == "service":
            port = ev.data.get("port")
            host = ev.data.get("host", "")
            key = f"service:{host}:{port}"
            if key in self._seen_entities:
                return None
            self._seen_entities.add(key)
            return EngineEvent(
                type=EventType.NEW_PORT,
                data={"value": host, "port": port, **ev.data},
                source_adapter=source_adapter,
                depth=parent_event.depth + 1,
                branch_id=parent_event.branch_id,
                timestamp=time.time(),
            )

        elif ev.entity == "finding":
            return EngineEvent(
                type=EventType.NEW_FINDING,
                data={"value": ev.data.get("title", ""), **ev.data},
                source_adapter=source_adapter,
                depth=parent_event.depth + 1,
                branch_id=parent_event.branch_id,
                timestamp=time.time(),
            )

        return None

    def _enqueue(self, event: EngineEvent, score: float) -> None:
        """Add an event to the priority queue (lower priority number = processed first)."""
        # Invert score: higher score = more important = lower priority number
        priority = 1.0 - score
        self._sequence += 1
        heapq.heappush(
            self._queue,
            PrioritizedEvent(priority=priority, sequence=self._sequence, event=event),
        )

    def _emit_seed_events(self, seed: str, seed_type: str) -> None:
        """Generate initial events from the seed."""
        if seed_type in ("domain", "subdomain", "url"):
            apex = apex_domain(seed)
            self._enqueue(
                EngineEvent(
                    type=EventType.NEW_SUBDOMAIN,
                    data={"value": apex, "type": "domain"},
                    source_adapter="seed",
                    depth=0,
                    branch_id="root",
                    timestamp=time.time(),
                ),
                score=1.0,  # Maximum priority for seed
            )
            host = seed.split("://")[-1].split("/")[0]
            if host and host != apex:
                self._enqueue(
                    EngineEvent(
                        type=EventType.NEW_SUBDOMAIN,
                        data={"value": host, "type": "subdomain"},
                        source_adapter="seed",
                        depth=0,
                        branch_id="root",
                        timestamp=time.time(),
                    ),
                    score=0.95,
                )
        elif seed_type == "ip":
            self._enqueue(
                EngineEvent(
                    type=EventType.HOST_VALIDATED_LIVE,
                    data={"value": seed, "type": "ip"},
                    source_adapter="seed",
                    depth=0,
                    branch_id="root",
                    timestamp=time.time(),
                ),
                score=1.0,
            )

    def _find_adapters_for_event(
        self, event: EngineEvent, available: dict[str, type[Adapter]]
    ) -> list[str]:
        """Find adapters that can handle an event based on their consumes field."""
        entity_type = event.data.get("type", "domain")
        result = []
        for name, cls in available.items():
            if entity_type in getattr(cls, "consumes", ()):
                result.append(name)
        return result[:10]  # Limit to prevent explosion

    def _enrich_inputs(
        self, inputs: dict[str, list[str]], event: EngineEvent
    ) -> dict[str, list[str]]:
        """Add the event's specific value to the inputs dict."""
        enriched = dict(inputs)
        entity_type = event.data.get("type", "domain")
        value = event.value
        if value:
            if entity_type not in enriched:
                enriched[entity_type] = []
            if value not in enriched[entity_type]:
                enriched[entity_type] = enriched[entity_type] + [value]
        return enriched

    def _gather_inputs(self, scan_id: str, scope: Scope) -> dict[str, list[str]]:
        """Read current assets from DB as inputs."""
        inputs: dict[str, list[str]] = {}
        with session_scope() as s:
            rows = s.execute(
                select(Asset).where(Asset.scan_id == scan_id)
            ).scalars().all()
            for a in rows:
                if not a.in_scope:
                    continue
                inputs.setdefault(a.type, []).append(a.value)
        return {k: sorted(set(v)) for k, v in inputs.items()}

    def _seed_asset(self, scan_id: str, seed: str, seed_type: str, scope: Scope) -> None:
        """Write seed into the canonical store."""
        events: list[Event] = []
        if seed_type in ("domain", "subdomain", "url"):
            apex = apex_domain(seed)
            events.append(Event.asset("seed", "domain", apex))
            host = seed.split("://")[-1].split("/")[0]
            if host and host != apex:
                events.append(Event.asset("seed", "subdomain", host))
        elif seed_type == "ip":
            events.append(Event.asset("seed", "ip", seed))
        elif seed_type == "cidr":
            events.append(Event.asset("seed", "cidr", seed))
        elif seed_type == "asn":
            events.append(Event.asset("seed", "asn", seed))
        else:
            events.append(Event.asset("seed", "domain", seed))
        with session_scope() as s:
            Normalizer(s, scan_id, scope=scope).ingest(events)

    def _build_scope(self, seed: str, seed_type: str) -> Scope:
        """Build scope from seed + config allowlist."""
        scope = Scope.from_seed(seed, seed_type)
        cfg = settings.scope_allowlist()
        scope.allow_domains |= set(cfg["allow_domains"])
        scope.allow_cidrs += [c for c in cfg["allow_cidrs"] if c not in scope.allow_cidrs]
        scope.allow_asns |= {a.upper() for a in cfg["allow_asns"]}
        scope.deny_domains |= set(cfg["deny_domains"])
        scope.deny_cidrs += [c for c in cfg["deny_cidrs"] if c not in scope.deny_cidrs]
        scope.__post_init__()
        return scope
