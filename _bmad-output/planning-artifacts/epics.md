---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - ../specs/spec-ShiftMind/SPEC.md
  - ../specs/spec-ShiftMind/acceptance-contract.md
  - prds/prd-ShiftMind-2026-07-21/prd.md
  - prds/prd-ShiftMind-2026-07-21/addendum.md
  - requirements-inventory.md
  - architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md
  - ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md
  - ux-designs/ux-ShiftMind-2026-07-22/DESIGN.md
---

# ShiftMind - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for ShiftMind, decomposing the requirements from the canonical spec, PRD, UX design, and architecture into implementable stories.
. K.

> Canonical requirement register: `requirements-inventory.md` (NFR numbering below is canonical and frozen there; FR normative text lives in the PRD). NFR35's thresholds and measurement protocol are final as of 2026-07-23 and defined normatively in the canonical register.

### Functional Requirements

FR1: Authenticate one pre-provisioned planner, support sign-in/sign-out, disable public registration, and deny page or API access without a valid application session.

FR2: Permit only one authenticatable application user and one active site membership in the portfolio environment; reject a second without changing the seeded planner.

FR3: Authorize every conversation, scenario, schedule, run, approval, tool call, audit record, and evidence reference from server-derived actor and site context; URL, payload, model-argument, or browser-held site tampering cannot cross scope.

FR4: Persist conversations, messages, turns, statuses, tool summaries, and outcomes so reload or reconnect reconstructs the same ordered durable state.

FR5: Let the agent inspect the selected scenario, current schedule, demand, qualifications, availability, locks, constraints, runs, and metrics through allow-listed read capabilities without direct database access.

FR6: Request clarification for materially ambiguous entity, intent, consequence, or version information and refuse unsupported, unauthorized, out-of-scope, injection-driven, or over-budget requests without widening tools or authority.

FR7: Bind every numerical or schedule-specific claim to saved facts or computed values for the selected scenario and schedule/run version; every displayed KPI must be recomputable and unsupported numbers must fail grounding.

FR8: When the conversational model is unavailable, identify agent features as unavailable while preserving authenticated access to Scenario Data, saved results, provenance, and the manual deterministic solver workflow.

FR9: Translate planner intent into a validated proposal with resolved entities, constraints or objectives, preserved locks, expected versions, and a human-readable consequence summary; reject invalid entities, tasks, ranges, or combinations before solver execution.

FR10: Make draft constraints and objectives reviewable, editable, rejectable, and abandonable without changing the operational baseline or its version.

FR11: Produce or validate accepted assignments and feasibility only through CP-SAT using versioned proposal inputs; no completed feasible candidate may violate a hard constraint.

FR12: Start optimization as a durable asynchronous job only from the planner's current explicit request or Run optimization transition; return a durable run ID and enforce positive application-owned ceilings for solver time, iterations, model/tool calls, retries, tokens, concurrency, and elapsed time with distinct bounded outcomes.

FR13: Persist and present queued, running, approval-required, completed, infeasible, timed-out, cancelled, and failed states; resume event delivery after reconnect and worker restart without losing accepted work or duplicating effects.

FR14: Retain immutable references from each run to its scenario inputs, active constraints, locks, solver configuration, relevant component versions, and result so feasibility and displayed KPIs can be reproduced.

FR15: Compare a candidate with its exact baseline by affected worker, shift, role/task, interval coverage, overtime, cost/objective components, constraint status, unresolved infeasibility, and versions.

FR16: Accept cooperative cancellation for queued or running work and make command replay, retry, and worker lease recovery return the same semantic effect without duplicate work or promotion.

FR17: Allow the agent to propose approval only for a feasible candidate; optimization completion alone must never change the operational baseline.

FR18: Require an explicit authenticated approval bound to actor, site, exact action, normalized parameters, candidate/version, current baseline/version, consequence summary, policy version, expiry, and one-time decision state; reject expired, reused, altered, stale, or mismatched attempts.

FR19: Atomically consume valid approval, change the baseline pointer once, persist authoritative audit and event evidence, and preserve prior schedule versions for inspection or separately approval-gated re-promotion.

FR20: Expose provenance linking request, evidence consulted, concise decision summary, tool proposals/results, guardrail and policy outcomes, solver run, approval, execution result, and before/after versions without hidden chain-of-thought.

FR21: Produce unsampled, append-only, site-scoped authoritative evidence for successful, denied, stale, failed, and cancelled consequential actions independently of observability.

FR22: Let the planner select only application-provided immutable fixture versions; no chat, UI, or API path may introduce or mutate custom scenario source data.

FR23: Support versioned capability modules declaring typed schemas, permissions, site/resource scope, risk and approval policy, budgets/timeouts, version/idempotency rules, safe audit/evidence mappings, errors, and evaluation fixtures; registration alone grants no authority and incomplete or ungranted modules remain unavailable.

FR24: Provide a read-only Scenario Data viewer for version metadata, work areas/tasks, workers/qualifications/availability, demand, baseline assignments, locks, and constraints/objectives using the same normalized projection as agent inspection; automated browser/API tests must prove value/identifier parity and no mutation controls or endpoints.

### NonFunctional Requirements

NFR1: Tenant-isolation tests must permit zero cross-site reads or writes.

NFR2: Every mutating tool call must use current authorization, expected resource version, idempotency protection, deterministic invariants, and authoritative audit evidence.

NFR3: Workforce, prompt, schedule, approval, and credential content must be excluded from external telemetry by default; only explicitly allow-listed sanitized metadata may leave the application boundary.

NFR4: Secrets must never appear in prompts, browser payloads, audit summaries, logs, traces, or evaluation fixtures.

NFR5: Prompt-injection tests must cover chat and every untrusted data channel introduced by the MVP.

NFR6: Worker termination, lease expiry, replay, and recovery must create zero duplicate effects.

NFR7: Accepted work must remain discoverable after browser, API, stream, or worker interruption.

NFR8: One hundred percent of operational-baseline promotions must require valid parameter- and version-bound approval.

NFR9: Baseline promotion, schedule versioning, successful authoritative audit, and the resulting persisted event must share one consistency boundary.

NFR10: Model-provider or Logfire failure must cause zero product-state corruption and zero authoritative-audit loss while supported manual and deterministic workflows remain available.

NFR11: One hundred percent of completed feasible schedules must satisfy deterministic hard constraints.

NFR12: One hundred percent of numerical agent claims must pass the grounding evaluator before release.

NFR13: Infeasible, timed-out, cancelled, failed, and successful outcomes must never be represented as equivalent.

NFR14: Planner locks must remain satisfied or the run must return a clear infeasibility diagnosis.

NFR15: The product must record API acknowledgement latency, first-persisted-event latency, end-to-end agent duration, model/tool latency, solver duration, queue age, approval age, token use, and cost per completed task.

NFR16: Agent and solver budgets must be explicit positive application configuration with safe defaults and must never be chosen by the model.

NFR17: Public-launch latency, availability, recovery, concurrency, retention, and cost objectives must be set from measured portfolio traffic before accepting a customer; the MVP makes no unsupported enterprise service-level claim.

NFR18: The primary desktop journey and read-only responsive views must meet WCAG 2.2 AA, remain keyboard-operable, use meaningful status text rather than color alone, and announce durable progress and approval state to assistive technology.

NFR19: Review, Run optimization, and Approve as baseline must remain distinct in language, control, consequence, and visual treatment.

NFR20: Zoom to 200%, text-spacing changes, and reduced-motion preferences must not hide controls, create page-level horizontal scrolling, or remove status meaning.

NFR21: Every environment must be reproducible from reviewed infrastructure code and immutable application images.

NFR22: Every agent run must be searchable by one stable run identifier across product records, audit, operational logs, and available traces without using high-cardinality IDs as metric labels.

NFR23: An unhealthy AWS release must be recoverable to the prior schema-compatible image through a tested rollback procedure.

NFR24: Automated RDS backups, a demonstrated restore drill, and documented recovery limitations are required for the portfolio environment.

NFR25: AWS cost, queue health, lease expiry, budget cutoffs, tool/guardrail denials, approval age/outcomes, solver duration/failure, evaluation regressions, audit-write failure, model failure, and telemetry-export health must be observable and alertable.

NFR26: Normal CI must be deterministic-first; live-provider tests are explicit, gated, budgeted, and never the sole release evidence.

NFR27: Every evaluation report must bind dataset, evaluator, model, prompt, tool, policy, application, scenario, solver, code, and image versions.

NFR28: The initial golden dataset is assumed to contain at least 50 versioned cases, at least four per allowed capability, and at least ten consequential/prohibited cases; it must achieve at least 90% overall tool routing and 100% consequential/prohibited routing.

NFR29: Any regression in authorization, approval, isolation, hard constraints, grounding, idempotency, authoritative audit, viewer parity, recovery, accessibility, backup/restore, or rollback must block release regardless of aggregate helpfulness.

NFR30: Product data and authoritative audit must remain in ShiftMind-controlled persistence; external model and telemetry providers receive only the minimum explicitly configured content.

NFR31: Successful mutations must write audit evidence in the business transaction where possible; denied and failed consequential attempts must be recorded reliably and separately.

NFR32: Audit must capture actor/site, request/run/tool/approval/job identifiers, action and policy outcome, safe input/result summaries or hashes, before/after versions, software/model/prompt/tool/policy versions, and immutable evidence references.

NFR33: Audit access must be site-scoped, and the normal application path must not update or delete audit events.

NFR34: The portfolio must document current conversation, audit, snapshot, log, backup, and telemetry retention settings and limitations without implying a customer deletion, residency, compliance, or regulatory-WORM policy.

NFR35: Before implementation acceptance, the final internal portfolio thresholds must be demonstrated under the canonical measurement protocol (`requirements-inventory.md`): initial Scenario Data group-window load ≤ 2 s, exact evidence-target resolution ≤ 2 s, first persisted run event after acknowledgement ≤ 5 s, and SSE reconnect replay to current state ≤ 5 s. These are internal acceptance thresholds, never customer service-level objectives (NFR17). Implemented by Stories 1.4, 1.5, 2.4, and 3.5; bound in architecture AD-26.

### Additional Requirements

- AR1: Implement a hexagonal modular monolith with durable workflow state machines; API and worker are separately runnable from one backend image, dependencies point inward, and domain/application code cannot import FastAPI, PydanticAI, SQLAlchemy, Cognito, S3, Logfire, or concrete model providers.
- AR2: Enforce the three-way authority partition: model proposes typed intent, application controls authorize and persist, and CP-SAT constructs or validates accepted schedules.
- AR3: Use Cognito authorization code with PKCE at a FastAPI BFF; keep tokens server-side, issue only Secure HttpOnly SameSite opaque application-session cookies, require same-origin plus CSRF protection for unsafe methods, re-resolve membership for every operation, and use PostgreSQL RLS as defense in depth.
- AR4: Store predefined fixtures as immutable `scenario_version` records and serve the viewer and agent from one `ScenarioProjectionV1` with deterministic ordering, bounded cursor windows/counts, and exact-target lookup.
- AR5: Compose authenticated capabilities through an application-owned registry with exactly `inspect`, `draft`, `compute`, `consequential`, and `prohibited` risk classes and a complete `CapabilityManifestV1` per module.
- AR6: Persist accepted messages, agent runs, tool calls, jobs, approvals, schedule runs, outcomes, and progress events before acknowledgement; lease jobs with owner, expiry, heartbeat, monotonically increasing fencing epoch, compare-and-set transitions, cooperative cancellation, and unique effect keys.
- AR7: Implement separate closed `AgentRun`, `ScheduleRun`, and `ApprovalRequest` state machines exactly as defined by the architecture; only feasible completed schedule runs may reference candidate schedule versions, and budget exhaustion has stable timed-out or failed reasons.
- AR8: Require mutating HTTP idempotency keys scoped to actor, site, operation, and canonical body hash plus expected resource version; use stable tool/job effect keys and database uniqueness for replay safety.
- AR9: Keep proposal, solver input/output, and schedule versions immutable; the site baseline is a versioned pointer and stale inputs fail closed without silent rebasing.
- AR10: Make approval a one-time persisted state machine with no approved-but-unconsumed state; approve, revalidate, consume, promote, audit, and emit the event atomically or leave the request pending.
- AR11: Use version-bound `EvidenceRefV1` locators and application calculators for every metric and comparison; missing, unauthorized, and version-mismatched evidence are distinct failures and never retarget.
- AR12: Keep PostgreSQL product/workflow state and append-only audit, checksummed create-only S3 evidence, CloudWatch diagnosis, sanitized OTel/Logfire traces, and version-controlled evaluation reports as separate records of truth.
- AR13: Publish versioned REST/JSON commands and queries plus persisted SSE from FastAPI; generate frontend endpoint types from OpenAPI, use one `openapi-fetch` client, and render application errors as RFC 7807 `ProblemDetailsV1` with stable codes and safe correlation/version fields.
- AR14: Use TanStack Query as the sole owner of remote browser cache and route/component state only for navigation/presentation; represent conversation history as a discriminated `ActivityItemV1` stream and never encode approval as ordinary chat text.
- AR15: Treat messages, prompts, fixture fields, model output, and tool output as untrusted; discard provider hidden-reasoning parts and persist only visible messages, concise application-owned summaries, typed recovery data, and evidence links.
- AR16: Use deterministic model doubles and versioned golden datasets for normal CI; bind all release reports to complete component and artifact versions.
- AR17: Deploy a private-S3 SPA behind CloudFront and an ALB to separate ECS Fargate API/worker tasks with non-public RDS PostgreSQL, create-only S3 evidence, Cognito, ECR, Secrets Manager, CloudWatch, optional sanitized Logfire, TLS 1.2+, encryption at rest, Block Public Access/OAC, Terraform, and GitHub Actions OIDC.
- AR18: Use PostgreSQL leasing before distributed coordination; introduce SQS only with a transactional outbox and measured need, and reconsider a workflow engine only for branching multi-day cross-system workflows.
- AR19: Introduce a ShiftMind-owned `AgentRuntime` port and keep existing provider-neutral constraint-parsing and cached-insight ports until deliberately migrated; complete a pinned PydanticAI compatibility spike before the first agent slice.
- AR20: Own versioned schemas in `application/contracts` for ScenarioProjection, EvidenceRef, Proposal, RunSnapshot, Assignment, MetricSet, ConstraintResult, ScheduleVersion, Comparison, CapabilityManifest, JobLease, ApprovalBinding, AuditEnvelope, ActivityItem, PersistedEvent, and ProblemDetails; hash RFC 8785 canonical JSON with SHA-256 and model schedule time as UTC horizon plus IANA timezone and integer-minute half-open offsets.
- AR21: Define persisted events with stream ID, decimal sequence, event type, occurred time, resource version, correlation IDs, and one typed activity payload; SSE IDs are `<stream_uuid>:<sequence>`, replay only greater matching-stream sequences, and 15-second non-persisted heartbeats must work end-to-end through CloudFront and ALB.
- AR22: Preserve module aggregate ownership and fixed atomic bundles for accept-turn, enqueue-compute, complete-compute, request-approval, and promote-baseline; only application orchestrators may cross owners.
- AR23: Use a NOLOGIN table/function owner, a deployment-only migrator, NOINHERIT/NOSUPERUSER/NOBYPASSRLS runtime roles, forced RLS on tenant tables, transaction-local trusted actor/site context, narrowly granted SECURITY DEFINER session/job functions, and create-only versioned S3 evidence permissions.
- AR24: Use expand-migrate-contract with N/N-1 API/worker/client read/write compatibility, versioned durable jobs, resumable backfills, explicit contraction gates, `/api/meta` client compatibility, no-cache `index.html`, retained hashed assets, schema-compatible image rollback, and roll-forward after contraction.
- AR25: Perform the Gate A one-way brownfield cutover in a maintenance window: disable legacy writes, drain/cancel the in-process worker, snapshot SQLite, import checksummed fixtures to PostgreSQL, deploy/test V1 API and regenerated client, switch the no-cache SPA index, and keep old SQLite scenarios/runs offline rather than fabricating governed history.
- AR26: Converge new work on the architecture structural seed under `backend/api`, `backend/worker`, `backend/application`, `backend/domain`, `backend/agent`, `backend/engine`, `backend/adapters`, `backend/migrations`, `backend/evals`, `frontend/src/api`, `frontend/src/features`, `frontend/src/routes`, `infra/terraform`, and `tests/architecture` without an all-at-once rename.
- AR27: Use the architecture's pinned/planned stack seeds and repository constraints; add and lock each planned dependency only at its implementation gate, and require immutable deployed image digests.
- AR28: Gate A must complete PostgreSQL/site membership, immutable fixtures, the normalized scenario read service, authenticated read-only Scenario Data, parity tests, and negative mutation tests before AgentRuntime or agent tools; Gate B adds durable recovery, evaluation, and observability in a reproducible local environment; Gate C adds the hosted AWS proof. No later gate may weaken an earlier gate's invariants.

### UX Design Requirements

UX-DR1: Implement real routes for Fixture catalogue, Chat, Scenario Data, Runs, and per-run Results; expose Chat, Scenario Data, Runs, and Results as four peer workspace tabs with browser Back/Forward support.

UX-DR2: Keep a persistent scenario/version context across all workspace surfaces showing scenario name, stable scenario ID, immutable fixture version, and operational-baseline version; never switch scenario implicitly from an evidence link.

UX-DR3: Present Scenario Data in the fixed group order Overview, Work areas and tasks, Workers, Demand, Baseline assignments, Locks, and Constraints and objectives using the same vocabulary as agent evidence.

UX-DR4: Keep Scenario Data visually and behaviorally read-only: no upload, create, edit, delete, import, bulk-action selection, editable cells, mutation overflow menus, or mutation-looking affordances.

UX-DR5: Use operational, bounded copy that names literal states and versions; avoid confidence scores, anthropomorphic waiting, hidden reasoning, celebration, urgency, and unsupported benefit claims.

UX-DR6: Build a durable conversation timeline that renders planner messages, grounded responses, clarifications, refusals, drafts, run progress, comparisons, approvals, and terminal outcomes in persisted order and deduplicates replay by event identity.

UX-DR7: Implement a multiline chat composer where Enter inserts a newline and Ctrl/Cmd+Enter sends; sending creates only a planner message and never authorizes optimization or approval.

UX-DR8: Render every numerical or schedule-specific claim with an adjacent evidence link naming exact group, record, field/range, and version rather than a generic message-level Sources link.

UX-DR9: Implement Draft cards showing resolved entities, proposed constraints/objectives, preserved locks, expected versions, consequence summary, and the label “Draft — no baseline change,” with separate revise, reject, and Run optimization controls.

UX-DR10: Implement Run progress cards showing run ID and literal persisted state without invented percentages or ETA; recovery must retain the same run ID.

UX-DR11: Implement Comparison summaries naming candidate and baseline versions plus worker/shift/task, coverage, overtime, cost/objective, constraint, and unresolved-gap deltas; absent metrics say “Not computed.”

UX-DR12: Implement Approval requests bound visibly to exact candidate, baseline, material parameters, consequences, and versions; approval is a separate explicit control and stale/rejected/expired states never resubmit.

UX-DR13: Implement Terminal outcomes for every literal final state and expose only valid next actions; a non-promotable result never shows an enabled Approve as baseline control.

UX-DR14: Implement semantic Scenario Data tables with captions and headers, stable server-defined tie-break ordering, visible sort/filter state, contained two-axis scrolling, sticky headers, and optional sticky identifier columns.

UX-DR15: Implement field-aware filters with explicit Apply/Clear, active-filter and total/matching counts, URL serialization, and distinct copy for filtered-empty versus intrinsically empty groups.

UX-DR16: Implement a session-scoped column chooser that cannot hide every stable ID/evidence/context column; an evidence jump to a hidden field temporarily reveals it and explains why.

UX-DR17: Implement identifier copy controls that copy the full stable value and announce “Copied {identifier type}” without implying row selection or editability.

UX-DR18: Implement application-owned evidence navigation carrying scenario, fixture/schedule/run version, group, record, optional field/range, and origin activity ID; load the exact page/window, focus and highlight exactly one target, and never retarget.

UX-DR19: Implement Return to claim so route, scroll position, and keyboard focus restore to the originating claim without resending or regenerating the conversation.

UX-DR20: Implement distinct evidence exception states for version mismatch, missing evidence, unauthorized evidence, and stale cache; unauthorized behavior must not reveal record existence or value.

UX-DR21: Implement Runs as a stable table with separately labelled row navigation, Cancel, and Retry controls; implement Results with deterministic result, warnings, metrics, schedule, comparison, evidence, and provenance independent of model availability.

UX-DR22: Implement Provenance as an ordered timeline of request, evidence, concise decision summary, tool/policy outcomes, solver, approval, execution, and versions without exposing private chain-of-thought.

UX-DR23: Provide consistent Status badge, Inline alert, Skeleton, Empty state, and Reconnect banner patterns; saved content remains visible during reconnect/model outage and replay never duplicates an activity.

UX-DR24: Never use unbounded infinite scroll; use bounded pagination or virtualization with total/matching counts, deterministic position/range, stable-ID tie-breaks, exact-target loading, and an accessible paginated mode if virtualization cannot preserve semantics.

UX-DR25: Preserve distinct cold/loading, empty, error/unavailable, stale, and reconnect states for Fixture catalogue, Chat, Scenario Data, Runs, and Results exactly as defined in the experience contract.

UX-DR26: Implement native keyboard and focus behavior for tabs, buttons, row links, sort/filter controls, evidence jumps, dialogs, Escape dismissal, Back/Forward restoration, and row-level action propagation; data cells are not made tabbable merely for viewing.

UX-DR27: On route changes focus the view heading, except evidence jumps focus the exact target; use live regions for durable state changes and restore focus after dialogs and Return to claim.

UX-DR28: Support desktop/laptop as the full workflow, tablet with stacked panels and contained table scroll, and phone as read-only triage that directs write/run/cancel/approve actions to desktop without using viewport as authorization.

UX-DR29: Meet 44x44 CSS-pixel touch targets, no hover-only actions, semantic table associations/`aria-sort`, announced virtualized row position, named dialogs, consequence-specific accessible approval names, visible focus, reduced motion, and 200% zoom/text-spacing support.

UX-DR30: Retain the existing shadcn/Tailwind/Radix/system-font design system and indigo accent; add the specified evidence link/surface/border/foreground/focus tokens, identifier monospace style, 24px workspace gutter, 8px data-cell padding, and 6px evidence/data-region radii.

UX-DR31: Keep Chat, Runs, and Results in the centered reading column while allowing Scenario Data to use viewport width inside 24px gutters; horizontal overflow must stay inside labelled table regions, never the page.

UX-DR32: Use borders, quiet surfaces, headings, and placement for hierarchy; prohibit AI glows, gradients, animated avatars, confidence gauges, celebratory effects, pulsing/flashing evidence, and color-only state communication.

UX-DR33: Preserve inherited component elevation, neutral/status tokens, radius scale, and optional dark-theme behavior; dark mode is not an MVP requirement and no new success/warning palette is introduced.

UX-DR34: Make Evidence links conventionally link-identifiable and use the exact quiet highlight treatment only on the resolved row/cell/record; reduced-motion behavior must be equivalent and non-animated.

UX-DR35: Keep Send, Run optimization, and Approve as baseline visually discontinuous and consequence-appropriate so no single “AI action” treatment spans authority levels.

### Deferred Requirements

The 2026-08-09 Epics 2–5 scope audit cut the stories that owned the
requirements below. They are **deferred, not withdrawn**: the canonical
register in `requirements-inventory.md` is unchanged and their normative text
still stands. They simply have no owning story at Gate B or Gate C, and no gate
may claim them as satisfied. Each carries a revisit trigger, mirrored in the
architecture spine's Deferred table.

| Requirement | Clause deferred | Why | Revisit trigger |
|---|---|---|---|
| NFR25 | All of it — per-signal severity, destination, deduplication key, and tested runbook | A single-operator portfolio has no on-call rotation or paging destination. Story 5.1's instrumentation covers diagnosis, which is the actual need. | First external pilot, or any operation the author does not personally observe |
| NFR24 | "a demonstrated restore drill" | Story 6.5 configures automated backups and documents recovery limitations. A rehearsed restore proves recoverability the portfolio does not yet need to claim. | First external user, or any non-reproducible data |
| AR24 / AD-24 | N/N-1 read/write compatibility, resumable backfills, `/api/meta` client gating, contraction gates | One API task and one worker task are replaced, not rolled; there is no concurrent prior version to stay compatible with and no user to strand. Story 6.5 implements only the schema-compatible image-rollback clause. | A second concurrent API/worker task, or the first external user |

Story 2.6's `AR24` reference is unaffected — it cites the historical-record
version-retention clause, which Epic 2 still implements.

### FR Coverage Map

FR1: Epic 1 - Seeded planner authentication
FR2: Epic 1 - One-user and one-membership enforcement
FR3: Epic 1 - Server-derived site-scoped authorization
FR4: Epic 2 - Durable conversations and reconnect reconstruction
FR5: Epic 2 - Allow-listed grounded schedule investigation
FR6: Epic 2 - Clarification, refusal, and authority preservation
FR7: Epic 2 - Version-bound evidence-linked explanations
FR8: Epic 3 - Model-outage access to saved work and manual deterministic optimization
FR9: Epic 3 - Typed validated schedule-change proposals
FR10: Epic 3 - Reversible draft boundary
FR11: Epic 3 - CP-SAT-owned schedule construction and feasibility
FR12: Epic 3 - Explicit bounded asynchronous optimization
FR13: Epic 3, Story 3.5 - Persisted optimization progress states and recovery; Epic 4, Story 4.1 - independently owned approval-required state, presentation, and replay
FR14: Epic 3 - Immutable reproducible run evidence
FR15: Epic 3 - Exact candidate/baseline comparison
FR16: Epic 3 - Cancellation, retry, lease, and idempotency safety
FR17: Epic 4 - Separate feasible-candidate approval proposal
FR18: Epic 4 - Exact-action, version-bound approval
FR19: Epic 4 - Atomic baseline promotion and prior-version preservation
FR20: Epic 4 - Complete decision provenance
FR21: Epic 4 - Unsampled append-only authoritative audit
FR22: Epic 1 - Immutable predefined fixture catalogue
FR23: Epic 2, Story 2.6 - Versioned governed capability-module extensibility, wholly owned and proven there
FR24: Epic 1 - Read-only Scenario Data viewer and viewer/agent parity

## Epic List

### Epic 1: Inspectable Single-Site Scenario Workspace

The seeded planner can sign in, choose an immutable predefined fixture, and independently inspect the exact normalized scenario facts and versions inside a site-scoped read-only workspace.

**FRs covered:** FR1, FR2, FR3, FR22, FR24

**Implementation notes:** Delivers the Gate A foundation and the one-way PostgreSQL cutover before AgentRuntime. Includes authenticated BFF/session scope, organization/site/membership enforcement, fixture catalogue, shared normalized projection, Scenario Data routes and tables, RLS defense in depth, viewer parity contract, and negative mutation-path proof. It is useful without any agent capability and becomes the evidence substrate for every later epic.

### Epic 2: Grounded Conversational Investigation

The planner can create and revisit durable conversations, ask why a schedule is weak, receive evidence-linked answers, and get safe clarification or refusal instead of fabricated context or widened authority.

**FRs covered:** FR4, FR5, FR6, FR7, FR23

**Implementation notes:** Builds the owned AgentRuntime boundary, the deterministic evaluation harness every later epic's proof story reuses, the application-owned capability registry and its first inspect capability, the governed-extensibility conformance proof (FR23, proven in the same epic that first owns the registry rather than deferred to a late release epic), durable activity stream, grounded claim/evidence navigation, and conversation recovery on Epic 1's scenario projection. It delivers useful investigation without requiring schedule mutation, optimization, or approval.

### Epic 3: Governed and Recoverable Schedule Repair

The planner can turn intent into a reversible draft, explicitly run bounded deterministic optimization, leave and recover the same work, inspect literal outcomes, and compare an exact candidate with its baseline without changing the operational schedule.

**FRs covered:** FR8, FR9, FR10, FR11, FR12, FR14, FR15, FR16, plus FR13's optimization progress and recovery behavior

**Implementation notes:** Keeps draft, compute, comparison, and baseline change separate while implementing the durable PostgreSQL job/event recovery boundary once. Includes typed proposal versions, CP-SAT snapshots, worker leasing/fencing, budgets, cancellation, SSE replay, immutable evidence, idempotency, comparison UI, and the model-outage manual solver path. The epic stands alone as a complete non-consequential repair-and-review workflow.

### Epic 4: Exact Baseline Decision and Decision Record

The planner can approve only the exact current feasible candidate as the internal operational baseline and later reconstruct who decided what, from which evidence and versions, with stale or repeated actions failing closed.

**FRs covered:** FR13's approval-required behavior, FR17, FR18, FR19, FR20, FR21

**Implementation notes:** Adds the consequential authority boundary after candidate creation is stable. Story 4.1 independently owns the approval-required `AgentRun` transition, presentation, and replay; no Epic 3 story depends on that behavior for acceptance. The epic also includes exact approval binding, separate approval interaction, atomic promotion, authoritative audit, immutable provenance, stale/expiry/replay handling, prior-version inspection, and evidence-linked before/after outcomes. It does not require future extensibility or AWS work to function.

### Epic 5: Demonstrable Local Planner Workspace

The complete planner journey runs reproducibly on any developer machine from one command, with agent runs instrumented for latency, budget, and cost, no sensitive content leaving the application boundary, and a published walkthrough.

**FRs covered:** none new (makes the FR1–FR24 outcomes reproducible and legible outside the author's machine)

**Implementation notes:** This is the portfolio milestone and completes Gate B. It delivers run instrumentation (tokens, cost, latency, budget outcomes, run-ID correlation), content and secret minimization with adversarial fixtures, a one-command reproducible environment whose locally built image digest satisfies every evaluation report's image binding, and the walkthrough that makes the system judgeable by a reader. NFR10's telemetry independence is already proven by Story 3.9; NFR35's thresholds are owned by Stories 1.4, 1.5, 2.4, and 3.5 and measured on CI per AD-26.

### Epic 6: Reliable Hosted Planner Workspace

The planner can sign in to the hosted ShiftMind workspace and trust it: reproducibly deployed from reviewed infrastructure code, diagnosable without privacy leaks, with its invariants holding through the real edge, load-balancer, and database topology.

**FRs covered:** none new (hardens FR1–FR24 outcomes in the hosted environment)

**Implementation notes:** Sequenced after the Epic 5 portfolio milestone and completes Gate C. Delivers AWS Terraform provisioning, Cognito/ECS/RDS/object-storage boundaries, health-gated immutable deployment including the SSE-through-CloudFront/ALB proof, a smoke-level hosted re-proof of the security/parity/mutation-denial invariants, backups, and a documented rollback path. It hardens an already complete and demonstrable planner workflow; nothing in Epics 1–5 depends on it.

> **No release-evaluation epic.** Release evaluation and capability-module conformance are not a separate late epic. Each is a definition of done attached to the epic it protects: the evaluation harness and FR23 conformance live in Epic 2 (Stories 2.2 and 2.6, beside the registry they validate), per-slice evaluation suites live in each epic's own proof stories, Story 4.6 proves the completed workflow's state semantics and accessibility, and the aggregate release-blocking thresholds are held in the Release Gate section at the end of this document rather than in a story. Epic 6 is a deployment epic, not a release-evaluation epic, and this principle is unchanged by its addition.

## Epic 1: Inspectable Single-Site Scenario Workspace

The seeded planner can sign in, choose an immutable predefined fixture, and independently inspect the exact normalized scenario facts and versions inside a site-scoped read-only workspace.

### Story 1.1: Establish Governed Fixture History [Technical Enabler]

As a portfolio operator,
I want predefined fixtures imported into site-scoped PostgreSQL history,
So that the planner starts from immutable, checksummed scenario facts rather than ambiguous legacy state.

Unblocks: Story 1.3 (fixture catalogue) and every scenario-read story.

**Acceptance Criteria:**

**Given** the existing SQLite demo data and a declared maintenance window
**When** the Gate A cutover is executed
**Then** legacy writes are disabled, the in-process worker is drained or cancelled, and SQLite is snapshotted before checksummed predefined fixtures are imported as immutable site-owned `scenario_version` records
**And** legacy scenarios and runs remain offline and no runtime adapter exposes both histories or fabricates governed history. (AR25)

**Given** the first governed fixture import
**When** migrations are applied
**Then** only the organization, site, scenario, scenario-version, fixture-lineage, and evidence-reference structures required by this story are created
**And** tenant tables carry `site_id`, forced RLS, server-generated identifiers, immutable version/checksum fields, and no planner-facing mutation grant. (AR4, AR23)

**Given** the same fixture package is imported again
**When** its canonical checksum and version already exist
**Then** the import is idempotent and returns the existing semantic result
**And** a conflicting payload for the same fixture version fails without changing stored history. (NFR6)

### Story 1.2: Sign In to the Seeded Site Safely

As a seeded planner,
I want to sign in to one protected site workspace,
So that every scenario and later agent action is authorized from my current server-side membership.

**Sizing note:** high implementation breadth — OIDC/BFF session, sign-out, one-user/membership persistence, CSRF/origin enforcement, and RLS isolation. Break into implementation tasks with one demonstrable acceptance boundary and one owner per cross-stack concern before sprint commitment. Do not split into separate stories unless each slice stays independently testable without a forward dependency.

**Acceptance Criteria:**

**Given** the pre-provisioned planner identity and active membership
**When** the planner completes OIDC authorization code with PKCE through the BFF
**Then** provider tokens remain server-side and the browser receives only a Secure, HttpOnly, SameSite opaque application-session cookie
**And** sign-out invalidates the application session without exposing credentials. (FR1, AR3)

**Given** no valid application session
**When** a protected page or API is requested
**Then** access is denied without exposing fixture or membership data
**And** no public registration route or UI can create an account. (FR1)

**Given** the seeded planner already exists
**When** provisioning attempts to create a second authenticatable user or activate a second membership
**Then** database and application invariants reject the change atomically
**And** the seeded planner and membership remain unchanged. (FR2)

**Given** identity and session persistence is introduced for the seeded planner
**When** Story 1.2 migrations are applied
**Then** this story creates only the minimal application-user, membership, application-session, and one-user enforcement structures and constraints it requires
**And** invitations, role administration, additional memberships, and other future identity structures are not created early. (AR22)

**Given** an authenticated unsafe request
**When** origin or CSRF validation fails, a browser-held site value is altered, or a resource belongs to another site
**Then** the request is denied from re-resolved session/membership context with a non-disclosing not-found shape where practical
**And** authorization tests prove zero cross-site reads or writes. (FR3, NFR1, AR3)

### Story 1.3: Choose an Immutable Fixture

As a planner,
I want a catalogue of predefined scenarios,
So that I can deliberately choose the exact fixture and version I will inspect.

**Acceptance Criteria:**

**Given** an authenticated site session with available fixtures
**When** the planner opens the application
**Then** the fixture catalogue lists only authorized immutable fixture versions with stable IDs and deterministic ordering
**And** selecting a row opens that scenario without changing or copying its source data. (FR22)

**Given** the fixture catalogue
**When** it renders in loading, empty, error, cached-stale, and loaded states
**Then** each state uses the required skeleton, safe copy, retry behavior, and authorization checks
**And** there is no create, upload, import, edit, or delete action. (UX-DR4, UX-DR23, UX-DR25)

**Given** a selected fixture
**When** the scenario workspace opens
**Then** a persistent context names scenario, scenario ID, immutable fixture version, and baseline version
**And** changing scenario returns through the catalogue rather than occurring implicitly. (UX-DR1, UX-DR2)

### Story 1.4: Serve the Normalized Scenario Read Contract [Technical Enabler]

As the scenario platform,
we want one versioned normalized scenario read contract,
So that direct inspection and assisted investigation cannot disagree about source facts.

Planner-visible outcome: none at this position — the Scenario Data workspace that consumes this contract is delivered by Story 1.7. Accepted through versioned API contract, window, and count tests.

**Acceptance Criteria:**

**Given** an authorized fixture version
**When** `ScenarioProjectionV1` is requested
**Then** it returns version/checksum metadata, horizon and IANA timezone, work areas/tasks, workers/qualifications/availability, demand intervals, baseline assignments, locks, constraints/objectives, and version-bound evidence references
**And** all schedule intervals use integer-minute half-open offsets from a UTC horizon. (FR24, AR4, AR20)

**Given** a projection group larger than one response window
**When** it is read, sorted, filtered, or deep-linked
**Then** bounded cursors expose total/matching counts and deterministic stable-ID tie-break ordering. (UX-DR14, UX-DR15, UX-DR24)

**Given** the normalized scenario query and its errors
**When** frontend and backend contracts are generated and consumed
**Then** FastAPI publishes versioned OpenAPI, the SPA uses generated endpoint types through one `openapi-fetch` client, and failures render stable RFC 7807 problem details with safe correlation/resource/version fields
**And** transport DTOs do not become domain authority. (AR13)

**Given** the NFR35 measurement fixture (the largest Gate A fixture, warm process and warm database, local or CI reference environment, three consecutive deterministic runs)
**When** the initial window of each Scenario Data group is requested
**Then** every run completes server-side request handling within 2 seconds, measured from request receipt to response completion
**And** the measured values are recorded as release evidence and a miss blocks implementation acceptance of this story. (NFR35)

### Story 1.5: Resolve Exact Evidence Targets [Technical Enabler]

As the scenario platform,
we want evidence locators resolved to exact records with distinct failure outcomes,
So that verification always lands on the cited fact or fails safely.

Planner-visible outcome: none at this position — evidence navigation that consumes this resolver is delivered by Story 2.8. Accepted through exact-target resolution, out-of-window, missing, and unauthorized-case tests.

**Acceptance Criteria:**

**Given** an exact-target evidence locator for an authorized record outside the current window
**When** the projection resolves it
**Then** exact-target lookup reveals that record without retargeting
**And** the behavior is available to both the viewer and the future inspect capability. (AR4, UX-DR24)

**Given** a missing, unauthorized, or version-mismatched evidence locator
**When** the projection resolves it
**Then** those outcomes are distinct, no similar row or current version is substituted, and unauthorized responses disclose no record existence or value
**And** the same contract is reusable by the future inspect capability. (AR11, UX-DR20)

**Given** the NFR35 measurement fixture and protocol used in Story 1.4
**When** an exact evidence target in the largest projection group is resolved, including the deepest out-of-window record
**Then** every run resolves within 2 seconds, measured from request receipt to response completion
**And** the measured values are recorded as release evidence and a miss blocks implementation acceptance of this story. (NFR35)

### Story 1.6: Establish ShiftMind Design Tokens and Shared Primitives [Technical Enabler]

As a product engineer,
I want the ShiftMind visual tokens and shared workspace primitives established before the first data UI,
So that every later story implements its visual contract once instead of retrofitting consistency.

Unblocks: Story 1.7 and every subsequent UI story.

**Acceptance Criteria:**

**Given** the existing shadcn/Tailwind/Radix theme
**When** ShiftMind design tokens are consolidated
**Then** primary/evidence/focus colors, evidence/data radii, 24px workspace gutter, 8px table-cell spacing, system typography, metric ramp, and identifier monospace match `DESIGN.md`
**And** inherited neutral, destructive, card, popover, input, muted, border, chart, elevation, radius, and optional dark-theme tokens remain unchanged. (UX-DR30, UX-DR33)

**Given** the shared Status badge, Inline alert, Skeleton, Empty state, Reconnect banner, Evidence link, and quiet highlight primitives
**When** they are implemented as reusable components
**Then** each has a deterministic state fixture covering its states without color-only meaning
**And** each subsequent UI story implements its component-specific visual contract in that story rather than deferring it. (UX-DR23, UX-DR32, UX-DR34)

### Story 1.7: Open the Read-Only Scenario Data Workspace

As a planner,
I want a read-only Scenario Data workspace,
So that I can verify the exact demand, workforce, assignments, locks, and rules before trusting assistance.

**Acceptance Criteria:**

**Given** a selected fixture
**When** the planner opens `/scenarios/:scenarioId/data`
**Then** the workspace shell exposes real routes for Chat, Scenario Data, Runs, and Results while Scenario Data shows the seven groups in the required fixed order
**And** Results is disabled with an accessible explanation until a run is selected. (UX-DR1, UX-DR3)

**Given** any Scenario Data group
**When** it renders
**Then** it uses a captioned semantic table with stable headers, contained two-axis scroll, and sticky orientation cues
**And** it exposes no editable cells, mutation controls, bulk selection, or mutation-looking menus. (FR24, UX-DR4, UX-DR14)

**Given** the model provider is unavailable
**When** the planner uses Scenario Data
**Then** the full read-only view remains available because it calls the application scenario-read service directly
**And** no AgentRuntime dependency is invoked. (FR8, partial; AR15)

### Story 1.8: Control Scenario Data Tables

As a planner,
I want sorting, filtering, bounded navigation, column visibility, and identifier copying on Scenario Data tables,
So that I can locate exact records in large groups without losing orientation.

**Acceptance Criteria:**

**Given** any Scenario Data group
**When** the planner sorts, filters, or pages it
**Then** explicit sorting and field-aware filtering with Apply/Clear, active-filter and total/matching counts, URL serialization, and bounded navigation behave deterministically with stable-ID tie-breaks
**And** copyable stable identifiers announce “Copied {identifier type}” without implying row selection or editability. (UX-DR14, UX-DR15, UX-DR17, UX-DR24)

**Given** a field is hidden through the session-scoped column chooser
**When** an exact evidence locator targets that field
**Then** the field becomes temporarily visible with an explanation
**And** the chooser can never hide every stable ID, evidence target, and key context column. (UX-DR16)

### Story 1.9: Prove Viewer Parity and Mutation Denial

As the product team,
we want the viewer's parity and read-only boundary proven automatically before release,
So that the facts the planner inspects are exactly the facts later used by the agent, and no path can alter fixture source data.

**Acceptance Criteria:**

**Given** every Gate A fixture
**When** viewer API/browser payloads are compared against the shared `ScenarioProjectionV1` contract fixture
**Then** all agent-relevant normalized values and stable identifiers match exactly
**And** the comparison runs against the contract fixture alone, so AgentRuntime and agent capabilities are not required for this story
**And** any mismatch blocks Gate A. (FR24, NFR29)

**Given** the supported browser and API surfaces
**When** mutation-path tests attempt upload, create, import, edit, delete, or source-data modification
**Then** no control, route, command handler, endpoint, or agent capability supports the mutation
**And** any discovered path blocks Gate A. (FR22, FR24)

### Story 1.10: Prove Scenario Data Accessibility and Responsiveness

As the product team,
we want the viewer proven usable with assistive technology across supported viewports,
So that the planner can inspect scenario facts without losing meaning, focus, or orientation.

**Acceptance Criteria:**

**Given** keyboard-only use, screen-reader use, reduced motion, text-spacing changes, and 200% zoom
**When** the planner navigates catalogue, workspace tabs, group controls, filters, tables, copy controls, and exact targets
**Then** headings, focus order, captions, `aria-sort`, status text, row position, touch targets, and contained scrolling satisfy WCAG 2.2 AA
**And** no meaning depends on color, hover, motion, or page-level horizontal scrolling. (NFR18, NFR20, UX-DR26, UX-DR27, UX-DR29)

**Given** desktop, tablet, and phone viewports
**When** Scenario Data is inspected
**Then** desktop supports the full wide data workspace, tablet stacks controls with contained scroll, and phone provides read-only triage
**And** server authorization never depends on viewport. (UX-DR28, UX-DR31)

### Story 1.11: Confirm Gate A Readiness [Technical Enabler]

As the product team,
we want every Gate A foundation invariant confirmed before agent work begins,
So that conversational implementation starts only on a proven site-scoped, immutable, read-only data substrate.

**Acceptance Criteria:**

**Given** all Gate A viewer, isolation, parity, mutation-denial, and accessibility checks
**When** readiness is evaluated
**Then** PostgreSQL/site membership, immutable fixtures, normalized reads, and the authenticated viewer must all pass before AgentRuntime or agent tools are introduced
**And** later work may not weaken any passed invariant. (AR28)

**Given** the Gate A decision is recorded
**When** readiness is declared
**Then** `evidence/story-1.11/gate-a-readiness-report.json` is persisted with the pass/fail result of each contributing Story 1.1–1.10 check, bound to fixture version, schema version, application image, and code commit
**And** the accountable owner is Product/QA, and any missing or unbound contributing result blocks the gate. (AR28, NFR27)

## Epic 2: Grounded Conversational Investigation

The planner can create and revisit durable conversations, ask why a schedule is weak, receive evidence-linked answers, and get safe clarification or refusal instead of fabricated context or widened authority.

### Story 2.1: Establish the Owned Agent Runtime Boundary [Technical Enabler]

As a product engineer,
I want a validated ShiftMind-owned agent runtime port,
So that conversational behavior can evolve without making a model framework part of product authority or persisted contracts.

Unblocks: Story 2.2 (which formalizes the model doubles this spike proves), Story 2.3, and every conversational story.

**Sizing note:** high implementation breadth — framework spike, owned port, dependency boundaries, brownfield seams, and hidden-reasoning discard. Break into implementation tasks with one demonstrable acceptance boundary and one owner per concern before sprint commitment.

**Acceptance Criteria:**

**Given** the repository's supported Python, Pydantic, provider, and test environments
**When** the pinned PydanticAI compatibility spike runs
**Then** it proves typed tools, deferred calls, deterministic model doubles, owned-message translation, bounded execution, provider failure mapping, and content-disabled instrumentation
**And** the tested version is added to manifests/lockfiles only after the spike passes. (AR19, AR27)

**Given** the `AgentRuntime` port and adapter
**When** domain or application modules are inspected
**Then** they contain no PydanticAI, provider-message, deferred-call, framework-tool, checkpoint, or telemetry event type
**And** the existing provider-neutral constraint parsing and cached-insight operations remain behind their own ports until deliberately migrated. (AR1, AR19)

**Given** new runtime work is added
**When** its module location and dependency direction are reviewed
**Then** it converges on the architecture structural seed under backend API/worker/application/domain/agent/engine/adapters/migrations/evals and frontend API/features/routes boundaries
**And** compatibility adapters permit incremental brownfield migration without an all-at-once rename. (AR26)

**Given** a provider response containing hidden reasoning or thinking parts
**When** the adapter translates the response
**Then** hidden reasoning is discarded and only planner-visible content, typed recovery data, concise application-owned summaries, and evidence references may persist
**And** no private chain-of-thought appears in product records or telemetry. (AR15, FR20 precursor)

### Story 2.2: Establish the Deterministic Evaluation Harness [Technical Enabler]

As a product engineer,
I want one versioned evaluation harness available from the first agent slice,
So that every epic proves its own behavior deterministically instead of deferring correctness evidence to a late release milestone.

Unblocks: the evaluation acceptance criteria in Stories 2.9, 3.10–3.12, 4.5–4.6, and 6.4.

**Acceptance Criteria:**

**Given** normal CI
**When** the evaluation harness runs
**Then** it executes against deterministic model doubles and version-controlled fixtures with no live provider call, and any live-provider suite is separately named, explicitly gated, budgeted, and marked non-authoritative
**And** a live-provider result can never satisfy a release gate on its own. (NFR26, AR16)

**Given** any evaluation report the harness produces
**When** it is persisted as release evidence
**Then** it binds dataset, evaluator, model, prompt, tool, policy, application, scenario, solver, code, and image versions
**And** a report missing any binding is rejected rather than recorded. (NFR27)

**Given** a reviewed failure from any epic
**When** it is sanitized and added to the golden dataset
**Then** the harness accepts it as a version-controlled regression case tagged with its owning capability and risk class
**And** each epic's proof stories contribute their cases to the same dataset so the Release Gate can measure the aggregate. (NFR28)

### Story 2.3: Create and Revisit Durable Conversations

As a planner,
I want my conversations and accepted turns to survive reconnects,
So that I can investigate a fixture without losing or duplicating the decision context.

**Acceptance Criteria:**

**Given** an authenticated selected scenario
**When** the planner creates a conversation or submits a message
**Then** the conversation, planner message, accepted agent run, first persisted activity event, actor/site context, scenario version, and correlation IDs commit before acknowledgement
**And** the accept-turn bundle is atomic and contains only the entities needed for durable conversation. (FR4, AR6, AR22)

**Given** one or more conversations for a scenario
**When** the planner opens Chat, chooses a prior conversation, creates a new one, reloads, or returns later
**Then** the same ordered `ActivityItemV1` timeline is reconstructed with stable activity identities
**And** replayed events never duplicate visible messages or cards. (FR4, UX-DR6)

**Given** a submitted planner message
**When** the composer is used
**Then** Enter inserts a newline, Ctrl/Cmd+Enter or the visible Send button submits, recoverable failure retains draft text, and sending creates only a planner message
**And** it never encodes Run optimization or approval. (UX-DR7, UX-DR35)

### Story 2.4: Replay Conversation Events Live

As a planner,
I want live conversation updates that survive reconnects,
So that returning to a conversation never duplicates or loses activity.

**Acceptance Criteria:**

**Given** a persisted conversation event stream
**When** the browser connects or reconnects with `Last-Event-ID`
**Then** the server validates stream identity and replays only greater decimal sequences using the canonical SSE ID format
**And** 15-second comment heartbeats carry no ID and are not persisted. (AR21)

**Given** a `Last-Event-ID` that is malformed, references a different stream, or carries a sequence the stream cannot contain
**When** the server validates it
**Then** the connection is rejected with a stable non-disclosing problem response that reveals no other stream's existence, sequence position, or content, and no events are replayed from the mismatched stream
**And** the browser recovers by re-establishing the stream from its own persisted cursor or falling back to labelled polling, without duplicating or silently dropping visible activity. (AR21, UX-DR6, UX-DR20)

**Given** the NFR35 measurement fixture and protocol used in Story 1.4, applied to a conversation whose stream holds the largest Gate A replay backlog
**When** the browser reconnects with a stale `Last-Event-ID`
**Then** every run replays to current state within 5 seconds, measured from reconnect request receipt to delivery of the last outstanding persisted event
**And** the measured values are recorded as release evidence and a miss blocks implementation acceptance of this story. (NFR35)

### Story 2.5: Inspect Scenario Facts Through a Governed Capability

As a planner,
I want the agent to inspect the same authorized scenario facts I can see,
So that conversational investigation is useful without granting database or administrative access.

Acceptance boundary: FR5 and the scheduling inspect capability only. The general `CapabilityManifestV1` contract and its add/remove conformance proof are wholly owned by Story 2.6; nothing in this story depends on Story 2.6 to complete.

**Acceptance Criteria:**

**Given** an authenticated conversation and selected fixture version
**When** the scheduling module is composed for the run
**Then** its inspect capability is granted from current role, site, feature policy, and conversation context through the application-owned registry
**And** model-generated capability names or module loading cannot grant authority. (FR5, AR5)

**Given** the scheduling inspect capability manifest
**When** it is validated
**Then** it declares versioned typed input/output, inspect risk, permission/scope, version semantics, budget/timeout, safe evidence/audit mapping, errors, and evaluation fixtures
**And** the handler calls the scenario-read use case rather than repositories or a second source-data interpretation. (FR5, AR5)

**Given** trusted `AgentDeps`
**When** the model proposes an inspection call
**Then** actor, site, membership, request/run IDs, current versions, policy version, clock, services, and remaining budget come only from server-owned dependencies
**And** arbitrary SQL, shell, credentials, unrestricted network, identity administration, or runtime capability installation do not exist. (FR3, FR6, AR2, AR15)

**Given** the primary Wednesday investigation question
**When** the agent inspects demand, assignments, qualifications, availability, locks, constraints, and relevant saved metrics
**Then** it can answer from allow-listed normalized facts without direct database access or fabricated context
**And** every tool result remains site- and version-scoped. (FR5)

### Story 2.6: Add and Remove a Governed Capability Module [Technical Enabler]

As a product engineer,
I want to extend the agent through a versioned governed module,
So that new product capabilities cannot bypass the core authority, evidence, budget, or evaluation contract.

Unblocks: governed capability growth beyond the MVP scheduling module (FR23). This story is the sole and complete owner of FR23: it defines the general `CapabilityManifestV1` contract and proves add/remove conformance. Placed here, immediately after Story 2.5 establishes the application-owned registry, so the extensibility contract is proven by the epic that owns it rather than deferred to a release milestone. Story 2.5 depends on nothing in this story to be independently acceptable.

**Acceptance Criteria:**

**Given** a demonstration capability module
**When** it is registered
**Then** its `CapabilityManifestV1` declares versioned input/output schemas, permission and site/resource scope, risk class, approval policy, budget/timeout, version/idempotency rules, safe audit/evidence mapping, errors, and evaluation fixtures
**And** the registry rejects any incomplete manifest. (FR23, AR5, AR20)

**Given** a complete registered module
**When** authenticated role, site, feature policy, or conversation context does not grant it
**Then** the capability is absent from the run and cannot be invoked by model-generated names or arguments
**And** loading the module grants no authority by itself. (FR23)

**Given** the module is granted for a deterministic test context
**When** it executes
**Then** it uses trusted dependencies, application use cases, current versions, policy, budgets, idempotency, evidence, and audit like the scheduling module
**And** no branch is added to core agent orchestration control flow. (FR23, AR2)

**Given** the demonstration module is removed
**When** the Story 2.2 harness runs the conformance and regression suites
**Then** core AgentRuntime and the Story 2.5 scheduling inspect capability require no code change and remain green
**And** historical records retain their manifest/contract version references. (FR23, AR24)

### Story 2.7: Ground Schedule Claims in Exact Evidence

As a planner,
I want every schedule-specific answer tied to exact evidence,
So that I can verify the agent's facts instead of trusting a confidence score.

**Acceptance Criteria:**

**Given** an agent response with a numerical or schedule-specific claim
**When** the response is validated for display
**Then** application calculators recompute the claim against immutable scenario/schedule/run versions and attach one or more `EvidenceRefV1` locators
**And** unsupported or version-mismatched numbers fail the grounding gate rather than rendering confidently. (FR7, NFR12, AR11)

**Given** a grounded visible response
**When** Chat renders it
**Then** each supported claim has an adjacent, conventionally identifiable Evidence link naming the exact group, record, field/range, and version
**And** a generic message-level Sources link or confidence score is insufficient. (UX-DR5, UX-DR8, UX-DR32)

**Given** evidence, calculation, or authorization failure for one claim
**When** the response outcome is persisted
**Then** the failure remains distinct and inspectable, safe saved content is preserved, and the agent does not target another row or version
**And** the evaluation fixture records the expected evidence IDs and oracle result. (AR11, NFR27)

### Story 2.8: Jump to Evidence and Return to the Claim

As a planner,
I want to move from an agent claim to its exact source record and back,
So that verification does not make me lose my place or conversation context.

**Acceptance Criteria:**

**Given** an Evidence link in Chat
**When** the planner activates it and then activates Return to claim or browser Back
**Then** app-owned navigation records the originating conversation, message, and claim; opens the cited Scenario Data or Results version/group; loads the exact target window; focuses one highlighted row/cell/record; and on return restores the originating message and focused Evidence link
**And** returning does not resend, regenerate, or silently switch the scenario. (UX-DR2, UX-DR18, UX-DR19, UX-DR34)

**Given** a version mismatch, missing locator, unauthorized target, or stale cached record
**When** evidence navigation resolves the exception
**Then** it uses the distinct required safe panel and recovery actions, never substitutes current/similar data, and never reveals an unauthorized record's existence or value
**And** historical claims with lost evidence remain visible but marked “Evidence unavailable.” (UX-DR20)

**Given** an evidence jump and return
**When** focus behavior is tested
**Then** focus moves to the exact evidence target on jump and returns to the invoking Evidence link on return, proven by the automated accessibility suite established in Epic 1
**And** the full locator is owned by the application and never entrusted to a model-generated URL. (UX-DR27, UX-DR34, AR15)

### Story 2.9: Clarify, Refuse, and Fail Safely

As a planner,
I want ambiguous or unsafe requests handled explicitly,
So that the agent never guesses consequential facts or gains authority from untrusted content.

**Acceptance Criteria:**

**Given** ambiguous worker names, task identity, scope, time, intended consequence, or resource version
**When** the ambiguity could change the chosen capability or result
**Then** the agent emits a structured clarification with safe entity candidates and creates no draft, run, or side effect
**And** the timeline and assistive technology identify it as a clarification. (FR6)

**Given** an unsupported, unauthorized, prohibited, injection-driven, or exhausted-budget request
**When** policy evaluates the proposed call
**Then** the agent refuses with bounded operational copy and a safe next step when one exists
**And** prompt, fixture, model, or tool content cannot add capabilities, permissions, budgets, or approval. (FR6, NFR5, AR15)

**Given** provider timeout, malformed model output, unexpected tool arguments, or AgentRuntime failure
**When** the turn terminates
**Then** the failure maps to a stable visible state, accepted conversation history remains durable, and no unsupported action executes
**And** Scenario Data remains reachable from the Chat error state. (NFR7, UX-DR23, UX-DR25)

**Given** deterministic normal, ambiguity, refusal, injection, provider-failure, and unsupported-number fixtures
**When** the investigation evaluation suite runs on the Story 2.2 harness
**Then** expected tool, arguments, allow/refuse outcome, evidence IDs, and visible state are asserted, and the cases are contributed to the shared golden dataset tagged by capability and risk class
**And** authorization, injection, or grounding regression blocks release. (NFR26, NFR27, NFR28, NFR29)

## Epic 3: Governed and Recoverable Schedule Repair

The planner can turn intent into a reversible draft, explicitly run bounded deterministic optimization, leave and recover the same work, inspect literal outcomes, and compare an exact candidate with its baseline without changing the operational schedule.

**Sequencing note.** Epic 3 delivers two planner-visible slices — the reversible draft (Story 3.1) and, from Story 3.6 onward, the complete run workflow. Stories 3.2–3.5 are deliberately service-only contracts that must exist before a run can be started safely: deterministic candidate construction, job leasing and fencing, the cancellation command, and persisted run state. They are labelled `[Technical Enabler]`, carry platform rather than planner personas, and are accepted through seeded and API-level tests. No story in this epic claims planner-visible value it does not itself deliver: Story 3.6 introduces the **Run optimization** control and command together, and Story 3.7 introduces the Runs workspace that makes the Story 3.4 cancellation command reachable. Nothing in Stories 3.2–3.5 depends on a later story to complete its own acceptance boundary.

### Story 3.1: Create and Revise a Reversible Repair Draft

As a planner,
I want operational intent resolved into a reviewable draft,
So that I can correct constraints and objectives before any computation or baseline change.

**Acceptance Criteria:**

**Given** a grounded request to preserve locks, avoid a named assignment, and reduce overtime
**When** the draft capability resolves the request
**Then** `ProposalV1` records proposal/version IDs, scenario and expected baseline versions, resolved entities, constraints/objectives, preserved locks, consequence summary, and canonical hash
**And** invalid entities, tasks, ranges, combinations, or stale expected versions fail before solver execution. (FR9, AR9, AR20)

**Given** a valid draft
**When** the planner reviews it in Chat
**Then** the Draft card shows resolved entities, constraints/objectives, locks, expected versions, consequences, and “Draft — no baseline change”
**And** revise and reject are separate active controls from Send and approval; this story introduces no Run optimization control or required placeholder. (FR10, UX-DR9, UX-DR35)

**Given** the planner revises or rejects a draft
**When** the command is accepted with expected version and idempotency key
**Then** a new immutable proposal version or terminal rejection is persisted exactly once
**And** the operational baseline pointer and schedule version remain unchanged. (FR10, AR8, AR9)

**Given** the current scenario or baseline version no longer matches the draft
**When** review or execution is attempted
**Then** the draft is visibly stale, computation is blocked, and the planner must refresh or create a new version
**And** no silent rebase occurs. (AR9, UX-DR25)

### Story 3.2: Produce a Deterministic Candidate from an Immutable Snapshot [Technical Enabler]

As the scheduling platform,
we want candidates constructed only by the deterministic scheduler from an immutable frozen snapshot,
So that once Story 3.6 makes optimization startable, no accepted assignment or feasibility claim can originate from model prose.

Planner-visible outcome: none at this position. Accepted through seeded snapshot and solver-adapter tests. Consumed by Story 3.6 (run start) and Story 3.8 (comparison).

**Sizing note:** high implementation breadth — snapshot freezing, solver adapter, candidate creation, and all terminal outcomes. Break into implementation tasks with one demonstrable acceptance boundary per cross-stack concern before sprint commitment.

**Acceptance Criteria:**

**Given** a valid proposal and current authorized scenario/baseline
**When** the application creates `RunSnapshotV1`
**Then** it freezes scenario checksum/version, baseline/proposal versions, locks, constraints/objectives, solver name/config/seed/limit, component versions, accepted time, and input evidence references
**And** the model cannot alter the snapshot after acceptance. (FR11, FR14, AR20)

**Given** an immutable run snapshot
**When** the `SchedulerEngine` executes CP-SAT
**Then** only the solver adapter constructs assignments or validates feasibility and returns typed assignments, metrics, constraint results, warnings, and evidence
**And** domain/application code remains independent of OR-Tools types. (FR11, AR1, AR2)

**Given** a feasible result
**When** completion is validated
**Then** every deterministic hard constraint and preserved lock passes before one immutable candidate `ScheduleVersionV1` is created
**And** all numerical result fields are recomputable from the frozen snapshot and evidence. (NFR11, NFR14)

**Given** infeasible, timed-out, cancelled, or failed execution
**When** the result is finalized
**Then** no candidate schedule version is created and the literal terminal status/reason is preserved
**And** no outcome is collapsed into completed or promotable. (NFR13, AR7)

### Story 3.3: Lease Solver Jobs with Fencing [Technical Enabler]

As the scheduling platform,
we want accepted optimization work leased and fenced durably,
So that when runs become startable in Story 3.6, recovery can never lose a run or repeat its effects.

Planner-visible outcome: none at this position. Accepted through seeded enqueue, lease, and fencing tests at the API and worker boundary.

**Acceptance Criteria:**

**Given** an accepted immutable run snapshot
**When** compute is enqueued
**Then** schedule-run, job, initial persisted event, actor/site/attempt IDs, contract/capability versions, idempotency key, and payload reference commit in one enqueue-compute bundle
**And** acknowledgement occurs only after commit using PostgreSQL leasing rather than a broker or workflow engine. (FR12, AR6, AR18, AR22)

**Given** one or more queued jobs
**When** the worker leases the next authorized job
**Then** the owner-held `workflow.lease_next_job` function uses `FOR UPDATE SKIP LOCKED` and returns job/site/actor context with lease owner, expiry, heartbeat, and monotonically increasing fencing epoch
**And** the runtime lease role cannot directly query tenant/control tables. (AR23)

**Given** a worker loses or exceeds its lease
**When** a stale worker attempts checkpoint or effect commit
**Then** fencing rejects the commit while a recovered worker may safely recompute under a newer epoch
**And** stable job/effect uniqueness prevents duplicate terminal evidence or candidate creation. (FR16, NFR6)

### Story 3.4: Provide the Safe Cancellation Command [Technical Enabler]

As the scheduling platform,
we want a versioned idempotent cancellation command for queued or running work,
So that when Story 3.7 exposes a reachable Cancel control, stopping work can never corrupt state or duplicate effects.

Planner-visible outcome: none at this position — this story delivers the command contract only. The planner-facing Cancel control and its Runs workspace are delivered by Story 3.7. Accepted through API-level cancellation, race, and idempotency tests.

**Acceptance Criteria:**

**Given** an explicit cancellation request for queued or running work
**When** the versioned idempotent command is accepted
**Then** cancellation is persisted once and observed cooperatively by the worker
**And** a race with completion resolves through the closed state machine without impossible or duplicate states. (FR16, AR7, AR8)

### Story 3.5: Persist Literal Run State and Replay Progress [Technical Enabler]

As the scheduling platform,
we want durable literal state and replayable progress events for each run,
So that once runs are startable and monitorable, reconnecting shows the same work instead of an invented restart or ETA.

Planner-visible outcome: none at this position — the progress surface that consumes these events is delivered by Story 3.7. Accepted through seeded state-machine, reconnect-replay, budget-exhaustion, and NFR35 latency tests.

**Acceptance Criteria:**

**Given** an agent run and schedule run before any approval request exists
**When** each aggregate transitions
**Then** queued, running, completed, infeasible, timed-out, cancelled, failed, and cancellation-requested behavior follows the applicable separate closed architecture state machine and emits one monotonic persisted event with stable reason/resource version
**And** adapters may project a combined timeline but never merge stored status types; approval-request behavior is outside this story's acceptance boundary. (FR13, AR7)

**Given** a browser disconnect or page reload during queued/running work
**When** the browser reconnects with the last matching event ID
**Then** only unseen persisted events replay, the same run ID and prior content remain visible, and duplicate activities are suppressed
**And** an unavailable stream falls back to labelled polling/manual refresh without changing authority. (FR13, UX-DR10, UX-DR23)

**Given** a budget or time ceiling is exhausted
**When** the state machine terminates the run
**Then** wall-time exhaustion becomes timed-out and other ceiling exhaustion becomes failed with stable `budget_exhausted` reason
**And** the event persists once with no implicit retry. (FR12, NFR16, AR7)

**Given** the NFR35 measurement fixture and protocol used in Story 1.4
**When** a run is accepted and acknowledged
**Then** every run delivers the first persisted run event to a connected browser within 5 seconds, measured from API acknowledgement to client receipt of that event
**And** the measured values are recorded as release evidence and a miss blocks implementation acceptance of this story. (NFR35)

### Story 3.6: Start Explicit Bounded Optimization

As a planner,
I want Run optimization to start only the exact reviewed computation,
So that drafting or ordinary chat never silently authorizes solver work.

**Acceptance Criteria:**

**Given** a current valid draft and the Run optimization control introduced by this story
**When** the planner activates Run optimization or makes an equivalent explicit current request
**Then** the compute capability validates trusted actor/site, proposal and baseline versions, policy, risk, invariants, budget, and idempotency before enqueueing one durable job
**And** merely sending, reviewing, or accepting draft parameters does not start computation; every mutating tool call carries current authorization, expected version, idempotency protection, and authoritative audit evidence
**And** the control, accessible sequencing copy, command contract, and enabled/disabled states are delivered together in this story. (FR12, NFR2, AR5)

**Given** release configuration
**When** the compute command is accepted
**Then** positive application-owned ceilings exist for solver time, agent iterations, model/tool calls, retries, tokens, site concurrency, and total elapsed time
**And** no ceiling originates from model output. (FR12, NFR16)

**Given** the same actor/site/operation/idempotency key and canonical body hash
**When** the command is replayed
**Then** it returns the original semantic run response and run ID
**And** a conflicting body hash or expected version fails without a second job. (FR16, AR8)

**Given** current site concurrency is exhausted or the draft is stale
**When** the planner requests a run
**Then** the command returns a stable bounded/stale problem response and creates no job
**And** Chat retains the draft and offers only valid recovery actions. (FR6, FR12)

### Story 3.7: Monitor, Cancel, and Reopen Runs

As a planner,
I want a Runs workspace and progress cards,
So that I can leave Chat, monitor accepted work, cancel when valid, and reopen one exact result.

**Acceptance Criteria:**

**Given** runs for the selected scenario
**When** the planner opens Runs
**Then** a stable newest-first table shows run ID, exact literal status, accepted/updated time, scenario/proposal/baseline versions, and safe actions
**And** row navigation, Cancel, Retry, and identifier-copy controls are separately labelled and keyboard-operable. (FR13, FR16, UX-DR17, UX-DR21)

**Given** no runs, loading, list failure, or model outage
**When** Runs renders
**Then** it uses the shared loading, empty, and alert states from the Story 1.6 primitives without hiding saved data
**And** manual deterministic Run optimization remains available when permitted. (FR8, UX-DR23, UX-DR25)

**Given** a run reaches a literal terminal state
**When** its progress card or row renders
**Then** completed, infeasible, timed-out, cancelled, and failed are textually and structurally distinct with only valid next actions
**And** no percentage, ETA, feasibility, or promotion control is invented. (NFR13, UX-DR10, UX-DR13)

### Story 3.8: Compare Candidate and Baseline Results

As a planner,
I want to inspect exactly what a candidate changes,
So that I can judge coverage repair and trade-offs before any approval decision.

**Acceptance Criteria:**

**Given** a completed feasible candidate and its frozen baseline
**When** `ComparisonV1` is calculated
**Then** it names both versions and includes affected workers, shifts, tasks/roles, interval coverage, overtime, total cost, objective components, constraint status, warnings, and unresolved gaps
**And** every value/delta is produced or verified by application calculators against immutable evidence. (FR15, AR11, AR20)

**Given** a selected completed run
**When** Results renders
**Then** deterministic status, warnings, metrics, comparison, schedule, and evidence remain available independently of model-generated summaries
**And** missing metrics say “Not computed” rather than zero or an invented value. (UX-DR11, UX-DR21)

**Given** a failed, infeasible, timed-out, or cancelled run
**When** Results renders
**Then** the literal non-promotable outcome and available evidence are distinct from fetch failure and completed result
**And** no enabled approval action is displayed. (UX-DR13, UX-DR25)

**Given** the current baseline changes after comparison
**When** the result is revisited
**Then** the comparison is marked stale with expected/current versions and remains historical evidence
**And** it is not silently recalculated or represented as current. (AR9)

### Story 3.9: Continue Deterministic Work During Model Outage

As a planner,
I want saved work and manual optimization to remain usable when the model is unavailable,
So that conversational assistance is never the recovery or scheduling authority.

**Acceptance Criteria:**

**Given** AgentRuntime or its provider is unavailable
**When** the planner opens Chat
**Then** durable conversation history remains visible, the composer/agent actions are disabled with narrow outage copy, and links to Scenario Data, Runs/manual optimization, and saved Results remain active
**And** the full workspace is not described as offline. (FR8, UX-DR5, UX-DR25)

**Given** a selected fixture during model outage
**When** the planner starts the existing manual deterministic solver flow
**Then** it uses the same scenario projection, run snapshot, trusted site/version checks, budgets, job recovery, idempotency, CP-SAT engine, and evidence model
**And** it does not invoke AgentRuntime. (FR8, AR15)

**Given** Logfire export is disabled or fails
**When** manual or agent-originated deterministic work executes
**Then** product state, solver behavior, saved results, CloudWatch diagnosis, and authoritative audit remain correct
**And** telemetry failure neither authorizes nor blocks work. (NFR10, AR12)

### Story 3.10: Prove Repair Correctness

As the product team,
we want deterministic solver outcomes proven before release,
So that a successful demo proves correctness rather than lucky conversational behavior.

**Acceptance Criteria:**

**Given** the seeded Wednesday outbound fixture
**When** the deterministic repair suite runs on the Story 2.2 harness
**Then** it closes the gap, preserves locks, creates zero hard violations, and keeps overtime at or below baseline in every CI run
**And** any miss blocks release. (NFR11, NFR14, NFR29)

**Given** the infeasible variant and timeout/cancel/failure fixtures
**When** they run
**Then** each yields its exact non-promotable state and evidence without a candidate
**And** no false success or status collapse is accepted. (NFR13)

### Story 3.11: Prove Recovery and Idempotency

As the product team,
we want interruption and replay proven before release,
So that accepted work is never lost, duplicated, or silently rebased by a failure.

**Acceptance Criteria:**

**Given** worker kill, lease expiry, browser reconnect, command replay, cancellation race, stale draft, and conflicting idempotency fixtures
**When** recovery tests execute on the Story 2.2 harness
**Then** accepted work remains discoverable and every semantic effect occurs at most once
**And** the same run/evidence lineage is retained. (NFR6, NFR7)

**Given** any recovery or idempotency case above
**When** it regresses
**Then** release is blocked regardless of aggregate helpfulness
**And** the failure names the exact gate and artifact versions. (NFR29)

### Story 3.12: Prove the Repair Browser Journey

As the product team,
we want the repair journey proven correct end to end in the browser before release,
So that the planner can complete draft, run, and comparison work through a reconnect without losing evidence targeting.

**Acceptance Criteria:**

**Given** the browser repair journey through Chat, Runs, and Results
**When** one end-to-end test executes draft, Run optimization, mid-run reconnect, terminal outcome, and comparison
**Then** the same run ID and prior content survive the reconnect, each literal state renders its required text, and every evidence link resolves to its exact target
**And** a regression in evidence targeting or journey completion blocks release. (NFR29, UX-DR10, UX-DR13)

**Given** the same journey
**When** the automated accessibility suite established in Epic 1 runs against its surfaces
**Then** keyboard operability, focus management, and semantic status text pass without manual assistive-technology verification
**And** an accessibility regression blocks release. (NFR18, NFR20, NFR29)

## Epic 4: Exact Baseline Decision and Decision Record

The planner can approve only the exact current feasible candidate as the internal operational baseline and later reconstruct who decided what, from which evidence and versions, with stale or repeated actions failing closed.

### Story 4.1: Request Approval for One Exact Feasible Candidate

As a planner,
I want approval proposed only for the exact feasible candidate I reviewed,
So that optimization completion never implicitly changes the operational baseline.

**Acceptance Criteria:**

**Given** a completed feasible candidate and current baseline comparison
**When** the planner or agent requests baseline approval
**Then** a pending `ApprovalBindingV1` records actor, site, action, normalized parameter hash, candidate/version, baseline/version, consequence-summary hash, policy version, creation/expiry, and one-time state
**And** the related agent run pauses in approval-required state with a persisted event
**And** this story independently owns `ApprovalRequest` persistence, the agent-run approval-required transition, and its literal presentation. (FR13, FR17, FR18, AR10, AR20)

**Given** a browser disconnect or reload while an agent run is approval-required
**When** Chat or Results reconstructs the persisted activity stream
**Then** the approval-required state, exact binding, and only currently valid decision controls replay once without losing or duplicating the pending decision
**And** the same agent-run and approval identifiers remain visible. (FR13, UX-DR6, UX-DR10, UX-DR23)

**Given** a missing candidate or a run that is infeasible, timed-out, cancelled, failed, or stale
**When** approval is proposed
**Then** policy rejects the request and creates no approvable binding
**And** optimization completion or model prose never changes the baseline pointer. (FR17, AR2)

**Given** a request-approval command replay
**When** actor/site/operation/body hash and expected versions match
**Then** the original binding/result is returned
**And** altered parameters or versions fail without a second effective request. (FR18, AR8)

### Story 4.2: Review and Decide the Exact Approval

As a planner,
I want a separate approval review that names the exact consequence and versions,
So that I cannot confuse running optimization with replacing the operational baseline.

**Acceptance Criteria:**

**Given** a current pending approval
**When** its Approval request renders in Chat or Results
**Then** it shows candidate, current baseline, material parameters, consequence summary, policy/expiry context, and versions before the separate Approve as baseline or Reject controls
**And** the accessible approval name states which candidate replaces which baseline. (FR18, UX-DR12, UX-DR29)

**Given** the planner closes the dialog, sends chat text, revisits the page, or reviews the draft/result
**When** no explicit authenticated decision is submitted
**Then** the approval remains pending and no baseline effect occurs
**And** approval is never encoded as ordinary text or inferred from rendering. (FR18, AR10, AR14)

**Given** the candidate, baseline, parameters, consequence hash, the initiating actor's active membership in the bound site, policy, or expiry no longer matches
**When** the planner attempts approval
**Then** the request becomes stale or expired with literal expected/current context, the action is disabled/rejected, and no silent rebase or resubmission occurs
**And** the planner is offered only refresh, revise, rerun, inspect, or return actions that are currently valid. (FR18, UX-DR12, UX-DR13)

**Given** rejection
**When** the authenticated decision commits
**Then** the binding becomes terminal rejected, the agent run cancels/ends according to its closed graph, and the baseline remains unchanged
**And** replay returns the same semantic rejection. (AR7, AR10)

**Given** the approve, reject, and stale-approval flows
**When** they render alongside Send and Run optimization
**Then** Approve as baseline remains distinct from Run optimization in language, control, consequence, and visual treatment; stale actions are disabled; dialogs restore focus; and the accessible approval name states which candidate replaces which baseline
**And** these are proven by the automated accessibility suite established in Epic 1, without manual assistive-technology verification. (NFR18, NFR19, UX-DR12, UX-DR27, UX-DR35)

### Story 4.3: Promote the Baseline Atomically with Audit

As a planner,
I want a valid approval to promote exactly one existing candidate once,
So that the operational baseline and its authoritative decision record cannot diverge.

**Acceptance Criteria:**

**Given** a valid pending approval
**When** Approve as baseline is processed
**Then** the deciding actor/site/active membership is re-resolved from the authenticated server session as the command-admission guard, and the shared command-transaction revalidation checks that the initiating actor identified by the binding still has an active membership in the binding's site, plus policy, binding hashes, candidate feasibility/version, baseline version, expiry, and idempotency
**And** a client boolean or prior UI state is never sufficient authorization. (FR18, NFR8)

**Given** all revalidation passes
**When** the transaction commits
**Then** the approval moves directly from pending to consumed, the site baseline pointer moves to the existing candidate, one successful audit envelope and persisted event are written, and prior schedule versions remain unchanged
**And** any failure rolls back the entire bundle to pending with no baseline change. (FR19, NFR9, AR10, AR22)

**Given** a retry or recovered command after successful promotion
**When** the same effect key is processed
**Then** uniqueness returns the original semantic result and cannot create another candidate, audit outcome, event, or pointer movement
**And** a different body/version is rejected. (FR19, NFR6, AR8)

**Given** successful, denied, stale, failed, cancelled, rejected, or expired consequential attempts
**When** authoritative evidence is recorded
**Then** successful mutation audit is transactionally unique by site/effect/outcome and non-success audit is reliably unique by site/attempt
**And** observability being disabled cannot remove or prevent the record. (FR21, NFR31, AR12)

### Story 4.4: Inspect Complete Decision Provenance

As a planner or reviewer,
I want one decision timeline from request through resulting baseline,
So that I can reconstruct what happened without access to hidden model reasoning.

**Acceptance Criteria:**

**Given** a run and any approval outcome
**When** provenance is queried
**Then** the ordered projection links request, evidence consulted, concise application-owned decision summary, typed tool proposals/results, guardrail/policy outcomes, solver run, comparison, approval, execution, and before/after versions
**And** every item retains site/actor and relevant request, attempt, conversation, agent-run, tool, approval, job, solver-run, audit, schedule, and evidence IDs. (FR20, NFR32)

**Given** the Results view
**When** the Provenance timeline renders
**Then** literal outcomes, stable IDs, evidence links, before/after versions, and collapsible safe details render with the semantics the Epic 1 automated accessibility suite asserts
**And** hidden chain-of-thought, raw prompts/completions, sensitive tool payloads, and credentials never appear. (UX-DR22, AR15)

**Given** a saved historical result during model or telemetry outage
**When** provenance is opened
**Then** authoritative product/audit records and immutable evidence remain available
**And** optional model summaries or traces may fail independently without removing the decision path. (FR20, NFR10)

**Given** unauthorized audit or evidence access
**When** the provenance query resolves a target
**Then** site scope is revalidated and protected existence/value is not disclosed
**And** the normal application path cannot update or delete audit events. (FR21, NFR33)

### Story 4.4a: Supply Audit Evidence References [Technical Enabler]

As the product team,
we want every consequential audit row to carry the checksum-bound evidence locators of the candidate its attempt targeted,
So that NFR32's evidence clause rests on a record that can actually fail, and Story 4.5 has a real oracle rather than a structurally empty field.

**Acceptance Criteria:**

**Given** a consequential attempt that resolves a candidate schedule version — request, promotion, terminal decision, or pre-write denial
**When** its audit event is written
**Then** the row carries that candidate's evidence references unchanged from the sealed `schedule_version` row, with no re-derivation, no re-checksumming, and no backfill of any prior row
**And** an attempt whose candidate does not resolve writes an empty set, proven by a demonstrated-red test rather than assumed. (FR21, NFR32)

**Given** the existing contracts and schema
**When** this story lands
**Then** no migration, no new column, no new port, and no new field on `ApprovalBindingV1` is introduced — the candidate is supplied from the `get_candidate` call that `request_approval` and `revalidate_binding` already make, on the repository `decide_approval_route` already injects
**And** `promote_baseline` receives the candidate as a parameter from its only caller, never by acquiring a repository of its own. (AD-1, AD-2)

**Given** a denial row written at the admission check, before revalidation runs
**When** its evidence references are read
**Then** they identify the candidate the refused attempt targeted, not evidence the attempt consulted, and both the story and the code state that distinction
**And** audit-sourced provenance items render these references with the semantics Story 4.4 already ships, without a new contract field. (FR20, NFR32)

**Given** the scope control declared by Story 4.4
**When** this story lands
**Then** `"audit_evidence_refs:empty_at_every_write_site"` is removed from `SCOPE_CONTROLS` in `application/contracts/decision_provenance.py`, because it is no longer true
**And** the corresponding deferred-work ledger entry is closed in the same commit, citing this story. (FR21, NFR32)

### Story 4.5: Prove Approval and Audit Invariants

As the product team,
we want consequential edge cases proven deterministically before release,
So that stale state, retries, or observability failure can never produce an unrecorded baseline change.

**Evidence scope note.** In this codebase evidence is a version-bound projection locator (`EvidenceRefV1` — `scenario_version_id` plus the checksum triple plus a record locator), not a stored object; no evidence port and no object-storage adapter exists. AR12's and AR23's create-only S3 evidence permissions are hosted-deployment requirements discharged by **Story 6.2** (`epics.md:1463`), not by this proof story. The earlier restatement at `sprint-change-proposal-2026-08-09-epics-2-5.md:149` removed the *hosted* dependency but kept an object-storage premise that has no subject here; this AC removes the premise rather than softening it a third time.

**Telemetry scope note (2026-09-03, Epic 4 retrospective action A6).** AC4 previously read *"telemetry export disabled and **CloudWatch** degraded independently"*. There is no CloudWatch subject in this repository — the same defect as the object-storage premise above, in the adjacent AC of the same story, and it survived because only AC3 was re-examined on 2026-09-01. CloudWatch is a hosted concern owned by **Story 6.1/6.2**. The clause is restated below against the subject Story 4.5 actually proved: the real local telemetry seam, exercised under both disabled-by-import-absence and raising-exporter conditions. This is a wording correction to a satisfied AC, not a scope change — no proof is added, removed, or re-run, which is why it is recorded here rather than routed through `bmad-correct-course` as the AC3 correction was.

**Acceptance Criteria:**

**Given** mismatch, expiry, replay, altered parameter, changed baseline, changed membership/policy, rejection, and repeated-decision fixtures
**When** the approval suite runs on the Story 2.2 harness
**Then** every invalid attempt fails closed with its exact terminal/pending outcome and zero baseline effect
**And** every valid approval promotes once with one authoritative audit/event bundle. (FR18, FR19, NFR8, NFR29)

**Given** database failure during the promotion bundle
**When** any write in approval consumption, baseline pointer, audit, or event fails
**Then** the entire transaction rolls back and the binding remains pending
**And** retry can complete exactly once after the fault clears. (NFR9)

**Given** promoted, rejected, expired, stale, and denied decisions, plus an evidence locator whose pinned scenario version no longer resolves
**When** each audit event and provenance item for those decisions is resolved through the evidence locator contract
**Then** every `EvidenceRefV1` resolves `resolved` against its pinned `scenario_version_id`, or reports `not_found` or `version_mismatch` explicitly, and no record presents an unresolvable locator as valid
**And** each audit row for an attempt that resolved a candidate carries that candidate's checksum-bound references, while a row whose candidate is absent carries an empty set asserted as absence rather than assumed. (AR12, AR23)

**Given** telemetry export disabled by import absence, and independently a configured exporter that raises
**When** approval, rejection, or stale attempts execute
**Then** product behavior and authoritative audit remain correct and inspectable
**And** audit continuity or idempotency regression blocks release. (FR21, NFR10, NFR29)

### Story 4.6: Prove Workflow State Semantics and Automated Accessibility

As a planner,
I want every workflow state to communicate its literal meaning and remain operable without manual assistive-technology verification,
So that I can distinguish drafts, progress, outcomes, and decisions correctly across the completed journey.

Consolidates the former Stories 4.6–4.9. Proof method is automated only, consistent with `EXPERIENCE.md`'s Accessibility Floor: the state matrix is asserted against the Story 1.6 fixture catalogue and the completed surfaces, and conformance is asserted by the Epic 1 axe/semantic/browser suites. No screenshot baseline and no manual assistive-technology pass is required or accepted as proof.

**Acceptance Criteria:**

**Given** messages, drafts, runs, comparisons, approvals, terminal outcomes, alerts, skeletons, empty states, and provenance across Epics 1–4
**When** every literal state renders
**Then** text, structure, and inherited components communicate meaning without color-only status, and each state is textually and structurally distinct
**And** no confidence gauge, AI glow, gradient, animated avatar, pulse, celebration, invented percentage, ETA, or merged action treatment appears. (UX-DR10, UX-DR13, UX-DR32, UX-DR35)

**Given** the complete desktop journey
**When** automated accessibility checks run at 100% and 200% zoom, with increased text spacing and reduced motion
**Then** WCAG 2.2 AA and the documented focus, overflow, touch-target, table, and state rules pass, with no page-level horizontal scroll, overlapping sticky text, or unreadable long identifier
**And** any accessibility regression blocks release. (NFR18, NFR20, NFR29, UX-DR31, UX-DR34)

**Given** the consolidated state-semantics and accessibility suite
**When** its result is persisted
**Then** `evidence/story-4.6/state-semantics-and-accessibility.json` names every tested state and binds the tested artifact versions
**And** the state matrix and the accessibility pass must each succeed for this story to complete. (NFR27, NFR29)

## Epic 5: Demonstrable Local Planner Workspace

The complete planner journey runs reproducibly on any developer machine from one command, with agent runs instrumented for latency, budget, and cost, no sensitive content leaving the application boundary, and a published walkthrough that lets a reader understand and run the system without prior context.

**This epic is the portfolio milestone.** It is the point at which ShiftMind is a complete, demonstrable, independently verifiable artifact. Hosted deployment is Epic 6 and is deliberately sequenced after it.

**Coverage note.** NFR10's telemetry-independence outcome is proven by Story 3.9's third acceptance criterion and is not restated here. NFR35's four thresholds are owned by Stories 1.4, 1.5, 2.4, and 3.5 and are measured on the CI reference environment per AD-26, never on a hosted topology — they do not depend on this epic or Epic 6.

### Story 5.0: Compare a Candidate Against the Real Promoted Baseline [Corrective Insert]

**Inserted 2026-09-03** by `sprint-change-proposal-2026-09-03.md`, from Epic 4 retrospective action A3(i). Numbered `5.0` rather than renumbering 5.1–5.4 because it is a corrective prerequisite, not a member of the portfolio sequence. It fires the spine's Deferred trigger *"first story needing authoritative baseline-side metrics after a real promotion"* — Story 5.4's walkthrough is that story.

**The defect.** `calculate_comparison` reads its baseline side from `ScenarioProjectionReader.get_baseline_assignments`, whose PostgreSQL implementation applies its query to a hardcoded empty tuple. With no promoted baseline the EAD-8 guard does not fire, so the comparison is computed against an empty baseline and renders fabricated deltas — cost delta equal to the candidate's entire cost, an all-`Satisfied` baseline constraint list, every worker reported `added`. After the first promotion the guard fires and the comparison disappears permanently. There is no state in which the feature works. EAD-8's premise that the pre-promotion rendering was *honest* is false and is amended by this proposal.

**The fix is a change of source, not a new supply.** `ScheduleVersionV1.assignments` is already `tuple[AssignmentV1, ...]`; `schedule_version.payload` already persists it; `site_baseline.schedule_version_id` already FK-pins the promoted row; `snapshot.baseline_schedule_version` is already `str(schedule_version_id)`. The wage and selected-shift prerequisites named in the Deferred row gate the `schedule_assignment` supply for the **projection** consumer, not this path.

As a planner,
I want the comparison to measure my candidate against the schedule that is actually running,
So that I can judge a repair before approving it — and, when no baseline exists yet, be told so rather than shown deltas against nothing.

Unblocks: Story 5.4's walkthrough claim that the approve → promote → compare loop is reproducible.

**Acceptance Criteria:**

**Given** a completed candidate whose run snapshot froze a non-null `baseline_schedule_version`
**When** `ComparisonV1` is calculated
**Then** the baseline assignments are read from the `schedule_version` row that identifier names, through a site-scoped repository read
**And** every baseline-side metric, constraint result, and assignment-diff entry derives from those assignments, and `ComparisonV1.evidence_refs` carries a baseline locator for each. (FR15, AR11, AR20)

**Given** a site with no promoted baseline
**When** Results renders the comparison
**Then** `baseline_metrics` is null, every delta reads "Not computed", and the baseline constraint list states that no baseline exists rather than listing satisfied constraints
**And** no assignment-diff entry claims a worker, shift, or task was added relative to a baseline that does not exist. (UX-DR11, UX-DR21)

**Given** a non-null frozen `baseline_schedule_version`
**When** the `schedule_version` row it names cannot be read
**Then** the comparison fails closed exactly as it does today
**And** a readable version whose assignment set is legitimately empty produces a real comparison instead, with that emptiness visible rather than inferred.

**Given** a real promoted baseline
**When** a later run completes and its result is read
**Then** the comparison is present and its deltas are measured against the promoted schedule, proven end to end against PostgreSQL
**And** each new guard is recorded in a demonstrated-red mutation table.

**Out of scope, deliberately.** The hardcoded `baseline_assignment_count=0` in the overview projection and `get_baseline_assignments` itself: they serve the Scenario Data workspace, a different consumer whose need does genuinely depend on the Stories 3.8/3.10 prerequisites. This story changes what *comparison* reads and leaves the projection group unchanged.

### Story 5.1: Instrument Agent Runs for Latency, Budget, and Cost

As a portfolio operator,
I want product and workflow activity correlated across structured logs and metrics,
So that I can diagnose one run and understand where its latency, budget, and cost went.

**Acceptance Criteria:**

**Given** API, worker, AgentRuntime, database, and solver execution
**When** operational telemetry is emitted
**Then** structured JSON logs and metrics record acknowledgement/first-event/end-to-end/model/tool/solver timings, queue and approval age, tokens, estimated cost, and budget outcomes
**And** every value is attributable to one agent run. (NFR15)

**Given** a completed agent run
**When** the operator searches product state, authoritative audit, and structured logs by its stable run or correlation identifier
**Then** the same lineage is discoverable across all three without exposing sensitive content
**And** authoritative audit remains the business record of truth. (NFR22)

### Story 5.2: Prevent Content and Secret Leaks

As a security reviewer,
I want logs and any exported traces limited to explicitly safe metadata,
So that diagnosis cannot leak credentials, workforce data, prompts, schedules, tool payloads, or approval evidence.

**Acceptance Criteria:**

**Given** structured application logging and any configured trace export
**When** logs and traces emit
**Then** content and binary capture are disabled by default, only allow-listed sanitized attributes may leave the application, and credentials, workforce data, prompts/completions, schedule payloads, tool arguments/results, and approval evidence are scrubbed
**And** external model and telemetry providers receive only the minimum explicitly configured content. (NFR3, NFR4, NFR30)

**Given** secret, prompt-injection, and adversarial telemetry fixtures
**When** the minimization suite executes
**Then** any prohibited content in a log or exported trace fails the story
**And** `evidence/story-5.2/content-minimization-report.json` records the tested channels, fixtures, and artifact versions. (NFR5, NFR27, NFR29)

### Story 5.3: Run ShiftMind Reproducibly from One Command [Technical Enabler]

As a reviewer of this portfolio,
I want to start the whole system from a clean clone with one command,
So that I can exercise the planner journey myself without reconstructing an environment.

Unblocks: Story 5.4's walkthrough, and the release-gate report's image binding.

**Acceptance Criteria:**

**Given** a clean clone and a documented prerequisite set
**When** the reviewer runs the single documented start command
**Then** application, worker, database, and seeded immutable fixtures come up together, the seeded planner can sign in, and the primary journey is completable end to end against deterministic model doubles with no provider credential required
**And** a live-provider run is available through explicit configuration but is never required to demonstrate the system. (NFR21, NFR26)

**Given** the local build
**When** application images are produced
**Then** tested constraints and lockfiles pin each used dependency version and the built image exposes a recorded content-addressed digest
**And** that digest satisfies the image binding every evaluation report requires, so no release evidence depends on hosted infrastructure. (NFR27, AR27)

### Story 5.4: Publish the Portfolio Walkthrough

As a reviewer of this portfolio,
I want one document that explains what ShiftMind proves and how to verify it,
So that I can judge the system's engineering without reading the whole repository.

**Acceptance Criteria:**

**Given** the completed local system
**When** the walkthrough is published
**Then** it states the product thesis and the three-way authority partition, walks the Wednesday-coverage journey with real output, shows the architecture boundary that keeps domain and application free of framework and provider types, and links to the evaluation reports, the release-gate report, and the Gate A/Gate B evidence artifacts
**And** every claim it makes about behavior is reproducible by the Story 5.3 command. (AR1, AR2)

**Given** the portfolio's current scope and configuration
**When** limitations are documented
**Then** single-planner scope, fixture-only source data, conversation/audit/snapshot/log retention settings, absence of hosted deployment at this milestone, and non-customer status are explicit
**And** no enterprise latency, availability, recovery, concurrency, or cost promise is made. (NFR17, NFR34)

## Epic 6: Reliable Hosted Planner Workspace

The planner can sign in to the hosted ShiftMind workspace and trust it: it is reproducibly deployed from reviewed infrastructure code, diagnosable without privacy leaks, and its invariants hold through the real edge, load-balancer, and database topology.

**Sequenced after the Epic 5 portfolio milestone.** Nothing in Epics 1–5 depends on this epic; it adds the hosted trust proof to an already complete and demonstrable system. Gate C is this epic's boundary, distinct from Gate B, which Epic 5 completes.

### Story 6.1: Provision AWS Edge, Identity, and Network Boundaries [Technical Enabler]

As a portfolio operator,
I want reviewed infrastructure code for the hosted edge, identity, and network,
So that browser access reaches only the intended private application boundary.

**Acceptance Criteria:**

**Given** the portfolio Terraform environment
**When** initialization, validation, and reviewed plan run
**Then** it provisions Route 53/ACM, CloudFront, a private S3 SPA with OAC, ALB, Cognito with public sign-up disabled, and private API/worker/data network boundaries
**And** no console-only resource is required for a reproducible environment. (NFR21, AR17)

**Given** public and service-to-service connections
**When** transport/storage policy is inspected
**Then** public hops and CloudFront-to-ALB use HTTPS/TLS 1.2+, RDS requires TLS, and S3/RDS/logs/secrets use encryption at rest with Block Public Access
**And** API ingress is only through ALB/CloudFront while the worker has no inbound listener. (AR17)

### Story 6.2: Provision AWS Data and Least-Privilege Runtime [Technical Enabler]

As a portfolio operator,
I want reviewed infrastructure for persistent data and runtime identities,
So that schedules, evidence, secrets, images, logs, and cost controls remain private and least-privileged.

**Acceptance Criteria:**

**Given** the completed private network and identity boundary
**When** the data/runtime Terraform plan is applied
**Then** it provisions non-public RDS PostgreSQL, create-only versioned S3 evidence, ECR, Secrets Manager, CloudWatch, AWS Budgets/cost tags, and separate API/worker task roles
**And** database/evidence endpoints are reachable only from their intended runtime boundary. (NFR21, AR17)

**Given** deployment, API, worker, lease, and owner roles
**When** privilege tests run
**Then** long-lived deploy keys are absent, GitHub Actions uses OIDC, runtime roles own no tables and cannot bypass RLS, and API/worker task roles receive only their required AWS actions
**And** S3 application roles cannot delete or overwrite evidence objects. (AR23)

**Given** the architecture's planned infrastructure dependencies
**When** infrastructure manifests are finalized for this gate
**Then** immutable image digests own deployed patch movement, building on the dependency pinning Story 5.3 established locally
**And** unused planned dependencies are not added prematurely. (AR27)

### Story 6.3: Deploy Immutable API, Worker, and Web Releases [Technical Enabler]

As a portfolio operator,
I want health-gated delivery of one immutable release across web, API, and worker,
So that the hosted planner workflow is reproducible and diagnosable.

**Sizing note:** high implementation breadth — CI/CD, immutable multi-process deployment, edge SSE proof, correlation, and environment limitations. Break into implementation tasks with one demonstrable acceptance boundary and one owner per concern before sprint commitment.

**Acceptance Criteria:**

**Given** a reviewed commit and passing release gates
**When** GitHub Actions builds and deploys
**Then** immutable content-addressed frontend and backend images/assets are published, the same backend image runs separate least-privilege API and worker commands, and deployment uses environment-reviewed Terraform plans
**And** no long-lived AWS deploy credential is used. (NFR21, AR17)

**Given** CloudFront, ALB, API, and persisted SSE
**When** the end-to-end streaming test executes
**Then** auth/API/SSE caching is disabled as required; cookies, query strings, Origin, CSRF, `Last-Event-ID`, and methods forward correctly; heartbeat arrives before proxy timeouts; reconnect replays only unseen events
**And** the test assumes no undocumented buffering toggle. (AR21)

**Given** the low-cost portfolio topology
**When** environment limitations are documented
**Then** one API task, one worker task, small RDS capacity, networking/availability limitations, and non-customer status are explicit
**And** no enterprise latency, availability, recovery, concurrency, or cost promise is made. (NFR17)

### Story 6.4: Prove Hosted Invariants, Parity, and Mutation Denial

As the product team,
we want the security, authority, and parity invariants re-exercised through the real hosted topology,
So that CloudFront, ALB, ECS, RDS, and object storage cannot widen agent authority or introduce fact drift.

Acceptance boundary: a smoke-level re-proof through the deployed topology only. The invariants themselves are proven exhaustively against the application by Stories 2.9, 3.11, and 4.5; this story proves the deployment boundary did not weaken them.

**Acceptance Criteria:**

**Given** the deployed topology
**When** the hosted smoke suite executes unauthenticated access, cross-site denial, stale approval, prompt injection, and authoritative-audit continuity checks
**Then** every invariant produces its expected deterministic outcome without a duplicate effect or unauthorized disclosure
**And** any failure blocks hosted release. (NFR29, AR15)

**Given** one immutable hosted fixture version exposed through the deployed Scenario Data route and API, and the corresponding agent inspection capability
**When** the hosted parity suite compares both normalized projections, and conventional POST, PUT, PATCH, and DELETE probes test source-data modification paths
**Then** values, stable identifiers, ordering, evidence targets, and versions match exactly through the CloudFront/ALB/API/generated-client boundary, and no supported mutation endpoint or browser mutation control exists
**And** any mismatch or discovered mutation path blocks hosted release. (FR22, FR24, NFR29, AR4)

**Given** the hosted suite completes
**When** its result is persisted
**Then** `evidence/story-6.4/hosted-invariant-report.json` binds topology, fixture, application, code, and image versions
**And** the invariant, parity, and mutation-denial slices must each pass. (NFR27)

### Story 6.5: Provide Backups and a Tested Rollback Path

As a portfolio operator,
I want automated backups and a documented way back to the previous release,
So that a hosted failure or unhealthy image cannot destroy durable work.

**Acceptance Criteria:**

**Given** the hosted database and evidence lifecycle
**When** infrastructure is provisioned
**Then** automated database backups retain seven days, teardown requires a final snapshot, object-storage evidence is versioned and create-only, and application log retention is explicit
**And** the product makes no regulatory-WORM or customer-deletion claim. (NFR24, NFR34, AR17)

**Given** an unhealthy release
**When** the documented rollback procedure runs
**Then** the prior schema-compatible API/worker image digest is redeployed and current durable jobs and state remain valid
**And** the procedure, its schema-compatibility precondition, and its limitations are recorded in the deployment runbook. (NFR23)

## Release Gate (Definition of Done)

Release evaluation is not an epic or story. Each epic proves its own slice through its own proof stories on the Story 2.2 harness, and this checklist holds only the aggregate thresholds that no single story can measure.

**Gate B — the portfolio milestone.** After Epic 5's stories pass, the Evaluation/QA owner evaluates the Gate B rows below as Epic 5's final definition of done and persists `evidence/epic-5/release-gate-report.json`. Every Gate B threshold is measurable locally on the CI reference environment; none requires hosted infrastructure.

**Gate C — hosted.** After Epic 6's stories pass, the same owner evaluates the Gate C rows and persists `evidence/epic-6/hosted-gate-report.json`.

| Gate | Milestone | Threshold | Evidence owner |
|---|---|---|---|
| Deterministic-first CI | B | No live-provider result satisfies any gate on its own; live suites are named, gated, budgeted, non-authoritative. | Story 2.2 |
| Report version binding | B | Every evaluation report binds dataset, evaluator, model, prompt, tool, policy, application, scenario, solver, code, and image versions; the image binding is satisfied by Story 5.3's locally built digest. | Stories 2.2, 5.3 |
| Golden dataset size | B | At least 50 versioned cases, at least four per allowed capability, and at least ten consequential/prohibited cases; case count may later change only from reviewed failure diversity. | Stories 2.9, 3.10–3.12, and 4.5–4.6 contribute; Gate B measures |
| Tool routing | B | At least 90% overall and 100% for consequential/prohibited cases. | Gate B |
| NFR35 internal thresholds | B | All four timing thresholds met under the canonical protocol on the CI reference environment (AD-26). | Stories 1.4, 1.5, 2.4, 3.5 |
| Blocking regressions | B | Any regression in authorization, approval, isolation, hard constraints, grounding, idempotency, authoritative audit, viewer parity, recovery, or accessibility blocks release regardless of aggregate helpfulness, and the failure names the exact gate and artifact versions. | Every proof story; Gate B confirms |
| Hosted invariants and parity | C | Hosted smoke invariants, viewer/agent parity, and mutation denial pass through the deployed topology. | Story 6.4 |
| Backup and rollback | C | Automated backups are configured and the rollback procedure is documented and exercised. | Story 6.5 |

> **Dataset-threshold caveat.** The 50-case floor was set when thirteen Epic 5 stories were expected to contribute cases. The hosted stories now in Epic 6 contribute infrastructure assertions rather than agent-behavior cases, so the floor must be re-verified against the actual contribution of Stories 2.9, 3.10–3.12, and 4.5–4.6 when Epic 2's harness lands. If it does not hold, lower the threshold with a recorded rationale — never pad the dataset to reach it.

## Story Map

| Epic | Stories |
|---|---|
| 1 - Inspectable Single-Site Scenario Workspace | 1.1 Fixture history [TE] - 1.2 Sign in - 1.3 Fixture catalogue - 1.4 Scenario read contract [TE] - 1.5 Exact evidence targets [TE] - 1.6 Design tokens/primitives [TE] - 1.7 Scenario Data workspace - 1.8 Table controls - 1.9 Parity and mutation denial - 1.10 Accessibility/responsiveness - 1.11 Gate A readiness [TE] |
| 2 - Grounded Conversational Investigation | 2.1 AgentRuntime boundary [TE] - 2.2 Evaluation harness [TE] - 2.3 Durable conversations - 2.4 Live event replay - 2.5 Governed inspect capability - 2.6 Governed capability module [TE] - 2.7 Evidence grounding - 2.8 Evidence jump/return - 2.9 Clarify/refuse/fail safely |
| 3 - Governed and Recoverable Schedule Repair | 3.1 Reversible draft - 3.2 Deterministic candidate [TE] - 3.3 Job leasing/fencing [TE] - 3.4 Cancellation command [TE] - 3.5 Literal run state/replay [TE] - 3.6 Explicit bounded optimization - 3.7 Monitor/cancel/reopen runs - 3.8 Candidate/baseline comparison - 3.9 Model-outage continuity - 3.10 Repair correctness - 3.11 Recovery and idempotency - 3.12 Repair browser journey |
| 4 - Exact Baseline Decision and Decision Record | 4.1 Request approval - 4.2 Review and decide - 4.3 Atomic promotion with audit - 4.4 Decision provenance - 4.5 Approval and audit invariants - 4.6 State semantics and automated accessibility |
| 5 - Demonstrable Local Planner Workspace | 5.1 Run instrumentation - 5.2 Content/secret leak prevention - 5.3 One-command reproducible run [TE] - 5.4 Portfolio walkthrough |
| 6 - Reliable Hosted Planner Workspace | 6.1 AWS edge/identity/network [TE] - 6.2 AWS data/runtime [TE] - 6.3 Immutable deploys [TE] - 6.4 Hosted invariants/parity/mutation denial - 6.5 Backups and rollback |

47 stories across 6 epics. Blocking dependencies are backward-only: 1 -> 2 -> 3 -> 4 -> 5 -> 6. Epic 5 is the portfolio milestone (Gate B) and is complete without Epic 6; Epic 6 adds the hosted proof (Gate C).

No story depends on a later story to complete its own acceptance boundary. Where a service contract necessarily precedes the surface that consumes it, the story is labelled `[TE]`, carries a platform persona, and states its non-planner-visible outcome explicitly: Stories 1.4/1.5 precede the Story 1.7 workspace and Story 2.8 evidence navigation; Stories 3.2–3.5 precede the Story 3.6 run control and the Story 3.7 Runs workspace. Story 2.5 is complete for FR5 and the scheduling inspect capability alone, and Story 2.6 wholly owns FR23. Story 3.1 delivers a complete draft without a Run optimization placeholder; Story 3.6 introduces the run control and command together; Story 3.7 makes the Story 3.4 cancellation command reachable. Story 3.5 independently owns optimization progress/recovery behavior; Story 4.1 independently owns approval-required behavior.
