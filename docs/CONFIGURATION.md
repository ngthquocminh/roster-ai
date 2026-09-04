<!-- generated-by: gsd-doc-writer -->
# Configuration

ShiftMind has two independently configured halves: the Python backend (FastAPI +
CP-SAT solver + LLM layer) and the Vite/React frontend. Each loads its own
`.env` file and neither shares configuration with the other except implicitly,
via CORS origins and the API base URL the frontend is told to call.

## Backend environment variables

Loaded by `backend/settings.py` via `default_settings()`, which re-reads
`os.environ` on every call so overrides apply at request time (all fields
except `cors_origins` — see [CORS configuration](#cors-configuration) below).

On import, `backend/settings.py` also loads `backend/.env` via
`python-dotenv` (`load_dotenv(_BACKEND_DIR / ".env", override=False)`), so an
already-set OS environment variable always wins over the `.env` file, and an
empty `KEY=` line in `.env` does not clobber a real OS-level value. Copy
`backend/.env.example` to `backend/.env` and fill in values to configure a
local backend.

| Variable | Required | Default | Description |
|---|---|---|---|
| `ROSTERAI_DB` | Optional | `backend/var/rosterai.db` | Path to the SQLite database file. |
| `ROSTERAI_DATA_DIR` | Optional | `<repo-root>/data` | Directory holding input fixture JSON files. |
| `LLM_PROVIDER` | Optional | `stub` | Selects the `LLMProvider` backend: `stub` (keyless, no network calls), `gemini`, or `openrouter`. |
| `LLM_MODEL` | Optional | `gemini-2.5-flash` | Model ID passed to the Gemini provider. |
| `GEMINI_API_KEY` | Required if `LLM_PROVIDER=gemini` | *(none)* | Google Gemini API key. |
| `OPENROUTER_API_KEY` | Required if `LLM_PROVIDER=openrouter` | *(none)* | OpenRouter API key. |
| `OPENROUTER_MODEL` | Optional | `openai/gpt-oss-20b:free` | Model slug passed to OpenRouter (distinct from `LLM_MODEL` because `LLM_MODEL`'s default is a Gemini-only model ID, not a valid OpenRouter slug). |
| `AGENT_MODEL_INPUT_USD_PER_MTOK` | Optional | `0` | Non-negative input-token price in USD per million tokens. When both price variables are unset/zero, telemetry reports `unpriced`, not free. |
| `AGENT_MODEL_OUTPUT_USD_PER_MTOK` | Optional | `0` | Non-negative output-token price in USD per million tokens. When both price variables are unset/zero, telemetry reports `unpriced`, not free. |
| `AGENT_MODEL_CACHE_READ_USD_PER_MTOK` | Optional | `0` | Non-negative price for cache-read tokens in USD per million tokens. A provider's `input_tokens` figure already includes cache tokens, so this rate — not the input rate above — prices them; zero means they contribute nothing to the estimate, not that caching is free. |
| `AGENT_MODEL_CACHE_WRITE_USD_PER_MTOK` | Optional | `0` | Same as above, for cache-write tokens. |
| `CORS_ORIGINS` | Optional | `http://localhost:5173,http://localhost:4173` | Comma-separated list of browser origins allowed to call the API. |
| `APPROVAL_EXPIRY_SECONDS` | Optional | `3600` | Positive lifetime, in seconds, snapshotted into a newly requested approval. |
| `SCHEDULING_BASELINE_ENABLED` | Optional | `true` | Enables the consequential baseline-approval capability. |

### Required vs optional settings

None of the backend settings cause a startup failure by themselves — every
field in the `Settings` dataclass has a default, and `GEMINI_API_KEY` /
`OPENROUTER_API_KEY` are passed straight through to the underlying SDK client
(`google.genai.Client(api_key=...)` / `openai.OpenAI(api_key=...)`) without
eager validation. The practical effect:

- With the default `LLM_PROVIDER=stub`, the app runs fully keyless — no
  environment variables are required at all.
- Setting `LLM_PROVIDER=gemini` or `LLM_PROVIDER=openrouter` without the
  matching API key does not fail at process startup; it fails later, at the
  first LLM call, when the vendor SDK rejects the missing/invalid key. That
  error is caught and re-raised as the provider-neutral `LLMProviderError`
  (see `backend/llm/base.py`).
- `create_provider()` (`backend/llm/base.py`) raises `ValueError` immediately
  if `settings=None` is passed for `"gemini"` or `"openrouter"` — this only
  matters if you are calling the provider factory directly rather than via
  the FastAPI dependency (`api/deps.py:get_llm_provider`), which always
  supplies `settings`.
- An explicitly empty `CORS_ORIGINS=""` yields an empty allow-list (no
  browser origin may call the API) rather than silently falling back to the
  default two Vite origins — the fallback only applies when the variable is
  absent from the environment entirely.

### Defaults

All defaults are defined inline in `backend/settings.py:default_settings()`:

- `db_path` → `str(_BACKEND_DIR / "var" / "rosterai.db")`
- `data_dir` → `str(_REPO_ROOT / "data")`
- `llm_provider` → `"stub"`
- `llm_model` → `"gemini-2.5-flash"`
- `openrouter_model` → `"openai/gpt-oss-20b:free"` (module constant
  `_OPENROUTER_DEFAULT_MODEL`, noted in source as live-verified tool-capable
  as of 2026-07-13, replacing a prior free-tier model that started returning
  upstream 429s)
- `agent_model_input_usd_per_mtok` → `0.0` and
  `agent_model_output_usd_per_mtok` → `0.0`; together these mean pricing is
  unconfigured (`cost_basis="unpriced"`), not that model usage is free
- `cors_origins` → `("http://localhost:5173", "http://localhost:4173")` (Vite
  dev server and preview server origins)

### CORS configuration

CORS is configured once, at FastAPI app construction time in
`backend/api/main.py`, not per-request:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().cors_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

Because `add_middleware` only runs once at import time, `CORS_ORIGINS` must be
set in the environment **before** the app module is imported — changing it
after the process has started (e.g. in a test that sets the env var
post-import) has no effect. `allow_credentials` is left at Starlette's default
of `False`: the app never sends cookies or an `Authorization` header, so no
credentialed cross-origin requests are needed.

### OpenRouter base URL

The OpenRouter provider (`backend/llm/openrouter.py`) points the `openai` SDK
at a hardcoded base URL, `https://openrouter.ai/api/v1` — this is not
configurable via environment variable.

## Frontend environment variables

Loaded by Vite's `import.meta.env` mechanism from `frontend/.env` (not
committed — copy from `frontend/.env.example`). Vite exposes only variables
prefixed `VITE_` to client code.

| Variable | Required | Default | Description |
|---|---|---|---|
| `VITE_API_BASE_URL` | Required | *(none)* | Origin of the backend API the frontend calls (e.g. `http://localhost:8000` in development, or the deployed API's origin in production). |

`frontend/src/lib/env.ts` is the single typed accessor for this variable —
every other module imports `API_BASE_URL` from there rather than reading
`import.meta.env.VITE_API_BASE_URL` directly, so there is exactly one place in
the codebase where a misconfigured origin could leak in. The module fails
loudly at load time if the variable is missing or empty:

```
VITE_API_BASE_URL is not set. Copy frontend/.env.example to frontend/.env
and set VITE_API_BASE_URL to the backend's origin (see .env.example for
the default and the cross-origin caveat).
```

### Test-time override

`frontend/vite.config.ts` sets a fixed test-only value so unit tests never
depend on a developer's local, gitignored `.env`:

```ts
test: {
  env: {
    VITE_API_BASE_URL: 'http://127.0.0.1:8000',
  },
},
```

This value is scoped to the Vitest `test` block only — `npm run dev` and
`npm run build` load the real `.env` file via Vite's own mechanism and are
unaffected by it.

## Per-environment overrides

- **Backend:** there is no built-in `NODE_ENV`-style environment switch.
  Per-environment configuration is done by pointing `ROSTERAI_DB` /
  `ROSTERAI_DATA_DIR` at different paths, or by setting a different
  `LLM_PROVIDER` (e.g. `stub` in CI, a real provider in staging/production).
  <!-- VERIFY: production environment variable values and secret storage mechanism (e.g. AWS Secrets Manager, App Runner environment configuration) are not present in the repository. -->
- **Frontend:** `VITE_API_BASE_URL` is the only per-environment value in
  practice — set it to the local backend origin in development and to the
  deployed API's origin in staging/production builds.
  <!-- VERIFY: the actual staging/production API origin is not discoverable from the repository. -->
- **CI/tests:** `backend/pyproject.toml` defines a `live` pytest marker for
  tests that exercise a real network-backed LLM provider; these are excluded
  by default (`pytest`) and only run explicitly (`pytest -m live`), so CI does
  not require `GEMINI_API_KEY` or `OPENROUTER_API_KEY` to pass. The frontend
  test suite (`npm test` / `vitest run`) uses the fixed
  `VITE_API_BASE_URL=http://127.0.0.1:8000` override shown above and needs no
  `.env` file.

## Config file format

Beyond the two `.env` files described above, there is no additional structured
config file (no `config.yaml`, `config.json`, or similar) — all runtime
configuration is environment-variable based.
