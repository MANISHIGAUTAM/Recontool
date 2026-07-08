# Tool-install fixes (apply to Dockerfile + install_tools.sh when the file lock clears)

Diagnosed 2026-06-13: 15 curated tools skipped as "missing binary". Root causes +
fixes (all validated live in an overlay image — see docker/Dockerfile.toolfixes):

1. PATH — pipx installs to /root/.local/bin, which is NOT on PATH, so sslyze,
   wafw00f, waymore, arjun, paramspider, trufflehog3 were installed-but-invisible.
   FIX (Dockerfile ENV): `ENV PATH="/root/.local/bin:${PATH}"`  ← unlocks 6 tools.

2. gitleaks go-install path moved. install_tools.sh uses
   github.com/gitleaks/gitleaks/v8 but the module declares itself as
   github.com/zricethezav/gitleaks/v8.
   FIX: `go install github.com/zricethezav/gitleaks/v8@latest`

3. amass — `github.com/owasp-amass/amass/v4/...@master` fails to build.
   FIX: `go install github.com/owasp-amass/amass/v4/cmd/amass@latest`

4. Data deps (masked-by-mount note): config/resolvers.txt (trickest) and
   config/fingerprints.json (EdOverflow can-i-take-over-xyz) created on the host
   so the ./config mount exposes them to puredns/massdns/subjack. Add the curl
   fetches to install_tools.sh:install_resources (resolvers URL works; the old
   haccer/subjack fingerprints URL 404s — use EdOverflow's).

STILL MISSING (hard, niche/redundant — skip cleanly):
- kr (kiterunner): not cleanly `go install`-able; routes-small.kite URL 404s.
- theHarvester: heavy pip build deps fail in-image.
- graphw00f: bare script repo, no pip package / console script.

The ~190 INVENTORY tools that skip are web UIs / paid-API services (Shodan,
Censys, VirusTotal, Maltego, …) — not installable binaries; they need API keys or
are GUI/web-only. Not in scope for "install the binary".
