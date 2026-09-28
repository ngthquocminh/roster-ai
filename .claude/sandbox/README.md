# Running the docker-compose stack in a Claude Code cloud sandbox

`docker compose up -d --build` from the repo root, as `README.md` says to,
fails in a Claude Code cloud session for two reasons that are specific to
*this kind of sandbox* — not the app, not CI, not a real deployment. If
you're reading this because that command just failed, run
`.claude/sandbox/docker-dev.sh` instead and skip the rest of this file.

## Why it fails here

1. **`ghcr.io` blob CDN is blocked.** The root `Dockerfile`'s first line
   (`FROM ghcr.io/astral-sh/uv:...`) needs `pkg-containers.githubusercontent.com`,
   which this sandbox's network policy denies (Docker Hub, PyPI, npm are all
   fine — confirmed via `curl -sS "$HTTPS_PROXY/__agentproxy/status"`, which
   logs the 403 as `recentRelayFailures`). `docker-dev.sh` first tries the
   real Dockerfile as-is; only on that specific failure does it fall back to
   `.claude/sandbox/Dockerfile.ghcr-fallback`, which installs `uv` from PyPI
   inside a container that trusts the session's proxy CA
   (`/root/.ccr/ca-bundle.crt`) and builds with `--network host`, per
   `/root/.ccr/README.md`'s docker section.

2. **`npm ci` inside the frontend's Docker build is flaky.** It intermittently
   dies with npm's own `Exit handler never called!` bug — a known npm issue
   under certain container networking, unrelated to this project (`npm ci`
   run directly on the sandbox host works fine, in ~15s). `docker-dev.sh`
   builds the frontend on the host and packages the static `dist/` into the
   nginx image with `.claude/sandbox/Dockerfile.web-static`, skipping
   in-container npm entirely.

**If a future session's network policy allows `ghcr.io`**, the script's
first attempt (plain `docker build .`) will just succeed and the fallback
path won't run — no changes needed here. If `npm ci` stops being flaky in
containers, the fallback in `build_frontend` is no longer necessary but is
harmless to keep.

## Docker Hub rate limiting

Docker Hub rate-limits anonymous pulls per source IP (100/6h at last check).
A shared sandbox egress IP can be near that limit from unrelated sessions,
surfacing as `429 Too Many Requests` on `FROM <image>` — even for an image
pulled minutes earlier, since Docker still does a manifest HEAD check.
`docker-dev.sh` retries each build with backoff (4 attempts, 15/30/60s) for
exactly this. If it's still 429 after that, it's a wait-it-out situation
(the window resets ~6h after the first pull that counted against it), not a
bug in this script or the app.

## Credentials

Live LLM calls (OpenRouter/Anthropic/Gemini) need network access to their
host to be allowed by this session's network policy, and a key. Both are
sandbox/environment settings (title bar → Edit → Network access / API
credentials), not anything in this repo. `docker-compose.yml` already passes
`AGENT_RUNTIME_MODEL` / `AGENT_RUNTIME_API_KEY` / `OPENROUTER_API_KEY` /
`ANTHROPIC_API_KEY` through from the session's own environment
(`${VAR:-default}`) — don't create a `backend/.env` with real keys in it to
test this; set the credential in the environment's Credentials section
instead and it'll be there next session.

## Smoke-testing after the stack is up

`api` and `worker` don't publish a host port (only `web` on 8080 and
`postgres` on 5432 do), and the app requires auth (fake OIDC + a
`Secure`-flagged session cookie, which `curl` won't resend over plain HTTP).
Get the api container's bridge IP and hit it directly:

```bash
API="http://$(docker inspect roster-ai-api-1 --format '{{json .NetworkSettings.Networks}}' \
  | python3 -c "import json,sys; print(list(json.load(sys.stdin).values())[0]['IPAddress'])"):8000"
curl -sS "$API/health"

# Fake-OIDC login (PKCE). Secure cookies won't round-trip through curl's
# jar over plain http, so pull the value out and pass it back as a header.
LOC=$(curl -sS -o /dev/null -D - "$API/api/v1/auth/login?redirect_uri=http://localhost:8080" \
  | grep -i '^location:' | sed 's/location: //I' | tr -d '\r')
AUTH_PATH="/oidc/authorize?${LOC#*\?}"
LOC2=$(curl -sS -o /dev/null -D - "$API$AUTH_PATH" \
  | grep -i '^location:' | sed 's/location: //I' | tr -d '\r')
CB_PATH="/api/v1/auth/callback?${LOC2#*\?}"
COOKIE=$(curl -sS -D - -o /dev/null "$API$CB_PATH" \
  | grep -i '^set-cookie:' | sed -E 's/set-cookie: (__Host-shiftmind_session=[^;]+);.*/\1/I' | tr -d '\r')

# Now use $COOKIE (and the csrf_token from /api/v1/auth/session, plus
# `Origin: http://localhost:8080` on POSTs) for authenticated calls, e.g.:
curl -sS -H "Cookie: $COOKIE" "$API/api/v1/scenarios"
```

For a full conversation → agent-run → schedule-run walkthrough, see the
session transcript this file was written from, or just ask Claude to re-run
one — the recipe above is the expensive part to rediscover, not that part.
