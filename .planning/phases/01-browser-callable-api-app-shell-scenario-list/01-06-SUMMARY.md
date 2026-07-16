---
phase: 01-browser-callable-api-app-shell-scenario-list
plan: 06
subsystem: ui
tags: [react, tanstack-query, react-router, tailwind, shadcn, vitest]

requires:
  - phase: 01-browser-callable-api-app-shell-scenario-list
    provides: "CORS-enabled backend (01-01), typed API client (01-04), app shell + ErrorBanner/RootErrorBoundary (01-05)"
provides:
  - "useScenarios() query hook (['scenarios'] key contract for 01-07's invalidation)"
  - "ScenarioTable covering all five UI-SPEC list states"
  - "Home mounted with the live scenario list (SCEN-01 satisfied end-to-end)"
affects: ["01-07 (create-scenario dialog wires the empty-state and header 'New Scenario' buttons, invalidates ['scenarios'])"]

tech-stack:
  added: []
  patterns:
    - "useQuery(['scenarios'], listScenarios) — thin hook, zero transformation, server owns ordering"
    - "List-state component returns early per state (loading/error/empty) before the populated table render — no combined/nested conditional soup"

key-files:
  created:
    - frontend/src/hooks/useScenarios.ts
    - frontend/src/components/scenarios/ScenarioTable.tsx
    - frontend/src/components/scenarios/ScenarioTable.test.tsx
  modified:
    - frontend/src/routes/Home.tsx
    - frontend/vite.config.ts
    - frontend/src/routes/router.test.tsx

key-decisions:
  - "created_at rendered as the server's raw ISO 8601 string, not locale-formatted — UI-SPEC only requires 'created timestamp' rendering, not a specific format; avoids inventing timezone-dependent formatting logic untested by this plan"
  - "Row click uses onClick + onKeyDown(Enter/Space) with tabIndex=0 on TableRow, no role override — preserves native table row semantics rather than fabricating a button role on a <tr>"
  - "vite.config.ts test block now sets a fixed VITE_API_BASE_URL for Vitest — tests must not depend on a developer's local, gitignored .env"

patterns-established:
  - "Query-key string literal (['scenarios']) is a cross-plan contract enforced by grep in acceptance criteria, not just convention"

requirements-completed: [SCEN-01]

coverage:
  - id: D1
    description: "useScenarios() hook fetches GET /scenarios under the ['scenarios'] query key, preserving server order, no polling"
    requirement: "SCEN-01"
    verification:
      - kind: unit
        ref: "frontend/src/hooks/useScenarios.ts (grep-gated: query key, no refetchInterval, no sort/reverse); npx tsc --noEmit"
        status: pass
    human_judgment: false
  - id: D2
    description: "ScenarioTable renders all five UI-SPEC list states (loading, empty, error, populated, overflow) plus adjacency/ordering/zero-one-many/T-1-03 edges"
    requirement: "SCEN-01"
    verification:
      - kind: unit
        ref: "frontend/src/components/scenarios/ScenarioTable.test.tsx (9 tests, one per behavior case)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Home mounts ScenarioTable; full frontend suite, tsc, and npm run build all pass"
    requirement: "SCEN-01"
    verification:
      - kind: unit
        ref: "npx vitest run (36/36 passing across 5 files)"
        status: pass
      - kind: unit
        ref: "npx tsc --noEmit / npm run build"
        status: pass
    human_judgment: false
  - id: D4
    description: "Real cross-origin CORS path (criterion 1): the running backend echoes access-control-allow-origin for an allowed dev origin and omits it for a disallowed one; a real-browser DevTools console/Network-tab check (which jsdom/pytest structurally cannot perform) was not completed by this agent — no browser-automation tool was available in this execution context"
    requirement: "SCEN-01"
    verification:
      - kind: manual_procedural
        ref: "curl -H 'Origin: http://localhost:5173' http://127.0.0.1:8000/scenarios -> 200, access-control-allow-origin: http://localhost:5173, vary: Origin; curl -H 'Origin: http://evil.example' -> 200, header absent"
        status: pass
    human_judgment: true
    rationale: "Server-side CORS behavior is proven by curl above, but the plan's own <human-check> explicitly calls this 'the one thing pytest and jsdom cannot prove' — it requires a real browser's DevTools (no CORS console error, Network tab showing a genuine cross-origin request). This agent had no browser-automation tool in its execution context (the claude-in-chrome skill reported its tools were not wired into this sub-agent), so the actual browser verification is deferred to a human or a differently-tooled agent."

duration: 15min
completed: 2026-07-16
status: complete
---

# Phase 1 Plan 06: Scenario List on Home Summary

**`useScenarios()` (TanStack Query) + `ScenarioTable` render the live backend's scenario list on Home across all five UI-SPEC states (loading/empty/error/populated/overflow), satisfying SCEN-01 end-to-end.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-16T18:08:40+07:00 (worktree base)
- **Completed:** 2026-07-16T18:22:58+07:00
- **Tasks:** 2 completed
- **Files modified:** 5 (3 created, 2 modified — plus 1 additional test file touched as a Rule-3 blocking fix)

## Accomplishments
- `useScenarios()` hook: thin `useQuery` wrapper over `listScenarios`, `['scenarios']` query key (the cross-plan contract 01-07's create mutation will invalidate), zero transformation, no polling.
- `ScenarioTable` component covering all five UI-SPEC E1 states: centered-spinner loading (no skeleton rows), "No scenarios yet" empty state with an inline (intentionally inert) "New Scenario" button, `ErrorBanner`-only error state with zero rows, populated rows (name / monospace fixture / created timestamp) in server order, and a fixed-height scrollable container for overflow (no pagination).
- Edge-case correctness proven by test: same-name-different-id rows both render (keyed by `id`, never `name`); identical-`created_at` rows preserve input order (no client sort); one row renders with identical chrome to many (no count label anywhere); an HTML-looking scenario `name` renders as literal visible text with no element created from it (T-1-03).
- `Home.tsx` mounts `ScenarioTable` beneath the existing page title — criterion 1 ("user opens the app, sees scenarios from the running backend") is now wired end-to-end.
- Server-side CORS path verified via curl against the actual running backend: the configured dev origin gets `access-control-allow-origin` echoed back; a disallowed origin does not.

## Task Commits

Each task was committed atomically (Task 2 used the TDD RED→GREEN cycle):

1. **Task 1: Build the useScenarios query hook** - `0636ba6` (feat)
2. **Task 2: Build the ScenarioTable with all five list states and mount it on Home** - `8a0c925` (test, RED) → `6c1de9a` (feat, GREEN)

**Plan metadata:** commit created by this same execution (see final commit list in completion report)

## Files Created/Modified
- `frontend/src/hooks/useScenarios.ts` - `useQuery(['scenarios'], listScenarios)`, no transformation, no polling
- `frontend/src/components/scenarios/ScenarioTable.tsx` - all five list states, row click navigation, keyed by `id`
- `frontend/src/components/scenarios/ScenarioTable.test.tsx` - 9 tests, one per `<behavior>` case (SCEN-01, Wave 0 gap closed)
- `frontend/src/routes/Home.tsx` - mounts `ScenarioTable` beneath the page title
- `frontend/vite.config.ts` - added a fixed test-only `VITE_API_BASE_URL` (Rule 3 deviation, see below)
- `frontend/src/routes/router.test.tsx` - `renderAt` now wraps a `QueryClientProvider` (Rule 3 deviation, see below)

## Decisions Made
- `created_at` renders as the server's raw ISO 8601 string, not locale-formatted. UI-SPEC only requires a "created timestamp" to render; inventing a display format (and the timezone-dependent test fragility that comes with it) was judged out of this plan's scope. A later phase can add display formatting as a pure presentation change if desired.
- The empty-state "New Scenario" button and (per the plan's own instruction) any header-level "New Scenario" button remain unwired — plan 01-07 attaches the create-scenario dialog. This plan only renders the button; clicking it currently does nothing.
- Row click uses `onClick` + `onKeyDown` (Enter/Space) with `tabIndex={0}` on the shadcn `TableRow`, without overriding its native `role="row"` — avoids the accessibility anti-pattern of stamping `role="button"` onto a table row, which would break table semantics for assistive tech.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Vitest run failed: `VITE_API_BASE_URL is not set`**
- **Found during:** Task 2, running the full frontend suite after mounting `ScenarioTable` into `Home`
- **Issue:** `src/lib/env.ts` throws loudly at import time if `VITE_API_BASE_URL` is unset. Before this plan, `Home.tsx` never touched the API client chain, so `router.test.tsx` (which renders the full route tree, unmocked) never exercised it. Mounting `ScenarioTable` (which calls `useScenarios` → `listScenarios` → `client` → `env.ts`) means `router.test.tsx` now transitively imports `env.ts`, which throws because no `frontend/.env` exists (correctly gitignored, developer-local) and Vitest doesn't otherwise supply the var.
- **Fix:** Added a fixed, test-only `VITE_API_BASE_URL` value to the `test.env` block in `vite.config.ts` — scoped to Vitest only, does not affect `npm run dev`/`npm run build` (those load real `.env` files via Vite's own mechanism).
- **Files modified:** `frontend/vite.config.ts`
- **Verification:** `npx vitest run` — the previously-failing suite now passes.
- **Committed in:** `6c1de9a` (Task 2 GREEN commit)

**2. [Rule 3 - Blocking] `router.test.tsx` crashed with "No QueryClient set, use QueryClientProvider to set one"**
- **Found during:** Task 2, same full-suite run above (after fixing deviation #1)
- **Issue:** `router.test.tsx`'s `renderAt` helper builds a `createMemoryRouter` directly from `App.tsx`'s `routes` config, without the `QueryClientProvider` that `main.tsx` mounts above the real app's router. Once `Home` renders `ScenarioTable`, which calls `useScenarios()` (a `useQuery`), any render through this test helper throws for lack of a `QueryClient`.
- **Fix:** Wrapped `renderAt`'s render call in a fresh per-render `QueryClientProvider` (retry disabled, since the underlying `listScenarios()` fetch is expected to reject in jsdom with no backend/`fetch` — none of `router.test.tsx`'s existing assertions depend on the resulting loading/error UI, only on shell/nav chrome).
- **Files modified:** `frontend/src/routes/router.test.tsx`
- **Verification:** `npx vitest run src/routes/router.test.tsx` — 12/12 passing; full suite 36/36 passing.
- **Committed in:** `6c1de9a` (Task 2 GREEN commit)

**3. [Rule 1 - Bug] Two of my own acceptance-criteria greps were tripped by my own doc comments**
- **Found during:** Task 2, running the plan's acceptance-criteria grep checks after GREEN
- **Issue:** `ScenarioTable.tsx`'s docstring literally contained the substrings `.sort()`/`.reverse()` and the word "pagination" while *explaining* that neither is used — which is exactly what the negative-grep acceptance criteria (`grep -rEn '\.sort\(|\.reverse\('` / `grep -rin 'pagination...'`) are designed to catch, false positive or not.
- **Fix:** Reworded the comments to describe the same intent ("no client-side re-ordering", "no page-by-page navigation control") without the literal trigger substrings.
- **Files modified:** `frontend/src/components/scenarios/ScenarioTable.tsx`
- **Verification:** Both greps now return no lines (exit 1); `npx tsc --noEmit` and the component test file still pass.
- **Committed in:** `6c1de9a` (Task 2 GREEN commit)

---

**Total deviations:** 3 auto-fixed (2 blocking test-harness fixes caused directly by this plan's own wiring, 1 self-inflicted grep-trip in doc comments)
**Impact on plan:** All three were necessary for the plan's own verification gates to pass honestly; none change `ScenarioTable`'s or `useScenarios`'s runtime behavior. No scope creep — the `test.env` addition and `router.test.tsx` provider wrap are both narrowly scoped to test infrastructure.

## Issues Encountered
- The plan's Task 2 `<human-check>` asks for a real-browser DevTools verification (console has no CORS error; Network tab shows a genuine cross-origin request to `127.0.0.1:8000`). This agent's execution context had no browser-automation tool available (the `claude-in-chrome` skill reported its tools were not wired into this sub-agent). As a substitute, both backend and frontend dev servers were started in this worktree and the CORS path was verified server-side via `curl` with an `Origin` header: the configured dev origin (`http://localhost:5173`) receives `access-control-allow-origin: http://localhost:5173` + `vary: Origin`; a disallowed origin (`http://evil.example`) receives neither. This proves the backend's half of criterion 1 but does **not** substitute for the actual browser check the plan calls out as unprovable by pytest/jsdom — that verification is deferred to a human or a browser-tooled agent. See `coverage: D4` above.
- No other issues — TDD RED→GREEN cycle for Task 2 proceeded cleanly (test file failed to resolve the not-yet-created `ScenarioTable.tsx` import, confirming RED; all 9 tests passed on first implementation attempt after two test-scoping fixes described in the RED note below).

## User Setup Required
None — no external service configuration required. (A `frontend/.env` was created transiently in this worktree during the CORS verification above, pointing `VITE_API_BASE_URL` at `http://127.0.0.1:8000`; it is gitignored and was not committed. A developer following `.env.example` will recreate the same file.)

## Next Phase Readiness
- Plan 01-07 (create-scenario dialog) can proceed: it will wire the empty-state and header "New Scenario" buttons and invalidate the `['scenarios']` query key established here — the exact string this plan pinned via grep-gated acceptance criteria.
- The real-browser CORS/console verification from this plan's `<human-check>` remains open and should be performed before the phase is considered fully verified (see Issues Encountered / coverage D4).

---
*Phase: 01-browser-callable-api-app-shell-scenario-list*
*Completed: 2026-07-16*

## Self-Check: PASSED

- FOUND: frontend/src/hooks/useScenarios.ts
- FOUND: frontend/src/components/scenarios/ScenarioTable.tsx
- FOUND: frontend/src/components/scenarios/ScenarioTable.test.tsx
- FOUND: frontend/src/routes/Home.tsx
- FOUND commit: 0636ba6 (feat: useScenarios hook)
- FOUND commit: 8a0c925 (test: ScenarioTable RED)
- FOUND commit: 6c1de9a (feat: ScenarioTable GREEN + Home mount)
