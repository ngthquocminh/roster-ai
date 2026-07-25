# Deferred Work

## Deferred from: code review of story-1-1-establish-governed-fixture-history (2026-07-24)

- `canonicalize_json`'s recursive `_serialize` has no depth guard; a pathologically deep payload raises an uncaught `RecursionError` [backend/adapters/postgres/canonical_json.py:63-83]. Only reachable today via trusted, shallow fixture files — worth bounding if this function is ever fed untrusted input.
- `PostgresFixtureHistoryAdapter` is built on a synchronous SQLAlchemy engine with no async/thread-offload [backend/adapters/postgres/fixture_history.py:44-53]. Not a problem while only called from a standalone script; the next story that calls it from a live FastAPI request handler must route it through a worker thread to avoid blocking the event loop.
- `site` table's RLS policy (`site.id = app.site_id`) is confirmed correct as designed, not a defect — but Story 1.2's real runtime session flow must resolve `site_id` via `auth.resolve_session()` before any RLS-scoped domain transaction, never by querying organization+name (that lookup-by-name path is a privileged, Gate-A-only migrator bootstrap operation, exempt from RLS by nature). **Story 1.2 action item: add a test proving a Site A runtime session cannot enumerate Site B, even within the same organization.**
