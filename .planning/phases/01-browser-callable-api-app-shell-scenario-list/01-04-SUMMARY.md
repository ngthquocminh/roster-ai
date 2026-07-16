---
phase: 01-browser-callable-api-app-shell-scenario-list
plan: 04
subsystem: api
tags: [openapi-typescript, openapi-fetch, fastapi, typescript, codegen, vitest]

requires:
  - phase: 01-browser-callable-api-app-shell-scenario-list
    provides: "frontend scaffold (Vite+React+TS), src/lib/env.ts's API_BASE_URL accessor, openapi-fetch/openapi-typescript deps already in package.json"
provides:
  - "backend/scripts/export_openapi.py — exports app.openapi() to JSON, no server/DB"
  - "frontend codegen pipeline (npm run codegen) producing committed schema.d.ts"
  - "single openapi-fetch client instance (src/api/client.ts)"
  - "three typed wrappers: listScenarios, listFixtures, createScenario (src/api/scenarios.ts)"
affects: [01-05, 01-06, 01-07, phase-2, phase-3, phase-4]

tech-stack:
  added: []
  patterns:
    - "Codegen'd typed client, thin hand-written wrappers (RESEARCH.md Pattern 1) — every endpoint payload type derives from schema.d.ts via indexed access into `paths`, never hand-typed"
    - "Wrapper functions destructure { data, error } (or + response), throw on error, return data — the shape every future endpoint wrapper (Phases 2-4) should follow"

key-files:
  created:
    - backend/scripts/export_openapi.py
    - frontend/src/api/schema.d.ts
    - frontend/src/api/client.ts
    - frontend/src/api/scenarios.ts
    - frontend/src/api/scenarios.test.ts
  modified:
    - frontend/package.json
    - .gitignore

key-decisions:
  - "Committed schema.d.ts, gitignored frontend/openapi.json (per PLAN.md's locked decision) — npm install && npm run build works standalone, no running backend required"
  - "createScenario's time_limit_s made optional in the wrapper's own parameter type (derived via Omit/Partial over an indexed-access CreateScenarioBody type, not hand-listed) — openapi-typescript marks JSON-Schema-`default`-carrying properties as non-optional in its generated TS type, which is a codegen-tool artifact, not a real API requirement; ScenarioCreate's actual `required` array (and docs/API.md) list only name+fixture as required. Caller omits time_limit_s; wrapper defaults it to 60 (docs/API.md's documented default) before the wire call."

requirements-completed: [SHELL-02]

coverage:
  - id: D1
    description: "backend/scripts/export_openapi.py exports app.openapi() to JSON with no running server and no DB file created"
    requirement: "SHELL-02"
    verification:
      - kind: other
        ref: "uv run python scripts/export_openapi.py <path> — exit 0, valid JSON with openapi/paths keys, no backend/var/ created"
        status: pass
    human_judgment: false
  - id: D2
    description: "npm run codegen regenerates schema.d.ts from the backend's own schema, deterministically, without a running server"
    requirement: "SHELL-02"
    verification:
      - kind: other
        ref: "npm run codegen (run twice consecutively) — exit 0, zero diff on schema.d.ts between runs"
        status: pass
    human_judgment: false
  - id: D3
    description: "Single openapi-fetch client instance typed against generated paths, baseUrl from API_BASE_URL"
    requirement: "SHELL-02"
    verification:
      - kind: unit
        ref: "grep -c 'createClient<' frontend/src/api/client.ts == 1; grep -rn createClient src --include=*.ts --include=*.tsx | grep -v client.ts == empty"
        status: pass
    human_judgment: false
  - id: D4
    description: "listScenarios, listFixtures, createScenario — three thin typed wrappers covering all 9 behavior cases (empty array, ordering, non-2xx rejection, 400 vs 422 status, concurrency)"
    requirement: "SHELL-02"
    verification:
      - kind: unit
        ref: "frontend/src/api/scenarios.test.ts (9 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Standalone build works with no backend running (npm install && npm run build)"
    requirement: "SHELL-02"
    verification:
      - kind: other
        ref: "npm run build (tsc -b && vite build) — exit 0, dist/ produced"
        status: pass
    human_judgment: false

duration: 55min
completed: 2026-07-16
status: complete
---

# Phase 1 Plan 04: Typed API Client (SHELL-02) Summary

**Codegen'd typed client (`openapi-typescript` + `openapi-fetch`) generating `schema.d.ts` from the backend's own live `app.openapi()`, with three thin wrappers (`listScenarios`, `listFixtures`, `createScenario`) — no hand-typed request/response shapes anywhere in `src/api/`.**

## Performance

- **Duration:** ~55 min (across a session interruption — resumed cleanly from an intact worktree)
- **Started:** 2026-07-16T17:34:00Z
- **Completed:** 2026-07-16T18:00:00Z
- **Tasks:** 2 (Task 2 followed the TDD RED→GREEN cycle; one Rule-1 fix landed after GREEN)
- **Files modified:** 7 (5 created, 2 modified)

## Accomplishments
- `backend/scripts/export_openapi.py` exports `app.openapi()` to JSON with no server started and no DB file created — verified directly (`backend/var/` never appears).
- `frontend/package.json` gained a two-step `codegen` script (`codegen:export` via `uv run --directory ../backend`, `codegen:types` via `openapi-typescript`) so a failure names which half broke.
- `frontend/src/api/schema.d.ts` is generated and committed; `frontend/openapi.json` is gitignored as the intermediate.
- `frontend/src/api/client.ts` exports the single `createClient<paths>` instance, `baseUrl` from `src/lib/env.ts`'s `API_BASE_URL`.
- `frontend/src/api/scenarios.ts` exports exactly `listScenarios`, `listFixtures`, `createScenario` — no more; every payload type traces to the generated `paths`.
- `frontend/src/api/scenarios.test.ts` proves all 9 `<behavior>` cases from the plan, mocked at the `./client` boundary with `vi.mock` (not `msw`).
- Full verification block green: `npx vitest run` (10/10 across the frontend suite), `npx tsc -b` (real project-references typecheck), `npm run build` (standalone, no backend running), full backend `uv run pytest` (137 passed).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add the OpenAPI export script and the frontend codegen pipeline** - `d0a1459` (feat)
2. **Task 2: Build the typed client instance and the three thin endpoint wrappers** (TDD):
   - RED - `4008193` (test) — `scenarios.test.ts`, fails because `scenarios.ts` doesn't exist yet
   - GREEN - `3ac52fb` (feat) — `client.ts` + `scenarios.ts`, all 9 tests pass
   - Rule-1 fix - `ac841c9` (fix) — corrected `createScenario`'s `time_limit_s` typing after `npm run build` (the real `tsc -b` check) surfaced a genuine type error that the plan's own `npx tsc --noEmit` verify command silently missed (see Deviations)

**Plan metadata:** this commit (docs: complete plan)

## Files Created/Modified
- `backend/scripts/export_openapi.py` - exports `app.openapi()` to JSON; resolves `backend/` onto `sys.path` from `__file__`, same fix `conftest.py` applies for pytest
- `frontend/src/api/schema.d.ts` - generated by `openapi-typescript`, committed, never hand-edited
- `frontend/src/api/client.ts` - the one `openapi-fetch` client instance
- `frontend/src/api/scenarios.ts` - three thin wrappers: `listScenarios`, `listFixtures`, `createScenario`
- `frontend/src/api/scenarios.test.ts` - 9 tests covering every `<behavior>` case
- `frontend/package.json` - added `codegen`, `codegen:export`, `codegen:types` scripts
- `.gitignore` - added `frontend/openapi.json`

## Decisions Made
- Committed `schema.d.ts`, gitignored `openapi.json` (locked by `01-04-PLAN.md`'s `<planner_decisions>`, executed as specified).
- `createScenario`'s parameter type derives `CreateScenarioBody` via an indexed access into `paths["/scenarios"]["post"]["requestBody"]["content"]["application/json"]`, then narrows it with `Omit`/`Partial` to make `time_limit_s` optional — the plan's own text explicitly permits deriving parameter types via indexed access ("Deriving a parameter type from the generated types... via an indexed access into paths is fine and encouraged; declaring the field list by hand is not"). The wrapper defaults `time_limit_s` to `60` (matching `docs/API.md`'s documented default) when the caller omits it, since SCEN-02's UI never collects it.

## Orchestrator-requested findings (a/b/c)

**(a) `uv run --directory` vs `cd` fallback:** `uv run --directory ../backend python scripts/export_openapi.py ../frontend/openapi.json` **worked directly** — uv 0.10.8 supports `--directory`. No `cd ../backend && uv run ...` fallback was needed. Verified by running the exact command from `frontend/` and confirming `openapi.json` was written with exit 0.

**(b) Generated schema vs `docs/API.md` agreement:** Agreed in every documented particular I compared:
- `ScenarioOut` fields: `id, name, fixture, time_limit_s, created_at` — exact match.
- `ScenarioCreate` fields: `name, fixture, time_limit_s` — exact match; `required: [name, fixture]` in the raw JSON schema matches docs/API.md's rules table (`time_limit_s` optional, default `60`).
- `RunOut` fields: `id, scenario_id, status, created_at, started_at, finished_at, solver_status, error` — exact match.
- Status codes: `POST /scenarios` → 400/422/201; `GET/POST /scenarios/{id}/...` → 404; `GET /runs/{id}/result` → 409; `POST /constraints` → 503; `GET /runs/{id}/insights` → 502 — all match docs/API.md's "Status code summary" table.
- One non-drift finding worth recording: the generated schema shows a `422` response on every path-parameterized `GET` (`/scenarios/{scenario_id}`, `/runs/{run_id}`, `/scenarios/{scenario_id}/runs`) that `docs/API.md`'s per-endpoint sections don't call out. This is standard FastAPI behavior (path-parameter coercion can fail validation on any route with a path param) rather than an application-level status this endpoint actually returns in practice — not a doc staleness finding, just codegen boilerplate. `docs/API.md` remains accurate.
- A **real disagreement did surface, but between the generated TS types and the actual API contract, not between the schema and docs/API.md**: `openapi-typescript` types every property carrying a JSON-Schema `default` (here, `time_limit_s`) as non-optional in the generated `paths` type, even though `ScenarioCreate`'s own `required` array (and `docs/API.md`) list it as optional. This is a known codegen-tool nuance (defaults conflated with required-ness), not a backend/docs drift — fixed in the wrapper via `Omit`/`Partial`, not by editing `schema.d.ts`.

**(c) Codegen determinism:** Confirmed deterministic across two consecutive runs, twice independently (once during Task 1, once again before writing this summary) — `diff` between the pre- and post-second-run `schema.d.ts` produced zero output both times.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `createScenario`'s hand-shaped parameter type broke the real project typecheck**
- **Found during:** Task 2, after the GREEN commit, while running the plan's own `<verification>` block item `npm run build`
- **Issue:** The initial `createScenario(body: { name: string; fixture: string })` signature passed `npx tsc --noEmit` (the command literally specified in both tasks' `<verify>` blocks) but failed `npm run build` (`tsc -b && vite build`) with `Property 'time_limit_s' is missing`. Root cause: `frontend/tsconfig.json` is a "solution style" config (`"files": []`, only `references`) — running bare `npx tsc --noEmit` from the repo root typechecks **zero files** and always exits 0, regardless of real type errors. The actual project typecheck requires `tsc -b` (what `npm run build` runs). This is a gap in the plan's specified verify command, not something this plan can fix (PLAN.md is not mine to edit), so it's recorded here for future plans to specify `tsc -b` instead.
- **Fix:** Derived `CreateScenarioBody` via indexed access into `paths` (no hand-listed fields), narrowed with `Omit<CreateScenarioBody, "time_limit_s"> & Partial<Pick<CreateScenarioBody, "time_limit_s">>` for the wrapper's public parameter type, and default `time_limit_s: 60` before calling `client.POST`.
- **Files modified:** `frontend/src/api/scenarios.ts`, `frontend/src/api/scenarios.test.ts` (updated one assertion to expect the defaulted `time_limit_s` in the outgoing body)
- **Verification:** `npx tsc -b --force` exit 0; `npm run build` exit 0 (dist/ produced); `npx vitest run src/api/scenarios.test.ts` 9/9 pass; full `npx vitest run` 10/10 pass
- **Committed in:** `ac841c9`

---

**Total deviations:** 1 auto-fixed (1 bug, Rule 1)
**Impact on plan:** Necessary for correctness — without it, `npm install && npm run build` (an explicit Phase 1 success criterion) would fail on a clean checkout. No scope creep; the fix stayed inside `frontend/src/api/scenarios.ts`'s existing responsibility.

## Issues Encountered

- **Acceptance-criteria grep imprecisions (informational, not corrected in code):**
  1. `grep -c 'createClient' frontend/src/api/client.ts` returns `2`, not the `1` the acceptance criteria literally expects — because the import line (`import createClient from "openapi-fetch"`) and the usage line (`export const client = createClient<paths>(...)`) both match the substring, and `grep -c` counts matching lines. `RESEARCH.md`'s own canonical Pattern 1 example has the identical two-line shape and would produce the same count. The actual invariant — exactly one client instance — holds: `grep -c 'createClient<'` (the invocation only) returns `1`, and no second `createClient(` call site exists anywhere else in `src/`.
  2. `grep -rn 'localhost:8000\|127.0.0.1:8000' frontend/src` matches one line: a doc-comment in `src/lib/env.ts` (from plan 01-03, untouched by this plan) that *describes* the failure mode `API_BASE_URL`'s fail-loud guard exists to prevent ("a built production bundle that quietly defaults to `localhost:8000`"). No actual hardcoded backend origin exists in `src/api/` or anywhere else touched by this plan.
  3. The naive interface/type-declaration grep (`^\s*(export\s+)?(interface|type)\s+\w+`) flags one line in `scenarios.ts`: `type CreateScenarioBody = paths[...]`. This is a derived indexed-access alias with no hand-listed fields — explicitly permitted by this plan's own `<action>` text (see Decisions above) and necessary for the Rule-1 fix above. Not a hand-authored endpoint shape in the sense SHELL-02 is guarding against.

  None of these represent an actual SHELL-02 violation; all are heuristic false positives from grep patterns that can't distinguish "hand-listed fields" from "derived via indexed access" or "code" from "comment". Recorded here rather than silently reconciled, per the plan's own instruction to report disagreements rather than paper over them.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- SHELL-02 is fully satisfied: the typed client structurally cannot drift from `docs/API.md`, since both derive from the same FastAPI route/Pydantic definitions.
- Plans 01-05/01-06/01-07 can build hooks (`useScenarios`, `useFixtures`, `useCreateScenario`) directly on top of `listScenarios`/`listFixtures`/`createScenario` per RESEARCH.md Pattern 3, with `createScenario`'s thrown `{status, ...}` shape ready for the 400-vs-422 branching UI-SPEC's Copywriting Contract requires.
- No blockers. One note for future phase planners: specify `npx tsc -b` (not bare `npx tsc --noEmit`) in `<verify>` blocks for this repo's frontend, since the root `tsconfig.json`'s solution-style config makes the bare form a silent no-op.

---
*Phase: 01-browser-callable-api-app-shell-scenario-list*
*Completed: 2026-07-16*
