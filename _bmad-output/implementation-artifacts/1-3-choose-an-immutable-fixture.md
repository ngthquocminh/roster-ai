---
baseline_commit: 4677bbb37c896a6d1b8e535442c3ba9078c303d0
---

# Story 1.3: Choose an Immutable Fixture

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want a catalogue of predefined scenarios,
so that I can deliberately choose the exact fixture and version I will inspect.

**Depends on:** Story 1.1 (done) — `scenario` / `scenario_version` tables, forced RLS, `shiftmind_runtime` SELECT grants, checksummed fixture rows. Story 1.2 (done) — opaque BFF session, `get_session`, `get_site_context`, `/api/v1` enforcement middleware, `RequireSession` guard.
**Unblocks:** Story 1.7 (Scenario Data workspace mounts inside the workspace shell this story starts) and every scenario-scoped surface in Epics 2–4.

**This is the first governed planner-facing UI.** It replaces the legacy SQLite Home/Editor screens at `/` and `/scenarios/:scenarioId`, which have been dark since Story 1.1's Gate A cutover (AD-25). See Task 5 — retiring them is part of the story, not optional cleanup.

## Acceptance Criteria

1. **Given** an authenticated site session with available fixtures, **when** the planner opens the application, **then** the fixture catalogue lists only authorized immutable fixture versions with stable IDs and deterministic ordering, **and** selecting a row opens that scenario without changing or copying its source data. *(FR22, AD-4)*

2. **Given** the fixture catalogue, **when** it renders in loading, empty, error, cached-stale, and loaded states, **then** each state uses the required skeleton, safe copy, retry behavior, and authorization checks, **and** there is no create, upload, import, edit, or delete action. *(UX-DR4, UX-DR23, UX-DR25)*

3. **Given** a selected fixture, **when** the scenario workspace opens, **then** a persistent context names scenario, scenario ID, immutable fixture version, and baseline version, **and** changing scenario returns through the catalogue rather than occurring implicitly. *(UX-DR1, UX-DR2)*

## Tasks / Subtasks

- [ ] Task 1: Owned catalogue read port + PostgreSQL adapter (AC: #1, #3)
  - [ ] `backend/application/ports/scenario_catalogue.py` — a `ScenarioCatalogueReader` `Protocol` with `list_fixture_versions(connection) -> tuple[FixtureCatalogueEntry, ...]` and `get_scenario_context(connection, scenario_id) -> ScenarioContext | None`, plus the two frozen dataclasses. Mirror the shape of `backend/application/ports/session.py` (frozen dataclasses + `Protocol`, no SQLAlchemy import in the port module beyond the `Connection` type — if that bothers the boundary, type the parameter as `Any` in the port and keep SQLAlchemy in the adapter).
  - [ ] `backend/adapters/postgres/scenario_catalogue.py` — the adapter. **It takes an already-open, already-site-scoped `Connection`; it must NOT create its own engine.** `get_site_context` (`backend/api/deps.py:107-133`) is the only supported way to reach domain data: it opens the transaction, sets `app.site_id` from the session row, and `SET LOCAL ROLE shiftmind_runtime`. A second engine would run as `shiftmind_login`, which holds no table grants of its own (NOINHERIT) — every query would fail, and if it somehow didn't, it would bypass the site scoping AD-3 requires.
  - [ ] **Never accept a `site_id` from the request** — not from path, query, body, or header. Row visibility comes entirely from the transaction-local `app.site_id` that `get_site_context` set from the session row, backed by Story 1.1's `USING (site_id = NULLIF(current_setting('app.site_id', true), '')::uuid)` policy on `scenario` and `scenario_version` (`backend/migrations/versions/d128d081ab48_...py:241-263`). Queries carry no site predicate at all.
  - [ ] Catalogue row = one `scenario_version` joined to its `scenario`. Select: `scenario.id`, `scenario.fixture_id`, `scenario.name`, `scenario_version.id`, `scenario_version.version`, `checksum_algorithm`, `checksum_schema_version`, `checksum_digest`, `imported_at`, `site_id`.
  - [ ] **Deterministic ordering is server-defined and must include a stable-ID tie-break** (AD-4, UX-DR24): `ORDER BY scenario.fixture_id, scenario_version.version, scenario_version.id`. No client-supplied sort in this story (sorting/filtering is Story 1.8, and only for Scenario Data tables).
  - [ ] `get_scenario_context` returns scenario name, scenario ID, the immutable fixture version, checksum, `site_id`, and `baseline_schedule_version` — see the Dev Notes entry **"Baseline version does not exist yet"** before you implement that last field.
  - [ ] **Multiple versions of one fixture:** the route map has no version segment (`/scenarios/:scenarioId` only — UX-DR1), so `get_scenario_context` resolves the scenario's governed version deterministically with the same server-defined ordering, taking the last: `ORDER BY version DESC, id DESC LIMIT 1`. Today exactly one version exists per fixture, so this is a documented tie-break, not a behavior change — and it is why the catalogue row still names the version explicitly. Do not invent `/scenarios/:id/versions/:version`.
  - [ ] **No migration.** Story 1.1 already granted `SELECT` on `scenario`/`scenario_version` to `shiftmind_runtime` (`d128d081ab48_...py:265-269`). This story adds no table, no column, no grant, and no Alembic revision. `alembic check` must still report zero drift.

- [ ] Task 2: Versioned read endpoints (AC: #1, #3)
  - [ ] New router `backend/api/routers/scenario_catalogue.py`, mounted with `app.include_router(scenario_catalogue.router, prefix="/api/v1")` in `backend/api/main.py` beside the existing `auth` include. The legacy unversioned `/scenarios` router stays mounted and untouched — it is Gate-A-503'd (AD-25) and nothing here modifies it. There is no path collision: the new paths are `/api/v1/scenarios` and `/api/v1/scenarios/{scenario_id}`.
  - [ ] `GET /api/v1/scenarios` → the ordered catalogue. `GET /api/v1/scenarios/{scenario_id}` → the workspace context for one scenario.
  - [ ] **Both handlers are `def`, not `async def`.** They depend on `get_site_context`, which drives a *synchronous* SQLAlchemy engine. A sync `def` path operation runs in FastAPI's threadpool; an `async def` one would block the event loop on every request. This is the explicit closure of Story 1.1's deferred item: *"the next story that calls it from a live FastAPI request handler must route it through a worker thread."*
  - [ ] **Add no auth code.** `enforce_versioned_session_and_csrf` (`backend/api/main.py:143-200`) already 401s any `/api/v1/*` path outside `_PUBLIC_VERSIONED_PATHS` and stashes the resolved session on `request.state`. `Depends(get_site_context)` reuses that session. Do not register a second middleware, a second cookie read, or a route-level session check.
  - [ ] **GET only.** Do not define `POST`/`PUT`/`PATCH`/`DELETE` on any `/api/v1/scenarios*` path — not even a stub, not even one returning 405. FR22 and Story 1.9's mutation-path audit read the OpenAPI document; an unused write verb there is a Gate A failure.
  - [ ] Unknown scenario id, or one belonging to another site: **404 with the same problem shape as absence** — never 403, never a distinguishing message. RLS makes the row invisible, so the adapter naturally returns `None`; raise `HTTPException(404)` and let `versioned_http_problem` (`backend/api/main.py:57-86`) render `resource_not_found`. Response bodies for 401/404 must contain no fixture name, scenario name, site name, or membership field.
  - [ ] Response models in `backend/api/schemas.py` next to `AuthSessionOut`: `FixtureCatalogueEntryOut` and `ScenarioContextOut`. Each carries `schema_version: str = "v1"` and `site_id` (the Structural Seed's normative contract minimum: *"Every contract carries `schema_version`; site-owned resources carry `site_id`"*). **Do not name anything `ScenarioProjectionV1` or put normalized workforce/demand/assignment data in these models** — that contract is Story 1.4's, and duplicating a partial version of it here is exactly the viewer/agent fact drift AD-4 exists to prevent.
  - [ ] Regenerate contracts after the routes exist: `npm run codegen` from `frontend/`. `frontend/src/api/schema.d.ts` is generated — never hand-edit (AD-13).

- [ ] Task 3: Fixture catalogue route and its five states (AC: #1, #2)
  - [ ] `frontend/src/api/scenarioCatalogue.ts` — thin typed wrappers over the one `client` (`frontend/src/api/client.ts`; its docstring forbids a second client). Derive every shape from the generated `paths` type; hand-author no response interface. Throw `{ status: response.status, ...error }` on failure, matching `api/auth.ts` / `api/scenarios.ts`.
  - [ ] `frontend/src/hooks/useFixtureCatalogue.ts` and `useScenarioContext.ts` — thin TanStack Query wrappers, no business logic (the repo rule; see `useSession.ts`). Query keys: `["fixture-catalogue"]` and `["scenario-context", scenarioId]`.
  - [ ] `frontend/src/routes/FixtureCatalogue.tsx` — route composition only; presentational parts go in `frontend/src/features/fixture-catalogue/`. **This story creates `frontend/src/features/`**, the Structural Seed's home for new UI work (AR26), the way Story 1.2 created `backend/application/`. Do not add to `frontend/src/components/{editor,runs,results,scenarios}/` — those are legacy leaves.
  - [ ] View heading is literally **“Fixture catalogue”** (the surface's name in the experience contract), focused on route change per Task 6. Render the catalogue as a **semantic table**: `<caption>`, `<th scope="col">`, one row per fixture version. Columns: scenario name, scenario ID, fixture version, imported at. Format `imported_at` with the existing `frontend/src/lib/formatTimestamp.ts` — do not write a second date formatter. Row activation is a **real link** to `/scenarios/:scenarioId` (anchor semantics, so Enter works natively and middle-click/Back behave — UX-DR26). No checkbox, no row-selection styling, no overflow menu, no editable-cell affordance (UX-DR4).
  - [ ] Implement all five states with the **exact copy from the experience contract's State Patterns table** (`EXPERIENCE.md:122`):
    - Cold/loading → skeleton rows plus “Loading predefined scenarios…”. Skeleton shapes match the final table region and impersonate no values.
    - Empty → “No predefined scenarios are available.” **No creation CTA.**
    - Error/unavailable → inline alert with retry. Authentication failure (401) routes to sign-in **without exposing fixture names** — `RequireSession` already handles a null session; make sure a 401 from *this* query never renders a partially-populated table.
    - Cached-stale → label “Saved catalogue — refresh unavailable”; selecting still requires current authorization (the navigation target re-fetches under the session; nothing is authorized from cache).
    - Loaded → the ordered table.
  - [ ] **There is no create, upload, import, edit, or delete control anywhere on this route.** Concretely: the “New Scenario” button, `CreateScenarioDialog`, and `ScenarioTable` that `routes/Home.tsx` renders today are all removed from `/` (Task 5).
  - [ ] Copy discipline (UX-DR5): literal, operational, bounded. No “Get started”, no “Create your first scenario”, no celebration, no invented counts.

- [ ] Task 4: Scenario workspace shell with persistent context (AC: #3)
  - [ ] `frontend/src/routes/ScenarioWorkspace.tsx` at `/scenarios/:scenarioId`, with `frontend/src/features/scenario-workspace/ScenarioVersionContext.tsx` for the context row.
  - [ ] The context row names, on every scenario surface: **scenario name** (primary), **stable scenario ID**, **immutable fixture version**, **baseline version**. Identifiers render in a monospace treatment (`DESIGN.md` `{typography.identifier}` — 12px `ui-monospace`); ordinary names stay sans-serif.
  - [ ] Baseline version renders the literal **“Not established”** when the API returns null. Read the Dev Notes entry on this before writing the code — do not invent a version string, a `v0`, an em dash, or a baseline table.
  - [ ] Changing scenario **returns through the catalogue**: the workspace carries an explicit “Change scenario” link back to `/`. Build **no** scenario switcher, dropdown, or sibling-scenario list in the workspace (UX-DR2: never switch scenario implicitly).
  - [ ] Scenario id not found / not this site → 404 from the API → a terminal, non-disclosing “not found” view with a link back to the catalogue. Do not fall back to another scenario or version.
  - [ ] **Do not build the four peer workspace tabs (Chat / Scenario Data / Runs / Results).** UX-DR1/UX-DR3 tabs are Story 1.7's acceptance boundary. This story delivers the persistent context and a placeholder body naming what arrives next, in literal copy. Building tabs here means Story 1.7 rewrites them and Story 1.9's route audit has two shells to reason about.
  - [ ] **Do not build the ShiftMind token layer.** Design tokens and the shared Status badge / Inline alert / Skeleton / Empty state / Reconnect banner / Evidence link primitives are Story 1.6's acceptance boundary. Use inherited shadcn/Tailwind, matching how `AppBar.tsx` and `ScenarioLayout.tsx` currently inline `#4F46E5`. If you need a Skeleton, add the standard shadcn `frontend/src/components/ui/skeleton.tsx` primitive (it is part of the inherited system, not a new token system) — Story 1.6 will govern it, not replace it.

- [ ] Task 5: Retire the legacy route tree (AC: #1, #2)
  - [ ] In `frontend/src/App.tsx`, `/` becomes `FixtureCatalogue` and `/scenarios/:scenarioId` becomes `ScenarioWorkspace`. **Remove** the legacy `Home` index, the `ScenarioLayout` wrapper with its three legacy tabs, and the `runs` / `runs/:runId` children. `RootLayout`, `AppBar`, `RequireSession`, `/signin`, and the `RootErrorBoundary` wiring stay exactly as they are.
  - [ ] Delete the now-unreachable legacy **route** components and their co-located tests: `routes/Home.tsx`, `routes/Editor.tsx(+.test)`, `routes/ScenarioLayout.tsx`, `routes/RunHistory.tsx(+.test)`, `routes/ResultsView.tsx(+.test)`. Their only purpose was routing; leaving them is dead code a future story could re-mount by accident, and they render “New Scenario”, “Run Scenario”, and constraint-mutation controls that FR22 and Story 1.9's mutation-path audit forbid on a governed surface.
  - [ ] **Expect the frontend test count to drop** (currently 250 passing) as those route tests are removed. That is the intended outcome, not a regression — say so in the completion notes with the before/after numbers.
  - [ ] **Leave `frontend/src/components/{editor,runs,results,scenarios}/**` and their hooks in place.** They become orphaned, their tests keep passing, and a full legacy sweep is a bigger cleanup than this story owns. Add one entry to `_bmad-output/implementation-artifacts/deferred-work.md` recording the orphaned legacy component/hook tree so Story 1.9's audit and a later cleanup have the list.
  - [ ] Rewrite `frontend/src/routes/router.test.tsx` against the new tree, keeping its two existing invariants intact: an unauthenticated deep link redirects to `/signin` with the `return_to` query, and a transient session-check error does **not** bounce an authenticated user off a protected route.
  - [ ] **Do not touch the backend legacy routers** (`/scenarios`, `/runs`, `/constraints`) or `services/`, `store/`, `llm/`. They stay offline exactly as they are (AD-25). Story 1.2's dev notes are still in force: don't "repair" legacy screens.

- [ ] Task 6: Accessibility contract for this story's surfaces (AC: #2, #3)
  - [ ] The epic is explicit that each UI story implements its own visual/a11y contract rather than deferring it to Story 1.10. For these two surfaces that means: table `<caption>` and `<th scope>` associations; on route change, focus moves to the view heading (UX-DR27); visible focus rings; 44×44 CSS px minimum touch targets; no hover-only affordance; no meaning carried by color alone; the loading skeleton respects reduced motion.
  - [ ] Long identifiers wrap or truncate with an accessible full value — they never force the page into horizontal scroll (UX-DR31, `DESIGN.md` Typography).

- [ ] Task 7: Tests
  - [ ] Backend — catalogue: returns every seeded fixture version for the session's site in the exact documented order, including the stable-ID tie-break; each row carries scenario ID, fixture version, and checksum.
  - [ ] Backend — isolation (`@pytest.mark.postgres`): a Site A session sees zero Site B rows from `GET /api/v1/scenarios`, and `GET /api/v1/scenarios/{site_b_scenario_id}` returns **404 with the identical body** as a random unknown UUID. Extend the existing `backend/tests/test_postgres_integration.py` RLS proof rather than starting a parallel one; reuse `governed_postgres_engine` / `fresh_postgres_database_url` from `backend/conftest.py:79-98` (they already skip cleanly when no local PostgreSQL is up — keep a keyless, serviceless run green).
  - [ ] Backend — no session → 401 problem details on both paths; assert the body contains no fixture name, scenario name, or site name.
  - [ ] Backend — mutation denial: iterate `app.routes` **and** `app.openapi()` and assert no `/api/v1/scenarios*` path exposes POST/PUT/PATCH/DELETE. This is the FR22 proof at this story's boundary and the seed of Story 1.9's audit.
  - [ ] Backend — read-only proof: after listing and opening a scenario, `scenario_version` row count, ids, and `checksum_digest` values are byte-identical (AC #1's "without changing or copying its source data").
  - [ ] Backend — the endpoints do not block the event loop: assert the handlers are sync `def` (e.g. `not inspect.iscoroutinefunction(...)`), the cheap regression guard for the async trap above.
  - [ ] Frontend — all five catalogue states render their specified copy; the loaded table has no button/control matching create/upload/import/edit/delete; each row is a link whose `href` is `/scenarios/{id}`.
  - [ ] Frontend — the workspace context renders all four fields, with baseline showing “Not established” when the API returns null, and exposes a “Change scenario” link to `/`; there is no scenario-switching control.
  - [ ] Frontend — `createMemoryRouter` deep-link tests over the real `routes` array from `@/App` (the established pattern in `router.test.tsx`): `/` mounts the catalogue, `/scenarios/:id` mounts the workspace, an unknown path still lands on `RootErrorBoundary`.
  - [ ] Full regression before done: `uv run --frozen pytest` (backend, default `-m "not live"`), `alembic check` (must report no drift — this story adds no migration), `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`.

## Dev Notes

- **Baseline version does not exist yet — and this story must not create it.** AC #3 requires the persistent context to name a baseline version, but the operational-baseline pointer is owned by the scheduling aggregate (AD-22) and arrives with Epic 3 (`ScheduleVersionV1`) and Epic 4 (atomic promotion, AD-10). Creating a baseline table, column, or pointer here would widen an aggregate bundle that AD-22 fixes and pre-empt AD-9's immutability rules. **The contract carries `baseline_schedule_version: str | None`, it is always `null` in this story, and the UI renders the literal “Not established”.** That is the UX-DR5-correct answer: name the literal state, invent nothing. When Epic 3/4 land the pointer, only the adapter query and the null branch change — the contract field and the UI slot are already in place.
- **The five states are four TanStack Query shapes, not five fetches.** Loading = `isPending`. Empty = success with a zero-length array (a legitimate zero-row catalogue is an empty state, never an error). Error = `isError` **with no cached data**. **Cached-stale = `isError` *with* `data` still present** — a background refetch failed while the previous successful response is still in cache; keep the rows visible, add the “Saved catalogue — refresh unavailable” label, and keep the retry available. That last branch is the one implementations silently drop; it is an explicit acceptance criterion here, and it is why cache must never be treated as authorization — selecting a row still round-trips under the current session (AD-14: cached data is never authority).
- **This story is the async closure Story 1.1 deferred.** `PostgresFixtureHistoryAdapter` and `get_site_context` both drive a synchronous SQLAlchemy engine. Story 1.1 recorded: *"the next story to call it from a FastAPI endpoint must route it through a worker thread."* Story 1.2 did that for identity via `run_in_threadpool`; this story does it for domain reads by keeping the path operations sync `def` so FastAPI's threadpool owns them. Pick one mechanism — sync `def` handlers — and do not mix in `run_in_threadpool` inside an `async def` handler for the same call.
- **`get_site_context` is the only door to domain data.** It sets `app.site_id` transaction-locally (`SET LOCAL`, cleared at commit — a pooled connection holding a stale setting is a cross-tenant leak) and `SET LOCAL ROLE shiftmind_runtime` (required, because the API's `shiftmind_login` role is `NOINHERIT` and holds no grants of its own). Depend on it; don't rebuild any part of it.
- **Non-disclosure is a behavior, not a message** (AD-3, carried from Story 1.2). A scenario in another site returns exactly what a nonexistent scenario returns. Reserve 403 for CSRF/origin failures, where the caller already proved session ownership.
- **`shiftmind_runtime` still holds `INSERT` on `scenario_version`** (Story 1.1, `d128d081ab48_...py:271`) so the cutover importer can run. Nothing in this story may use it, and no code path this story adds may reach a write. Flag it in your completion notes for Story 1.9's mutation-path audit — a *grant* is not a *path*, but the audit will want to see it named and bounded.
- **Do not preempt Story 1.4.** `ScenarioProjectionV1` — normalized work areas, tasks, workers, qualifications, availability, demand intervals, baseline assignments, locks, constraints/objectives, `horizon_start`, IANA timezone, integer-minute half-open offsets, bounded cursors, exact-target lookup — is Story 1.4's contract. This story reads only catalogue metadata that already exists as columns on `scenario` / `scenario_version`. It does not open the JSONB `payload`, does not normalize anything, and does not add a cursor/window API.
- **Do not preempt Story 1.6 or 1.7.** Tokens and shared primitives are 1.6; the four peer tabs and the seven Scenario Data groups are 1.7. Ship a persistent context plus a literal placeholder body.
- **Scope discipline (AD-22):** the scenario aggregate owns fixture catalogue, scenario, scenario version — *"seeding/import use cases; read-only to planner/agent in MVP."* Conversations, jobs, approvals, and audit belong to Epics 2–4. Sign-in/selection events are not audited here; the append-only audit ledger (`AuditEnvelopeV1`) is Epic 4 (FR21). Persist nothing that pretends to be it.
- **Domain purity (AD-1):** nothing under `backend/domain/` may import SQLAlchemy, psycopg, or FastAPI. All of this story's backend code lives in `backend/api/`, `backend/application/ports/`, and `backend/adapters/postgres/`.
- **No new dependency at this gate (AR27).** Every library needed here is already a repository lock: FastAPI 0.138.1, SQLAlchemy 2.0.51, psycopg 3.3.4, React 19.2.7, React Router 8.2.0, TanStack Query 5.101.2, openapi-fetch 0.17.0, TypeScript 5.9.3, Vite 8.1.x. The shadcn Skeleton primitive is a copy-in component of the already-installed system, not a package. Do not add or lock anything; `uv.lock` and `package-lock.json` should be untouched by this story.
- **Test conventions:** backend tests in `backend/tests/test_*.py`, run `uv run --frozen pytest`; database-backed tests use `@pytest.mark.postgres` and the shared throwaway-database fixtures that `pytest.skip` without a local PostgreSQL service — keep that behavior. Frontend: `npm test` (Vitest + Testing Library), tests co-located with implementation, `createMemoryRouter` for real route tests.
- **Vite dev proxy already exists** (`frontend/vite.config.ts:12-18`, `/api` → `127.0.0.1:8000`) with `VITE_API_BASE_URL` pointing at the SPA's own origin, so the `__Host-`-style `SameSite=Lax` session cookie is sent. Don't re-solve that; if the catalogue 401s in the browser but passes in tests, check the backend is actually running on 8000 before suspecting auth.

### Project Structure Notes

- New backend files converge on the Structural Seed: `backend/application/ports/scenario_catalogue.py`, `backend/adapters/postgres/scenario_catalogue.py`, `backend/api/routers/scenario_catalogue.py`. Response models extend the existing `backend/api/schemas.py`.
- New frontend work creates `frontend/src/features/` (seed path, first use in this repo) with `fixture-catalogue/` and `scenario-workspace/` subfolders; `frontend/src/routes/` stays route composition only; hooks stay thin TanStack Query wrappers in `frontend/src/hooks/`; API wrappers stay in `frontend/src/api/` behind the single client.
- `backend/store/`, `backend/services/`, `backend/llm/`, and `frontend/src/components/{editor,runs,results,scenarios}/` are frozen legacy (AD-25). Read them for pattern; extend none of them.
- Conventions to match rather than reinvent: RFC 7807 bodies via `api/problems.py` + `versioned_http_problem`; `Protocol` + frozen dataclasses for ports (`application/ports/session.py`); site-scoped transaction via `api/deps.py:get_site_context`; single `openapi-fetch` client with derived types (`frontend/src/api/client.ts`, `api/auth.ts`); fixed user-facing error copy in `frontend/src/lib/errors.ts` (`USER_ERROR_COPY`) so backend diagnostics never cross into JSX.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.3: Choose an Immutable Fixture] — story statement and the three acceptance criteria (lines 384-405)
- [Source: _bmad-output/planning-artifacts/epics.md#FR22, UX-DR1, UX-DR2, UX-DR4, UX-DR5, UX-DR14, UX-DR23, UX-DR24, UX-DR25, UX-DR26, UX-DR27, UX-DR31] — requirements bound to this story
- [Source: _bmad-output/planning-artifacts/prds/prd-ShiftMind-2026-07-21/prd.md:186-189] — FR-22 normative text: select from an application-provided catalogue; no uploads, no creation or modification of source data
- [Source: .../architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md#AD-4] — immutable `scenario_version` records, deterministic stable ordering, exact-target lookup, no scenario-source mutation command/route/tool/UI control, Gate A ordering
- [Source: ARCHITECTURE-SPINE.md#AD-3, AD-13, AD-14, AD-22, AD-23, AD-25, AD-26] — server-derived site authority and non-disclosing not-found; versioned REST + RFC 7807 + one generated client; TanStack Query as sole remote-cache owner and peer scenario surfaces; scenario aggregate ownership; transaction-local site context; one-way brownfield cutover
- [Source: ARCHITECTURE-SPINE.md#Structural Seed] — `frontend/src/features/`, `backend/application/`, `backend/adapters/`; normative contract minimums (`schema_version`, `site_id`); `ScenarioProjectionV1` is a separate contract owned by Story 1.4
- [Source: .../ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md:32-42] — route/surface map: Fixture catalogue at `/`, workspace at `/scenarios/:scenarioId`, persistent scenario/version context, changing scenario returns through the catalogue
- [Source: EXPERIENCE.md:122] — the Fixture catalogue row of the State Patterns table: exact loading/empty/error/stale copy this story must use verbatim
- [Source: EXPERIENCE.md:241-249] — Flow 2, and its failure paths (empty group, query failure, unauthorized fixture)
- [Source: EXPERIENCE.md:185-196] — accessibility floor: headings/landmarks, caption and `<th scope>`, focus on route change, 44×44 targets, reduced motion
- [Source: .../ux-designs/ux-ShiftMind-2026-07-22/DESIGN.md:88-96, 110-118] — identifier monospace treatment, scenario/version context visual contract, 24px workspace gutter; ShiftMind token consolidation itself is Story 1.6
- [Source: _bmad-output/implementation-artifacts/1-1-establish-governed-fixture-history.md#Review Findings] — deferred item this story closes: the sync SQLAlchemy engine must be routed through a worker thread by the first story calling it from a FastAPI request handler
- [Source: _bmad-output/implementation-artifacts/1-2-sign-in-to-the-seeded-site-safely.md#Dev Notes] — session/site re-resolution per request, `SET LOCAL app.site_id`, non-disclosure as behavior, "Story 1.3 begins the replacement UI — don't repair legacy screens"
- [Source: backend/migrations/versions/d128d081ab48_establish_governed_fixture_history.py:241-276] — the RLS policy expression and the `SELECT` grants this story relies on (and the `INSERT` grant it must not use)
- [Source: backend/api/deps.py:107-133] — `get_site_context`: the only supported site-scoped transaction
- [Source: backend/api/main.py:57-86, 143-200, 220-225] — the versioned problem-details handler, `/api/v1` session/CSRF enforcement, and where to include the new router
- [Source: backend/adapters/postgres/schema.py:74-144] — `scenario` / `scenario_version` columns and the composite `(id, site_id)` uniqueness convention
- [Source: frontend/src/App.tsx, frontend/src/routes/router.test.tsx] — the route tree being replaced and the `createMemoryRouter` test pattern to keep
- [Source: frontend/src/routes/Home.tsx, frontend/src/components/scenarios/*] — the legacy create/upload surface being removed from `/`

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created

### File List

### Change Log
