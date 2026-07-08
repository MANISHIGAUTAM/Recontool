"""DNS permutation with a mandatory resolve-gate (dnsgen).

Tool: ProjectAnte/dnsgen — https://github.com/ProjectAnte/dnsgen
  Invocation (from the official README):
      dnsgen domains.txt
    or, equivalently, via stdin:
      cat domains.txt | dnsgen -
  Output: ONE generated candidate hostname per line on stdout, plain text.
  (We use the file-argument form so we can write our scoped seed list to a
  tempfile and pass its path.)

WHY THE RESOLVE-GATE IS MANDATORY
---------------------------------
dnsgen emits THOUSANDS of UNRESOLVED candidate names — it permutes the known
subdomains against a wordlist (dev-, -staging, api2, etc.). The vast majority of
those names do NOT exist. If we stored every candidate as a real subdomain we
would flood the graph with non-existent hosts.

So this adapter does two things dnsgen alone never does:
  1. resolves every candidate (socket.gethostbyname in a thread pool, bounded
     concurrency), and
  2. emits Event.asset("subdomain", host) ONLY for candidates that BOTH
     (a) actually resolve AND (b) are in scope.

The pure scope-filter (_in_scope_candidates) is unit-tested without any real
DNS or subprocess; run() layers the live resolve-gate on top — that resolve
step is the flood guard and is exercised only at runtime.
"""
from __future__ import annotations

import asyncio
import os
import socket
import tempfile

from recontool.adapters.base import Adapter, AdapterContext, Event
from recontool.adapters.registry import register
from recontool.core.scope import Scope

# Bound the blast radius. dnsgen explodes: each input subdomain produces many
# permutations, and each permutation costs one DNS lookup in the resolve-gate.
MAX_INPUT_SEEDS = 200       # cap how many known subdomains we feed dnsgen
MAX_CANDIDATES = 5000       # cap how many generated names we will resolve
RESOLVE_CONCURRENCY = 50    # simultaneous in-flight DNS lookups
RESOLVE_TIMEOUT = 3.0       # seconds per candidate lookup
DNSGEN_TIMEOUT = 120.0      # seconds for the whole dnsgen subprocess


@register("p3_enrichment")
class DnsPermute(Adapter):
    """Generate subdomain permutations with dnsgen, keep only the ones that
    actually resolve and are in scope."""

    name = "dnsgen"
    category = "CAT-2"
    # Pure DNS resolution against public resolvers; it does not touch the
    # target's own services, so it is a passive enrichment step.
    is_active = False
    default_on = False
    consumes = ("subdomain",)
    produces = ("subdomain",)

    def available(self, ctx: AdapterContext) -> bool:
        import shutil

        return shutil.which("dnsgen") is not None

    # ------------------------------------------------------------------ pure
    def _in_scope_candidates(self, raw_stdout: str, scope: Scope) -> list[str]:
        """Pure helper: turn dnsgen's raw stdout into a deduped, in-scope list
        of candidate hostnames.

        NOTE: this does NOT resolve anything — it only normalizes, dedupes, and
        scope-filters. run() additionally resolve-gates the survivors so that
        only names that actually resolve are emitted (the flood guard). This
        split lets the test exercise scope handling without real DNS.
        """
        seen: set[str] = set()
        out: list[str] = []
        for line in raw_stdout.splitlines():
            host = line.strip().lower().rstrip(".")
            if not host or host in seen:
                continue
            seen.add(host)
            if scope.contains("subdomain", host):
                out.append(host)
        return out

    # ------------------------------------------------------------------- live
    async def run(self, ctx: AdapterContext) -> list[Event]:
        # 1. Gather known, in-scope subdomains to seed dnsgen.
        known = sorted(
            {
                s.strip().lower()
                for s in ctx.seeds_of("subdomain")
                if s and s.strip() and ctx.scope.contains("subdomain", s.strip())
            }
        )
        if not known:
            return []
        seeds = known[:MAX_INPUT_SEEDS]

        # 2. Write seeds to a tempfile and run dnsgen on it.
        tmp_path: str | None = None
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="dnsgen_", suffix=".txt")
            with os.fdopen(fd, "w") as fh:
                fh.write("\n".join(seeds) + "\n")

            try:
                proc = await asyncio.create_subprocess_exec(
                    "dnsgen", tmp_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                out, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=DNSGEN_TIMEOUT
                )
            except (asyncio.TimeoutError, OSError, Exception):
                # subprocess failed / timed out / binary vanished — fail closed,
                # emit nothing rather than half a candidate set.
                try:
                    if proc.returncode is None:  # type: ignore[possibly-undefined]
                        proc.kill()  # type: ignore[possibly-undefined]
                except Exception:
                    pass
                return []
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        raw_stdout = out.decode(errors="ignore")

        # 3. Pure pass: dedupe + scope-filter the generated candidates, capped.
        candidates = self._in_scope_candidates(raw_stdout, ctx.scope)
        generated = len(candidates)
        candidates = candidates[:MAX_CANDIDATES]

        # 4. THE RESOLVE-GATE: keep only candidates that actually resolve.
        loop = asyncio.get_event_loop()
        sem = asyncio.Semaphore(RESOLVE_CONCURRENCY)
        resolved: list[str] = []

        async def resolve(host: str) -> None:
            async with sem:
                try:
                    await asyncio.wait_for(
                        loop.run_in_executor(None, socket.gethostbyname, host),
                        timeout=RESOLVE_TIMEOUT,
                    )
                except Exception:
                    # NXDOMAIN / timeout / transient failure -> not a real host.
                    return
                resolved.append(host)

        await asyncio.gather(*(resolve(h) for h in candidates))

        # 5. Audit trail: persist a note on generated-vs-resolved counts.
        # (The newer engine exposes a `log_tool_io` helper for this; on this
        # base we record the same generated/resolved accounting via the real
        # ArtifactStore.save_text API so the trail is never silently empty.)
        ctx.artifacts.save_text(
            self.name,
            "resolve_gate.txt",
            (
                f"seeds_fed={len(seeds)} "
                f"generated_in_scope={generated} "
                f"considered={len(candidates)} "
                f"resolved={len(resolved)}\n"
                + "\n".join(sorted(resolved))
            ),
        )

        # 6. Emit ONLY the resolving, in-scope names.
        return [Event.asset(self.name, "subdomain", host) for host in sorted(resolved)]
