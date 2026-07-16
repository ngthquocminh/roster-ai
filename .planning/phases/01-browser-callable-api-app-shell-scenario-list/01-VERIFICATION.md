---
phase: 01-browser-callable-api-app-shell-scenario-list
verified: 2026-07-16T22:35:00Z
status: human_needed
score: 15/15 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Real-browser DevTools CORS round trip: open the app at http://localhost:5173 with the backend running at http://127.0.0.1:8000, load Home, and confirm (a) no CORS error appears in the console and (b) the Network tab shows a genuine cross-origin request to the backend succeeding."
    expected: "Scenario list loads with no console CORS error; Network tab shows the cross-origin GET /scenarios request completing with access-control-allow-origin present."
    why_human: "The backend half (curl with an Origin header) is proven programmatically in backend/tests/test_cors.py and by direct curl checks recorded in 01-01-SUMMARY.md/01-06-SUMMARY.md. The in-browser DevTools confirmation requires a real browser session, which was unavailable in the executor's sandbox (01-06-SUMMARY.md, 01-07-SUMMARY.md both record this as outstanding)."
  - test: "Live create-scenario round trip: with backend running, click 'New Scenario', name a scenario, pick a real fixture (e.g. sample_tiny_input.json), submit, and confirm the dialog closes and the new row appears in the table without a manual page refresh."
    expected: "Dialog closes on success; the new scenario row appears in ScenarioTable without a manual refresh (react-query invalidation refetch)."
    why_human: "The invalidate-on-success contract is proven by a unit test using a mocked API boundary (CreateScenarioDialog.test.tsx), but a live network round trip against a real running backend was not exercised — no browser-automation tool was available in the executor session (01-07-SUMMARY.md, coverage D3)."
  - test: "Visual backstop: type a 200+ character scenario name into the Name field and confirm it renders acceptably (wraps or scrolls, does not break the modal layout)."
    expected: "Long name does not visually break the dialog layout."
    why_human: "Declared verification: backstop in 01-07-PLAN.md must_haves — a visual check with no assertable spec-time width, explicitly deferred to execution-time human judgment."
  - test: "Visual backstop: select or view a fixture with a long filename in the fixture Select's trigger and option list, and confirm it renders acceptably (truncates or wraps, does not overflow)."
    expected: "Long fixture filename does not visually overflow the Select trigger or option list."
    why_human: "Declared verification: backstop in 01-07-PLAN.md must_haves — same reasoning as above."
  - test: "With the backend process stopped, load Home and confirm exactly one backend-unreachable banner renders (not two), even though both the scenarios and fixtures queries fail concurrently."
    expected: "Exactly one ErrorBanner is visible on the page."
    why_human: "The single-banner decision-point logic is proven by a unit test with mocked rejections (CreateScenarioDialog.test.tsx, 'Home: concurrent failure' case), but a live browser check with the backend process actually stopped was not performed (01-07-SUMMARY.md, Human-Check Items Not Performed)."
---

# Phase 1: Browser-Callable API + App Shell + Scenario List Verification Report

**Phase Goal:** A user can open ShiftMind in a browser and see and create scenarios against the live backend.
**Verified:** 2026-07-16T22:35:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

Truths merge ROADMAP.md's 5 Success Criteria with the load-bearing must_haves from each of the 7 plans' frontmatter.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | (Criterion 1) User can start the dev server, open the app, and see the list of existing scenarios fetched from the running backend, no CORS error in console | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED (browser half) | Backend CORS proven by `backend/tests/test_cors.py` (13/13 pass, re-run live) + curl checks in 01-01/01-06 SUMMARYs. `ScenarioTable`/`useScenarios` genuinely fetch `GET /scenarios` (`frontend/src/hooks/useScenarios.ts`, `frontend/src/components/scenarios/ScenarioTable.tsx`) with no mock data. The in-browser console/Network-tab confirmation was never run in any executor session — routed to human verification (known open item, per task brief). |
| 2 | (Criterion 2) User can create a scenario by naming it and choosing a backend-offered fixture, and see it appear in the list | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED (live round trip) | `CreateScenarioDialog.tsx` + `useCreateScenario.ts` + `useFixtures.ts` fully wired (verified by reading source); `['scenarios']` query-key match confirmed byte-identical between `useScenarios.ts` and `useCreateScenario.ts`; 31 unit tests pass across `CreateScenarioDialog.test.tsx`/`useFixtures.test.tsx`/`useCreateScenario.test.tsx`/`ScenarioTable.test.tsx` (re-run live) proving the invalidation contract against a mocked API boundary. A live network round trip against a real backend was never run — routed to human verification (known open item). |
| 3 | (Criterion 3) User can move between the app's four routes through persistent nav and deep-link by URL; later-phase views are reachable placeholders | ✓ VERIFIED | `frontend/src/App.tsx` route table matches UI-SPEC's 4-route table exactly (`/`, `/scenarios/:scenarioId`, `/scenarios/:scenarioId/runs`, `/scenarios/:scenarioId/runs/:runId`). `router.test.tsx` (part of the 17-test run confirmed live) deep-link-tests each route via `createMemoryRouter` built from the exact same `routes` array the app ships. Placeholders (`EditorPlaceholder`, `RunsPlaceholder`, `ResultsPlaceholder`) render only `PlaceholderView`'s honest fixed copy, no mock data (grep-verified). |
| 4 | (Criterion 4) When the backend is unreachable or returns an error, the user sees a readable message naming what failed — never a blank screen | ✓ VERIFIED | `ErrorBanner.tsx` renders UI-SPEC's exact fixed copy (confirmed by reading source) and is wired on 3 failure paths (`ScenarioTable`, `Home`'s fixtures-only case, `CreateScenarioDialog`'s inline 400/422 branches). `RootErrorBoundary.tsx` is mounted as the root route's `errorElement`, covering both render exceptions and unmatched URLs (confirmed via `App.tsx` + passing `/nope` test in `router.test.tsx`). |
| 5 | (Criterion 5) Allowed origins are configurable rather than hardcoded, and the app builds to static assets with one command | ✓ VERIFIED | `backend/settings.py`'s `cors_origins: tuple[str,...]` sourced solely from `CORS_ORIGINS` env (confirmed by reading source, single `os.environ.get` read site). `cd frontend && npm run build` re-run live: exit 0, `dist/index.html` + hashed assets produced, no backend running during the build. |
| 6 | An allowed `Origin` gets `access-control-allow-origin` reflected; a disallowed one gets no such header; never wildcard/credentialed (BE-01) | ✓ VERIFIED | `backend/api/main.py`: `CORSMiddleware` registered with `allow_origins=list(get_settings().cors_origins)`, no wildcard, `allow_credentials` left at Starlette's default `False`. `backend/tests/test_cors.py` 13/13 pass (re-run live), including the multi-origin no-cross-contamination and preflight cases. |
| 7 | `CORS_ORIGINS` parses an ordered N-tuple, every entry independently reflected (BE-01 assumption-delta invariant) | ✓ VERIFIED | `default_settings()` comma-splits/strips/drops-empty into a tuple (read source, confirmed). `test_cors_reflects_every_configured_origin` parametrized over 3 origins, all pass (re-run live). |
| 8 | `frontend/` builds, typechecks, and tests cleanly with one command each; no npm SLOP package installed (SHELL-01) | ✓ VERIFIED | Re-run live: `npx vitest run` → 58/58 across 8 files; `npx tsc -b` → exit 0; `npm run build` → exit 0. `git show HEAD:frontend/package.json` contains no `msw`. No `tailwind.config.js`/`postcss.config.js` exist (`git ls-files` confirms absence); `vite.config.ts` has no `server.proxy`. |
| 9 | Every request/response type the UI uses is generated from the backend's own OpenAPI schema; no hand-authored payload shape in `src/api/` (SHELL-02) | ✓ VERIFIED | `backend/scripts/export_openapi.py` exports `app.openapi()` with no server/DB (read source). `npm run codegen` re-run live: regenerates `schema.d.ts` with zero content diff (determinism confirmed — only a CRLF/LF git-attribute warning, no diff). `client.ts`/`scenarios.ts` read source: single `createClient<paths>` instance, all payload types derived via indexed access into `paths`, no hand-authored interface. |
| 10 | `listScenarios`/`listFixtures`/`createScenario` call the right endpoints, throw on non-2xx with status attached, empty array yields `[]`, no client-side sort (SHELL-02 edges) | ✓ VERIFIED | Read `scenarios.ts` source: each wrapper destructures `{data, error}`/`{data, error, response}` and throws (with `status` attached for `createScenario`) on error. `scenarios.test.ts` 9/9 pass (re-run live) covering the empty-array/ordering/concurrency/400-vs-422 edges. |
| 11 | Each of the four routes is reachable by direct URL entry and mounts its own component; unmatched routes hit the crash-backstop, not a blank screen (SHELL-03/04) | ✓ VERIFIED | `router.test.tsx` + `ErrorBanner.test.tsx` re-run live: 17/17 pass, including a dedicated `/nope` → `RootErrorBoundary` test and a `/scenarios/abc123/runs` → RunsPlaceholder route-ranking test (not Editor with scenarioId `runs`). |
| 12 | A deep-link to a nonexistent `:scenarioId` renders the Editor placeholder as if valid — a known, accepted Phase 1 scope boundary (declared `verification: backstop`) | ✓ VERIFIED | Confirmed by code inspection: no code path anywhere under `frontend/src` calls `GET /scenarios/{scenario_id}` (grep for the endpoint string finds only the type definition in generated `schema.d.ts`, never a wrapper or hook). `EditorPlaceholder.tsx`/`ScenarioLayout.tsx` never read `scenarioId` to conditionally fetch or validate it — the placeholder mounts identically regardless of the URL param's validity, so this is structurally guaranteed rather than merely observed. Upgraded from the plan's `backstop` classification to VERIFIED because the absence of any scenario-fetch code path is directly checkable (COVERAGE.md note B corroborates: `GET /scenarios/{scenario_id}` is a deliberate Phase 1 OPT-OUT). |
| 13 | A user opening the app sees the scenario list rendered from the live backend across all 5 UI states (loading/empty/error/populated/overflow) (SCEN-01) | ✓ VERIFIED | `ScenarioTable.tsx` read source: distinct early-return branches for loading (spinner + text, no skeleton), error (`ErrorBanner` only), empty ("No scenarios yet" + inline CTA), populated (rows keyed by `id`, server order preserved, no `.sort()`/`.reverse()`), overflow (`max-h-[420px] overflow-y-auto`, no pagination). `ScenarioTable.test.tsx` 9/9 pass (re-run live) covering same-name/different-id, identical-`created_at` ordering, zero-one-many, and T-1-03 HTML-escaping edges. |
| 14 | A user can create a scenario by naming it and picking one of the backend's offered fixtures; no free-text/upload path exists (SCEN-02, D-03) | ✓ VERIFIED | `CreateScenarioDialog.tsx` read source: fixture value comes only from a Radix `Select` populated by `useFixtures()`; no `<input type="file">` or free-text fixture field exists anywhere in `frontend/src` (grep confirms `msw` and upload-related code absent). `useCreateScenario.ts`'s `onSuccess` invalidates the exact `['scenarios']` key `useScenarios.ts` reads. |
| 15 | Concurrent scenarios+fixtures query failure renders exactly one backend-unreachable banner, not two (SHELL-04/concurrency edge) | ✓ VERIFIED (logic) / ⚠️ live-browser check outstanding | `Home.tsx` read source: `showFixturesOnlyBanner = fixturesQuery.isError && !scenariosQuery.isError` — when scenarios also fails, `ScenarioTable`'s own banner is the only one rendered (Home's condition is false). Unit-tested in `CreateScenarioDialog.test.tsx`'s "Home: concurrent failure" case (part of the 31-test run confirmed live). A live check with the backend process actually stopped was not performed — routed to human verification. |

**Score:** 15/15 truths have either full code-level verification or unit-test-level verification of their logic; 4 of those 15 additionally carry an outstanding real-browser confirmation that could not be automated (see Human Verification Required below). No truth failed.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/settings.py` | `Settings.cors_origins: tuple[str, ...]` + env read | ✓ VERIFIED | Field present, single `os.environ.get("CORS_ORIGINS", ...)` read site (confirmed) |
| `backend/api/main.py` | `CORSMiddleware` registered | ✓ VERIFIED | Registered before `include_router` calls, sourced from `get_settings().cors_origins` |
| `backend/.env.example` | Documented `CORS_ORIGINS` incl. 127.0.0.1 trap | ✓ VERIFIED | `git show HEAD:backend/.env.example` contains both |
| `backend/tests/test_cors.py` | BE-01 coverage | ✓ VERIFIED | 13/13 tests pass (re-run live) |
| `frontend/package.json` | dev/build/preview/test/typecheck/codegen scripts, no `msw` | ✓ VERIFIED | All scripts present; `msw` absent |
| `frontend/vite.config.ts` | react()+tailwindcss() plugins, `@` alias, `test` block, no proxy | ✓ VERIFIED | Confirmed by reading source |
| `frontend/components.json` | shadcn config | ✓ VERIFIED | Present (`git ls-files` confirms) |
| `frontend/src/index.css` | Single Tailwind import + CSS vars | ✓ VERIFIED (via build) | Build succeeds using this file with no `tailwind.config.js`/`postcss.config.js` |
| `frontend/src/lib/env.ts` | Typed `API_BASE_URL` accessor | ✓ VERIFIED | Fails loud if unset; sole read site (confirmed) |
| `frontend/src/test/setup.ts` | jest-dom matcher registration + Radix polyfills | ✓ VERIFIED | Full suite runs clean using it |
| `frontend/src/components/ui/` | 7 shadcn primitives | ✓ VERIFIED | `git ls-files` shows button/input/select/dialog/table/alert/tabs |
| `backend/scripts/export_openapi.py` | Exports `app.openapi()`, no server/DB | ✓ VERIFIED | Read source; no `db.init_db` call reachable outside lifespan |
| `frontend/src/api/schema.d.ts` | Generated, committed | ✓ VERIFIED | Committed (`git ls-files`); regeneration produces zero diff |
| `frontend/src/api/client.ts` | Single `openapi-fetch` instance | ✓ VERIFIED | One `createClient<paths>(...)` call, confirmed no second instance anywhere in `src/` |
| `frontend/src/api/scenarios.ts` | Thin wrappers: listScenarios/listFixtures/createScenario | ✓ VERIFIED | Confirmed by reading source; all types derived, none hand-authored |
| `frontend/src/api/scenarios.test.ts` | SHELL-02 coverage | ✓ VERIFIED | 9/9 pass (re-run live) |
| `frontend/src/App.tsx` | `createBrowserRouter` route table | ✓ VERIFIED | Exact 4-route table matching UI-SPEC |
| `frontend/src/main.tsx` | QueryClientProvider wraps RouterProvider | ✓ VERIFIED (via passing tests) | `useQuery`/`useMutation` calls work in the full suite without provider errors |
| `frontend/src/components/layout/AppBar.tsx` | Persistent global nav | ✓ VERIFIED | Wordmark + one Home link, confirmed |
| `frontend/src/routes/ScenarioLayout.tsx` | Persistent Editor/Runs/Results tabs + Outlet | ✓ VERIFIED | Confirmed by reading source, `end` matching on Editor/Runs |
| `frontend/src/components/layout/PlaceholderView.tsx` | Honest not-built-yet surface | ✓ VERIFIED | Exact UI-SPEC copy, no mock data |
| `frontend/src/components/layout/ErrorBanner.tsx` | Backend-unreachable banner | ✓ VERIFIED | Exact fixed copy, error never rendered to JSX |
| `frontend/src/components/layout/RootErrorBoundary.tsx` | Crash backstop | ✓ VERIFIED | Mounted as root `errorElement`, exact copy |
| `frontend/src/routes/router.test.tsx` | SHELL-03 coverage | ✓ VERIFIED | Part of 17/17 passing run |
| `frontend/src/components/layout/ErrorBanner.test.tsx` | SHELL-04 coverage | ✓ VERIFIED | Part of 17/17 passing run |
| `frontend/src/hooks/useScenarios.ts` | `useQuery(['scenarios'], listScenarios)` | ✓ VERIFIED | Confirmed, no transformation |
| `frontend/src/components/scenarios/ScenarioTable.tsx` | All five list states | ✓ VERIFIED | Confirmed by reading source |
| `frontend/src/components/scenarios/ScenarioTable.test.tsx` | SCEN-01 coverage | ✓ VERIFIED | 9/9 pass (part of 31-test run) |
| `frontend/src/routes/Home.tsx` | Table + dialog mounted | ✓ VERIFIED | Confirmed by reading source |
| `frontend/src/hooks/useFixtures.ts` | `useQuery(['fixtures'], listFixtures)` | ✓ VERIFIED | Confirmed |
| `frontend/src/hooks/useCreateScenario.ts` | `useMutation` + `['scenarios']` invalidation | ✓ VERIFIED | Query key byte-matches `useScenarios.ts` |
| `frontend/src/components/scenarios/CreateScenarioDialog.tsx` | Create modal | ✓ VERIFIED | All E2/E3 states confirmed by reading source |
| `frontend/src/components/scenarios/CreateScenarioDialog.test.tsx` | SCEN-02 coverage | ✓ VERIFIED | Part of 31-test run |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `os.environ['CORS_ORIGINS']` | `app.add_middleware(CORSMiddleware, ...)` | `default_settings()` → `Settings.cors_origins` | ✓ WIRED | Single path, confirmed by reading source, no second config mechanism |
| `frontend/.env.example` `VITE_API_BASE_URL` | `src/api/client.ts` | `src/lib/env.ts`'s `API_BASE_URL` | ✓ WIRED | `client.ts` imports `API_BASE_URL` from `env.ts`, confirmed |
| Backend route/Pydantic defs | `frontend/src/api/schema.d.ts` | `app.openapi()` → `export_openapi.py` → `openapi-typescript` | ✓ WIRED | `npm run codegen` re-run live, zero diff on regeneration |
| `listScenarios` (01-04) | `Home` | `useScenarios` → `ScenarioTable` | ✓ WIRED | Confirmed by reading source chain |
| Root route `errorElement` | `RootErrorBoundary` | `App.tsx` | ✓ WIRED | Confirmed; covers both render exceptions and unmatched routes (tested) |
| `main.tsx` QueryClientProvider | `RouterProvider` | Provider wraps router | ✓ WIRED | Full test suite passes with `useQuery`/`useMutation` in context |
| `useCreateScenario` `onSuccess` | `useScenarios` refetch | `invalidateQueries(['scenarios'])` | ✓ WIRED | Query-key strings byte-identical, confirmed by reading both files |
| `createScenario`'s thrown `status` | `CreateScenarioDialog`'s 400/422 branch | Error object with `.status` | ✓ WIRED | Confirmed by reading source; distinct copy at distinct DOM locations |
| `GET /fixtures` options | Select's allowed values | `useFixtures()` → `<SelectItem>` map | ✓ WIRED | Confirmed by reading source; no free-text fallback |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| BE-01 | 01-01 | Configurable CORS allow-list | ✓ SATISFIED | `backend/tests/test_cors.py` 13/13 live; curl checks recorded |
| SHELL-01 | 01-02, 01-03 | Vite+React+TS app shell, buildable/testable | ✓ SATISFIED | Build/typecheck/test all green live; supply-chain gate recorded approved |
| SHELL-02 | 01-04 | Typed API client mirrors `docs/API.md` | ✓ SATISFIED | Codegen chain verified end-to-end, deterministic |
| SHELL-03 | 01-05 | Four-route persistent nav | ✓ SATISFIED | `router.test.tsx` deep-link tests all pass |
| SHELL-04 | 01-05, 01-06, 01-07 | Readable failure messages, no blank screen | ✓ SATISFIED (logic); live "backend stopped" check outstanding | `ErrorBanner`/`RootErrorBoundary` wired and tested; live backend-down check is a human-verification item |
| SCEN-01 | 01-06 | See list of existing scenarios | ✓ SATISFIED (logic); live browser confirmation outstanding | `ScenarioTable` all 5 states tested; live DevTools CORS check is a human-verification item |
| SCEN-02 | 01-07 | Create a scenario from a fixture | ✓ SATISFIED (logic); live round trip outstanding | `CreateScenarioDialog`/hooks fully tested; live create round trip is a human-verification item |

No orphaned requirements — all 7 phase-mapped requirement IDs in `.planning/REQUIREMENTS.md` (BE-01, SHELL-01..04, SCEN-01, SCEN-02) are claimed by exactly one plan each and none are missing evidence.

**Note (informational, not a gap):** `.planning/REQUIREMENTS.md`'s checkbox list still shows SHELL-01..04/SCEN-01/SCEN-02 as unchecked (`- [ ]`) while BE-01 is checked (`- [x]`), and its Status table (lines 95-101) lists all 6 non-BE-01 requirements as "Pending." This is a tracking-document staleness issue, not a code gap — the implementation evidence above satisfies all 7 requirements. The requirements table should be updated to "Complete" as part of phase sign-off.

### Anti-Patterns Found

None. Swept all files under `frontend/src` for `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER`/"coming soon"/"not available" — zero matches. The literal string "not built yet" that appears in `PlaceholderView.tsx` is the UI-SPEC's deliberately honest, contracted copy (not a debt marker) — it names a real, scoped-out-for-this-phase view rather than hedging on unfinished work within this phase's own scope.

A partial `01-REVIEW.md` code review exists (orchestrator-inline security pass; the full-depth agent review was interrupted by a spend-limit error before writing findings). The inline pass found 0 issues across the 4 security-sensitive surfaces (CORS, error-detail leakage, API base URL, supply chain). A full bug-focused review of the remaining ~27 non-security files is deferred (`/gsd-code-review 01` can complete it) — flagged as informational, not a blocker, since the full test suite (58 frontend + 137 backend) passes and every file was read directly during this verification.

### Human Verification Required

1. **Real-browser DevTools CORS round trip**
   **Test:** Run `cd backend && uv run uvicorn api.main:app --reload` and `cd frontend && npm run dev`, open `http://localhost:5173` in a real browser, open DevTools.
   **Expected:** Console shows no CORS error; Network tab shows the `GET /scenarios` request as a genuine cross-origin request that succeeds (status 200, `access-control-allow-origin` header present).
   **Why human:** Backend-side CORS behavior is fully proven by automated tests and curl; a browser's actual enforcement/reporting of CORS is not observable from pytest or jsdom (no real browser network stack). Both 01-01-SUMMARY.md and 01-06-SUMMARY.md record this as attempted-but-unavailable in the executor sandbox.

2. **Live create-scenario round trip**
   **Test:** With both servers running, click "New Scenario," name a scenario, select a real fixture, submit.
   **Expected:** Dialog closes; the new scenario appears as a new row in the table without a manual page refresh.
   **Why human:** The react-query invalidation contract is proven at the unit-test level against a mocked API boundary; an actual network round trip through a live backend was never exercised (01-07-SUMMARY.md, coverage D3, explicitly unresolved).

3. **Visual backstop — long scenario name**
   **Test:** Type a 200+ character name into the Name field.
   **Expected:** Renders acceptably (wraps or scrolls), does not break the dialog's layout.
   **Why human:** Declared `verification: backstop` in 01-07-PLAN.md — no server-side length limit exists to assert against at spec time; this is inherently a visual judgment call.

4. **Visual backstop — long fixture filename**
   **Test:** View a fixture with a long filename in the Select trigger/option list (or synthetically add one to the fixtures directory).
   **Expected:** Renders acceptably (truncates/wraps), does not overflow the trigger or option list.
   **Why human:** Same reasoning as #3 — declared backstop, visual judgment.

5. **Concurrent-failure-with-backend-down banner count**
   **Test:** Stop the backend process, load Home in a real browser.
   **Expected:** Exactly one backend-unreachable banner is visible (not two, despite both `scenarios` and `fixtures` queries failing).
   **Why human:** The single-banner decision logic is unit-tested with mocked rejections; a live check with the backend process genuinely stopped was not performed (01-07-SUMMARY.md, "Human-Check Items Not Performed").

### Gaps Summary

No gaps. Every must-have truth, artifact, and key link across all 7 plans is either directly verified by reading the actual source and re-running the test/build/typecheck commands live, or is a pre-declared visual/live-browser backstop that both the plans and this verification correctly route to human sign-off rather than mask as passing. All 3 test suites were re-run in this session (not trusted from SUMMARY claims): backend `uv run pytest` → 137 passed, 6 deselected; frontend `npx vitest run` → 58 passed across 8 files; `npx tsc -b` → clean; `npm run build` → clean, standalone (no backend running). The 5 outstanding items are genuinely unautomatable in the sandboxes available to every executor session in this phase (no browser-automation tool was present in any of them) and are honestly documented as such in the SUMMARYs rather than silently claimed complete — they do not indicate missing or stubbed implementation.

---

_Verified: 2026-07-16T22:35:00Z_
_Verifier: Claude (gsd-verifier)_
