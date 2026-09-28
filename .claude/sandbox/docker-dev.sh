#!/usr/bin/env bash
# Bring up the full docker-compose stack (postgres, bootstrap, api, worker, web)
# inside a Claude Code cloud sandbox session.
#
# Why this exists: a first-principles `docker compose up -d --build` fails twice
# in this sandbox, for reasons that have nothing to do with the app:
#
#   1. The tracked backend Dockerfile pulls `ghcr.io/astral-sh/uv`. This
#      sandbox's network policy blocks ghcr.io's blob CDN
#      (pkg-containers.githubusercontent.com) even when Docker Hub, PyPI and
#      npm are all reachable. Workaround: install `uv` from PyPI instead,
#      inside a container that trusts the session's proxy CA bundle
#      (/root/.ccr/ca-bundle.crt) and builds with --network host (see
#      /root/.ccr/README.md's "docker build / docker run" section).
#   2. `npm ci` run *inside* the frontend's Docker build intermittently dies
#      with npm's own "Exit handler never called!" bug — specific to this
#      sandbox's container networking, not the project. `npm ci` on the host
#      directly is fine. Workaround: build the frontend on the host with the
#      already-installed host npm, then package the static `dist/` into the
#      nginx image without any in-container npm step.
#
# Both are sandbox-networking artifacts, not app bugs — see
# .claude/sandbox/README.md for the full story and how to tell if either
# workaround is no longer needed (e.g. because the environment's network
# policy was widened to allow ghcr.io).
#
# Safe to re-run. Doesn't touch anything outside Docker's own storage plus a
# transient copy of the CA bundle in the repo root (always cleaned up).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
REPO_ROOT="$PWD"

log() { printf '\n\033[1m>> %s\033[0m\n' "$1"; }

# Docker Hub rate-limits anonymous pulls per source IP (currently 100/6h).
# A shared sandbox egress IP can already be near that limit from unrelated
# sessions, surfacing as "429 Too Many Requests" on any `FROM <image>` that
# needs a fresh manifest check — even for an image pulled minutes ago. Retry
# with backoff; if it's still 429 after that, it's a wait-it-out situation,
# not a bug in this script.
retry_build() {
  local attempt=1 max=4 delay=15
  while true; do
    if "$@"; then
      return 0
    fi
    if [ "$attempt" -ge "$max" ]; then
      return 1
    fi
    log "Build attempt $attempt failed (possibly Docker Hub rate limiting); retrying in ${delay}s..."
    sleep "$delay"
    attempt=$((attempt + 1))
    delay=$((delay * 2))
  done
}

ensure_dockerd() {
  if docker info >/dev/null 2>&1; then
    return
  fi
  log "Starting dockerd..."
  (dockerd >/tmp/dockerd.log 2>&1 &)
  for _ in $(seq 1 30); do
    docker info >/dev/null 2>&1 && return
    sleep 1
  done
  echo "dockerd did not come up; see /tmp/dockerd.log" >&2
  exit 1
}

build_backend() {
  log "Building backend image (shiftmind-backend:local)..."
  if retry_build docker build -t shiftmind-backend:local . >/tmp/backend-build.log 2>&1; then
    log "Backend built normally (ghcr.io reachable in this session)."
    return
  fi
  if ! grep -q "ghcr.io\|pkg-containers.githubusercontent.com" /tmp/backend-build.log; then
    echo "Backend build failed for a reason unrelated to ghcr.io — see /tmp/backend-build.log" >&2
    tail -n 40 /tmp/backend-build.log >&2
    exit 1
  fi
  log "ghcr.io blocked as expected; falling back to PyPI-installed uv..."
  trap 'rm -f "$REPO_ROOT/.ca-bundle.sandboxtmp"' EXIT
  cp /root/.ccr/ca-bundle.crt "$REPO_ROOT/.ca-bundle.sandboxtmp"
  retry_build docker build --network host -f .claude/sandbox/Dockerfile.ghcr-fallback \
    -t shiftmind-backend:local .
  rm -f "$REPO_ROOT/.ca-bundle.sandboxtmp"
  trap - EXIT
}

build_frontend() {
  log "Building frontend on the host (avoids in-container npm ci flakiness)..."
  npm --prefix frontend ci
  VITE_API_BASE_URL="${APP_ORIGIN:-http://localhost:8080}" npm --prefix frontend run build
  log "Packaging frontend/dist into the nginx image (shiftmind-web:local)..."
  # frontend/.dockerignore excludes dist/ (correct for the real, in-container
  # build). Stage nginx.conf + dist in a throwaway dir with no .dockerignore
  # of its own, rather than touching frontend/'s ignore rules.
  local stage
  stage="$(mktemp -d)"
  trap 'rm -rf "$stage"' RETURN
  cp frontend/nginx.conf "$stage/"
  cp -r frontend/dist "$stage/"
  retry_build docker build -f .claude/sandbox/Dockerfile.web-static -t shiftmind-web:local "$stage"
}

up_stack() {
  log "Starting postgres..."
  docker compose up -d --wait postgres

  log "Running bootstrap (migrations + fixture seed)..."
  docker compose up -d bootstrap
  docker wait "$(docker compose ps -q bootstrap)" >/dev/null

  log "Starting api, worker, web..."
  docker compose up -d --force-recreate api worker web

  log "Done. docker compose ps:"
  docker compose ps
}

ensure_dockerd
build_backend
build_frontend
up_stack

cat <<'EOF'

Stack is up. Notes:
  - api/worker/web don't publish host ports except web (8080) and postgres
    (5432) — reach the api container directly by IP if you need to curl it
    without going through nginx: see .claude/sandbox/README.md.
  - AGENT_RUNTIME_MODEL / AGENT_RUNTIME_API_KEY (or OPENROUTER_API_KEY /
    ANTHROPIC_API_KEY) are picked up automatically from this session's own
    environment via docker-compose.yml's ${VAR:-default} passthrough — set
    them in the Claude Code environment's Credentials section, not in a
    committed .env file.
EOF
