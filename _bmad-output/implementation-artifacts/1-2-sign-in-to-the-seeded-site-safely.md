---
baseline_commit: 3e9540c748183c4747ad991259e686d32561871c
---

# Story 1.2: Sign In to the Seeded Site Safely

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a seeded planner,
I want to sign in to one protected site workspace,
so that every scenario and later agent action is authorized from my current server-side membership.

**Sizing note (from the epic):** high implementation breadth — OIDC/BFF session, sign-out, one-user/membership persistence, CSRF/origin enforcement, and RLS isolation. The task breakdown below is that split: one demonstrable acceptance boundary per task. Do **not** split into separate stories.

**Depends on:** Story 1.1 (done) — PostgreSQL, Alembic, `site`/`organization` tables, forced RLS, `shiftmind_runtime` role, `app.site_id` transaction-local convention.
**Unblocks:** Story 1.3 (fixture catalogue) and every authenticated read in Epic 1.

## Acceptance Criteria

1. **Given** the pre-provisioned planner identity and active membership, **when** the planner completes OIDC authorization code with PKCE through the BFF, **then** provider tokens remain server-side and the browser receives only a Secure, HttpOnly, SameSite opaque application-session cookie, **and** sign-out invalidates the application session without exposing credentials. *(FR1, AR3/AD-3)*

2. **Given** no valid application session, **when** a protected page or API is requested, **then** access is denied without exposing fixture or membership data, **and** no public registration route or UI can create an account. *(FR1)*

3. **Given** the seeded planner already exists, **when** provisioning attempts to create a second authenticatable user or activate a second membership, **then** database and application invariants reject the change atomically, **and** the seeded planner and membership remain unchanged. *(FR2)*

4. **Given** identity and session persistence is introduced for the seeded planner, **when** Story 1.2 migrations are applied, **then** this story creates only the minimal application-user, membership, application-session, and one-user enforcement structures and constraints it requires, **and** invitations, role administration, additional memberships, and other future identity structures are not created early. *(AR22/AD-22)*

5. **Given** an authenticated unsafe request, **when** origin or CSRF validation fails, a browser-held site value is altered, or a resource belongs to another site, **then** the request is denied from re-resolved session/membership context with a non-disclosing not-found shape where practical, **and** authorization tests prove zero cross-site reads or writes — including that a Site A runtime session cannot enumerate Site B **within the same organization**. *(FR3, NFR1, AR3/AD-3, AD-23)*

## Tasks / Subtasks

- [x] Task 1: Owned identity port + OIDC adapters (AC: #1)
  - [x] Add `authlib==1.7.2` to `backend/pyproject.toml` `[project].dependencies` and lock it (`uv lock`). This is a "planned dependency at its implementation gate" (AR27) — the architecture Stack table names Cognito but pins no OIDC client library, so this story picks and locks it. Authlib 1.7.2 (released 2026-05-06) supports Python 3.10+, inside the repo's `>=3.10,<3.13`.
  - [x] Define the owned port in `backend/application/ports/identity.py`: an `OidcProvider` `Protocol` with `authorization_url(state, nonce, code_challenge, redirect_uri) -> str`, `exchange_code(code, code_verifier, redirect_uri, nonce) -> OidcIdentity`, and `end_session_url(post_logout_redirect_uri) -> str | None`. `OidcIdentity` is a frozen dataclass carrying **only** `subject`, `email`, `issuer`, `expires_at` — never the raw ID/access token. Mirror the existing `backend/llm/base.py` Protocol + `create_provider()` factory shape; this is the repo's established pluggable-backend pattern.
  - [x] `backend/adapters/cognito/oidc.py` — real adapter. Fetch `{issuer}/.well-known/openid-configuration` once and cache it; exchange the code with `authlib.integrations.httpx_client.AsyncOAuth2Client` passing `code_verifier`; validate the ID token against cached JWKS with Authlib's JWT, asserting `iss`, `aud` (= client id), `exp`, and `nonce`.
  - [x] `backend/adapters/oidc/fake.py` — deterministic double that signs an ID token with a locally generated key and serves its own discovery/JWKS in-process. **Default provider in tests and local dev** (`OIDC_PROVIDER=fake`), exactly as `llm_provider="stub"` keeps CI keyless (NFR26, AD-16). No live Cognito call in normal CI, ever.
  - [x] **Do not** use `authlib.integrations.starlette_client`. Its `authorize_redirect`/`authorize_access_token` store `state`, `nonce`, and `code_verifier` in `request.session` — a signed *client* cookie. AD-3 requires the handshake to stay server-side; keep the verifier in PostgreSQL (Task 2).
  - [x] Extend `backend/settings.py` `Settings`/`default_settings()` using the existing env-override pattern: `oidc_provider` (`"fake"` default | `"cognito"`), `oidc_issuer`, `oidc_client_id`, `oidc_client_secret` (**`field(repr=False)`** — same treatment as `llm_api_key`, T-04-01), `oidc_redirect_uri`, `app_base_url`, `session_ttl_s`. Update `backend/.env.example`.

- [x] Task 2: Identity + session schema migration (AC: #3, #4)
  - [x] New Alembic revision with `down_revision = "d128d081ab48"`. Follow the Story 1.1 revision's style exactly (explicit `op.create_table`, named constraints, RLS/grant/role SQL via `op.execute`, symmetric `downgrade()`). Add the same tables to `backend/adapters/postgres/schema.py` so `alembic check` reports no drift — the Story 1.1 suite already asserts drift-free metadata.
  - [x] Create **only**: `app_user`, `membership`, and schema-qualified `auth.session_index` + `auth.login_handshake`. No invitation, role, permission, or second-membership structure (AC #4).
  - [x] `app_user`: server UUID id, `idp_subject` (unique), `email`, `created_at`, `disabled_at`. Not site-scoped (identity is org-level per AD-22), so no `site_id` and no RLS on this table.
  - [x] `membership`: server UUID id, `app_user_id`, `site_id`, `created_at`, `revoked_at`. Carries `site_id` + `ENABLE`/`FORCE ROW LEVEL SECURITY` + the same `app.site_id` policy expression Story 1.1 used, so it is a tenant table like the rest.
  - [x] **One-user / one-active-membership invariants must be database constraints, not application checks** (AC #3 says "database and application invariants"): `CREATE UNIQUE INDEX uq_app_user_singleton ON app_user ((true))` and `CREATE UNIQUE INDEX uq_membership_single_active ON membership ((true)) WHERE revoked_at IS NULL`. A second insert then fails with `IntegrityError` inside the transaction, leaving the seeded planner untouched.
  - [x] `auth.session_index`: id, `session_token_hash` (unique; **store SHA-256 of the token, never the token**), `csrf_token_hash`, `app_user_id`, `site_id`, `created_at`, `expires_at`, `revoked_at`. `auth.login_handshake`: id, `state` (unique), `nonce`, `code_verifier`, `redirect_target`, `created_at`, `expires_at`, `consumed_at`. Both are internal control tables — AD-23: **grant runtime roles no table access at all** on them; they are not tenant query surfaces and get no RLS policy because nothing may query them directly.
  - [x] `CREATE FUNCTION auth.resolve_session(token_hash text)` — `SECURITY DEFINER`, owned by the migrator/owner role, `SET search_path = auth, pg_catalog`, **no dynamic SQL**, returns `(app_user_id, site_id, csrf_token_hash, expires_at)` for a non-revoked unexpired session joined to its **currently active** membership. `REVOKE ALL ... FROM PUBLIC`, then `GRANT EXECUTE ... TO shiftmind_runtime`. Same treatment for `auth.consume_login_handshake(state)` if you need one; a plain owner-side function is preferable to widening table grants.
  - [x] Reuse the existing `shiftmind_runtime` role as the API runtime role. Do **not** invent `shiftmind_api`/`shiftmind_lease` now — the worker/lease split arrives with Epic 3's job queue.

- [x] Task 3: BFF auth endpoints (AC: #1, #2)
  - [x] New router `backend/api/routers/auth.py` mounted under the **versioned** prefix `/api/v1` (AD-13). Legacy `/scenarios`, `/runs`, `/constraints` routers stay exactly as they are — they are Gate-A-gated legacy (AD-25) and nothing in this story touches them.
  - [x] `GET /api/v1/auth/login` → generate `state`, `nonce`, PKCE `code_verifier` + S256 `code_challenge`; persist them in `auth.login_handshake` with a short expiry; 302 to the provider authorize URL. Nothing secret reaches the browser.
  - [x] `GET /api/v1/auth/callback?code&state` → consume the handshake row **once** (`consumed_at` set in the same transaction; a replayed `state` fails), exchange the code, validate the ID token, then resolve `app_user` by `idp_subject` **and** an active `membership`. If either is absent → deny; **never auto-provision a user**. On success create a session row and 302 to `app_base_url`.
  - [x] Session cookie: name `__Host-shiftmind_session`; value = 256-bit `secrets.token_urlsafe(32)`; `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, no `Domain` (all required by the `__Host-` prefix). Only the SHA-256 hash is stored. Provider access/ID/refresh tokens are never persisted and never leave the adapter.
  - [x] `GET /api/v1/auth/session` → 200 `{app_user_id, site_id, csrf_token, expires_at}` for a valid session, else 401. The **CSRF token is returned in this response body, not as a second cookie** — its hash lives in `auth.session_index`, so validation does not depend on cookie integrity (stronger than double-submit).
  - [x] `POST /api/v1/auth/logout` → set `revoked_at`, clear the cookie, 204. Unsafe method ⇒ it must itself pass the Task 4 CSRF/origin check.
  - [x] All failures render `ProblemDetailsV1` / RFC 7807 (`application/problem+json`) with stable codes — reuse the shape already emitted by `refuse_legacy_routes_during_gate_a` in `backend/api/main.py:51-61`. 401/403 bodies must contain **no** fixture name, membership, site name, or policy internals (AC #2).

- [x] Task 4: Request-time authorization, CSRF, and origin enforcement (AC: #2, #5)
  - [x] `backend/api/deps.py`: add `get_session(request)` — hash the cookie value, call `auth.resolve_session`, raise 401 on miss/expiry/revocation. Add `get_site_context(session)` that opens the PostgreSQL transaction and issues `SET LOCAL app.site_id = <session.site_id>` **before any domain query**, then clears it. This is the only supported way to obtain site context.
  - [x] **Site identity comes from the session row only.** Ignore any `site_id` in the URL, body, query, or header — do not even read one. A resource fetched under a mismatched site must return the **same 404 shape as absence** (AD-3 non-disclosure), not 403.
  - [x] CSRF/origin check for unsafe methods (`POST`/`PUT`/`PATCH`/`DELETE`) on `/api/v1/*`: `Origin` (falling back to `Referer`) must be in the allow-list **and** the `X-CSRF-Token` header must hash-match `auth.session_index.csrf_token_hash`. Failure → 403 with a stable code.
  - [x] **Regression boundary — scope every new check to `/api/v1/*`.** A global auth or CSRF middleware would break the ~206 existing backend tests and the legacy `/scenarios`,`/runs`,`/constraints` routes. Mount enforcement as a router-level dependency or a path-prefixed middleware, and keep it ordered so the existing Gate A middleware still wins on legacy prefixes.
  - [x] Leave `CORSMiddleware` with `allow_credentials=False` and do **not** add credentialed CORS. The SPA reaches the API same-origin (CloudFront→ALB in production per AD-17; Vite dev proxy locally per Task 6) — that is what makes the same-origin requirement in AD-3 enforceable.

- [x] Task 5: Seed provisioning (AC: #3)
  - [x] `backend/scripts/seed_planner.py` — an operator-only one-shot that creates the single `app_user` + `membership` against the Story 1.1 seed site, reading `SHIFTMIND_SEED_PLANNER_SUBJECT` / `SHIFTMIND_SEED_PLANNER_EMAIL` from env. Idempotent re-run returns the existing semantic result (same contract as Story 1.1's fixture import).
  - [x] Attempting a second user or a second active membership must fail atomically and leave the seeded rows byte-identical. There is **no HTTP route, UI control, or agent capability** that can create a user (AC #2's "no public registration").

- [x] Task 6: Frontend session boundary (AC: #1, #2)
  - [x] Add a Vite dev proxy in `frontend/vite.config.ts` mapping `/api` → `http://127.0.0.1:8000`, and set `VITE_API_BASE_URL` to the SPA's own origin so `src/lib/env.ts`'s loud-failure contract still holds. Without this the `__Host-`/`SameSite=Lax` cookie is silently never sent from `localhost:5173` to `localhost:8000` — this is the single most likely way this story "works in tests but not in the browser".
  - [x] `frontend/src/api/client.ts`: add `credentials: "include"` and an `openapi-fetch` middleware that attaches `X-CSRF-Token` from the cached session to unsafe requests. Keep it one client (the file's own docstring forbids a second).
  - [x] `frontend/src/api/auth.ts` (thin typed wrapper) + `frontend/src/hooks/useSession.ts` (TanStack Query wrapper, no business logic) + a `RequireSession` guard and a `/signin` route with a single "Sign in" control that navigates to `/api/v1/auth/login`. Add a sign-out control to `AppBar`. Unstyled beyond existing primitives — ShiftMind design tokens are **Story 1.6**, not this story.
  - [x] Regenerate contracts after the routes exist: `uv run python scripts/export_openapi.py` then `npm run codegen`. `frontend/src/api/schema.d.ts` is generated — never hand-edit it (AD-13).

- [x] Task 7: Tests
  - [x] Full happy path through `TestClient` against the fake provider: login → callback → `GET /auth/session` 200 → authenticated read → `POST /auth/logout` → the same cookie now 401.
  - [x] Cookie assertions: `Secure`, `HttpOnly`, `SameSite=Lax`, `__Host-` prefix rules; the response contains no provider token; `auth.session_index` stores a hash, not the cookie value.
  - [x] ID-token rejection cases: wrong `aud`, wrong `iss`, expired `exp`, mismatched `nonce`, replayed `state`.
  - [x] Unauthenticated `/api/v1/*` → 401 problem details; assert the body contains no fixture name, site name, or membership field.
  - [x] No-registration proof: assert no route on `app.routes` and no path in `app.openapi()` creates a user or membership.
  - [x] FR2: second `app_user` insert and second active `membership` insert each raise `IntegrityError`; after rollback the seeded rows are unchanged.
  - [x] CSRF: unsafe request with a missing/wrong `X-CSRF-Token` → 403; with a foreign `Origin` → 403; a valid pair → success.
  - [x] **NFR1 isolation (carries the Story 1.1 review invariant):** a Site A runtime session cannot read or enumerate Site B **within the same organization** — assert zero rows, not an error. Extend the existing `backend/tests/test_postgres_integration.py` RLS proof rather than starting a parallel one.
  - [x] AD-23 proof: `shiftmind_runtime` has no `SELECT` on `auth.session_index` / `auth.login_handshake`; `auth.resolve_session` has `EXECUTE` revoked from `PUBLIC` and granted to `shiftmind_runtime`; `prosecdef` is true and `proconfig` pins `search_path`.
  - [x] Migration `upgrade head` → `downgrade base` → `upgrade head` round trip on a throwaway database, using the existing `fresh_postgres_database_url` / `governed_postgres_engine` fixtures in `backend/conftest.py` (they already provision and force-drop unique databases — do not add a new fixture).
  - [x] Frontend: `useSession`/guard tests with a mocked client; a `createMemoryRouter` test proving an unauthenticated deep link lands on `/signin` (the established pattern in `frontend/src/routes/router.test.tsx`).

## Dev Notes

- **The application session is opaque and server-side. There is no JWT in the browser.** The cookie carries a random token; every request re-resolves actor + site through `auth.resolve_session` against current membership (AD-3: "re-resolves actor/site … and current PostgreSQL membership"). A revoked membership must stop working on the very next request, which a self-contained signed token could not deliver.
- **PKCE lives entirely server-side.** The BFF is a confidential client that *also* uses PKCE. `code_verifier` never touches the browser — that is why `auth.login_handshake` exists and why the Authlib Starlette integration is off-limits here (it persists the verifier into a client cookie).
- **Non-disclosure is a behavior, not a message.** Cross-site and unauthorized lookups return the same shape as absence (AD-3). Reserve 403 for CSRF/origin failures, where the caller already proved session ownership and nothing is disclosed by saying so.
- **`app.site_id` is set per transaction, never per connection.** Story 1.1's RLS policies read `current_setting('app.site_id', true)`. Use `SET LOCAL` inside the transaction and let it clear at commit — a pooled connection that keeps a stale setting is a cross-tenant leak.
- **The session lookup cannot itself be RLS-scoped** — site context does not exist yet at that moment. That circularity is exactly what AD-23's `SECURITY DEFINER auth.resolve_session` resolves: it runs as the owner, outside RLS, and is the *only* owner-privileged function the API role may execute.
- **Async boundary (carried from Story 1.1's review):** `PostgresFixtureHistoryAdapter` uses a **synchronous** SQLAlchemy engine, and Story 1.1 explicitly deferred the async question with "the next story to call it from a FastAPI endpoint must route it through a worker thread." This story is that next story. Either offload synchronous DB work to a thread (`fastapi.concurrency.run_in_threadpool` / `def` endpoints) or introduce an async engine for the new identity adapter — do not block the event loop on every authenticated request.
- **Scope discipline (AD-22 aggregate ownership):** identity owns organization, site, app user, membership, session. Conversations, jobs, approvals, and audit tables belong to Epics 2–4. Audit of sign-in events is **not** in this story — `AuditEnvelopeV1` and the append-only audit ledger are Epic 4 (FR21). Persist nothing that pretends to be that ledger.
- **Domain purity (AD-1):** nothing under `backend/domain/` may import Authlib, SQLAlchemy, psycopg, or FastAPI. All of this story's code lives in `backend/api/`, `backend/application/ports/`, `backend/adapters/`, `backend/migrations/`, and `backend/scripts/`.
- **Test conventions:** backend tests live in `backend/tests/test_*.py`, run with `uv run --frozen pytest` (default `addopts = -m "not live"`). Database-backed tests use the `@pytest.mark.postgres` marker and the shared throwaway-database fixtures, which `pytest.skip` when no local PostgreSQL service is up — keep that behavior so a keyless, serviceless run still passes. Frontend: `npm test` (Vitest + Testing Library), tests co-located with implementation. Full regression before done: backend pytest, `alembic check`, `npm test`, `npm run typecheck`, `npm run lint`.
- **The legacy SPA is already dark against a cut-over backend.** Gate A 503s `/scenarios`, `/runs`, `/constraints`, so today's Editor/Runs/Results screens cannot work. That is expected (AD-25) and is **not** this story's problem to fix — Story 1.3 begins the replacement UI. Don't "repair" legacy screens.

### Project Structure Notes

- New backend code converges on the Structural Seed: `backend/api/routers/auth.py`, `backend/application/ports/identity.py`, `backend/adapters/cognito/`, `backend/adapters/oidc/`, `backend/migrations/versions/`, `backend/scripts/seed_planner.py`. `backend/application/` does not exist yet — this story creates it (with `__init__.py`), matching how Story 1.1 created `backend/adapters/`.
- `backend/store/`, `backend/services/`, `backend/llm/` are frozen legacy (AD-25). Read them for *pattern*, extend none of them.
- Frontend follows the seed's `frontend/src/api` (generated contract + the one client) and `frontend/src/routes` (route composition only) split; hooks stay thin TanStack Query wrappers.
- Existing conventions to match rather than reinvent: `Settings` frozen dataclass with env overrides and `repr=False` on secrets (`backend/settings.py`); `Protocol` + factory for pluggable backends (`backend/llm/base.py`); RFC 7807 error bodies (`backend/api/main.py:51-61`); throwaway-database test fixtures (`backend/conftest.py:79-98`).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.2: Sign In to the Seeded Site Safely] — story statement, sizing note, and the five acceptance criteria (lines 349-382)
- [Source: _bmad-output/planning-artifacts/epics.md#FR1, FR2, FR3, AR3, AR22, AR23, AR26, AR27, AR28, NFR1] — requirements bound to this story
- [Source: _bmad-output/planning-artifacts/prds/prd-ShiftMind-2026-07-21/prd.md:113-121] — FR-1/FR-2/FR-3 normative text and their testable consequences
- [Source: .../architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md#AD-3] — Cognito OIDC + PKCE at the FastAPI BFF, server-side tokens, opaque session cookie, same-origin + CSRF, per-request re-resolution, non-disclosing not-found
- [Source: ARCHITECTURE-SPINE.md#AD-23] — NOLOGIN owner, `NOINHERIT NOSUPERUSER NOBYPASSRLS` runtime roles, `auth.session_index` as a non-tenant control table, `SECURITY DEFINER auth.resolve_session` with revoked PUBLIC / fixed `search_path` / no dynamic SQL
- [Source: ARCHITECTURE-SPINE.md#AD-13, AD-22, AD-25, AD-1, AD-15, AD-16] — versioned REST + RFC 7807 + one generated client; identity aggregate ownership; one-way brownfield cutover; hexagonal boundary; untrusted content; deterministic-first CI
- [Source: ARCHITECTURE-SPINE.md#Stack] — no OIDC client library is pinned; AR27 makes this story the gate that adds and locks one
- [Source: .../ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md:122] — "Authentication failure routes to sign-in without exposing fixture names"; :169 — reauthorization follows the application sign-in path
- [Source: _bmad-output/implementation-artifacts/1-1-establish-governed-fixture-history.md#Review Findings] — recorded invariant for this story: resolve `site_id` via `auth.resolve_session()` before any RLS-scoped transaction (never by org+name lookup), and prove a Site A session cannot enumerate Site B in the same organization
- [Source: backend/migrations/versions/d128d081ab48_establish_governed_fixture_history.py] — the migration style, RLS policy expression, role creation, and grant/revoke pattern to extend
- [Source: backend/adapters/postgres/schema.py] — `_id_column()` / `_site_id_column()` helpers and the composite `(id, site_id)` uniqueness convention that keeps foreign keys site-bound
- [Source: backend/conftest.py:48-98] — throwaway-database fixtures (`governed_postgres_engine`, `fresh_postgres_database_url`) to reuse
- [Source: backend/api/main.py:31-62] — Gate A legacy-route middleware and the RFC 7807 body shape; middleware ordering constraint
- [Source: backend/settings.py:30-49] — `Settings` dataclass, `repr=False` secret handling, env-override pattern
- [Source: frontend/src/lib/env.ts, frontend/src/api/client.ts, frontend/vite.config.ts] — single-client rule, loud `VITE_API_BASE_URL` failure, and where the dev proxy must go
- Authlib **1.7.2** (latest; released 2026-05-06; BSD-3-Clause; Python 3.10+) — https://pypi.org/project/Authlib/ and https://docs.authlib.org. Register a discovery-based client via `server_metadata_url`; PKCE requires `client_kwargs={"code_challenge_method": "S256"}`. Context7 `/authlib/authlib` confirms `authorize_access_token()` reads `code_verifier`/`nonce` from `request.session` in the Starlette integration — the reason this story uses `authlib.integrations.httpx_client.AsyncOAuth2Client` plus server-side handshake storage instead.

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

- 2026-07-26 — Task 1 RED/GREEN/refactor: introduced the provider-neutral OIDC port, keyless signed fake, cached Cognito/Authlib adapter, and env-backed settings. Verified with `uv run --frozen pytest tests/test_identity_provider.py -q` and the full backend suite.
- 2026-07-26 — Task 2 RED/GREEN/refactor: added the bounded identity/session schema, forced membership RLS, singleton indexes, and hardened `auth.resolve_session`. Verified migration upgrade/check/downgrade/upgrade on a throwaway PostgreSQL database and the full backend suite.
- 2026-07-26 — Task 3 RED/GREEN/refactor: added injectable BFF persistence, PKCE login/callback, opaque application sessions, session introspection, logout, and stable problem details. Verified the complete fake-provider endpoint flow and the full backend suite.
- 2026-07-26 — Task 4 RED/GREEN/refactor: added `/api/v1`-scoped session enforcement, same-origin CSRF validation, and the session-derived transaction-local RLS context. Verified denial/allow paths, legacy-route isolation, PostgreSQL context clearing, and the full backend suite.
- 2026-07-26 — Task 5 RED/GREEN/refactor: added operator-only, advisory-locked seeded planner provisioning with semantic replay and atomic conflict rejection. Verified byte-identical preservation on conflict and the full backend suite.
- 2026-07-26 — Task 6 RED/GREEN/refactor: added same-origin Vite proxying, credentialed single-client requests with CSRF middleware, typed session APIs/hooks, protected routing, sign-in, and sign-out. Regenerated OpenAPI types and verified 245 frontend tests, typecheck, and lint.
- 2026-07-26 — Task 7 RED/GREEN/refactor: completed the story's security, isolation, migration, no-registration, cookie, invalid-claim, and frontend guard proofs. Full validation: 238 backend tests and 245 frontend tests pass; TypeScript, lint, and production build pass.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created
- Task 1 complete: Authlib 1.7.2 is locked; provider tokens stay inside adapters; OIDC settings redact the client secret; 212 backend tests pass.
- Task 2 complete: minimal identity persistence and session controls are drift-free; runtime has function-only access to session resolution; 216 backend tests pass.
- Task 3 complete: authentication endpoints never auto-provision, keep provider credentials server-side, hash session/CSRF material, and pass 220 backend tests.
- Task 4 complete: unsafe versioned requests require both a current session and valid origin/CSRF pair; client-supplied site values are never consulted; 226 backend tests pass.
- Task 5 complete: the sole planner and active membership can only be provisioned through the environment-driven operator script; 229 backend tests pass.
- Task 6 complete: the SPA now uses the opaque BFF session through one generated client and redirects unauthenticated deep links to sign-in; 245 frontend tests pass.
- Task 7 complete: every listed authentication, authorization, tenancy, migration, and route-guard test exists and passes.
- Definition of Done complete: all acceptance criteria are covered, all 238 backend and 245 frontend tests pass, migration drift/round-trip checks pass, TypeScript/lint/build pass, and the File List matches every changed source artifact.

### File List

- _bmad-output/implementation-artifacts/1-2-sign-in-to-the-seeded-site-safely.md
- _bmad-output/implementation-artifacts/sprint-status.yaml
- backend/.env.example
- backend/adapters/cognito/__init__.py
- backend/adapters/cognito/oidc.py
- backend/adapters/oidc/__init__.py
- backend/adapters/oidc/fake.py
- backend/adapters/postgres/schema.py
- backend/adapters/postgres/identity.py
- backend/api/deps.py
- backend/api/auth_security.py
- backend/api/main.py
- backend/api/problems.py
- backend/api/routers/auth.py
- backend/api/schemas.py
- backend/application/__init__.py
- backend/application/ports/__init__.py
- backend/application/ports/identity.py
- backend/application/ports/session.py
- backend/pyproject.toml
- backend/migrations/env.py
- backend/migrations/versions/5e2a4c9d1f70_add_seeded_site_identity.py
- backend/scripts/seed_planner.py
- backend/settings.py
- backend/tests/test_identity_schema.py
- backend/tests/test_identity_provider.py
- backend/tests/test_auth_api.py
- backend/tests/test_postgres_integration.py
- backend/tests/test_postgres_schema.py
- backend/tests/test_seed_planner.py
- backend/uv.lock
- frontend/.env.example
- frontend/openapi.json
- frontend/src/App.tsx
- frontend/src/api/auth.ts
- frontend/src/api/client.test.ts
- frontend/src/api/client.ts
- frontend/src/api/schema.d.ts
- frontend/src/components/layout/AppBar.tsx
- frontend/src/hooks/useSession.test.tsx
- frontend/src/hooks/useSession.ts
- frontend/src/routes/RequireSession.tsx
- frontend/src/routes/SignIn.tsx
- frontend/src/routes/router.test.tsx
- frontend/vite.config.ts

### Change Log

- 2026-07-26 — Implemented Story 1.2 seeded-site OIDC/BFF authentication, server-side sessions, one-user persistence, CSRF/origin and RLS authorization, operator provisioning, frontend session guarding, generated contracts, and comprehensive security/regression tests. Status moved to review.
