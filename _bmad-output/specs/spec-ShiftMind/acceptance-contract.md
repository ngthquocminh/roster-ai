# ShiftMind Acceptance Contract

This companion preserves the line-item product, quality, and release contract absorbed from the PRD and technical addendum. Implementation mechanics, interaction behavior, and visual rules remain in the adopted architecture and UX companions listed by `SPEC.md`.

## Authority and action classes

| Class | Allowed outcome | Authorization boundary |
| --- | --- | --- |
| Inspect | Read scenario, schedule, demand, workforce, evidence, runs, metrics, and provenance | Automatic after server-derived authorization |
| Draft | Create or revise reversible constraints, objectives, and candidate parameters | Planner reviews or rejects; no baseline change |
| Compute | Start bounded deterministic optimization | Current explicit planner run request; not consequential approval |
| Consequential | Promote or replace the ShiftMind operational baseline | Exact authenticated action- and version-bound approval |
| Prohibited | Identity administration, arbitrary SQL/shell/network/credential access, policy or optimizer bypass | Never exposed |

No model output, model memory, untrusted content, browser-held site value, or client approval flag can authorize an action. Prompts, messages, fixture fields, tool output, and future uploads are untrusted data.

## Functional acceptance matrix

| Source | Capability | Required acceptance evidence |
| --- | --- | --- |
| FR-1 | CAP-1 | One pre-provisioned planner can sign in and out; unauthenticated page/API access fails; public self-registration creates no account. |
| FR-2 | CAP-1 | Provisioning and persistence reject a second authenticatable user or active membership without changing the seeded planner. |
| FR-3 | CAP-1 | Conversations, scenarios, schedules, runs, approvals, tools, audit, and evidence are scoped from server-derived actor/site context; URL, payload, model-argument, or browser-site tampering cannot cross scope. |
| FR-4 | CAP-3 | Persisted messages, turns, statuses, tool summaries, and outcomes reconstruct the same ordered conversation after reload or reconnect. |
| FR-5 | CAP-3 | Allow-listed reads can inspect the selected scenario, current schedule, demand, qualifications, availability, locks, constraints, runs, and metrics without direct database access or fabricated context. |
| FR-6 | CAP-3 | Materially ambiguous entities, intent, consequence, or versions trigger clarification; unsupported, unauthorized, out-of-scope, injection-driven, or over-budget requests refuse without widening tools or authority. |
| FR-7 | CAP-3 | Every displayed numerical or schedule-specific claim cites saved facts or computations bound to the selected scenario and schedule/run version; each KPI is recomputable and unsupported numbers fail. |
| FR-8 | CAP-11 | Model outage is labelled narrowly; authenticated Scenario Data, saved results, provenance, and the manual deterministic solver workflow remain usable. |
| FR-9 | CAP-4 | A proposal contains resolved entities, constraints/objectives, preserved locks, expected versions, and a human-readable consequence summary; invalid entities, ranges, tasks, or combinations fail before solver execution. |
| FR-10 | CAP-4 | Draft parameters can be reviewed, revised, rejected, or abandoned without changing the operational baseline or its version. |
| FR-11 | CAP-5 | CP-SAT alone produces or validates accepted assignments from versioned proposal inputs; no completed candidate violates a hard constraint. |
| FR-12 | CAP-6 | Only the current explicit planner request or Run optimization transition starts a durable asynchronous job; the response exposes a run ID and positive application-owned ceilings for solver time, iterations, model/tool calls, retries, tokens, concurrency, and elapsed time. Limit exhaustion ends in a distinct bounded state. |
| FR-13 | CAP-6 | Queued, running, approval-required, completed, infeasible, timed-out, cancelled, and failed states persist; event delivery resumes after reconnect and worker restart without losing accepted work or duplicating effects. |
| FR-14 | CAP-6 | Every run immutably references scenario inputs, active constraints, locks, solver configuration, relevant component versions, and result so feasibility and displayed KPIs can be reproduced. |
| FR-15 | CAP-7 | Candidate/baseline comparison names affected worker, shift, role/task, interval coverage, overtime, cost/objective components, constraint status, unresolved infeasibility, and exact versions. |
| FR-16 | CAP-6 | Queued/running work accepts cooperative cancellation; command replay, lease recovery, and retry return the same semantic effect and never duplicate work or promotion. |
| FR-17 | CAP-8 | Optimization may propose approval only for a feasible candidate; completion alone never changes the operational baseline. |
| FR-18 | CAP-8 | Approval binds actor, site, action, normalized parameters, candidate and version, current baseline and version, consequence-summary hash, policy version, expiry, and one-time decision state; expired, reused, altered, stale, or mismatched attempts fail closed. |
| FR-19 | CAP-8 | Approval consumption, baseline-pointer change, authoritative audit, and event commit atomically once; prior schedule versions remain inspectable and eligible only for a new approval-gated promotion. |
| FR-20 | CAP-9 | Provenance links request, evidence consulted, concise decision summary, tool proposals/results, guardrail/policy outcomes, solver run, approval, execution, and before/after versions without storing private chain-of-thought. |
| FR-21 | CAP-9 | Successful, denied, stale, failed, and cancelled consequential actions create unsampled, append-only, site-scoped authoritative evidence independent of observability. |
| FR-22 | CAP-1 | The planner selects only application-provided immutable fixture versions; no chat, UI, or API path introduces or mutates custom scenario source data. |
| FR-23 | CAP-10 | A capability module declares versioned schemas, permissions, site/resource scope, risk and approval policy, budgets/timeouts, version/idempotency rules, safe audit/evidence mappings, errors, and evaluation fixtures. Registration does not grant authority; incomplete or ungranted modules remain unavailable. |
| FR-24 | CAP-2 | Scenario Data shows version metadata, work areas/tasks, workers/qualifications/availability, demand, baseline assignments, locks, and constraints/objectives from the same normalized projection used by agent inspection; automated browser/API tests prove field/identifier parity and absence of mutation controls/endpoints. |

## Gate cutline

| Gate | Required proof |
| --- | --- |
| Gate A — Inspectable agent thesis | FR-1–FR-11, FR-15, and FR-17–FR-24 deliver one secure inspect–investigate–draft–optimize–compare–approve journey in a deterministic local environment. PostgreSQL/site membership, immutable fixtures, normalized scenario reads, authenticated Scenario Data, parity tests, and negative mutation-path tests precede AgentRuntime and tool orchestration. |
| Gate B — Production-shaped proof | FR-12–FR-14, FR-16, quality/evaluation requirements, AWS deployment, observability independence, backup/restore, and rollback complete the portfolio MVP. |
| Beyond | All non-goals and future SaaS capabilities remain outside both gates. Schedule pressure may reduce polish but cannot weaken an authority, evidence, approval, isolation, audit, or recovery invariant. |

## Quality gates

### Security and privacy

- Tenant-isolation tests permit zero cross-site reads or writes.
- Every mutating tool call carries current authorization, expected resource version, idempotency protection, and audit evidence.
- External telemetry is allow-list-only and excludes workforce, prompt, schedule, approval, credential, and raw tool content by default.
- Secret scanning covers prompts, browser payloads, audit summaries, logs, traces, and evaluation fixtures.
- Prompt-injection tests cover chat and every untrusted input channel introduced by the MVP.

### Reliability and correctness

- Worker termination and recovery create zero duplicate effects; accepted work stays discoverable after browser, API, or worker interruption.
- Every baseline promotion has valid parameter- and version-bound approval; promotion, schedule versioning, and successful audit share one consistency boundary.
- Model-provider or Logfire failure causes zero corruption or authoritative-audit loss and preserves supported deterministic/manual workflows.
- Every completed feasible schedule satisfies deterministic hard constraints; locks remain satisfied or the result is explicitly infeasible.
- Infeasible, timed-out, cancelled, failed, and successful outcomes remain distinct everywhere.

### Accessibility and usability

- The full desktop journey and read-only responsive views meet WCAG 2.2 AA.
- Keyboard operation, focus restoration, semantic status text, durable progress announcements, evidence targeting, and exact-action approval follow `EXPERIENCE.md`.
- Review, Run optimization, and Approve as baseline remain distinct in copy, interaction, and visual treatment.

### Deployability and operations

- Reviewed infrastructure code and immutable application images reproduce every environment.
- Stable run IDs correlate product records, audit, logs, and available traces without becoming high-cardinality metric labels.
- A tested procedure rolls back an unhealthy AWS image/schema-compatible release; backup and restore evidence is retained.
- AWS cost, queue health, budgets, tool/guardrail denials, approval age/outcomes, solver behavior, evaluation regression, audit failure, model failure, and telemetry-export health are observable and alertable.
- Public customer SLOs, recovery objectives, concurrency, retention, residency, and cost targets require measured AWS traffic and customer/legal input.

## Evaluation and release evidence

Normal CI uses deterministic model doubles. A live-provider demonstration is explicit and budgeted, never the sole release proof. Every report binds dataset, evaluator, model, prompt, tool, policy, application, scenario, solver, code, and image versions.

Required suites cover tool selection and arguments; authorization and isolation; forbidden/excessive agency; approval required/mismatch/expiry/replay/staleness; grounding; injection; viewer read-only/parity; malformed model output/provider timeout/budgets; solver feasibility/infeasibility/timeout/locks; worker recovery/replay/cancellation/idempotency; telemetry-independent operation/audit; keyboard-complete browser flow; backup/restore; and rollback.

| Measure | Release rule |
| --- | --- |
| Seeded disruption repair | Close the Wednesday outbound gap, preserve locks, create zero hard violations, and keep overtime at or below baseline in every CI run. |
| Scenario Data integrity | 100% viewer/agent parity for normalized values and identifiers across every Gate A fixture, with no supported mutation path. |
| Infeasibility honesty | The deterministic infeasible fixture never produces a promotable candidate. |
| Numerical grounding | 100% of numerical claims verify against saved evidence. |
| Tool routing | At least 90% overall and 100% on consequential/prohibited cases in the initial golden set. |
| Stale and repeated actions | 100% of stale conflicts reject and retries/recovery create zero duplicate effects. |
| Primary journey | The automated browser suite passes every run; ten portfolio rehearsals report duration and failures without claiming an external-user benchmark. |
| Runtime and cost | Tokens, model/tool/solver duration, queue/approval age, and estimated cost are recorded; no customer target is asserted before measurement. |

Any regression in authorization, approval, tenant isolation, deterministic hard constraints, grounding, idempotency, authoritative audit, viewer parity, recovery, accessibility, backup/restore, or rollback blocks release regardless of aggregate helpfulness.

## Deferred decisions and triggers

| Decision | Current boundary | Revisit trigger |
| --- | --- | --- |
| Baseline meaning | Internal ShiftMind baseline only; no WMS export or execution | Any WMS/export integration |
| Self-approval | Seeded planner may self-approve through the distinct exact-action flow | A second user or security review |
| Product differentiation | Portfolio hypothesis only | At least five planner/manager interviews; revisit if fewer than three identify disruption repair as top-three pain, understand the draft/run/approve boundary, or prefer ShiftMind after reviewing the proof |
| Custom scenario and DC management | No source-data writes | Dedicated DC-management milestone with separate governed modules |
| Roles and separation of duties | Only the seeded planner is active | Multi-user milestone |
| Integrations | None beyond managed identity | Product discovery selects a WMS, HR, demand, or identity system |
| Customer SLOs and compliance | No enterprise, residency, retention, regulatory, or model-provider claim | Measured AWS traffic or a selected customer/region |
| Queue/workflow infrastructure | PostgreSQL leasing and owned state machines | Measured backlog/polling harm, independent consumers, or genuinely branching multi-day cross-system work |

## Domain terms

| Term | Contract meaning |
| --- | --- |
| Scenario | Versioned scheduling inputs, workforce, demand, locks, constraints, and objectives. |
| Scenario Data | Read-only view of the selected fixture's normalized agent-relevant facts and versions. |
| Draft | Reversible constraints/objectives that do not change the operational baseline. |
| Run | Durable bounded CP-SAT execution with versioned inputs, state, result, and evidence. |
| Schedule version | Immutable candidate or baseline assignment set derived from a scenario/run. |
| Operational baseline | Schedule version currently promoted for internal ShiftMind operational use. |
| Baseline promotion | Approval-gated pointer change to one feasible candidate, not WMS export or execution. |
| Material ambiguity | Missing or conflicting identity, scope, time, action, consequence, or version information that could change the capability or result. |
| Evidence-linked | Bound to saved facts or reproducible computation for exact scenario/schedule/run versions. |
| Budget | Positive application-owned ceiling for model/tool calls, tokens, retries, solver time, concurrency, or elapsed time. |
| Authoritative audit | Unsampled append-only business evidence independent of logs and traces. |
| Approval | Authenticated one-time decision over an exact action, consequence summary, and current versions. |
| Provenance | Evidence chain from request and policy through solver, approval, and resulting state. |
