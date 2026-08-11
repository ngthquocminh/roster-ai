---
baseline_commit: f89c92d22ec3569caf16f18b90d2492051fd272b
---

# Story 2.5: Inspect Scenario Facts Through a Governed Capability

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want the agent to inspect the same authorized scenario facts I can see,
So that conversational investigation is useful without granting database or administrative access.

**Acceptance boundary (verbatim, `epics.md:715`):** FR5 and the scheduling inspect
capability only. The general `CapabilityManifestV1` contract and its add/remove
conformance proof are wholly owned by Story 2.6; nothing in this story depends on
Story 2.6 to complete.

This is the story that builds the **tool gateway**: an application-owned registry
that decides which capabilities exist for a run from server-derived context, one
`scheduling_inspect` capability whose handler reads Epic 1's normalized projection,
and a trusted `AgentDeps` structure that is the *only* source of actor, site,
version, policy, clock, services, and remaining budget. Everything the model says
is untrusted input to that gateway — never an authority decision.

### Six decisions were made at story creation — do not re-litigate them

#### Decision 1 — This story composes and executes the capability at the **seam**, not on an HTTP request path

The registry, the manifest, `AgentDeps`, the handler, and the adapter that renders
granted capabilities into PydanticAI tools are all built and executed for real —
through the actual `PydanticAIAgentRuntime` with a deterministic model double, the
same way `backend/evals/report.py:82-88` already drives a run today. What this
story does **not** do is wire agent execution into a FastAPI route.

Concretely, and non-negotiably, this story ships:

- **no new HTTP route, and no change to `POST /api/v1/conversations/{id}/messages`**;
- **no `agent_run` state transition** — `agent_queued` remains the only status ever
  written, so **no migration** and **no `GRANT UPDATE (status) ON agent_run`**;
- **no new `ActivityItemV1` payload**, no new `event_type`, no new SSE frame;
- **no frontend change whatsoever.**

Why, in order of force:

1. **No acceptance criterion asks for it.** AC1 says "composed **for the run**" —
   composition. AC2 validates a manifest. AC3 is about where `AgentDeps` values come
   from. AC4 says the agent "**can answer**" — a capability claim, not a rendered
   answer. Compare Story 2.4-AC3, which spells out a measured threshold and
   "blocks implementation acceptance"; nothing of that kind appears here.
2. **A visible agent answer before Story 2.7 would violate UX-DR8.** An inspect
   answer is, by construction, numbers about demand and coverage. UX-DR8
   (`epics.md:192`) requires *"every numerical or schedule-specific claim"* to carry
   an adjacent evidence link naming exact group, record, field/range, and version;
   NFR12 requires 100% of numerical claims to pass the grounding evaluator. Story
   2.7 wholly owns both the grounding gate and the evidence-link rendering
   (`epics.md:769-790`). Shipping the answer here forces a choice between violating
   UX-DR8 and pre-empting 2.7. Both are worse than waiting.
3. **`agent_run` has no UPDATE grant, deliberately.** Story 2.3 withheld it in
   writing: *"Epic 3 will need `UPDATE` on `agent_run` to advance the state machine;
   it is that story's job to grant it, not this one's to grant it early."* Executing a
   turn means transitioning that row, which means a migration, which moves the
   `schema_version` binding of **every** evidence file in the repo. That cost buys
   nothing any AC requires.
4. **Story 2.6 needs exactly this shape.** Its AC4 (`epics.md:764-767`) requires that
   removing a demonstration module leave *"the Story 2.5 scheduling inspect
   capability"* green with no code change. A registry + manifest + handler slice is
   precisely what that conformance proof composes against.

**Handoff, recorded so it is not lost:** the first story to execute an agent turn on
a request path is **Story 2.7**. It inherits, together: the `agent_run` UPDATE grant
and its migration, the `agent_response` `ActivityItemV1` payload, `run_in_threadpool`
for the synchronous `run_sync` call, `create_agent_runtime()`'s missing live-model
wiring (`deferred-work.md:86`), and `translate.py`'s silent drops (Decision 6).

#### Decision 2 — The handler reads through `ScenarioProjectionReader`, never `ScenarioCatalogueReader`

AC2 requires *"the handler calls the scenario-read use case rather than repositories
or a second source-data interpretation."* Two read ports exist. The choice is forced:

- `ScenarioProjectionReader` (`backend/application/ports/scenario_projection.py:102-177`)
  types its connection `connection: Any` — AD-1 clean. Every page it returns already
  carries `scenario_id`, **`scenario_version_id`**, and **`site_id`**, which is
  exactly AC4's *"every tool result remains site- and version-scoped"* with nothing
  for the handler to synthesise. `get_overview()` supplies the version pin.
- `ScenarioCatalogueReader` (`backend/application/ports/scenario_catalogue.py:9`) does
  `from sqlalchemy import Connection` at module scope and puts that vendor type in the
  Protocol's own signatures. It is **the one open AD-1 violation in
  `backend/application/`**, ticketed at `deferred-work.md:112-131`, whose owner is
  restated as *"the next story that modifies `ScenarioCatalogueReader` or
  `adapters/postgres/scenario_catalogue.py` for any reason."*

**Touch the catalogue port and this story inherits a tier-3 refactor of a Gate A read
port, its adapter, `api/deps.py`, and a router — plus a Gate A re-measurement.** The
projection reader supplies everything AC2 and AC4 need, so this story does not touch
the catalogue. `ALLOWED_LEAKS` in `backend/tests/architecture/test_conversation_boundaries.py:26-28`
stays exactly as it is; `test_every_allowed_leak_still_exists_and_still_leaks` goes red
if anyone half-fixes it.

#### Decision 3 — The manifest is a module-local declaration, **not** `CapabilityManifestV1`

AC2 requires *"the scheduling inspect capability manifest"* to declare typed
input/output, inspect risk, permission/scope, version semantics, budget/timeout, safe
evidence/audit mapping, errors, and evaluation fixtures. `epics.md:715` simultaneously
assigns *"the general `CapabilityManifestV1` contract"* wholly to Story 2.6, and
AD-20 (`ARCHITECTURE-SPINE.md:204-208, 327`) fixes that name to `application/contracts`.

Settled: this story ships **`InspectCapabilityManifest`** in
`backend/application/capabilities/`, carrying every field AC2 lists **plus
`approval_policy`** (see the trap below). Story 2.6 lifts it into the canonical
`CapabilityManifestV1` under `application/contracts/` and adds the general
registration/rejection semantics.

Rationale: naming it `CapabilityManifestV1` now leaves Story 2.6 with two bad options —
inherit a canonical, versioned AD-20 contract it was told it owns, or rename one after
it is in use, which for a versioned contract is a compatibility event. A module-local
declaration that 2.6 generalises costs one refactor of one file and breaks nothing.

**Trap inside this decision:** AC2's field list omits `approval_policy`, but AD-5
(`ARCHITECTURE-SPINE.md:76`) and `CapabilityManifestV1`'s required shape
(`ARCHITECTURE-SPINE.md:327`) both require it. For an `inspect` capability it is
trivially "none" — declare it explicitly as `none` rather than omitting the field. An
absent field and a field that says "no approval" are different claims.

#### Decision 4 — Authority is proved by **absence**, not by a check the model can reach

AC1's *"model-generated capability names or module loading cannot grant authority"* and
AC3's *"arbitrary SQL, shell, credentials, unrestricted network, identity
administration, or runtime capability installation do not exist"* are both statements
about what is **not registered**.

The registry composes the granted set from trusted context **before** the runtime is
constructed, and the adapter registers *only* those capabilities on that run's `Agent`.
A capability the run was not granted is therefore not a denied tool — it is a tool that
does not exist, and the model calling its name gets the framework's own unknown-tool
path. Do **not** implement this as a registered tool that checks a permission and
refuses: that shape puts the authority decision downstream of a name the model
supplied, and it is exactly what AD-2's *"No model output … grants authority"* forbids.

`AgentToolCallProposalV1`'s own docstring
(`backend/application/contracts/agent_runtime.py:122-128`) already states the rule:
*"The capability name here is model-supplied and therefore UNTRUSTED (AD-2, AD-15): the
application resolves it against its own registry before anything executes. It is never
itself an authority decision."*

PydanticAI's `prepare=` hook (a `ToolDefinition | None` callback, verified against the
pinned 2.27.0 API) may be used as a **second** gate. It may not be the first: the
authoritative decision lives in `backend/application/`, which cannot import
`pydantic_ai` at all.

#### Decision 5 — `AgentDeps` reaches the adapter by **construction**, never on `AgentTurnRequestV1`

`backend/tests/test_agent_runtime_port.py:196-204` pins `AgentTurnRequestV1`'s field set
to exactly `{schema_version, prompt, history, budget, approvals}` and separately asserts
that none of `capability_name, capability, permission, permissions, scope, authority,
is_authorized, allow, role` appears. Adding trusted deps to the turn request turns that
test red, and the test is right: the request contract is the thing the model's content
travels in.

So: **one runtime instance is composed per run**, constructed with that run's granted
capabilities and its trusted `AgentDeps`. This is not a new pattern — the eval harness
already does exactly this (`backend/evals/report.py:83`,
`PydanticAIAgentRuntime(model=build_model_double(case))`, one per case). The
`AgentRuntime` port signature `run_turn(request) -> outcome`
(`backend/application/ports/agent_runtime.py:41-63`) is **unchanged**.

#### Decision 6 — The `translate.py` silent-drop item is re-annotated, not closed

`deferred-work.md:91` describes `to_framework_messages` silently dropping an
unrecognized `AgentMessageV1.role`, and `_from_response` skipping an unrecognized
`AgentPartV1.kind`. Story 2.3 reassigned it to this story on the premise that
*"Story 2.5 … is the first story to run a turn and rehydrate history."*

**Verified at creation: the premise is false under Decision 1.** The drop is reachable
only when a persisted `AgentTurnV1` is deserialized back into framework messages. This
story persists no turn and rehydrates no history — `to_framework_messages` runs, but
only over turns this process just built with `to_owned_turn`, which is the same
single-producer situation Story 2.1 described.

Follow Story 2.4's precedent for exactly this situation (it corrected the ledger's
false premise about the `scenario_catalogue` owner rather than absorbing the work):
**annotate the entry in place, restate the owner as "the first story that persists an
`AgentTurnV1` and rehydrates it", and leave it open.** Do not silently close it. Do not
edit `backend/agent/translate.py` — that file keeps a zero-line diff even though the
rest of `backend/agent/**` does not.

## Acceptance Criteria

1. **Given** an authenticated conversation and selected fixture version **when** the
   scheduling module is composed for the run **then** its inspect capability is granted
   from current role, site, feature policy, and conversation context through the
   application-owned registry **and** model-generated capability names or module
   loading cannot grant authority. *(FR5, AR5)*

2. **Given** the scheduling inspect capability manifest **when** it is validated
   **then** it declares versioned typed input/output, inspect risk, permission/scope,
   version semantics, budget/timeout, safe evidence/audit mapping, errors, and
   evaluation fixtures **and** the handler calls the scenario-read use case rather than
   repositories or a second source-data interpretation. *(FR5, AR5)*

3. **Given** trusted `AgentDeps` **when** the model proposes an inspection call
   **then** actor, site, membership, request/run IDs, current versions, policy version,
   clock, services, and remaining budget come only from server-owned dependencies
   **and** arbitrary SQL, shell, credentials, unrestricted network, identity
   administration, or runtime capability installation do not exist. *(FR3, FR6, AR2, AR15)*

4. **Given** the primary Wednesday investigation question **when** the agent inspects
   demand, assignments, qualifications, availability, locks, constraints, and relevant
   saved metrics **then** it can answer from allow-listed normalized facts without
   direct database access or fabricated context **and** every tool result remains site-
   and version-scoped. *(FR5)*

## Note for review — "role", "feature policy", and "policy version" do not exist yet

AC1 grants the capability *"from current role, site, feature policy, and conversation
context"* and AC3 sources *"policy version"* from server-owned dependencies. **Verified
at creation by exhaustive grep over `backend/{adapters,application,api,agent,domain,evals,config,scripts}`
and `settings.py`: none of `role`, `permission`, `feature_flag`, `entitlement`, or
`policy_version` has any application-level representation.** The only `role` in the
backend is the PostgreSQL role `shiftmind_runtime`; `membership`
(`backend/adapters/postgres/schema.py:218-243`) has columns
`id, app_user_id, site_id, created_at, revoked_at` and **no role column**, under a
partial unique index `uq_membership_single_active ON (true) WHERE revoked_at IS NULL` —
one active membership per database.

This is the one-user MVP the spine's Deferred table already records:
*"Multiple roles and separation of duties | one seeded planner may self-approve |
revisit trigger: activating a second user or customer security review"*
(`ARCHITECTURE-SPINE.md:447-464`).

**Required posture — honest seam, not invented authority.** Model the grant inputs as a
real, server-owned typed structure whose values in this milestone are: role derived
from the single active membership, feature policy a server-side constant, policy
version a server-side constant string. Do **not** fabricate a role table, a permissions
model, or a policy service — that is scope this story has no requirement for and no
story owns yet. Do **not** collapse the inputs away either: the registry must take them
as arguments and branch on them, so substituting a real policy source later is a change
of *supplier*, not a change of *shape*. Record the reduction in
`deferred-work.md` naming the revisit trigger above.

A grant function that ignores three of its four inputs is a lie about coverage — the
same defect the Story 2.1 review fixed in an over-claiming guard docstring. State in the
docstring exactly which inputs are currently constant and why.

## Tasks / Subtasks

- [ ] **Task 1: The authoritative risk-class and permission vocabulary** (AC: #1, #2)
  - [ ] Create `backend/application/capabilities/__init__.py` and
        `backend/application/capabilities/vocabulary.py`. Define `RiskClassV1` as
        `Literal["inspect", "draft", "compute", "consequential", "prohibited"]` —
        AD-5's exact five values (`ARCHITECTURE-SPINE.md:76`), no sixth, no rename.
        The addendum's older four-value `read/draft/compute/consequential` list
        (`addendum.md:71`) is superseded; the class is `inspect`, never `read`.
  - [ ] This is the **authoritative** type. `backend/evals/cases.py:14-16` currently
        declares the identical `Literal` as a *dataset tag that grants nothing* —
        Story 2.2 wrote that it *"may later lift this vocabulary or define its own
        authoritative one."* Lift it: have `evals/cases.py` import `RiskClassV1` from
        `application.capabilities.vocabulary` and keep its `RISK_CLASSES` tuple derived
        from it, so the two can never drift.
  - [ ] Direction check before you do it: `test_evaluation_boundaries.py:104-114`
        forbids `application/**` importing `evals`. `evals` importing `application` is
        permitted and already happens. The authoritative literal must therefore live in
        `application/`, never the reverse.
  - [ ] **Acceptance boundary:** a test asserting the five values, that
        `evals.cases.RISK_CLASSES` is derived from the application vocabulary rather
        than re-declared, and that the two golden cases on disk still load unchanged.

- [ ] **Task 2: Trusted `AgentDeps`** (AC: #3)
  - [ ] Create `backend/application/capabilities/deps.py` with a frozen
        `AgentDepsV1` carrying every value AC3 names: `actor_id`, `site_id`,
        `membership_id`, `request_id`, `agent_run_id`, `conversation_id`,
        `scenario_id`, `scenario_version_id`, `policy_version`, a `clock` callable, the
        service handles the handler needs, and `remaining_budget`.
        `addendum.md:66` is the normative list.
  - [ ] Follow the house contract convention exactly: `from __future__ import
        annotations`, module-level `SCHEMA_VERSION = "1"`, `@dataclass(frozen=True)`,
        `schema_version: str = SCHEMA_VERSION` last, `V1` suffix. Frozen dataclass —
        **not** a pydantic `BaseModel`; pydantic in this repo is for HTTP wire models in
        `api/schemas.py` only.
  - [ ] **Every field is server-derived.** `actor_id`/`site_id` come from
        `ResolvedSession` (`backend/application/ports/session.py:25-31`);
        `scenario_version_id` is re-resolved server-side, never taken from a payload;
        `remaining_budget` derives from `AgentBudgetV1`. Nothing is read from a request
        body, a browser value, or model output.
  - [ ] **Do not add these to `AgentTurnRequestV1`** (Decision 5).
        `backend/tests/test_agent_runtime_port.py:196-204` pins its five fields and
        forbids the names `capability, permission, scope, role, authority` — that test
        must stay green untouched.
  - [ ] The `services` handle is typed against the **port Protocol**
        (`ScenarioProjectionReader`) plus an opaque connection/opener, never a
        SQLAlchemy type. `test_conversation_boundaries.py` flags root imports of
        `sqlalchemy` and `fastapi` in guarded application modules.
  - [ ] **Acceptance boundary:** a test constructing `AgentDepsV1` and asserting every
        AC3-named value is present, plus the still-green
        `test_agent_runtime_port.py` field-set assertion proving none of it leaked onto
        the turn request.

- [ ] **Task 3: The scheduling inspect capability manifest** (AC: #2)
  - [ ] Create `backend/application/capabilities/scheduling_inspect.py`. Declare
        `InspectCapabilityManifest` (Decision 3 — **not** `CapabilityManifestV1`) with
        every AC2 field: capability name + version, typed input schema ref, typed
        output schema ref, `risk_class="inspect"`, permission/scope, version and
        idempotency semantics, budget and timeout, safe audit/evidence mapping, the
        error vocabulary, and evaluation-fixture refs.
  - [ ] Add `approval_policy="none"` explicitly — AD-5 and `CapabilityManifestV1`'s
        required shape (`ARCHITECTURE-SPINE.md:327`) both require the field even though
        AC2's list omits it. An absent field is not the same claim as "no approval".
  - [ ] Budget and timeout are **application configuration, never model-chosen** —
        NFR16, AD-7 (`ARCHITECTURE-SPINE.md:88`), `prd.md:272`. Put the numbers in
        `backend/settings.py` beside the existing `agent_runtime_*` fields, not as
        literals in the handler.
  - [ ] Evaluation-fixture refs must name **files that exist** after Task 7. A manifest
        field pointing at nothing is the "declared but never used" defect the Story 2.3
        review caught with `PersistedEventV1`.
  - [ ] **Acceptance boundary:** a validation test asserting every AC2 field is present
        and non-empty, that `risk_class == "inspect"`, that each declared evaluation
        fixture path resolves on disk, and that the declared budget/timeout come from
        settings rather than a hardcoded literal.

- [ ] **Task 4: The application-owned capability registry** (AC: #1)
  - [ ] Create `backend/application/capabilities/registry.py`. One function composes
        the granted set for a run from trusted inputs — role, site, feature policy, and
        conversation context (see "Note for review" for what each is in this milestone).
        It returns the granted capability declarations; it returns nothing derived from
        model output.
  - [ ] **Grant by absence (Decision 4).** An ungranted capability must not be
        registered on the run at all. Do not register-then-refuse.
  - [ ] Nothing in this module may import `pydantic_ai`, `sqlalchemy`, or `fastapi`.
        `test_agent_runtime_boundaries.py:208-231` already forbids the first for all of
        `application/**`; add this module to `test_conversation_boundaries.GUARDED` for
        the other two (Task 8).
  - [ ] **Acceptance boundary:** three tests — the capability is granted for a
        well-formed trusted context; it is **absent** (not denied) when the context does
        not grant it; and a proposed capability name that is not in the registry
        resolves to nothing, asserted against the registry function directly rather
        than through a refusal message.

- [ ] **Task 5: The scenario-read use case and the inspect handler** (AC: #2, #4)
  - [ ] Add `backend/application/use_cases/read_scenario_facts.py`. **Verified at
        creation: no scenario-read use case exists** — `application/use_cases/` contains
        only `accept_turn.py`, and the projection port is consumed directly by
        `api/routers/scenario_projection.py`. AC2 requires one, so this story creates
        it. Copy `accept_turn.py`'s exact shape: module-level function, port first,
        `connection: Any` second, keyword-only arguments after.
  - [ ] The handler in `scheduling_inspect.py` calls **that use case only**. It must not
        import an adapter, must not construct SQL, and must not re-derive filtering or
        sorting semantics — the adapter is the single source-data interpretation
        (`addendum.md:18`: the viewer exists partly to *"prevent the agent adapter from
        becoming a second interpretation of source data"*).
  - [ ] Cover AC4's seven fact kinds through the existing port
        (`backend/application/ports/scenario_projection.py:102-129`): demand →
        `get_demand`, assignments → `get_baseline_assignments`, locks → `get_locks`,
        constraints → `get_constraints`, and **qualifications + availability →
        `get_workers`**, since `WorkerV1` nests `qualifications` and
        `availability_windows` (`application/contracts/scenario_projection.py:72-83`).
  - [ ] **"Relevant saved metrics" — read this before inventing one.** There is no
        metrics group in the projection. The only saved aggregates are the counts on
        `ScenarioOverviewV1` (`work_area_count`, `task_count`, `worker_count`,
        `demand_interval_count`, `baseline_assignment_count`, `lock_count`,
        `constraint_count`, plus `horizon_minutes` and the checksum fields) from
        `get_overview`. Map "relevant saved metrics" to those and say so in the
        docstring. `MetricSetV1` is an AD-20 contract that **does not exist yet** and
        belongs to the epic that computes run metrics — do not create it here, and do
        not compute a metric in the handler. AR11 assigns recomputation to application
        calculators under Story 2.7.
  - [ ] **Bounded reads, honest truncation.** `GroupQueryV1` defaults to `limit=50` and
        the routers cap at 200. Every page returns `next_cursor`, `total_count`, and
        `matching_count` — surface truncation in the typed output. A truncated fact set
        presented as complete is a grounding lie, and Story 2.3's review caught exactly
        this shape (a 200-item window with no `has_more`).
  - [ ] **Site and version scope come from the data, not from the handler.** Every
        `*PageV1` already carries `site_id` and `scenario_version_id`. Propagate them
        into the typed output; do not re-stamp them from `AgentDepsV1`, and assert the
        page's `scenario_version_id` matches the deps' pin — a mismatch is a distinct
        typed error, never a silent retarget (AR11).
  - [ ] **Acceptance boundary:** a test driving the handler against a stubbed
        `ScenarioProjectionReader` that answers the Wednesday outbound question across
        all seven fact kinds; asserting `site_id` and `scenario_version_id` on every
        result; asserting the truncation signal is set when a page is short; and
        asserting the handler module imports no adapter and no `sqlalchemy`.

- [ ] **Task 6: Render granted capabilities into PydanticAI tools** (AC: #1, #3)
  - [ ] In `backend/agent/` — the only package permitted to import `pydantic_ai` —
        add the module that turns granted declarations into registered tools.
        `backend/agent/**` has carried a mandated zero-line diff since Story 2.1; **this
        story deliberately breaks that fence** and must say so in completion notes.
        `backend/agent/translate.py` still keeps a zero-line diff (Decision 6).
  - [ ] Construct the run's `Agent` with `deps_type=AgentDepsV1` and pass the deps at
        `run_sync(..., deps=...)`. Verified against the pinned PydanticAI 2.27.0 API:
        `@agent.tool` receives `ctx: RunContext[DepsT]` and `ctx.deps`; an optional
        `prepare=` callback returning `ToolDefinition | None` can conditionally omit a
        tool. Use `prepare=` only as a second gate (Decision 4).
  - [ ] **`RunContext` must not cross into `application/`.** It is in
        `FRAMEWORK_TYPE_NAMES` (`test_agent_runtime_boundaries.py:57-100`), which
        forbids the *name* appearing in `domain/` or `application/` code at all. The
        framework-facing wrapper lives in `agent/`, unpacks `ctx.deps`, and calls the
        application handler with plain typed values.
  - [ ] Compose **one runtime per run** with that run's granted capabilities and deps
        (Decision 5). Do not change the `AgentRuntime` port signature. Do not touch
        `AgentTurnRequestV1`.
  - [ ] Leave `shiftmind_demonstration` (`backend/agent/runtime.py:115-130`) registered
        and behaving exactly as it does — Story 2.2's two golden cases and
        `test_agent_runtime_adapter.py` depend on it, and Story 2.6 removes it under its
        own conformance proof, not this one.
  - [ ] **Do not call `create_agent_runtime()`.** It is a known-incomplete factory —
        `config.model`/`config.api_key` are stored and never read, so it returns a
        runtime that cannot run (`deferred-work.md:86`). Live model wiring belongs to
        the story that first puts `AgentRuntime` on a request path, which under
        Decision 1 is not this one. Tests inject a deterministic double.
  - [ ] **Acceptance boundary:** a test running a real turn through
        `PydanticAIAgentRuntime` with a deterministic model double where the model calls
        `scheduling_inspect` and the outcome carries the handler's typed result; plus a
        second test where the model calls an **ungranted** name and the assertion is
        that the tool was never registered — not that a refusal string came back.

- [ ] **Task 7: Golden evaluation cases for `scheduling_inspect`** (AC: #2, #4)
  - [ ] Story 2.2 named this story as their owner and forbade them until now:
        *"Do not fabricate a `scheduling_inspect`-shaped case that Story 2.5 hasn't
        built yet"* and *"Real capability cases (scheduling inspect, …) | Stories 2.5,
        2.7, 2.9, …"*. AC2 additionally requires the manifest to declare evaluation
        fixtures, which is only honest if they exist. **Contribute them.**
  - [ ] Add at least **four** cases under `backend/evals/golden/scheduling_inspect/`,
        tagged `"capability": "scheduling_inspect"`, `"risk_class": "inspect"` —
        NFR28's floor is *"at least four per allowed capability"*
        (`requirements-inventory.md:49`).
  - [ ] **Do not pad toward the 50-case Gate B aggregate.** `epics.md:1527`:
        *"lower the threshold with a recorded rationale — never pad the dataset to reach
        it."* Four real cases, each measuring something the tool-routing evaluator can
        actually judge (tool name and arguments). Gate B's re-verification is Story
        2.9's and the release report's, not this story's.
  - [ ] Cases that read real fixture data must set
        `"scenario_fixtures": ["<fixture_id>:<version>"]` — `evals/report.py:154-170`
        parses that into the NFR27 `scenario` binding, and the demonstration cases'
        empty list is correct only because they touch no fixture.
  - [ ] Every field in `CASE_FIELDS` is required and unknown fields are rejected
        (`evals/cases.py:89-172`); each `scripted_turns` entry declares **exactly one**
        of `tool_name` / `response_text`. Note the wire shape nests tool args under the
        parameter name — check the handler's parameter name against
        `golden/demonstration/repeat-once.json:10-15` before writing `arguments`.
  - [ ] **This will turn `test_evaluation_harness.py:251` red**:
        `assert {case.capability for case in cases} == {"demonstration"}`. Relax it to
        assert `"demonstration"` remains present (its two shapes must survive, per the
        comment at `:235-240`) while permitting later contributors. Preserve
        `len(cases) >= 2` and both coverage assertions at `:240-250` untouched.
  - [ ] `evals/README.md` and `test_readme_documents_exact_contribution_shape_and_owners`
        (`:272-276`) pin literal README strings — update both together or neither.
  - [ ] Any new module under `backend/evals/` that imports `pydantic_ai` must carry
        `models.ALLOW_MODEL_REQUESTS = False` at **module scope**, enforced by
        `test_evaluation_boundaries.py:88-101`.
  - [ ] **Acceptance boundary:** `uv run --frozen pytest tests/test_evaluation_harness.py`
        green with the new cases loaded, at least four `scheduling_inspect` cases
        present, and the tool-routing evaluator returning a real verdict on each.

- [ ] **Task 8: Architecture guards, red then green** (AC: #1, #3)
  - [ ] Extend `GUARDED` in
        `backend/tests/architecture/test_conversation_boundaries.py:13-20` with every
        new `application/capabilities/**` module. That module's own
        docstring states the convention: *"a guard whose file list stops growing with the
        layer it guards quietly becomes a claim about coverage it no longer has."* Note
        `application/use_cases/**` is already swept automatically (`:43`), so the new
        use case needs no entry.
  - [ ] Leave `ALLOWED_LEAKS` (`:27-29`) exactly as it is — Decision 2 means the
        `scenario_catalogue` leak is untouched, and
        `test_every_allowed_leak_still_exists_and_still_leaks` goes red if it is
        half-fixed.
  - [ ] Add the **prohibited-capability absence proof** for AC3: an executable
        assertion that no registered capability, in any composed grant, exposes SQL
        execution, shell, credential access, unrestricted network, identity
        administration, or runtime capability installation. Assert against the composed
        registry's actual output, not against a hand-maintained list of names — a test
        that enumerates the tools that *do* exist and asserts the set is a subset of the
        manifest-declared allow-list cannot be satisfied by adding a new tool and
        forgetting to update it.
  - [ ] **Every new guard must be demonstrated red then green.** Story 2.1's rule,
        repeated by 2.2 and 2.3: *"a guard nobody has seen go red is a guard nobody has
        tested."* Add the self-redness tests beside the existing ones
        (`test_agent_runtime_boundaries.py:335-377`,
        `test_conversation_boundaries.py:53`).
  - [ ] **Every guard states what it does not cover.** Scope as data, not prose — the
        `ALLOWED_LEAKS` dict is the pattern; a docstring claim is what the Story 2.1
        review had to narrow and what the Story 2.3 review rejected as
        "unimplementable as written".
  - [ ] **Acceptance boundary:** each new guard shown failing against a deliberately
        violating tree and passing on the shipped one, with the redness demonstration
        recorded in the Debug Log.

- [ ] **Task 9: Close the inherited ledger items honestly** (AC: none — housekeeping, do not skip)
  - [ ] `deferred-work.md:91` (`translate.py:61-105` silent drops): annotate in place
        with the Decision 6 finding — the reassignment premise was that 2.5 rehydrates
        persisted turns, and under Decision 1 it does not. Restate the owner as *"the
        first story that persists an `AgentTurnV1` and rehydrates it"*. **Leave it
        open.** Follow the annotation style Story 2.4 used at `:8` and `:125-131`.
  - [ ] `deferred-work.md:86` (`create_agent_runtime()` wires no real model): annotate
        that Story 2.5 evaluated it, did not call the factory, and that the owner is
        unchanged.
  - [ ] Add a new entry recording the "Note for review" reduction: role, feature policy,
        and policy version are server-owned constants in the one-user MVP; the revisit
        trigger is the spine's Deferred-table row *"activating a second user or customer
        security review"*.
  - [ ] Add a new entry recording that this story is the first to break
        `backend/agent/**`'s zero-line-diff fence, and which files it touched, so a later
        story does not read the fence as still standing.
  - [ ] **Acceptance boundary:** every entry above present, each naming its owner and
        revisit trigger; nothing closed that was not actually fixed.

- [ ] **Task 10: Full regression gate** (AC: all)
  - [ ] **Re-derive the baselines below rather than trusting them.** Story 2.4 recorded
        a postgres figure of 27 that was actually 36 by the time it ran; the reviewer had
        to correct it. Measure first, then compare.
  - [ ] Backend from `backend/`: `uv run --frozen pytest`
        (baseline 602 passed / 1 skipped / 7 deselected on a dirty tree; 603 / 0 clean —
        the skip is `test_evidence_binding.py:350`'s documented clean-tree self-skip).
  - [ ] `uv run --frozen pytest -m postgres` (baseline 43 passed) with the Docker
        PostgreSQL 18 service from `docker-compose.yml` up.
  - [ ] `uv run --frozen pytest tests/test_evidence_convention.py` (baseline 48 passed).
  - [ ] **From the repository root**, `uv run --project backend alembic check` →
        *"No new upgrade operations detected."* From `backend/` it fails with
        `No 'script_location' key found in configuration` — a working-directory mistake
        that reads like a missing config. **Do not synthesize a temporary alembic
        config**; `deferred-work.md:100-110` carries the corrected measurement table.
        Under Decision 1 this story adds no migration, so the diff must stay at zero.
  - [ ] Frontend from `frontend/`: `npm run codegen`, `npm run typecheck`, `npm run lint`,
        `npm test`, `npm run build`, `npm run test:e2e` (build-first since Story 2.2).
        Baselines: 55 files / 322 tests, 46 e2e, 3 pre-existing
        `only-export-components` warnings. **Under Decision 1 the frontend must show a
        zero-line diff** — including `frontend/openapi.json` and
        `frontend/src/api/schema.d.ts`, since no route changes.
  - [ ] **Re-run Gate A and report it by name.** AR28 binds every story. Regenerate
        `evidence/story-1.11/gate-a-readiness-report.json` per
        `docs/EVIDENCE-CONVENTION.md` — commit code, confirm `git status --porcelain` is
        empty, measure, generate, then commit the evidence **separately** — and confirm
        `gate_a_passed` still reads `true` with `blocking: []`.
  - [ ] Confirm the zero-line diffs this story claims: `backend/agent/translate.py`,
        `backend/services/**`, `backend/domain/**`, `backend/engine/**`,
        `backend/llm/**`, `backend/migrations/**`, `backend/tests/test_gate_a_mutation_audit.py`,
        and all of `frontend/`.
  - [ ] **Acceptance boundary:** every suite above green, every zero-line diff verified
        with `git diff --stat`, `gate_a_passed: true`, and the measured numbers recorded
        in Completion Notes — not the numbers copied from this task.

## Dev Notes

### What this story is, and the eight things it is not

It is the **tool gateway**: an application-owned registry, one governed `inspect`
capability, a trusted `AgentDeps`, and the adapter that renders the granted set into
framework tools. It is the first story where the model is handed something real to
propose and the application decides whether that proposal means anything.

It is **not**:

| Not this | Owner | Source |
|---|---|---|
| Executing an agent turn on an HTTP request path | Story 2.7 | Decision 1 |
| The general `CapabilityManifestV1` contract, registry rejection of incomplete manifests, add/remove conformance | Story 2.6 | `epics.md:715, 739-767` |
| Grounding, evidence links, claim recomputation | Story 2.7 | `epics.md:769-790`, NFR12, AR11 |
| Evidence navigation and return-to-claim | Story 2.8 | `epics.md:792-813` |
| Clarification and refusal variants | Story 2.9 | `epics.md`, FR6 |
| `MetricSetV1`, run metrics, calculators | Epic 3 / Story 2.7 | AD-20, AR11 |
| An `agent_run` UPDATE grant and its migration | Epic 3 | `2-3` Task 3 |
| Any frontend change | — | Decision 1 |

### The seven traps, ranked by how quietly they fail

1. **Registering an ungranted capability and refusing inside it.** Reads correct,
   passes a naive test, and inverts AD-2 — the authority decision now sits downstream of
   a model-supplied name. Grant by absence (Decision 4). The tell: your test asserts on a
   refusal message instead of on the registered tool set.
2. **Putting trusted deps on `AgentTurnRequestV1`.** This one *does* fail loudly —
   `test_agent_runtime_port.py:196-204` pins five fields and forbids the names
   `capability, permission, scope, role, authority`. Listed here because the obvious
   first instinct is to add a field, and the second instinct is to amend the test.
   Amend neither; construct per run (Decision 5).
3. **Reaching for `ScenarioCatalogueReader` to get a version pin.** It silently drags in
   the repo's one open AD-1 violation, a tier-3 refactor of Gate A code, and a Gate A
   re-measurement. `get_overview()` on the projection reader gives you
   `scenario_version_id` with none of that (Decision 2).
4. **Re-deriving filter or sort semantics in the handler.** The router's six
   `sort: Literal[...]` query enums (`api/routers/scenario_projection.py:211, 257, 307,
   355, 398, 443`) are an HTTP allow-list, not the interpretation. Build a `GroupQueryV1` and let the one adapter
   interpret. Two interpretations of the same fixture is precisely the drift AD-4 and
   `addendum.md:18` exist to prevent, and it fails as *wrong numbers*, not as a red test.
5. **Inventing "saved metrics".** There is no metrics group and no `MetricSetV1`. A
   handler that computes a coverage figure has quietly become an ungoverned calculator
   that Story 2.7's grounding gate will later have to recompute against. Map to
   `ScenarioOverviewV1`'s counts and say so.
6. **Returning a truncated page as if it were the whole answer.** `GroupQueryV1` defaults
   to 50 rows. An agent that answers "there are 50 demand intervals" from a first page is
   fabricating context — the exact failure FR5 names. Surface `next_cursor` /
   `total_count` / `matching_count` in the typed output.
7. **A grant function that ignores three of its four inputs.** AC1 names role, site,
   feature policy, and conversation context. Three of them are constants in this
   milestone. Taking them as parameters and branching on them keeps the seam honest;
   quietly dropping them makes the later substitution a redesign. See "Note for review".

### Existing conventions to match, not reinvent

- **Contracts**: frozen dataclasses in `application/contracts/`, module-level
  `SCHEMA_VERSION = "1"`, `schema_version` field last with that default, `V1` suffix,
  `from __future__ import annotations`, absolute imports from the backend root. Pydantic
  is for `api/schemas.py` wire models only. Reference example:
  `application/contracts/activity.py` (40 lines, read it whole).
- **Ports**: `typing.Protocol`, `connection: Any` as the second positional parameter —
  copy `application/ports/scenario_projection.py:104`, never
  `application/ports/scenario_catalogue.py:9`.
- **Use cases**: module-level function, port first, `connection: Any` second,
  keyword-only after. `application/use_cases/accept_turn.py:10-18` is the only existing
  example — copy its shape exactly.
- **Dependency seams**: add the registry seam to `backend/api/deps.py` following
  `get_projection_reader` (`:78`) — module-level singleton plus a
  `dependency_overrides`-friendly getter — even though no route consumes it yet, so
  Story 2.7 finds the seam already shaped.
- **`site_context()`** (`api/deps.py:140-177`) is *the* single place trusted site context
  is established. If any test needs a real connection, go through it or through
  `get_site_context_opener` (`:190-210`). Do not open a second engine.
- **Tests**: flat `backend/tests/test_*.py`, boundary guards in
  `backend/tests/architecture/`. `test_<thing>_api.py` = transport with
  `dependency_overrides`; `test_<thing>_postgres.py` = real DB with
  `pytestmark = pytest.mark.postgres` and the `governed_postgres_engine` module fixture
  (`backend/conftest.py:83-102`). Any test module importing `pydantic_ai` sets
  `models.ALLOW_MODEL_REQUESTS = False` at module scope.
- **Seeding test data**: `app_user` and `membership` are singletons
  (`uq_app_user_singleton`, `uq_membership_single_active`). Reuse the shared
  select-or-insert helper Story 2.4 added rather than inserting your own actor — this
  made a Story 2.4 test order-dependent.
- **No new dependency.** Everything this story needs is in the pinned
  `pydantic-ai-slim[google,openrouter]==2.27.0`. Adding one triggers AR19/AR27 ceremony
  (`ARCHITECTURE-SPINE.md:264`: *"add and lock each planned dependency only at its
  implementation gate"*).
- **`.github/` still does not exist.** Do not add a CI workflow.

### Latest technical information (verified 2026-08-11 against the pinned versions)

PydanticAI is a **repository lock at 2.27.0**
(`ARCHITECTURE-SPINE.md:271`, `backend/pyproject.toml:31`, exact pin); AD-19's spike is
closed by Story 2.1 with the verdict in `docs/AGENT-RUNTIME-DECISION.md`. Do not
re-open it, do not version-shop.

Verified against the current PydanticAI documentation for the pinned line:

- `Agent(deps_type=MyDeps)` plus `agent.run_sync(prompt, deps=deps)` is the supported
  typed-dependency mechanism; tools declared with `@agent.tool` receive
  `ctx: RunContext[MyDeps]` and read `ctx.deps`. `@agent.tool_plain` is the
  context-free variant.
- `@agent.tool(prepare=fn)` where `fn(ctx, tool_def) -> ToolDefinition | None` omits the
  tool from the run when it returns `None` — a supported per-run filter, usable as the
  second gate but never the first (Decision 4).
- The existing adapter builds its `Agent` **without** `deps_type`
  (`backend/agent/runtime.py:109-113`) and registers `shiftmind_demonstration` with a
  bare `@self._agent.tool` closure whose `ctx` is untyped. Adding `deps_type` changes the
  generic parameter of `RunContext` for every registered tool in that agent — check the
  demonstration tool still type-checks and its two golden cases still pass.
- `run_turn` calls `self._agent.run_sync(...)` (`runtime.py:136-210`). It is
  **synchronous**. Under Decision 1 it is only ever called from tests, so no threadpool
  question arises here; Story 2.7 inherits it.
- The adapter is instrumented content-disabled with no parameter to enable content
  (`runtime.py:96-108`) — AD-12/AD-15. Do not add one.

### Project Structure Notes

New modules, all converging on AR26's structural seed
(`ARCHITECTURE-SPINE.md:293-310`):

```
backend/application/capabilities/__init__.py          NEW
backend/application/capabilities/vocabulary.py        NEW  RiskClassV1 (authoritative)
backend/application/capabilities/deps.py              NEW  AgentDepsV1
backend/application/capabilities/registry.py          NEW  grant composition
backend/application/capabilities/scheduling_inspect.py NEW manifest + handler
backend/application/use_cases/read_scenario_facts.py  NEW  AC2's scenario-read use case
backend/agent/<capability rendering module>           NEW  declarations -> framework tools
backend/evals/golden/scheduling_inspect/*.json        NEW  >=4 cases
backend/tests/...                                     NEW  unit + guard coverage
```

Recorded variances, both inherited and both deliberate:

- Architecture boundary tests live at `backend/tests/architecture/`, not the spine's
  root-level `tests/architecture/`. pytest runs from `backend/` with
  `testpaths = ["tests"]` and `backend/conftest.py` supplies the `sys.path`; a
  root-level suite needs its own conftest, a `testpaths` change, and a second rootdir.
  Carried since Story 2.1.
- `backend/application/capabilities/` is a new package under `application/`, which AR26
  names as *"use cases, policy, state machines, ports, DTOs"*. A capability registry is
  policy; this is inside the seam, not a variance.

### Anti-patterns for this story

```python
# WRONG — the authority decision now depends on a name the model supplied.
@agent.tool
def scheduling_inspect(ctx, request: InspectRequest) -> InspectResult:
    if not ctx.deps.permissions.allows("scheduling_inspect"):
        raise ToolDenied(...)

# RIGHT — the application decided before the Agent existed; an ungranted
# capability is not registered, so there is nothing for the model to name.
granted = compose_granted_capabilities(role=..., site_id=..., policy=..., conversation=...)
runtime = PydanticAIAgentRuntime(model=..., capabilities=granted, deps=deps)
```

```python
# WRONG — a second interpretation of source data, and it fails as wrong
# numbers rather than as a red test.
rows = [r for r in reader.get_demand(conn, sid, GroupQueryV1()).items
        if r.family == "outbound" and r.start_minute >= wednesday_start]

# RIGHT — one interpretation, in the one adapter that owns it.
query = GroupQueryV1(filters=(("family", "outbound"), ("start_minute_gte", start)))
page = read_scenario_facts(reader, conn, scenario_id=sid, group="demand", query=query)
```

```python
# WRONG — trusted context on the turn request. Turns
# test_agent_runtime_port.py:196-204 red, and it is right to.
AgentTurnRequestV1(prompt=..., deps=agent_deps)

# WRONG — a metric the handler invented, which no calculator governs.
return {"coverage_pct": covered / required * 100}

# WRONG — a page presented as the whole truth.
return {"demand_intervals": [asdict(i) for i in page.items]}
# RIGHT — carry the bound.
return InspectResult(items=..., total_count=page.total_count,
                     returned=len(page.items), next_cursor=page.next_cursor,
                     site_id=page.site_id, scenario_version_id=page.scenario_version_id)
```

### References

- [Source: `_bmad-output/planning-artifacts/epics.md:709-737`] — story statement and all
  four acceptance criteria, verbatim; `:715` the acceptance boundary; `:739-767`
  Story 2.6's ownership of `CapabilityManifestV1` and its AC4 dependency on this story.
- [Source: `_bmad-output/planning-artifacts/epics.md:151`] — AR5, the application-owned
  registry and the five risk classes. Note the spine has **no AR numbers**: AR1–AR28 are
  defined normatively in `epics.md`'s Requirements Inventory (`:147-174`) and the spine
  uses AD-1…AD-26. AR5 ≡ AD-5.
- [Source: `.../architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md:72-76`] —
  AD-5 verbatim, the five risk classes and the per-module declaration list.
- [Source: `ARCHITECTURE-SPINE.md:48-52`] AD-1 hexagonal boundary; `:54-58` AD-2 authority
  partition; `:66-70` AD-4 one immutable projection *"Scenario Data queries and agent
  inspection tools consume the same application-owned normalized projection"*;
  `:174-178` AD-15 *"Arbitrary SQL, shell, credentials, unrestricted network, identity
  administration, and runtime capability installation do not exist"*; `:204-208` AD-20
  contract set; `:257` *"tools call use cases, not repositories"*; `:327`
  `CapabilityManifestV1`'s required shape; `:293-310` the structural seed;
  `:447-464` the Deferred table's multiple-roles row.
- [Source: `.../prds/prd-ShiftMind-2026-07-21/prd.md:127-128`] — FR-5 verbatim;
  `:119-120` FR-3; `:130-131` FR-6; `:191-202` the MVP capability catalogue;
  `:209-210` FR-24's viewer/agent parity clause; `:225-231` the autonomy-tier table
  (`Inspect … Automatic`; `Prohibited … Never available`); `:272` budgets are not
  chosen by the model.
- [Source: `.../prds/prd-ShiftMind-2026-07-21/addendum.md:66`] — the normative
  `AgentDeps` contents; `:68-77` the per-tool declaration checklist (note its
  four-class list is superseded by AD-5); `:81-94` the registry rule and *"The later
  agent inspection adapter uses that same service and schema"*; `:18` *"prevents the
  agent adapter from becoming a second interpretation of source data"*.
- [Source: `.../ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md:228-239`] — Flow 1, the
  primary Wednesday journey; `:18` the authority-partition posture.
- [Source: `_bmad-output/planning-artifacts/requirements-inventory.md:49`] — NFR28's
  ≥4-cases-per-capability floor; `:48` NFR27's eleven bindings; `:12-14` the
  FR/NFR/UX-DR/AR sourcing rule.
- [Source: `backend/application/ports/scenario_projection.py:27-177`] — `GroupQueryV1`,
  the six `*PageV1` shapes each carrying `site_id` + `scenario_version_id`, the seven
  group reads and six `resolve_*` methods.
- [Source: `backend/application/contracts/scenario_projection.py:19-122`] —
  `ScenarioOverviewV1`'s saved counts; `WorkerV1`'s nested `qualifications` and
  `availability_windows`.
- [Source: `backend/application/contracts/agent_runtime.py:122-128, 170-188`] —
  `AgentToolCallProposalV1`'s untrusted-name docstring; `AgentTurnRequestV1`'s
  deliberate absence of any authority field.
- [Source: `backend/tests/test_agent_runtime_port.py:185-204`] — the pinned five-field
  set and the forbidden-name loop.
- [Source: `backend/agent/runtime.py:76-131, 136-210`] — the adapter constructor, the
  `Agent` built without `deps_type`, `shiftmind_demonstration`'s registration, and
  `run_turn`'s exception mapping.
- [Source: `backend/agent/translate.py:42-105`] — the whitelist translation and the two
  silent-drop branches Decision 6 leaves open.
- [Source: `backend/evals/cases.py:1-6, 14-33, 56-71, 89-172`] — the risk-class dataset
  tag and Story 2.2's explicit handoff, `GoldenCase`, and the strict loader.
- [Source: `backend/evals/evaluators.py:15-31`] — `EvalVerdict`, `Evaluator` Protocol,
  and `authoritative` gating on `run_source == "double"`.
- [Source: `backend/evals/report.py:43-72, 82-88, 154-170`] — resolve-bindings-then-write,
  the canonical per-case run loop, and `scenario_fixtures` → NFR27 `scenario` binding.
- [Source: `backend/tests/test_evaluation_harness.py:235-251`] — the assertion this story
  must relax and the two coverage assertions it must preserve.
- [Source: `backend/tests/architecture/test_conversation_boundaries.py:13-69`] —
  `GUARDED`, `ALLOWED_LEAKS`, the automatic `use_cases/**` sweep, and the
  suppression-outlives-violation test.
- [Source: `backend/tests/architecture/test_agent_runtime_boundaries.py:48-100, 208-294`] —
  `FORBIDDEN_ROOT_MODULES`, `FRAMEWORK_TYPE_NAMES` (including `RunContext`), and the
  contract-field guard.
- [Source: `backend/api/deps.py:140-210`] — `site_context()`, `get_site_context`,
  `SiteContextOpener`, and the `get_*` seam pattern to copy.
- [Source: `backend/application/use_cases/accept_turn.py:10-18`] — the only existing
  use-case shape.
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md:86-95, 112-131`] —
  `create_agent_runtime()`'s missing model wiring, the `translate.py` silent drops, and
  the `scenario_catalogue` AD-1 leak with its three fix tiers and restated owner.
- [Source: `_bmad-output/implementation-artifacts/2-3-…md:52-62, 115`] — Decision 2
  (accept, do not execute) and the deliberate absence of an `agent_run` UPDATE grant.
- [Source: `_bmad-output/implementation-artifacts/2-4-…md:56-61, 125-136, 432-437`] —
  the `run_in_threadpool` rule, non-disclosure as control flow, and the ledger
  re-annotation precedent this story's Decision 6 follows.
- [Source: `docs/EVIDENCE-CONVENTION.md:9-20, 64-96, 191-199`] — commit → clean →
  measure → generate → commit-separately, and the eleven bindings.

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

## Change Log

| Date | Change |
|---|---|
| 2026-08-11 | Story created on branch `story/2-5-inspect-scenario-facts-through-a-governed-capability`; status ready-for-dev. Six creation-time decisions recorded. |
