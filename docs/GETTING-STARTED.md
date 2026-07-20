<!-- generated-by: gsd-doc-writer -->
# Getting Started

This walks a brand-new contributor from a fresh clone to a running backend
(API + CLI solve) and a running frontend talking to it. For the full command
reference and rationale behind these steps, see [`README.md`](../README.md#quick-start)
and [`docs/CONFIGURATION.md`](CONFIGURATION.md) — this doc sequences the same
verified commands into a single first-run path and doesn't duplicate their
detail.

## Prerequisites

- **Python** 3.10–3.12 (backend `requires-python = ">=3.10,<3.13"` in
  `backend/pyproject.toml`).
- **[uv](https://docs.astral.sh/uv/)** — Astral's Python package manager;
  manages the backend's virtualenv and lockfile (`backend/uv.lock`).
- **Node.js** 20 or later and **npm** — required to run the frontend's
  toolchain (Vite 8, Vitest 4).
- No database server to install — SQLite (via Python's stdlib `sqlite3`,
  WAL mode) is used and the file is created automatically on first run.

## Installation steps

### 1. Clone the repository

```bash
git clone https://github.com/ngthquocminh/roster-ai.git rosterai
cd rosterai
```

### 2. Install backend dependencies

```bash
cd backend
uv sync                 # creates backend/.venv and installs from uv.lock
```

### 3. Install frontend dependencies

```bash
cd ../frontend
npm install
```

## First run

### Run the solver from the CLI (no server needed)

From `backend/`, solve the committed fixture directly and print the schedule
metrics:

```bash
cd backend
uv run python run.py ../data/sample_tiny_input.json
```

This loads `data/sample_tiny_input.json` (a small, real-schema weekly
fixture), runs the CP-SAT solver, and prints solve metrics and a schedule
sample to stdout. No database or API server is involved in this path.

Optionally confirm the test suite passes (uses the keyless `stub` LLM
provider, no network calls):

```bash
uv run pytest -q
```

### Start the backend API

Still from `backend/`:

```bash
uv run uvicorn api.main:app --reload
```

The API listens at `http://127.0.0.1:8000` (interactive docs at `/docs`,
`/redoc`, and the raw schema at `/openapi.json`). By default
`LLM_PROVIDER=stub`, so plain-English constraint parsing and insight
generation work immediately with no API key. See
[`docs/CONFIGURATION.md`](CONFIGURATION.md) for every backend environment
variable and [`docs/API.md`](API.md) for the full endpoint reference and an
example scenario → run → result lifecycle with `curl`.

### Start the frontend, pointed at the running backend

With the backend from the previous step still running, from `frontend/`:

```bash
cd frontend
echo "VITE_API_BASE_URL=http://127.0.0.1:8000" > .env
npm run dev
```

Open `http://localhost:5173`. The app fails loudly at load time if
`VITE_API_BASE_URL` is missing — see
[`docs/CONFIGURATION.md`](CONFIGURATION.md#frontend-environment-variables)
for the exact variable and its default-origin caveats. The backend's default
`CORS_ORIGINS` already allows `http://localhost:5173` and
`http://localhost:4173`, so no extra CORS configuration is needed for this
default dev setup.

You now have a full loop: create a scenario from a fixture in the UI, shape
it with a plain-English constraint, trigger a solve, and read back the
schedule, coverage, and an on-demand insight report — all from the browser.

## Common setup issues

- **`ortools` install/import errors or segfaults.** The backend pins
  `ortools==9.11.4210` in `backend/pyproject.toml` specifically because the
  9.15 wheel segfaults on the reference dev machine. If `uv sync` pulls a
  different version somehow (e.g. a stale lockfile), re-run `uv sync` to
  restore the pinned version — do not upgrade `ortools` without re-verifying.
- **Frontend fails to start with a `VITE_API_BASE_URL is not set` error.**
  You skipped creating `frontend/.env` (or copying it from
  `frontend/.env.example`). Create it with the backend's origin as shown
  above, then restart `npm run dev`.
- **API calls from the browser fail with a CORS error.** The frontend's dev
  origin doesn't match `CORS_ORIGINS`. This only happens if you changed the
  frontend's dev port or are running the backend with a custom
  `CORS_ORIGINS` value — the defaults (`http://localhost:5173`,
  `http://localhost:4173`) already cover `npm run dev` and `npm run preview`.
  `CORS_ORIGINS` must be set before the backend process starts (it is read
  once at app construction), so restart `uvicorn` after changing it.
- **A run stays `PENDING`/`RUNNING` and never completes.** The solver runs
  in a single worker thread off the event loop, so only one solve executes
  at a time; a second run queued while one is in-flight waits its turn. Poll
  `GET /runs/{run_id}` until `status` is `COMPLETED` or `FAILED`.
- **CLI solve takes a long time on the full fixture.** The full-week
  instance solves the primary (unmet labour-hours) objective in roughly
  20 seconds, but proving cost-optimality can take ~2 minutes. Pass a shorter
  time limit as the third CLI argument (`run.py <input> cpsat <seconds>`) to
  get a faster, unmet-optimal result during a quick probe.

## Next steps

- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — system design, components, and
  the reasoning behind them.
- [`docs/API.md`](API.md) — full HTTP endpoint and model reference.
- [`docs/CONFIGURATION.md`](CONFIGURATION.md) — every environment variable
  for both the backend and the frontend, with defaults and per-environment
  guidance.
- [`README.md`](../README.md) — project overview, status, and doc ownership
  split.
