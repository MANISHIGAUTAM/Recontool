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
FROM golang:1.23-bookworm AS base

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

# Install the Python platform first (better layer caching).
COPY requirements.txt pyproject.toml ./
COPY recontool ./recontool
RUN pip3 install --no-cache-dir -r requirements.txt && pip3 install --no-cache-dir -e .

# Install external recon tools (Go + pip + git). This is the heavy layer.
COPY docker/install_tools.sh ./docker/install_tools.sh
RUN bash docker/install_tools.sh all || true

# Copy the rest (config, docs).
COPY . .

# Default config: if user hasn't provided one, fall back to the example.
RUN test -f config/recontool.yaml || cp config/recontool.example.yaml config/recontool.yaml || true

# Self-test the image at build time: provider config + demo pipeline must work
# entirely offline (no network, no keys). Fails the build if the stack is broken.
RUN RECON_MODE=demo recontool config-validate --env demo \
    && RECON_MODE=demo RECON_ARTIFACT_DIR=/tmp/build-demo recontool demo recontool.local \
    && rm -rf /tmp/build-demo

# Container healthcheck: provider config stays valid.
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD recontool config-validate --env demo || exit 1

ENTRYPOINT ["recontool"]
CMD ["--help"]
