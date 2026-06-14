#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Recontool — external tool installer.
#
# Installs the CLI recon tools referenced in config/tools.yaml. Safe to run on a
# fresh Debian/Ubuntu box or inside the Docker image. Idempotent: skips tools
# already on PATH. Each tool is OPTIONAL — Recontool degrades gracefully if a
# tool is missing (the matching adapter just reports unavailable).
#
# Usage:
#   bash docker/install_tools.sh            # install everything
#   bash docker/install_tools.sh core       # only the default-on core set
#   GOBIN=/usr/local/bin bash docker/install_tools.sh
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

SET="${1:-all}"
GOBIN="${GOBIN:-/usr/local/bin}"
export GOBIN GO111MODULE=on
mkdir -p "$GOBIN"

log()  { printf '\033[1;34m[*]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }

have() { command -v "$1" >/dev/null 2>&1; }

# retry <attempts> <cmd...> — run cmd up to N times with linear backoff. Network
# fetches in a Docker build are flaky (rate limits, transient DNS); one attempt
# is why SecLists/gitleaks/etc. intermittently "failed". Returns cmd's status.
retry() {
  local n="$1"; shift; local i=1
  while :; do
    "$@" && return 0
    [ "$i" -ge "$n" ] && return 1
    warn "retry $i/$n failed: $1 …"; sleep $((i * 3)); i=$((i + 1))
  done
}

go_install() {  # go_install <binary> <module@version>
  local bin="$1" mod="$2"
  if have "$bin"; then ok "$bin already installed"; return; fi
  log "go install $mod"
  if retry 3 go install "$mod" 2>/dev/null; then ok "installed $bin"; else warn "failed: $bin"; fi
}

# Like go_install, but for binary names that collide with a non-Go tool of the
# same name already on PATH (e.g. the `httpx` console-script shipped by the
# Python `httpx` HTTP-client library, a recontool dependency installed in an
# earlier layer). have() alone can't tell them apart, so confirm the existing
# binary actually prints `sig` via -version before skipping; otherwise install
# (and overwrite) the real Go tool.
go_install_verified() {  # go_install_verified <binary> <module@version> <version-signature>
  local bin="$1" mod="$2" sig="$3"
  if have "$bin" && "$bin" -version 2>&1 | grep -qi "$sig"; then
    ok "$bin already installed"; return
  fi
  log "go install $mod"
  if retry 3 go install "$mod" 2>/dev/null; then ok "installed $bin"; else warn "failed: $bin"; fi
}

pip_install() { # pip_install <binary> <pkg>
  local bin="$1" pkg="$2"
  if have "$bin"; then ok "$bin already installed"; return; fi
  log "pip install $pkg"
  if retry 3 sh -c "pipx install '$pkg' 2>/dev/null || pip3 install --quiet '$pkg' 2>/dev/null"; then
    ok "installed $bin"; else warn "failed: $bin"; fi
}

apt_install() { # apt_install <binary> <pkg>
  local bin="$1" pkg="$2"
  if have "$bin"; then ok "$bin already installed"; return; fi
  log "apt-get install $pkg"
  if sudo apt-get install -y -q "$pkg" 2>/dev/null || apt-get install -y -q "$pkg" 2>/dev/null; then
    ok "installed $bin"; else warn "failed: $bin"; fi
}

# ── ProjectDiscovery + Go ecosystem (the default-on CORE) ────────────────────
install_core() {
  log "Installing CORE (default-on) tools..."
  go_install subfinder "github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest"
  go_install dnsx      "github.com/projectdiscovery/dnsx/cmd/dnsx@latest"
  go_install_verified httpx "github.com/projectdiscovery/httpx/cmd/httpx@latest" "projectdiscovery"
  go_install naabu     "github.com/projectdiscovery/naabu/v2/cmd/naabu@latest"
  go_install nuclei    "github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest"
  go_install asnmap    "github.com/projectdiscovery/asnmap/cmd/asnmap@latest"
  go_install uncover   "github.com/projectdiscovery/uncover/cmd/uncover@latest"
  go_install gau       "github.com/lc/gau/v2/cmd/gau@latest"
  ok "core done. Updating nuclei templates..."
  have nuclei && nuclei -update-templates -silent 2>/dev/null || true
}

# ── Full ecosystem ───────────────────────────────────────────────────────────
install_all() {
  install_core
  log "Installing EXTENDED tools..."
  # ProjectDiscovery extras
  go_install katana    "github.com/projectdiscovery/katana/cmd/katana@latest"
  go_install tlsx      "github.com/projectdiscovery/tlsx/cmd/tlsx@latest"
  go_install mapcidr   "github.com/projectdiscovery/mapcidr/cmd/mapcidr@latest"
  go_install alterx    "github.com/projectdiscovery/alterx/cmd/alterx@latest"
  go_install cdncheck  "github.com/projectdiscovery/cdncheck/cmd/cdncheck@latest"
  go_install notify    "github.com/projectdiscovery/notify/cmd/notify@latest"
  go_install interactsh-client "github.com/projectdiscovery/interactsh/cmd/interactsh-client@latest"
  # Tomnomnom utilities (glue)
  go_install waybackurls "github.com/tomnomnom/waybackurls@latest"
  go_install anew      "github.com/tomnomnom/anew@latest"
  go_install gf        "github.com/tomnomnom/gf@latest"
  go_install unfurl    "github.com/tomnomnom/unfurl@latest"
  go_install qsreplace "github.com/tomnomnom/qsreplace@latest"
  # Discovery / scanning
  go_install ffuf      "github.com/ffuf/ffuf/v2@latest"
  go_install gowitness "github.com/sensepost/gowitness@latest"
  go_install subjack   "github.com/haccer/subjack@latest"
  go_install puredns   "github.com/d3mondev/puredns/v2@latest"
  go_install s3scanner "github.com/sa7mon/s3scanner@latest"
  go_install cero      "github.com/glebarez/cero@latest"
  go_install jsluice   "github.com/BishopFox/jsluice/cmd/jsluice@latest"
  go_install metabigor "github.com/j3ssie/metabigor@latest"
  go_install github-subdomains "github.com/gwen001/github-subdomains@latest"
  go_install gitleaks  "github.com/zricethezav/gitleaks/v8@latest"
  go_install amass     "github.com/owasp-amass/amass/v4/cmd/amass@latest"
  # Python tools
  pip_install dnsvalidator dnsvalidator
  pip_install wafw00f wafw00f
  pip_install sslyze sslyze
  pip_install waymore waymore
  pip_install paramspider "git+https://github.com/devanshbatham/ParamSpider"
  pip_install arjun arjun
  pip_install theHarvester theHarvester
  pip_install trufflehog3 trufflehog3
  # Playwright powers the js-render live crawler (the next-gen data source).
  # Best-effort: js-render degrades to a static fetch if this is absent.
  if pip3 install --quiet playwright 2>/dev/null; then
    python3 -m playwright install --with-deps chromium 2>/dev/null \
      && ok "playwright + chromium" || warn "playwright installed; chromium fetch failed"
  else
    warn "playwright (optional) skipped"
  fi
  # apt packages
  apt_install nmap nmap
  apt_install masscan masscan
  apt_install whatweb whatweb
  apt_install whois whois

  install_resources
  install_batch_clis
}

# ── massdns (needs build) ─────────────────────────────────────────────────────
install_massdns() {
  if have massdns; then ok "massdns already installed"; return; fi
  log "Building massdns from source..."
  git clone --depth 1 https://github.com/blechschmidt/massdns /tmp/massdns 2>/dev/null \
    && make -C /tmp/massdns >/dev/null 2>&1 \
    && cp /tmp/massdns/bin/massdns "$GOBIN/" && ok "installed massdns" || warn "failed: massdns"
}

# ── SecLists + a clean resolver list + tool data-files ────────────────────────
# Many CLI tools need a DATA dependency, not just a binary: gf needs ~/.gf/*.json
# patterns, subjack needs a fingerprints.json takeover-signature DB, puredns/
# massdns need a trusted resolver list. Without these the tool runs but produces
# nothing. install_resources provisions them and writes paths the {resolvers}/
# {fingerprints} tokens (adapters/generic.py:_aux_tokens) resolve to.
# fetch_url <url> <dest> [maxtime] — resilient single-file download (curl's own
# --retry for transient HTTP + our retry() for total failures); succeeds only if
# the file is non-empty. -L follows GitHub release redirects.
fetch_url() {
  local url="$1" dest="$2" maxtime="${3:-180}"
  [ -s "$dest" ] && return 0
  mkdir -p "$(dirname "$dest")"
  retry 3 curl -fsSL -L --retry 3 --retry-delay 2 --max-time "$maxtime" "$url" -o "$dest" \
    && [ -s "$dest" ]
}

install_resources() {
  log "Fetching resources (wordlists + resolvers + tool data-files)..."

  # SecLists: a FULL clone is ~2.6GB and frequently times out in the build (the
  # recurring 'SecLists clone failed'). Fetch ONLY the wordlists the wired tools
  # reference ({content_wordlist}/{dns_wordlist} in adapters/generic.py, a few MB)
  # via raw URLs with retries; fall back to a shallow full clone only if those
  # fail. Keeps ffuf/gobuster/feroxbuster working without the giant repo.
  local SL="https://raw.githubusercontent.com/danielmiessler/SecLists/master"
  local wc="/opt/SecLists/Discovery/Web-Content/raft-medium-directories.txt"
  local dns="/opt/SecLists/Discovery/DNS/subdomains-top1million-5000.txt"
  if [ ! -s "$wc" ] || [ ! -s "$dns" ]; then
    if fetch_url "$SL/Discovery/Web-Content/raft-medium-directories.txt" "$wc" \
       && fetch_url "$SL/Discovery/DNS/subdomains-top1million-5000.txt" "$dns"; then
      ok "SecLists (targeted wordlists) -> /opt/SecLists"
    elif retry 2 git clone --depth 1 https://github.com/danielmiessler/SecLists /opt/SecLists; then
      ok "SecLists (full clone) -> /opt/SecLists"
    else
      warn "SecLists fetch failed (ffuf/gobuster/feroxbuster content-discovery will skip)"
    fi
  fi

  # Resolvers: validate a fresh list if dnsvalidator is present, else fall back
  # to a known-good static list (the build often has no time/network for the
  # full validation pass, which is why config/resolvers.txt was missing before).
  if have dnsvalidator && dnsvalidator -tL https://public-dns.info/nameservers.txt \
       -threads 50 -o config/resolvers.txt 2>/dev/null && [ -s config/resolvers.txt ]; then
    ok "resolvers (validated) -> config/resolvers.txt"
  elif fetch_url https://raw.githubusercontent.com/trickest/resolvers/main/resolvers.txt \
       config/resolvers.txt 60; then
    ok "resolvers (trickest static) -> config/resolvers.txt"
  else
    printf '1.1.1.1\n8.8.8.8\n9.9.9.9\n8.8.4.4\n1.0.0.1\n' > config/resolvers.txt
    warn "resolvers: fell back to a 5-entry built-in list"
  fi

  # subjack takeover fingerprints (the -c signature DB).
  if fetch_url https://raw.githubusercontent.com/EdOverflow/can-i-take-over-xyz/master/fingerprints.json \
       config/fingerprints.json 60; then
    ok "subjack fingerprints -> config/fingerprints.json"
  else
    warn "fingerprints.json fetch failed (subjack will skip)"
  fi

  # gf patterns -> ~/.gf (grep-pattern DB for ssrf/xss/sqli/... url triage).
  if [ ! -d "$HOME/.gf" ]; then
    retry 2 git clone --depth 1 https://github.com/1ndianl33t/Gf-Patterns "$HOME/.gf" \
      && ok "gf patterns -> ~/.gf" || warn "gf patterns clone failed"
  fi

  # kiterunner API-route wordlist (the SMALL routes set, ~10MB; routes-large is
  # ~1GB and intentionally not shipped). Path is the {kite_wordlist} default.
  if fetch_url https://github.com/assetnote/wordlists/releases/download/data/routes-small.kite \
       /opt/kite/routes-small.kite 300; then
    ok "kiterunner routes-small.kite -> /opt/kite"
  else
    warn "routes-small.kite fetch failed (kiterunner will skip)"
  fi
}

# ── Optional Python extras (API server, JS-render browser, favicon pivot) ─────
install_python_extras() {
  log "Installing optional Python extras (fastapi/uvicorn/mmh3/playwright)..."
  pip3 install --quiet fastapi uvicorn mmh3 playwright 2>/dev/null \
    && ok "python extras (API + favicon-hash) installed" \
    || warn "some python extras failed (API/favicon degrade cleanly)"
  # Playwright needs a browser for the live JS-render crawler; without it the
  # js-render tool falls back to a static fetch (so this is optional).
  if have playwright || python3 -c "import playwright" 2>/dev/null; then
    python3 -m playwright install --with-deps chromium 2>/dev/null \
      && ok "playwright chromium installed (live JS-render enabled)" \
      || warn "playwright browser install failed — js-render uses static fallback"
  fi
}


# ── extra installable CLI recon tools (batch-wired in config/tools.yaml) ──────
install_batch_clis() {
  log "Installing batch CLI tools..."
  go_install assetfinder "github.com/tomnomnom/assetfinder@latest"
  go_install hakrawler   "github.com/hakluke/hakrawler@latest"
  go_install gobuster    "github.com/OJ/gobuster/v3@latest"
  go_install shuffledns  "github.com/projectdiscovery/shuffledns/cmd/shuffledns@latest"
  go_install cariddi     "github.com/edoardottt/cariddi/cmd/cariddi@latest"
  go_install gauplus     "github.com/bp0lr/gauplus@latest"
  go_install gospider    "github.com/jaeles-project/gospider@latest"
  pip_install sublist3r sublist3r
  pip_install fierce fierce
  pip_install dnsgen dnsgen
  apt_install dnsenum dnsenum
  apt_install dnsrecon dnsrecon
  apt_install exiftool libimage-exiftool-perl
  apt_install binwalk binwalk
  # nikto: not in Debian -> git + perl wrapper
  if ! have nikto; then
    git clone --depth 1 https://github.com/sullo/nikto /opt/nikto 2>/dev/null && \
      printf '#!/bin/sh\nexec perl /opt/nikto/program/nikto.pl "$@"\n' > "$GOBIN/nikto" && \
      chmod +x "$GOBIN/nikto" && ok "nikto -> /opt/nikto" || warn "nikto clone failed"
  fi
}

case "$SET" in
  core) install_core ;;
  resources) install_resources ;;
  batch) install_batch_clis ;;
  massdns) install_massdns ;;
  python|extras) install_python_extras ;;
  all) install_all; install_massdns; install_python_extras ;;
  *) echo "usage: $0 [core|all|resources|massdns|python]"; exit 1 ;;
esac

ok "Tool installation finished. Check with: recontool tools"
