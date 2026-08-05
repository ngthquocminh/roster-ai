---
baseline_commit: 80ef64eb81a5ef8c121f1bf52a9354ac9c22970f
---

# Story 1.5: Resolve Exact Evidence Targets

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the scenario platform,
we want evidence locators resolved to exact records with distinct failure outcomes,
so that verification always lands on the cited fact or fails safely.

**[Technical Enabler] — no planner-visible outcome.** The evidence navigation UI that consumes this resolver is Story 2.8's acceptance boundary. This story is accepted entirely through exact-target resolution, out-of-window, missing, and unauthorized-case tests. **There is no frontend UI work in this story** beyond regenerating the generated OpenAPI client types — no route, no hook, no component, no "jump to evidence" control.

**Depends on:** Story 1.3 (done) — `_VERSION_ORDINAL`, the RFC 7807 problem-details middleware, the non-disclosing 404 convention. Story 1.4 (done) — the entire `ScenarioProjectionV1` read path this story extends: `backend/application/contracts/scenario_projection.py` (the `*V1` frozen dataclasses and their per-group `record_id` schemes), `backend/application/ports/scenario_projection.py` (`ScenarioProjectionReader` Protocol), `backend/adapters/postgres/scenario_projection.py` (`PostgresScenarioProjectionReader`, `_projection_row`, the `_normalize_*` functions, `_VERSION_ORDINAL`-based "latest version" resolution), `backend/api/routers/scenario_projection.py` (the seven GET-only endpoints and their field-by-field response mapping), `backend/api/deps.py`'s `get_projection_reader` seam. Story 1.4's Dev Notes explicitly deferred "a full `EvidenceRefV1` locator type or exact-target-outside-window resolution" to this story.
**Unblocks:** Story 2.8 ("Jump to Evidence and Return to the Claim" — the frontend evidence-navigation UI consumes this resolver's endpoints and `EvidenceRefV1` shape), Epic 2's grounding work generally (AR11 requires every agent-produced metric/claim to attach `EvidenceRefV1` locators resolved through this same contract), and any later epic that cites a scenario fact by locator instead of by live window.

## Acceptance Criteria

1. **Given** an exact-target evidence locator for an authorized record outside the current window, **when** the projection resolves it, **then** exact-target lookup reveals that record without retargeting, **and** the behavior is available to both the viewer and the future inspect capability. *(AR4, UX-DR24)*

2. **Given** a missing, unauthorized, or version-mismatched evidence locator, **when** the projection resolves it, **then** those outcomes are distinct, no similar row or current version is substituted, and unauthorized responses disclose no record existence or value, **and** the same contract is reusable by the future inspect capability. *(AR11, UX-DR20)*

3. **Given** the NFR35 measurement fixture and protocol used in Story 1.4, **when** an exact evidence target in the largest projection group is resolved, including the deepest out-of-window record, **then** every run resolves within 2 seconds, measured from request receipt to response completion, **and** the measured values are recorded as release evidence and a miss blocks implementation acceptance of this story. *(NFR35)*

## Tasks / Subtasks

- [ ] Task 1: Define the `EvidenceRefV1` contract type (AC: #1, #2)
  - [ ] New module `backend/application/contracts/evidence_ref.py`. AD-20's canonical cross-epic contract set lists `EvidenceRefV1` as its own peer contract alongside `ScenarioProjectionV1` — not a sub-shape of it — because Epic 2's grounding gate (AR11) and Epic 3/4's run/schedule evidence will import it from a neutral module, not from `scenario_projection.py`. **[Judgment call — flag this]:** the Structural Seed's normative shape for `EvidenceRefV1` is "snapshot ID/checksum, scenario version, producing/baseline run and schedule versions when applicable, group, record ID, optional field and minute interval." The "producing/baseline run and schedule versions" fields describe `RunSnapshotV1`/`ScheduleVersionV1` identity that does not exist until Epic 3 — no run or schedule concept exists anywhere in the codebase yet. Follow the exact precedent Story 1.4 set for `AssignmentV1`/`LockV1` (define the full normative field now, populate it as always-`None` until the owning epic lands, so the schema doesn't need a breaking change later): `producing_run_version: str | None` and `baseline_schedule_version: str | None`, both always `None` in this story. Treat `scenario_version_id` (already unique and immutable per Story 1.1/1.4) as satisfying the "snapshot ID" field for this story's scope — Epic 1 evidence lives directly in `scenario_version.payload`, not in a separate S3 `EvidenceSnapshot` aggregate (AD-12's `EvidenceSnapshot` is for larger run/schedule evidence, out of scope here).
  - [ ] Frozen dataclass:
    ```python
    @dataclass(frozen=True)
    class EvidenceRefV1:
        scenario_version_id: UUID
        checksum_algorithm: str
        checksum_schema_version: str
        checksum_digest: str
        producing_run_version: str | None
        baseline_schedule_version: str | None
        group: Literal[
            "work-areas-and-tasks", "workers", "demand",
            "baseline-assignments", "locks", "constraints-and-objectives",
        ]
        record_id: str
        field: str | None = None
        start_minute: int | None = None
        end_minute: int | None = None
    ```
    `group` reuses the exact six path-segment literals Story 1.4's router already uses (`"work-areas-and-tasks"`, `"workers"`, `"demand"`, `"baseline-assignments"`, `"locks"`, `"constraints-and-objectives"`) — no seventh value for `"overview"`, since the overview group has no per-record `record_id` concept to cite. No SQLAlchemy/FastAPI/Pydantic import (AD-1) — this file lives in `application/contracts/`.
  - [ ] Add one resolution-outcome dataclass per group (mirrors Story 1.4's non-generic `TaskPageV1`/`WorkerPageV1`/... style rather than fighting Python generics — Task 2 of Story 1.4 explicitly chose that convention): e.g. `TaskResolutionV1`, `WorkerResolutionV1`, `DemandIntervalResolutionV1`, `AssignmentResolutionV1`, `LockResolutionV1`, `ConstraintResolutionV1`, each shaped:
    ```python
    @dataclass(frozen=True)
    class TaskResolutionV1:
        outcome: Literal["resolved", "not_found", "version_mismatch"]
        scenario_id: UUID
        current_scenario_version_id: UUID
        item: TaskV1 | None  # populated only when outcome == "resolved"
    ```
    `current_scenario_version_id` is always the scenario's actual current governed version (from `_VERSION_ORDINAL`), even on `not_found`/`version_mismatch` — this is what lets a `version_mismatch` response name what changed without leaking anything about the cited record itself (AC #2's "distinct outcomes" applies to failure *class*, not to the *record's* existence/value). An **unauthorized or unknown `scenario_id`** does not produce one of these dataclasses at all — see Task 2's non-disclosure rule.

- [ ] Task 2: Port method + PostgreSQL adapter — exact-target resolution (AC: #1, #2, #3)
  - [ ] Extend the existing `ScenarioProjectionReader` Protocol (`backend/application/ports/scenario_projection.py`) — do not create a second reader Protocol; Story 1.4's Unblocks line for this story says evidence-target resolution "reuses this same read path." Add one method per non-overview group, e.g.:
    ```python
    def resolve_task(
        self, connection: Any, scenario_id: UUID, scenario_version_id: UUID, record_id: str
    ) -> TaskResolutionV1 | None: ...
    ```
    (and the five siblings for workers/demand/baseline-assignments/locks/constraints). Returning `None` means "unauthorized or unknown `scenario_id`" — identical in spirit to `get_overview`'s existing `None`-means-404 contract, so the router's non-disclosure handling is unchanged code, not new code.
  - [ ] `backend/adapters/postgres/scenario_projection.py` — implement the six `resolve_*` methods on `PostgresScenarioProjectionReader`. **This is the resolver's core new logic and the reason Story 1.4 deferred it:** `_projection_row` currently *always* resolves "latest version" via `_VERSION_ORDINAL` and has no way to target an older, specifically-named `scenario_version_id`. Add a way to fetch the row for **the scenario's current latest version** (reuse `_projection_row` unmodified — resolving "latest" is still correct, because AC #2's version-mismatch check compares the *caller's cited* `scenario_version_id` against *that* row's `scenario_version_id`, it does not need to fetch a historical version's payload). Do **not** add a "fetch an arbitrary named version's payload" code path — no historical scenario version is ever queried directly in this MVP (every fixture import today produces the one governed version; the mismatch case is provable by comparing IDs, not by resolving two different payloads).
  - [ ] Resolution algorithm per group (identical shape across all six — extract a shared private helper if that reads cleaner, e.g. `_resolve(items, requested_scenario_version_id, actual_scenario_version_id, record_id) -> tuple[outcome, item | None]`):
    1. `row = self._projection_row(connection, scenario_id)`; if `row is None` → return `None` (unauthorized/unknown scenario — non-disclosing).
    2. If `scenario_version_id != row.scenario_version_id` → outcome `"version_mismatch"`, `item=None`. **Do not** attempt to look up the record under the caller's cited (non-current) version — there is no per-version payload store to look it up in, and AC #2 explicitly forbids substituting a different version's data.
    3. Normalize the group's full tuple (reuse the exact same `_normalize_*` function Story 1.4 already built — e.g. `_normalize_tasks(payload)` — do not write a second normalization path) and search it by `record_id` (a linear scan over the already-in-memory tuple is fine at this fixture scale — the group is already fully materialized for every paginated read today, per Story 1.4's Task 2 YAGNI note on caching).
    4. Found → outcome `"resolved"`, `item=<the matching TaskV1/WorkerV1/...>`. Not found → outcome `"not_found"`, `item=None`.
  - [ ] **Distinct record_id schemes to search against — reuse Story 1.4's verbatim, do not reinvent:** raw `TaskID`/`ContactID` for tasks/workers, `f"outbound:{i}"` / `f"inbound:{i}:{k}"` / `f"indirect:{i}"` for demand, `f"constraint:{i}"` for constraints, and the empty tuples for baseline-assignments/locks (a resolve call against either group always returns `"not_found"` in this story — nothing to resolve into, same reason those pages are always empty per Story 1.4's Dev Notes).

- [ ] Task 3: Exact-target resolution endpoints (AC: #1, #2, #3)
  - [ ] Six new `GET` routes on the existing `backend/api/routers/scenario_projection.py` router (same `router`, same file — do not create a second router module), one per non-overview group, path pattern `GET /api/v1/scenarios/{scenario_id}/projection/{group}/{record_id}`, e.g. `GET /api/v1/scenarios/{scenario_id}/projection/work-areas-and-tasks/{record_id}`. Query parameter `scenario_version_id: UUID` (required — the cited/expected version carried by the `EvidenceRefV1` locator; there is no meaningful "resolve without knowing what you expected" call, and requiring it is what makes version-mismatch detectable at all). **GET only** — same FR22/mutation-denial rule as every other route under `/api/v1/scenarios/*/projection*`.
  - [ ] **Critical wiring gotcha found in `backend/api/main.py`'s `versioned_http_problem` handler (lines 66-95): every plain `HTTPException(status_code=404)` on any `/api/v1/*` path is mapped through one fixed lookup table to the single generic `code="resource_not_found"`, regardless of `exc.detail`.** Raising `HTTPException(404)` three different ways for `not_found` / `version_mismatch` / unauthorized will silently collapse to the *same* problem `code` and fail AC #2's "distinct outcomes" requirement — this is not a hypothetical edge case, it is exactly what the existing infrastructure does today. Resolve this deliberately: keep the plain `HTTPException(status_code=404)` path for the **unauthorized/unknown-`scenario_id`** case only (so it keeps the existing generic, non-disclosing shape — this is correct, not a bug, per AC #2's "unauthorized responses disclose no record existence or value"). For the two **authorized-but-distinguishable** failures (`not_found`, `version_mismatch`), call `api.problems.problem_response(status=404, code=..., title=..., detail=...)` directly from the endpoint and return that `JSONResponse` instead of raising — e.g. `code="evidence_not_found"` and `code="evidence_version_mismatch"`. This bypasses the generic handler's code-collapsing on the two paths that need to stay distinct while reusing it unchanged for the one path that must not disclose anything.
  - [ ] On `outcome == "resolved"`, return the item mapped through the *existing* per-group `_task_out`/`_worker_out`/... helper functions Story 1.4's router already defines — do not write new mapping functions, the wire shape of one resolved record is identical to one item inside today's paginated `items` list. **No new Pydantic response schemas are needed for the two failure outcomes.** Declare `response_model=TaskProjectionOut` (etc., the existing per-group `*Out`/`*ProjectionOut` schema) on each route as normal; when returning `problem_response(...)` for `not_found`/`version_mismatch`, that call already returns a `JSONResponse` instance — FastAPI passes a returned `Response` subclass straight through without applying `response_model` serialization to it, so no `*ResolutionOut` wrapper schema needs to exist at the API layer. The `*ResolutionV1` dataclasses from Task 1 stay internal to the port/adapter boundary only.
  - [ ] All six handlers **sync `def`, not `async def`** — same reason as every other handler in this router (`get_site_context` drives a synchronous SQLAlchemy engine). Extend the existing sync-handler assertion test to cover them.
  - [ ] Depend on `get_site_context` and `get_projection_reader` (unmodified) — no new dependency seam needed.
  - [ ] Regenerate contracts: `npm run codegen` from `frontend/`. No UI consumes the new endpoints in this story (Story 2.8 does) — regenerating only keeps `frontend/src/api/schema.d.ts` current for that later story, same rationale as Story 1.4 Task 3's codegen step.

- [ ] Task 4: NFR35 measurement and release evidence (AC: #3)
  - [ ] `evidence/story-1.5/nfr35-evidence-target-resolution.json`, following the exact JSON shape and field set Story 1.4 established in `evidence/story-1.4/nfr35-scenario-data-load.json` (fixture, environment, protocol, code_versions, measurements[], maximum_duration_ms, passed). Same fixture (`sample_tiny_input_more_tm.json`), same warm/cold and 3-consecutive-runs rule, same server-side request-receipt-to-response-completion clock boundary — this story does not get to loosen the protocol, per `requirements-inventory.md`'s NFR35 measurement protocol table.
  - [ ] **The twist AC #3 calls out: "including the deepest out-of-window record."** Measuring only a first-page/easy record would not prove exact-target resolution actually reaches outside the default cursor window — it would just prove the endpoint works, which Task 3's tests already cover. Pick the **`demand`** group (Story 1.4 measured it normalizing to ~1,547 intervals — by far the largest group and the one most likely to expose an accidental O(window) or O(pages-scanned) implementation instead of the intended single in-memory linear scan over the already-normalized tuple) and resolve its **last** `record_id` in normalized order (index 1546, far outside the default `limit=50` window) three consecutive times, alongside at least one shallow/first-page record for contrast. Record both in the evidence file.
  - [ ] A miss on any run blocks marking this story done, identical rule to Story 1.4 Task 4.

- [ ] Task 5: Tests
  - [ ] Backend — successful out-of-window resolution: resolve a `demand` record far outside the default window (e.g. index 1200+) and confirm it matches the same record fetched by paging to it — same fixture-backed cross-check pattern Story 1.4's Task 5 used for pagination correctness.
  - [ ] Backend — the three distinct failure outcomes are genuinely distinct, not conflated (`@pytest.mark.postgres` or fixture-backed unit test, whichever the existing `test_scenario_projection.py` pattern favors for this kind of check): (a) a syntactically valid but non-existent `record_id` under the correct `scenario_version_id` → `evidence_not_found`; (b) a valid `record_id` but a `scenario_version_id` that doesn't match the scenario's current version (use a random/garbage UUID — no second real version exists in the Gate A fixtures, so a fabricated UUID is sufficient to prove the mismatch path) → `evidence_version_mismatch`; (c) an unauthorized/unknown `scenario_id` (Site B session against a Site A scenario, or a random UUID) → the plain non-disclosing 404, byte-identical in shape to every other unauthorized 404 in this router, and the response body must not contain the `record_id`, `group`, or any hint the record does/doesn't exist.
  - [ ] Backend — non-disclosure: assert the unauthorized-case response body is identical regardless of whether the cited `record_id` would have resolved or not (resolve against both a real and a fake `record_id` under an unauthorized scenario and diff the two response bodies).
  - [ ] Backend — reusable contract shape: assert `EvidenceRefV1` and the six `*ResolutionV1` types import cleanly with no FastAPI/SQLAlchemy/Pydantic dependency (mirror however Story 1.4/1.3 proved domain purity, if such a test already exists — otherwise a direct import-and-inspect test is sufficient).
  - [ ] Backend — mutation denial: extend the existing `app.routes`/`app.openapi()` iteration (Story 1.3/1.4's pattern) to also assert none of the six new `/projection/{group}/{record_id}` paths expose POST/PUT/PATCH/DELETE.
  - [ ] Backend — sync-handler guard: extend the existing `inspect.iscoroutinefunction(...)` assertion to the six new handlers.
  - [ ] Backend — empty groups: resolving any `record_id` against `baseline-assignments` or `locks` always returns `evidence_not_found` (never `resolved`), consistent with those groups always being empty in this story.
  - [ ] Backend — no migration: `alembic check` reports zero drift (this story adds no table/column, same as Story 1.4).
  - [ ] Frontend — none required beyond confirming `npm run codegen` produces a clean diff and `npm run typecheck`/`npm run build` still pass with the new generated types present but unused.
  - [ ] Full regression before done: `uv run --frozen pytest` (backend, default `-m "not live"`), `alembic check`, `npm run typecheck`, `npm run lint`, `npm run build`.

## Dev Notes

- **What NOT to build.** No frontend work of any kind (route/hook/component/evidence-link UI) — that is Story 2.8's boundary. No historical-version payload storage or lookup — every fixture import today produces exactly one governed `scenario_version` per `scenario_id`, so version-mismatch is provable by comparing the cited `scenario_version_id` to the current one, not by fetching two different payloads. No `producing_run_version`/`baseline_schedule_version` population — those name Epic 3 concepts (`RunSnapshotV1`, `ScheduleVersionV1`) that don't exist yet; the fields exist on `EvidenceRefV1` now (full normative shape, AD-20) but are always `None` until the owning epic lands, exactly like Story 1.4 defined `AssignmentV1`/`LockV1` now and left them always-empty. No new caching layer — same YAGNI rationale as Story 1.4's Task 2 (the group is already fully materialized in Python for every paginated read; a resolve call is one more linear scan over data already in memory, not a new I/O path).
- **The version-pinning gap Story 1.4's review deferred is directly relevant, not incidental.** Story 1.4's `_projection_row` re-resolves "latest version" independently on every call with no cursor pinned to a `scenario_version_id` — flagged in that story's Review Findings as an accepted known limitation (fixture imports are rare/governed, so drift within one paginated browsing session is low-probability). This story's resolver is different in kind: it takes an explicit `scenario_version_id` **as input** and must compare it against "current," which is exactly the version-identity discipline that gap was missing. Do not silently repeat the gap here — the resolver's whole job is to *not* let a stale citation quietly reinterpret against a newer version, which is the literal AC #2 requirement.
- **Distinct failure outcomes (AC #2) — this is the story's central design constraint.** `evidence_not_found`, `evidence_version_mismatch`, and the unauthorized/non-disclosing 404 must never collapse into one shape. The router-level gotcha in `api/main.py`'s `versioned_http_problem` handler (documented in Task 3) is the concrete trap: it maps every `HTTPException(404)` to one fixed generic `code`, so two of the three outcomes must be built by calling `api.problems.problem_response(...)` directly rather than raising. The third (unauthorized) *should* keep using the generic path — that genericness is the correct non-disclosing behavior, not a bug to fix.
- **Non-disclosure precedent.** Mirror Story 1.3/1.4's rule exactly: an unauthorized or unknown `scenario_id` reveals nothing about whether the cited `record_id` exists, what group it's in, or what it would contain — same shape, same status, same body regardless of the answer. This is stronger than ordinary "record not found" semantics because the *scenario itself* is the thing being hidden, not just the record.
- **NFR35 protocol reuse, with the AC #3 twist.** Reuse Story 1.4's exact measurement method (fixture, warm/cold, 3-consecutive-runs-all-must-pass rule, server-side clock boundary) — see `requirements-inventory.md`'s NFR35 measurement protocol table and `evidence/story-1.4/nfr35-scenario-data-load.json` for the exact evidence-file shape to match. The one addition: measure the **deepest out-of-window record** in the **largest** group (`demand`, ~1,547 items per Story 1.4's measurement), not just a shallow one — this is the case that would expose an accidental linear-scan-through-pages implementation instead of an O(1)-lookup-into-an-already-normalized-tuple implementation.
- **Domain purity (AD-1) still applies.** `backend/application/contracts/evidence_ref.py` and the extended `backend/application/ports/scenario_projection.py` must not import SQLAlchemy, FastAPI, or Pydantic. All SQL/adapter code stays in `backend/adapters/postgres/scenario_projection.py`; all Pydantic response models stay in `backend/api/schemas.py`.
- **No migration.** Every field this story needs already exists in `scenario_version.payload` or is derived (`scenario_version_id`, checksum fields already on the row `_projection_row` fetches). No new table, column, or Alembic revision. `alembic check` must report zero drift.
- **Test conventions:** same as Story 1.3/1.4 — `backend/tests/test_*.py` (likely extending `backend/tests/test_scenario_projection.py`), `uv run --frozen pytest`; PostgreSQL-backed tests use `@pytest.mark.postgres` and the `governed_postgres_engine`/`fresh_postgres_database_url` fixtures in `backend/conftest.py`, which skip cleanly with no local PostgreSQL service.

### Project Structure Notes

- New file: `backend/application/contracts/evidence_ref.py` (`EvidenceRefV1` and the six `*ResolutionV1` dataclasses — a new peer module to `scenario_projection.py`, not appended to it, per AD-20's canonical contract set treating `EvidenceRefV1` as its own contract).
- Extended files (no new modules otherwise): `backend/application/ports/scenario_projection.py` (six new `resolve_*` Protocol methods), `backend/adapters/postgres/scenario_projection.py` (six new `resolve_*` implementations on `PostgresScenarioProjectionReader`), `backend/api/routers/scenario_projection.py` (six new `GET .../{group}/{record_id}` routes on the same `router`). `backend/api/schemas.py` needs **no new Pydantic models** — resolved items reuse the existing per-group `*Out`/`*ProjectionOut` schemas as `response_model`; failure outcomes return `problem_response(...)`'s `JSONResponse` directly (see Task 3).
- No change to `backend/api/deps.py` — `get_projection_reader`/`get_site_context` are reused unmodified.
- `backend/store/`, `backend/services/`, `backend/llm/`, and `frontend/src/components/{editor,runs,results,scenarios}/` remain frozen legacy (AD-25) — untouched by this story.
- No new frontend feature directory — only `frontend/src/api/schema.d.ts` and `frontend/openapi.json` (both generated) change.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.5: Resolve Exact Evidence Targets, lines 436-459] — story statement, planner-visible-outcome note, and the three acceptance criteria
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.4: Serve the Normalized Scenario Read Contract, lines 407-434] — the read contract this story extends; its Dev Notes explicitly deferred `EvidenceRefV1`/exact-target resolution here
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.7, lines 481-502 and Story 2.8, lines 767-793] — downstream consumers: the Scenario Data workspace (no direct dependency on this story) and the evidence-navigation UI (direct consumer of this story's endpoints and `EvidenceRefV1` shape)
- [Source: _bmad-output/planning-artifacts/epics.md#AR4, AR11, line 151, 158] — "exact-target lookup" (AR4) and "version-bound `EvidenceRefV1` locators... missing, unauthorized, and version-mismatched evidence are distinct failures and never retarget" (AR11)
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR18, UX-DR20, UX-DR24, lines 213, 217, 225] — evidence navigation locator fields; distinct exception states for version mismatch/missing/unauthorized/stale, non-disclosure; bounded pagination with exact-target loading
- [Source: _bmad-output/planning-artifacts/epics.md#NFR35, line 144] — allocation of exact evidence-target resolution ≤2s to this story
- [Source: _bmad-output/planning-artifacts/requirements-inventory.md#NFR35 measurement protocol, lines 56-71] — fixture, warm/cold, runs-and-rule, clock boundary, evidence format; explicit allocation "Story 1.5 (evidence-target resolution)"
- [Source: .../architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md#AD-4, lines 66-70] — "exact-target lookup so a deep-linked record can be revealed outside the current window"
- [Source: ARCHITECTURE-SPINE.md#AD-11, lines 150-154] — the normative definition of an evidence reference (scenario version, producing/baseline schedule/run version, group, record ID, optional field/time range) and the three-distinct-failures rule this story implements
- [Source: ARCHITECTURE-SPINE.md#AD-1, AD-13, AD-20, AD-26, lines 48-52, 162-166, 204-208, 240-244] — hexagonal module boundary; one public contract chain (RFC 7807); canonical contract set naming `EvidenceRefV1` as its own peer contract with its required-shape row; NFR35 allocated to the scenario read service (AD-4), not a new component
- [Source: ARCHITECTURE-SPINE.md#Structural Seed / Normative contract minimums, line 318] — `EvidenceRefV1` required shape: "snapshot ID/checksum, scenario version, producing/baseline run and schedule versions when applicable, group, record ID, optional field and minute interval"
- [Source: _bmad-output/implementation-artifacts/1-4-serve-the-normalized-scenario-read-contract.md] — the entire prior story: contract/port/adapter/router file paths and exact names, the per-group `record_id` schemes, the `_VERSION_ORDINAL`/`_projection_row` "latest version" resolution this story reuses without a historical-version fetch path, the non-generic `*PageV1` wrapper convention this story's `*ResolutionV1` types mirror, and its Review Findings' deferred version-pinning gap (directly relevant prior art for this story's version-mismatch design, not something to blindly re-defer)
- [Source: backend/application/contracts/scenario_projection.py] — the exact `TaskV1`/`WorkerV1`/`DemandIntervalV1`/`AssignmentV1`/`LockV1`/`ConstraintV1` shapes this story's resolution types wrap
- [Source: backend/application/ports/scenario_projection.py] — `ScenarioProjectionReader` Protocol and the non-generic `*PageV1` dataclass convention to mirror for `*ResolutionV1`
- [Source: backend/adapters/postgres/scenario_projection.py:322-357] — `PostgresScenarioProjectionReader._projection_row` (the "latest version" query this story reuses unmodified) and the `_normalize_*` functions this story's resolvers search against
- [Source: backend/api/routers/scenario_projection.py] — the seven existing endpoints, the `_task_out`/`_worker_out`/... mapping helpers this story reuses for resolved items, and the router module this story's six new routes are added to
- [Source: backend/api/main.py:66-95] — `versioned_http_problem`, the global `HTTPException` handler whose fixed code-lookup table collapses all plain `HTTPException(404)` calls to `code="resource_not_found"` — the concrete reason two of this story's three failure outcomes must call `api.problems.problem_response(...)` directly instead of raising
- [Source: backend/api/problems.py] — `problem_response(*, status, code, title, detail) -> JSONResponse`, the direct RFC 7807 response builder this story uses to produce distinct codes
- [Source: backend/api/deps.py:71-77] — `get_projection_reader`, reused unmodified
- [Source: evidence/story-1.4/nfr35-scenario-data-load.json] — the exact NFR35 evidence-file JSON shape and field set to match, including the 1,547-item `demand` group measurement this story's "deepest out-of-window record" case builds on

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
