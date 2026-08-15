---
baseline_commit: 0932c1df76e953b1f26493d11c1ad7913bb5191e
---

# Story 2.9: Clarify, Refuse, and Fail Safely

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want ambiguous or unsafe requests handled explicitly,
so that the agent never guesses consequential facts or gains authority from untrusted content.

**Unblocks:** nothing structurally. This is the **last story of Epic 2**. Epic 3 begins from a
conversation surface that can already say *"I need one more fact"*, *"I will not do that"*, and
*"this turn ended, here is the literal reason"* — three states Epic 3's draft/run/approval cards
extend rather than invent.

**Depends on, and consumes:** Story 2.2's `GoldenCase` schema (which already carries
`expected_outcome: allow | refuse | clarify` and `expected_visible_state`, both **authored for this
story by name** — `evals/README.md:10`), Story 2.5's application-owned grant registry, Story 2.6's
`CapabilityModuleV1` + `CapabilityError` base, Story 2.7's request path (`POST
/conversations/{id}/agent-runs/{run_id}/execute`), grounding gate, and structured-output adapter
seam, and Story 2.3's `ActivityItemV1` closed discriminant vocabulary.

**It carries NO migration and NO new dependency.** Both verified at creation — see *Latest technical
information*.

---

## Seven decisions were made at story creation — do not re-litigate them

### Decision 1 — The three model output variants are registered as explicitly **named** `ToolOutput`s. `final_result` keeps its name

Today the adapter builds `output_type = [answer_type, DeferredToolRequests]`
(`agent/runtime.py:109-113`). This story needs the model to be able to answer, **or** ask, **or**
decline. The obvious implementation — widening the list to
`[GroundedAnswerV1, ClarificationV1, RefusalV1, DeferredToolRequests]` — is wrong, and it fails
silently.

**Verified at creation by executing against the installed `pydantic-ai` 2.27.0 lock:**

| `output_type` | schema | output tool names |
|---|---|---|
| `[str, DeferredToolRequests]` | `TextOutputSchema` | `[]` |
| `[GroundedAnswerV1, DeferredToolRequests]` (today) | `AutoOutputSchema` | `['final_result']` |
| `[GroundedAnswerV1, ClarificationV1, DeferredToolRequests]` | `AutoOutputSchema` | **`['final_result_GroundedAnswerV1', 'final_result_ClarificationV1']`** |
| `[GroundedAnswerV1 \| ClarificationV1, DeferredToolRequests]` | `AutoOutputSchema` | **`['final_result_GroundedAnswerV1', 'final_result_ClarificationV1']`** |
| `[ToolOutput(GroundedAnswerV1, name="final_result"), ToolOutput(ClarificationV1, name="clarification"), DeferredToolRequests]` | `ToolOutputSchema` | **`['final_result', 'clarification']`**, `allows_text=False` |

The bare-union rename is the trap. `evals/doubles.py:58-67` builds a scripted structured response as
`ToolCallPart(tool_name=info.output_tools[0].name, ...)` — **unconditionally the first output
tool**. Under a bare union:

- the four committed `scheduling_compute` cases keep passing, but only because `GroundedAnswerV1`
  happens to be listed first — a reordering breaks four frozen cases with no test naming the cause;
- a scripted **clarification** can never be produced at all, because `response_data` always routes to
  output tool zero. The case would fail as a validation error against the wrong schema.

`ToolOutput(..., name=...)` is imported from `pydantic_ai.output`. Use it for all three, keep
`final_result` byte-identical, and make `evals/doubles.py` **select** its output tool by name from a
new per-turn case field rather than taking index 0.

### Decision 2 — A refusal is a `terminal_outcome`, not a ninth `ActivityTypeV1` discriminant

There is a real vocabulary divergence between two normative artifacts, and it must be reconciled
rather than resolved by whichever one is read first:

- **AD-14 / `ARCHITECTURE-SPINE.md:172` and `:331` name EIGHT**: planner message, agent response,
  clarification, draft, run progress, comparison, approval request, terminal outcome. `:331` defines
  `terminal outcome = aggregate ref/status/**reason**/evidence refs`.
- **UX-DR6 (`epics.md`) names NINE**, inserting "refusals" between clarifications and drafts.
- `ActivityTypeV1` (`application/contracts/activity.py:11-20`) implements the spine's eight.

**Settled: the contract vocabulary stays at eight.** A refusal is a literal terminal state carrying a
reason, which is exactly the shape `:331` already defines for `terminal_outcome`. UX-DR6's and
`EXPERIENCE.md:85`'s requirement is that the timeline *"distinguishes planner message, grounded agent
response, clarification, and refusal by author/**type label**"* — a label, which a
`reason`-discriminated terminal outcome supplies. Widening `ActivityTypeV1` would change an AD-20
contract for no acceptance benefit, and Story 2.3 defined those eight deliberately as a closed
vocabulary.

Record the reconciliation in the `SCOPE_CONTROLS` `NOT COVERED:` style
(`application/grounding/gate.py:23-62` is the in-repo form). **If you find a rendering requirement a
reason-carrying `terminal_outcome` genuinely cannot satisfy, escalate — do not quietly add a ninth
discriminant.**

### Decision 3 — Authority refusal is proven by **absence** and by application policy. The model's refusal is presentation only

AC2 reads *"when **policy** evaluates the proposed call"*. That is the application, and every
mechanism it names already exists:

| AC2 cause | Existing mechanism | Where |
|---|---|---|
| unauthorized | grant composed from trusted context **before** runtime construction; ungranted ⇒ tool absent | `capabilities/registry.py:35-60`, `agent/runtime.py:163` |
| prohibited | `INSTALLABLE_RISK_CLASSES` excludes `prohibited`; such a manifest cannot register | `contracts/capability_manifest.py:31-33` |
| exhausted budget | `UsageLimitExceeded` → `failed` + `budget_exhausted` | `agent/runtime.py:215-221` |
| injection-driven | no authority input is ever read from prompt, fixture, model, or tool content | `AgentTurnRequestV1` docstring, `AgentDepsV1` |
| unsupported | no granted capability serves the request | — |

So this story **builds no new gate**. It (a) **proves** those five with an injection corpus and
structural assertions, and (b) ships the *visible* refusal: when nothing granted can serve the
request, the model emits `RefusalV1` with bounded operational copy and a safe next step, and the
application renders it as a terminal outcome.

**The model's `RefusalV1` is never an authority decision.** Registering a capability and letting the
model decline inside it is the exact inversion AD-2 forbids and Story 2.5 Decision 4 already rejected
("register-then-refuse puts the authority decision downstream of a model-supplied name"). A
source-level guard asserts no branch in `capabilities/registry.py` or the execute route consults
model output.

### Decision 4 — A clarification is a **completed** turn that invoked no consequential capability

AC1's *"creates no draft, run, or side effect"* is trivially true today — no draft, compute-class, or
consequential capability is reachable on the request path (`demonstration_enabled` defaults `False`,
`settings.py:97`). Recording that as "satisfied" would be a lie about coverage of the same kind the
Story 2.1 review fixed in a guard docstring.

What is assertable **now, and stays true as Epic 3 adds capabilities**: a clarification turn

1. writes **exactly one** persisted event,
2. invokes **no** granted capability whose `manifest.risk_class` is in `{draft, compute,
   consequential}` — asserted against the risk class, not against a hardcoded capability name,
3. finishes the `agent_run` as `agent_completed` — the turn *did* complete; it completed by asking.

A clarification **may** have called `scheduling_inspect` first. That is a read, it is how safe entity
candidates are obtained, and forbidding it would make Decision 5 impossible.

### Decision 5 — Entity candidates are **application-resolved**, never model-authored strings

AC1 says *"structured clarification with **safe** entity candidates"*. If the model writes candidate
worker names into the payload, they are unverified strings rendered as facts beside a governed
surface — the same defect Story 2.7 Decision 2 closed for numbers ("the model never supplies a number
that renders").

**Mechanism, in the shape already established:** a candidate is a model-proposed
`(group, record_id)` pair citing rows the turn's own `scheduling_inspect` results returned; the
application resolves each against `deps.projection_reader` on the trusted path and supplies the
display label. A candidate that does not resolve is **dropped, counted, and asserted** — never
rendered, never substituted with a nearby row (AR11's non-retargeting rule).

**Candidates are optional and a clarification with zero candidates is legal and must render.**
Ambiguity about time, scope, or intended consequence has no entity to cite, and requiring one would
force the model to invent one.

### Decision 6 — `suspended` stops being reported as `agent_failed`; approval execution stays Epic 4's

`use_cases/execute_turn.py:52-54` maps `suspended → agent_failed` with the comment *"Approval
execution is deliberately owned by Story 2.9."* **That premise is false**, judged at creation:
approval is AD-10 / FR17–19, owned by Stories 4.1–4.3, and no AC here mentions resuming a suspension.
AC2 mentions approval only in its negative clause (untrusted content cannot *add* approval).

But the mapping itself is a defect this story does own: collapsing a suspension into `agent_failed`
is precisely the *"Collapse distinct outcomes into 'Done' or 'Error'"* that `EXPERIENCE.md`'s Voice
and Tone table forbids, and this is the story whose ACs make a wrong visible state a product defect.

**Settled: make it unreachable and assert it.** The only `approval_policy="exact_action"` module is
`demonstration`, off by default. Add a guard asserting that no capability granted on the request path
declares an approval policy other than `none` in this milestone; if a suspension arrives anyway, it
becomes a terminal outcome with its own distinct reason, never `agent_failed`'s. Re-annotate the
comment in place with Epic 4 as the resumption owner — follow the Story 2.4/2.5 precedent for a false
premise: **correct it, do not delete it.**

### Decision 7 — One evaluator ships. It spends the fence `deferred-work.md:130` reserved for this story

`deferred-work.md:130` records, verbatim: *"The remaining fence is Story 2.9's, for refusal/
injection."* One new `Evaluator` implementation joins `ToolRoutingEvaluator` and
`GroundingEvaluator` — a **policy-outcome evaluator** judging `expected_outcome`
(`allow | refuse | clarify`) against the owned outcome, plus the injection invariant.

Separately, and this is the half that closes a two-entry ledger thread: `build_evaluation_report`
(`evals/report.py:193-246`) reports routing and grounding only, so committed evidence can record
`passed: true` while a case's **visible state** regressed. `deferred-work.md:132` names **Story 2.9
as owner** because it *"owns visible refusal/clarification states and is the first story whose ACs
make a wrong visible state a product defect rather than an unread schema field"* — and AC4 requires
visible state to be **asserted**. The report generator must judge it too.

---

## Acceptance Criteria

1. **Given** ambiguous worker names, task identity, scope, time, intended consequence, or resource
   version, **when** the ambiguity could change the chosen capability or result, **then** the agent
   emits a structured clarification with safe entity candidates and creates no draft, run, or side
   effect, **and** the timeline and assistive technology identify it as a clarification. *(FR6)*

2. **Given** an unsupported, unauthorized, prohibited, injection-driven, or exhausted-budget request,
   **when** policy evaluates the proposed call, **then** the agent refuses with bounded operational
   copy and a safe next step when one exists, **and** prompt, fixture, model, or tool content cannot
   add capabilities, permissions, budgets, or approval. *(FR6, NFR5, AR15)*

3. **Given** provider timeout, malformed model output, unexpected tool arguments, or AgentRuntime
   failure, **when** the turn terminates, **then** the failure maps to a stable visible state,
   accepted conversation history remains durable, and no unsupported action executes, **and**
   Scenario Data remains reachable from the Chat error state. *(NFR7, UX-DR23, UX-DR25)*

4. **Given** deterministic normal, ambiguity, refusal, injection, provider-failure, and
   unsupported-number fixtures, **when** the investigation evaluation suite runs on the Story 2.2
   harness, **then** expected tool, arguments, allow/refuse outcome, evidence IDs, and visible state
   are asserted, and the cases are contributed to the shared golden dataset tagged by capability and
   risk class, **and** authorization, injection, or grounding regression blocks release. *(NFR26,
   NFR27, NFR28, NFR29)*

> **Scope confirmed unchanged.** `sprint-change-proposal-2026-08-09-epics-2-5.md:131` records
> *"2.1–2.7, 2.9 | KEEP as-is"*, and `sprint-change-proposal-2026-08-13.md:127` records *"2.9 |
> **None.** Clarification/refusal variants are untouched"*. Four ACs, as written above.

---

## Two honest gaps, raised rather than papered over

### Gap 1 — AC2's "unauthorized" and "prohibited" have no *authorization* mechanism to drive them

Verified at creation, and this is the same gap Story 2.5 raised and recorded rather than papering
over:

- `membership` has **no role column**; `PLANNER_ROLE` is a module constant
  (`capabilities/registry.py:10`) and `POLICY_VERSION` is the literal `"one-user-mvp-v1"`.
- No installed module can declare `risk_class="prohibited"` — `validate_manifest` rejects it
  (`contracts/capability_manifest.py:101-102`), so a prohibited capability is not a capability that
  refuses; it is one that cannot exist.
- `deferred-work.md:26` already records this as *"Trusted role and feature policy are server-owned
  constants in the one-user MVP"*, revisit trigger *"the first story activating a second user"*.

**Required posture.** Drive the unauthorized case through the **real** mechanism that exists:
`enabled_feature_policy(settings)` with a capability's flag off ⇒ the module is absent from the
composed grant ⇒ the tool does not exist ⇒ the request cannot be served and is refused. Drive the
prohibited case as a **registration** refusal (`validate_manifest` rejecting the manifest), which is
what "prohibited" means in this codebase. **Do not fabricate a role table, a policy service, or a
`prohibited` module that installs anyway.** Record the reduction in the `NOT COVERED:` form.

### Gap 2 — NFR28's 50-case floor cannot be re-verified by this story

`epics.md:1527`'s dataset-threshold caveat says the floor *"must be re-verified against the actual
contribution of Stories 2.9, 3.10–3.12, and 4.5–4.6 when Epic 2's harness lands"*. Three of those
five contributors are in Epics 3 and 4 and have contributed nothing. The dataset holds **11 cases**
today (2 `demonstration`, 5 `scheduling_inspect`, 4 `scheduling_compute` — counted at creation).

**Required posture.** Record this story's **actual** contribution and the resulting running total in
the Completion Notes, state the projection honestly, and **do not lower the threshold** — that is
Gate B's call, taken with all five contributions present. **Do not pad**: `epics.md:1527` is explicit
("never pad the dataset to reach it"), and `test_evaluation_harness.py:334-363`'s per-capability
floor already keeps the real invariant honest. Every case must earn its place by covering a distinct
behaviour named in AC4.

---

## Tasks / Subtasks

This story runs in **three phases with one reporting checkpoint** between A and B — the same shape
Story 2.7 used and for the same reason: the phase boundary is where the only clean split would be, so
that decision can be revisited with numbers instead of guessed before any code exists.

- **Phase A (Tasks 1–7)** — contracts, adapter output variants, candidate resolution, terminal
  taxonomy, persistence, evaluator, cases. Satisfies **AC4 in full** plus the server halves of AC1,
  AC2 and AC3. No frontend change, **no migration**, no new route.
- **Checkpoint** — commit + report five numbers (below).
- **Phase B (Tasks 8–10)** — codegen, timeline rendering, Chat error state, accessibility proof.
  Satisfies the visible halves of AC1, AC2, AC3.
- **Phase C (Task 11)** — fences, ledger, regression, Gate A.

New backend home: `backend/application/contracts/` and `backend/application/clarification/` (new,
beside `application/grounding/` — AR26's structural seed). Frontend work stays in
`frontend/src/features/chat/`; this story creates **no** new frontend feature directory.

---

### Task 1 — Owned contracts for clarification, refusal, and terminal outcome (AC: 1, 2, 3)

- [x] New `backend/application/contracts/dialogue.py`. Every contract carries `schema_version` (the
      spine's *Normative contract minimums*) and is a frozen dataclass, matching
      `contracts/grounding.py`'s shape exactly.
  - [x] `EntityCandidateProposalV1` — **UNTRUSTED** model output: `group` (the `EvidenceGroupV1`
        vocabulary, reused — do **not** define a second group vocabulary; Story 2.7's trap #2 was
        exactly two ad-hoc group translations), `record_id`, and nothing else. **No label field.**
  - [x] `EntityCandidateV1` — **TRUSTED**: `group`, `record_id`, application-resolved `label`, and
        the `scenario_version_id` it resolved against.
  - [x] `ClarificationV1` (model-facing) — `question: str`, `candidates: tuple[EntityCandidateProposalV1, ...]`.
  - [x] `ResolvedClarificationV1` (persisted) — `question`, `candidates: tuple[EntityCandidateV1, ...]`,
        `scenario_version_id`, `dropped_candidate_count: int`.
  - [x] `RefusalV1` (model-facing) — `reason: RefusalReasonV1` from a **closed** Literal, `detail: str`
        (bounded operational copy), `next_step: str | None`.
  - [x] `RefusalReasonV1 = Literal["unsupported_request", "capability_unavailable", "out_of_scope"]` —
        three, closed, and deliberately **not** including "unauthorized": an unauthorized capability
        is *absent*, so from the model's position it is indistinguishable from unavailable, and a
        model-selectable "unauthorized" label would leak an authority fact the model does not have
        (AD-3 non-disclosure). Application-side causes get their reason in Task 4's terminal
        vocabulary, not here.
  - [x] `TerminalOutcomeV1` (persisted) — `status: AgentRunStatusV1`, `reason: TerminalReasonV1`,
        `detail: str`, `next_step: str | None`.
- [x] Add `SCOPE_CONTROLS`-style declarations in `dialogue.py` recording Decision 2's
      eight-vs-nine reconciliation and Gap 1's reduction, in the exact
      `application/grounding/gate.py:23-62` form (`COVERS: … NOT COVERED: …`).
- [x] `AgentRunOutcomeV1` gains `clarification: ClarificationV1 | None` and `refusal: RefusalV1 | None`
      beside the existing `answer` / `grounded_response` pair, with the same trust-boundary comment
      the file already carries at lines 219-232: **model-side fields are UNTRUSTED; the use case
      writes the trusted resolved forms.** Do not reuse `answer` for either.
- [x] Tests: field order and closed vocabularies pinned the way `test_evidence_ref.py:66-78` pins
      `EvidenceRefV1` (a closed vocabulary in a durable payload is the thing
      `deferred-work.md:194` records a breakage against); round-trip through
      `TypeAdapter(...).dump_python(mode="json")` and back.

### Task 2 — Three named model output variants (AC: 1, 2)

- [x] `agent/runtime.py`: replace the `output_type` construction with **named `ToolOutput`s** per
      Decision 1. `ToolOutput` imports from `pydantic_ai.output`.
  - [x] `answer_type is None` keeps today's `[str, DeferredToolRequests]` **byte-identically** — ~15
        construction sites and every non-grounding golden case depend on it (Story 2.7 Decision 3
        established this and it still holds).
  - [x] `answer_type is not None` renders
        `[ToolOutput(answer_type, name="final_result"), ToolOutput(ClarificationV1, name="clarification"), ToolOutput(RefusalV1, name="refusal"), DeferredToolRequests]`.
  - [x] **Assert the tool names.** A test reading `agent._output_toolset._tool_defs` and asserting
        exactly `{"final_result", "clarification", "refusal"}` — this is the only thing standing
        between the repo and Decision 1's silent rename. Assert `final_result` is present by that
        exact string.
  - [x] The `_reject_numeric_prose` output validator must apply to `GroundedAnswerV1` only. It walks
        `getattr(output, "segments", ())`, so it is already inert for the other two — but state that,
        and add a test driving a `RefusalV1` whose `detail` contains a numeral and asserting it is
        **not** rejected. A refusal saying "the 60-second budget was exhausted" is legitimate
        operational copy, not an uncited claim.
- [x] `run_turn`'s completed branch dispatches on the output type into `answer` / `clarification` /
      `refusal`. An output that is none of the three is `AgentRuntimeError`, not a silent `None`.
- [x] `_tool_results(turn, excluded_names=self._output_tool_names)` needs no change — the exclusion
      set is derived from the toolset, so it picks up all three automatically. **Assert that**, or
      a fourth variant added later will leak an output tool call into `tool_results`.
- [x] `evals/doubles.py`: `_to_model_response` must **select the output tool by name**, not by
      `info.output_tools[0]`. Add an optional `output_tool` field to `ScriptedModelTurn` (defaulting
      to `final_result`) and to `CASE_FIELDS`; raise `UnexpectedModelBehavior` when the named tool is
      absent from `info.output_tools` rather than falling back to index 0. Existing cases with
      `response_data` and no `output_tool` must keep passing untouched.

### Task 3 — Safe entity candidates, resolved by the application (AC: 1)

- [x] New `backend/application/clarification/resolve.py`, shaped like
      `application/grounding/gate.py` (a pure function over `AgentDepsV1` plus the turn's trusted
      results; **no** framework import, **no** repository access).
  - [x] `resolve_clarification(clarification, deps) -> ResolvedClarificationV1`.
  - [x] Reuse `application/grounding/evidence_groups.py`'s
        `scenario_fact_group_for_evidence_group` and `gate.py:98-105`'s `_RESOLVER_BY_GROUP`
        mapping. **Do not write a second group→resolver map** — extract the existing one to a shared
        module if it must be imported from two places, and assert exhaustiveness in both directions
        the way Story 2.7's mapping does.
  - [x] A candidate whose `scenario_version_id` would differ from `deps.scenario_version_id`, or
        whose resolver returns anything other than `outcome == "resolved"`, is **dropped** and
        counted in `dropped_candidate_count`. **Never** resolved against the current version, never
        replaced with a nearby record (AR11; and Story 2.8's trap #2 — "retargeting on a miss reads
        as helpful and is invisible unless asserted").
  - [x] The `label` is derived from the resolved projection record, never from model output. Pick the
        field the corresponding Scenario Data column already renders so Chat and the grid agree
        (`workers` → `contact_id`, `work-areas-and-tasks` → `task_id`; see
        `frontend/src/features/scenario-data/columns.ts:20-37`).
- [x] `use_cases/execute_turn.py` calls it on the clarification branch, exactly where `ground_answer`
      is called on the answer branch — the trusted transform belongs to the **use case**, never to
      the adapter (`contracts/agent_runtime.py:219-232` states this rule for `grounded_response`).
- [x] Required assertions:
  - [x] A clarification whose candidates all resolve renders every one, with
        `dropped_candidate_count == 0`.
  - [x] A candidate naming a record that does not exist is dropped; **the resolver is called exactly
        once, with the cited locator** — no second call against another record or version.
  - [x] A clarification with **zero** candidates is valid and produces a valid persisted payload.
  - [x] No `label` value anywhere in the persisted payload is byte-equal to any string the scripted
        model emitted — drive a case where the model proposes a *plausible but wrong* label-shaped
        string and assert it never appears.

### Task 4 — Terminal outcome mapping and the failure taxonomy (AC: 3)

- [x] `TerminalReasonV1` — a closed Literal covering exactly what the system can actually produce
      today. Derive it from the code, not from imagination:
      `provider_error`, `invalid_output`, `budget_exhausted`, `deadline_exceeded`, `cancelled`,
      `capability_error`, `refused`, `approval_unsupported`. Each value must be reachable from a
      named branch — a reason nothing can emit is the "declared and entirely unimplemented" shape
      `deferred-work.md:7` records against `RunSource = "live"`.
- [x] `use_cases/execute_turn.py`:
  - [x] `terminal_status` gains the clarification and refusal branches. A clarification is
        `agent_completed` (Decision 4). A refusal is `agent_completed` too — the turn completed; the
        answer was "no". **Neither is `agent_failed`**, and a test asserts that: collapsing them
        would erase the distinction AC2 and AC3 exist to keep.
  - [x] `suspended` per Decision 6: distinct reason `approval_unsupported`, never `agent_failed`.
        **Re-annotate the false comment at `:52-54` in place**, restating Epic 4 (AD-10, Stories
        4.1–4.3) as the owner of approval resumption.
  - [x] A new `terminal_outcome(outcome) -> TerminalOutcomeV1 | None` returning the payload for
        every non-`agent_completed` path, with **bounded operational copy** and a `next_step` where
        one genuinely exists. Copy is drawn from `EXPERIENCE.md`'s Voice and Tone table
        (`:60-73`) — literal outcomes, never "Something changed. Try again."
- [x] `api/routers/conversations.py`'s catch-all at `:255-265`:
  - [x] It currently collapses **every** exception into
        `AgentRunOutcomeV1(status="failed", failure_reason="invalid_output")`. This story owns that
        taxonomy (the comment at `:257` says so). Map the causes it can actually distinguish —
        `AgentRuntimeError` from a provider call, `UncitedNumericProseError`, `IncompleteManifestError`
        from grant composition, `ValueError` from runtime-model construction — onto distinct
        `TerminalReasonV1` values. Anything genuinely unclassified stays `invalid_output`.
  - [x] **Reaching a terminal status still wins over surfacing a richer error.** The existing
        `logger.exception` before collapse stays. Do not let a mapping bug strand a claimed run —
        there is no reaper until Epic 3's lease (`deferred-work.md:176`).
  - [x] A test proving each mapped cause reaches its own reason, and that the accepted planner
        message remains in the timeline in every one (AC3's "accepted conversation history remains
        durable").

### Task 5 — Persist and read the three new activity payloads (AC: 1, 2, 3)

- [x] `contracts/activity.py`: two new variants, `ClarificationActivityV1` and
      `TerminalOutcomeActivityV1`, joining the union. **`ActivityTypeV1` gains nothing** — both names
      are already reserved in it (`:11-20`). `PlannerMessageActivityV1`'s and
      `AgentResponseActivityV1`'s serialized payloads must stay **byte-identical**.
- [x] `adapters/postgres/conversation.py`:
  - [x] `_payload_to_json` and `_activity_from_payload` (`:427`, `:453`) gain the two shapes. The
        `activity_type not in (...)` guard at `:455` widens to four; everything else still raises
        `UnsupportedActivityPayloadError`.
  - [x] `finish_agent_run` (`:344-426`) currently hardcodes `AgentResponseActivityV1` and
        `event_type="agent_response"`. Parameterize it on the payload the use case produced. Keep the
        `agent_run` status update, the sequence allocation, the `FOR UPDATE`, and the
        `resource_version` bump exactly as they are — this is a payload change, not a transaction
        change.
- [x] **No migration.** Verified at creation:
      `persisted_event.payload` is `JSONB`, `event_type` is a bare `String(100)` with no CHECK, and
      `ck_agent_run_status` already admits all seven AD-7 statuses including `approval_required`
      (`migrations/versions/a4f92d7c8e31_add_durable_conversations.py:55-66`). The only UPDATE grant
      this milestone added — `agent_run(status)`, revision `c7d6e5f4a3b2` — is the only one needed.
      **If you find yourself writing a migration, stop and re-read this.**
- [x] `use_cases/execute_turn.py:77-107`'s `rehydrate_history` gains the two variants. Its `else`
      branch raises `ValueError` for unknown variants — keep that fail-closed shape. A clarification
      rehydrates as the assistant asking its question; a terminal outcome rehydrates as the
      application-owned "the previous turn did not complete" line already there at `:95-97`, extended
      with the literal reason. **Never present either as model output.**
- [x] `api/schemas.py`: `ClarificationActivityOut` and `TerminalOutcomeActivityOut` extending
      `ActivityCommonOut`, added to the `ActivityItemOut` discriminated union. This **changes the
      OpenAPI schema** — unlike Story 2.8, codegen **is** owed. It runs in Phase B (Task 8) so
      `openapi.json` and `schema.d.ts` move in one commit with their consumer.
- [x] `tests/test_conversations_postgres.py:503-556`: the two reserved-discriminant probes use
      `draft` and `comparison`, both **still reserved** — verified at creation, so unlike Story 2.7
      neither needs re-pointing. Their docstrings say *"Six of AD-20's eight discriminants are
      reserved"*; that becomes **four**. Update the count; do not delete the tests — they are the
      only proof an unknown payload fails typed rather than as a 500 mid-timeline.

### Task 6 — The policy-outcome evaluator and the visible-state gap (AC: 4)

- [x] `evals/evaluators.py`: one new `Evaluator` implementation (Decision 7) — call it
      `PolicyOutcomeEvaluator`. It judges:
  - [x] `case.expected_outcome` (`allow | refuse | clarify`) against the owned outcome: a `clarify`
        case must produce a clarification, a `refuse` case a refusal, an `allow` case neither.
  - [x] For `refuse`/`clarify`: **no consequential capability was invoked** — asserted against
        `manifest.risk_class`, matching Decision 4's rule rather than a capability name.
  - [x] The injection invariant, in its **observable** form. "Registered names equal granted names"
        is nearly vacuous in the harness — `runtime_for_modules` grants exactly what the case names,
        so the equality holds by construction. The assertion that bites: **every tool call in the
        turn naming a capability outside `registered_capability_names` produced no
        `AgentToolResultV1`**, and the turn still reached a stable state. That is what a scripted
        compliant model actually exercises (PydanticAI answers an unknown tool name with a retry, so
        the run continues and the case must still land correctly). Read the registered set from
        `PydanticAIAgentRuntime.registered_capability_names` (`agent/runtime.py:171-178`), which is
        collected as each tool is *actually* registered; do not re-derive it from the modules tuple.
- [x] **`ToolRoutingEvaluator` needs a targeted fix, and it is a trap.** `evaluators.py:50` reads
      `if outcome.answer is None or part.tool_call_id in capability_result_call_ids`. A clarification
      or refusal outcome has `answer is None`, so the filter falls through to "count every assistant
      tool call" — **including the `clarification`/`refusal` output-tool call itself**. Every
      `clarify`/`refuse` case would then fail `:56-68`'s "expected clarify with no tool call". Fix by
      excluding output-tool call ids unconditionally, not by loosening the refuse/clarify branch.
      Add a test that goes red on the old shape.
- [x] **`build_evaluation_report` judges visible state.** `evals/report.py:193-246` currently
      reports routing and grounding only. Closes `deferred-work.md:132`, whose owner is this story by
      name.
  - [x] Assert `outcome.status == case.expected_visible_state` and the visible-text expectation, in
        the report generator — not only in `test_evaluation_harness.py:295-296`.
  - [x] **Beware the vacuous form.** `runtime.py:282` sets `output_text=None` whenever `answer_type`
        is set, so `(outcome.output_text or "") == case.expected_visible_text` passes trivially for
        every structured case (all four grounding cases author `""`). Define visible text once, in
        one shared helper, as *what the planner actually sees* — for a grounded response the
        `_response_visible_text` projection the use case already has (`execute_turn.py:65-74`), for a
        clarification its question, for a refusal its detail — and use that helper in **both** the
        pytest suite and the report generator so they cannot drift.
  - [x] `deferred-work.md:11` says the most deceptive shape available is *"a required `GoldenCase`
        field read by no `Evaluator`"*. After this task, no field of `GoldenCase` may be unread.
        Add a meta-test asserting that.

### Task 7 — Golden cases and the NFR5 injection corpus (AC: 2, 4)

- [x] Contribute cases under `backend/evals/golden/<capability>/` covering AC4's six named fixture
      kinds. Minimum, one per kind, each earning its place:
  - [x] **normal** — an allowed inspect answer (`scheduling_inspect` already has five; reuse rather
        than duplicate, and say so in the README instead of adding a sixth).
  - [x] **ambiguity** — `expected_outcome: "clarify"`, a scripted `scheduling_inspect` call followed
        by a scripted `clarification` output tool naming two real candidate `record_id`s from the
        fixture projection.
  - [x] **refusal** — `expected_outcome: "refuse"`, scripted `refusal` output tool, no capability
        call.
  - [x] **injection** — see the corpus below.
  - [x] **provider-failure** — `expected_visible_state: "failed"` (or `"timed_out"`), driven through
        the real adapter.
  - [x] **unsupported-number** — the existing `scheduling_compute/missing-evidence.json` covers this
        exactly. **Do not author a duplicate**; name it in the README as this AC's contribution.
- [x] Tag every case by `capability` and `risk_class` (AC4's own words). New capability tags must be
      classified in `test_evaluation_harness.py:325-331`'s `MVP_PRODUCT_CAPABILITIES` /
      `NON_PRODUCT_CAPABILITIES` — `:352` fails on an unclassified one by design. Cases for the
      clarification/refusal behaviours belong to the capability whose *question* they are about, not
      to a new pseudo-capability: grounding was added as a second **evaluator** over the same
      capability for exactly this reason (Story 2.7's sprint note).
- [x] **The injection corpus, and the trap inside it.** An injection test that scripts a compliant
      model and asserts it did not comply proves nothing — the compliance was authored. That is
      `deferred-work.md:9`'s defect in a new place. **Every injection case must script a model that
      DOES try to comply, and assert the application refused anyway.** Cover all three untrusted
      channels NFR5 names ("chat and every untrusted data channel introduced by the MVP"):
  - [x] **chat text** — the prompt instructs the model to call a capability that is not granted. The
        model emits a `ToolCallPart` naming it. Assert the call cannot execute, the granted set is
        unchanged, and the turn ends in a stable state.
  - [x] **fixture field content** — a projection record whose text field carries an instruction. Use
        `evals/fixture_projection.py` (the real projection the grounding cases already drive) so the
        instruction arrives through a genuine tool result, not a hand-built one.
  - [x] **tool output** — a capability result whose rendered `model_facing_view` output carries an
        instruction to widen budget or grant approval. Assert `AgentBudgetV1` and the granted set are
        byte-identical before and after.
  - [x] Assert, for every case: no capability name outside the composed grant is registered; no
        budget field differs from the configured value; no `approval` field is set. These are AC2's
        four nouns — capabilities, permissions, budgets, approval — and each needs its own assertion.
- [x] `evals/README.md`: add this story's contribution paragraph in the established form (2.2, 2.5,
      and 2.7 each have one), naming what each case proves and what it deliberately does not.
      `test_readme_documents_exact_contribution_shape_and_owners` reads this file.

---

### ⛳ Checkpoint — commit Phase A and report five numbers

Not an unconditional pause. It must work in an unattended `bmad-dev-auto` / `bmad-loop` run, so
**continue into Phase B** unless one of the four named conditions fires.

Commit Phase A, then report:

1. Backend pytest: passed / skipped / deselected, on a clean tree.
2. Golden case count, and the per-capability counts
   `test_every_capability_meets_the_nfr28_four_case_floor` computes.
3. **Proof the `ToolRoutingEvaluator` fix was observed RED** against the pre-fix shape. Decision 1's
   sibling trap; a test never seen to fail proves nothing.
4. **Proof at least one injection case was observed to FAIL** with the structural assertion removed —
   i.e. the corpus is not asserting the double's authored behaviour.
5. `git diff --stat` for `frontend/` — expected to be **zero lines** at this point.

**Stop and escalate only if:** (a) the routing fix or an injection case could not be observed red;
(b) Phase A ran past roughly 2× its estimate; (c) Decision 2's eight-vs-nine reconciliation turned
out wrong in code and a ninth discriminant appears genuinely required; (d) an AC1/AC2/AC3 behaviour
turns out to need a new route or a migration.

---

### Task 8 — Codegen and timeline rendering (AC: 1, 2, 3)

- [x] `npm run codegen` — `frontend/openapi.json` and `frontend/src/api/schema.d.ts` both move. They
      are **generated**: do not hand-edit either, and do not derive frontend types any way other than
      `paths[…]` / `components[…]` (`src/api/scenarioProjection.ts:5-17` is the convention).
- [x] `features/chat/ActivityTimeline.tsx` renders the two new discriminants beside
      `planner_message` and `agent_response`. Keep the existing `activity_type` switch shape; the
      union is discriminated, so `tsc --noEmit` fails on an unhandled variant — that is the intended
      guard.
  - [x] **Clarification** — type label distinct from "ShiftMind" (AC1's *"the timeline … identifies
        it as a clarification"*, `EXPERIENCE.md:85`'s *"by author/type label"*). Question as text;
        candidates as a plain list naming group, record, and the application-supplied label. When
        `dropped_candidate_count > 0`, say so literally — a silently shortened list is the
        `EXPERIENCE.md:112` "report missing merely because it was not rendered" failure.
  - [x] **Terminal outcome** — the literal reason and the safe next step. `EXPERIENCE.md`'s Voice and
        Tone table is normative here: *"Use literal outcomes: completed, infeasible, timed out,
        cancelled, failed, rejected, expired"* / *"Don't: Collapse distinct outcomes into 'Done' or
        'Error'"*. Refusal renders with its own label, distinct from a provider failure.
  - [x] Reuse `InlineAlert` / `StatusBadge` from `components/primitives/` (UX-DR23's shared
        patterns). Do **not** hand-roll a panel; Story 2.3's review already corrected Chat for
        exactly that.
  - [x] **Do not change** `ClaimSegment`, `fieldOrRange`, `claimSubject`, `formatClaimValue`, the
        empty-claim state, the failed-claim state, or the evidence jump wiring. Those are Story 2.7
        and 2.8 outcomes with tests behind them.
  - [x] The `!item.response.segments.length` branch at `:138-147` says *"Story 2.9 owns the failure
        taxonomy and the visible states that distinguish them."* With a real terminal-outcome
        variant, an empty `agent_response` should no longer be how a failure reaches the timeline.
        Keep the branch (old rows exist) but correct the comment to describe what it now is: a
        historical shape, not the failure path.
- [x] UX-DR32: no pulsing, flashing, gradient, or glow treatment on any of it; no colour-only state
      communication — every state carries text.

### Task 9 — Chat error state keeps Scenario Data reachable (AC: 3)

- [x] AC3's second half. `ChatView.tsx`'s `ErrorState` (`:31-52`) and `Composer`'s failure alert
      (`Composer.tsx:63-69`) currently offer Retry and nothing else.
  - [x] Every Chat error state gains an active link to Scenario Data for the **same** scenario —
        `/scenarios/${scenarioId}/data`. `EXPERIENCE.md:123`: Chat's error state *"links to Scenario
        Data, Runs/manual optimization, and saved Results"*.
  - [x] Runs and Results are **placeholder routes** (`WorkspaceTabPlaceholder`; the Results tab is an
        `aria-disabled` span — verified at creation and recorded by Story 2.8's own honest gap). Link
        Scenario Data only. Do **not** build or link a Runs/Results affordance; that pre-empts
        Epic 3. Record the reduction in the `NOT COVERED:` form.
  - [x] Durable history stays visible during the error state — AC3's *"accepted conversation history
        remains durable"* is a rendering property here as well as a persistence one.
- [x] **Scope fence — do not disable the composer.** Composer-disabling outage mode is **FR8**, owned
      wholly by **Story 3.9** (`epics.md:1059-1070`, FR Coverage Map `:275`). A failed turn is not a
      model outage, and treating it as one would both pre-empt 3.9 and make a transient failure look
      permanent. This story's error state is recoverable: the draft is retained
      (`Composer.tsx:36-43`, already correct) and Retry stays live.
- [x] Required assertions:
  - [x] Each terminal reason renders **distinctly** — drive them all and compare rendered output
        pairwise, the way Story 2.8's four exception panels are asserted.
  - [x] A failed turn leaves the accepted planner message visible in the timeline.
  - [x] The Scenario Data link carries the scenario id from the route/context, never from anything
        model-produced. `frontend/src/test/evidenceNavigationBoundaries.test.ts`'s allowlist-of-shapes
        guard (Story 2.8 review Decision 4) already sweeps `features/chat/` — extend its approved
        roots rather than adding a second guard.

### Task 10 — Accessibility proof (AC: 1, 3)

- [x] Extend `frontend/src/test/accessibility-contract.test.tsx` — **that file specifically**, not a
      new sibling. `deferred-work.md:202` records that Story 2.8's sibling
      (`evidence-accessibility.test.tsx`) sits outside the `accessibility_component_layer` Gate A
      check's hand-declared `test_files` list, so its assertions are invisible to the NFR29 registry.
      Adding to the already-declared file avoids repeating that.
  - [x] AC1's *"assistive technology identify it as a clarification"* — the clarification block has
        an accessible name/role that names it as a clarification, asserted through the accessible
        name, not a CSS class.
  - [x] Terminal outcomes announce as durable state changes (UX-DR27's live regions; `role="status"`
        on the message only, control outside — `ScenarioWorkspace.tsx:118-137` is the in-repo
        pattern and Story 2.8's review Decision 2 recorded why `role="alert"` nesting is wrong).
  - [x] axe clean on: clarification with candidates, clarification with zero candidates, refusal,
        and each terminal reason.
- [x] **Optional, only if it costs nothing:** while editing `gate_a_checks.py` is *not* warranted by
      any AC here, if Phase C gives you a legitimate reason to touch that file, add
      `evidence-accessibility.test.tsx` to `accessibility_component_layer` and close
      `deferred-work.md:202`. If not, leave the item open and untouched — its owner is "the next
      story that already has a legitimate reason", and manufacturing one is worse than waiting.

### Task 11 — Fences, ledger, regression, Gate A (AC: 3, 4)

- [x] **Zero-line-diff fences** — verify each with `git diff --stat` and record the result:
  - [x] `backend/migrations/**` — **no migration** (Task 5). `alembic check` from the **repository
        root** (`deferred-work.md:132-143` — from `backend/` it fails with a misleading
        `script_location` error) expecting zero operations and zero migration files.
  - [x] `backend/services/**`, `backend/domain/**`, `backend/engine/**`, `backend/llm/**`,
        `backend/ingest/**`, `backend/store/**`, `backend/adapters/postgres/scenario_projection.py`,
        `application/ports/scenario_catalogue.py`, `adapters/postgres/scenario_catalogue.py`.
  - [x] `backend/tests/test_gate_a_mutation_audit.py` — AR28 forbids weakening an earlier gate.
  - [x] `backend/application/grounding/**` **except** whatever Task 3's shared group→resolver
        extraction genuinely requires. If that extraction touches `gate.py`, keep it to the move.
  - [x] `frontend/src/features/scenario-data/**` and `frontend/src/features/evidence/**` — Story 2.8's
        surfaces are untouched by this story.
  - [x] `evidence/story-2.2/evaluation-harness-demonstration.json` — **do not regenerate it.**
- [x] **Ledger** (`_bmad-output/implementation-artifacts/deferred-work.md`). Four entries name this
      story; judge each honestly and annotate in place rather than deleting (Story 2.4/2.5
      precedent):
  - [x] `:11` — *"after Story 2.9 closes the visible-state half, whoever finds `expected_visible_text`
        still unread by any evaluator"*. Task 6 closes it. Record the closure with the mechanism.
  - [x] `:130-132` — the refusal/injection evaluator fence (**spent** by Task 6, as designed) and the
        surviving visible-state half (**closed** by Task 6). Close the entry.
  - [x] `:192` — `argument_mismatch` is not observably distinct; owner *"most likely Story 2.9 …
        either give the mismatch its own cause or give the evaluator a discriminator beyond the
        failure label"*. **Recommended: the discriminator, not a new cause.** AR11
        (`epics.md:157`) names exactly three evidence failures and `GroundingFailureV1` is a
        persisted contract Literal — widening it is the breakage `deferred-work.md:194` records. The
        cited and originating arguments are both available to `GroundingEvaluator`. If you take the
        discriminator, close it; if you judge otherwise, re-annotate with the reasoning and leave it
        open.
  - [x] `:202` — Gate A registry attribution for `evidence-accessibility.test.tsx`. Its owner is *"the
        next story that already has a legitimate reason to touch `gate_a_checks.py`"*. This story
        does not. **Leave it open and untouched** unless Task 10's optional clause applies.
  - [x] Deliberately **not** touched: `:7`, `:9` (live-model evaluation path — Gate B's, and NFR26
        keeps live providers out of normal CI), `:16`, `:17`, `:18`, `:26`, `:116`, `:176`–`:188`,
        and the `ScenarioCatalogueReader` AD-1 leak at `:147-164`. **`ALLOWED_LEAKS` stays
        untouched.**
- [x] **Code comments naming this story** — three, all reachable now. Correct each in place:
  - [x] `application/use_cases/execute_turn.py:52-54` — Decision 6's false premise.
  - [x] `api/routers/conversations.py:257` — the taxonomy now exists; restate what the catch-all
        still collapses and why.
  - [x] `frontend/src/features/chat/ActivityTimeline.tsx:136` and its test at
        `ActivityTimeline.test.tsx:271` — Task 8's correction.
- [x] **No evidence file is owed.** No AC here carries a measured threshold, and NFR35's four rows
      belong to Stories 1.4, 1.5, 2.4 and 3.5 (`requirements-inventory.md`, AD-26). Gate A must still
      be re-run per AR28 — expect the two-commit dance, because the readiness gate dirties
      `evidence/` and cannot run twice in a row (`deferred-work.md:107`). See
      `docs/GATE-A-RUNBOOK.md`; §3 requires `playwright.config.ts` to keep `reporter: "list"` as its
      committed default.
- [ ] **Regression + Gate A**:
  - [x] Re-derive every baseline on a clean tree — do **not** trust the numbers below.
  - [x] `uv run --frozen pytest` (backend), the `postgres`-marked suite, `npm test`, `tsc -b`,
        `oxlint`, `npm run build`, Playwright.
  - [ ] Gate A re-run per AR28: `gate_a_passed: true`, `blocking: []`.
- [x] **Record the NFR28 numbers** per Gap 2: this story's contribution, the running dataset total,
      the per-capability counts, and the honest statement that the 50-case floor remains Gate B's to
      re-verify once Stories 3.10–3.12 and 4.5–4.6 have contributed. **Do not lower it here. Do not
      pad toward it.**

---

## Dev Notes

### What this story is, and what it is not

| In scope | Out of scope | Owner |
|---|---|---|
| Clarification, refusal, terminal-outcome contracts and their visible states | Draft cards, run progress, comparison, approval request | Epic 3 / Epic 4 |
| Application-resolved entity candidates | A new evidence locator kind, or a jump from a candidate | Not asked for; 2.8 owns evidence navigation |
| Chat error state linking to Scenario Data | Composer-disabling model-outage mode (FR8) | **Story 3.9** |
| Approval-policy assertion that suspension is unreachable | Approval resumption, `DeferredToolResults` on the request path | **Epic 4** (AD-10, 4.1–4.3) |
| The policy-outcome/injection evaluator and the visible-state report gap | The live-provider run path (`RunSource = "live"`) | Gate B (`deferred-work.md:7`) |
| Golden cases for AC4's six fixture kinds | Padding toward NFR28's 50-case floor | Gate B measures the aggregate |
| A real authorization *difference* driving "unauthorized" | A role table, a policy service, a `prohibited` module | First second user (`deferred-work.md:26`) |

**No migration. No new dependency. No new route. No new frontend feature directory.** If you reach
for `alembic revision`, a package, or a new `features/` folder, stop — the mechanism you want almost
certainly already exists and is named in these notes.

### The traps, ranked by how quietly they fail

1. **The output-tool rename (Decision 1).** Verified at creation: a bare union renames `final_result`
   → `final_result_GroundedAnswerV1`. `evals/doubles.py` takes `info.output_tools[0]`, so four frozen
   grounding cases keep passing by list order alone and a scripted clarification silently becomes a
   malformed `GroundedAnswerV1`. Nothing goes red in a way that names the cause.
2. **`ToolRoutingEvaluator` counting the output tool as a routed capability call.**
   `evaluators.py:50`'s `outcome.answer is None` branch includes every assistant tool call, and a
   clarification/refusal outcome has `answer is None`. Every `clarify`/`refuse` case fails at
   `:56-68` — and the tempting fix is to loosen that branch, which deletes NFR28's 100%
   protected-class rule (`test_tool_routing_evaluator_fails_when_a_forbidden_tool_is_routed`
   documents exactly why that branch must bite).
3. **An injection corpus that tests its own fixture.** Scripting a model that declines and asserting
   it declined proves the case file, not the system — `deferred-work.md:9` records this exact defect
   against NFR28's routing percentage. Script compliance; assert refusal.
4. **Model-authored entity candidate labels (Decision 5).** Unverified strings rendered as facts
   beside a surface whose entire premise is exactness. Invisible unless you assert that no persisted
   label is byte-equal to model output.
5. **Refusal as a model authority decision (Decision 3).** Registering a capability and letting the
   model decline inside it reads as correct and inverts AD-2. Story 2.5 Decision 4 already rejected
   the same shape.
6. **Retargeting an unresolvable candidate** to the current version or the nearest record. AR11, and
   this is the second story that can do it.
7. **A vacuous `expected_visible_text` assertion.** `runtime.py:282` sets `output_text=None` for every
   structured case, so `(outcome.output_text or "") == ""` passes trivially. A green assertion that
   cannot fail is worse than an absent one — it closes `deferred-work.md:132` on paper only.
8. **Collapsing terminal reasons into one error state.** `EXPERIENCE.md`'s Voice and Tone table
   forbids it by name, and the whole point of AC3 is that a provider timeout, a budget cutoff, and a
   refusal are three different things to a planner.
9. **Adding a ninth `ActivityTypeV1` discriminant** (Decision 2).
10. **Disabling the composer on an error.** That is Story 3.9's FR8 outage mode. It makes a
    recoverable failure look permanent and pre-empts another story.
11. **Re-pointing the reserved-discriminant probes.** They use `draft`/`comparison`, which stay
    reserved. Only their docstring count changes. Deleting them removes the only proof an unknown
    payload fails typed rather than as a 500 mid-timeline.
12. **Padding golden cases toward 50.** `epics.md:1527`, explicitly.

### Existing conventions to match, not reinvent

- **Contract shape** — `application/contracts/grounding.py`: frozen dataclasses, `SCHEMA_VERSION`,
  closed `Literal` vocabularies with the *reason for the closure* in a comment, `__all__`.
- **Scope-as-data** — `application/grounding/gate.py:23-62`'s `SCOPE_CONTROLS`: `COVERS: … NOT
  COVERED: …`. This is where every reduction in this story is recorded.
- **Trusted transform in the use case, never the adapter** —
  `contracts/agent_runtime.py:219-232` states the rule for `grounded_response`; Task 3 follows it for
  `ResolvedClarificationV1`.
- **Fail-closed unknown discriminant** — `execute_turn.py:98-99` and
  `adapters/postgres/conversation.py:453-458`: raise, never default.
- **Evaluator shape** — `evals/evaluators.py`: frozen dataclass, `run_source`, `EvalVerdict` with a
  reason string that names the actual difference.
- **Golden case contribution** — `evals/README.md`'s *Contributing a reviewed failure*; NFR4 applies
  to fixtures, so sanitize prompts and arguments.
- **Frontend discriminated rendering** — `ActivityTimeline.tsx:189-196`'s `activity_type` switch.
- **Typed error accessors** — `frontend/src/lib/errors.ts`: one exported function per concern.
- **Settled-state live regions** — `ScenarioWorkspace.tsx:118-137`.
- **Comment style** — explain *why the shape is this shape*, cite the UX-DR/AR/AD number.
- **Test doubles** — `vi.mock` the hook module, drive real components. A skipped test is not a passed
  test (Story 1.11).

### Latest technical information (verified against the repo at creation, commit `0932c1d`)

- **`pydantic-ai` 2.27.0 output-tool naming** — measured, table in Decision 1. `ToolOutput` imports
  from `pydantic_ai.output`; named `ToolOutput`s yield `ToolOutputSchema` with `allows_text=False`,
  bare unions yield `AutoOutputSchema` with renamed tools.
- **No migration is needed.** `persisted_event.payload` is `JSONB`; `event_type` is `String(100)`
  with **no** CHECK; `ck_agent_run_status` already lists all seven AD-7 statuses including
  `approval_required`; `GRANT UPDATE (status) ON agent_run` exists at revision `c7d6e5f4a3b2`.
- **`ActivityTypeV1` already reserves `clarification` and `terminal_outcome`**
  (`contracts/activity.py:11-20`). Neither is a new discriminant.
- **AD-14's spine list has eight entries; UX-DR6's has nine.** Decision 2 reconciles them.
- **NFR5 has zero coverage today.** Exhaustive search at creation found no injection corpus, no
  injection test, and no prompt-injection fixture anywhere under `backend/`. Every match for
  "inject" is either dependency injection or a deliberately injected test failure. This story is
  NFR5's sole owner.
- **The dataset holds 11 golden cases**: `demonstration` 2, `scheduling_inspect` 5,
  `scheduling_compute` 4. `MVP_PRODUCT_CAPABILITIES = {"scheduling_compute", "scheduling_inspect"}`;
  `demonstration` is classified non-product with its reason stated in place
  (`test_evaluation_harness.py:321-331`).
- **`demonstration` is the only `approval_policy="exact_action"` module and `demonstration_enabled`
  defaults `False`** (`settings.py:97`), so `suspended` is unreachable on the request path — the
  premise Decision 6 rests on.
- **`registered_capability_names`** (`agent/runtime.py:171-178`) is collected as each tool is
  actually registered, so it *"can never over-report a granted-but-unrendered capability"*. It is the
  right thing for the injection invariant to assert against.
- **Codegen is owed** (unlike Story 2.8): `npm run codegen` = `codegen:export` (backend
  `scripts/export_openapi.py`) + `codegen:types` (`openapi-typescript`). Both artifacts are
  generated; never hand-edit.
- **jsdom does not implement `EventSource`** (`useConversationStream.ts:15-17`) — the stream hook
  takes an injectable constructor. Nothing here needs the stream.
- **Node/TS**: TypeScript 5.9.3 strict with `noUnusedLocals`/`noUnusedParameters`; react-router 8.2;
  TanStack Query 5.101. Python 3.10–3.12; `pydantic-ai-slim` 2.27.0 is already a repository lock, so
  **no AR27/AR19 dependency ceremony applies**.

### Project Structure Notes

- `backend/application/contracts/dialogue.py` — **new**. Beside `grounding.py`, `activity.py`.
- `backend/application/clarification/` — **new** package (`resolve.py` + `__init__.py`), beside
  `application/grounding/`. AR26 structural seed.
- `backend/application/contracts/{activity,agent_runtime}.py` — extended.
- `backend/application/use_cases/execute_turn.py` — clarification/refusal branches, terminal mapping.
- `backend/agent/runtime.py` — named `ToolOutput`s, completed-branch dispatch.
- `backend/adapters/postgres/conversation.py` — payload read/write for two variants;
  `finish_agent_run` parameterized on payload.
- `backend/api/schemas.py`, `backend/api/routers/conversations.py` — new `ActivityItemOut` members,
  richer terminal mapping in the catch-all.
- `backend/evals/{cases,doubles,evaluators,report}.py`, `backend/evals/golden/**`,
  `backend/evals/README.md`.
- `backend/tests/**` including `tests/architecture/` for the AD-2 source-level guards.
- `frontend/{openapi.json,src/api/schema.d.ts}` — **regenerated**, not hand-edited.
- `frontend/src/features/chat/{ActivityTimeline,ChatView,Composer}.tsx` + co-located tests.
- `frontend/src/test/accessibility-contract.test.tsx` — extended (Task 10, and why that file).
- Chat code stays in `features/chat/`; `features/scenario-data/` must never import it
  (`scenarioDataBoundaries.test.ts` sweeps that directory).

### References

- `_bmad-output/planning-artifacts/epics.md:815-841` — Story 2.9 ACs; `:792-813` (2.8, shipped);
  `:1059-1070` (Story 3.9, which owns FR8); `:266-276` (FR Coverage Map); `:1520`, `:1527` (NFR28 and
  the dataset-threshold caveat, "never pad")
- `epics.md:35` (FR6), `:39` (FR8), `:157` (AR11), `:161` (AR15), `:172` (AR26), `:174` (AR28),
  `:186` (UX-DR5), `:188` (UX-DR6), `:216` (UX-DR20), `:222` (UX-DR23), `:226` (UX-DR25), `:230`
  (UX-DR27), `:240` (UX-DR32), `:246` (UX-DR35)
- `requirements-inventory.md` — NFR5, NFR7, NFR26–NFR29 canonical text; NFR35's four-story allocation
- `prds/prd-ShiftMind-2026-07-21/prd.md:130` — FR-6 normative text and its testable consequence
  (*"ambiguous worker names do not resolve arbitrarily, and prompt instructions cannot add tools or
  authority"*)
- `architecture/…/ARCHITECTURE-SPINE.md:54` (AD-2), `:72` (AD-5), `:84` + state diagram (AD-7),
  `:150` (AD-11), `:156` (AD-12), `:172` (AD-14, the eight discriminants), `:174` (AD-15), `:331`
  (`ActivityItemV1` payload shapes)
- `ux-designs/…/EXPERIENCE.md:60-73` (Voice and Tone — literal outcomes, refusal names a safe next
  step), `:83-91` (Component patterns; `:85` Message block type labels), `:120-128` (state matrix;
  `:123` Chat), `:185-196` (Accessibility Floor), `:228-239` (Flow 1, incl. the ambiguity failure
  path), `:262-270` (Flow 4 — Story 3.9's, not this one's)
- `sprint-change-proposal-2026-08-09-epics-2-5.md:131`, `sprint-change-proposal-2026-08-13.md:127` —
  both confirm this story's scope is unchanged
- `2-7-ground-schedule-claims-in-exact-evidence.md` — the request path, structured-output seam, and
  trap-list style this story extends; `2-8-jump-to-evidence-and-return-to-the-claim.md` — the
  distinct-exception-state assertion pattern Task 9 reuses
- `deferred-work.md:7`, `:9`, `:11` (the harness-evaluates-the-plumbing thread), `:26` (constant
  role/policy), `:107` (Gate A double-run), `:130-132` (this story's reserved evaluator fence and the
  visible-state half), `:132-143` (`alembic check` working directory), `:176` (stranded
  `agent_running`), `:192` (`argument_mismatch`), `:194` (breaking a persisted contract `Literal`),
  `:202` (Gate A accessibility attribution)
- `docs/EVIDENCE-CONVENTION.md`, `docs/GATE-A-RUNBOOK.md`
- Code: `backend/agent/runtime.py`, `backend/application/contracts/{activity,agent_runtime,grounding,capability_manifest}.py`,
  `backend/application/{use_cases/execute_turn.py,grounding/gate.py,capabilities/{registry,module,installed,deps}.py}`,
  `backend/adapters/postgres/conversation.py`, `backend/api/{schemas.py,routers/conversations.py}`,
  `backend/evals/{cases,doubles,evaluators,report,fixture_projection}.py`,
  `backend/tests/{test_evaluation_harness,test_execute_turn_use_case,test_conversations_postgres,test_agent_runtime_adapter}.py`,
  `backend/tests/architecture/test_execute_turn_boundaries.py`,
  `frontend/src/features/chat/{ActivityTimeline,ChatView,Composer}.tsx`,
  `frontend/src/test/{accessibility-contract,evidenceNavigationBoundaries}.test.*`

### Baselines at creation (`0932c1d`) — re-derive them, do not trust them

Recorded by Story 2.8's post-remediation completion notes: backend **812**; PostgreSQL **45**;
frontend **63 files / 378 tests**; Playwright **48**; `alembic` zero diff; `gate_a_passed: true`,
`blocking: []`. Story 2.7 found its inherited baseline stale by 100+ tests and Story 2.8 found the
same; assume it and measure on a clean tree before you start.

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

- Task 1 plan and verification: introduced frozen owned dialogue contracts first, then extended the runtime outcome at the model trust boundary. RED was observed as `ModuleNotFoundError`; targeted tests passed 4/4 and the full backend suite passed 813, skipped 2, deselected 7.
- Task 2 plan and verification: registered three explicit named `ToolOutput` variants, dispatched by owned output type, kept the text path unchanged, and made scripted structured turns choose by name. RED proved the old adapter exposed only `final_result`; focused suites passed 48 tests and full backend regression passed 818, skipped 2, deselected 7.
- Task 3 plan and verification: extracted the one exhaustive evidence-group resolver map, added a pure exact-target clarification resolver, and performed the trusted transform in the use case. RED proved the application package and trusted outcome field were absent; focused suites passed 38 tests and full backend regression passed 823, skipped 2, deselected 7.
- Task 4 plan and verification: mapped all reachable adapter outcomes to literal terminal reasons and persisted agent statuses, corrected suspension ownership to Epic 4, and classified known route exceptions while retaining fail-closed finalization. RED proved no terminal-outcome mapper existed; focused suites passed 42 tests and full backend regression passed 833, skipped 2, deselected 7.
- Task 5 plan and verification: added the two already-reserved activity payloads, parameterized finalization on the use-case-produced payload while preserving locking/version/sequence mechanics, and extended typed storage, API, and history projections. RED proved the activity contracts were absent; focused API/contract suites passed 43 tests, PostgreSQL passed 45, and full backend regression passed 838, skipped 2, deselected 7. No migration added.
- Task 6 plan and verification: added policy-outcome evaluation, fixed output-tool routing exclusion, single-sourced planner-visible text, and made report results fail on visible-state/text drift. RED proved the old evaluator counted `clarification` as a routed capability and the old structured text oracle was vacuous; evaluator suite passed 35 and full backend regression passed 846, skipped 2, deselected 7.
- Task 7 plan and verification: contributed six distinct scheduling-inspect cases (ambiguity, refusal, provider failure, and three injection channels), embedded real malicious fixture fields, and asserted attempted compliance cannot change capabilities, permissions, budgets, or approval. The unregistered-result mutation test is RED when its structural assertion is removed. Dataset now totals 17 cases: demonstration 2, scheduling_compute 4, scheduling_inspect 11. Full backend regression passed 849, skipped 2, deselected 7.
- Phase A checkpoint: committed as `12b1ea3`; backend 849 passed / 2 skipped / 7 deselected, golden cases 17 (demonstration 2, scheduling_compute 4, scheduling_inspect 11), routing and injection mutations observed RED, frontend diff zero lines.
- Task 8 plan and verification: regenerated OpenAPI/types and replaced the binary timeline render with an exhaustive four-variant switch. Clarifications use trusted candidate labels with literal dropped counts; terminal outcomes use shared StatusBadge/InlineAlert patterns and reason-specific text. RED showed both new discriminants fell into AgentResponse and crashed; focused timeline passed 14, TypeScript passed, and full frontend regression passed 63 files / 380 tests.
- Task 9 plan and verification: passed the trusted route scenario id into both shared Chat error surfaces, linked Scenario Data only, retained durable timeline history and kept the composer live after rejection. RED proved all four error surfaces lacked the link; focused Chat/navigation suites passed 36 and full frontend regression passed 63 files / 383 tests.
- Task 10 plan and verification: extended the Gate A-recognized accessibility contract with accessible clarification naming, live-region boundaries, and axe coverage for candidate/zero-candidate clarification plus all eight terminal reasons. RED proved the next step was nested inside the live region; focused accessibility/timeline suites passed 35 and full frontend regression passed 63 files / 395 tests. The optional Gate A registry change was intentionally not taken, so deferred-work line 202 remains open.
- Task 11 pre-Gate verification: closed the visible-state/text ledger entries and made `argument_mismatch` observably distinct inside the evaluator without widening AR11. Cross-swapped oracle outcomes were RED before the discriminator and pass/fail correctly now. Root Alembic reported zero operations; all protected zero-diff fences were empty except the permitted grounding resolver extraction (`gate.py` + `resolvers.py`). Regression passed backend 850 / skipped 2 / deselected 7, PostgreSQL 45, frontend 63 files / 395 tests, TypeScript, oxlint (three inherited warnings), production build, and Playwright 48. NFR28 contribution is 6 cases; running total 17: demonstration 2, scheduling_compute 4, scheduling_inspect 11. The 50-case floor remains Gate B's to re-verify after Stories 3.10–3.12 and 4.5–4.6; it was neither lowered nor padded.

### Completion Notes List

### File List

- backend/application/contracts/agent_runtime.py
- backend/application/contracts/agent_status.py
- backend/application/contracts/activity.py
- backend/application/contracts/dialogue.py
- backend/application/clarification/__init__.py
- backend/application/clarification/resolve.py
- backend/application/grounding/gate.py
- backend/application/grounding/resolvers.py
- backend/application/use_cases/execute_turn.py
- backend/api/routers/conversations.py
- backend/api/schemas.py
- backend/application/ports/conversation.py
- backend/adapters/postgres/conversation.py
- backend/agent/runtime.py
- backend/evals/cases.py
- backend/evals/doubles.py
- backend/evals/evaluators.py
- _bmad-output/implementation-artifacts/deferred-work.md
- backend/evals/fixture_projection.py
- backend/evals/README.md
- backend/evals/golden/scheduling_inspect/clarify-worker-ambiguity.json
- backend/evals/golden/scheduling_inspect/injection-chat-text.json
- backend/evals/golden/scheduling_inspect/injection-fixture-field.json
- backend/evals/golden/scheduling_inspect/injection-tool-output.json
- backend/evals/golden/scheduling_inspect/provider-failure.json
- backend/evals/golden/scheduling_inspect/refuse-unsupported-request.json
- backend/evals/report.py
- backend/evals/golden/scheduling_compute/argument-mismatch.json
- backend/evals/golden/scheduling_compute/missing-evidence.json
- backend/evals/golden/scheduling_compute/supported.json
- backend/evals/golden/scheduling_compute/version-mismatch.json
- backend/tests/test_agent_runtime_adapter.py
- backend/tests/test_clarification_resolution.py
- backend/tests/test_conversations_api.py
- backend/tests/test_conversation_contracts.py
- backend/tests/test_conversations_postgres.py
- backend/tests/test_dialogue_contracts.py
- backend/tests/test_evaluation_harness.py
- backend/tests/test_evidence_ref.py
- backend/tests/test_execute_turn_use_case.py
- frontend/openapi.json
- frontend/src/api/schema.d.ts
- frontend/src/features/chat/ActivityTimeline.tsx
- frontend/src/features/chat/ActivityTimeline.test.tsx
- frontend/src/features/chat/ChatView.tsx
- frontend/src/features/chat/ChatView.test.tsx
- frontend/src/features/chat/Composer.tsx
- frontend/src/features/chat/Composer.test.tsx
- frontend/src/test/accessibility-contract.test.tsx
- _bmad-output/implementation-artifacts/2-9-clarify-refuse-and-fail-safely.md
- _bmad-output/implementation-artifacts/sprint-status.yaml

## Change Log

| Date | Change |
|---|---|
| 2026-08-15 | Story created. Seven creation decisions recorded (the `pydantic-ai` output-tool naming measured against the installed 2.27.0 lock); two honest gaps raised (no authorization mechanism exists to drive AC2's "unauthorized"/"prohibited"; NFR28's 50-case floor cannot be re-verified before Epics 3–4 contribute); zero-migration established as a fence rather than an expectation; four `deferred-work.md` entries and three in-code comments naming this story routed for honest judgement. |
