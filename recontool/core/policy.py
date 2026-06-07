"""Policy Engine — scope + authorization + demo/test-mode gate (diagram box C).

Enforces the authorized-only policy at the top of the pipeline, before any source
runs. Three layers:

  1. SCOPE          — is the seed/entity inside the declared scope? (core/scope.Scope)
  2. AUTHORIZATION  — has the operator attested authorization for ACTIVE testing?
  3. MODE           — standard | demo. In `demo` mode, ONLY a fixed allow-list of
                      sanctioned public test targets may be scanned (safe defaults
                      for trying the tool without owning a target).

This replaces ad-hoc gating with one auditable decision point. No evasion logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from recontool.core.scope import Scope, apex_domain, classify_seed

# Public targets explicitly published for scanning/testing. Demo mode is restricted
# to these so the tool can be exercised without an owned/authorized target.
DEMO_ALLOWLIST = {
    "example.com", "example.org", "example.net",      # IANA reserved documentation
    "scanme.nmap.org", "nmap.org",                    # Nmap's sanctioned scan target
    "testphp.vulnweb.com", "vulnweb.com",             # Acunetix public test sites
    "testhtml5.vulnweb.com", "testasp.vulnweb.com", "testaspnet.vulnweb.com",
    "demo.testfire.net",                              # IBM AltoroMutual demo bank
    "juice-shop.herokuapp.com",                       # OWASP Juice Shop demo
    "ginandjuice.shop",                               # PortSwigger demo shop
    "google-gruyere.appspot.com",                     # Google Gruyere training
}


@dataclass
class Decision:
    allowed: bool
    reason: str
    active_allowed: bool = False


@dataclass
class PolicyEngine:
    """Single authorization decision point for the whole run."""

    scope: Scope
    authorized_active: bool = False          # operator attestation for active testing
    mode: str = "standard"                   # standard | demo
    extra_demo_targets: set[str] = field(default_factory=set)

    @classmethod
    def for_seed(cls, seed: str, *, authorized_active: bool = False,
                 mode: str = "standard", extra_demo_targets: set[str] | None = None) -> "PolicyEngine":
        seed_type = classify_seed(seed)
        scope = Scope.from_seed(seed, seed_type)
        return cls(scope=scope, authorized_active=authorized_active, mode=mode,
                   extra_demo_targets=extra_demo_targets or set())

    # ── decisions ────────────────────────────────────────────────────────
    def authorize_seed(self, seed: str) -> Decision:
        """May we begin a run against this seed at all?"""
        seed_type = classify_seed(seed)
        if self.mode == "demo" and not self._demo_ok(seed, seed_type):
            return Decision(False,
                            "demo mode: seed not in the sanctioned test allow-list",
                            active_allowed=False)
        # standard mode trusts the operator's scope + attestation; we still record it.
        return Decision(True, f"authorized ({self.mode} mode)",
                        active_allowed=self.authorized_active)

    def allow_active(self, entity_type: str, value: str) -> Decision:
        """May an ACTIVE (target-touching) check run against this entity?"""
        if not self.authorized_active:
            return Decision(False, "active scanning not authorized (attestation required)")
        if not self.scope.contains(entity_type, value):
            return Decision(False, "entity out of scope")
        if self.mode == "demo" and not self._demo_ok(value, entity_type):
            return Decision(False, "demo mode: entity not in sanctioned test allow-list")
        return Decision(True, "active authorized + in scope", active_allowed=True)

    def in_scope(self, entity_type: str, value: str) -> bool:
        return self.scope.contains(entity_type, value)

    # ── helpers ────────────────────────────────────────────────────────────
    def _allowlist(self) -> set[str]:
        return DEMO_ALLOWLIST | {x.lower() for x in self.extra_demo_targets}

    def _demo_ok(self, value: str, entity_type: str) -> bool:
        host = value
        if "://" in value:
            from urllib.parse import urlsplit
            host = urlsplit(value).hostname or value
        host = host.lower().rstrip(".")
        al = self._allowlist()
        if host in al:
            return True
        # allow subdomains of an allow-listed apex (e.g. *.vulnweb.com)
        apex = apex_domain(host)
        return apex in al or any(host.endswith("." + a) for a in al)

    def to_json(self) -> dict:
        return {"mode": self.mode, "authorized_active": self.authorized_active,
                "scope": self.scope.to_json()}
