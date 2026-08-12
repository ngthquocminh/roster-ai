---
baseline_commit: ba8f86d7f8e6fa85e7992169064a167411080df3
---

# Story 2.6: Add and Remove a Governed Capability Module

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a product engineer,
I want to extend the agent through a versioned governed module,
So that new product capabilities cannot bypass the core authority, evidence, budget, or
evaluation contract.

**This is the generalization story.** Story 2.5 built one governed capability and, by its own
Decision 3, deliberately refused to name its manifest `CapabilityManifestV1`
(`2-5-…md:103-120`). It shipped a module-local `InspectCapabilityManifest`, a registry that
returns a hardcoded 1-tuple, and a renderer keyed by a per-capability dispatch table. Every one
of those is a placeholder this story replaces with the general contract. Story 2.5 is `done` and
green at this story's `baseline_commit` (`ba8f86d`, `main`).

**This story wholly owns FR23** (`epics.md:290`, `:745`, `:1542`). No other story contributes to
it and no later story completes it.

**Story 2.5 handed this story three things by name:**

1. Lift the module-local manifest into the canonical contract — *"2.6 lifts the module-local
   declaration"* (`sprint-status.yaml:84`, `2-5-…md:114`).
2. Remove the unconditional demonstration tool — *"NOT COVERED: the always-present
   `shiftmind_demonstration` seam, which is registered unconditionally and is owned by Story
   2.6's removal proof"* (`backend/agent/runtime.py:155-158`), restated at `2-5-…md:404-407`:
   *"Story 2.6 removes it under its own conformance proof, not this one."*
3. Treat the new runtime rendering seam as the baseline rather than assuming the old
   `backend/agent/**` zero-line fence still stands (`deferred-work.md:10`).

**Unblocks:** governed capability growth beyond the MVP scheduling module. Every later capability
— Epic 3's draft/compute/consequential modules, Epic 4's approval-bearing promotion — is declared
against the contract this story defines. Getting the shape wrong here is paid for five times.

---

### Seven decisions were made at story creation — do not re-litigate them

#### Decision 1 — Removal is proven by **composition**, never by deleting files

AC4 says *"Given the demonstration module is removed"*. The obvious reading — delete the module
and its fixtures, run the suites — **is forbidden by the story's own closing clause**, and its
failure mode is worse than a red test:

- `test_evaluation_harness.py:301` (`"demonstration" in {case.capability for case in cases}`) and
  `:321-336` (`test_every_golden_file_validates…`) go **red** — loudly, which is the good half.
- `:295-300` requires *some* case with `risk_class == "consequential"` and
  `expected_visible_state == "suspended"`. Today the **only** such case in the whole dataset is
  `demonstration-repeat-with-approval.json`. Deleting it silently removes the repo's only proof
  of the approval-suspension shape.
- `evidence/story-2.2/evaluation-harness-demonstration.json` pins both case files by path **and
  sha256** — and this is the quiet part. Verified at creation: `audit_evidence_drift`'s
  `_PATH_HINT_KEYS` (`evidence_binding.py:693-708`) only collects strings found *under* hint keys,
  while those paths are dict **keys** inside `version_bindings.dataset.files`. So deleting them
  does **not** raise drift — the frozen report just goes on asserting digests for files that no
  longer exist, forever, with nothing to notice. Story 2.5 recorded the surrounding rule
  explicitly (`2-5-…md:696-706`): **do not regenerate that evidence file.**

AC4's own second clause is the resolution: **"And historical records retain their
manifest/contract version references. (FR23, AR24)"** — and `epics.md:263-264` confirms Story
2.6's AR24 citation survives AD-24's deferral precisely because it is *"the historical-record
version-retention clause, which Epic 2 still implements."* A removal that erases the historical
record fails the AC it claims to satisfy.

So "removed" means **not installed, not granted, not rendered** — proven by composing the system
without the module and asserting the core is untouched and green. The conformance test drives
`INSTALLED_MODULES` as a parameter rather than reading the global, so the removed-world is a real
composition and not a comment.

#### Decision 2 — `shiftmind_demonstration` is **promoted**, not replaced; the tool name is preserved

Three options existed. Choosing a new name (e.g. `demo_module`) is cleaner in isolation but
leaves the ungoverned always-on tool registered forever, contradicting `runtime.py:157`'s
recorded assignment and leaving FR23's own testable consequence — *"a demonstration capability
can be registered and removed without editing orchestration control flow, remains unavailable by
default"* (`prd.md:205`) — unproven for the one tool that is currently available by default.

This story therefore moves the tool body out of `runtime.py`'s constructor into a governed
module, **keeping the tool name `shiftmind_demonstration` and the eval tag `capability="demonstration"`
byte-identical**. That single choice keeps the two golden cases, the frozen Story 2.2 evidence,
`report.py`'s tool binding, and `test_evaluation_harness.py:301` all true without editing any of
them.

**Its behaviour must not change**: `repeat == 1` executes freely; `repeat > 1` raises
`ApprovalRequired` unless `ctx.tool_call_approved`. Story 2.1 chose conditional approval so one
tool proves both halves of the deferred-call seam (`2-1-…md`, `runtime.py:129-135`), and this
story needs exactly that — it is the only module that can exercise a non-`none` `approval_policy`.

**The cost, stated plainly so it is not discovered at hour six:** the tool stops being
unconditional, so every test that assumed it was present must now compose it. There are ~15
`PydanticAIAgentRuntime(...)` construction sites across `test_agent_runtime_adapter.py`,
`test_agent_runtime_hidden_reasoning.py`, `test_evaluation_harness.py` and `evals/report.py:85`,
plus `test_evaluation_harness.py:46-72`'s `_case_payload()` helper, which hardcodes the tool name
and feeds roughly twelve tests. Budget for it. This churn **is the proof**, not an obstacle to
it: AC2 says loading grants no authority, and a test that got the tool for free was never testing
that.

#### Decision 3 — The manifest is data; the **module declaration** is the executable binding

Do not try to make `CapabilityManifestV1` carry the handler. AD-20 puts it in
`application/contracts`, whose every member is a frozen, pure-data, framework-free dataclass
(verified across all six existing contract modules). A contract holding a callable is a contract
that cannot be serialized into an audit envelope or a durable job payload — and AD-24's retained
clause requires exactly that (*"every durable job stores contract and required-capability
versions"*).

Two types, two homes:

| Type | Home | Contains |
|---|---|---|
| `CapabilityManifestV1` | `application/contracts/capability_manifest.py` | pure declared data — the AD-20 record |
| `CapabilityModuleV1` | `application/capabilities/module.py` | manifest + handler + request type + error type + retryable codes + grant requirements |

`input_schema_ref` stays a dotted **string** on the manifest (the record of which type was
declared); the module declaration carries the actual type object (the thing the renderer builds
a schema from). A test asserts the string resolves to the object — otherwise the record is
decorative.

#### Decision 4 — The renderer becomes generic via `Tool.from_schema`; `_RENDERERS` is deleted

AC3 forbids adding a branch to core agent orchestration control flow. `capability_tools.py:64-66`
is a `dict[str, Callable]` keyed by capability name — adding a second module by adding a second
entry is precisely the branch AC3 forbids, and `_RETRYABLE_CODES` at `:40` is a second one.

**The technical obstacle, and its resolution.** A generic renderer cannot write
`def tool(ctx: RunContext[...], request: SchedulingInspectRequestV1)` — the annotation differs
per module and PydanticAI infers the schema from the signature.

`Tool.from_schema` is the escape, and it was **executed against the installed lock at story
creation**, not read from documentation:

```
$ uv run --frozen python -c "import pydantic_ai; from pydantic_ai import Tool; ..."
version: 2.27.0
has from_schema: True
(function: 'Callable[..., Any]', name: 'str', description: 'str | None',
 json_schema: 'JsonSchemaValue', takes_ctx: 'bool' = False, sequential: 'bool' = False,
 args_validator: 'ArgsValidatorFunc[Any, ...] | None' = None) -> 'Self'
```

So the renderer: builds `json_schema` from the module's declared request type
(`pydantic.TypeAdapter(module.request_type).json_schema()`), passes `takes_ctx=True`, and wraps a
`**kwargs` function that constructs `module.request_type` and calls the handler. One code path,
every module. **Note `args_validator`** — it may be a cleaner place to do the request-type
coercion than inside the function body; either is acceptable, but the coercion must happen
somewhere, because raw model-supplied kwargs reaching a handler is precisely AD-2's failure mode.

If `from_schema` proves awkward, the fallback is a closure whose `__annotations__` are set from
`module.request_type` before registration (PydanticAI resolves signatures through
`typing.get_type_hints`). **Do not** fall back to keeping a per-capability table; record a
blocker instead.

#### Decision 5 — One general `CapabilityError` base, because `except SchedulingInspectError` is the branch

`runtime.py:205-213` catches `SchedulingInspectError` by name and maps `exc.code` to
`failure_reason`. A second module with its own error type needs a second `except` — a branch in
core orchestration, forbidden by AC3.

`CapabilityError` (with a `code: str` class attribute) is defined beside the manifest contract;
`SchedulingInspectError` subclasses it; `runtime.py` catches the base. **Zero behaviour change
for Story 2.5** — every existing subclass keeps its code and every existing assertion keeps
passing.

**A live inconsistency this uncovers, and what to do about it.**
`AgentFailureReasonV1 = Literal["budget_exhausted","provider_error","invalid_output","cancelled"]`
(`contracts/agent_runtime.py:46-51`), but `runtime.py:211` already assigns `exc.code` — values
like `"scenario_not_found"` — into `failure_reason`. That is a pre-existing type violation on the
exact line this story generalizes. Task 6 fixes it honestly: widen the field's declared type and
add the invariant that makes the wider type safe — **any `failure_reason` outside
`AgentFailureReasonV1` must appear in a granted manifest's declared `errors` tuple.** That
converts a silent lie into a checked contract. If it proves invasive, deferring is acceptable
**only** with a `deferred-work.md` entry naming an owner; leaving it undocumented is not.

#### Decision 6 — Installation is a **static tuple**. No dynamic discovery, ever

AD-15 (`ARCHITECTURE-SPINE.md:178`): *"Arbitrary SQL, shell, credentials, unrestricted network,
identity administration, and **runtime capability installation do not exist.**"*

The tempting implementation of "modules can be added" is a plugin mechanism — `pkgutil.iter_modules`
over `application/capabilities/`, an entry-point group, a config-driven import list. **All are
forbidden.** `INSTALLED_MODULES: tuple[CapabilityModuleV1, ...]` is a literal tuple in one module,
resolved at import time. Adding a capability is a source change reviewed like any other; that is
the feature, not a limitation.

An architecture guard asserts no module under `application/capabilities/` or `backend/agent/`
imports `importlib`, `pkgutil`, or `entry_points`.

#### Decision 7 — Grant requirements are declared **by the module**, evaluated **by the registry**

`compose_granted_capabilities` currently reads:

```python
if (context.role != PLANNER_ROLE
    or context.site_id != context.conversation_site_id
    or SCHEDULING_INSPECT_POLICY not in context.feature_policy
    or context.conversation_id in context.revoked_conversation_ids):
    return ()
return (scheduling_inspect_manifest(),)
```

Every clause is correct; three of the four are **general** (site match, conversation not revoked,
role) and one is **module-specific** (`scheduling_inspect_enabled`). The general clauses stay in
the registry; the specific one moves onto the module declaration as
`required_feature_policy: str` and `required_role: str`. The registry then evaluates declared
requirements against trusted context in a loop — no capability name appears in registry control
flow.

**Grant remains composed before the runtime is constructed** and an ungranted capability is
**absent**, never present-and-refusing (Story 2.5 Decision 4, `sprint-status.yaml:90-95`;
AD-2). PydanticAI's `prepare=` hook may be a second gate, never the first — and it is not used
anywhere in the repo today, which is correct.

**The reduction this story inherits, and must not paper over:** `role`, `feature_policy` and
`policy_version` still have no database-backed supplier (`deferred-work.md:9`). This story does
not fix that and must not fabricate a role table. It must keep the constants *branched on* so a
real supplier is a change of supplier, not of shape — the same posture Story 2.5 was held to.

---

## Acceptance Criteria

1. **Given** a demonstration capability module **when** it is registered **then** its
   `CapabilityManifestV1` declares versioned input/output schemas, permission and site/resource
   scope, risk class, approval policy, budget/timeout, version/idempotency rules, safe
   audit/evidence mapping, errors, and evaluation fixtures **and** the registry rejects any
   incomplete manifest. *(FR23, AR5, AR20)*

2. **Given** a complete registered module **when** authenticated role, site, feature policy, or
   conversation context does not grant it **then** the capability is absent from the run and
   cannot be invoked by model-generated names or arguments **and** loading the module grants no
   authority by itself. *(FR23)*

3. **Given** the module is granted for a deterministic test context **when** it executes **then**
   it uses trusted dependencies, application use cases, current versions, policy, budgets,
   idempotency, evidence, and audit like the scheduling module **and** no branch is added to core
   agent orchestration control flow. *(FR23, AR2)*

4. **Given** the demonstration module is removed **when** the Story 2.2 harness runs the
   conformance and regression suites **then** core AgentRuntime and the Story 2.5 scheduling
   inspect capability require no code change and remain green **and** historical records retain
   their manifest/contract version references. *(FR23, AR24)*

## One honest gap, raised for review rather than papered over

**AC3 requires the demonstration module to use "evidence and audit like the scheduling module."
Neither exists yet as a mechanism.** Verified at creation: `EvidenceRefV1` exists
(`contracts/evidence_ref.py`) but no capability emits one — Story 2.7 owns grounding and
`AuditEnvelopeV1` has no implementation anywhere in `backend/`. The scheduling module satisfies
this clause today by *declaring* `audit_mapping` and `evidence_mapping` as manifest strings and
nothing more.

So "like the scheduling module" is satisfiable at exactly that level: the demonstration module
declares both mappings, and a conformance test asserts every installed module declares them
non-empty. **Do not build an audit-envelope writer or an evidence emitter in this story** — that
pre-empts Story 2.7 and Epic 4's `AuditEnvelopeV1`, and would put an ungoverned second
implementation in the repo before the contract that governs it exists.

What this story *can* honestly prove, and must: that the declaration is **required, validated,
and non-empty for every installed module**, so the first story that implements emission has a
populated mapping to implement against rather than a nullable field nobody filled in. Record the
reduction in the module docstring in the `SCOPE_CONTROLS` "NOT COVERED" style Story 2.5
established — a claim that outlives its enforcement is the defect the 2.1 review fixed in a guard
docstring.

## Tasks / Subtasks

- [x] **Task 1: `CapabilityManifestV1` — the canonical AD-20 contract** (AC: #1)
  - [x] New file `backend/application/contracts/capability_manifest.py`. Frozen dataclass, module
        docstring citing AD-5/AD-20, explicit `__all__` — match `contracts/stream_cursor.py`, the
        closest existing example. **Not a pydantic `BaseModel`**: every member of
        `application/contracts` is a frozen dataclass and `test_agent_runtime_boundaries.py:293`
        sweeps this directory for framework-typed fields.
  - [x] Carry every field of `InspectCapabilityManifest` (`scheduling_inspect.py:123-139`) —
        that list already satisfies AC1's enumeration — **plus** `schema_version: str = SCHEMA_VERSION`.
        The spine's Normative contract minimums (`ARCHITECTURE-SPINE.md:314`) require it of every
        contract, and the module-local declaration is the one type in the repo missing it.
  - [x] `approval_policy` becomes a closed `ApprovalPolicyV1 = Literal["none", "exact_action"]`,
        not a bare `str`. AD-5 distinguishes consequential (needs exact-action approval) from the
        rest; the demonstration module is the first thing in the repo that needs a non-`none`
        value, so an open string would let a typo silently mean "no approval".
  - [x] Do **not** add `site_id`. The manifest is a declaration, not a site-owned resource
        (`ARCHITECTURE-SPINE.md:314` scopes that minimum to site-owned resources); site scope is
        carried by the `scope` field as text and enforced by `AgentDepsV1`.
  - [x] Define `CapabilityError(Exception)` with `code: str = "capability_error"` in this same
        module — the general base Decision 5 requires.
  - [x] **Acceptance boundary:** a test asserts the frozen dataclass has exactly the declared
        field set (the same shape-pinning `test_agent_runtime_port.py:196-204` uses), and that
        `CapabilityManifestV1` is reachable from `application.contracts`.

- [x] **Task 2: Completeness validation — what "incomplete" means, as code** (AC: #1)
  - [x] `validate_manifest(manifest) -> None`, raising `IncompleteManifestError` (a
        `ValueError` subclass). AC1's *"the registry rejects any incomplete manifest"* has **no
        implementation today** — this is net-new behaviour, not a refactor.
  - [x] Reject, each as its own case: any empty string field; `errors` empty; `evaluation_fixtures`
        empty; `budget_limit < 1`; `timeout_seconds <= 0`; `risk_class` outside `RiskClassV1`;
        `approval_policy` outside `ApprovalPolicyV1`; `input_schema_ref`/`output_schema_ref` not a
        dotted path of at least two segments; `capability_name` not a valid Python identifier
        (it becomes a tool name the model types).
  - [x] **Do not read the filesystem here.** `evaluation_fixtures` are validated as *shape* in the
        application layer; their *existence on disk* is asserted by the conformance test (Task 9).
        `application/**` reaching for files is a boundary smell and would make manifest validation
        depend on the working directory.
  - [x] Validation runs at **registration** — i.e. when `INSTALLED_MODULES` is composed and again
        in `compose_granted_capabilities` before anything is granted. An invalid manifest must
        never reach the renderer.
  - [x] **Acceptance boundary:** a table-driven test over at least the ten rejection cases above,
        each built by `dataclasses.replace`-ing a valid manifest so the test cannot drift from the
        real shape, plus one accepting case per installed module.

- [x] **Task 3: `CapabilityModuleV1` and the static installed set** (AC: #1, #2)
  - [x] `backend/application/capabilities/module.py` — frozen dataclass `CapabilityModuleV1`:
        `manifest: CapabilityManifestV1`, `handler: Callable[..., object]`,
        `request_type: type`, `error_type: type[CapabilityError]`,
        `retryable_error_codes: frozenset[str]`, `required_role: str`,
        `required_feature_policy: str`.
  - [x] `backend/application/capabilities/installed.py` — `INSTALLED_MODULES: tuple[CapabilityModuleV1, ...]`,
        a **literal tuple** naming the scheduling module and the demonstration module. Per
        **Decision 6** there is no discovery, no config, no entry points.
  - [x] Module docstring states the AD-15 rule in one line so the next person does not "improve"
        it into a plugin loader.
  - [x] Both new modules land inside `application/capabilities/`, which
        `tests/architecture/test_conversation_boundaries.py:26-29` already sweeps **whole** —
        its comment names this story ("2.6 adds and removes modules under it"), so they inherit
        the sqlalchemy/fastapi fence automatically. Note `:83`'s
        `len(capability_modules) >= 5` is currently *exactly* 5; this story raises it to 8, and
        the removed-world composition never deletes a file, so it stays satisfied.
  - [x] **Acceptance boundary:** an architecture guard asserts no file under
        `backend/application/capabilities/` or `backend/agent/` imports `importlib`, `pkgutil`, or
        references `entry_points`; and a test asserts every entry of `INSTALLED_MODULES` passes
        `validate_manifest` and that `manifest.input_schema_ref` resolves to `module.request_type`.

- [x] **Task 4: Generalize the registry — grant by declared requirement, not by name** (AC: #2)
  - [x] Rewrite `compose_granted_capabilities` per **Decision 7**: keep the general clauses
        (`site_id == conversation_site_id`, `conversation_id not in revoked_conversation_ids`) as
        run-level gates; evaluate `required_role` and `required_feature_policy` **per module**.
        `SCHEDULING_INSPECT_POLICY` moves out of `registry.py` onto the scheduling module's
        declaration. **No capability name may appear in registry control flow** — a test greps
        the module's own source for the literals `scheduling_inspect` and `shiftmind_demonstration`
        and fails if either is present.
  - [x] Signature becomes `compose_granted_capabilities(context, modules=INSTALLED_MODULES) -> tuple[CapabilityModuleV1, ...]`.
        The `modules` parameter is what makes **Decision 1**'s removal proof a real composition;
        default it so every existing caller is unchanged.
  - [x] Return granted **modules**, not manifests — the renderer needs the handler. Keep
        `resolve_granted_capability` working against the new element type.
  - [x] `api/deps.py:88-101`'s `CapabilityComposer` alias and `get_capability_registry()` follow
        the new types. No route consumes it yet; that stays true (Story 2.7 owns the request path).
  - [x] Keep `CapabilityGrantContextV1`'s docstring honest about which fields are still constants
        (`deferred-work.md:9`). Its wording is already correct — update it only where the shape
        actually changed.
  - [x] **Acceptance boundary:** a matrix test over {granted, wrong role, missing feature policy,
        site mismatch, revoked conversation} × {scheduling, demonstration} asserting the exact
        granted tuple — including that a context granting one module grants *only* that one.

- [x] **Task 5: Generalize the renderer — delete `_RENDERERS`** (AC: #2, #3)
  - [x] Rewrite `backend/agent/capability_tools.py` per **Decision 4**: one
        `_register_module(agent, module, deps)` building the tool through `Tool.from_schema`
        (schema from `TypeAdapter(module.request_type).json_schema()`), wrapping a function that
        validates kwargs into `module.request_type`, calls `module.handler(ctx.deps, request, module.manifest)`,
        and maps `module.error_type` with a code in `module.retryable_error_codes` to `ModelRetry`.
  - [x] `_RENDERERS` and the module-level `_RETRYABLE_CODES` are **deleted**. `UnknownCapabilityError`
        survives but changes meaning: it can no longer mean "no renderer exists" (every module is
        renderable by construction), so it retains only the duplicate-grant case. Update its
        docstring — a comment that outlives its cause is worse than none.
  - [x] Preserve exactly: `ctx.deps is None` → `RuntimeError("trusted agent dependencies are unavailable")`;
        `deps is None` at render time → `ValueError(f"{name} requires trusted AgentDepsV1")`;
        duplicate grant → `UnknownCapabilityError`; and `registered_capability_names` collected as
        each tool is actually registered, never mirroring the input (that regression was a 2.5
        review finding — `2-5-…md:557`).
  - [x] `RunContext`, `ModelRetry`, `Tool` and every other framework type stay inside this package.
        `test_agent_runtime_boundaries.py`'s 40-name `FRAMEWORK_TYPE_NAMES` sweep and
        `FORBIDDEN_ROOT_MODULES` already cover `application/**`; do not weaken either.
  - [x] **Acceptance boundary:** `test_a_granted_capability_with_no_renderer_fails_loudly`
        (`test_scheduling_inspect.py:515`) is now unreachable as written — replace it with a test
        that a module whose `request_type` cannot produce a JSON schema fails **at registration**,
        loudly, rather than at first model call. Keep `test_a_capability_granted_twice_is_rejected`
        green unmodified.

- [x] **Task 6: One error base, one failure-reason contract** (AC: #3)
  - [x] `SchedulingInspectError` subclasses `CapabilityError`. No code, message, or `ERROR_CODES`
        value changes — verify by leaving every existing assertion in `test_scheduling_inspect.py`
        untouched and green.
  - [x] `runtime.py:205` becomes `except CapabilityError`. **This is the only edit to `run_turn`'s
        control flow this story makes**, and it *removes* a per-capability branch rather than
        adding one — which is what AC3 requires.
  - [x] Per **Decision 5**, address `AgentFailureReasonV1`: widen `AgentRunOutcomeV1.failure_reason`
        to admit a manifest-declared error code, document both sources in the field's docstring,
        and add the invariant test — **any `failure_reason` not in `AgentFailureReasonV1` must
        appear in a granted manifest's `errors`**. If this proves invasive, defer it with a
        `deferred-work.md` entry naming an owner; do not leave it silent.
  - [x] **Acceptance boundary:** a test drives each installed module to raise its own declared
        error and asserts the outcome is an owned `AgentRunOutcomeV1` whose `failure_reason` is in
        that module's manifest `errors` — never a raw builtin crossing the port.

- [x] **Task 7: Migrate the scheduling module onto the general contract** (AC: #4)
  - [x] Delete `InspectCapabilityManifest`; `scheduling_inspect.py` imports `CapabilityManifestV1`.
        A type **alias** is not acceptable — Story 2.5 named this a one-file refactor
        (`2-5-…md:117-120`) and an alias leaves two names for one contract.
  - [x] Add the module's `CapabilityModuleV1` declaration beside `scheduling_inspect_manifest()`,
        carrying `required_feature_policy="scheduling_inspect_enabled"`, `required_role="planner"`,
        `retryable_error_codes=frozenset({"invalid_query"})` (moved verbatim from
        `capability_tools.py:40`), and `approval_policy="none"` unchanged.
  - [x] Update `PydanticAIAgentRuntime.__init__`'s `capabilities:` parameter type from
        `tuple[InspectCapabilityManifest, ...]` to `tuple[CapabilityModuleV1, ...]`, and
        `runtime.py:45-48`'s direct imports from `application.capabilities.scheduling_inspect`
        become imports of the general types. **After this task, `backend/agent/**` names no
        specific capability** — that is the mechanical statement of AC3, and a test asserts it.
  - [x] **Behaviour must not change.** Every assertion in `test_scheduling_inspect.py` about
        manifest values, `SCOPE_CONTROLS`, error codes, allow-listing, `budget_limit` clamping and
        site/version mismatch stays green **unmodified** apart from type names and the
        manifest→module change at construction sites.
  - [x] **Acceptance boundary:** `test_scheduling_inspect.py` passes with no assertion weakened;
        `git diff` on the assertion bodies is limited to type/constructor renames.

- [x] **Task 8: Promote `shiftmind_demonstration` into a governed module** (AC: #1, #3)
  - [x] New `backend/application/capabilities/demonstration.py`: `DemonstrationRequestV1`
        (frozen dataclass, `label: str`, `repeat: int = 1` — moved out of `runtime.py:52`, and it
        becomes a dataclass like every other application type rather than a pydantic model),
        `DemonstrationResultV1`, `DemonstrationError(CapabilityError)` subclasses with codes, a
        `demonstration_manifest()` factory, and the handler.
  - [x] Manifest values, chosen deliberately: `risk_class="consequential"` (it is the only module
        that suspends for approval, and AD-5 ties exact-action approval to that class),
        `approval_policy="exact_action"`, `permission="demonstration:execute"`,
        `scope="current_site/current_conversation"`,
        `evaluation_fixtures=("evals/golden/demonstration/repeat-once.json", "evals/golden/demonstration/repeat-with-approval.json")`
        — the two existing files, which is why they must not be deleted.
  - [x] `idempotency_semantics` must be a real statement, not filler: the handler is pure over its
        arguments and AD-8 scopes tool-effect keys to `(agent_run_id, tool_call_id)`; say that.
        Same for `audit_mapping`/`evidence_mapping` — declare them per the **honest gap** section
        above, with the `NOT COVERED` reduction recorded in the docstring.
  - [x] The handler takes `AgentDepsV1` like the scheduling handler (AC3: "uses trusted
        dependencies"), reads `deps.remaining_budget` for the same budget precheck, and touches no
        repository, no projection, no scenario data. It must remain something that "resembles no
        real capability" (`2-1-…md:105`).
  - [x] **Approval behaviour is preserved exactly**: `repeat > 1` and not approved →
        `ApprovalRequired`. That exception is a **framework type** and may only be raised in
        `backend/agent/` — so the handler raises a typed application signal and the renderer maps
        it, the same shape Story 2.5's review used for `ModelRetry` (`2-5-…md:550`). Getting this
        backwards puts `pydantic_ai` in `application/**` and turns the architecture guard red.
  - [x] Delete the inline tool and `DemonstrationRequestV1` from `runtime.py:52-60, 125-140`.
        Update `registered_capability_names`' docstring — its "NOT COVERED" clause is now false.
  - [x] **Acceptance boundary:** with the module granted, a scripted double reproduces both
        existing golden cases byte-for-byte (`completed` for `repeat=1`, `suspended` for
        `repeat=2`); with it ungranted, `"shiftmind_demonstration" not in agent._function_toolset.tools`.

- [x] **Task 9: The conformance suite — parametrized over every installed module** (AC: #1, #2, #3)
  - [x] New `backend/tests/test_capability_conformance.py`, parametrized over `INSTALLED_MODULES`
        so **a future module inherits every assertion by existing**. This is the artifact
        `ARCHITECTURE-SPINE.md:442` names ("capability registry and module conformance tests") and
        it is the story's most durable deliverable.
  - [x] Per module, assert: manifest passes `validate_manifest`; `input_schema_ref`/`output_schema_ref`
        resolve to real types; every path in `evaluation_fixtures` **exists on disk** (the check
        Task 2 deliberately kept out of the application layer); `errors` is non-empty and every
        code is reachable from a declared exception class; `audit_mapping`/`evidence_mapping`
        non-empty; the handler module imports none of `{sqlalchemy, adapters, fastapi, pydantic_ai}`
        (reuse the AST walk at `test_scheduling_inspect.py:440-459`, which must check
        `ast.ImportFrom` as well as `ast.Import` — walking only `ast.Import` was 2.5 review
        finding 7).
  - [x] Assert the grant-by-absence invariant per module: ungranted → the tool name is absent from
        `agent._function_toolset.tools`, and a model-supplied call to that name cannot execute.
  - [x] **Include a self-redness proof.** Story 2.5's review found a guard shipped without one
        (finding 9) and the fix produced the `SWEPT_PACKAGES` mechanism; hold this suite to the
        same bar — construct a deliberately non-conforming module in-test and assert the suite
        rejects it.
  - [x] **Acceptance boundary:** the suite is green over both installed modules, and demonstrably
        red for a synthetic module missing any one required declaration.

- [x] **Task 10: The removal proof** (AC: #4)
  - [x] Per **Decision 1**, a test composes `compose_granted_capabilities(context, modules=<INSTALLED_MODULES without demonstration>)`
        and asserts: the demonstration tool is absent from the real tool set; `scheduling_inspect`
        still grants, renders and executes to a `completed` outcome; and the full
        `test_scheduling_inspect.py` surface is unaffected.
  - [x] Assert **no core file names the demonstration module**: `agent/runtime.py`,
        `agent/capability_tools.py`, `agent/translate.py`, `application/capabilities/registry.py`,
        `application/capabilities/module.py` and `application/contracts/capability_manifest.py`
        must not contain the literal `demonstration`. Source-level, because that is the mechanical
        meaning of "require no code change" — and it is the same check that proves AC3's "no branch
        added" for the *next* module too.
  - [x] Assert the **historical-record clause** directly: `evidence/story-2.2/evaluation-harness-demonstration.json`
        still resolves every `referenced_paths` entry and its recorded `capability`/`case_version`
        values still match the on-disk cases, in the removed-world composition. This is AR24's
        retained clause and it is the half of AC4 most likely to be skipped.
  - [x] **Do not** delete files, and **do not** regenerate the Story 2.2 evidence file
        (`2-5-…md:696-706`).
  - [x] **Acceptance boundary:** all three assertions green, and the removed-world composition is
        exercised by a real `PydanticAIAgentRuntime` rather than asserted about a tuple.

- [x] **Task 11: Eval harness, golden cases, and the NFR28 exemption** (AC: #4)
  - [x] The two demonstration golden cases are **unchanged on disk** (their sha256 is pinned by
        frozen evidence). `evals/report.py:85` constructs a runtime with **no `capabilities=` and
        no `deps=`**, so demonstration cases would now find no tool — fix the report generator to
        compose each case's granted modules from its `capability` tag, the way
        `test_evaluation_harness.py:110-156`'s `_run_case` already does.
  - [x] **This also fixes a live pre-existing hole, so do not treat it as refactoring.** The five
        `scheduling_inspect` cases already route a tool that does not exist on that agent — Story
        2.5 did not update the report generator. Verified at creation: `generate_demonstration_report`
        has **zero test callers** (only `report.py:75,187,199` reference it), which is exactly why
        nothing went red. AC4's "the Story 2.2 harness runs the conformance and regression suites"
        means the report generator too, not pytest alone.
  - [x] `report.py:32-40`'s `DEMONSTRATION_BINDINGS["tool"]` still says "from the Story 2.1
        AgentRuntime adapter". Derive the tool binding from the granted manifests instead of
        hardcoding it — NFR27 requires the report bind the *tool* version, and a hardcoded string
        stops being true the moment a capability version moves.
  - [x] **Confront the NFR28 exemption rather than inheriting it.** `test_evaluation_harness.py:312-317`
        exempts `"demonstration"` from the ≥4-per-capability floor because "Story 2.2 contributed
        exactly two". Once demonstration is a *granted capability*, that justification no longer
        describes reality. Verified against `prd.md:191-202`: the MVP capability catalogue lists
        six product capabilities and a demonstration module is not among them — so the honest
        position is that NFR28's floor reads on **allowed product capabilities**, and the
        exemption survives with its rationale **restated in those terms and asserted**, not with
        a bare name check. Choose that or contribute four genuine cases; **do not pad**
        (`epics.md:1527`), and do not leave the stale rationale in place.
  - [x] `test_evaluation_harness.py:301`'s `"demonstration" in {…}`, the `>= 2` assertion, and
        `:295-300`'s consequential-and-suspended coverage all stay green **unmodified** — Decision
        2 exists so they can. One line does need re-authoring: `:290`'s comment asserts *"no later
        story may remove them"*, which contradicts this story's AC4. Restate it as what is
        actually true — the **cases** are permanent; the module's **installation** is not.
  - [x] **Acceptance boundary:** `uv run --frozen python -m evals.report` (or its existing entry
        point) produces a report whose tool binding names both granted capabilities and whose
        demonstration cases actually route to a registered tool.

- [x] **Task 12: Fences, ledger, baselines, Gate A** (AC: #4)
  - [x] **Zero-line diff required** in: `backend/agent/translate.py`, `backend/services/**`,
        `backend/domain/**`, `backend/engine/**`, `backend/llm/**`, `backend/migrations/**`,
        `backend/adapters/**`, `backend/tests/test_gate_a_mutation_audit.py`, and **all of
        `frontend/`**. This story adds **no migration and no dependency** — PydanticAI 2.27.0 is
        already a repository lock, so no AR27 ceremony is owed.
  - [x] `deferred-work.md:10` is the entry that names this story by owner. **Close it** — its
        instruction ("treat the new runtime rendering seam as the baseline") is discharged by this
        story. Correct its stale text first: it says only `runtime.py` was modified, but review
        commit `6f77a40` also added `backend/agent/capability_tools.py`.
  - [x] Do **not** close: the `translate.py` silent-drop item (`:100`, owner is the first story
        that persists and rehydrates an `AgentTurnV1` — not this one, which persists none); the
        `ScenarioCatalogueReader` AD-1 leak (`:123-140`, its trigger is modifying that port, which
        this story does not); `create_agent_runtime()`'s missing live-model wiring (`:95`, Story 2.7).
        Leave `ALLOWED_LEAKS` untouched.
  - [x] Add a ledger entry for the eval-report pass-signal gap (`deferred-work.md:108`) if this
        story's report changes touch it, and for the `AgentFailureReasonV1` widening if Task 6 defers.
  - [x] Re-derive regression baselines rather than trusting the recorded ones — that is this
        repo's standing rule and it has caught a stale figure twice. **The most recent real
        numbers are in `6f77a40`'s commit message, not in the story file:** backend **645 passed /
        2 skipped / 7 deselected**, postgres 43, evidence convention 48, alembic no new upgrade
        operations. Story 2.5's Completion Notes still say 610 — they predate its own review
        patches. Frontend 55 files / 322 tests; e2e 46. The 7 deselected are `@pytest.mark.live`
        (`addopts = -m "not live"`); the documented skip is `test_evidence_binding.py:350`'s
        clean-tree self-skip.
  - [x] **Re-run Gate A per AR28** (`docs/GATE-A-RUNBOOK.md` §3) and confirm `gate_a_passed: true`
        with `blocking: []`. **Known trap:** the gate cannot be run twice in a row — it writes into
        `evidence/`, dirtying the tree, so the next `resolve_bindings()` raises `DirtyTreeError`
        (`deferred-work.md:90`). Story 2.5 handled this by committing evidence, then rebinding in a
        second commit (`5586717` → `ba8f86d`); expect the same two-commit sequence.
  - [x] **Acceptance boundary:** every fence verified empty by `git diff --stat`, the ledger
        reflects reality, and the Gate A report is bound to a clean tree at this story's commit.

## Dev Notes

### What this story is, and what it is not

| In scope | Out of scope | Owner |
|---|---|---|
| `CapabilityManifestV1` in `application/contracts` | Grounding, `EvidenceRefV1` emission, NFR12 | Story 2.7 |
| Registry rejection of incomplete manifests | Any HTTP route, `agent_run` state transition, migration | Story 2.7 |
| Generic renderer; deletion of `_RENDERERS` | Clarification / refusal / injection variants | Story 2.9 |
| The governed demonstration module | Audit envelope writer, `AuditEnvelopeV1` | Epic 4 |
| Add/remove conformance suite | `JobLeaseV1`, durable capability versions | Epic 3 |
| One general `CapabilityError` | Real role/policy suppliers | deferred (`:9`) |

**No frontend change. No migration. No new dependency. No new API route.** Story 2.5's Decision 1
established that Epic 2 capability work composes at the seam rather than on a request path, and
Story 2.7 is the first story to execute a turn on one.

### The traps, ranked by how quietly they fail

1. **Deleting the demonstration golden cases to prove "removal".** Fails as a red
   `test_evidence_convention.py` sweep — but only *after* you have restructured the suite around
   deletion. **Decision 1** exists to stop this at hour zero.
2. **Reimplementing `_RENDERERS` as a `match` statement or an `if isinstance` chain.** Reads as
   cleanup, is the exact branch AC3 forbids, and will not fail any test you write yourself. Task
   10's source-level assertion is the mechanical defence.
3. **Building a plugin loader** because "add a module" sounds like discovery. Forbidden by AD-15's
   *"runtime capability installation do not exist"*. Fails as a security-model violation that no
   functional test detects.
4. **Raising `ApprovalRequired` from `application/capabilities/demonstration.py`.** The natural
   translation of the existing code, and it puts a `pydantic_ai` import in the application layer.
   This one *does* fail loudly (`test_agent_runtime_boundaries.py`), which is why it is ranked
   below the silent ones — but it will cost an hour if discovered late.
5. **Aliasing `InspectCapabilityManifest = CapabilityManifestV1`** to avoid touching call sites.
   Leaves two names for one versioned contract, which is the compatibility event Story 2.5's
   Decision 3 spent a whole decision avoiding.
6. **Letting the demonstration module inherit the NFR28 floor exemption silently.** It is a name
   check today; once demonstration is a granted capability the comment beside it is false. Task 11
   requires a decision, not inheritance.

### Existing conventions to match, not reinvent

- **Contract style** (`contracts/stream_cursor.py` is the model): `from __future__ import annotations`
  on line 2, `SCHEMA_VERSION = "1"` module constant, frozen dataclasses only, `V1` suffix on every
  type including `Literal` aliases, module docstring that explains *why the shape is this shape*
  and cites AD numbers, explicit `__all__`.
- **Scope-as-data** (`scheduling_inspect.py:36-58`): a `Mapping[str, str]` where every value names
  what the control does **and** what it does `NOT COVER`, asserted by a test. Use this for the
  audit/evidence reduction in the demonstration module.
- **Deferred settings import** (`scheduling_inspect.py:146`): `from settings import default_settings`
  inside the factory, not at module scope — `application/**` must be importable without process
  configuration.
- **Error shape**: exception classes carrying a `code` class attribute, plus a module-level
  `ERROR_CODES` tuple that the manifest declares. Mirror it.
- **Test doubles**: `build_model_double(case)` from the Story 2.2 harness with `models.ALLOW_MODEL_REQUESTS = False`
  at module scope. Nothing in this story may reach a network or skip itself — Story 1.11
  established that a skipped test is not a passed test.
- **Distinct UUIDs per identity field** in `AgentDepsV1` fixtures. Sharing one `uuid4()` made
  every scope assertion vacuous; that was 2.5 review finding 8.

### Latest technical information (verified 2026-08-11 against the pinned lock)

- **PydanticAI 2.27.0** is a repository lock (`ARCHITECTURE-SPINE.md:271`), landed by Story 2.1
  under AD-19's same-evidence clause. **No dependency is added by this story**, so AR27's
  add-and-lock-at-the-gate ceremony is not owed.
- `Tool.from_schema(function, name, description, json_schema, takes_ctx=False, sequential=False,
  args_validator=None)` — **signature executed against the installed 2.27.0 at story creation**,
  not read from docs. This is the mechanism **Decision 4** depends on; no re-verification is owed.
- `FunctionToolset(tools=[...])` and `add_function(...)` are alternative composition routes if
  per-run toolsets read better than per-run agents. Either is acceptable; **grant must still be
  composed before construction** (AD-2), so a toolset assembled from already-granted modules is
  fine and a toolset filtered at call time is not.
- `ApprovalRequired`, `ModelRetry`, `RunContext`, `DeferredToolRequests`, `ToolDenied` and
  `CancellationToken` are already imported and exercised by `runtime.py`; none of their behaviour
  changes here.
- Python floor is 3.10 (`>=3.10,<3.13`); the venv is 3.10.9. Avoid 3.11+ syntax.

### Project Structure Notes

- `backend/application/contracts/capability_manifest.py` — **new**, the AD-20 name.
  `test_agent_runtime_boundaries.py:380-394` parametrizes over contract/port modules by name "so a
  future refactor that deletes them fails loudly"; add the new module to that list.
- `backend/application/capabilities/{module,installed,demonstration}.py` — **new**, inside the
  package Story 2.5 created. `2-5-…md:764-766` already recorded that `application/capabilities/`
  is policy living inside the seam, not a structural variance.
- `backend/tests/test_capability_conformance.py` — **new**. Architecture guards stay in
  `backend/tests/architecture/` per Story 2.1's recorded AR26 variance (one rootdir, one
  `conftest.py`); this is an acceptance suite, so it sits beside `test_scheduling_inspect.py`.
- No new port. The `AgentRuntime` port signature is **unchanged** — `registered_capability_names`
  remains a concrete-adapter property, not a port method.

### References

- `_bmad-output/planning-artifacts/epics.md:739-767` — Story 2.6 ACs
- `epics.md:69` (FR23), `:290`, `:1542` — sole ownership; `prd.md:204-205` — FR23 normative form
  and its testable consequence
- `epics.md:148` (AR2), `:151` (AR5), `:166` (AR20), `:170` + `:263-264` (AR24 + the exemption
  that keeps Story 2.6's citation live), `:172` (AR26), `:173` (AR27), `:174` (AR28)
- `ARCHITECTURE-SPINE.md:72-76` (AD-5), `:54-58` (AD-2), `:48-52` (AD-1), `:174-178` (AD-15,
  "runtime capability installation do not exist"), `:204-208` (AD-20), `:132-136` (AD-8),
  `:228-233` (AD-24, and the durable capability-version clause), `:312-314` + `:327`
  (`CapabilityManifestV1` required shape and the `schema_version` minimum), `:442` (FR-23 →
  "capability registry and module conformance tests")
- `prd.md:191-202` — the six-capability MVP catalogue, the basis for Task 11's NFR28 reading
- `epics.md:129` (NFR28), `:127` (NFR27), `:1527` (dataset-threshold caveat — never pad)
- `_bmad-output/implementation-artifacts/2-5-…md:103-126` (Decision 3 and its `approval_policy`
  trap), `:404-407` (the `shiftmind_demonstration` handoff), `:544-567` (review findings this
  story must not regress), `:696-706` (do not regenerate the Story 2.2 evidence)
- `deferred-work.md:9` (constant role/policy), `:10` (this story's named entry), `:90` (the
  double-run Gate A trap), `:100`, `:108`, `:123-140` (entries this story must **not** close)
- `docs/GATE-A-RUNBOOK.md` §3 — AR28 re-run; `docs/EVIDENCE-CONVENTION.md` — commit, measure,
  generate, commit separately
- Code: `application/capabilities/{registry,scheduling_inspect,deps,vocabulary}.py`,
  `agent/{runtime,capability_tools}.py`, `contracts/agent_runtime.py:46-51`,
  `tests/test_evaluation_harness.py:301,312-317`, `evals/report.py:32-40,85`

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Implementation Plan

- Introduce the pure manifest contract and executable module declaration first, then validate both at registration.
- Generalize grant composition and PydanticAI rendering without capability-name branches.
- Promote scheduling and demonstration onto the module contract, then prove conformance, removal, historical retention, and regression behavior.
- Re-run all repository gates and bind Gate A evidence to a clean implementation commit.

### Debug Log References

- Customization resolver fell back to manual TOML merge because the ambient Python lacked `tomllib`; no team/user overrides existed.
- The first parallel Playwright Gate A capture exceeded 180 seconds at 36/46 cases; a single-worker rerun completed all 46 cases in 3.9 minutes.
- Gate A report binds clean implementation commit `02b7100085991f1201983c6348327133344bc43c`; evidence committed separately as `bf0a61d`.

### Completion Notes List

- Added canonical `CapabilityManifestV1`, completeness validation, `CapabilityModuleV1`, and a static two-module installation set.
- Replaced capability-specific grant/render branches with declared requirements and one generic `Tool.from_schema` renderer.
- Promoted `shiftmind_demonstration` into a governed module while preserving exact-action approval and both frozen golden cases.
- Added inherited conformance, removed-world composition, core-name-agnostic, and historical digest/version retention proofs.
- Updated evaluation report generation to grant the case-tagged module and derive tool bindings from manifest versions; all 7 golden cases pass.
- Regression results: backend 671 passed / 1 skipped / 7 deselected in Gate A capture; frontend 55 files / 322 tests; Playwright 46 passed; lint and typecheck pass.
- Gate A: `gate_a_passed: true`, `blocking: []`; all mandated zero-diff fences verified empty.

### File List

- `_bmad-output/implementation-artifacts/2-6-add-and-remove-a-governed-capability-module.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `backend/agent/capability_tools.py`
- `backend/agent/runtime.py`
- `backend/api/deps.py`
- `backend/application/capabilities/demonstration.py`
- `backend/application/capabilities/installed.py`
- `backend/application/capabilities/module.py`
- `backend/application/capabilities/registry.py`
- `backend/application/capabilities/scheduling_inspect.py`
- `backend/application/contracts/__init__.py`
- `backend/application/contracts/agent_runtime.py`
- `backend/application/contracts/capability_manifest.py`
- `backend/evals/report.py`
- `backend/tests/architecture/test_agent_runtime_boundaries.py`
- `backend/tests/test_agent_runtime_adapter.py`
- `backend/tests/test_agent_runtime_hidden_reasoning.py`
- `backend/tests/test_capability_conformance.py`
- `backend/tests/test_capability_manifest.py`
- `backend/tests/test_evaluation_harness.py`
- `backend/tests/test_scheduling_inspect.py`
- `evidence/story-1.11/gate-a-readiness-report.json`

## Change Log

| Date | Change |
|---|---|
| 2026-08-11 | Story created; seven creation decisions recorded. |
| 2026-08-12 | Implemented governed module generalization, conformance/removal proofs, harness integration, and clean-bound Gate A evidence; moved to review. |
