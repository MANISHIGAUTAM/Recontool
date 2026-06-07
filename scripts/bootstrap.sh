#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Recontool bootstrap — the minimal one-command setup path.
#
#   bash scripts/bootstrap.sh          # local (pip) bootstrap
#   bash scripts/bootstrap.sh docker   # docker compose bootstrap
#
# Steps: ensure .env, install the platform, validate provider config, run a
# zero-network demo to prove the stack works end to end.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."

MODE="${1:-local}"
log() { printf '\033[1;34m[bootstrap]\033[0m %s\n' "$*"; }

# 1. .env
if [ ! -f .env ]; then
  log "creating .env from .env.example (fill in API keys later — all optional)"
  cp .env.example .env
fi

if [ "$MODE" = "docker" ]; then
  log "building + starting the stack via docker compose"
  docker compose build
  log "running zero-network demo inside the container"
  docker compose run --rm recontool demo recontool.local
  log "done. Try:  docker compose run --rm recontool scan acme.com --mode live"
  exit 0
fi

# local path
log "installing the platform (editable)"
pip install -e ".[dev]" >/dev/null
log "validating provider config (demo env)"
recontool config-validate --env demo
log "running zero-network demo"
RECON_MODE=demo recontool demo recontool.local
log "done. Try:  recontool scan acme.com --mode live   (passive, safe)"
