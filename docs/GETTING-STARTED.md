# Getting Started

ShiftMind’s complete local environment starts from a clean clone with one command.

## Prerequisites

- Git
- Docker Desktop (or Docker Engine with Compose v2)
- At least 8 GB of memory available to Docker
- Ports `5432` and `8080` free

Python, Node, uv, npm, PostgreSQL, migrations, fixture import, and planner provisioning run inside the reviewed container composition; they do not need to be installed on the host.

## Start ShiftMind

```bash
git clone https://github.com/ngthquocminh/roster-ai.git rosterai
cd rosterai
docker compose up -d --build
```

Open `http://localhost:8080`. Choose sign in; the local fake identity provider signs in the pre-provisioned planner through the normal OIDC callback and session-cookie path. Select either immutable fixture and walk the planner journey. The default agent model is the deterministic, keyless `TestModel`; no provider credential is required.

Check readiness with `docker compose ps` and inspect failures with `docker compose logs bootstrap api worker web`. Running the start command again is safe: migrations, fixture imports, and planner provisioning are idempotent.

For a live model, explicitly set `AGENT_RUNTIME_MODEL` and `AGENT_RUNTIME_API_KEY` before starting. Live-provider output is optional and never required release evidence.

Host-port overrides are available when the defaults are occupied:

```bash
POSTGRES_PORT=55432 WEB_PORT=18080 APP_ORIGIN=http://localhost:18080 docker compose up -d --build
```

Use the same port in `WEB_PORT` and `APP_ORIGIN`. The browser must use `localhost`; another hostname can cause the secure `__Host-` session cookie to be discarded.

See [Configuration](CONFIGURATION.md) for the full settings surface and [Development](DEVELOPMENT.md) for running individual processes and tests.
