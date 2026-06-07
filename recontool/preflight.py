"""Preflight health checks — validate config, credentials, storage, queues, scope.

Run before a scan starts (and standalone via ``recontool preflight``) so failures
are caught early with actionable messages rather than mid-scan. Each check returns
a ``Check`` result; checks never raise. The aggregate ``ok`` is False if any
check with ``level == "error"`` failed.

Implements the spec requirement:
  "preflight health checks for config, credentials, storage, queues, and scope".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from recontool import categories as C
from recontool.config import load_tool_registry, settings
from recontool.core.mode import RunMode


@dataclass
class Check:
    name: str
    ok: bool
    level: str  # "error" | "warn" | "info"
    detail: str = ""


@dataclass
class Preflight:
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks if c.level == "error")

    @property
    def errors(self) -> list[Check]:
        return [c for c in self.checks if c.level == "error" and not c.ok]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.level == "warn" and not c.ok]

    def add(self, name, ok, level="error", detail=""):
        self.checks.append(Check(name, ok, level, detail))

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "checks": [c.__dict__ for c in self.checks],
        }


def run_preflight(seed: str | None = None, *, mode: RunMode | None = None,
                  authorize_active: bool = False) -> Preflight:
    """Run all preflight checks. ``seed`` enables scope validation."""
    pf = Preflight()
    mode = mode or settings.run_mode

    _check_config(pf)
    _check_category_registry(pf)
    _check_tool_registry(pf)
    _check_storage(pf)
    _check_db(pf)
    _check_queue(pf)
    _check_credentials(pf)
    _check_mode(pf, mode, authorize_active)
    if seed:
        _check_scope(pf, seed)
    return pf


# ── individual checks ────────────────────────────────────────────────────────
def _check_config(pf: Preflight) -> None:
    try:
        prof = settings.profile()
        pf.add("config.profile", True, "info",
               f"profile={prof.name} active_enabled={prof.active_enabled}")
    except Exception as exc:  # noqa: BLE001
        pf.add("config.profile", False, "error", f"cannot resolve profile: {exc}")


def _check_category_registry(pf: Preflight) -> None:
    try:
        errs = C.validate()
        if errs:
            pf.add("registry.categories", False, "error",
                   f"{len(errs)} integrity errors: {errs[:3]}")
        else:
            pf.add("registry.categories", True, "info",
                   f"{len(C.load_categories())} categories valid")
    except Exception as exc:  # noqa: BLE001
        pf.add("registry.categories", False, "error", str(exc))


def _check_tool_registry(pf: Preflight) -> None:
    try:
        reg = load_tool_registry()
        ok = len(reg) > 0
        pf.add("registry.tools", ok, "warn" if not ok else "info",
               f"{len(reg)} tool contracts loaded")
    except Exception as exc:  # noqa: BLE001
        pf.add("registry.tools", False, "warn", str(exc))


def _check_storage(pf: Preflight) -> None:
    try:
        d = settings.artifact_dir
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".preflight_write_test"
        probe.write_text("ok")
        probe.unlink()
        pf.add("storage.artifacts", True, "info", f"writable: {d}")
    except Exception as exc:  # noqa: BLE001
        pf.add("storage.artifacts", False, "error",
               f"artifact dir not writable: {exc}")


def _check_db(pf: Preflight) -> None:
    try:
        from sqlalchemy import text

        from recontool.core import db
        db.create_all()
        with db.session_scope() as s:
            s.execute(text("SELECT 1"))
        pf.add("storage.database", True, "info", f"reachable: {settings.db_url.split('://')[0]}")
    except Exception as exc:  # noqa: BLE001
        pf.add("storage.database", False, "error", f"DB not reachable: {exc}")


def _check_queue(pf: Preflight) -> None:
    # Redis is optional; in-process queue is always available.
    if not settings.redis_url:
        pf.add("queue", True, "info", "in-process queue (no Redis configured)")
        return
    try:
        import redis  # type: ignore

        client = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        client.ping()
        pf.add("queue.redis", True, "info", "Redis reachable")
    except Exception as exc:  # noqa: BLE001
        pf.add("queue.redis", False, "warn",
               f"Redis configured but unreachable ({exc}); falling back to in-process")


def _check_credentials(pf: Preflight) -> None:
    # Credentials are all optional (passive recon works with none) -> info/warn only.
    present = []
    for env in ("SHODAN_API_KEY", "CENSYS_API_ID", "VIRUSTOTAL_API_KEY",
                "SECURITYTRAILS_API_KEY", "GITHUB_TOKEN", "URLSCAN_API_KEY"):
        if settings.api_key(env):
            present.append(env)
    pf.add("credentials", True, "info",
           f"{len(present)} provider key(s) present: {', '.join(present) or 'none (passive-only ok)'}")


def _check_mode(pf: Preflight, mode: RunMode, authorize_active: bool) -> None:
    pf.add("mode", True, "info", f"run mode = {mode.value}")
    if mode is RunMode.LIVE and authorize_active:
        pf.add("mode.active", True, "warn",
               "LIVE mode with active scanning authorized — ensure written authorization exists")


def _check_scope(pf: Preflight, seed: str) -> None:
    try:
        from recontool.core.scope import Scope, classify_seed
        st = classify_seed(seed)
        scope = Scope.from_seed(seed, st)
        merged = _merge_config_scope(scope)
        has_allow = bool(merged.allow_domains or merged.allow_cidrs or merged.allow_asns)
        pf.add("scope", has_allow, "error" if not has_allow else "info",
               f"seed={seed} type={st} allow_domains={sorted(merged.allow_domains)} "
               f"allow_cidrs={merged.allow_cidrs}")
    except Exception as exc:  # noqa: BLE001
        pf.add("scope", False, "error", str(exc))


def _merge_config_scope(scope):
    """Merge config-driven scope allowlist into a seed-derived Scope."""
    cfg = settings.scope_allowlist()
    scope.allow_domains |= set(cfg["allow_domains"])
    scope.allow_cidrs += [c for c in cfg["allow_cidrs"] if c not in scope.allow_cidrs]
    scope.allow_asns |= set(a.upper() for a in cfg["allow_asns"])
    scope.deny_domains |= set(cfg["deny_domains"])
    scope.deny_cidrs += [c for c in cfg["deny_cidrs"] if c not in scope.deny_cidrs]
    scope.__post_init__()
    return scope
