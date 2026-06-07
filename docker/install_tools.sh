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
  go_install httpx     "github.com/projectdiscovery/httpx/cmd/httpx@latest"
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
  # ── Tools backing the full 28-lane coverage ──────────────────────────────
  pip_install sherlock "sherlock-project"        # cat 8: social media recon
  pip_install graphw00f graphw00f                # cat 23: GraphQL fingerprinting
  pip_install apkleaks apkleaks                  # cat 26: mobile / APK recon
  pip_install bbot bbot                          # cat 14: automation suite (one source)
  # apt packages
  apt_install nmap nmap
  apt_install masscan masscan
  apt_install whatweb whatweb
  apt_install whois whois
  apt_install exiftool libimage-exiftool-perl    # cat 11: document metadata

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

# ── SecLists + a clean resolver list ──────────────────────────────────────────
install_resources() {
  log "Fetching resources (wordlists + resolvers)..."
  if [ ! -d /opt/SecLists ]; then
    git clone --depth 1 https://github.com/danielmiessler/SecLists /opt/SecLists 2>/dev/null \
      && ok "SecLists -> /opt/SecLists" || warn "SecLists clone failed"
  fi
  if have dnsvalidator; then
    dnsvalidator -tL https://public-dns.info/nameservers.txt -threads 50 \
      -o config/resolvers.txt 2>/dev/null && ok "resolvers -> config/resolvers.txt" || true
  fi
}

case "$SET" in
  core) install_core ;;
  resources) install_resources ;;
  massdns) install_massdns ;;
  all) install_all; install_massdns ;;
  *) echo "usage: $0 [core|all|resources|massdns]"; exit 1 ;;
esac

ok "Tool installation finished. Check with: recontool tools"
