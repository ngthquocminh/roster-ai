# Deferred Work

## Deferred from: code review of story-1-1-establish-governed-fixture-history (2026-07-24)

- `canonicalize_json`'s recursive `_serialize` has no depth guard; a pathologically deep payload raises an uncaught `RecursionError` [backend/adapters/postgres/canonical_json.py:63-83]. Only reachable today via trusted, shallow fixture files — worth bounding if this function is ever fed untrusted input.
- `PostgresFixtureHistoryAdapter` is built on a synchronous SQLAlchemy engine with no async/thread-offload [backend/adapters/postgres/fixture_history.py:44-53]. Not a problem while only called from a standalone script; the next story that calls it from a live FastAPI request handler must route it through a worker thread to avoid blocking the event loop.
- `site` table's RLS policy (`site.id = app.site_id`) is confirmed correct as designed, not a defect — but Story 1.2's real runtime session flow must resolve `site_id` via `auth.resolve_session()` before any RLS-scoped domain transaction, never by querying organization+name (that lookup-by-name path is a privileged, Gate-A-only migrator bootstrap operation, exempt from RLS by nature). **Story 1.2 action item: add a test proving a Site A runtime session cannot enumerate Site B, even within the same organization.**

## Deferred from: code review of story-1-2-sign-in-to-the-seeded-site-safely (2026-07-26)

- No cleanup/retention job for expired `auth.login_handshake` / `auth.session_index` rows — both tables grow unbounded over time [backend/migrations/versions/5e2a4c9d1f70_add_seeded_site_identity.py]. Operational housekeeping reasonably arrives with Epic 3's job-queue infrastructure; no acceptance criterion requires it now.
- No `X-Frame-Options` / CSP `frame-ancestors` header on the new sign-in surface [backend/api/main.py]. Clickjacking hardening is an app-wide/infra concern better addressed holistically (e.g. at a reverse proxy or in a dedicated hardening pass) rather than piecemeal in this identity story.

## Deferred from: story-1-3-choose-an-immutable-fixture (2026-07-27)

- The legacy route components were retired, leaving the intentionally orphaned `frontend/src/components/{editor,runs,results,scenarios}/**` trees and their hooks: `useApplyConstraint`, `useCreateScenario`, `useFixtures`, `useOverrides`, `useRun`, `useRunInsights`, `useRunResult`, `useRuns`, `useScenario`, `useScenarios`, and `useTriggerRun`. Keep them unreachable; Story 1.9's mutation-path audit and a later cleanup should verify and remove this inventory without re-mounting it.
