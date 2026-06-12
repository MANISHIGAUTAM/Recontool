# ─────────────────────────────────────────────────────────────────────────────
# Recontool — all-in-one image (Python platform + Go recon tools).
#
#   docker build -t recontool .
#   docker run --rm -v "$PWD/output:/app/output" recontool scan www.xyz.com
#
# For active scanning, mount config and authorize:
#   docker run --rm -v "$PWD/config:/app/config" recontool \
#       scan www.xyz.com --profile stealth --authorize-active
# ─────────────────────────────────────────────────────────────────────────────
# NOTE: ProjectDiscovery tools (subfinder, httpx, nuclei v3, naabu, ...) installed
# at @latest by docker/install_tools.sh require Go 1.24+. Keep this >= 1.24 or the
# go-install layer silently skips those tools (failures are non-fatal by design).
FROM golang:1.24-bookworm AS base

ENV DEBIAN_FRONTEND=noninteractive \
    GOBIN=/usr/local/bin \
    PYTHONUNBUFFERED=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1

# System deps: python, build tools, git, pipx, and libs the scanners need.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv pipx \
        git make gcc libpcap-dev ca-certificates curl \
        nmap masscan whatweb whois dnsutils \
    && rm -rf /var/lib/apt/lists/*

RUN pipx ensurepath || true

WORKDIR /app

# ── Dependency + tool layers FIRST (heavy + rarely changing) ─────────────────
# Install Python deps from requirements (NOT the editable package yet) so that
# editing app code further down never invalidates these expensive layers.
COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt \
    && pip3 install --no-cache-dir fastapi uvicorn mmh3

# Install external recon tools (Go + pip + git). This is the ~40-min heavy layer
# — kept ABOVE the app-code COPY so a code change never busts it.
COPY docker/install_tools.sh ./docker/install_tools.sh
RUN bash docker/install_tools.sh all || true

# ── App code LAST (changes often, cheap to rebuild) ──────────────────────────
# Editable install: a code change only rebuilds from here down (seconds), and the
# bind-mount in docker-compose lets local edits apply with NO rebuild at all.
COPY pyproject.toml ./
COPY recontool ./recontool
RUN pip3 install --no-cache-dir -e .

# Copy the rest (config, docs).
COPY . .

# Default config: if user hasn't provided one, fall back to the example.
RUN test -f config/recontool.yaml || cp config/recontool.example.yaml config/recontool.yaml || true

ENTRYPOINT ["recontool"]
CMD ["--help"]
