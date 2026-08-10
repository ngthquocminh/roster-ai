---
baseline_commit: 5ce7d1b1a2000371139338f03a27bb13dd727f45
---

# Story 2.3: Create and Revisit Durable Conversations

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want my conversations and accepted turns to survive reconnects,
So that I can investigate a fixture without losing or duplicating the decision context.

**This is the first planner-visible Epic 2 feature**, and the first story in the repository that **writes to governed PostgreSQL from a request**. Everything before it was read-only by construction (Gate A / AD-4). That single fact is the source of most of the traps below.

**Stories 2.1 and 2.2 are its foundation, not its subject.** `AgentRuntime`, its owned contracts, and the `backend/agent/` adapter exist and are green. This story *persists conversations*; it does not modify that seam and does not run the agent (see Decision 2).

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

- [ ] **Task 1: Define the two owned contracts** (AC: #1, #2)
  - [ ] `backend/application/contracts/activity.py` — `ActivityItemV1`. Required shape per AD-20: common activity ID, discriminant, aggregate refs/versions, occurred time; the `planner_message` variant adds message ID + text.
  - [ ] Declare the discriminant as a closed `Literal` of **exactly** these eight, spelled as `snake_case`: `planner_message`, `agent_response`, `clarification`, `draft`, `run_progress`, `comparison`, `approval_request`, `terminal_outcome`. Implement the payload for `planner_message` only; the other seven are reserved names, not shipped shapes.
  - [ ] `backend/application/contracts/persisted_event.py` — `PersistedEventV1`. Required shape per AD-21: `stream_id`, decimal `sequence`, `event_type`, `occurred_at`, `resource_version`, correlation IDs, and exactly one typed `ActivityItemV1` payload.
  - [ ] Every contract carries `schema_version` (spine, *Normative contract minimums*). Frozen dataclasses, `V1` suffix — mirror `application/contracts/evidence_ref.py` and `agent_runtime.py`, which are the two established examples.
  - [ ] **Acceptance boundary:** a contract test asserts the discriminant `Literal` has exactly eight members and that constructing `PersistedEventV1` without a payload is impossible.

- [ ] **Task 2: The `sequence` is decimal, and it is serialized as a string** (AC: #1, #2)
  - [ ] AD-21 says **decimal** `sequence`, not integer. Use PostgreSQL `NUMERIC` (SQLAlchemy `Numeric`, `asdecimal=True` → Python `Decimal`). **Do not use `bigint`** — AD-21 is normative and Story 2.4 builds `Last-Event-ID` replay directly on this column.
  - [ ] **Serialize `sequence` as a JSON string in every API response.** A JSON number becomes an IEEE-754 double in the browser; AD-21's SSE ID format is `<stream_uuid>:<sequence>`, so a value that round-trips through a float has already broken Story 2.4 before it starts. This is the single most likely silent defect in this story.
  - [ ] Allocate the sequence **inside** the accept-turn transaction, monotonically per stream, with a database `UNIQUE (stream_id, sequence)` constraint backing it. Do not allocate in Python from a prior `SELECT MAX(...)` read outside the transaction.
  - [ ] `stream_id` for a conversation stream **is the conversation's own UUID**. Record this so Story 2.4 does not invent a second stream identifier.
  - [ ] **Acceptance boundary:** a test asserts the serialized `sequence` is a JSON string, and a test asserts two concurrent accept-turns on one conversation cannot produce the same sequence (the unique constraint must be the thing that proves it).

- [ ] **Task 3: The migration — the first governed write surface** (AC: #1)
  - [ ] One Alembic revision with `down_revision = "5e2a4c9d1f70"` (current head; `alembic check` must show zero diff afterwards). Four tables: `conversation`, `message`, `agent_run`, `persisted_event`.
  - [ ] Follow `5e2a4c9d1f70_add_seeded_site_identity.py` exactly for structure, and `d128d081ab48`'s loop for RLS. Every table: `site_id` column, `ENABLE` **and** `FORCE ROW LEVEL SECURITY`, plus a `<table>_site_isolation` policy with both `USING` and `WITH CHECK` on `site_id = NULLIF(current_setting('app.site_id', true), '')::uuid` (AD-23).
  - [ ] Use the composite `(id, site_id)` unique-constraint + composite-FK pattern from `adapters/postgres/schema.py:87-88,119-131` so a cross-site foreign key is **structurally impossible**, not merely policy-prevented.
  - [ ] `conversation` pins `scenario_id` **and** `scenario_version_id` at creation (AD-4/AD-9: the version a conversation reasons about must not drift), and carries `resource_version bigint NOT NULL DEFAULT 1` (spine: *mutable aggregates carry monotonic `bigint` versions*).
  - [ ] `agent_run.status` gets a `CHECK` constraint over AD-7's **complete closed** vocabulary — `agent_queued`, `agent_running`, `approval_required`, `agent_completed`, `agent_timed_out`, `agent_cancelled`, `agent_failed` — even though this story only ever writes `agent_queued`. AD-7 is the only legal status graph; fixing it here stops a later story inventing a parallel vocabulary.
  - [ ] **Grants: least privilege, this story's writes only.** `GRANT SELECT, INSERT` on all four tables to `shiftmind_runtime`; `GRANT UPDATE (resource_version)` on `conversation` alone (Task 4 bumps it); `REVOKE UPDATE, DELETE` everywhere else — mirroring `d128d081ab48`'s treatment of `scenario_version`. Epic 3 will need `UPDATE` on `agent_run` to advance the state machine; **it is that story's job to grant it**, not this one's to grant it early.
  - [ ] Write a real `downgrade()` that reverses grants, policies, and tables in order — both existing migrations do, and `alembic check` is part of the gate.
  - [ ] **Acceptance boundary:** `alembic upgrade head` then `downgrade` then `upgrade` succeeds against the Docker PostgreSQL 18 service, and `alembic check` reports zero diff.

- [ ] **Task 4: The accept-turn use case — one transaction, one bundle** (AC: #1)
  - [ ] `backend/application/use_cases/accept_turn.py` (new package `backend/application/use_cases/`, per AR26's `application/  # use cases, policy, state machines, ports, DTOs`). **Do not add this to `backend/services/`** — that is the legacy seam AD-1 permits to remain but not to grow.
  - [ ] The bundle is fixed by AD-22 and may not be widened: **message + agent-run + event**, committed together, plus the `conversation.resource_version` bump. Nothing else. No audit envelope, no evidence snapshot, no job row — those belong to their own owners and none is required by an AC here.
  - [ ] Everything trusted comes from server state: `actor_id` and `site_id` from `ResolvedSession` (via `get_site_context`), `scenario_version_id` re-resolved from the conversation row. **Nothing authority-bearing is read from the request body** (AD-2, AD-15). The body carries the message text and, on create, a `scenario_id` — both of which are *inputs to be validated*, never authority.
  - [ ] Correlation IDs: generate a server-side `request_id` (UUID) in the use case and persist it on the event alongside `conversation_id`, `agent_run_id`, `site_id`, `actor_id` (spine, *Correlation* row). **Do not build app-wide correlation middleware** — the repo has none, `api/problems.py` carries no correlation ID today, and closing that AD-13 gap globally is not this story's scope. Note it in completion notes.
  - [ ] **Atomicity must be proven by a failure, not asserted by a comment.** Write a test that injects a failure *after* the message insert and *before* the event insert, and assert that zero rows from the bundle survive.
  - [ ] **Acceptance boundary:** the injected-failure test leaves no partial bundle, and a successful accept-turn writes exactly one row to each of `message`, `agent_run`, `persisted_event` and bumps `conversation.resource_version` by one.

- [ ] **Task 5: The port and the PostgreSQL adapter** (AC: #1, #2)
  - [ ] `backend/application/ports/conversation.py` — a `Protocol` plus frozen-dataclass DTOs.
  - [ ] **Copy `application/ports/scenario_projection.py`, not `application/ports/scenario_catalogue.py`.** The projection port types its connection parameter as `connection: Any` (`scenario_projection.py:104`), keeping SQLAlchemy out of the application layer per AD-1. The older catalogue port does `from sqlalchemy import Connection` (`scenario_catalogue.py:9`) — a real, pre-existing AD-1 leak. **Do not copy it, and do not fix it here** (it is Gate A code and out of scope); Task 11 pins the new port against repeating it.
  - [ ] `backend/adapters/postgres/conversation.py` — SQLAlchemy Core against the Task 3 tables, driven by the `Connection` yielded by `get_site_context`. That dependency already does `SET LOCAL ROLE shiftmind_runtime` and sets `app.site_id`; **do not open a second engine or connection** — the RLS context lives on that transaction and nowhere else.
  - [ ] Timeline read: ordered by `sequence` ascending, returning `ActivityItemV1[]` derived from `persisted_event` rows, plus the conversation's `resource_version` and its latest agent-run status. Deterministic stable ordering, no `LIMIT`-less unbounded scan of an unbounded table — bound the window and say so in the response (AD-4's ordering discipline, UX-DR24's no-infinite-scroll rule).
  - [ ] **Acceptance boundary:** a `@pytest.mark.postgres` test proves a Site B session cannot read or insert into a Site A conversation, and that the denial is indistinguishable from absence (AD-3's non-disclosure rule; the same shape as `test_scenario_projection.py`'s existing cross-site cases).

- [ ] **Task 6: The API router** (AC: #1, #2)
  - [ ] `backend/api/routers/conversations.py`, mounted at `/api/v1` per **Decision 1**. Model the file on `api/routers/scenario_projection.py`: `APIRouter(prefix=…, tags=…)`, `Depends(get_site_context)`, `_PROBLEM_RESPONSES` declaring `ProblemDetailsV1` for the error statuses, explicit response models in `api/schemas.py`.
  - [ ] The four endpoints from Decision 1. `POST` returns `201` with the created resource; the message command returns the accepted activity item and the conversation's new `resource_version`.
  - [ ] Errors are RFC 7807 via `api/problems.py` (AD-13). A conversation belonging to another site returns the **same** shape as one that does not exist. Unknown `scenario_id` on create → `404`, not `422`.
  - [ ] **CSRF and session already work — do not rebuild them.** `api/main.py:180-237`'s middleware authenticates every `/api/v1` path and enforces same-origin + `X-CSRF-Token` on `POST`. `CORSMiddleware` already lists `POST` (`api/main.py:253`). The frontend client already attaches the header (`frontend/src/api/client.ts:17-25`). Your job is to *use* this, and to prove it: a `POST` with no CSRF header must return `403 csrf_validation_failed`.
  - [ ] **Acceptance boundary:** OpenAPI shows the four paths with the intended methods; the CSRF-less `POST` returns 403; and `test_gate_a_mutation_audit.py::test_gate_a_scenario_openapi_surface_is_get_only` is still green, unmodified.

- [ ] **Task 7: Regenerate the client contract** (AC: #2, #3)
  - [ ] `npm run codegen` from `frontend/` (runs `scripts/export_openapi.py` then `openapi-typescript`). **Never hand-edit `frontend/src/api/schema.d.ts`.**
  - [ ] `frontend/src/api/conversations.ts` — thin typed wrappers over the single shared `client`, deriving every request/response type from `paths[…]`, exactly like `api/scenarioProjection.ts`. Throw `{ ...error, status: response.status }` on failure, matching the established shape that `lib/errors.ts:getErrorStatus` consumes.
  - [ ] **Acceptance boundary:** `npm run typecheck` passes with zero hand-authored request/response interfaces in the new client module.

- [ ] **Task 8: Hooks and the timeline** (AC: #2)
  - [ ] `frontend/src/hooks/useConversations.ts`, `useConversationTimeline.ts`, `useSendMessage.ts` — thin TanStack Query wrappers, no business logic, matching `useScenarioProjection.ts`.
  - [ ] `useSendMessage` is the repo's **first mutation**. `onSuccess` → `queryClient.invalidateQueries({ queryKey: [...] })` for the timeline and conversation list. Query keys are cross-plan contracts; name them deliberately.
  - [ ] `frontend/src/features/chat/` — `ChatView`, `ConversationList`, `ActivityTimeline`, `Composer`. Reuse the existing primitives rather than inventing new ones: `EmptyState`, `InlineAlert`, `StatusBadge`, `Skeleton`, and `ReconnectBanner` all exist in `components/primitives/` from Story 1.6 and were built for exactly these states.
  - [ ] **Deduplicate by activity identity, not by array position** (UX-DR6, AC2). Key the rendered list on the activity ID; a re-fetch that returns an already-rendered activity must not produce a second card. Prove it with a test that feeds the same activity twice.
  - [ ] Empty conversation renders EXPERIENCE.md's required copy shape: *"New conversation prompt with example scope, not fabricated history"* — no invented prior turns.
  - [ ] **Acceptance boundary:** a test renders a timeline, re-delivers an identical activity item, and asserts exactly one visible card; a second test asserts reload reconstructs the same ordered activity IDs.

- [ ] **Task 9: The composer** (AC: #3)
  - [ ] Verbatim from EXPERIENCE.md's *Keyboard and focus* section: *"`Enter` inserts a new line; `Ctrl+Enter` / `Command+Enter` sends. The visible Send button is always available when sending is valid. Sending never triggers Run optimization or approval."* Handle **both** `ctrlKey` and `metaKey`.
  - [ ] Multiline `<textarea>`, not an `<input>`. A plain `<form onSubmit>` around a textarea would submit on Enter — that is precisely the behavior AC3 forbids.
  - [ ] **Recoverable failure retains the draft.** Clear the textarea on *success only* — never in the submit handler, never optimistically. `ConstraintInput.tsx`'s existing comment records this exact lesson from the legacy UI: clear on the success condition, not on HTTP 200.
  - [ ] Disable Send while `mutation.isPending` (this is also Decision 4's double-submit answer).
  - [ ] **UX-DR35: Send must be visually discontinuous from Run optimization and Approve.** No shared "AI action" button treatment spanning authority levels. This story ships only Send; do not add a disabled Run or Approve control "for later".
  - [ ] **Acceptance boundary:** four tests — Enter inserts a newline and does not submit; Ctrl+Enter and Cmd+Enter each submit; the Send button submits; a rejected mutation leaves the draft text in the textarea.

- [ ] **Task 10: Wire the route** (AC: #2, #3)
  - [ ] Replace `frontend/src/routes/ScenarioChat.tsx`'s `WorkspaceTabPlaceholder` with the real `ChatView`. The route already exists as the workspace index route (`App.tsx`); `WorkspaceTabs.tsx` already links to it. **No routing change is needed** — do not restructure the route tree.
  - [ ] Take `scenarioId` from `useParams` as it does today, and the pinned version context from the existing `ScenarioVersionContext` / `useScenarioContext` rather than re-fetching it.
  - [ ] **Acceptance boundary:** the existing workspace and router tests stay green, and a route test deep-links to `/scenarios/:id` and renders Chat.

- [ ] **Task 11: Make the new boundary executable** (AC: #1)
  - [ ] Extend `backend/tests/architecture/test_agent_runtime_boundaries.py` (or add a sibling in the same package) to assert the **new** application-layer modules — `application/contracts/activity.py`, `contracts/persisted_event.py`, `ports/conversation.py`, `use_cases/**` — import neither `sqlalchemy` nor `fastapi`.
  - [ ] Scope the new guard to those modules with an explicit, **documented** allow-list entry for the known `application/ports/scenario_catalogue.py` leak. A guard that lies about its own coverage is exactly the defect the Story 2.1 review fixed in this file's docstring (`deferred-work.md`, 2026-08-10) — state precisely what is and is not covered.
  - [ ] In the allow-list entry's comment, cite `deferred-work.md`'s *"Deferred from: story-2-3 creation (2026-08-10)"* item, which tracks the leak, records the three fix tiers, and names deleting this entry as its definition of done. A suppression with no ticket behind it becomes permanent.
  - [ ] **Acceptance boundary:** the guard **fails** when temporarily given a real `from sqlalchemy import Connection` in `ports/conversation.py`, and passes on the shipped tree. Demonstrate both — a guard nobody has seen go red is a guard nobody has tested.

- [ ] **Task 12: Full regression gate** (AC: #1, #2, #3)
  - [ ] Backend: `uv run --frozen pytest`; `uv run --frozen pytest -m postgres` (Docker PostgreSQL 18 via `docker-compose.yml`); `alembic check` zero diff.
  - [ ] Frontend: `npm run codegen`, `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`, `npm run test:e2e`.
  - [ ] **Re-run Gate A and report by name.** AR28 binds this story hard: it is the first to add a write path, and `gate_a_passed` must still read `true`. Regenerate `evidence/story-1.11/gate-a-readiness-report.json` per `docs/EVIDENCE-CONVENTION.md` — **commit code first, measure on a clean tree, generate through `backend/scripts/evidence_binding.py`, commit evidence separately.** Never hand-type it.
  - [ ] **Re-derive baselines at the start rather than trusting these.** Recorded after Story 2.1 (`0091dcf`): backend **485 passed / 1 self-skip on a dirty tree**; postgres **27**; frontend **50 files / 287 tests**; e2e **46**; alembic zero diff. Story 2.2 is landing in parallel and will move the backend count — re-derive, do not assume.
  - [ ] **Acceptance boundary:** every suite green at its re-derived baseline plus this story's new tests, and Gate A still `true`.

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

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List

## Change Log

| Date | Change |
|---|---|
| 2026-08-10 | Story created. Four creation-time decisions recorded: conversation routes mount at `/api/v1/conversations` rather than under the GET-only `/api/v1/scenarios` Gate A surface; this story accepts and persists a turn but does not execute the agent; `ActivityItemV1`/`PersistedEventV1` contracts and their write/read sides are owned here while Story 2.4 owns the SSE transport; and no idempotency key is built, because AD-8 does not bind FR-4. |
