"""AI decision layer for the event-driven engine.

Provides intelligent decision-making with LLM integration and heuristic fallback.
When an LLM is available, it advises on which adapters to run, error handling
strategies, and anomaly detection. When unavailable, pure heuristic rules drive
all decisions.

Every decision is logged with reasoning for auditability.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from recontool.engine.events import EngineEvent, EventType
from recontool.engine.log_analyzer import LogAnalyzer


@dataclass
class Decision:
    """A decision about whether/how to process an event."""

    should_process: bool = True
    adapters_to_run: list[str] | None = None  # None = use default handler
    priority_adjustment: float = 0.0
    reason: str = ""


@dataclass
class ErrorDecision:
    """A decision about how to handle an adapter error."""

    action: str = "skip"  # retry | skip | alternative
    alternative_adapter: str | None = None
    retry_delay: float = 0.0
    reason: str = ""


@dataclass
class StrategyAdjustment:
    """Adjustment to scan strategy after a phase completes."""

    explore_deeper: bool = False
    skip_phases: list[str] = field(default_factory=list)
    priority_adapters: list[str] = field(default_factory=list)
    reason: str = ""


@dataclass
class Anomaly:
    """A detected anomaly in scan data."""

    category: str  # internal_ip_leak | staging_exposed | debug_endpoint | sensitive_path | etc.
    severity: str  # critical | high | medium | low | info
    detail: str
    evidence: str


@dataclass
class AIDecisionLog:
    """A logged AI decision with timestamp and reasoning."""

    timestamp: float
    decision_type: str  # error_handling | strategy | anomaly | adapter_selection
    context: str
    decision: str
    reasoning: str


class AIDecisionLayer:
    """Makes intelligent decisions about event processing, error handling,
    strategy adjustment, and anomaly detection.

    When an AI supervisor is available, consults it for complex decisions.
    Falls back to heuristic rules otherwise.
    """

    def __init__(
        self,
        log_analyzer: LogAnalyzer,
        supervisor: Any = None,
        max_depth: int = 5,
        stream: Any = None,
    ) -> None:
        self.log_analyzer = log_analyzer
        self.supervisor = supervisor
        self.max_depth = max_depth
        self._stream = stream
        self._decisions: list[AIDecisionLog] = []
        self._anomalies: list[Anomaly] = []

    @property
    def decisions(self) -> list[AIDecisionLog]:
        """All logged decisions."""
        return list(self._decisions)

    @property
    def anomalies(self) -> list[Anomaly]:
        """All detected anomalies."""
        return list(self._anomalies)

    def _log_decision(
        self, decision_type: str, context: str, decision: str, reasoning: str
    ) -> None:
        """Log a decision and emit it to the stream callback."""
        entry = AIDecisionLog(
            timestamp=time.time(),
            decision_type=decision_type,
            context=context,
            decision=decision,
            reasoning=reasoning,
        )
        self._decisions.append(entry)
        if self._stream:
            self._stream(
                "ai_decision",
                decision_type=decision_type,
                context=context,
                decision=decision,
                reasoning=reasoning,
            )
        from recontool.obs import log_event
        log_event(
            "ai.decision",
            decision_type=decision_type,
            context=context,
            decision=decision,
            reasoning=reasoning,
        )

    async def decide(self, event: EngineEvent, available_adapters: list[str]) -> Decision:
        """Decide how to handle an event.

        Uses heuristic rules (fast) and optionally AI supervision for
        complex decisions.
        """
        # Always apply heuristic rules first
        decision = self._heuristic_decide(event, available_adapters)

        # If AI supervisor is available and decision is ambiguous, consult it
        if self.supervisor and decision.should_process and event.depth >= 3:
            ai_decision = await self._ai_decide(event, available_adapters)
            if ai_decision is not None:
                return ai_decision

        return decision

    def handle_error(
        self,
        adapter_name: str,
        error: str,
        phase: str,
        available_alternatives: list[str] | None = None,
    ) -> ErrorDecision:
        """Decide how to handle an adapter error: retry, skip, or try alternative.

        Uses heuristic rules based on error type and adapter history.
        """
        stats = self.log_analyzer.get_stats(adapter_name)
        alternatives = available_alternatives or []

        # Classify error type
        error_lower = error.lower()
        is_timeout = "timeout" in error_lower or "timed out" in error_lower
        is_rate_limit = "429" in error_lower or "rate limit" in error_lower
        is_auth = "401" in error_lower or "403" in error_lower or "unauthorized" in error_lower
        is_network = "connection" in error_lower or "dns" in error_lower or "resolve" in error_lower

        # Decision logic
        if is_auth:
            decision = ErrorDecision(
                action="skip",
                reason=f"Authentication/authorization error for {adapter_name}; "
                       f"credentials likely invalid or missing",
            )
        elif is_rate_limit:
            decision = ErrorDecision(
                action="retry",
                retry_delay=30.0,
                reason=f"Rate limited on {adapter_name}; will retry after cooldown",
            )
        elif is_timeout and (stats is None or stats.consecutive_failures < 2):
            decision = ErrorDecision(
                action="retry",
                retry_delay=5.0,
                reason=f"Timeout on {adapter_name} (attempt {(stats.consecutive_failures if stats else 0) + 1}); retrying",
            )
        elif is_network and alternatives:
            alt = alternatives[0]
            decision = ErrorDecision(
                action="alternative",
                alternative_adapter=alt,
                reason=f"Network error on {adapter_name}; trying alternative {alt}",
            )
        elif stats and stats.consecutive_failures >= 3:
            decision = ErrorDecision(
                action="skip",
                reason=f"{adapter_name} has {stats.consecutive_failures} consecutive failures; skipping",
            )
        elif alternatives and stats and stats.consecutive_failures >= 2:
            alt = alternatives[0]
            decision = ErrorDecision(
                action="alternative",
                alternative_adapter=alt,
                reason=f"{adapter_name} failed {stats.consecutive_failures} times; trying {alt}",
            )
        elif stats and stats.consecutive_failures < 2:
            decision = ErrorDecision(
                action="retry",
                retry_delay=2.0,
                reason=f"Transient error on {adapter_name}; retrying",
            )
        else:
            decision = ErrorDecision(
                action="skip",
                reason=f"Unrecoverable error on {adapter_name}: {error[:100]}",
            )

        self._log_decision(
            "error_handling",
            f"adapter={adapter_name} phase={phase} error={error[:100]}",
            decision.action,
            decision.reason,
        )
        return decision

    def adjust_strategy(
        self,
        phase: str,
        phase_counts: dict[str, int],
        total_assets: int,
        scan_elapsed: float,
    ) -> StrategyAdjustment:
        """After a phase completes, decide whether to explore deeper or move on.

        Heuristic-based strategy adjustment considering discovery rate and scan progress.
        """
        new_assets = phase_counts.get("asset", 0)
        new_endpoints = phase_counts.get("endpoint", 0)
        new_findings = phase_counts.get("finding", 0)

        # High discovery rate suggests exploring deeper
        discovery_rate = new_assets / max(total_assets, 1)

        if discovery_rate > 0.3 and total_assets < 500:
            adjustment = StrategyAdjustment(
                explore_deeper=True,
                reason=f"High discovery rate ({discovery_rate:.0%}) in {phase}; "
                       f"surface is still growing rapidly",
            )
        elif new_findings > 5:
            adjustment = StrategyAdjustment(
                explore_deeper=True,
                priority_adapters=["nuclei", "httpx", "ffuf"],
                reason=f"Found {new_findings} findings in {phase}; "
                       f"prioritizing vulnerability checks",
            )
        elif new_assets == 0 and new_endpoints == 0:
            # No new discoveries; skip further passive expansion
            skip = []
            if phase in ("p1_seed", "p2_expansion"):
                skip = ["p3_enrichment"]
            adjustment = StrategyAdjustment(
                explore_deeper=False,
                skip_phases=skip,
                reason=f"No new discoveries in {phase}; moving on",
            )
        elif scan_elapsed > 300 and discovery_rate < 0.05:
            adjustment = StrategyAdjustment(
                explore_deeper=False,
                reason=f"Scan running {scan_elapsed:.0f}s with low discovery rate; converging",
            )
        else:
            adjustment = StrategyAdjustment(
                explore_deeper=False,
                reason=f"Normal progression after {phase}",
            )

        self._log_decision(
            "strategy",
            f"phase={phase} new_assets={new_assets} total={total_assets} "
            f"elapsed={scan_elapsed:.0f}s",
            "explore_deeper" if adjustment.explore_deeper else "move_on",
            adjustment.reason,
        )
        return adjustment

    def detect_anomalies(self, data: dict[str, Any]) -> list[Anomaly]:
        """Detect anomalies in discovered data.

        Checks for internal IP leaks, staging environments, debug endpoints,
        sensitive file paths, and other security-relevant patterns.
        """
        anomalies: list[Anomaly] = []

        # Check assets for anomalies
        assets = data.get("assets", [])
        subdomains = data.get("subdomains", [])
        endpoints = data.get("endpoints", [])
        ips = data.get("ips", [])

        # 1. Internal IP addresses leaked
        internal_patterns = [
            r"^10\.\d+\.\d+\.\d+$",
            r"^172\.(1[6-9]|2[0-9]|3[01])\.\d+\.\d+$",
            r"^192\.168\.\d+\.\d+$",
        ]
        for ip in ips:
            for pattern in internal_patterns:
                if re.match(pattern, ip):
                    anomaly = Anomaly(
                        category="internal_ip_leak",
                        severity="high",
                        detail=f"Internal/private IP address discovered: {ip}",
                        evidence=ip,
                    )
                    anomalies.append(anomaly)
                    break

        # 2. Staging/dev environments exposed
        staging_keywords = [
            "staging", "stage", "dev", "development", "test", "qa",
            "uat", "sandbox", "demo", "preview", "canary", "internal",
            "pre-prod", "preprod",
        ]
        for sub in subdomains:
            sub_lower = sub.lower()
            for kw in staging_keywords:
                if kw in sub_lower.split(".")[0]:
                    anomaly = Anomaly(
                        category="staging_exposed",
                        severity="medium",
                        detail=f"Staging/dev subdomain publicly accessible: {sub}",
                        evidence=sub,
                    )
                    anomalies.append(anomaly)
                    break

        # 3. Debug/admin endpoints
        debug_patterns = [
            r"/debug", r"/admin", r"/phpinfo", r"/server-status",
            r"/\.env", r"/\.git", r"/wp-admin", r"/actuator",
            r"/swagger", r"/api-docs", r"/graphql", r"/console",
            r"/elmah\.axd", r"/_profiler", r"/trace",
        ]
        for ep in endpoints:
            ep_lower = ep.lower()
            for pattern in debug_patterns:
                if re.search(pattern, ep_lower):
                    anomaly = Anomaly(
                        category="debug_endpoint",
                        severity="high",
                        detail=f"Debug/admin endpoint exposed: {ep}",
                        evidence=ep,
                    )
                    anomalies.append(anomaly)
                    break

        # 4. Sensitive file paths in discovered data
        sensitive_patterns = [
            r"\.sql$", r"\.bak$", r"\.old$", r"\.backup$",
            r"\.log$", r"\.conf$", r"\.config$", r"\.ini$",
            r"id_rsa", r"\.pem$", r"\.key$", r"\.p12$",
        ]
        for ep in endpoints:
            ep_lower = ep.lower()
            for pattern in sensitive_patterns:
                if re.search(pattern, ep_lower):
                    anomaly = Anomaly(
                        category="sensitive_path",
                        severity="high",
                        detail=f"Sensitive file path discovered: {ep}",
                        evidence=ep,
                    )
                    anomalies.append(anomaly)
                    break

        # 5. Version disclosure in subdomains (e.g. v1.api.example.com)
        version_pattern = r"^v\d+[.-]"
        for sub in subdomains:
            if re.match(version_pattern, sub.split(".")[0]):
                anomaly = Anomaly(
                    category="version_disclosure",
                    severity="low",
                    detail=f"Version-labelled subdomain: {sub}",
                    evidence=sub,
                )
                anomalies.append(anomaly)

        # Log all anomalies
        for anomaly in anomalies:
            self._log_decision(
                "anomaly",
                f"category={anomaly.category} evidence={anomaly.evidence}",
                f"detected [{anomaly.severity}]",
                anomaly.detail,
            )

        self._anomalies.extend(anomalies)
        return anomalies

    def generate_summary(self, scan_id: str, seed: str, phase_results: list[Any]) -> str:
        """Generate an executive summary of all AI decisions made during the scan.

        Uses heuristic text generation (no LLM needed).
        """
        total_decisions = len(self._decisions)
        error_decisions = [d for d in self._decisions if d.decision_type == "error_handling"]
        strategy_decisions = [d for d in self._decisions if d.decision_type == "strategy"]
        anomaly_decisions = [d for d in self._decisions if d.decision_type == "anomaly"]

        lines = [
            f"AI Decision Summary for {seed}",
            f"Scan ID: {scan_id}",
            "=" * 60,
            "",
            f"Total decisions made: {total_decisions}",
            f"  Error handling: {len(error_decisions)}",
            f"  Strategy adjustments: {len(strategy_decisions)}",
            f"  Anomalies detected: {len(anomaly_decisions)}",
            "",
        ]

        # Error handling summary
        if error_decisions:
            retries = sum(1 for d in error_decisions if "retry" in d.decision)
            skips = sum(1 for d in error_decisions if "skip" in d.decision)
            alternatives = sum(1 for d in error_decisions if "alternative" in d.decision)
            lines.append("Error Handling Breakdown:")
            lines.append(f"  Retries: {retries}")
            lines.append(f"  Skips: {skips}")
            lines.append(f"  Alternatives used: {alternatives}")
            lines.append("")

        # Strategy summary
        if strategy_decisions:
            deeper = sum(1 for d in strategy_decisions if "explore_deeper" in d.decision)
            lines.append("Strategy Adjustments:")
            lines.append(f"  Explored deeper: {deeper} times")
            lines.append(f"  Moved on: {len(strategy_decisions) - deeper} times")
            lines.append("")

        # Anomaly summary
        if self._anomalies:
            lines.append("Anomalies Detected:")
            by_severity: dict[str, int] = {}
            for a in self._anomalies:
                by_severity[a.severity] = by_severity.get(a.severity, 0) + 1
            for sev in ("critical", "high", "medium", "low", "info"):
                if sev in by_severity:
                    lines.append(f"  {sev}: {by_severity[sev]}")
            lines.append("")
            lines.append("Top anomalies:")
            # Sort by severity importance
            sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
            sorted_anomalies = sorted(self._anomalies, key=lambda a: sev_order.get(a.severity, 9))
            for a in sorted_anomalies[:10]:
                lines.append(f"  [{a.severity.upper()}] {a.detail}")
            lines.append("")

        # Recommendations
        lines.append("Recommendations:")
        if self._anomalies:
            high_count = sum(1 for a in self._anomalies if a.severity in ("critical", "high"))
            if high_count > 0:
                lines.append(
                    f"  - {high_count} high/critical anomalies require immediate review"
                )
            staging = [a for a in self._anomalies if a.category == "staging_exposed"]
            if staging:
                lines.append(
                    f"  - {len(staging)} staging/dev environments are publicly accessible"
                )
            internal_ips = [a for a in self._anomalies if a.category == "internal_ip_leak"]
            if internal_ips:
                lines.append(
                    f"  - {len(internal_ips)} internal IP addresses are leaking"
                )
        else:
            lines.append("  - No critical anomalies detected")
            lines.append("  - Consider running active phases for deeper coverage")

        return "\n".join(lines) + "\n"

    def format_decisions_log(self) -> str:
        """Format all decisions as a text log suitable for ai_decisions.txt."""
        if not self._decisions:
            return "No AI decisions were made during this scan.\n"

        lines = ["AI Decision Log", "=" * 60, ""]
        for entry in self._decisions:
            import datetime
            ts = datetime.datetime.fromtimestamp(entry.timestamp).strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"[{ts}] {entry.decision_type.upper()}")
            lines.append(f"  Context: {entry.context}")
            lines.append(f"  Decision: {entry.decision}")
            lines.append(f"  Reasoning: {entry.reasoning}")
            lines.append("")

        return "\n".join(lines) + "\n"

    def _heuristic_decide(self, event: EngineEvent, available_adapters: list[str]) -> Decision:
        """Pure heuristic decision-making (no LLM needed)."""
        # Depth limit: stop deep exploration
        if event.depth > self.max_depth:
            return Decision(
                should_process=False,
                reason=f"depth {event.depth} exceeds limit {self.max_depth}",
            )

        # Filter out adapters that should be skipped
        filtered = [
            a for a in available_adapters
            if not self.log_analyzer.should_skip(a)
        ]

        if not filtered:
            return Decision(
                should_process=False,
                reason="all candidate adapters are in skip state",
            )

        # Deprioritize adapters that are underperforming
        priority_adj = 0.0
        deprioritized = [
            a for a in filtered
            if self.log_analyzer.should_deprioritize(a)
        ]
        if len(deprioritized) == len(filtered):
            priority_adj = -0.3  # Lower priority if all adapters are weak

        return Decision(
            should_process=True,
            adapters_to_run=filtered,
            priority_adjustment=priority_adj,
            reason="heuristic",
        )

    async def _ai_decide(self, event: EngineEvent, available_adapters: list[str]) -> Decision | None:
        """Consult AI supervisor for decision (returns None if AI unavailable)."""
        if not self.supervisor or not hasattr(self.supervisor, "plan_phase"):
            return None

        try:
            # Ask supervisor which adapters to keep for this event
            keep = await self.supervisor.plan_phase(
                f"event_{event.type.value}",
                available_adapters,
                event.data.get("scan_id", ""),
            )
            if keep is not None:
                self._log_decision(
                    "adapter_selection",
                    f"event_type={event.type.value} depth={event.depth}",
                    f"keep={keep}",
                    "AI supervisor selected adapters",
                )
                return Decision(
                    should_process=True,
                    adapters_to_run=list(keep),
                    reason="ai_supervisor",
                )
        except Exception:  # noqa: BLE001
            pass
        return None
