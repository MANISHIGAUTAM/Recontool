# ─────────────────────────────────────────────────────────────────────────────
# Recontool — all-in-one image with ALL recon tools pre-installed.
#
# Multi-stage build:
#   Stage 1 (go-builder): compile all Go recon tools in isolation
#   Stage 2 (runtime): Python platform + compiled Go binaries + system tools
#
# Usage:
#   docker build -t recontool .
#   docker run --rm -v "$PWD/output:/app/output" --env-file .env recontool scan groww.in --mode live --authorize-active
#
# Push to Docker Hub:
#   docker build -t yourhub/recontool:latest .
#   docker push yourhub/recontool:latest
# ─────────────────────────────────────────────────────────────────────────────

# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1: Compile Go recon tools (isolated, cached layer)
# ══════════════════════════════════════════════════════════════════════════════
FROM golang:1.24-bookworm AS go-builder

ENV GOBIN=/go-tools \
    CGO_ENABLED=0 \
    GO111MODULE=on \
    GOTOOLCHAIN=auto

RUN mkdir -p /go-tools

# Install libpcap-dev for naabu (needs CGO for pcap)
RUN apt-get update && apt-get install -y --no-install-recommends libpcap-dev && rm -rf /var/lib/apt/lists/*

# Install Go tools one-by-one with pinned versions where needed.
# Each RUN is a separate layer so failures are isolated and cacheable.

# ── Core ProjectDiscovery suite (MUST succeed — fail build if these break) ────
RUN go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
RUN go install github.com/projectdiscovery/httpx/cmd/httpx@latest
RUN CGO_ENABLED=1 go install github.com/projectdiscovery/naabu/v2/cmd/naabu@latest
RUN go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest

# ── Extended PD tools (graceful — don't block build) ─────────────────────────
RUN go install github.com/projectdiscovery/dnsx/cmd/dnsx@latest || true
RUN go install github.com/projectdiscovery/katana/cmd/katana@latest || true
RUN go install github.com/projectdiscovery/tlsx/cmd/tlsx@latest || true
RUN go install github.com/projectdiscovery/asnmap/cmd/asnmap@latest || true
RUN go install github.com/projectdiscovery/uncover/cmd/uncover@latest || true
RUN go install github.com/projectdiscovery/alterx/cmd/alterx@latest || true
RUN go install github.com/projectdiscovery/notify/cmd/notify@latest || true
RUN go install github.com/projectdiscovery/interactsh/cmd/interactsh-client@latest || true
RUN go install github.com/projectdiscovery/mapcidr/cmd/mapcidr@latest || true
RUN go install github.com/projectdiscovery/cdncheck/cmd/cdncheck@latest || true

# ── URL/archive tools (graceful) ─────────────────────────────────────────────
RUN go install github.com/lc/gau/v2/cmd/gau@latest || true
RUN go install github.com/tomnomnom/waybackurls@latest || true
RUN go install github.com/tomnomnom/assetfinder@latest || true
RUN go install github.com/tomnomnom/anew@latest || true
RUN go install github.com/tomnomnom/unfurl@latest || true
RUN go install github.com/tomnomnom/qsreplace@latest || true
RUN go install github.com/tomnomnom/gf@latest || true

# ── Discovery / scanning (graceful) ──────────────────────────────────────────
RUN go install github.com/ffuf/ffuf/v2@latest || true
RUN go install github.com/haccer/subjack@latest || true
RUN go install github.com/d3mondev/puredns/v2@latest || true
RUN go install github.com/glebarez/cero@latest || true
RUN go install github.com/j3ssie/metabigor@latest || true
RUN go install github.com/gwen001/github-subdomains@latest || true
RUN go install github.com/gitleaks/gitleaks/v8@latest || true

# ── Known-flaky tools (graceful) ─────────────────────────────────────────────
RUN go install github.com/sensepost/gowitness@latest || true
RUN go install github.com/sa7mon/s3scanner@latest || true
RUN go install github.com/BishopFox/jsluice/cmd/jsluice@latest || true

# Verify what we got
RUN ls /go-tools/ && echo "=== $(ls /go-tools/ | wc -l) Go tools compiled ==="


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2: Runtime image (Python + Go binaries + system tools)
# ══════════════════════════════════════════════════════════════════════════════
FROM python:3.12-slim-bookworm AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1 \
    PATH="/usr/local/go-tools:$PATH"

# System packages needed at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates dnsutils whois \
        nmap libpcap0.8 \
        libimage-exiftool-perl \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled Go tools from builder stage
COPY --from=go-builder /go-tools /usr/local/go-tools

# Verify Go tools are functional
RUN subfinder -version 2>&1 | head -1 || true && \
    nuclei -version 2>&1 | head -1 || true && \
    echo "Go tools ready: $(ls /usr/local/go-tools/ | wc -l) binaries"

# Update nuclei templates
RUN nuclei -update-templates -silent 2>/dev/null || true

WORKDIR /app

# Install Python dependencies (cached layer)
COPY requirements.txt pyproject.toml ./
COPY recontool ./recontool
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -e .

# Install Python recon tools that are safe/stable
RUN pip install --no-cache-dir \
    wafw00f \
    arjun \
    2>/dev/null || true

# Copy the rest (config, docs, scripts)
COPY . .

# Default config fallback
RUN test -f config/recontool.yaml || cp config/recontool.example.yaml config/recontool.yaml || true

# Build-time self-test: demo pipeline must work offline (no network, no keys)
RUN RECON_MODE=demo RECON_ARTIFACT_DIR=/tmp/build-demo \
    recontool config-validate --env demo \
    && RECON_MODE=demo RECON_ARTIFACT_DIR=/tmp/build-demo recontool demo recontool.local \
    && rm -rf /tmp/build-demo \
    && echo "=== BUILD SELF-TEST PASSED ==="

# Runtime healthcheck
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD recontool config-validate --env demo || exit 1

ENTRYPOINT ["recontool"]
CMD ["--help"]
