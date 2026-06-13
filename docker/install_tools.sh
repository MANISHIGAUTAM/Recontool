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

go_install() {  # go_install <binary> <module@version>
  local bin="$1" mod="$2"
  if have "$bin"; then ok "$bin already installed"; return; fi
  log "go install $mod"
  if go install "$mod" 2>/dev/null; then ok "installed $bin"; else warn "failed: $bin"; fi
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
  if go install "$mod" 2>/dev/null; then ok "installed $bin"; else warn "failed: $bin"; fi
}

pip_install() { # pip_install <binary> <pkg>
  local bin="$1" pkg="$2"
  if have "$bin"; then ok "$bin already installed"; return; fi
  log "pip install $pkg"
  if pipx install "$pkg" 2>/dev/null || pip3 install --quiet "$pkg" 2>/dev/null; then
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
  go_install gitleaks  "github.com/gitleaks/gitleaks/v8@latest"
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
install_resources() {
  log "Fetching resources (wordlists + resolvers + tool data-files)..."
  if [ ! -d /opt/SecLists ]; then
    git clone --depth 1 https://github.com/danielmiessler/SecLists /opt/SecLists 2>/dev/null \
      && ok "SecLists -> /opt/SecLists" || warn "SecLists clone failed"
  fi

  # Resolvers: validate a fresh list if dnsvalidator is present, else fall back
  # to a known-good static list (the build often has no time/network for the
  # full validation pass, which is why config/resolvers.txt was missing before).
  if have dnsvalidator && dnsvalidator -tL https://public-dns.info/nameservers.txt \
       -threads 50 -o config/resolvers.txt 2>/dev/null && [ -s config/resolvers.txt ]; then
    ok "resolvers (validated) -> config/resolvers.txt"
  elif curl -fsSL https://raw.githubusercontent.com/trickest/resolvers/main/resolvers.txt \
       -o config/resolvers.txt 2>/dev/null && [ -s config/resolvers.txt ]; then
    ok "resolvers (trickest static) -> config/resolvers.txt"
  else
    printf '1.1.1.1\n8.8.8.8\n9.9.9.9\n8.8.4.4\n1.0.0.1\n' > config/resolvers.txt
    warn "resolvers: fell back to a 5-entry built-in list"
  fi

  # subjack takeover fingerprints (the -c signature DB).
  if [ ! -s config/fingerprints.json ]; then
    curl -fsSL https://raw.githubusercontent.com/haccer/subjack/master/fingerprints.json \
      -o config/fingerprints.json 2>/dev/null && ok "subjack fingerprints -> config/fingerprints.json" \
      || warn "fingerprints.json fetch failed (subjack will skip)"
  fi

  # gf patterns -> ~/.gf (grep-pattern DB for ssrf/xss/sqli/... url triage).
  if [ ! -d "$HOME/.gf" ]; then
    git clone --depth 1 https://github.com/1ndianl33t/Gf-Patterns "$HOME/.gf" 2>/dev/null \
      && ok "gf patterns -> ~/.gf" || warn "gf patterns clone failed"
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

case "$SET" in
  core) install_core ;;
  resources) install_resources ;;
  massdns) install_massdns ;;
  python|extras) install_python_extras ;;
  all) install_all; install_massdns; install_python_extras ;;
  *) echo "usage: $0 [core|all|resources|massdns|python]"; exit 1 ;;
esac

ok "Tool installation finished. Check with: recontool tools"
