#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# docker compose smoke test — proves a clean checkout boots with only env vars.
#
#   bash scripts/compose-smoke.sh
#
# Validates compose config, builds the image, and runs the zero-network demo +
# provider config validation inside the container. No API keys required.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."

log() { printf '\033[1;34m[compose-smoke]\033[0m %s\n' "$*"; }

[ -f .env ] || cp .env.example .env

log "1/4 validating compose file"
docker compose config >/dev/null

log "2/4 building image"
docker compose build recontool

log "3/4 provider config validation (demo) in-container"
docker compose run --rm -e RECON_MODE=demo recontool config-validate --env demo

log "4/4 full zero-network demo pipeline in-container"
docker compose run --rm -e RECON_MODE=demo recontool demo recontool.local

log "compose smoke PASSED"
