---
baseline_commit: e925c07965a363f7f0a6aae73b4bfddcd3842e4d
---

# Story 1.9: Prove Viewer Parity and Mutation Denial

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the product team,
we want the viewer's parity and read-only boundary proven automatically before release,
so that the facts the planner inspects are exactly the facts later used by the agent, and no path can alter fixture source data.

**This is a test/proof story — no new planner-visible surface.** It adds no route, no component, no endpoint. It writes the automated evidence that Gate A requires: that the Scenario Data viewer (Story 1.7/1.8) shows exactly the same normalized values the backend contract produces, and that nothing anywhere in the application — old or new — can mutate fixture source data.

**HARD BLOCKER — read before starting.** This story's AC #1 requires comparing *"viewer API/browser payloads"* against the contract. As of this story's creation:
- **Story 1.7 (`ready-for-dev`, not `done`):** `frontend/src/features/scenario-data/`, `frontend/src/routes/ScenarioData.tsx`, `frontend/src/api/scenarioProjection.ts`, `frontend/src/hooks/useScenarioProjection.ts` do not exist on disk. Verified directly: `frontend/src/routes/ScenarioWorkspace.tsx` still renders the Story-1.3-era placeholder — *"Scenario Data will be available in this workspace."* — with no group tabs, no tables.
- **Story 1.8 (`ready-for-dev`, not `done`):** sorting/filtering/column-chooser/copy controls this story's mutation audit must inspect (Story 1.8's own words: *"Story 1.9 (mutation-denial audit must see the filter/sort/chooser/copy controls and confirm none of them mutate)"*) do not exist either.
- **Story 1.6 (`ready-for-dev`, not `done`):** the design tokens/primitives 1.7/1.8 build on.
- The backend half (contract fixture, API-level parity, legacy-route/OpenAPI mutation audit) has **no such blocker** — Stories 1.1, 1.4, and 1.5 are `done`, and the read endpoints this story audits already exist and are already exercised in `backend/tests/test_postgres_integration.py`.

**Sequencing guidance, not a gate this story enforces itself:** build and land the backend half (Tasks 1–3) now — it is fully self-contained and testable today. Do **not** attempt Task 4 (frontend parity) or the frontend half of Task 5 (mutation-path audit over Story 1.7/1.8's controls) until Story 1.7 and Story 1.8 are actually `done`; there is nothing on disk yet for those tasks to point at. If you are asked to execute this whole story before 1.7/1.8 land, stop and flag it rather than fabricating assertions against components that don't exist — see the Open Questions note at the end of Dev Notes.

**Depends on:**
- **Story 1.4 (done)** — `ScenarioProjectionV1` and its normalizers (`_horizon`, `_normalize_tasks`, `_normalize_workers`, `_normalize_demand`, `_normalize_constraints` in `backend/adapters/postgres/scenario_projection.py`) are the authoritative reference this story compares everything else against.
- **Story 1.5 (done)** — not directly exercised here; its exact-target resolvers are Story 2.8's consumer.
- **Story 1.7 — hard blocker for Task 4 and the frontend half of Task 5** (see above).
- **Story 1.8 — hard blocker for the frontend half of Task 5**, since sort/filter/chooser/copy controls are what the mutation audit inspects (Story 1.8, line 27, its own stated "Unblocks").
- **Story 1.1 (done)** — the Gate A cutover mechanism (`backend/scripts/gate_a_cutover.py`, the `refuse_legacy_routes_during_gate_a` middleware in `backend/api/main.py`) this story's legacy-route audit extends.

**Unblocks:** Story 1.10 (accessibility proof assumes the same rendered surface this story already proved matches the contract), Story 1.11 (Gate A readiness rolls up this story's pass/fail into `evidence/story-1.11/gate-a-readiness-report.json`).

**Scope boundary — read this before writing tests.** *"The comparison runs against the contract fixture alone, so AgentRuntime and agent capabilities are not required for this story"* (epics.md AC #1). Nothing in Epic 2 exists yet (Story 2.1 introduces `AgentRuntime`). This story never imports, mocks, or references any agent/chat module — it proves the viewer matches the *contract*, not that the future agent-inspection tool matches the viewer (that cross-check is Story 2.7's job, over evidence grounding).

## Acceptance Criteria

1. **Given** every Gate A fixture, **when** viewer API/browser payloads are compared against the shared `ScenarioProjectionV1` contract fixture, **then** all agent-relevant normalized values and stable identifiers match exactly, **and** the comparison runs against the contract fixture alone, so `AgentRuntime` and agent capabilities are not required for this story, **and** any mismatch blocks Gate A. *(FR24, NFR29)*

2. **Given** the supported browser and API surfaces, **when** mutation-path tests attempt upload, create, import, edit, delete, or source-data modification, **then** no control, route, command handler, endpoint, or agent capability supports the mutation, **and** any discovered path blocks Gate A. *(FR22, FR24)*

## Tasks / Subtasks

- [x] Task 1: Establish the canonical Gate A contract fixture (AC: #1)
  - [x] Both Gate A predefined fixtures are `data/sample_tiny_input.json` (10 workers) and `data/sample_tiny_input_more_tm.json` (22 workers) — confirmed as the complete set in `backend/scripts/gate_a_cutover.py:default_fixtures()`. There is no third fixture. Every test in this story is parametrized over exactly these two, matching the existing precedent in `backend/tests/test_scenario_projection.py::test_gate_a_fixtures_normalize_to_exact_group_counts` and `backend/tests/test_postgres_integration.py::test_projection_api_is_complete_windowed_empty_group_safe_and_site_isolated`.
  - [x] New script `backend/scripts/export_contract_fixture.py`: for each Gate A fixture, load the raw JSON, run it through the **existing, already-tested** normalizers (`_horizon`, `_normalize_tasks`, `_normalize_workers`, `_normalize_demand`, `_normalize_constraints` — do not reimplement or fork them), and serialize the full ordered result (every `TaskV1`/`WorkerV1`/`DemandIntervalV1`/`ConstraintV1`, plus the derived `ScenarioOverviewV1` counts) to a deterministic JSON file via `dataclasses.asdict`. Write output to `data/contract/<fixture_id>.projection-v1.json` (new `data/contract/` directory — two files: `sample_tiny_input.projection-v1.json`, `sample_tiny_input_more_tm.projection-v1.json`).
  - [x] **This generator is deliberately not an independent oracle for correctness** — it calls the same normalizers Story 1.4/1.5 already unit-tested with hardcoded literal assertions (e.g. `first_task.record_id == "1E5596F1-C9AD-43F1-8DC4-7CF8013C9D0B"`). That is fine: this story's job is *cross-surface* parity (does the live API return what the frontend renders, and do both match the one normalized source?), not re-proving normalization correctness a second time. Say so in completion notes so a reviewer doesn't mistake it for a weaker test than it is.
  - [x] Commit the two generated JSON files to the repo (they are fixtures, not build output — same convention as `evidence/story-1.4/nfr35-scenario-data-load.json` being a committed, hand-inspectable artifact). Add a `make`/`uv run` invocation comment at the top of the script so a future fixture change (Story 1.1's governed import path only) has a documented regeneration step.
  - [x] `baseline-assignments` and `locks` are permanently empty for both Gate A fixtures per Story 1.4 — the contract fixture's arrays for those two groups are `[]`, and the parity tests below must not treat that as a failure.

- [x] Task 2: Backend API parity — every record, every group, both fixtures (AC: #1)
  - [x] Extend `backend/tests/test_postgres_integration.py` (new `@pytest.mark.postgres` test, sibling to `test_projection_api_is_complete_windowed_empty_group_safe_and_site_isolated`): reuse its exact setup shape (`PostgresFixtureHistoryAdapter.import_fixture`, `_catalogue_client`, `SESSION_COOKIE_NAME` cookie header) to import both Gate A fixtures under one seeded site, then **page through every group to completion** (the existing test already proves this loop is safe/deterministic for `demand`) and assert the **full record** — every field, not just `record_id` — of every returned item equals the corresponding entry in this story's `data/contract/<fixture_id>.projection-v1.json` (Task 1), in the same order. Cover all six list groups (`work-areas-and-tasks`, `workers`, `demand`, `baseline-assignments`, `locks`, `constraints-and-objectives`) plus the `Overview` group's counts.
  - [x] This is a **stricter version** of the existing `test_gate_a_fixtures_normalize_to_exact_group_counts` (which only spot-checks specific indices/fields) and the existing `test_projection_api_is_complete_windowed_empty_group_safe_and_site_isolated` (which checks counts and `record_id` uniqueness/order but not full-field equality) — do not delete or weaken either; this task adds the missing full-equality assertion on top of them.
  - [x] Skip cleanly without a live Postgres, exactly like every other `@pytest.mark.postgres` test in this repo (the marker itself + `governed_postgres_engine`'s existing skip behavior handles this — do not add a second skip mechanism).

- [x] Task 3: Backend mutation-path and legacy-route audit (AC: #2)
  - [x] **OpenAPI method-surface check** (new test, e.g. in `backend/tests/test_scenario_projection.py` or a new `backend/tests/test_gate_a_mutation_audit.py`): call `app.openapi()` and assert that every path whose prefix is `/api/v1/scenarios` (the Gate A catalogue + projection surface introduced by Stories 1.2–1.5) exposes **only** the `get` method — no `post`, `put`, `patch`, or `delete` key present on any such path's operations dict. This is a structural, self-updating check: it fails the moment anyone adds a mutating operation to this router group, without needing to enumerate every current endpoint by name.
  - [x] **Legacy-route regression** (extend `backend/tests/test_gate_a_cutover.py`, which already proves `/scenarios`, `/runs`, `/constraints` return 503 once `ROSTERAI_MAINTENANCE_FLAG` points at an existing path): add an assertion that this refusal covers **every** HTTP method on those prefixes, not just the ones the existing tests happen to call (`GET /scenarios`, `POST /scenarios`, `GET /runs/{id}`) — parametrize over `GET`/`POST`/`PUT`/`PATCH`/`DELETE` for at least one path per legacy prefix and assert 503 in every case once the flag is set.
  - [x] **Revised decision — do NOT assert against the shared dev/test sandbox's real ambient state, and do NOT run the actual Gate A cutover to make such an assertion pass.** An earlier draft of this task asked for a test against unmocked `default_settings()` proving `_gate_a_flag_is_set()` is `True`. That is wrong for *this* sandbox and must not be implemented as written: `test_api.py`, `test_scenarios_api.py`, `test_constraints_api.py`, `test_insights_api.py` (61 tests) exercise the legacy routers via `TestClient(app)` with **no override** of `maintenance_flag_path` — verified directly, they only override `get_engine`/`get_llm_provider`. They depend on `var/gate-a-maintenance` **not existing**. Running the real cutover (or otherwise creating that file) to satisfy an "is the flag set" assertion here would pass this story's check by breaking all 61 of those tests — an unacceptable trade, and not what AC #2 is asking for. **Do not run `gate_a_cutover.py` against this repo checkout as part of this story.**
  - [x] **What this task actually owns:** prove the *mechanism* is correct — that once the flag exists, every method on every legacy prefix is refused (the parametrized extension in the bullet above), using the existing **isolated** `tmp_path`/`replace(default_settings(), ...)` pattern (`_catalogue_client`, `test_cutover_drains_workers_snapshots_sqlite_and_imports_fixtures`) that never touches the shared sandbox's real `var/` state. That is a complete, sandbox-safe proof of AC #2's mechanism.
  - [x] **What this task does NOT own:** confirming the flag is actually set in whatever environment is used to certify a real Gate A release. That is an operational/deployment fact, not a pytest assertion inside a shared checkout that other tests deliberately keep pre-cutover — it belongs to Story 1.11's Gate A readiness process (a runbook/deploy-gate check reading the real production/staging settings, immediately before Story 1.11 writes `gate-a-readiness-report.json`), or to CI pipeline configuration for whatever environment is treated as canonical for the release decision. Record this scope boundary explicitly in Task 6's evidence file rather than leaving it implicit.
  - [x] **Static SQL-verb scan** (new test): grep/AST-scan `backend/adapters/postgres/scenario_projection.py` and `backend/adapters/postgres/scenario_catalogue.py` for the substrings `INSERT`, `UPDATE`, `DELETE` (case-insensitive) in any SQL string literal — assert none are present. This catches a future "helper" write path added to a reader module without going through the governed import in `backend/adapters/postgres/fixture_history.py`, which is the only place those verbs may legitimately appear against `scenario_version`/fixture tables.
  - [x] `GET /fixtures` (legacy, `backend/api/routers/fixtures.py`) is out of the `_LEGACY_ROUTE_PREFIXES` block by design (confirmed: it stays 200 during maintenance per the existing `test_api_refuses_legacy_reads_when_cutover_flag_exists`) — it only lists filenames, has no mutating verb, and is not in scope for this audit's *findings*, but note its exemption explicitly in completion notes so a future reader doesn't assume it was missed.

- [x] Task 4: Frontend viewer parity — do not start until Story 1.7 AND Story 1.8 are `done` (AC: #1)
  - [x] For each Gate A fixture and each of the seven Scenario Data groups (Overview + six list panels), mock the relevant `useScenarioProjection` hook (mock at the **hook boundary**, per this repo's established convention — `vi.mock("@/hooks/useScenarioProjection")`, not `openapi-fetch`/`client.ts`) to return the exact contents of this story's `data/contract/<fixture_id>.projection-v1.json` (Task 1), paginated exactly as Story 1.8's controls would page it.
  - [x] Render each panel (through `ScenarioDataView` so URL-driven group/page/sort/filter state is exercised too, not the panel in isolation) and assert **every rendered cell's text**, across **every page** of every group, equals the corresponding field in the contract fixture — including stable identifiers (`task_id`, `contact_id`, `record_id`, `area_id`, etc., which must render exactly, not truncated or reformatted).
  - [x] Do this for both Gate A fixtures. This is the "browser payloads" half of AC #1; Task 2 is the "API payloads" half. Both must pass against the same `data/contract/` artifacts — that shared source is what makes this a *parity* proof rather than two independent correctness proofs.

- [x] Task 5: Frontend mutation-path audit and legacy-component cleanup — Story 1.7/1.8-dependent portion cannot start until they are `done` (AC: #2)
  - [x] **Structural no-mutation-affordance check**, extending the pattern Story 1.7 Task 6 already established for AC #3 (its static import-check test): assert no file under `frontend/src/features/scenario-data/`, `frontend/src/routes/ScenarioData.tsx`, or any Scenario-Data panel renders an `<input>`, editable `<select>` (other than Story 1.8's read-oriented filter/sort controls, which must be proven to never fire a mutating request — see next bullet), checkbox, `contentEditable`, drag handle, or a button whose accessible name implies create/upload/import/edit/delete. Extend rather than duplicate Story 1.7's existing static-import-check machinery.
  - [x] **Every exported function in `frontend/src/api/scenarioProjection.ts` and `frontend/src/api/scenarioCatalogue.ts` issues only `client.GET(...)`** — a static test (grep-based, mirroring Task 3's backend SQL-verb scan) asserting no `client.POST`/`PUT`/`PATCH`/`DELETE` call exists in either file.
  - [x] **Orphaned legacy component sweep — this story is where `deferred-work.md` explicitly assigns it** (*"Deferred from: story-1-3-choose-an-immutable-fixture… Story 1.9's mutation-path audit and a later cleanup should verify and remove this inventory without re-mounting it"*). Verify `frontend/src/components/{editor,runs,results,scenarios}/**` and their hooks (`useApplyConstraint`, `useCreateScenario`, `useFixtures`, `useOverrides`, `useRun`, `useRunInsights`, `useRunResult`, `useRuns`, `useScenario`, `useScenarios`, `useTriggerRun`) — plus the three modules deferred-work.md flags as *transitively* orphaned outside those directories (`frontend/src/components/layout/ErrorBanner.tsx`, `frontend/src/lib/runStatus.ts`, `frontend/src/lib/formatShiftWindow.ts`'s legacy consumers) — are unreachable from the live route tree (`frontend/src/App.tsx`). Some of these modules (e.g. `useApplyConstraint`, `useCreateScenario`) are themselves mutation UI (constraint editing, scenario creation) — their unreachability *is* part of this story's mutation-denial proof, not incidental cleanup. **Check importers before removing** `ErrorBanner.tsx` specifically — deferred-work.md warns it sits beside live components (`AppBar`, `RootErrorBoundary`) in `components/layout/` and must not be swept by directory alone.
  - [x] Delete the confirmed-orphaned tree once proven unreachable (a static reachability test first, then the deletion, in that order, so the test fails loudly if anything still imports it) — do not merely leave it and note it as "still there" a second time; deferred-work.md already deferred it once.
  - [x] The **backend legacy router mount** (`backend/api/main.py:257-261` — `fixtures.router`, `scenarios.router`, `runs.router`, `constraints.router`) is a separate concern from the frontend component tree and is covered by Task 3, not this task.

- [x] Task 6: Record Gate A evidence for this story (AC: #1, #2)
  - [x] Following the `evidence/story-1.4/`, `evidence/story-1.5/` convention (NFR27 — *"every evaluation report binds dataset, evaluator, model, prompt, tool, policy, application, scenario, solver, code, and image versions"*, applied here to a parity/mutation report rather than a latency one), write `evidence/story-1.9/gate-a-viewer-parity-and-mutation-denial.json` recording: the two Gate A fixture identities/versions, the pass/fail result of Task 2 (API parity), Task 4 (browser parity, once unblocked), Task 3 and Task 5 (mutation audits), the measurement/test date, and the code commit under test. This is the contributing result Story 1.11's `gate-a-readiness-report.json` will bind to for this story.
  - [x] If Task 4/the frontend half of Task 5 could not run because Story 1.7/1.8 were not yet `done`, the evidence file must say so explicitly (`"frontend_parity": "blocked — Story 1.7/1.8 not done as of <date>"`) rather than omitting the field or reporting a false pass.
  - [x] Record the Task 3 scope boundary explicitly, e.g. `"legacy_route_mechanism": "proven (isolated settings)"` and `"legacy_route_live_flag_state": "not verified by this story — operational fact, owned by Story 1.11 / release runbook"`. Do not report the legacy-route finding as a bare "pass" — the mechanism and the live-environment fact are two different claims and this story only proves one of them.

- [x] Task 7: Full regression gate
  - [x] `uv run --frozen pytest` and `uv run --frozen pytest -m postgres` (from `backend/`) — the postgres-marked suite requires a live local PostgreSQL (see existing `governed_postgres_engine` conftest fixture); `alembic check` must show zero diff (this story adds no migration).
  - [x] If Task 4/5's frontend portion was completed: `npm run typecheck`, `npm run lint`, `npm run build`, `npm test` (from `frontend/`).
  - [x] Report backend and frontend test counts before and after, and explicitly state in completion notes which tasks ran versus which were blocked on Story 1.7/1.8.

## Dev Notes

- **Nothing here is new product surface.** This story adds test code, one small export script, two committed JSON fixtures, and (pending Story 1.7/1.8) deletion of already-dead code. If you find yourself building a new component or route, stop — that belongs to a different story.
- **The two Gate A fixtures, by name, are the entire scope.** `sample_tiny_input.json` (10 workers) and `sample_tiny_input_more_tm.json` (22 workers), both `version: "v1"` — confirmed in `backend/scripts/gate_a_cutover.py::default_fixtures()` and reused identically in `test_scenario_projection.py` and `test_postgres_integration.py`. Known exact values from existing tests, reusable as spot-check anchors: `work_area_count=3`, `task_count=6`, `demand_interval_count=1_547`, `constraint_count=14`, `baseline_assignment_count=0`, `lock_count=0` for **both** fixtures (only `worker_count` differs, 10 vs 22).
- **"Contract fixture" is this story's own artifact, not a pre-existing one.** Neither `epics.md`, `ARCHITECTURE-SPINE.md`, nor `EXPERIENCE.md`/`DESIGN.md` names a literal `data/contract/` directory or export script — Task 1's design (generate a committed JSON snapshot of the normalizer output, shared by backend and frontend tests) is authored here to make AC #1's "shared… contract fixture" concrete and testable. Flag this in completion notes for reviewer confirmation, same posture Story 1.8 took with its invented column-chooser explanation copy.
- **The legacy mutation-path gap — decided, see Task 3 (revised after a real dev run caught the first version's flaw).** `POST /scenarios`, `POST /constraints`, `POST /runs` are live routes in `backend/api/main.py` today, and their `refuse_legacy_routes_during_gate_a` middleware guard only activates once `ROSTERAI_MAINTENANCE_FLAG` points at an existing path — an operator action documented in `gate_a_cutover.py`'s docstring. **Deleting these routers is explicitly out of scope for this story**: AD-25/AR25 require them to remain as offline legacy demo data (a deliberate one-way-cutover design, not an oversight), and 61 tests across `test_api.py`/`test_scenarios_api.py`/`test_constraints_api.py`/`test_insights_api.py` still depend on them existing and depend on the ambient flag **not** being set.
- **Do not run the real Gate A cutover against this repo checkout, and do not add a test that requires it to have been run.** An earlier version of this task asked for an assertion against unmocked `default_settings()`. That is wrong: it conflates "is the block *mechanism* correct" (answerable safely inside this sandbox, via isolated `tmp_path` settings — already done) with "has cutover actually been performed against the environment being certified for release" (an operational fact that belongs to Story 1.11's Gate A readiness process, not to a pytest assertion that would otherwise force someone to either fabricate the flag locally — breaking the 61 legacy tests — or leave the assertion permanently red for the wrong reason). If a dev agent is ever asked to "just run the cutover to make the test pass," that is a signal the assertion is targeting the wrong environment — stop and revisit this note rather than proceeding.
- **`GET /fixtures` is deliberately out of the legacy block** (`_LEGACY_ROUTE_PREFIXES = ("/scenarios", "/runs", "/constraints")` does not include it) and stays 200 during Gate A maintenance per the existing `test_api_refuses_legacy_reads_when_cutover_flag_exists`. It is read-only (lists filenames) and out of scope for this story's findings — noted so it isn't mistaken for a missed audit gap.
- **Story 1.9's own name appears twice already in the codebase before this story exists:** `deferred-work.md`'s Story 1.3 entry explicitly assigns the orphaned-legacy-component sweep to "Story 1.9's mutation-path audit," and Story 1.8's Dev Notes name Story 1.9 as the consumer proving its new controls don't mutate. Both are folded into Task 5 above — this is not new scope invented by this story, it is scope other stories already deferred to it by name.
- **Test conventions to follow, unchanged from prior stories:** backend — pytest, `uv run --frozen pytest` from `backend/`, `@pytest.mark.postgres` only for genuinely live-database tests (they must skip cleanly without one). Frontend — Vitest + React Testing Library, co-located `*.test.tsx`/`*.test.ts`, mock at the **hook** boundary, never at `openapi-fetch`/`client.ts` directly.
- **jsdom does not evaluate Tailwind classes** (repeated caveat from Story 1.3/1.8's reviews) — Task 4's parity assertions must be on rendered text/DOM structure, not class-name presence.
- **Open questions for the reviewer (do not block Task 1–3, 6–7 on these):**
  1. Is `data/contract/` (Task 1) an acceptable new top-level data directory, or should the generated contract fixture live under `backend/tests/fixtures/` (backend-only) with the frontend instead re-deriving its own expected values independently? The story as written picks `data/contract/` specifically so both stacks share one file and cannot drift from each other by construction — flag if this placement conflicts with a convention not visible in the docs reviewed for this story.
  2. Given the hard blocker on Story 1.7/1.8, should this story be implemented in two commits (backend now, frontend once unblocked) rather than one? Task 7 already treats them as separable gates; explicit sign-off on splitting the story's completion into two dated passes (matching Task 6's "blocked" evidence field) may be worth a product decision rather than an assumption.

### Project Structure Notes

- **Backend, new:** `backend/scripts/export_contract_fixture.py`; `data/contract/sample_tiny_input.projection-v1.json`, `data/contract/sample_tiny_input_more_tm.projection-v1.json`; `evidence/story-1.9/gate-a-viewer-parity-and-mutation-denial.json`; a new mutation-audit test file (or extension of an existing one — see Task 3).
- **Backend, modified:** `backend/tests/test_postgres_integration.py` (new full-parity test), `backend/tests/test_gate_a_cutover.py` (parametrized method coverage for the legacy-route refusal).
- **Backend, untouched:** every production module — this story is test/evidence-only on the backend side. No migration, no route, no port change.
- **Frontend, new (blocked on Story 1.7/1.8):** parity tests over `ScenarioDataView`/panels (Task 4), a static grep-based no-mutation-verb test for `scenarioProjection.ts`/`scenarioCatalogue.ts` (Task 5).
- **Frontend, deleted (blocked on Story 1.7/1.8's landing, but not blocked on their content — the deletion targets pre-existing dead code, not anything 1.7/1.8 add):** `frontend/src/components/{editor,runs,results,scenarios}/**` and the hooks/shared modules named in Task 5, once a reachability test proves them unreachable. **This deletion is not actually gated on Story 1.7/1.8** — it can be done as soon as Task 5's static reachability check is written, independent of whether the new Scenario Data UI exists yet. Consider doing it alongside the backend half (Tasks 1–3) rather than waiting.
- Placement follows the same `backend/tests/`, `evidence/story-N/`, `data/` conventions every prior story in this epic already used — no new top-level convention beyond the new `data/contract/` subdirectory (see Open Question #2).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.9, lines 522-539] — story statement and both acceptance criteria, verbatim
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.8, lines 504-520, and its own story file's line 27] — "Unblocks: Story 1.9 (mutation-denial audit must see the filter/sort/chooser/copy controls and confirm none of them mutate)"
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.11, lines 559-575] — Gate A readiness rollup this story's evidence feeds; `evidence/story-1.11/gate-a-readiness-report.json` binds each contributing story's pass/fail
- [Source: _bmad-output/planning-artifacts/requirements-inventory.md, lines 50, 56-64] — NFR29 ("any regression in… viewer parity… blocks release regardless of aggregate helpfulness") and NFR35's measurement-protocol precedent this story's evidence file follows in spirit
- [Source: _bmad-output/planning-artifacts/prds/prd-ShiftMind-2026-07-21/reconcile-scenario-data-viewer.md] — "Read-only viewer… with a negative mutation-path acceptance test" and "Gate A… viewer and its tests to pass before AgentRuntime or tool orchestration begins"
- [Source: _bmad-output/implementation-artifacts/deferred-work.md, "Deferred from: story-1-3-choose-an-immutable-fixture (2026-07-27)"] — the orphaned legacy component inventory explicitly assigned to this story's mutation-path audit
- [Source: _bmad-output/implementation-artifacts/1-7-open-the-read-only-scenario-data-workspace.md] — the exact files/routes/hooks this story's frontend parity and mutation audit target once done (`ScenarioData.tsx`, `ScenarioDataView.tsx`, seven group panels, `scenarioProjection.ts`, `useScenarioProjection.ts`); its own Task 6 established the static-import-check pattern this story's Task 5 extends
- [Source: _bmad-output/implementation-artifacts/1-8-control-scenario-data-tables.md] — confirms Story 1.7/1.8 are both `ready-for-dev` as of this story's creation and names this story as their mutation-audit consumer
- [Source: backend/scripts/gate_a_cutover.py, `default_fixtures()`] — the exact two Gate A fixtures (`sample_tiny_input.json`, `sample_tiny_input_more_tm.json`, both `v1`) and the `_enable_maintenance`/maintenance-flag operational contract
- [Source: backend/api/main.py, lines 127-150] — `_LEGACY_ROUTE_PREFIXES`, `_gate_a_flag_is_set()`, and the `refuse_legacy_routes_during_gate_a` middleware this story's Task 3 audits and extends
- [Source: backend/api/routers/scenarios.py, constraints.py, runs.py, fixtures.py] — confirms live mutating verbs (`POST /scenarios`, `POST /constraints`, `POST /scenarios/{id}/runs`) exist today behind the flag-gated middleware, and that `fixtures.py` is GET-only and outside the legacy-block prefix list
- [Source: backend/tests/test_gate_a_cutover.py] — existing legacy-route-refusal test coverage (`test_api_refuses_mutating_requests_when_cutover_flag_exists`, `test_api_refuses_legacy_reads_when_cutover_flag_exists`) this story's Task 3 extends rather than duplicates
- [Source: backend/tests/test_scenario_projection.py, lines 209-237] — `test_gate_a_fixtures_normalize_to_exact_group_counts`, the existing spot-check parity precedent this story's Task 1/2 generalize into full-field, all-groups, all-records parity
- [Source: backend/tests/test_postgres_integration.py, lines 352-508] — `test_projection_api_is_complete_windowed_empty_group_safe_and_site_isolated`, the exact client/session/pagination-loop pattern Task 2 extends; confirms full-page iteration over `demand` (1,547 rows) is already a proven-safe pattern in this repo
- [Source: backend/application/contracts/scenario_projection.py] — the frozen `ScenarioProjectionV1` dataclasses (`TaskV1`, `WorkerV1`, `DemandIntervalV1`, `AssignmentV1`, `LockV1`, `ConstraintV1`, `ScenarioOverviewV1`) Task 1's export script serializes
- [Source: evidence/story-1.4/nfr35-scenario-data-load.json, evidence/story-1.5/nfr35-evidence-target-resolution.json] — the committed evidence-artifact convention (dated record, fixture identity, environment, measured/observed values, pass/fail, code version) this story's Task 6 follows for a parity/mutation report instead of a latency one
- [Source: frontend/src/routes/ScenarioWorkspace.tsx, lines 151-161] — verified current placeholder state confirming Story 1.7 has not landed as of this story's creation

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Implementation Plan

- Reconcile the pre-Story-1.6/1.7/1.8 assumptions against the landed Scenario Data route, hook, controls, and tests before implementing the proof.
- Generate one deterministic shared contract snapshot from the production normalizers, then prove backend and browser parity against that same artifact.
- Add structural mutation-denial audits, prove legacy-route refusal, remove only confirmed unreachable legacy frontend code, and publish Gate A evidence after full backend/frontend validation.

### Debug Log References

- RED (Task 1): `test_export_contract_fixture.py` failed collection because the exporter did not exist.
- GREEN (Task 1): exporter tests 3 passed; backend regression 330 passed, 6 deselected.
- GREEN (Task 2): live PostgreSQL parity test passed; backend regression 331 passed, 6 deselected.
- SUPERSEDED (Task 3): The unmocked shared-sandbox flag assertion exposed a specification error and was removed by product decision; live cutover state belongs to Story 1.11.
- GREEN (Task 3): mutation audit 21 passed; backend regression 348 passed, 6 deselected.
- RED (Task 4): overview parity initially omitted row-header text from its DOM extraction; the full-suite run also exposed the need for a concurrency-safe timeout on the exhaustive 1,547-row page walk.
- GREEN (Task 4): 14 exhaustive viewer-parity cases passed; frontend regression 78 files, 381 tests.
- RED (Task 5): structural scan initially included a test-contract helper, and the deletion guard failed while the proven-orphaned tree still existed.
- GREEN (Task 5): reachability/mutation guards 5 passed; typecheck and lint passed; frontend regression after legacy cleanup is 50 files, 220 tests.
- RED (Task 6): evidence contract test failed because the Story 1.9 report did not yet exist.
- GREEN (Task 6): evidence contract 3 focused tests passed; backend regression 349 passed, 6 deselected.
- GREEN (Task 7): frozen backend 349 passed/6 deselected; explicit PostgreSQL 27 passed/328 deselected; Alembic reported no new upgrade operations; frontend typecheck/lint/build and 220 tests passed.

### Completion Notes List

- Task 1: Added deterministic snapshots for exactly the two Gate A fixtures. The generator intentionally reuses Story 1.4's already-literal-tested production normalizers; it is the shared cross-surface parity source, not an independent normalization oracle.
- Task 2: Added live-PostgreSQL full-record equality across both fixtures, all six paged groups, and every contract overview field; backend regression is 331 passed, 6 deselected.
- Task 3: The governed `/api/v1/scenarios` OpenAPI surface is GET-only; all five audited HTTP methods are refused on each legacy prefix under isolated maintenance settings; reader SQL literals contain no INSERT/UPDATE/DELETE. `GET /fixtures` remains deliberately exempt because it only lists filenames. Per product decision, Story 1.11 owns verification of the live release flag state.
- Task 4: Proved both Gate A fixtures through the actual `ScenarioDataView`, including overview and every rendered cell across every 50-record page of all six list groups.
- Task 5: Proved Scenario Data has no mutation affordance or mutating API verb, then deleted the unreachable legacy UI and mutation hooks. Preserved `formatShiftWindow.ts` because Story 1.7/1.8 made `formatMinuteWindow` a live Scenario Data dependency.
- Task 6: Published version-bound Gate A evidence with contract SHA-256 digests and separate fields for the proven legacy-route mechanism versus the Story-1.11-owned live flag state.
- Task 7: All backend and frontend gates ran; none were blocked because Stories 1.7 and 1.8 were already done. Backend grew from 327 to 349 selected tests. Frontend grew from 367 to 381 tests before removing 161 proven-orphaned legacy tests, finishing with 220 live-surface tests.

### File List

- _bmad-output/implementation-artifacts/1-9-prove-viewer-parity-and-mutation-denial.md
- _bmad-output/implementation-artifacts/sprint-status.yaml
- backend/scripts/export_contract_fixture.py
- backend/tests/test_export_contract_fixture.py
- backend/tests/test_postgres_integration.py
- backend/tests/test_gate_a_cutover.py
- backend/tests/test_gate_a_mutation_audit.py
- frontend/src/features/scenario-data/ScenarioDataParity.test.tsx
- frontend/src/test/scenarioDataBoundaries.test.ts
- frontend/src/test/legacyReachability.test.ts
- evidence/story-1.9/gate-a-viewer-parity-and-mutation-denial.json
- data/contract/sample_tiny_input.projection-v1.json
- data/contract/sample_tiny_input_more_tm.projection-v1.json
- frontend/src/components/editor/ConstraintInput.test.tsx (deleted)
- frontend/src/components/editor/ConstraintInput.tsx (deleted)
- frontend/src/components/editor/ConstraintTranscript.test.tsx (deleted)
- frontend/src/components/editor/ConstraintTranscript.tsx (deleted)
- frontend/src/components/editor/OverridesList.test.tsx (deleted)
- frontend/src/components/editor/OverridesList.tsx (deleted)
- frontend/src/components/editor/ProviderDownBanner.tsx (deleted)
- frontend/src/components/editor/ScenarioHeader.test.tsx (deleted)
- frontend/src/components/editor/ScenarioHeader.tsx (deleted)
- frontend/src/components/editor/TranscriptEntry.test.tsx (deleted)
- frontend/src/components/editor/TranscriptEntry.tsx (deleted)
- frontend/src/components/layout/ErrorBanner.test.tsx (deleted)
- frontend/src/components/layout/ErrorBanner.tsx (deleted)
- frontend/src/components/results/CoverageByDayTable.test.tsx (deleted)
- frontend/src/components/results/CoverageByDayTable.tsx (deleted)
- frontend/src/components/results/CoverageSummary.test.tsx (deleted)
- frontend/src/components/results/CoverageSummary.tsx (deleted)
- frontend/src/components/results/DemandVsServedChart.test.tsx (deleted)
- frontend/src/components/results/DemandVsServedChart.tsx (deleted)
- frontend/src/components/results/InsightPanel.test.tsx (deleted)
- frontend/src/components/results/InsightPanel.tsx (deleted)
- frontend/src/components/results/ScheduleTable.test.tsx (deleted)
- frontend/src/components/results/ScheduleTable.tsx (deleted)
- frontend/src/components/results/WarningsBanner.test.tsx (deleted)
- frontend/src/components/results/WarningsBanner.tsx (deleted)
- frontend/src/components/runs/RunHistoryTable.test.tsx (deleted)
- frontend/src/components/runs/RunHistoryTable.tsx (deleted)
- frontend/src/components/runs/RunInFlightPanel.test.tsx (deleted)
- frontend/src/components/runs/RunInFlightPanel.tsx (deleted)
- frontend/src/components/runs/RunStatusLabel.test.tsx (deleted)
- frontend/src/components/runs/RunStatusLabel.tsx (deleted)
- frontend/src/components/runs/TriggerRunButton.test.tsx (deleted)
- frontend/src/components/runs/TriggerRunButton.tsx (deleted)
- frontend/src/components/scenarios/CreateScenarioDialog.test.tsx (deleted)
- frontend/src/components/scenarios/CreateScenarioDialog.tsx (deleted)
- frontend/src/components/scenarios/ScenarioTable.test.tsx (deleted)
- frontend/src/components/scenarios/ScenarioTable.tsx (deleted)
- frontend/src/hooks/useApplyConstraint.test.tsx (deleted)
- frontend/src/hooks/useApplyConstraint.ts (deleted)
- frontend/src/hooks/useCreateScenario.test.tsx (deleted)
- frontend/src/hooks/useCreateScenario.ts (deleted)
- frontend/src/hooks/useFixtures.test.tsx (deleted)
- frontend/src/hooks/useFixtures.ts (deleted)
- frontend/src/hooks/useOverrides.test.tsx (deleted)
- frontend/src/hooks/useOverrides.ts (deleted)
- frontend/src/hooks/useRun.test.tsx (deleted)
- frontend/src/hooks/useRun.ts (deleted)
- frontend/src/hooks/useRunInsights.test.tsx (deleted)
- frontend/src/hooks/useRunInsights.ts (deleted)
- frontend/src/hooks/useRunResult.test.tsx (deleted)
- frontend/src/hooks/useRunResult.ts (deleted)
- frontend/src/hooks/useRuns.test.tsx (deleted)
- frontend/src/hooks/useRuns.ts (deleted)
- frontend/src/hooks/useScenario.test.tsx (deleted)
- frontend/src/hooks/useScenario.ts (deleted)
- frontend/src/hooks/useScenarios.ts (deleted)
- frontend/src/hooks/useTriggerRun.test.tsx (deleted)
- frontend/src/hooks/useTriggerRun.ts (deleted)
- frontend/src/lib/runStatus.test.ts (deleted)
- frontend/src/lib/runStatus.ts (deleted)

## Change Log

- 2026-08-06: Added shared contract fixtures, exhaustive backend/browser parity proofs, backend/frontend mutation audits, isolated legacy-route mechanism proof, orphaned legacy UI cleanup, and version-bound Gate A evidence. Live cutover state was explicitly transferred to Story 1.11 by product decision.
