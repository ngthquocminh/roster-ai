---
phase: 01-browser-callable-api-app-shell-scenario-list
plan: 05
subsystem: frontend-app-shell
tags: [react-router, app-shell, error-boundary, ui-spec]
status: complete

dependency-graph:
  requires: [01-03]
  provides:
    - app-shell-routes
    - persistent-two-tier-nav
    - error-banner
    - root-error-boundary
  affects:
    - frontend/src/App.tsx
    - frontend/src/main.tsx

tech-stack:
  added: []
  patterns:
    - "createBrowserRouter data-router with a scenario-scoped layout route (react-router, not react-router-dom)"
    - "Shared route-config array (routes) exported from App.tsx so tests build a createMemoryRouter against the exact production route tree instead of a hand-duplicated copy"
    - "Root route errorElement doubles as both the render-exception backstop and the unmatched-URL 404 surface"

key-files:
  created:
    - frontend/src/routes/Home.tsx
    - frontend/src/routes/ScenarioLayout.tsx
    - frontend/src/routes/EditorPlaceholder.tsx
    - frontend/src/routes/RunsPlaceholder.tsx
    - frontend/src/routes/ResultsPlaceholder.tsx
    - frontend/src/routes/router.test.tsx
    - frontend/src/components/layout/AppBar.tsx
    - frontend/src/components/layout/PlaceholderView.tsx
    - frontend/src/components/layout/ErrorBanner.tsx
    - frontend/src/components/layout/ErrorBanner.test.tsx
    - frontend/src/components/layout/RootErrorBoundary.tsx
  modified:
    - frontend/src/App.tsx
    - frontend/src/main.tsx

decisions:
  - "Results tab renders disabled (no runId exists in Phase 1); route stays deep-linkable by URL per criterion 3, only the in-app link source is deferred to Phase 3"
  - "App.tsx exports a plain `routes` config array (not just the constructed `router`) so router.test.tsx can build createMemoryRouter against the identical production route tree"
  - "ErrorBanner and RootErrorBoundary both accept the caught error only for console.error logging — never as render input — per T-1-02"

metrics:
  duration_minutes: 20
  tasks_completed: 2
  files_created: 11
  files_modified: 2
  commits: 2
  tests_added: 18
  completed_date: 2026-07-16
---

# Phase 1 Plan 05: App Shell — Four-Route Table, Two-Tier Nav, Error Surfaces Summary

Built the SHELL-03 four-route shell (root layout + scenario-scoped layout with Editor/Runs/Results
placeholders) and the SHELL-04 error floor (persistent backend-unreachable banner + root-route crash
backstop), using react-router's data router with a shared route-config array reused by both the app
and its deep-link test suite.

## What Was Built

**Task 1 — Four-route table with persistent two-tier nav and honest placeholders** (commit `53045f5`)

- `App.tsx` exports a `routes: RouteObject[]` array and the `router` built from it via
  `createBrowserRouter`. Root route (`RootLayout`: persistent `AppBar` + `Outlet`) → index `Home` →
  nested `scenarios/:scenarioId` (`ScenarioLayout`: persistent three-tab nav + `Outlet`) → index
  `EditorPlaceholder`, `runs` → `RunsPlaceholder`, `runs/:runId` → `ResultsPlaceholder`. Editor sits at
  the layout's index route exactly as UI-SPEC specifies — no `/editor` segment was introduced.
- `main.tsx` mounts a module-scope `QueryClient` inside `QueryClientProvider`, which wraps
  `RouterProvider` (imported from `react-router/dom`) — the provider is above the router so plans
  01-06/01-07's first `useQuery`/`useMutation` calls have it in context.
- `AppBar`: "ShiftMind" wordmark + a single "Home" link (`NavLink` to `/`, `end`) — no auth affordance.
- `ScenarioLayout`: `NavLink` tabs for Editor/Runs, each with `end` matching (Editor's index route is a
  URL *prefix* of Runs/Results, and Runs is in turn a prefix of Results — both need `end` to avoid a
  parent tab staying marked active on a child route). React Router's `NavLink` sets `aria-current="page"`
  automatically on the active match, which the test suite asserts directly rather than re-deriving
  active-state logic by hand.
- **Results tab handling (per Output spec, item a):** rendered as a disabled `<button>`, not a link —
  `runs/:runId` requires a `runId` nothing in Phase 1 produces. The route itself remains deep-linkable
  by direct URL entry (satisfying criterion 3); only the *in-app* link source is deferred until Phase 3
  produces a real run. Its active/inactive styling is still computed via `useMatch` so visiting the
  route directly shows it correctly highlighted even though it has no clickable in-app origin.
- `PlaceholderView` + three placeholder route components render UI-SPEC's exact honest copy
  (`"{View} — not built yet"` / `"This view ships in a later phase of the v0.4 milestone."`) with zero
  mock data — verified by an explicit lorem/mockData/sampleRows/fakeData grep sweep.
- `router.test.tsx`: 10 tests, one or more per `<behavior>` case, built against `createMemoryRouter(routes, ...)` —
  the exact same route-config array `App.tsx` exports, not a hand-duplicated test tree. This is what
  gives the route-ranking assertion (`/scenarios/abc123/runs` → Runs placeholder, never Editor with
  `scenarioId === 'runs'`) real teeth: a production route-ranking regression would fail this test too.

**Task 2 — Backend-unreachable banner and crash backstop** (commit `b3895c3`)

- `ErrorBanner`: persistent inline `Alert`-based banner (not a toast) rendering UI-SPEC's fixed,
  non-diagnostic copy verbatim, including the literal remediation command
  `uv run uvicorn api.main:app --reload`. It accepts `error: unknown` as a prop purely for
  `console.error` logging and never reads `.message`/`.stack` for render — verified by a test that
  injects a fake stack trace + file path into the error's `.message` and asserts none of that text
  reaches the DOM. Empty-message and null/undefined-message cases both render the identical fixed copy.
  No CORS-vs-network detection logic exists anywhere (grep-verified) — `fetch` cannot reliably make that
  distinction, and UI-SPEC is explicit that pretending otherwise would be dishonest.
- `RootErrorBoundary`: renders "Something went wrong." + the console-check body copy + a "Reload" button
  (`window.location.reload()`). Wired as `App.tsx`'s root-route `errorElement`, which — per
  react-router's data-router semantics — catches both a render exception anywhere below the root AND an
  unmatched URL (confirmed live: react-router treats a 404 as a route error, so `/nope` lands on
  `RootErrorBoundary` with no extra catch-all `*` route needed — see Output spec item b below).
- `router.test.tsx` gained two more tests: a `/nope` deep-link asserting the crash-backstop heading/body/
  button render, and a dedicated throw-test using a small ad-hoc `createMemoryRouter` (a component that
  throws during render, with `RootErrorBoundary` as its `errorElement`) to prove the render-exception path
  independent of the full app tree.

## Output Spec Answers

**(a) How the Results tab's no-runId problem was handled:** Disabled tab (a plain `<button disabled>`),
not a link to an invented path. `/scenarios/:scenarioId/runs/:runId` remains fully deep-linkable by
direct URL entry — criterion 3 is satisfied — but there is no in-app click affordance to reach it until
Phase 3 produces a real run and can render a link with a concrete `runId`. Its active-state highlighting
(`aria-current="page"`, computed via `useMatch`) still works correctly when the route is visited
directly, keeping the persistent nav visually honest even for a tab with no click path yet.

**(b) Unmatched-route confirmation:** Confirmed against the installed `react-router@8.2.0` — a route
error object is thrown for both an unmatched URL and a render exception, and both are caught by the
nearest ancestor route's `errorElement`. No catch-all `*` route was needed; the single `errorElement` on
the root route (`App.tsx` line ~46) covers both cases, exactly as RESEARCH.md/UI-SPEC predicted. Verified
live by two passing tests: a `/nope` deep-link test and a dedicated throwing-component test.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - blocking] `router.test.tsx` needed the Task 2 crash-backstop tests, though Task 2's
`<files>` list omitted it**
- **Found during:** Task 2
- **Issue:** Task 2's acceptance criteria explicitly require
  `npx vitest run src/routes/router.test.tsx` to pass "now including the `/nope` → RootErrorBoundary
  case," but Task 2's `<files>` tag listed only `ErrorBanner.tsx`, `ErrorBanner.test.tsx`,
  `RootErrorBoundary.tsx`, and `App.tsx` — not `router.test.tsx`.
- **Fix:** Added the `/nope` deep-link test and a dedicated throwing-child-route test to
  `router.test.tsx` as part of Task 2, since the plan's own acceptance criteria required it and
  `RootErrorBoundary` did not exist yet during Task 1 (so it could not have been tested then).
- **Files modified:** `frontend/src/routes/router.test.tsx`
- **Commit:** `b3895c3`

**2. [Rule 1 - bug-adjacent, doc wording] Explanatory comments unintentionally tripped their own
negative-affordance / single-occurrence greps**
- **Found during:** Task 1 and Task 2 self-verification
- **Issue:** `AppBar.tsx`'s docstring originally explained the *absence* of a user menu/avatar/account
  affordance using those exact words ("no user menu, no avatar... an inert account icon"), which a
  literal `grep -in 'avatar|account|...'` check would flag as a false positive. Similarly, `App.tsx`'s
  docstring mentioned "errorElement" in prose immediately above the actual `errorElement:` JSX prop,
  making `grep -c 'errorElement'` return 2 instead of the acceptance criterion's expected 1.
- **Fix:** Reworded both docstrings to convey the same rationale without repeating the literal grepped
  substring, so the comments and the acceptance-criteria greps agree with each other's intent (comment
  explains "why", grep verifies "what's actually there").
- **Files modified:** `frontend/src/components/layout/AppBar.tsx`, `frontend/src/App.tsx`
- **Commit:** `53045f5`, `b3895c3`

### Known Acceptance-Criteria Discrepancy (not fixed — documented, not a functional defect)

- **`grep -c 'createBrowserRouter' frontend/src/App.tsx` returns `2`, not the plan's stated `1`.** The
  identifier necessarily appears on two distinct lines in any idiomatic implementation: the named import
  (`import { createBrowserRouter, ... } from "react-router"`) and the single call site
  (`export const router = createBrowserRouter(routes)`). There is exactly **one** router construction in
  the file (verified: `router` is assigned exactly once, from exactly one `createBrowserRouter` call) —
  the discrepancy is in how the criterion's `grep -c` count was estimated, not in the code's structure.
  Contorting the import (e.g., aliasing or namespace-importing solely to reduce a text match) was judged
  worse for readability than leaving this documented. All functional verification (`vitest run`,
  `tsc --noEmit`, `npm run build`, and the four-route/error-boundary behavior itself) passes.

No other deviations. All behaviors, edge cases, and prohibitions in the plan's `must_haves` were
implemented as specified.

## Known Stubs

None. `Home.tsx` is intentionally a page-shell-only component per the plan's explicit scope
("Plans 01-06 and 01-07 fill it with the table and the create dialog; this plan only guarantees the
route mounts") — it renders only the page title, no placeholder table or fake row data, so there is
nothing that could be mistaken for a broken real view.

## Threat Flags

None. Both STRIDE register rows this plan addresses (T-1-02 information disclosure via error
surfaces, T-1-07 information disclosure via unmatched-route default error page) are mitigated exactly
as planned, with no new surface introduced beyond what the threat model anticipated.

## Verification

- `cd frontend && npx vitest run` — 3 files, 18 tests, all passing (10 in `router.test.tsx` Task 1 set +
  2 crash-backstop tests + 5 in `ErrorBanner.test.tsx` + 1 pre-existing harness smoke test)
- `cd frontend && npx tsc --noEmit` — exits 0, no errors
- `cd frontend && npm run build` — exits 0 (`tsc -b && vite build`, 239 modules transformed)
- `grep -rn "react-router-dom" frontend/src` — no matches
- `grep -rin 'lorem|mockData|sampleRows|fakeData' frontend/src/routes frontend/src/components/layout` —
  no matches
- `grep -rin "includes('CORS')|includes(\"CORS\")|match(/cors/i)" frontend/src` — no matches
- `grep -rn '\.stack' frontend/src/components/layout` — no matches rendering into JSX
- `frontend/src/api/` untouched (does not exist yet; correctly left for the parallel 01-04 worktree)
- `node_modules/` remains gitignored; no generated artifacts committed

## Self-Check: PASSED

- FOUND: frontend/src/App.tsx
- FOUND: frontend/src/main.tsx
- FOUND: frontend/src/routes/Home.tsx
- FOUND: frontend/src/routes/ScenarioLayout.tsx
- FOUND: frontend/src/routes/EditorPlaceholder.tsx
- FOUND: frontend/src/routes/RunsPlaceholder.tsx
- FOUND: frontend/src/routes/ResultsPlaceholder.tsx
- FOUND: frontend/src/routes/router.test.tsx
- FOUND: frontend/src/components/layout/AppBar.tsx
- FOUND: frontend/src/components/layout/PlaceholderView.tsx
- FOUND: frontend/src/components/layout/ErrorBanner.tsx
- FOUND: frontend/src/components/layout/ErrorBanner.test.tsx
- FOUND: frontend/src/components/layout/RootErrorBoundary.tsx
- FOUND commit: 53045f5
- FOUND commit: b3895c3
