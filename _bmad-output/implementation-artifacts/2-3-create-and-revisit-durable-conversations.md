---
baseline_commit: 8c21de0bfc680920359f91740d13d3eb36776ff0
---

# Story 2.3: Create and Revisit Durable Conversations

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want my conversations and accepted turns to survive reconnects,
So that I can investigate a fixture without losing or duplicating the decision context.

**This is the first planner-visible Epic 2 feature**, and the first story in the repository that **writes to governed PostgreSQL from a request**. Everything before it was read-only by construction (Gate A / AD-4). That single fact is the source of most of the traps below.

**Stories 2.1 and 2.2 are its foundation, not its subject — and both are `done`.** `AgentRuntime`, its owned contracts, the `backend/agent/` adapter, `backend/evals/`, and the evaluation harness all exist and are green at this story's `baseline_commit` (`8c21de0`, `main`). This story *persists conversations*; it does not modify either seam and does not run the agent (see Decision 2).

**This story contributes no golden evaluation cases.** Story 2.2's harness now exists, and it is tempting to feed it. Resist: 2.3 has no evaluation AC, and 2.2's Task 3 ships exactly one evaluator (tool routing) that judges tool name and arguments — it has nothing to say about a message that was persisted but never routed to a tool. The evaluators that would make a 2.3 case meaningful are Story 2.7's (grounding) and 2.9's (refusal/injection). Adding cases here would pad NFR28's aggregate without measuring anything, which `epics.md`'s own dataset-threshold caveat explicitly warns against.

**Unblocks:** Story 2.4 (SSE replay over the event stream this story persists), 2.5 (the inspect capability that finally gives an accepted turn something to execute), and every later conversational story.

---

### Four decisions were made at story creation — do not re-litigate them

#### Decision 1 — Conversation routes are mounted at `/api/v1/conversations`, **never** under `/api/v1/scenarios`

This is not a style preference. `backend/tests/test_gate_a_mutation_audit.py:25` asserts:

```python
scenario_paths = {p: ops for p, ops in app.openapi()["paths"].items()
                  if p.startswith("/api/v1/scenarios")}
for path, operations in scenario_paths.items():
    methods = set(operations) - {"parameters"}
    assert methods == {"get"}, f"{path} exposes {sorted(methods)}"
```

A `POST /api/v1/scenarios/{id}/conversations` turns that Gate A test **red**. AR28 is explicit: *"No later gate may weaken an earlier gate's invariants."* Editing the assertion to carve out an exception would weaken AD-4's *"no scenario-source mutation command, route, tool, or UI control"* proof — the exact thing Story 1.9 built it to guarantee.

Mounting elsewhere is also the architecturally correct answer, not merely the convenient one: AD-22 gives `conversation` its own aggregate owner, distinct from `scenario`. The scenario stays read-only; the conversation is a peer resource that *references* a scenario version.

- `POST /api/v1/conversations` — body carries `scenario_id`; server resolves and pins the current `scenario_version_id`.
- `GET /api/v1/conversations?scenario_id=…` — list conversations for a scenario.
- `POST /api/v1/conversations/{conversation_id}/messages` — the accept-turn command.
- `GET /api/v1/conversations/{conversation_id}/timeline` — the ordered `ActivityItemV1` reconstruction.

**Verify, do not assume:** after wiring the router, run `test_gate_a_mutation_audit.py` and confirm it is still green. Note that line 31's bare `assert scenario_paths` already guards the empty-set case, so you do not need to add that check — you need to not *break* it.

#### Decision 2 — This story **accepts and persists** a turn. It does not **execute** the agent.

AC1's own words are *"accepted agent run"* — not *completed*, not *executed*. AD-22 fixes the bundle as `accept-turn = message + agent-run + event`, and stops there.

The `AgentRun` row is created in AD-7's initial state `agent_queued` and this story never transitions it. That is faithful, not lazy:

- Story **2.5** is what gives an agent turn anything worth executing (the governed inspect capability). Running a turn now would mean either a live provider on a request path or a test double in production code — and would drag in the capability registry that Story 2.5 explicitly owns.
- Story **2.4** owns the live event stream that would carry a run's progress.

**The consequence must be represented honestly in the UI.** A run that will never leave `agent_queued` in this slice may not be dressed as activity: UX-DR5 forbids *"anthropomorphic waiting"*, and EXPERIENCE.md's Chat row requires literal persisted state. Render the literal status (e.g. `Agent run accepted — queued`), never a typing indicator, animated ellipsis, "Thinking…", or a fabricated ETA.

#### Decision 3 — This story defines `ActivityItemV1` + `PersistedEventV1` and owns the **write and read** sides. Story 2.4 owns the **transport**.

Story 2.1 deliberately refused to define these two contracts, naming Stories 2.3 and 2.4 as their owners (`backend/application/contracts/agent_runtime.py:19-23`). The split between 2.3 and 2.4 is settled here by what each story's ACs actually require:

| Concern | Owner | Evidence |
|---|---|---|
| `ActivityItemV1` and `PersistedEventV1` contracts | **2.3** | 2.3-AC1 cannot commit a *"first persisted activity event"* without them |
| Stream identity, monotonic decimal sequence allocation, the persisted row | **2.3** | same |
| Timeline reconstruction endpoint | **2.3** | 2.3-AC2 *"the same ordered `ActivityItemV1` timeline is reconstructed"* |
| SSE endpoint, `Last-Event-ID` validation, replay, 15-s heartbeats | **2.4** | every 2.4 AC is about the *stream*, not the record |
| NFR35 reconnect-replay measurement | **2.4** | 2.4-AC3 names it explicitly |

**Define the full eight-value `ActivityItemV1` discriminant vocabulary as a closed `Literal`; implement only the `planner_message` payload.** AD-20 names all eight (planner message, agent response, clarification, draft, run progress, comparison, approval request, terminal outcome). Fixing the vocabulary now stops a later story inventing a ninth name or renaming one; implementing only the variant this story actually produces avoids shipping seven unvalidated payload shapes. This is the same move Story 2.2 made with AD-5's five risk classes — a vocabulary that constrains, without claiming authority it has not proved.

#### Decision 4 — No idempotency key on the message command

AD-8/AR8 scope idempotency keys to *"FR-12, FR-16, FR-18, FR-19 and all mutating capability modules."* **FR-4 is not in that list**, and no AC in this story mentions one. AC2's *"replayed events never duplicate visible messages or cards"* is **replay deduplication by event identity** (UX-DR6), which is a different mechanism from command idempotency.

Double-submit is handled where it belongs for this slice: the composer disables Send while the mutation is in flight (Task 9). Do not build an `idempotency_key` column, an `Idempotency-Key` header, or a canonical body hash here — Story 3.1+ owns that under AD-8, and a half-built version now would have to be replaced.

---

## Acceptance Criteria

1. **Given** an authenticated selected scenario **when** the planner creates a conversation or submits a message **then** the conversation, planner message, accepted agent run, first persisted activity event, actor/site context, scenario version, and correlation IDs commit before acknowledgement **and** the accept-turn bundle is atomic and contains only the entities needed for durable conversation. *(FR4, AR6, AR22)*

2. **Given** one or more conversations for a scenario **when** the planner opens Chat, chooses a prior conversation, creates a new one, reloads, or returns later **then** the same ordered `ActivityItemV1` timeline is reconstructed with stable activity identities **and** replayed events never duplicate visible messages or cards. *(FR4, UX-DR6)*

3. **Given** a submitted planner message **when** the composer is used **then** Enter inserts a newline, Ctrl/Cmd+Enter or the visible Send button submits, recoverable failure retains draft text, and sending creates only a planner message **and** it never encodes Run optimization or approval. *(UX-DR7, UX-DR35)*

## Tasks / Subtasks

- [x] **Task 1: Define the two owned contracts** (AC: #1, #2)
  - [x] `backend/application/contracts/activity.py` — `ActivityItemV1`. Required shape per AD-20: common activity ID, discriminant, aggregate refs/versions, occurred time; the `planner_message` variant adds message ID + text.
  - [x] Declare the discriminant as a closed `Literal` of **exactly** these eight, spelled as `snake_case`: `planner_message`, `agent_response`, `clarification`, `draft`, `run_progress`, `comparison`, `approval_request`, `terminal_outcome`. Implement the payload for `planner_message` only; the other seven are reserved names, not shipped shapes.
  - [x] `backend/application/contracts/persisted_event.py` — `PersistedEventV1`. Required shape per AD-21: `stream_id`, decimal `sequence`, `event_type`, `occurred_at`, `resource_version`, correlation IDs, and exactly one typed `ActivityItemV1` payload.
  - [x] Every contract carries `schema_version` (spine, *Normative contract minimums*). Frozen dataclasses, `V1` suffix — mirror `application/contracts/evidence_ref.py` and `agent_runtime.py`, which are the two established examples.
  - [x] **Acceptance boundary:** a contract test asserts the discriminant `Literal` has exactly eight members and that constructing `PersistedEventV1` without a payload is impossible.

- [x] **Task 2: The `sequence` is decimal, and it is serialized as a string** (AC: #1, #2)
  - [x] AD-21 says **decimal** `sequence`, not integer. Use PostgreSQL `NUMERIC` (SQLAlchemy `Numeric`, `asdecimal=True` → Python `Decimal`). **Do not use `bigint`** — AD-21 is normative and Story 2.4 builds `Last-Event-ID` replay directly on this column.
  - [x] **Serialize `sequence` as a JSON string in every API response.** A JSON number becomes an IEEE-754 double in the browser; AD-21's SSE ID format is `<stream_uuid>:<sequence>`, so a value that round-trips through a float has already broken Story 2.4 before it starts. This is the single most likely silent defect in this story.
  - [x] Allocate the sequence **inside** the accept-turn transaction, monotonically per stream, with a database `UNIQUE (stream_id, sequence)` constraint backing it. Do not allocate in Python from a prior `SELECT MAX(...)` read outside the transaction.
  - [x] `stream_id` for a conversation stream **is the conversation's own UUID**. Record this so Story 2.4 does not invent a second stream identifier.
  - [x] **Acceptance boundary:** a test asserts the serialized `sequence` is a JSON string, and a test asserts two concurrent accept-turns on one conversation cannot produce the same sequence (the unique constraint must be the thing that proves it).

- [x] **Task 3: The migration — the first governed write surface** (AC: #1)
  - [x] One Alembic revision with `down_revision = "5e2a4c9d1f70"` (current head; `alembic check` must show zero diff afterwards). Four tables: `conversation`, `message`, `agent_run`, `persisted_event`.
  - [x] Follow `5e2a4c9d1f70_add_seeded_site_identity.py` exactly for structure, and `d128d081ab48`'s loop for RLS. Every table: `site_id` column, `ENABLE` **and** `FORCE ROW LEVEL SECURITY`, plus a `<table>_site_isolation` policy with both `USING` and `WITH CHECK` on `site_id = NULLIF(current_setting('app.site_id', true), '')::uuid` (AD-23).
  - [x] Use the composite `(id, site_id)` unique-constraint + composite-FK pattern from `adapters/postgres/schema.py:87-88,119-131` so a cross-site foreign key is **structurally impossible**, not merely policy-prevented.
  - [x] `conversation` pins `scenario_id` **and** `scenario_version_id` at creation (AD-4/AD-9: the version a conversation reasons about must not drift), and carries `resource_version bigint NOT NULL DEFAULT 1` (spine: *mutable aggregates carry monotonic `bigint` versions*).
  - [x] `agent_run.status` gets a `CHECK` constraint over AD-7's **complete closed** vocabulary — `agent_queued`, `agent_running`, `approval_required`, `agent_completed`, `agent_timed_out`, `agent_cancelled`, `agent_failed` — even though this story only ever writes `agent_queued`. AD-7 is the only legal status graph; fixing it here stops a later story inventing a parallel vocabulary.
  - [x] **Grants: least privilege, this story's writes only.** `GRANT SELECT, INSERT` on all four tables to `shiftmind_runtime`; `GRANT UPDATE (resource_version)` on `conversation` alone (Task 4 bumps it); `REVOKE UPDATE, DELETE` everywhere else — mirroring `d128d081ab48`'s treatment of `scenario_version`. Epic 3 will need `UPDATE` on `agent_run` to advance the state machine; **it is that story's job to grant it**, not this one's to grant it early.
  - [x] Write a real `downgrade()` that reverses grants, policies, and tables in order — both existing migrations do, and `alembic check` is part of the gate.
  - [x] **Acceptance boundary:** `alembic upgrade head` then `downgrade` then `upgrade` succeeds against the Docker PostgreSQL 18 service, and `alembic check` reports zero diff.

- [x] **Task 4: The accept-turn use case — one transaction, one bundle** (AC: #1)
  - [x] `backend/application/use_cases/accept_turn.py` (new package `backend/application/use_cases/`, per AR26's `application/  # use cases, policy, state machines, ports, DTOs`). **Do not add this to `backend/services/`** — that is the legacy seam AD-1 permits to remain but not to grow.
  - [x] The bundle is fixed by AD-22 and may not be widened: **message + agent-run + event**, committed together, plus the `conversation.resource_version` bump. Nothing else. No audit envelope, no evidence snapshot, no job row — those belong to their own owners and none is required by an AC here.
  - [x] Everything trusted comes from server state: `actor_id` and `site_id` from `ResolvedSession` (via `get_site_context`), `scenario_version_id` re-resolved from the conversation row. **Nothing authority-bearing is read from the request body** (AD-2, AD-15). The body carries the message text and, on create, a `scenario_id` — both of which are *inputs to be validated*, never authority.
  - [x] Correlation IDs: generate a server-side `request_id` (UUID) in the use case and persist it on the event alongside `conversation_id`, `agent_run_id`, `site_id`, `actor_id` (spine, *Correlation* row). **Do not build app-wide correlation middleware** — the repo has none, `api/problems.py` carries no correlation ID today, and closing that AD-13 gap globally is not this story's scope. Note it in completion notes.
  - [x] **Atomicity must be proven by a failure, not asserted by a comment.** Write a test that injects a failure *after* the message insert and *before* the event insert, and assert that zero rows from the bundle survive.
  - [x] **Acceptance boundary:** the injected-failure test leaves no partial bundle, and a successful accept-turn writes exactly one row to each of `message`, `agent_run`, `persisted_event` and bumps `conversation.resource_version` by one.

- [x] **Task 5: The port and the PostgreSQL adapter** (AC: #1, #2)
  - [x] `backend/application/ports/conversation.py` — a `Protocol` plus frozen-dataclass DTOs.
  - [x] **Copy `application/ports/scenario_projection.py`, not `application/ports/scenario_catalogue.py`.** The projection port types its connection parameter as `connection: Any` (`scenario_projection.py:104`), keeping SQLAlchemy out of the application layer per AD-1. The older catalogue port does `from sqlalchemy import Connection` (`scenario_catalogue.py:9`) — a real, pre-existing AD-1 leak. **Do not copy it, and do not fix it here** (it is Gate A code and out of scope); Task 11 pins the new port against repeating it.
  - [x] `backend/adapters/postgres/conversation.py` — SQLAlchemy Core against the Task 3 tables, driven by the `Connection` yielded by `get_site_context`. That dependency already does `SET LOCAL ROLE shiftmind_runtime` and sets `app.site_id`; **do not open a second engine or connection** — the RLS context lives on that transaction and nowhere else.
  - [x] Timeline read: ordered by `sequence` ascending, returning `ActivityItemV1[]` derived from `persisted_event` rows, plus the conversation's `resource_version` and its latest agent-run status. Deterministic stable ordering, no `LIMIT`-less unbounded scan of an unbounded table — bound the window and say so in the response (AD-4's ordering discipline, UX-DR24's no-infinite-scroll rule).
  - [x] **Acceptance boundary:** a `@pytest.mark.postgres` test proves a Site B session cannot read or insert into a Site A conversation, and that the denial is indistinguishable from absence (AD-3's non-disclosure rule; the same shape as `test_scenario_projection.py`'s existing cross-site cases).

- [x] **Task 6: The API router** (AC: #1, #2)
  - [x] `backend/api/routers/conversations.py`, mounted at `/api/v1` per **Decision 1**. Model the file on `api/routers/scenario_projection.py`: `APIRouter(prefix=…, tags=…)`, `Depends(get_site_context)`, `_PROBLEM_RESPONSES` declaring `ProblemDetailsV1` for the error statuses, explicit response models in `api/schemas.py`.
  - [x] The four endpoints from Decision 1. `POST` returns `201` with the created resource; the message command returns the accepted activity item and the conversation's new `resource_version`.
  - [x] Errors are RFC 7807 via `api/problems.py` (AD-13). A conversation belonging to another site returns the **same** shape as one that does not exist. Unknown `scenario_id` on create → `404`, not `422`.
  - [x] **CSRF and session already work — do not rebuild them.** `api/main.py:180-237`'s middleware authenticates every `/api/v1` path and enforces same-origin + `X-CSRF-Token` on `POST`. `CORSMiddleware` already lists `POST` (`api/main.py:253`). The frontend client already attaches the header (`frontend/src/api/client.ts:17-25`). Your job is to *use* this, and to prove it: a `POST` with no CSRF header must return `403 csrf_validation_failed`.
  - [x] **Acceptance boundary:** OpenAPI shows the four paths with the intended methods; the CSRF-less `POST` returns 403; and `test_gate_a_mutation_audit.py::test_gate_a_scenario_openapi_surface_is_get_only` is still green, unmodified.

- [x] **Task 7: Regenerate the client contract** (AC: #2, #3)
  - [x] `npm run codegen` from `frontend/` (runs `scripts/export_openapi.py` then `openapi-typescript`). **Never hand-edit `frontend/src/api/schema.d.ts`.**
  - [x] `frontend/src/api/conversations.ts` — thin typed wrappers over the single shared `client`, deriving every request/response type from `paths[…]`, exactly like `api/scenarioProjection.ts`. Throw `{ ...error, status: response.status }` on failure, matching the established shape that `lib/errors.ts:getErrorStatus` consumes.
  - [x] **Acceptance boundary:** `npm run typecheck` passes with zero hand-authored request/response interfaces in the new client module.

- [x] **Task 8: Hooks and the timeline** (AC: #2)
  - [x] `frontend/src/hooks/useConversations.ts`, `useConversationTimeline.ts`, `useSendMessage.ts` — thin TanStack Query wrappers, no business logic, matching `useScenarioProjection.ts`.
  - [x] `useSendMessage` is the repo's **first mutation**. `onSuccess` → `queryClient.invalidateQueries({ queryKey: [...] })` for the timeline and conversation list. Query keys are cross-plan contracts; name them deliberately.
  - [x] `frontend/src/features/chat/` — `ChatView`, `ConversationList`, `ActivityTimeline`, `Composer`. Reuse the existing primitives rather than inventing new ones: `EmptyState`, `InlineAlert`, `StatusBadge`, `Skeleton`, and `ReconnectBanner` all exist in `components/primitives/` from Story 1.6 and were built for exactly these states.
  - [x] **Deduplicate by activity identity, not by array position** (UX-DR6, AC2). Key the rendered list on the activity ID; a re-fetch that returns an already-rendered activity must not produce a second card. Prove it with a test that feeds the same activity twice.
  - [x] Empty conversation renders EXPERIENCE.md's required copy shape: *"New conversation prompt with example scope, not fabricated history"* — no invented prior turns.
  - [x] **Acceptance boundary:** a test renders a timeline, re-delivers an identical activity item, and asserts exactly one visible card; a second test asserts reload reconstructs the same ordered activity IDs.

- [x] **Task 9: The composer** (AC: #3)
  - [x] Verbatim from EXPERIENCE.md's *Keyboard and focus* section: *"`Enter` inserts a new line; `Ctrl+Enter` / `Command+Enter` sends. The visible Send button is always available when sending is valid. Sending never triggers Run optimization or approval."* Handle **both** `ctrlKey` and `metaKey`.
  - [x] Multiline `<textarea>`, not an `<input>`. A plain `<form onSubmit>` around a textarea would submit on Enter — that is precisely the behavior AC3 forbids.
  - [x] **Recoverable failure retains the draft.** Clear the textarea on *success only* — never in the submit handler, never optimistically. `ConstraintInput.tsx`'s existing comment records this exact lesson from the legacy UI: clear on the success condition, not on HTTP 200.
  - [x] Disable Send while `mutation.isPending` (this is also Decision 4's double-submit answer).
  - [x] **UX-DR35: Send must be visually discontinuous from Run optimization and Approve.** No shared "AI action" button treatment spanning authority levels. This story ships only Send; do not add a disabled Run or Approve control "for later".
  - [x] **Acceptance boundary:** four tests — Enter inserts a newline and does not submit; Ctrl+Enter and Cmd+Enter each submit; the Send button submits; a rejected mutation leaves the draft text in the textarea.

- [x] **Task 10: Wire the route** (AC: #2, #3)
  - [x] Replace `frontend/src/routes/ScenarioChat.tsx`'s `WorkspaceTabPlaceholder` with the real `ChatView`. The route already exists as the workspace index route (`App.tsx`); `WorkspaceTabs.tsx` already links to it. **No routing change is needed** — do not restructure the route tree.
  - [x] Take `scenarioId` from `useParams` as it does today, and the pinned version context from the existing `ScenarioVersionContext` / `useScenarioContext` rather than re-fetching it.
  - [x] **Acceptance boundary:** the existing workspace and router tests stay green, and a route test deep-links to `/scenarios/:id` and renders Chat.

- [x] **Task 11: Make the new boundary executable** (AC: #1)
  - [x] Add a **sibling** file in `backend/tests/architecture/` asserting the **new** application-layer modules — `application/contracts/activity.py`, `contracts/persisted_event.py`, `ports/conversation.py`, `use_cases/**` — import neither `sqlalchemy` nor `fastapi`. Do not bolt this onto `test_agent_runtime_boundaries.py`, whose scope is the agent seam.
  - [x] **Model it on `backend/tests/architecture/test_evaluation_boundaries.py`**, which Story 2.2 added to this same package. It is the current best example in the repo: a focused guard plus explicit self-tests that prove the guard fails on a violating input (`test_network_guard_actually_fails_on_a_violating_builder`, `test_direction_guard_actually_fails_on_a_reverse_import`). Copy that shape — it satisfies this task's red-then-green requirement by construction.
  - [x] Note that `test_evaluation_boundaries.py::test_application_and_domain_never_import_evals` already covers `backend/application/**` and will pick up the new `use_cases/` package automatically. Nothing under `application/` may import `evals`; no action needed beyond not doing it.
  - [x] Scope the new guard to those modules with an explicit, **documented** allow-list entry for the known `application/ports/scenario_catalogue.py` leak. A guard that lies about its own coverage is exactly the defect the Story 2.1 review fixed in this file's docstring (`deferred-work.md`, 2026-08-10) — state precisely what is and is not covered.
  - [x] In the allow-list entry's comment, cite `deferred-work.md`'s *"Deferred from: story-2-3 creation (2026-08-10)"* item, which tracks the leak, records the three fix tiers, and names deleting this entry as its definition of done. A suppression with no ticket behind it becomes permanent.
  - [x] **Acceptance boundary:** the guard **fails** when temporarily given a real `from sqlalchemy import Connection` in `ports/conversation.py`, and passes on the shipped tree. Demonstrate both — a guard nobody has seen go red is a guard nobody has tested.

- [x] **Task 12: Full regression gate** (AC: #1, #2, #3)
  - [x] Backend: `uv run --frozen pytest`; `uv run --frozen pytest -m postgres` (Docker PostgreSQL 18 via `docker-compose.yml`); `alembic check` zero diff.
  - [x] **The exact alembic invocation, verified at `8c21de0` with Docker PostgreSQL up.** From the **repository root**:
    ```
    uv run --project backend alembic check     # → "No new upgrade operations detected."
    ```
    From `backend/` (pytest's working directory, and the natural place to stand) it fails with `FAILED: No 'script_location' key found in configuration.` — which reads exactly like a missing config and is **not**. `alembic.ini` is checked in at the repo root (Story 1.1, `3e9540c`), `script_location = %(here)s/backend/migrations`, and `backend/migrations/env.py:20-22` fills `sqlalchemy.url` from `default_settings().provisioning_database_url`, so no manual URL is needed.
  - [x] **Do not synthesize a temporary alembic config.** Story 2.2 did, on the basis of a `deferred-work.md` entry claiming the repository has no checked-in `alembic.ini`. That claim is false; the entry has been struck through and corrected in place with the measurement table above. You are the first story since to add a migration — get this right.
  - [x] Frontend: `npm run codegen`, `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`, `npm run test:e2e`. Note `test:e2e` is now build-first (`npm run build && playwright test`, `frontend/package.json:13`) — Story 2.2 changed it, so a stale `dist/` no longer silently passes.
  - [x] **Re-run Gate A and report by name.** AR28 binds this story hard: it is the first to add a write path, and `gate_a_passed` must still read `true`. Regenerate `evidence/story-1.11/gate-a-readiness-report.json` per `docs/EVIDENCE-CONVENTION.md` — **commit code first, measure on a clean tree, generate through `backend/scripts/evidence_binding.py`, commit evidence separately.** Never hand-type it.
  - [x] Story 2.2 extended `resolve_bindings()` with keyword-only `dataset_files=` and `code_binding=` parameters, both defaulted — **the signature is backward compatible and the Gate A call path is unchanged.** This story needs neither parameter (it produces no evaluation report); call it exactly as the existing Gate A flow does.
  - [x] **Re-derive baselines at the start rather than trusting these.** Recorded at this story's `baseline_commit` (`8c21de0`, Story 2.2 `done`): backend **510 passed / 7 deselected**; postgres **27 passed**; live **7 skipped** (no API key); frontend **50 files / 287 tests**; e2e **46 passed**; alembic zero diff; `gate_a_passed: true`. These are one story fresher than the numbers Story 2.2 worked from — still re-derive on a clean tree before treating any delta as this story's regression.
  - [x] **Acceptance boundary:** every suite green at its re-derived baseline plus this story's new tests, and Gate A still `true`.

### Review Findings

Code review 2026-08-10 (Blind Hunter + Edge Case Hunter + Acceptance Auditor, all three layers completed). 27 patch, 1 deferred, 3 dismissed as noise. Severity is `[high]` / `[medium]` / `[low]` by consequence for the planner. Both originally decision-needed items were resolved with Minh on 2026-08-10 and are recorded below in their resolved form.

**Patch**

- [x] [Review][Patch] `[high]` The server invents the version pin instead of honouring the one the planner is looking at — `create()` runs `ORDER BY imported_at DESC LIMIT 1` [backend/adapters/postgres/conversation.py:18], a "newest wins" rule no requirement asks for. Task 10 is explicit: *"the pinned version context from the existing `ScenarioVersionContext` / `useScenarioContext`"* — and `ScenarioChat.tsx` imports neither. Pinning is otherwise enforced correctly and immutably (column written once, only `resource_version` is grantable for `UPDATE`, composite FK with `RESTRICT`), which is precisely what makes an arbitrary *initial* selection the whole defect: AD-9's "must not drift" is meaningless if the thing pinned was chosen by accident. **Resolution (Minh, 2026-08-10): select by version identity, do not resolve latest.** (1) `ChatView` reads `scenario_version_id` from `useScenarioContext` and sends it in the create body; (2) the server validates it belongs to that `scenario_id` and `site_id`, returning 404 on mismatch per AD-3 non-disclosure — a selector to be validated, exactly as Task 4 already blesses for `scenario_id`, not authority from the body; (3) delete the `imported_at DESC` lookup entirely, which also moots the tie-break. **Blocker to clear first:** `ScenarioContextOut` does not expose `scenario_version_id` [backend/api/schemas.py:155] — add it (`ScenarioOverviewOut` is the precedent) or repoint the workspace, then re-run the Gate A readiness report since this touches a Gate A read model.
- [x] [Review][Patch] `[medium]` Chat ships entirely unstyled — zero `className` anywhere under `frontend/src/features/chat/`, unlike every other feature in the app, and none of Task 8's mandated primitives (`EmptyState`, `InlineAlert`, `StatusBadge`, `Skeleton`, `ReconnectBanner`) is imported. **Resolution: adopt the mandated primitives plus minimal Tailwind consistent with the surrounding app.** The UX-DR35 visual-discontinuity requirement is split out as a deferred item below.
- [x] [Review][Patch] `[high]` Timeline returns the *oldest* 200 events and never signals truncation, so past 200 activities the planner's own new messages become permanently invisible with no cursor and no `has_more` — breaks AC2's "the same ordered timeline is reconstructed" [backend/adapters/postgres/conversation.py:32]
- [x] [Review][Patch] `[high]` Zero HTTP-level tests for any of the four endpoints — Task 6's acceptance boundary "a `POST` with no CSRF header must return `403 csrf_validation_failed`" is unproven, as are 201, 404, and the cross-site-equals-absence response shape; the only router coverage is OpenAPI introspection [backend/tests/test_conversation_contracts.py:86]
- [x] [Review][Patch] `[high]` Task 10's acceptance boundary "a route test deep-links to `/scenarios/:id` and renders Chat" does not exist — the workspace route test stubs the index route out, and `ChatView`, `ConversationList`, `useSendMessage`, `useConversations`, `useConversationTimeline`, and `api/conversations.ts` have no coverage at all [frontend/src/routes/ScenarioWorkspace.test.tsx:38]
- [x] [Review][Patch] `[high]` Chat has no pending and no error branch — `timeline.data?.items ?? []` collapses loading and every failure into the "Start a new conversation…" empty prompt, showing "no history" for a conversation that has persisted turns; contradicts EXPERIENCE.md's restore-timeline skeleton and UX-DR25 [frontend/src/features/chat/ChatView.tsx:14]
- [x] [Review][Patch] `[high]` Conversation selection is not durable — `useState("")` resets when the tab switch unmounts `ChatView`, and the auto-select effect silently lands the planner on the newest conversation, so the next message posts into a different conversation than the one they were reading; this is exactly AC2's "chooses a prior conversation … returns later" [frontend/src/features/chat/ChatView.tsx:10]
- [x] [Review][Patch] `[medium]` `sequence` is absent from `ActivityItemOut` and `TimelineOut`, so Task 2's "serialize `sequence` as a JSON string in **every** API response" is half done and a client reconstructing a timeline has no `<stream_uuid>:<sequence>` for Story 2.4 to resume from [backend/api/schemas.py:105]
- [x] [Review][Patch] `[medium]` `_activity_from_payload` reads `message_id` and `text` unconditionally, so the first non-`planner_message` event ever persisted poisons the whole conversation's read path with an uncaught `KeyError` → 500; `ActivityItemV1` also makes both fields required for all eight discriminants, so no reserved variant is constructible [backend/adapters/postgres/conversation.py:55]
- [x] [Review][Patch] `[medium]` A test-only `after_message` injection callback is baked into the production `ConversationRepository` Protocol, the use case signature, and the adapter — every future implementer must honour a hook that exists so one test can raise [backend/application/ports/conversation.py:40]
- [x] [Review][Patch] `[medium]` The atomicity test is tautological — the test itself calls `tx.rollback()`, then asserts only that `message` is empty; `agent_run`, `persisted_event`, and `conversation.resource_version` are never re-checked, and the production teardown path is never exercised [backend/tests/test_conversations_postgres.py:40]
- [x] [Review][Patch] `[medium]` The concurrency test can never exercise `uq_persisted_event_stream_sequence` — the advisory lock plus `FOR UPDATE` fully serialize the writers, so deleting the unique constraint leaves the test passing, defeating Task 2's "the unique constraint must be the thing that proves it" [backend/tests/test_conversations_postgres.py:51]
- [x] [Review][Patch] `[medium]` `pg_advisory_xact_lock` is acquired *before* the RLS-filtered select, so a Site B caller takes a cluster-global lock on a Site A conversation UUID — blocking the legitimate owner and turning lock-wait into an existence oracle; the lock is also redundant with the `FOR UPDATE` on the next line [backend/adapters/postgres/conversation.py:38]
- [x] [Review][Patch] `[medium]` Whitespace-only message text returns 500 `internal_error` instead of 422 — `MessageCreateIn` enforces `min_length=1` without stripping, so `{"text":"   "}` validates and then hits `raise ValueError` in the use case with no handler [backend/application/use_cases/accept_turn.py:22]
- [x] [Review][Patch] `[medium]` "New conversation" has no in-flight guard and no rejection path — `onClick={() => void start()}` discards the promise, so a 403/404/503 is silent and a double-click creates two conversations [frontend/src/features/chat/ChatView.tsx:13]
- [x] [Review][Patch] `[medium]` Conversation labels are positional (`Conversation {i + 1}`) over a `created_at DESC` list, so creating a new conversation renames every existing one — destabilising the only human-readable handle for AC2's "chooses a prior conversation" [frontend/src/features/chat/ConversationList.tsx:2]
- [x] [Review][Patch] `[medium]` The composer can double-submit — the only re-entrancy guard is the `isPending` prop, which updates a render later, so held or double-tapped Ctrl/Cmd+Enter sends twice; Decision 4 named this disable as the sole double-submit defence [frontend/src/features/chat/Composer.tsx:5]
- [x] [Review][Patch] `[medium]` `persisted_event` is the one new table missing the composite `(id, site_id)` unique constraint the other three carry, so no site-bound foreign key can ever reference an event row — Task 3 required the pattern on every table [backend/adapters/postgres/schema.py:313]
- [x] [Review][Patch] `[medium]` No indexes on any of the four new tables — `conversation.scenario_id`, `persisted_event.conversation_id`, `agent_run.(conversation_id, created_at)`, and `site_id` on all four (the FORCE-RLS predicate) are unindexed; `uq_persisted_event_stream_sequence` is the only usable index in the aggregate [backend/migrations/versions/a4f92d7c8e31_add_durable_conversations.py:20]
- [x] [Review][Patch] `[medium]` `PersistedEventV1` is dead code — the write path hand-builds an untyped dict and the read path rehydrates a dict, so the AD-21 envelope this story exists to own has never round-tripped a real row, against Decision 3's "owns the write and read sides" [backend/adapters/postgres/conversation.py:49]
- [x] [Review][Patch] `[medium]` The `stream_id == conversation_id` invariant is asserted only in prose — reads filter on `conversation_id` while uniqueness is on `stream_id`, so a later writer using a different stream for the same conversation yields duplicate sequences inside one rendered timeline [backend/adapters/postgres/conversation.py:32]
- [x] [Review][Patch] `[medium]` `ChatView` emits a second `<h1>` on a page whose loaded state already renders one in `ScenarioVersionContext`; the placeholder it replaced used `<h2>`, which the sibling Runs/Results tabs still emit, and neither a11y suite was extended to cover the new surface [frontend/src/features/chat/ChatView.tsx:14]
- [x] [Review][Patch] `[medium]` Conversation list is capped at 100 `created_at DESC` with no pagination and no truncation signal, so the oldest conversations become permanently unreachable [backend/api/routers/conversations.py:37]
- [x] [Review][Patch] `[low]` A scenario that exists in-site but has zero versions returns 404 `resource_not_found`, indistinguishable from a bad ID or a cross-site probe — wrong diagnosis for a recoverable data condition [backend/adapters/postgres/conversation.py:19]
- [x] [Review][Patch] `[low]` The status line hardcodes the "Agent run accepted —" prefix for all seven `agent_run` statuses the CHECK constraint admits, so Epic 3 will render "Agent run accepted — failed" [frontend/src/features/chat/ChatView.tsx:14]
- [x] [Review][Patch] `[low]` Task 11's allow-list exists only as module-docstring prose, not as a data entry — `deferred-work.md` records "deleting that allow-list entry" as the item's definition of done and "the thing to grep for", which is unimplementable as written [backend/tests/architecture/test_conversation_boundaries.py:14]
- [x] [Review][Patch] `[low]` Debug Log References records a pre-implementation baseline of "backend 516 passed" while the story spec and the regenerated evidence file both use 510 → 523; restate the figure so the delta reconciles [_bmad-output/implementation-artifacts/2-3-create-and-revisit-durable-conversations.md:330]

**Deferred**

- [x] [Review][Defer] `[low]` UX-DR35's "Send must be visually discontinuous from Run optimization and Approve" has no expression in code and no test [frontend/src/features/chat/Composer.tsx:6] — deferred, not actionable in this slice: the Chat surface ships no Run or Approve control for Send to be discontinuous *from*, and Task 9 explicitly forbids adding a disabled one "for later". Owner is the first story to ship a Run or Approve control on this surface.

**Dismissed as noise (3):** `frontend/openapi.json` entering version control (defensible codegen practice, nothing depends on its absence); "bare `HTTPException(404)` bypasses RFC 7807" (false — `api/main.py:67-96` maps every `/api/v1/` `HTTPException` to `problem_response`); an audit misquote of the architecture guard's path list (the file does correctly guard `application/contracts/persisted_event.py`).

**Verified genuinely met, not re-raised:** Decision 1 (routes mount at `/api/v1/conversations`; `test_gate_a_mutation_audit.py` untouched and green), Decision 2 (only `agent_queued` is ever written; literal status rendered, no anthropomorphic waiting), Decision 4 (no idempotency key anywhere), Task 1's closed eight-value `Literal` and payload-less-construction-impossible tests, Task 3's migration in full (FORCE RLS with `USING` + `WITH CHECK`, composite site-bound FKs, the seven-value `ck_agent_run_status`, least-privilege grants with no `UPDATE` on `agent_run`, a real ordered `downgrade()`), Task 5's `connection: Any` port shape and cross-site repository denial test, Task 7's zero hand-authored types, Task 9's composer contract and all five of its tests, and the zero-line diff on every forbidden seam.

## Dev Notes

### What this story is, and the seven things it is not

It is: four governed tables, one atomic use case, two owned contracts, four endpoints, and a real Chat surface.

It is **not**:

| Not this | Owned by | Why not here |
|---|---|---|
| SSE, `Last-Event-ID`, heartbeats, replay | Story 2.4 | every 2.4 AC is about the stream; 2.3 persists the record it replays |
| Executing the agent turn | Story 2.5 | Decision 2 |
| The capability registry, `CapabilityManifestV1` | Stories 2.5, 2.6 | Story 2.1 already fenced these |
| Grounding, `EvidenceRefV1` on responses | Story 2.7 | no agent response exists yet |
| Evidence jump/return navigation | Story 2.8 | needs a grounded claim first |
| Clarification / refusal activity variants | Story 2.9 | reserved discriminant names only (Task 1) |
| Idempotency keys, `JobLeaseV1`, the worker | Epic 3 | Decision 4; AD-8 does not bind FR-4 |

### The five traps, ranked by how quietly they fail

1. **`POST` under `/api/v1/scenarios` turns Gate A red.** Decision 1. This one fails loudly — which makes it the *least* dangerous on this list.
2. **`sequence` as a JSON number.** Silently lossy in the browser, and Story 2.4 inherits the wreckage. Serialize as a string (Task 2).
3. **Clearing the composer in the submit handler.** Looks correct in every manual test where the request succeeds. AC3 requires the failure path (Task 9).
4. **Deduplicating the timeline by array index.** Passes until a refetch reorders or re-delivers. Key by activity ID (Task 8).
5. **Copying `scenario_catalogue.py`'s `from sqlalchemy import Connection` into the new port.** It is right there, it type-checks, and it violates AD-1. Task 11's guard is the mechanical defence.

### Inherited work this story is expected to close

`deferred-work.md` (2026-08-10, Story 2.1 review) assigns one item here by name:

> `to_framework_messages` silently drops an unrecognized `AgentMessageV1.role` (no `else`), and `_from_response`'s counterpart silently skips an unrecognized `AgentPartV1.kind` — both unreachable today since `to_owned_turn` is the only producer, but become reachable **once persisted/deserialized turns exist**. `[backend/agent/translate.py:61-105]` — *real persistence/deserialization boundary belongs to Story 2.3.*

**Judgement call, made deliberately: it does not become reachable in this story, so do not fix it here.** This story persists *planner messages and activity items*, not `AgentTurnV1` transcripts — no code path deserializes an owned turn back into framework messages, because Decision 2 means no turn is ever executed. The item becomes live in **Story 2.5**, which is the first story to run a turn and rehydrate history. Leave the ledger entry open and say so in completion notes; do not silently close it, and do not modify `backend/agent/**` (which must show a zero-line diff, as it did for Story 2.2).

### Existing conventions to match, not reinvent

| Need | Copy the pattern from |
|---|---|
| Port as `Protocol`, connection typed `Any` | `backend/application/ports/scenario_projection.py` — **not** `scenario_catalogue.py` |
| Versioned contract dataclasses, `V1` suffix, `schema_version` | `backend/application/contracts/evidence_ref.py`, `agent_runtime.py` |
| RLS + composite `(id, site_id)` FK | `backend/adapters/postgres/schema.py`; `d128d081ab48`'s RLS loop |
| Migration structure, roles, grants, real `downgrade()` | `backend/migrations/versions/5e2a4c9d1f70_add_seeded_site_identity.py` |
| Router shape, `_PROBLEM_RESPONSES`, `Depends(get_site_context)` | `backend/api/routers/scenario_projection.py` |
| RFC 7807 responses | `backend/api/problems.py` |
| Typed client wrappers derived from `paths[…]` | `frontend/src/api/scenarioProjection.ts` |
| TanStack query hook | `frontend/src/hooks/useScenarioProjection.ts` |
| Cross-site non-disclosure tests | `backend/tests/test_scenario_projection.py` |
| Postgres test fixtures | `backend/conftest.py:83-101` — `governed_postgres_engine`, `fresh_postgres_database_url` |
| Absolute backend imports | every module: `from application.contracts… import …`, never relative |

### Latest technical information (verified 2026-08-10)

**TanStack Query v5.101.2** — this story writes the repo's first `useMutation`. Confirmed current v5 patterns:

```tsx
const queryClient = useQueryClient();
const mutation = useMutation({
  mutationFn: (body: SendMessageBody) => sendMessage(conversationId, body),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["conversation-timeline", conversationId] });
  },
});

// Wrap mutate in your own handler — do NOT pass `mutation.mutate` directly as onSubmit.
const onSubmit = (event: React.FormEvent) => {
  event.preventDefault();
  mutation.mutate({ text: draft });
};
```

- `mutation.isPending` is the v5 name for the in-flight flag (v4's `isLoading` is gone). Task 9 gates Send on it.
- `invalidateQueries` takes an **object** in v5: `invalidateQueries({ queryKey: [...] })`, not a bare key.
- **`mutation.handleSubmit(...)` and `mutation.register(...)` do not exist.** Some circulating examples show them; they are `react-hook-form` API, and `react-hook-form` is not a dependency of this project. Do not add it.

**PostgreSQL / SQLAlchemy 2.0.51** — `Numeric` maps to `NUMERIC` and returns `Decimal` when `asdecimal=True` (the default for `Numeric`). Python's `json` module cannot serialize `Decimal` at all, and Pydantic v2 will render it as a JSON number unless the field is typed `str`. Task 2's string-serialization rule is the resolution; type the response field as `str` and convert at the schema boundary.

### Project Structure Notes

- **New (backend):** `backend/migrations/versions/<rev>_add_durable_conversations.py`, `backend/application/contracts/activity.py`, `contracts/persisted_event.py`, `backend/application/ports/conversation.py`, `backend/application/use_cases/__init__.py` + `accept_turn.py`, `backend/adapters/postgres/conversation.py`, `backend/api/routers/conversations.py`, and their tests.
- **New (frontend):** `frontend/src/api/conversations.ts`, `frontend/src/hooks/use{Conversations,ConversationTimeline,SendMessage}.ts`, `frontend/src/features/chat/**`.
- **Modified:** `backend/adapters/postgres/schema.py` (four table definitions), `backend/api/main.py` (one `include_router` line), `backend/api/schemas.py`, `frontend/src/api/schema.d.ts` (**generated only**), `frontend/src/routes/ScenarioChat.tsx`.
- **Not modified (verify a zero-line diff):** `backend/agent/**`, `backend/application/contracts/agent_runtime.py`, `backend/application/ports/agent_runtime.py`, `backend/llm/**`, `backend/services/**`, `backend/domain/**`, `backend/engine/**`, every existing migration.
- **Do not put conversation code under `frontend/src/features/scenario-data/`.** `frontend/src/test/scenarioDataBoundaries.test.ts` audits that directory for mutation affordances and forbidden imports; a chat composer landing there fails a Gate A frontend invariant. `features/chat/` is outside its scope by design — keep it that way.
- **Variance carried forward from Story 2.1:** architecture tests live at `backend/tests/architecture/`, not the spine's root-level `tests/architecture/`, because pytest runs from `backend/` with `testpaths = ["tests"]`. Task 11 follows the existing location; do not create a second rootdir.

### Anti-patterns for this story

- **Do not mount any `POST` under `/api/v1/scenarios`,** and do not edit `test_gate_a_mutation_audit.py` to make room for one.
- **Do not serialize `sequence` as a JSON number**, and do not "simplify" it to `bigint`.
- **Do not execute an agent turn**, add a capability registry, or call `create_agent_runtime()` — it is a known-incomplete factory (`deferred-work.md`, 2026-08-10) and wiring it is the job of whichever story first needs a live model.
- **Do not clear the composer draft anywhere but the success path.**
- **Do not build idempotency keys, a worker, a job queue, or SSE.** Decisions 3 and 4.
- **Do not implement the seven reserved `ActivityItemV1` payload variants.** Reserve the names, ship one shape.
- **Do not grant `UPDATE` on `agent_run`** — nothing in this story transitions a run.
- **Do not open a second database engine or connection.** RLS context lives on `get_site_context`'s transaction; a second connection has no `app.site_id` and will either fail closed or, worse, read as an unscoped role.
- **Do not add app-wide correlation-ID middleware** while closing AC1's correlation-ID requirement. Persist the IDs the event needs; record the AD-13 problem-details gap as still open.
- **Do not extend `backend/services/`.** It is the legacy seam; new use cases go in `backend/application/use_cases/`.
- **Do not add a CI workflow.** `.github/` does not exist; pipeline ownership remains out of scope (Stories 1.10, 1.11, 2.1).
- **Do not hand-type an evidence file.** `docs/EVIDENCE-CONVENTION.md` governs: commit code → measure on a clean tree → generate → commit evidence separately.
- **Do not weaken Gate A.** If a change breaks `ScenarioDataParity.test.tsx`, `scenarioDataBoundaries.test.ts`, `legacyReachability.test.ts`, or `test_gate_a_mutation_audit.py`, fix the change.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.3] — story statement and all three acceptance criteria, verbatim
- [Source: epics.md, *Additional Requirements*] — AR6 (persist accepted messages/agent runs/events before acknowledgement), AR14 (`ActivityItemV1` stream; approval never encoded as chat text), AR21 (persisted event fields, SSE ID format), AR22 (fixed atomic bundles; accept-turn), AR23 (RLS, roles, grants), AR26 (structural seed), AR28 (Gate A precedence; no later gate weakens an earlier one)
- [Source: epics.md, *UX Design Requirements*] — UX-DR6 (durable timeline, dedupe replay by event identity), UX-DR7 (composer: Enter newline, Ctrl/Cmd+Enter sends, planner message only), UX-DR35 (Send/Run/Approve visually discontinuous), UX-DR5 (no anthropomorphic waiting), UX-DR24 (no infinite scroll), UX-DR25 (distinct Chat states)
- [Source: ARCHITECTURE-SPINE.md, AD-6 lines 78-82] — accepted messages, agent runs, and progress events commit before acknowledgement; neither process memory nor the stream is authoritative
- [Source: ARCHITECTURE-SPINE.md, AD-7 lines 84-130] — the closed `AgentRun` graph whose initial state is `agent_queued`, and the complete status vocabulary Task 3's CHECK constraint pins
- [Source: ARCHITECTURE-SPINE.md, AD-20 lines 204-208, 312-333] — `ActivityItemV1` and `PersistedEventV1` required shapes; the eight activity discriminants; the `schema_version` normative minimum
- [Source: ARCHITECTURE-SPINE.md, AD-21 line 214] — `PersistedEventV1` carries `stream_id`, **decimal** `sequence`, `event_type`, `occurred_at`, `resource_version`, correlation IDs, one typed payload; SSE `id` is `<stream_uuid>:<sequence>`
- [Source: ARCHITECTURE-SPINE.md, AD-22 line 220] — aggregate ownership (conversation owns messages/agent runs) and the fixed `accept-turn = message + agent-run + event` bundle that repositories may not widen
- [Source: ARCHITECTURE-SPINE.md, AD-23 line 226] — forced RLS on every tenant table, transaction-local trusted site context, NOINHERIT/NOSUPERUSER/NOBYPASSRLS runtime roles
- [Source: ARCHITECTURE-SPINE.md, AD-8 lines 132-136] — idempotency keys bound to FR-12/16/18/19, **not** FR-4 (Decision 4's evidence)
- [Source: ARCHITECTURE-SPINE.md, AD-4 line 70] — "The MVP contains no scenario-source mutation command, route, tool, or UI control" (Decision 1's evidence)
- [Source: ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md, *Interaction Primitives → Keyboard and focus*] — the composer contract quoted verbatim in Task 9
- [Source: EXPERIENCE.md, *State Patterns* → Chat row] — restore-timeline skeleton, new-conversation prompt without fabricated history, message-send failure retains draft text
- [Source: backend/tests/test_gate_a_mutation_audit.py:25-36] — `test_gate_a_scenario_openapi_surface_is_get_only`, the assertion Decision 1 is built around
- [Source: frontend/src/test/scenarioDataBoundaries.test.ts] — the frontend mutation audit's exact directory scope, and why `features/chat/` must stay outside it
- [Source: backend/api/main.py:159-237, 250-265] — the existing `/api/v1` session + CSRF middleware, `allow_methods=["GET","POST"]`, and the `include_router` block Task 6 appends to
- [Source: backend/api/deps.py:129-154] — `get_site_context`: `app.site_id` + `SET LOCAL ROLE shiftmind_runtime`, the sole supported site-scoped transaction
- [Source: backend/migrations/versions/5e2a4c9d1f70_add_seeded_site_identity.py:166-208] — the RLS policy, grant, and role pattern Task 3 mirrors
- [Source: backend/migrations/versions/d128d081ab48_establish_governed_fixture_history.py:249-274] — the per-table RLS loop and the `GRANT SELECT, INSERT` / `REVOKE UPDATE, DELETE` treatment of `scenario_version`
- [Source: backend/adapters/postgres/schema.py:87-88, 119-131] — the composite `(id, site_id)` unique + FK pattern that makes cross-site references structurally impossible
- [Source: backend/application/ports/scenario_projection.py:104] — `connection: Any`, the AD-1-clean port shape to copy
- [Source: backend/application/ports/scenario_catalogue.py:9] — `from sqlalchemy import Connection`, the pre-existing AD-1 leak **not** to copy and not to fix here
- [Source: backend/application/contracts/agent_runtime.py:19-23] — Story 2.1's explicit hand-off of `ActivityItemV1` to this story and `PersistedEventV1` to Story 2.4
- [Source: frontend/src/api/client.ts:11-31] — the single `openapi-fetch` client and its existing `X-CSRF-Token` middleware
- [Source: frontend/src/App.tsx] — the route tree; `ScenarioChat` is already the workspace index route, so Task 10 changes no routing
- [Source: _bmad-output/implementation-artifacts/deferred-work.md, 2026-08-10 story-2-1 block] — the `translate.py` deserialization item named for this story, and the `create_agent_runtime()` incompleteness
- [Source: _bmad-output/implementation-artifacts/2-1-establish-the-owned-agent-runtime-boundary.md] — the decision-recording, halt-rule, and anti-pattern conventions this story follows
- [Source: docs/EVIDENCE-CONVENTION.md; .claude/CLAUDE.md] — commit → measure on a clean tree → generate → commit evidence separately
- [Source: /tanstack/query v5_84_1 docs — guides/mutations.md, guides/invalidations-from-mutations.md] — `isPending`, object-form `invalidateQueries`, and the "wrap `mutate` in your own submit handler" rule quoted in *Latest technical information*

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Debug Log References

- Re-derived baseline before implementation: backend 510 passed / 7 deselected; frontend 50 files / 287 tests. (An earlier note recorded 516; that figure came from a different selection and did not reconcile with the 510 → 523 delta the evidence file records.)
- Final clean-tree measurement at implementation commit `b05f81f`: backend 523 passed / 7 deselected; frontend 52 files / 294 tests; Playwright 46 passed.

### Completion Notes List

- Added four FORCE-RLS governed tables with composite site-bound foreign keys, decimal per-stream sequences, closed agent-run statuses, and least-privilege grants. Alembic downgrade → upgrade → check completed with zero diff.
- Added atomic accept-turn persistence, bounded ordered timeline reads, server-owned correlation context, and cross-site absence-equivalent behavior. Concurrent turns produced unique sequences; injected failure left no partial bundle.
- Added four `/api/v1/conversations` methods, generated typed clients, and Chat UI with stable-ID deduplication, literal queued status, command-key submission, in-flight disabling, and success-only draft clearing.
- The tracked `scenario_catalogue` SQLAlchemy leak remains open by design. No agent execution, SSE, idempotency keys, app-wide correlation middleware, or reserved activity payload shapes were added; forbidden seams retain a zero-line diff.
- Gate A was generated from clean-tree JUnit measurements and remains `gate_a_passed: true`; evidence commit: `742370d`.

**Code review follow-up (2026-08-11).** All 27 patch findings applied in `ab78996`; Gate A rebound on a clean tree in `02b468e`, still `gate_a_passed: true`. Final measurement: backend **545 passed / 7 deselected**; frontend **54 files / 307 tests**; Playwright **46 passed**; `alembic check` zero diff after a full downgrade → upgrade round trip.

- The version pin was the substantive defect. `create()` resolved the version itself by `imported_at DESC` while `get_scenario_context` resolves by version ordinal — two different rules, so the pinned version could disagree with the one the planner was shown *without any new import*. The client now sends `scenario_version_id` and the server validates it; `ScenarioContextOut` gained the field so it can. This touches a Gate A read model, which is why Gate A was re-measured rather than assumed.
- `PersistedEventV1` was dead code — the write path inserted an untyped dict, the read path rehydrated one. Both sides now go through the envelope, which also gave the timeline its `sequence` without widening `ActivityItemV1` with a field AD-21 assigns to the event.
- The `after_message` seam is gone from the port, use case and adapter. Atomicity is now proven by monkeypatching a private helper and letting `engine.begin()` roll back exactly as `get_site_context` does, with all four tables asserted; a separate test drives `uq_persisted_event_stream_sequence` directly, since the advisory-locked path could never reach it.
- Migration `a4f92d7c8e31` was **edited in place**, not superseded, because the story is unmerged. Any checkout holding the previous revision must `alembic downgrade 5e2a4c9d1f70 && alembic upgrade head`.
- One review finding was deferred: UX-DR35's Send/Run/Approve visual discontinuity, which cannot be expressed while Chat ships no Run or Approve control. Recorded in `deferred-work.md` and owned by the first story to ship one.
- The `scenario_catalogue` SQLAlchemy leak remains open by design and is now allow-listed as a greppable data entry rather than docstring prose, with a guard test that fails if the leak is fixed without closing the ledger item.

### File List

- `_bmad-output/implementation-artifacts/2-3-create-and-revisit-durable-conversations.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `backend/adapters/postgres/conversation.py`, `backend/adapters/postgres/schema.py`
- `backend/api/deps.py`, `backend/api/main.py`, `backend/api/routers/conversations.py`, `backend/api/schemas.py`
- `backend/application/contracts/activity.py`, `backend/application/contracts/persisted_event.py`
- `backend/application/ports/conversation.py`, `backend/application/use_cases/__init__.py`, `backend/application/use_cases/accept_turn.py`
- `backend/migrations/versions/a4f92d7c8e31_add_durable_conversations.py`
- `backend/tests/architecture/test_conversation_boundaries.py`, `backend/tests/test_conversation_contracts.py`, `backend/tests/test_conversations_postgres.py`
- `backend/tests/test_evidence_binding.py`, `backend/tests/test_postgres_schema.py`
- `evidence/story-1.11/gate-a-readiness-report.json`
- `frontend/openapi.json`, `frontend/src/api/conversations.ts`, `frontend/src/api/schema.d.ts`
- `frontend/src/features/chat/ActivityTimeline.test.tsx`, `frontend/src/features/chat/ActivityTimeline.tsx`, `frontend/src/features/chat/ChatView.tsx`
- `frontend/src/features/chat/Composer.test.tsx`, `frontend/src/features/chat/Composer.tsx`, `frontend/src/features/chat/ConversationList.tsx`
- `frontend/src/hooks/useConversationTimeline.ts`, `frontend/src/hooks/useConversations.ts`, `frontend/src/hooks/useSendMessage.ts`
- `frontend/src/routes/ScenarioChat.tsx`

## Change Log

| Date | Change |
|---|---|
| 2026-08-11 | Code review run (three layers). 27 patch findings applied in `ab78996`, Gate A rebound in `02b468e`, one finding deferred. Story moved to done. |
| 2026-08-10 | Implemented durable conversations end to end and moved the story to review; all regression, migration, and Gate A gates are green. |
| 2026-08-10 | Story created. Four creation-time decisions recorded: conversation routes mount at `/api/v1/conversations` rather than under the GET-only `/api/v1/scenarios` Gate A surface; this story accepts and persists a turn but does not execute the agent; `ActivityItemV1`/`PersistedEventV1` contracts and their write/read sides are owned here while Story 2.4 owns the SSE transport; and no idempotency key is built, because AD-8 does not bind FR-4. |
