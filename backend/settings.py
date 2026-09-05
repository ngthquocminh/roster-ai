"""Runtime settings — filesystem paths and LLM provider config, resolved from
env with sane defaults.

Kept to a single lightweight config-layer dependency (python-dotenv) so any
layer can import it. Env overrides let tests point at a temp DB / data dir, or
select an LLM provider/model, without touching code.
"""
from __future__ import annotations

import os
import math
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent

# Load backend/.env once at import time, resolved relative to this file so it
# works regardless of process CWD (API server, run.py CLI, pytest). A real OS
# env var always wins (override=False); an empty `GEMINI_API_KEY=` in the file
# does not clobber an already-set OS key.
load_dotenv(_BACKEND_DIR / ".env", override=False)


# Live-verified tool-capable as of 2026-07-13; replaces meta-llama/llama-3.3-70b-instruct:free, which started returning upstream 429 rate-limit errors.
_OPENROUTER_DEFAULT_MODEL = "openai/gpt-oss-20b:free"

# FR12 / NFR16 closed vocabulary. Keeping the application-owned ceilings named
# in one place makes omission detectable when the contract changes.
#
# `lease_seconds` is included even though FR12 does not name it: it is a
# positive, application-owned ceiling bounding how long one solve may hold its
# work, and it was previously validated at process start while sitting outside
# the very tuple that exists to notice an unvalidated ceiling.
AC2_CEILING_FIELDS = (
    "solver_wall_time_limit_seconds",
    "agent_runtime_request_limit",
    "agent_runtime_tool_calls_limit",
    "agent_runtime_retries_limit",
    "agent_runtime_total_tokens_limit",
    "site_max_concurrent_runs",
    "agent_runtime_deadline_seconds",
    "lease_seconds",
    "agent_availability_recency_seconds",
)


@dataclass(frozen=True)
class Settings:
    db_path: str            # SQLite file
    data_dir: str           # directory holding input fixtures (*.json)
    database_url: str = field(repr=False)  # restricted API runtime credential (T-04-01)
    provisioning_database_url: str = field(repr=False)  # privileged credential (T-04-01)
    maintenance_flag_path: str  # persistent Gate A legacy-write lock
    llm_provider: str       # "stub" (default) | "gemini" | "openrouter"
    llm_model: str          # model id passed to the selected provider
    # T-04-01: keep the API key out of the auto-generated __repr__ so it never
    # surfaces in logs, FastAPI dependency errors, or unhandled-exception dumps.
    llm_api_key: str | None = field(repr=False, default=None)  # from GEMINI_API_KEY; None for stub
    # Same repr=False treatment as llm_api_key (T-04-01) — from OPENROUTER_API_KEY.
    openrouter_api_key: str | None = field(repr=False, default=None)
    # Separate from llm_model because llm_model's default "gemini-2.5-flash" is
    # not a valid OpenRouter slug.
    openrouter_model: str = _OPENROUTER_DEFAULT_MODEL
    # Browser origins allowed to call this API (BE-01, D-04). Not secret, so
    # this field carries no repr override — that treatment is reserved for the
    # two API key fields above.
    cors_origins: tuple[str, ...] = field(default=())
    oidc_provider: str = "fake"
    oidc_issuer: str = "http://shiftmind.test/oidc"
    oidc_client_id: str = "shiftmind-local"
    oidc_client_secret: str | None = field(repr=False, default=None)
    oidc_redirect_uri: str = "http://shiftmind.test/api/v1/auth/callback"
    app_base_url: str = "http://shiftmind.test"
    session_ttl_s: int = 3600
    # HMAC pepper for deriving the CSRF token from the session token (see
    # api/auth_security.py). Not itself persisted; a per-deployment secret
    # so a leaked session token alone can't also reconstruct the CSRF
    # token. repr=False for the same reason as the API keys above (T-04-01).
    csrf_secret: str = field(repr=False, default="shiftmind-local-csrf-secret")
    # AgentRuntime seam (Story 2.1, AD-19). Deliberately SEPARATE fields from
    # llm_provider/llm_model: the agent runtime and the task-specific
    # LLMProvider are two seams, and overloading one seam's configuration onto
    # the other is what makes them impossible to migrate independently later.
    agent_runtime_model: str = "test"
    # USD per million tokens. Zero means no configured price, not a free model.
    agent_model_input_usd_per_mtok: float = 0.0
    agent_model_output_usd_per_mtok: float = 0.0
    # `input_tokens` is a parent bucket that already includes cache tokens
    # (pydantic-ai's UsageBase), so `estimate_cost_usd` prices the non-cache
    # remainder at the input rate and cache tokens at these separate rates,
    # never both -- otherwise cache tokens are double-billed at full input
    # price (code review of story-5.1, decision 4). Zero means cache tokens
    # contribute nothing to the estimate; set explicitly to price them.
    agent_model_cache_read_usd_per_mtok: float = 0.0
    agent_model_cache_write_usd_per_mtok: float = 0.0
    # Same repr=False treatment as the other API keys (T-04-01).
    agent_runtime_api_key: str | None = field(repr=False, default=None)
    # AD-7: budgets are application configuration, never model output. These are
    # the defaults; a caller may tighten them per request via AgentBudgetV1.
    agent_runtime_request_limit: int = 8
    agent_runtime_tool_calls_limit: int = 8
    agent_runtime_deadline_seconds: float = 60.0
    agent_runtime_retries_limit: int = 2
    agent_runtime_total_tokens_limit: int = 32_768
    agent_availability_recency_seconds: float = 120.0
    site_max_concurrent_runs: int = 2
    scheduling_inspect_row_limit: int = 200
    scheduling_inspect_timeout_seconds: float = 5.0
    # scheduling_compute drains whole fact groups to compute a total, so it is
    # bounded separately from scheduling_inspect's page limit. Sized against
    # real data, not guessed: `sample_tiny_input` holds 1547 demand rows, and
    # task+family pushdown leaves 53-197 -- but `family` is optional, and
    # task-only pushdown leaves 218-295. 200 fails closed on five of six tasks.
    scheduling_compute_row_limit: int = 400
    scheduling_compute_timeout_seconds: float = 5.0
    scheduling_draft_timeout_seconds: float = 5.0
    scheduling_draft_max_constraints: int = 10
    # Governed solver ceilings (Story 3.2, AD-7). These are application-owned
    # inputs frozen into RunSnapshotV1; neither a model nor a caller chooses
    # them. Single-worker + deterministic time is the reproducible default.
    solver_engine_name: str = "cpsat"
    solver_seed: int = 42
    solver_num_search_workers: int = 1
    solver_max_deterministic_time: float = 30.0
    solver_wall_time_limit_seconds: float = 30.0
    lease_seconds: int = 120
    # AD-2 feature policy. `compose_granted_capabilities` refuses any module
    # whose `required_feature_policy` is absent here, so this is the supplier
    # that gate has always expected. It must NEVER be derived from the
    # installed set -- that makes the predicate unfalsifiable and grants every
    # installed module by construction.
    #
    # `demonstration` defaults OFF: it is a harness module (risk_class
    # "consequential", approval_policy "exact_action") that exists to prove
    # capability add/removal, and an approval suspension from it terminates a
    # real planner turn. Story 2.6's proof is unaffected -- it stays installed
    # and grantable whenever this flag is on.
    scheduling_compute_enabled: bool = True
    scheduling_draft_enabled: bool = True
    scheduling_inspect_enabled: bool = True
    scheduling_optimize_enabled: bool = True
    approval_expiry_seconds: int = 3600
    scheduling_baseline_enabled: bool = True
    demonstration_enabled: bool = False


def resolve_fixture_path(data_dir: str, fixture: str) -> str | None:
    """Resolve `fixture` against `data_dir`, rejecting any path that escapes it
    (an absolute path, or a relative path containing `../` sequences) — CR-03.

    `os.path.join(data_dir, fixture)` silently discards `data_dir` when
    `fixture` is absolute, and a relative `fixture` containing `../` can
    normalize outside `data_dir` even without being absolute; either lets a
    caller reference an arbitrary file on disk (path traversal).

    Returns the resolved absolute path, or None if `fixture` is invalid.
    Callers translate None into the appropriate "unknown fixture" response
    for their layer (400 at scenario-creation time, 404/LookupError at
    constraint-parse time) — never a bare filesystem error.
    """
    if os.path.isabs(fixture):
        return None
    data_dir_abs = os.path.abspath(data_dir)
    candidate = os.path.normpath(os.path.join(data_dir_abs, fixture))
    if candidate != data_dir_abs and not candidate.startswith(data_dir_abs + os.sep):
        return None
    return candidate


class InvalidFlagError(ValueError):
    """A feature-policy flag was set to something that is not a boolean."""


def _flag(name: str, raw: str | None, fallback: bool) -> bool:
    """Parse a feature-policy flag. Unset falls back; a malformed value RAISES.

    Falling back on an unrecognized token was fail-open in the direction that
    matters. For the two capabilities defaulting True, `SCHEDULING_COMPUTE_ENABLED
    =disabled` silently left the capability granted -- an operator's attempt to
    turn something off did nothing and said nothing. A flag that governs whether
    a governed capability reaches a live planner has to fail loudly at startup
    rather than quietly resolve to the more permissive answer.
    """
    if raw is None:
        return fallback
    normalized = raw.strip().lower()
    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False
    raise InvalidFlagError(
        f"{name}={raw!r} is not a boolean; use one of 1/true/yes/on or 0/false/no/off"
    )


# `_optional_int` and `_optional_float` were deleted here, not left unused.
# They documented that an explicit empty value means "no limit" (None) — the
# exact semantics AC2 reverses, since an unbounded ceiling is not a positive
# one. Leaving them beside the `_positive_*` helpers would invite the next
# editor to reach for the parser that cannot fail.


def _positive_int(name: str, raw: str | None, fallback: int) -> int:
    try:
        value = fallback if raw is None else int(raw)
    except ValueError as exc:
        raise InvalidFlagError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise InvalidFlagError(f"{name} must be a positive integer")
    return value


def _positive_float(name: str, raw: str | None, fallback: float) -> float:
    try:
        value = fallback if raw is None else float(raw)
    except ValueError as exc:
        raise InvalidFlagError(f"{name} must be a positive finite number") from exc
    if not math.isfinite(value) or value <= 0:
        raise InvalidFlagError(f"{name} must be a positive finite number")
    return value


def _non_negative_float(name: str, raw: str | None, fallback: float) -> float:
    try:
        value = fallback if raw is None else float(raw)
    except ValueError as exc:
        raise InvalidFlagError(f"{name} must be a non-negative finite number") from exc
    if not math.isfinite(value) or value < 0:
        raise InvalidFlagError(f"{name} must be a non-negative finite number")
    return value


def _nonempty(name: str, raw: str | None, fallback: str) -> str:
    value = fallback if raw is None else raw.strip()
    if not value:
        raise InvalidFlagError(f"{name} must not be empty")
    return value


def default_settings() -> Settings:
    """Read settings fresh each call so env overrides apply at request time."""
    db_path = os.environ.get("ROSTERAI_DB", str(_BACKEND_DIR / "var" / "rosterai.db"))
    data_dir = os.environ.get("ROSTERAI_DATA_DIR", str(_REPO_ROOT / "data"))
    # The API's own connection: a non-superuser login that carries no table
    # grants of its own and cannot bypass RLS. It authenticates only to reach
    # `SET LOCAL ROLE shiftmind_runtime` (domain reads) and the `auth.*`
    # SECURITY DEFINER functions (identity/session lifecycle) — see AD-23.
    database_url = os.environ.get(
        "ROSTERAI_DATABASE_URL",
        "postgresql+psycopg://shiftmind_login:shiftmind_login@localhost:5432/rosterai",
    )
    # A genuinely privileged connection, used only by Alembic (schema/role
    # DDL) and the operator-only seed_planner.py script — never by the
    # request-serving API process.
    provisioning_database_url = os.environ.get(
        "ROSTERAI_PROVISIONING_DATABASE_URL",
        "postgresql+psycopg://rosterai:rosterai@localhost:5432/rosterai",
    )
    maintenance_flag_path = os.environ.get(
        "ROSTERAI_MAINTENANCE_FLAG",
        str(_BACKEND_DIR / "var" / "gate-a-maintenance"),
    )
    llm_provider = os.environ.get("LLM_PROVIDER", "stub")
    llm_model = os.environ.get("LLM_MODEL", "gemini-2.5-flash")
    llm_api_key = os.environ.get("GEMINI_API_KEY")
    openrouter_api_key = os.environ.get("OPENROUTER_API_KEY")
    openrouter_model = os.environ.get("OPENROUTER_MODEL", _OPENROUTER_DEFAULT_MODEL)
    # The os.environ.get default only applies when CORS_ORIGINS is absent from
    # env entirely; an explicitly empty CORS_ORIGINS="" yields an empty
    # allow-list (a valid "no browser origin may call this" posture), not a
    # silent fallback to the default two Vite origins.
    cors_origins_raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:4173")
    cors_origins = tuple(o.strip() for o in cors_origins_raw.split(",") if o.strip())
    oidc_provider = os.environ.get("OIDC_PROVIDER", "fake")
    oidc_issuer = os.environ.get("OIDC_ISSUER", "http://shiftmind.test/oidc")
    oidc_client_id = os.environ.get("OIDC_CLIENT_ID", "shiftmind-local")
    oidc_client_secret = os.environ.get("OIDC_CLIENT_SECRET")
    oidc_redirect_uri = os.environ.get(
        "OIDC_REDIRECT_URI",
        "http://shiftmind.test/api/v1/auth/callback",
    )
    app_base_url = os.environ.get("APP_BASE_URL", "http://shiftmind.test")
    try:
        session_ttl_s = int(os.environ.get("SESSION_TTL_S", "3600"))
    except ValueError:
        session_ttl_s = 3600
    csrf_secret = os.environ.get("CSRF_SECRET", "shiftmind-local-csrf-secret")
    agent_runtime_model = os.environ.get("AGENT_RUNTIME_MODEL", "test")
    agent_runtime_api_key = os.environ.get("AGENT_RUNTIME_API_KEY")
    agent_model_input_usd_per_mtok = _non_negative_float(
        "AGENT_MODEL_INPUT_USD_PER_MTOK",
        os.environ.get("AGENT_MODEL_INPUT_USD_PER_MTOK"),
        0.0,
    )
    agent_model_output_usd_per_mtok = _non_negative_float(
        "AGENT_MODEL_OUTPUT_USD_PER_MTOK",
        os.environ.get("AGENT_MODEL_OUTPUT_USD_PER_MTOK"),
        0.0,
    )
    agent_model_cache_read_usd_per_mtok = _non_negative_float(
        "AGENT_MODEL_CACHE_READ_USD_PER_MTOK",
        os.environ.get("AGENT_MODEL_CACHE_READ_USD_PER_MTOK"),
        0.0,
    )
    agent_model_cache_write_usd_per_mtok = _non_negative_float(
        "AGENT_MODEL_CACHE_WRITE_USD_PER_MTOK",
        os.environ.get("AGENT_MODEL_CACHE_WRITE_USD_PER_MTOK"),
        0.0,
    )
    agent_runtime_request_limit = _positive_int(
        "AGENT_RUNTIME_REQUEST_LIMIT", os.environ.get("AGENT_RUNTIME_REQUEST_LIMIT"), 8
    )
    agent_runtime_tool_calls_limit = _positive_int(
        "AGENT_RUNTIME_TOOL_CALLS_LIMIT", os.environ.get("AGENT_RUNTIME_TOOL_CALLS_LIMIT"), 8
    )
    agent_runtime_deadline_seconds = _positive_float(
        "AGENT_RUNTIME_DEADLINE_SECONDS", os.environ.get("AGENT_RUNTIME_DEADLINE_SECONDS"), 60.0
    )
    agent_runtime_retries_limit = _positive_int(
        "AGENT_RUNTIME_RETRIES_LIMIT", os.environ.get("AGENT_RUNTIME_RETRIES_LIMIT"), 2
    )
    agent_runtime_total_tokens_limit = _positive_int(
        "AGENT_RUNTIME_TOTAL_TOKENS_LIMIT",
        os.environ.get("AGENT_RUNTIME_TOTAL_TOKENS_LIMIT"),
        32_768,
    )
    agent_availability_recency_seconds = _positive_float(
        "AGENT_AVAILABILITY_RECENCY_SECONDS",
        os.environ.get("AGENT_AVAILABILITY_RECENCY_SECONDS"),
        120.0,
    )
    site_max_concurrent_runs = _positive_int(
        "SITE_MAX_CONCURRENT_RUNS", os.environ.get("SITE_MAX_CONCURRENT_RUNS"), 2
    )
    scheduling_inspect_row_limit = _positive_int(
        "SCHEDULING_INSPECT_ROW_LIMIT", os.environ.get("SCHEDULING_INSPECT_ROW_LIMIT"), 200
    )
    scheduling_inspect_timeout_seconds = _positive_float(
        "SCHEDULING_INSPECT_TIMEOUT_SECONDS",
        os.environ.get("SCHEDULING_INSPECT_TIMEOUT_SECONDS"),
        5.0,
    )
    scheduling_compute_row_limit = _positive_int(
        "SCHEDULING_COMPUTE_ROW_LIMIT", os.environ.get("SCHEDULING_COMPUTE_ROW_LIMIT"), 400
    )
    scheduling_compute_timeout_seconds = _positive_float(
        "SCHEDULING_COMPUTE_TIMEOUT_SECONDS",
        os.environ.get("SCHEDULING_COMPUTE_TIMEOUT_SECONDS"),
        5.0,
    )
    scheduling_draft_timeout_seconds = _positive_float(
        "SCHEDULING_DRAFT_TIMEOUT_SECONDS",
        os.environ.get("SCHEDULING_DRAFT_TIMEOUT_SECONDS"),
        5.0,
    )
    scheduling_draft_max_constraints = _positive_int(
        "SCHEDULING_DRAFT_MAX_CONSTRAINTS",
        os.environ.get("SCHEDULING_DRAFT_MAX_CONSTRAINTS"),
        10,
    )
    solver_engine_name = _nonempty(
        "SOLVER_ENGINE_NAME", os.environ.get("SOLVER_ENGINE_NAME"), "cpsat"
    )
    solver_seed = _positive_int(
        "SOLVER_SEED", os.environ.get("SOLVER_SEED"), 42
    )
    solver_num_search_workers = _positive_int(
        "SOLVER_NUM_SEARCH_WORKERS",
        os.environ.get("SOLVER_NUM_SEARCH_WORKERS"),
        1,
    )
    solver_max_deterministic_time = _positive_float(
        "SOLVER_MAX_DETERMINISTIC_TIME",
        os.environ.get("SOLVER_MAX_DETERMINISTIC_TIME"),
        30.0,
    )
    solver_wall_time_limit_seconds = _positive_float(
        "SOLVER_WALL_TIME_LIMIT_SECONDS",
        os.environ.get("SOLVER_WALL_TIME_LIMIT_SECONDS"),
        30.0,
    )
    minimum_lease_seconds = math.ceil(solver_wall_time_limit_seconds * 4)
    lease_seconds = _positive_int(
        "LEASE_SECONDS",
        os.environ.get("LEASE_SECONDS"),
        max(60, minimum_lease_seconds),
    )
    if lease_seconds < minimum_lease_seconds:
        raise InvalidFlagError(
            "LEASE_SECONDS must be at least four times "
            "SOLVER_WALL_TIME_LIMIT_SECONDS"
        )
    scheduling_compute_enabled = _flag(
        "SCHEDULING_COMPUTE_ENABLED",
        os.environ.get("SCHEDULING_COMPUTE_ENABLED"), True
    )
    scheduling_draft_enabled = _flag(
        "SCHEDULING_DRAFT_ENABLED",
        os.environ.get("SCHEDULING_DRAFT_ENABLED"), True
    )
    scheduling_inspect_enabled = _flag(
        "SCHEDULING_INSPECT_ENABLED",
        os.environ.get("SCHEDULING_INSPECT_ENABLED"), True
    )
    scheduling_optimize_enabled = _flag(
        "SCHEDULING_OPTIMIZE_ENABLED",
        os.environ.get("SCHEDULING_OPTIMIZE_ENABLED"),
        True,
    )
    approval_expiry_seconds = _positive_int(
        "APPROVAL_EXPIRY_SECONDS", os.environ.get("APPROVAL_EXPIRY_SECONDS"), 3600
    )
    scheduling_baseline_enabled = _flag(
        "SCHEDULING_BASELINE_ENABLED", os.environ.get("SCHEDULING_BASELINE_ENABLED"), True
    )
    demonstration_enabled = _flag(
        "DEMONSTRATION_ENABLED", os.environ.get("DEMONSTRATION_ENABLED"), False
    )
    return Settings(
        db_path=db_path,
        data_dir=data_dir,
        database_url=database_url,
        provisioning_database_url=provisioning_database_url,
        maintenance_flag_path=maintenance_flag_path,
        llm_provider=llm_provider,
        llm_model=llm_model,
        llm_api_key=llm_api_key,
        openrouter_api_key=openrouter_api_key,
        openrouter_model=openrouter_model,
        cors_origins=cors_origins,
        oidc_provider=oidc_provider,
        oidc_issuer=oidc_issuer.rstrip("/"),
        oidc_client_id=oidc_client_id,
        oidc_client_secret=oidc_client_secret,
        oidc_redirect_uri=oidc_redirect_uri,
        app_base_url=app_base_url.rstrip("/"),
        session_ttl_s=session_ttl_s,
        csrf_secret=csrf_secret,
        agent_runtime_model=agent_runtime_model,
        agent_runtime_api_key=agent_runtime_api_key,
        agent_model_input_usd_per_mtok=agent_model_input_usd_per_mtok,
        agent_model_output_usd_per_mtok=agent_model_output_usd_per_mtok,
        agent_model_cache_read_usd_per_mtok=agent_model_cache_read_usd_per_mtok,
        agent_model_cache_write_usd_per_mtok=agent_model_cache_write_usd_per_mtok,
        agent_runtime_request_limit=agent_runtime_request_limit,
        agent_runtime_tool_calls_limit=agent_runtime_tool_calls_limit,
        agent_runtime_deadline_seconds=agent_runtime_deadline_seconds,
        agent_runtime_retries_limit=agent_runtime_retries_limit,
        agent_runtime_total_tokens_limit=agent_runtime_total_tokens_limit,
        agent_availability_recency_seconds=agent_availability_recency_seconds,
        site_max_concurrent_runs=site_max_concurrent_runs,
        scheduling_inspect_row_limit=scheduling_inspect_row_limit,
        scheduling_inspect_timeout_seconds=scheduling_inspect_timeout_seconds,
        scheduling_compute_row_limit=scheduling_compute_row_limit,
        scheduling_compute_timeout_seconds=scheduling_compute_timeout_seconds,
        scheduling_draft_timeout_seconds=scheduling_draft_timeout_seconds,
        scheduling_draft_max_constraints=scheduling_draft_max_constraints,
        solver_engine_name=solver_engine_name,
        solver_seed=solver_seed,
        solver_num_search_workers=solver_num_search_workers,
        solver_max_deterministic_time=solver_max_deterministic_time,
        solver_wall_time_limit_seconds=solver_wall_time_limit_seconds,
        lease_seconds=lease_seconds,
        scheduling_compute_enabled=scheduling_compute_enabled,
        scheduling_draft_enabled=scheduling_draft_enabled,
        scheduling_inspect_enabled=scheduling_inspect_enabled,
        scheduling_optimize_enabled=scheduling_optimize_enabled,
        approval_expiry_seconds=approval_expiry_seconds,
        scheduling_baseline_enabled=scheduling_baseline_enabled,
        demonstration_enabled=demonstration_enabled,
    )
