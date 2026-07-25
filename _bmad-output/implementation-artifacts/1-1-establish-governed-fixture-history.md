---
baseline_commit: d4280b377015e937543f5ae9cd1387c6ac08d340
---

# Story 1.1: Establish Governed Fixture History [Technical Enabler]

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a portfolio operator,
I want predefined fixtures imported into site-scoped PostgreSQL history,
so that the planner starts from immutable, checksummed scenario facts rather than ambiguous legacy state.

Unblocks: Story 1.3 (fixture catalogue) and every later scenario-read story. This is the **first PostgreSQL-backed story in the project** — today the app is 100% SQLite (`backend/store/db.py`). Nothing in this story depends on any other Epic-1 story.

## Acceptance Criteria

1. **Given** the existing SQLite demo data and a declared maintenance window, **when** the Gate A cutover is executed, **then** legacy writes are disabled, the in-process worker is drained or cancelled, and SQLite is snapshotted before checksummed predefined fixtures are imported as immutable site-owned `scenario_version` records, **and** legacy scenarios and runs remain offline and no runtime adapter exposes both histories or fabricates governed history. *(AR25)*

2. **Given** the first governed fixture import, **when** migrations are applied, **then** only the organization, site, scenario, scenario-version, fixture-lineage, and evidence-reference structures required by this story are created, **and** tenant tables carry `site_id`, forced RLS, server-generated identifiers, immutable version/checksum fields, and no planner-facing mutation grant. *(AR4, AR23)*

3. **Given** the same fixture package is imported again, **when** its canonical checksum and version already exist, **then** the import is idempotent and returns the existing semantic result, **and** a conflicting payload for the same fixture version fails without changing stored history. *(NFR6)*

## Tasks / Subtasks

- [x] Task 1: Add the PostgreSQL toolchain (AC: #2)
  - [x] Add `sqlalchemy==2.0.51`, `psycopg[binary]==3.3.4` (repo target: `psycopg` v3, **not** `psycopg2`), `alembic==1.18.5` to `backend/pyproject.toml` per the architecture Stack table — these are "planned seed" and this story is their implementation gate (AR27), so lock the exact versions now.
  - [x] Add `DATABASE_URL` to `backend/settings.py` `Settings`/`default_settings()` following the existing `db_path`/`data_dir` env-override pattern (e.g. `ROSTERAI_DATABASE_URL`, default `postgresql+psycopg://rosterai:rosterai@localhost:5432/rosterai` for local dev). Do **not** remove `db_path` — legacy SQLite stays wired for the snapshot step in Task 3.
  - [x] Add a local Postgres dev/test service (no docker-compose exists yet in the repo) — a `docker-compose.yml` at repo root with a single `postgres:18` service is the simplest option consistent with the architecture's RDS 18.4 target.
  - [x] `alembic init backend/migrations` per the Structural Seed path (`backend/migrations/`), wire `env.py` to a SQLAlchemy `MetaData` object and to `DATABASE_URL` from `settings.py` (see Dev Notes → Alembic wiring).

- [x] Task 2: New adapter module + schema migration (AC: #2)
  - [x] Create `backend/adapters/postgres/` (Structural Seed path — new work converges here, not into `backend/store/`, which is frozen legacy per AD-25).
  - [x] Write the first Alembic revision creating **only**: `organization`, `site`, `scenario`, `scenario_version`, `fixture_lineage`, `evidence_reference`. Do not create membership/conversation/agent/job tables — those belong to later stories (AR22 aggregate ownership; don't widen the bundle).
  - [x] Every tenant table carries `site_id`, `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` (AD-23). Server-generated UUID primary keys (no client-supplied IDs). `scenario_version` columns are append-only/immutable: no `UPDATE`/`DELETE` grant for the runtime application role, only `INSERT`/`SELECT`.
  - [x] `scenario_version` stores: scenario/version IDs, the raw fixture JSON payload (JSONB — the existing "Scenario Range / Task / Function / ..." table shape from `backend/ingest/input_adapter.py`, unchanged; normalization into `ScenarioProjectionV1` is Story 1.4's job, not this one), a SHA-256 checksum, and import timestamp.
  - [x] `fixture_lineage` records which source fixture file/package produced each `scenario_version` (import provenance, not agent evidence).
  - [x] Full AD-23 role model (NOLOGIN owner, migrator-only `SET ROLE`, `SECURITY DEFINER` functions) is architecture-wide; implement the slice this story needs — forced RLS + no mutation grant for the runtime role — without inventing the auth/session functions Story 1.2 owns.

- [x] Task 3: Gate A maintenance-window cutover (AC: #1)
  - [x] Write a one-shot cutover script (e.g. `backend/scripts/gate_a_cutover.py`, alongside the existing `backend/scripts/` module) that: (a) flips a flag/env var so `backend/api/main.py` refuses new mutating requests against the SQLite-backed routes, (b) drains/cancels the worker pool in `services/run_service.py` (`_pool` / `_pool_lock`), (c) copies the SQLite file (`Settings.db_path`) to a timestamped snapshot path, (d) imports each predefined fixture (currently `data/sample_tiny_input.json`, `data/sample_tiny_input_more_tm.json`) as a checksummed `scenario_version` via Task 2's adapter.
  - [x] Do **not** write a runtime code path that reads both `backend/store/` (SQLite) and `backend/adapters/postgres/` — the legacy repos/services stay as-is and untouched for historical reference only; nothing new imports them.
  - [x] The existing `scenarios`/`runs` SQLite tables and the fixtures they reference remain offline (readable only via the pre-cutover snapshot file) — no story migrates their row data into `scenario_version`; only the fixture JSON is reimported as new governed history.

- [x] Task 4: Idempotent, checksum-based import (AC: #3)
  - [x] Compute the fixture checksum as SHA-256 over RFC 8785 canonical JSON, storing algorithm + schema version beside the digest (AD-20 — this is the project's one canonical hashing rule; reuse it verbatim rather than inventing a second hashing scheme later).
  - [x] Re-importing a fixture whose canonical checksum and version already exist in `scenario_version` returns the existing row's semantic result (no new row, no error).
  - [x] Importing a *different* payload under the same fixture version (checksum mismatch for that version) fails the import and leaves stored history unchanged — enforce via a DB uniqueness constraint on `(site_id, fixture_id, version)`, not just application logic, so a race can't double-import.

- [x] Task 5: Tests
  - [x] Migration test: `alembic upgrade head` then `alembic downgrade base` round-trips cleanly against a fresh Postgres instance.
  - [x] RLS test: a session scoped to site A cannot read/write a `scenario_version` row belonging to site B (set `site_id` via a transaction-local session variable; assert zero cross-site rows visible) — this is the first NFR1 tenant-isolation proof and later stories will extend it.
  - [x] Idempotent import test: import the same fixture twice, assert one row and the same returned `scenario_version` id/checksum.
  - [x] Conflict test: import a mutated payload under the same fixture version, assert rejection and zero change to stored history.
  - [x] Cutover script test: run the cutover against a throwaway SQLite copy + throwaway Postgres, assert a snapshot file is created, the worker pool reports drained, and both fixtures land as checksummed `scenario_version` rows.

## Dev Notes

- **This is a from-scratch infra story.** The repo currently has zero SQLAlchemy/Alembic/Postgres code — everything in `backend/store/`, `backend/services/scenario_service.py`, `backend/services/run_service.py` is SQLite and is **legacy** as of this story (AD-25: "no runtime adapter exposes both histories"). Do not extend those files; do not delete them either (they're the source the cutover script snapshots/reads).
- **Domain stays pure.** Per AD-1/AR1, `backend/domain/` must not import SQLAlchemy/psycopg — this story's code lives entirely in `backend/adapters/postgres/`, `backend/migrations/`, and `backend/scripts/`, none of which the domain layer touches.
- **Fixture payload shape is unchanged.** The raw fixture JSON (`Scenario Range`, `Task`, `Function`, `EBA Grade Rate`, `Outbound Workload`, etc. — see `backend/ingest/input_adapter.py:52-80` for the table names this format uses) is stored as-is in `scenario_version` as JSONB. This story does **not** build the normalized `ScenarioProjectionV1` read contract — that is Story 1.4, which will read `scenario_version.payload` and project it.
- **Scope discipline (AR22 aggregate ownership):** this story owns exactly `organization`, `site`, `scenario`, `scenario_version`, `fixture_lineage`, `evidence_reference`. Membership/session (Story 1.2), fixture catalogue API (Story 1.3), and the normalized projection (Story 1.4) are explicitly out of scope — don't pre-build their tables or endpoints even though they're adjacent.
- **AD-23 role model is architecture-wide, not fully this story's job.** Implement only: `FORCE ROW LEVEL SECURITY` on every tenant table, and a runtime role with no `UPDATE`/`DELETE` grant on `scenario_version`. The `SECURITY DEFINER auth.resolve_session` function and full NOLOGIN-owner/migrator split belong to Story 1.2 (session/membership) — note the shape here so Story 1.2 doesn't have to retrofit RLS onto tables this story already created.
- **AD-20 canonical hashing is the one hash rule for the whole project** — SHA-256 over RFC 8785 canonical JSON, digest stored beside algorithm/schema version. Every later evidence/approval/audit hash reuses this exact rule; get it right here since it's the first implementation.

### Project Structure Notes

- New code goes under `backend/adapters/postgres/` and `backend/migrations/` (Alembic), plus a `backend/scripts/gate_a_cutover.py` entry point — all per the architecture's Structural Seed (`ARCHITECTURE-SPINE.md` → Structural Seed block).
- `backend/store/`, `backend/services/scenario_service.py`, `backend/services/run_service.py` (SQLite) are **not touched** by this story; they remain functional legacy code referenced only by the cutover snapshot step.
- No `docker-compose.yml` exists in the repo today — this story introduces the first one, for local/CI Postgres only (not a broader deployment change).
- `backend/pyproject.toml` currently has no PostgreSQL/ORM/migration dependencies at all — this story adds the first ones.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.1: Establish Governed Fixture History] — story statement and acceptance criteria (lines 324-347)
- [Source: _bmad-output/planning-artifacts/epics.md#AR4, AR23, AR25, AR20, AR22, AR27, AR26] — Additional Requirements referenced by this story
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md#AD-1, AD-3, AD-4, AD-20, AD-23, AD-25] — invariants this story must satisfy
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md#Stack] — pinned versions: SQLAlchemy 2.0.51, Psycopg 3.3.4, Alembic 1.18.5, PostgreSQL/RDS 18.4 (all "planned seed" — first locked here)
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md#Structural Seed] — `backend/adapters/`, `backend/migrations/` target paths
- [Source: _bmad-output/planning-artifacts/requirements-inventory.md#NFR6] — idempotent recovery requirement behind AC #3
- [Source: backend/store/db.py] — legacy SQLite schema/connection being snapshotted and retired at runtime
- [Source: backend/settings.py] — existing env-override settings pattern to extend with `DATABASE_URL`
- [Source: backend/ingest/input_adapter.py:52-80] — raw fixture JSON table shape stored verbatim in `scenario_version`
- [Source: backend/services/run_service.py] — worker pool (`_pool`/`_pool_lock`) that the cutover script must drain
- Alembic `env.py` wiring pattern: https://alembic.sqlalchemy.org (Context7 `/websites/alembic_sqlalchemy`) — `context.configure(connection=connection, target_metadata=target_metadata)` inside `run_migrations_online()`, engine built from `DATABASE_URL` via `engine_from_config`.
- SQLAlchemy 2.0 psycopg (v3) dialect: connection URL scheme is `postgresql+psycopg://` (distinct from the `+psycopg2` scheme shown in the current SQLAlchemy 2.0 docs) — confirm against `psycopg==3.3.4` installed in this story before wiring `create_engine`.

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

- Task 1 RED: `uv run --frozen pytest tests/test_postgres_toolchain.py -q` failed 5/5 against the pre-story toolchain.
- Task 1 implementation plan: pin and lock the architecture versions, preserve SQLite settings, add a single-service PostgreSQL Compose model, and wire Alembic to application settings plus shared SQLAlchemy metadata.
- Task 1 GREEN/regression: 5 focused tests and 158 backend tests passed; Compose config rendered successfully; installed versions reported Alembic 1.18.5, psycopg 3.3.4, and SQLAlchemy 2.0.51.
- Task 2 RED: schema contracts failed against empty metadata and a missing first revision.
- Task 2 implementation plan: model only the six owned aggregates, bind cross-table references to the same site, enforce checksummed append-only versions, then add forced RLS and the bounded NOLOGIN runtime role slice in the migration.
- Task 2 GREEN/regression: 6 schema tests and 164 backend tests passed; a live PostgreSQL 18 upgrade/downgrade/upgrade round trip succeeded; live catalog checks confirmed exactly six story tables, forced RLS, and only `SELECT`/`INSERT` on `scenario_version`.
- Task 3 RED: cutover tests initially failed because the maintenance script and PostgreSQL fixture-history adapter did not exist.
- Task 3 implementation plan: persist the mutation lock as an env-configurable flag file, drain/cancel the frozen legacy worker through its existing pool boundary, use SQLite's consistent backup API, and pass only raw predefined fixture payloads to the new adapter.
- Task 3 GREEN/regression: 2 focused cutover tests and 166 backend tests passed; the tests proved mutation refusal, worker drain/cancel, snapshot preservation, and exactly two raw fixture imports without touching developer data.
- Task 4 RED: the RFC 8785/import suite initially failed because no canonical JSON module existed.
- Task 4 implementation plan: implement I-JSON validation, ECMAScript-compatible number serialization, UTF-16 property sorting, SHA-256 metadata, and a savepoint-backed insert/replay path that relies on the database uniqueness key under races.
- Task 4 GREEN/regression: 32 focused tests and 198 backend tests passed, including the RFC 8785 sample, UTF-16 ordering, all published Appendix B numeric vectors, live replay identity, and live conflict rollback.
- Task 5 RED: the isolated database test exposed that a cluster-wide runtime role could not be dropped while another database still depended on it.
- Task 5 implementation plan: create/dispose a unique PostgreSQL database for migration round trips, exercise RLS under `SET LOCAL` transaction context, and run the complete cutover against throwaway SQLite plus the real PostgreSQL adapter.
- Task 5 GREEN/regression: 3 live integration tests and 201 backend tests passed; Alembic reported no schema drift; Python compilation passed; frontend regression was 239 tests plus clean typecheck, with lint completing successfully and reporting only four pre-existing Fast Refresh warnings.
- Task 5 isolation hardening: all live PostgreSQL tests now provision, migrate, and force-drop unique throwaway databases; 35 focused PostgreSQL tests passed and the locally created Docker database was reset to an empty migrated schema.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created
- Task 1 complete: PostgreSQL dependencies are exactly locked, `ROSTERAI_DATABASE_URL` is configurable without removing legacy SQLite, local PostgreSQL 18 is available through Compose, and Alembic is initialized at the structural seed path.
- Task 2 complete: the bounded six-table adapter schema uses server UUIDs, JSONB raw payloads, site-bound foreign keys, checksum constraints, provenance lineage, forced RLS, and immutable `scenario_version` enforcement without introducing later-story auth/session structures.
- Task 3 complete: the one-shot Gate A script leaves the maintenance flag active, drains legacy work before snapshotting, preserves SQLite history offline, and imports fixture JSON only; no runtime adapter combines legacy and governed histories.
- Task 4 complete: AD-20 canonical hashing is implemented once, replay returns the existing semantic result, and same-version checksum conflicts fail transactionally while the database uniqueness constraint closes the race window.
- Task 5 complete: migration upgrade/downgrade, cross-site RLS denial, idempotent replay, conflict rollback, and the two-fixture Gate A cutover are all automated and live-verified against PostgreSQL 18.
- Test isolation complete: immutable integration rows never accumulate in the persistent local database; only the disposable databases created by each test module are mutated.
- Definition of Done complete: all acceptance criteria and tasks are satisfied; backend and frontend regression suites, schema drift, compilation, typecheck, and lint gates passed.

### File List

- _bmad-output/implementation-artifacts/1-1-establish-governed-fixture-history.md
- _bmad-output/implementation-artifacts/sprint-status.yaml
- alembic.ini
- backend/.env.example
- backend/adapters/__init__.py
- backend/adapters/postgres/__init__.py
- backend/adapters/postgres/canonical_json.py
- backend/adapters/postgres/fixture_history.py
- backend/adapters/postgres/schema.py
- backend/api/main.py
- backend/conftest.py
- backend/migrations/README
- backend/migrations/env.py
- backend/migrations/script.py.mako
- backend/migrations/versions/d128d081ab48_establish_governed_fixture_history.py
- backend/pyproject.toml
- backend/scripts/__init__.py
- backend/scripts/gate_a_cutover.py
- backend/settings.py
- backend/tests/test_fixture_history_import.py
- backend/tests/test_gate_a_cutover.py
- backend/tests/test_postgres_schema.py
- backend/tests/test_postgres_integration.py
- backend/tests/test_postgres_toolchain.py
- backend/uv.lock
- docker-compose.yml

## Change Log

- 2026-07-24: Implemented governed PostgreSQL fixture history, Gate A cutover controls, RFC 8785 checksum idempotency, forced RLS, and complete live integration coverage; moved story to review.
- 2026-07-25: Code review complete (2 decision-needed, 5 patch, 3 defer, 10 dismissed). Both decisions resolved with the user (Gate A drain documented as an offline runbook; `site` RLS policy confirmed correct as designed). All 5 patches applied and covered by new/updated tests; full backend suite green (206 passed). Moved story to done.

### Review Findings

- [x] [Review][Patch] Gate A worker-pool drain cannot reach the live server process (resolved as documentation) — confirmed with the user: Gate A is an offline maintenance operation. The runbook is (1) disable supervisor auto-restart / scale the API to zero, (2) stop the running `uvicorn` process and wait for it to fully exit — process termination is the authoritative worker-drain boundary, (3) run `gate_a_cutover.py`, which writes the persistent maintenance flag before snapshot/import, (4) restart only after validating the import. `_drain_worker_pool()` is a defensive same-process check only (for tests/programmatic invocation), not a substitute for step 2. No admin endpoint introduced — no authenticated admin model exists yet. Documented in the module docstring and `_drain_worker_pool()`'s own docstring in `backend/scripts/gate_a_cutover.py`.
- [x] [Review][Defer] `site` table RLS policy scope (`site.id = app.site_id`) — confirmed correct as designed, not a defect. Gate A's `ensure_seed_site()` bootstrap lookup-by-name is a privileged migrator-context operation (runs as the migrator/owner role, exempt from RLS by nature), not evidence the policy is wrong. Story 1.2's real runtime session flow must resolve `site_id` via `auth.resolve_session()` before beginning any RLS-scoped domain transaction — never by querying org+name. Recorded invariant for Story 1.2: **add a test proving a Site A runtime session cannot enumerate Site B, even within the same organization.**

- [x] [Review][Patch] Legacy scenarios/runs stay live-readable via GET after cutover, contradicting Task 3's explicit "remain offline (readable only via the pre-cutover snapshot file)" requirement [backend/api/main.py:32-50] — fixed: the Gate A gate now matches on legacy route prefixes (`/scenarios`, `/runs`, `/constraints`) for all HTTP methods, not just mutating verbs; `/health` and `/fixtures` (not SQLite-backed) stay available. Covered by `test_api_refuses_legacy_reads_when_cutover_flag_exists`.
- [x] [Review][Patch] `ensure_seed_site` has no unique constraint or conflict handling against concurrent runs, unlike the sibling `scenario` insert in the same file [backend/adapters/postgres/fixture_history.py:61-93] — fixed with a transaction-scoped Postgres advisory lock keyed on a Python-side hash of `(organization_name, site_name)`, per the user's guidance not to impose a schema-level uniqueness constraint on human-readable names (an undecided, broader domain question). Covered by `test_ensure_seed_site_is_race_safe_under_concurrent_calls`.
- [x] [Review][Patch] `canonicalize_json` silently loses precision for integers outside ±2^53 by routing them through `float()` instead of rejecting them [backend/adapters/postgres/canonical_json.py:45-54] — fixed: now raises `ValueError` when the float round-trip doesn't reproduce the original integer exactly. Covered by `test_rfc8785_rejects_integers_that_would_silently_lose_precision`.
- [x] [Review][Patch] Maintenance flag check uses `.is_file()`, which silently fails open (permits mutations) if the path ever resolves to something other than a regular file [backend/api/main.py:37] — fixed: `_gate_a_flag_is_set()` now uses `.exists()` (any file/dir/symlink present counts as active) and fails closed (treats as active) on any `OSError` while checking. Normal operation (path absent) is unaffected. Covered by `test_api_treats_directory_at_flag_path_as_maintenance_active`.
- [x] [Review][Patch] Test teardown swallows `DROP DATABASE ... WITH (FORCE)` failures silently, allowing throwaway test databases to leak with no signal [backend/conftest.py:65-71] — fixed: now emits a `UserWarning` naming the database and the underlying exception instead of a bare `except: pass`. Covered by `test_temporary_database_cleanup_warns_on_drop_failure`.

- [x] [Review][Defer] `canonicalize_json`'s recursive `_serialize` has no depth guard; a pathologically deep payload raises an uncaught `RecursionError` [backend/adapters/postgres/canonical_json.py:63-83] — deferred, pre-existing (only reachable via trusted, shallow fixture files today)
- [x] [Review][Defer] `PostgresFixtureHistoryAdapter` uses a synchronous SQLAlchemy engine with no async/thread-offload [backend/adapters/postgres/fixture_history.py:44-53] — deferred, pre-existing (not yet called from a live request handler; next story to call it from a FastAPI endpoint must route it through a worker thread)
