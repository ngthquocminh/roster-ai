---
stepsCompleted:
  - step-01-document-discovery
  - step-02-prd-analysis
  - step-03-epic-coverage-validation
  - step-04-ux-alignment
  - step-05-epic-quality-review
  - step-06-final-assessment
assessmentDate: 2026-07-22
assessor: OpenAI Codex using BMAD Implementation Readiness workflow
overallReadiness: NOT READY
includedFiles:
  prd:
    - prds/prd-ShiftMind-2026-07-21/prd.md
    - prds/prd-ShiftMind-2026-07-21/addendum.md
  architecture:
    - architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md
  epics:
    - epics.md
  ux:
    - ux-designs/ux-ShiftMind-2026-07-22/DESIGN.md
    - ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md
---

# Implementation Readiness Assessment Report

**Date:** 2026-07-22
**Project:** ShiftMind

## Document Inventory

### PRD

- `prds/prd-ShiftMind-2026-07-21/prd.md`
- `prds/prd-ShiftMind-2026-07-21/addendum.md`

### Architecture

- `architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md`

### Epics and Stories

- `epics.md`

### UX Design

- `ux-designs/ux-ShiftMind-2026-07-22/DESIGN.md`
- `ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md`

### Discovery Notes

- No whole-versus-sharded duplicate formats were found.
- Nested PRD, architecture, and UX collections do not use `index.md`; the identified primary documents are included directly.
- Review, reconciliation, rubric, and `.memlog.md` files are excluded from the primary assessment.

## PRD Analysis

### Functional Requirements

**FR-1 — Seeded planner authentication.** The system shall authenticate one pre-provisioned planner, support sign-in/sign-out, disable public registration, and reject access without a valid application session. Verification: unauthenticated API and page access is denied; attempts to self-register cannot create an account.

**FR-2 — One-user MVP enforcement.** The system shall permit only one authenticatable application user and one active site membership in the portfolio environment. Verification: an attempt to provision a second authenticatable user or activate a second membership fails without changing the seeded planner.

**FR-3 — Site-scoped authorization.** Every conversation, scenario, schedule, run, approval, tool call, audit record, and evidence reference shall be authorized from server-derived actor and site context. Verification: changing a URL, payload, model argument, or browser-held site value cannot access another site's resource.

**FR-4 — Durable conversations.** The planner shall create and revisit conversations whose messages, turns, status, tool summaries, and outcomes persist across browser reconnects. Verification: reloading or reconnecting reconstructs the same ordered conversation and pending state.

**FR-5 — Grounded schedule investigation.** The agent shall inspect the selected scenario, current schedule, demand intervals, workforce qualifications and availability, locks, constraints, runs, and stored metrics through allow-listed read capabilities. Verification: the primary journey can be answered without direct database access or fabricated context.

**FR-6 — Clarification and refusal.** The agent shall request clarification when an entity, intent, or consequence is materially ambiguous and shall refuse unsupported, unauthorized, out-of-scope, or over-budget requests. Verification: ambiguous worker names do not resolve arbitrarily, and prompt instructions cannot add tools or authority.

**FR-7 — Evidence-linked explanations.** Numerical and schedule-specific claims shall reference facts or computed values tied to the selected scenario and schedule/run version. Verification: every displayed KPI can be recomputed from saved evidence, and an unsupported number fails the grounding gate.

**FR-8 — Model-outage fallback.** When the conversational model is unavailable, the product shall preserve access to saved scenarios/results and the existing manual deterministic solver workflow while identifying agent features as unavailable. Verification: disabling the model provider cannot block an authenticated planner from viewing existing work or starting a manual solver run.

**FR-9 — Typed proposal creation.** The agent shall translate planner intent into a validated proposal containing resolved entities, proposed constraints or objectives, preserved locks, expected version, and a human-readable consequence summary. Verification: invalid workers, tasks, ranges, or combinations are rejected before solver execution.

**FR-10 — Reversible draft boundary.** Draft constraints and optimization goals shall be reviewable, editable, and rejectable without changing the current operational schedule. Verification: abandoning a draft leaves the operational baseline and its version unchanged.

**FR-11 — Deterministic schedule generation.** New assignments and feasibility claims shall be produced or validated only by the CP-SAT scheduling engine using the versioned proposal inputs. Verification: the model cannot directly create an accepted assignment, and no completed candidate contains a hard-constraint violation.

**FR-12 — Bounded asynchronous run.** The agent shall start optimization as a durable job only as direct fulfillment of the planner's current explicit request or **Run optimization** transition, with explicit limits for solver time, agent iterations, model/tool calls, retries, tokens, concurrency, and total elapsed time. Verification: the request returns a durable run identifier; every listed limit has a positive application-owned ceiling in the release configuration; exceeding any ceiling ends in a distinct bounded state.

**FR-13 — Progress and recovery.** The product shall show persisted queued, running, approval-required, completed, infeasible, timed-out, cancelled, and failed states and resume event delivery after reconnect. Verification: browser disconnect and worker restart do not lose an accepted run or duplicate its effects.

**FR-14 — Immutable run evidence.** Each run shall retain an immutable reference to its scenario inputs, active constraints, locks, solver configuration, relevant component versions, and result. Verification: rerunning the saved inputs can reproduce feasibility and recompute displayed KPIs.

**FR-15 — Before/after comparison.** The system shall compare a candidate with its baseline by affected worker, shift, role/task, interval coverage, overtime, cost/objective components, constraint status, and unresolved infeasibility. Verification: the demo clearly shows what moved, why, and the measurable benefit or regression.

**FR-16 — Retry and cancellation safety.** The product shall accept planner cancellation requests for queued or running work, and repeated commands shall return the same semantic result rather than duplicate work or baseline promotion. Verification: retries and worker lease recovery produce zero duplicate effects.

**FR-17 — Baseline-promotion proposal.** The agent may propose approving a feasible candidate as the site's internal operational baseline but shall not promote it as an implicit part of optimization. Verification: a completed candidate remains separate from the operational baseline until an approval decision is recorded.

**FR-18 — Exact-action approval.** Baseline promotion or replacement shall require an explicit authenticated decision bound to the candidate, current baseline, material parameters, consequence summary, and their versions. Verification: expired, reused, mismatched, altered, or stale approval attempts are rejected and require a refreshed proposal.

**FR-19 — Atomic baseline promotion and recovery.** A valid approval shall promote one schedule version and preserve prior versions for inspection and approval-gated re-promotion. Verification: baseline promotion and its authoritative audit record either both succeed or neither succeeds; a retry cannot create a second effect.

**FR-20 — Complete decision provenance.** The planner shall inspect a timeline linking the request, evidence consulted, concise decision summary, tool proposals and results, guardrail/policy outcomes, solver run, approval, execution result, and before/after versions. Verification: a reviewer can reconstruct who requested and approved a change, what evidence and versions governed it, and what changed without access to hidden chain-of-thought.

**FR-21 — Complete authoritative audit.** Successful, denied, stale, failed, and cancelled consequential actions shall produce unsampled, append-only, site-scoped business audit evidence. Verification: disabling observability does not remove or prevent the authoritative record.

**FR-22 — Predefined scenario selection.** The planner shall select the active scenario from an application-provided fixture catalogue; the MVP shall not accept scenario uploads or creation/modification of source workforce, demand, or DC configuration data. Verification: every agent run references an immutable predefined fixture version, and no chat, page, or API path can introduce custom scenario source data.

**FR-23 — Extensible governed capability model.** New agent capabilities shall be addable as versioned modules that declare typed contracts, permissions, site/resource scope, risk and approval policy, budgets, audit summaries, and evaluation cases without changing the core agent loop. Verification: a demonstration capability can be registered and removed without editing orchestration control flow, remains unavailable by default, and cannot execute until its policy and evaluation contract are present.

**FR-24 — Read-only Scenario Data viewer.** For the selected predefined fixture version, the authenticated planner shall be able to open a read-only Scenario Data viewer that exposes the agent-relevant normalized data: stable identifiers and version metadata; work areas and tasks; workers, qualifications, and availability; demand intervals; operational-baseline assignments; locks; and active scheduling constraints and objectives. Values and identifiers shown in the viewer shall match those available to the agent's allow-listed scenario inspection capability for that fixture version. The viewer shall provide no upload, create, edit, delete, or import action. Verification: an automated browser/API test verifies the normalized viewer payload against the agent inspection payload for the same fixture version and confirms that the viewer surface exposes no data-mutation control or supported mutation endpoint.

**Total FRs: 24**

### Non-Functional Requirements

**NFR-1 — Tenant isolation.** Zero cross-site reads or writes in the tenant-isolation test suite.

**NFR-2 — Mutating-tool controls.** One hundred percent of mutating tool calls include current authorization, expected resource version, idempotency protection, and audit evidence.

**NFR-3 — Telemetry privacy.** Workforce, prompt, schedule, and credential content is excluded from external telemetry by default; only explicitly allow-listed sanitized metadata may leave the application boundary.

**NFR-4 — Secret protection.** Secrets never appear in prompts, browser payloads, audit summaries, logs, traces, or evaluation fixtures.

**NFR-5 — Injection coverage.** Prompt-injection tests cover chat messages and every untrusted data channel introduced by the MVP.

**NFR-6 — Recovery idempotency.** Worker termination and recovery produce zero duplicate effects.

**NFR-7 — Durable accepted work.** Accepted work remains discoverable after browser, API, or worker interruption.

**NFR-8 — Approval integrity.** One hundred percent of operational-baseline promotions require a valid parameter- and version-bound approval.

**NFR-9 — Promotion consistency.** Baseline promotion, schedule versioning, and its successful audit evidence share one consistency boundary.

**NFR-10 — Dependency failure safety.** Model-provider or Logfire failure produces zero corruption and zero loss of authoritative audit; supported manual and deterministic workflows remain available.

**NFR-11 — Hard-constraint correctness.** One hundred percent of completed feasible schedules satisfy deterministic hard constraints.

**NFR-12 — Numerical grounding.** One hundred percent of numerical agent claims pass the grounding evaluator before release.

**NFR-13 — Outcome clarity.** Infeasible, timed-out, cancelled, failed, and successful runs are never presented as equivalent.

**NFR-14 — Lock preservation.** Planner locks remain satisfied or the run returns a clear infeasibility diagnosis.

**NFR-15 — Performance instrumentation.** The product records API acknowledgement latency, time to first persisted event, end-to-end agent duration, model/tool latency, solver duration, queue age, approval age, token use, and cost per completed task.

**NFR-16 — Application-owned budgets.** All agent and solver budgets are explicit configuration with safe defaults; they are not chosen by the model.

**NFR-17 — Evidence-based service objectives.** Public-launch latency, availability, recovery, concurrency, retention, and cost objectives shall be set from measured portfolio traffic before accepting a customer. No unsupported enterprise service-level claim is part of the MVP.

**NFR-18 — Accessible primary journey.** The primary desktop-web journey is operable by keyboard, exposes meaningful status text rather than color alone, and announces durable progress and approval state to assistive technology.

**NFR-19 — Distinct consequential actions.** Consequences and approval controls use plain operational language and keep “review,” “run optimization,” and “approve as baseline” as distinct actions.

**NFR-20 — Reproducible environments.** Every environment is reproducible from reviewed infrastructure code and immutable application images.

**NFR-21 — Cross-system traceability.** Every agent run is searchable by a stable run identifier across product records, audit, operational logs, and available traces.

**NFR-22 — Tested rollback.** An unhealthy AWS release can be rolled back to the prior image and schema-compatible version through a tested procedure.

**NFR-23 — Operational observability.** AWS costs, queue health, agent budget cutoffs/failures, tool denials/timeouts, guardrail denials, approval age/outcomes, solver duration/failure, evaluation regressions, audit write failures, model failures, and telemetry-export health are observable and alertable.

**Total NFRs: 23**

### Additional Requirements

- Delivery is split into Gate A (the inspectable agent thesis) and Gate B (the production-shaped proof). The Scenario Data viewer, normalized scenario-read contract, and viewer read-only/parity tests must pass before agent runtime or tool orchestration implementation begins.
- The language model is restricted to interpretation and orchestration. Application code owns identity, site scope, authorization, policy, risk, approval, versioning, budgets, idempotency, persistence, and audit; CP-SAT owns schedule construction and feasibility.
- The agent capability surface is allow-listed and excludes general-purpose database, code-execution, credential, administrative, and network access. Capabilities must be composed through a versioned application-owned registry and remain unavailable by default until policy and evaluation contracts exist.
- Model output, memory, browser-supplied tenant values, untrusted content, and client-supplied approval flags cannot authorize actions. Stale proposals fail closed and are not silently rebased.
- The system stores concise decision summaries and evidence, not private chain-of-thought.
- Approval records must bind actor, site, action type, normalized parameter hash, candidate/version, baseline/version, consequence-summary hash, policy version, creation/expiry, and one-time decision state.
- Mutating HTTP commands require caller-provided idempotency keys scoped to actor, site, operation, and body hash plus an expected resource version. Internal effects use stable run/tool-call keys.
- Every user-owned table carries or derives site scope; repositories require trusted site context and PostgreSQL row-level security provides defense in depth.
- Audit records are append-only through the normal application path. S3 evidence uses checksummed, content- or immutable-version-addressed keys with create-only application semantics; no regulatory WORM claim is made unless Object Lock is configured and governed.
- Product state and authoritative audit remain independent of CloudWatch diagnosis, sanitized Logfire/OpenTelemetry traces, and version-controlled evaluation reports. External telemetry must disable prompt/tool content capture by default.
- The target is a modular monolith with separately runnable FastAPI API and worker processes, PostgreSQL/SQLAlchemy/Alembic persistence, a PostgreSQL job table, persisted SSE replay, Cognito/BFF authentication, S3 evidence, and Terraform/GitHub Actions OIDC deployment to AWS.
- Required evaluation suites cover tool routing, authorization and tenant denial, excessive agency, approval mismatch/expiry/replay/staleness, grounding, injection, Scenario Data parity/read-only enforcement, malformed/provider/budget failure, solver outcomes and constraints, recovery/cancellation/idempotency, telemetry independence, accessibility, and the repeatable browser journey.
- The initial golden evaluation dataset is assumed to contain at least 50 versioned cases, at least four cases per allowed capability, and at least ten consequential or prohibited-action cases. Release thresholds are at least 90% overall tool selection and 100% correct consequential/prohibited routing; any regression in authorization, approval, tenant isolation, hard constraints, grounding, idempotency, or authoritative audit blocks release.
- The seeded repair fixture must close the known gap, preserve locks, produce no hard violations, and keep overtime at or below baseline. The infeasible fixture must never produce a promotable candidate.
- Customer-specific retention, export, deletion, residency, legal, model-provider, availability, and recovery targets remain deferred but must be resolved before an external production pilot.
- Before claiming validated differentiation or beginning an external production pilot, at least five DC planners or managers must be interviewed using the journey and evidence prototype. The thesis is to be revisited under the PRD's stated interview decision rule.
- Non-goals include SaaS administration, multiple active users, payroll/timekeeping, WMS execution, cross-site optimization, autonomous promotion, multi-agent orchestration, generalized RAG, unrestricted tools, custom scenario editing/upload, and full customer-specific scheduling-rule fidelity.

### PRD Completeness Assessment

The PRD is unusually strong for implementation planning: all 24 functional requirements are numbered, testable, and tied to explicit authority boundaries; 23 measurable non-functional requirements cover security, reliability, scheduling correctness, privacy, accessibility, deployability, and operations; delivery gates and release-blocking evaluation rules are explicit; and the technical addendum turns the product contract into concrete architectural mechanisms without superseding it.

The principal completeness limitations are intentional deferred decisions rather than hidden gaps: production SLOs, recovery objectives, retention/residency policy, customer integration priorities, multi-user role separation, and customer-specific scheduling rules remain unresolved until measured traffic or pre-pilot discovery. The primary persona and several dataset/portfolio assumptions are not validated customer evidence. These items do not prevent portfolio MVP implementation, but they do prevent an external-production or product-market-fit claim without the stated follow-up work.

## Epic Coverage Validation

### Coverage Matrix

| FR Number | PRD Requirement | Epic and Story Coverage | Status |
|---|---|---|---|
| FR-1 | Seeded planner authentication | Epic 1; Story 1.2 | ✓ Covered |
| FR-2 | One-user MVP enforcement | Epic 1; Story 1.2 | ✓ Covered |
| FR-3 | Server-derived site-scoped authorization | Epic 1; Story 1.2, reinforced by Story 2.3 | ✓ Covered |
| FR-4 | Durable conversations | Epic 2; Story 2.2 | ✓ Covered |
| FR-5 | Allow-listed grounded schedule investigation | Epic 2; Story 2.3 | ✓ Covered |
| FR-6 | Clarification and refusal for ambiguous, unsafe, or over-budget requests | Epic 2; Story 2.6, reinforced by Story 3.5 | ✓ Covered |
| FR-7 | Version-bound evidence-linked explanations | Epic 2; Story 2.4 | ✓ Covered |
| FR-8 | Model-outage fallback for saved work and deterministic optimization | Epic 3; Stories 3.6 and 3.8, with viewer independence in Story 1.5 | ✓ Covered |
| FR-9 | Typed validated schedule-change proposals | Epic 3; Story 3.1 | ✓ Covered |
| FR-10 | Reversible draft boundary | Epic 3; Story 3.1 | ✓ Covered |
| FR-11 | CP-SAT-owned schedule construction and feasibility | Epic 3; Story 3.2 | ✓ Covered |
| FR-12 | Explicit bounded asynchronous optimization | Epic 3; Stories 3.3, 3.4, and 3.5 | ✓ Covered |
| FR-13 | Persisted progress states and recovery | Epic 3; Stories 3.4 and 3.6 | ✓ Covered |
| FR-14 | Immutable reproducible run evidence | Epic 3; Story 3.2 | ✓ Covered |
| FR-15 | Exact candidate/baseline comparison | Epic 3; Story 3.7 | ✓ Covered |
| FR-16 | Cancellation, retry, lease, and idempotency safety | Epic 3; Stories 3.3, 3.5, and 3.6 | ✓ Covered |
| FR-17 | Separate feasible-candidate approval proposal | Epic 4; Story 4.1 | ✓ Covered |
| FR-18 | Exact-action, version-bound approval | Epic 4; Stories 4.1, 4.2, 4.3, and 4.5 | ✓ Covered |
| FR-19 | Atomic baseline promotion and prior-version preservation | Epic 4; Stories 4.3 and 4.5 | ✓ Covered |
| FR-20 | Complete decision provenance | Epic 4; Story 4.4 | ✓ Covered |
| FR-21 | Unsampled append-only authoritative audit | Epic 4; Stories 4.3, 4.4, and 4.5 | ✓ Covered |
| FR-22 | Immutable predefined fixture catalogue | Epic 1; Stories 1.3 and 1.6 | ✓ Covered |
| FR-23 | Versioned governed capability-module extensibility | Epic 5; Story 5.1, with contract precursor in Story 2.3 | ✓ Covered |
| FR-24 | Read-only Scenario Data viewer and viewer/agent parity | Epic 1; Stories 1.4, 1.5, and 1.6 | ✓ Covered |

### Missing Requirements

No PRD functional requirements are missing from the epics and stories document. No epic FR identifiers exist outside the PRD's FR-1 through FR-24 range.

### Coverage Statistics

- Total PRD FRs: 24
- FRs claimed in the epic coverage map: 24
- FRs with concrete story-level coverage: 24
- Missing FRs: 0
- Extra FRs not present in the PRD: 0
- Coverage: 100%

## UX Alignment Assessment

### UX Document Status

**Found.** Two final UX documents are included:

- `ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md` — information architecture, routes, behavior, states, interactions, accessibility, responsiveness, evidence navigation, and six key flows.
- `ux-designs/ux-ShiftMind-2026-07-22/DESIGN.md` — visual hierarchy, tokens, component treatments, evidence affordances, layout, and authority-level differentiation.

The UX is implementation-oriented rather than conceptual: it defines canonical routes, component contracts, state behavior, exception paths, responsive modes, keyboard/focus rules, evidence navigation, and source-requirement coverage.

### UX ↔ PRD Alignment

The UX matches the PRD's primary disruption-repair journey end to end: select an immutable fixture, inspect Scenario Data, investigate through grounded chat, create a reversible draft, explicitly start deterministic optimization, recover durable state, compare candidate and baseline, approve the exact current candidate, and inspect provenance. It preserves every major product boundary: evidence before confidence, no scenario mutation, no model authority over schedules, no implicit computation or promotion, exact version binding, literal terminal states, and model-outage fallback.

The strongest points of alignment are:

- FR-4 through FR-20, FR-22, and FR-24 have explicit UX behaviors, components, states, or flows.
- Scenario Data fields and grouping match the PRD's agent-relevant normalized data.
- Evidence links are claim-adjacent, version-bound, exact-targeted, and non-retargeting.
- Send, Run optimization, and Approve as baseline remain semantically and visually distinct.
- Infeasible, timed-out, cancelled, failed, stale, rejected, expired, and completed states remain distinct.
- Saved data, deterministic results, manual optimization, and existing evidence remain usable during a model outage.

Minor PRD/UX documentation gaps:

1. The UX source-coverage table omits FR-21 even though the Provenance timeline and audit-independent Results behavior partially express its user-facing consequences. FR-21 should be added to that map for explicit traceability.
2. WCAG 2.2 AA, 200% zoom, text-spacing, reduced-motion, 44×44 touch targets, and phone read-only triage are more specific than the PRD's explicit accessibility and desktop-primary language. These are sensible refinements and are already represented in the epics, but the PRD should either adopt them as normative MVP requirements or label them as UX-derived acceptance constraints.

### UX ↔ Architecture Alignment

The architecture supports nearly all material UX contracts:

- AD-4 and `ScenarioProjectionV1` provide the shared read model, immutable fixture versions, deterministic ordering, bounded windows, counts, and exact-target lookup needed by Scenario Data and evidence navigation.
- AD-6, AD-7, and AD-21 provide durable activity state, persisted SSE replay, literal closed statuses, reconnect recovery, and stable event identity.
- AD-11 and `EvidenceRefV1` support exact version-bound claims, fields/ranges, missing/unauthorized/version-mismatch distinctions, and deterministic comparisons.
- AD-13 and AD-14 support real routes, generated frontend contracts, one remote-cache owner, peer workspace surfaces, application-owned activity types, browser history, and focus/return context.
- AD-15 isolates model outage and prevents untrusted content or hidden reasoning from widening authority or entering product records.
- AD-20 defines the cross-epic contracts needed by drafts, runs, comparisons, approvals, provenance, persisted events, and safe errors.
- React, React Router, TanStack Query, OpenAPI/openapi-fetch, shadcn/ui, Tailwind, and Radix are compatible with the prescribed component and interaction patterns.
- AD-16 makes accessibility regression release-blocking, and the architecture preserves server-side authorization independently of viewport behavior.

### Alignment Issues

1. **`last verified` contract gap.** UX requires a “last verified timestamp” in Scenario Data Overview and stale-state copy. The normative `ScenarioProjectionV1` minimum does not define such a field or specify whether it is server verification time, projection generation time, or client fetch time. Add a versioned server-owned field or explicitly define it as non-authoritative client metadata.
2. **No quantitative UX performance targets.** UX requires responsive exact-target loading, bounded tables, immediate durable run identity, and usable reconnect behavior; architecture provides the mechanisms and instrumentation but no portfolio acceptance thresholds for initial data load, evidence-jump resolution, time to first persisted event, or replay recovery. Public SLOs can remain deferred, but internal demonstration thresholds should be established before implementation acceptance.
3. **UX traceability map incompleteness.** The UX behavior covers more than its source-requirement table states, particularly FR-21 and the authenticated workspace implications of FR-1 through FR-3. This is a documentation gap, not a design contradiction.

### Warnings

- Phone read-only triage is an assumed responsive enhancement, not a validated user need. It should not displace the desktop Gate A journey or expand into a mobile worker workflow.
- Accessibility is declared release-blocking, but the source documents do not yet name the supported browser/assistive-technology matrix or exact automated/manual test tooling. Define this in test planning before claiming WCAG 2.2 AA conformance.
- The design spine reserves the primary indigo/white combination for large text or verified controls; shipped contrast must be tested before using it for ordinary control text.

**UX alignment verdict:** Aligned with minor non-blocking contract and traceability gaps. No UX/PRD/architecture contradiction prevents implementation planning.

## Epic Quality Review

### Epic Compliance Summary

| Epic | User-value focus | Independent from future epics | Story sizing | No forward dependency | Entity timing | Acceptance criteria | FR traceability |
|---|---|---|---|---|---|---|---|
| Epic 1 — Inspectable Single-Site Scenario Workspace | Pass | Pass | Flag | Pass | Pass | Pass | Pass |
| Epic 2 — Grounded Conversational Investigation | Pass | Pass | Flag | Pass | Pass | Pass | Pass |
| Epic 3 — Governed and Recoverable Schedule Repair | Pass | Pass at epic level | Flag | **Fail** | Pass | Pass | Pass |
| Epic 4 — Exact Baseline Decision and Decision Record | Pass | Pass | Mostly pass | Pass | Pass | Pass | Pass |
| Epic 5 — Production-Shaped Trust and Governed Growth | **Fail** | Pass | Flag | Pass | Pass/N/A | Mostly pass | Pass |

The overall epic sequence is logically progressive: Epic 1 is independently useful; Epic 2 uses only Epic 1; Epic 3 uses Epics 1–2; Epic 4 uses Epics 1–3; and Epic 5 uses the completed workflow. There are no circular epic dependencies. Database/entity timing is generally disciplined: each story introduces only the tables or aggregates first needed by that capability, and Story 1.1 explicitly forbids creating the entire future schema up front.

Acceptance criteria are a major strength. They consistently use Given/When/Then, name literal outcomes and versions, include authorization/failure/recovery paths, and are specific enough to automate. FR traceability is complete.

### 🔴 Critical Violations

#### CQ-1 — Epic 5 is a technical milestone rather than a planner-value epic

**Evidence:** Epic 5's stated beneficiary is “the product team,” and Stories 5.1 and 5.3–5.9 focus on capability-module conformance, evaluation infrastructure, telemetry, Terraform, AWS boundaries, deployment, backup/restore, and rollback. The epic's primary outcome is a production-shaped release proof rather than a standalone planner capability.

**Why this violates the standard:** The epic is organized around technical hardening and infrastructure layers. A planner cannot receive the epic's value independently in the same way they can receive inspectable data, grounded investigation, schedule repair, or exact baseline decisions.

**Remediation:** Reframe Gate B as one or more observable operational-value increments, for example:

- “Planner can reliably resume and trust the hosted ShiftMind workspace” for deployability, recovery, backup, and rollback outcomes.
- “Product operator can safely diagnose and recover the hosted planner workflow” for observability and operations.
- Keep FR-23 as a small governed-extensibility enabler tied to a concrete demonstration capability, or explicitly classify it as an architecture enabler outside the user-value epic hierarchy.

Where practical, distribute cross-cutting NFR work into the vertical epic that first needs it instead of deferring all operational proof to one technical epic.

#### CQ-2 — Story 3.4 depends on the future Epic 4 approval implementation

**Evidence:** Story 3.4 requires “an agent run, schedule run, and optional approval pause” to follow separate state machines, including approval-required behavior. `ApprovalRequest` and the approval interaction are not introduced until Epic 4 Stories 4.1–4.2.

**Why this violates the standard:** Story 3.4 cannot fully satisfy its acceptance criteria using only completed prior stories. It either implements part of Epic 4 early or remains incomplete until future work.

**Remediation:** Restrict Story 3.4 to `AgentRun` and `ScheduleRun` transitions used by non-consequential repair. Introduce `ApprovalRequest` persistence and approval-required transitions in Story 4.1. Shared enum/contract scaffolding may exist earlier, but Story 3.4 acceptance must not require the future aggregate's behavior.

### 🟠 Major Issues

#### MQ-1 — Story 3.1 exposes Run optimization before Story 3.5 implements the command

Story 3.1 requires a Draft card with a separate Run optimization control, while Story 3.5 later implements the validated command, durable enqueue, budgets, and replay semantics. A visible control without its complete command path is not an independently complete increment.

**Remediation:** Move the active Run optimization control to Story 3.5. Story 3.1 may define the draft's future action slot or render the action unavailable with explicit sequencing copy, but its acceptance should not imply a usable control before the command exists.

#### MQ-2 — Several stories are too broad for low-risk independent implementation

The following stories combine multiple independently risky concerns:

- **Story 1.4:** normalized seven-domain projection, paging/filter/sort, exact-target evidence resolution, OpenAPI generation, frontend client generation, and RFC 7807 errors.
- **Story 1.5:** the full seven-group Scenario Data workspace, routing, semantic tables, scrolling, sorting/filtering, column visibility, identifier copying, and model-outage independence.
- **Story 2.2:** persistence model, atomic accepted turn, conversation selection/creation UI, timeline reconstruction, SSE replay, and heartbeat behavior.
- **Story 3.3:** PostgreSQL queueing, privileged lease function, fencing, stale-worker recovery, effect uniqueness, and cancellation races.
- **Story 5.9:** N/N-1 schema/API/worker/client compatibility, web asset caching, durable-job compatibility, rollback/roll-forward rules, and the complete AWS proof suite.

**Remediation:** Split each at a verifiable contract boundary while preserving backward-only sequencing. Good split seams are read contract versus exact-target behavior; basic read-only workspace versus advanced table controls; durable conversation persistence versus live replay; leasing/fencing versus cancellation; and mixed-version rollout versus rollback proof.

#### MQ-3 — Visual-system consolidation occurs after four UI-heavy epics

Story 5.2 consolidates design tokens, evidence visuals, status patterns, and visual regression coverage only after Epics 1–4 have already implemented most UI components.

**Impact:** This ordering encourages rework and inconsistent treatment of evidence, authority levels, focus, and status across earlier stories.

**Remediation:** Move foundational ShiftMind tokens and shared primitives into Epic 1 before the first Scenario Data UI. Implement each component's visual contract alongside the story that introduces it. Retain only cross-workflow visual regression and final consistency auditing in the production-hardening work.

#### MQ-4 — NFR identifiers are not governed by one canonical source

The PRD contains an unnumbered 23-item NFR section, while `epics.md` defines and references 34 numbered NFRs enriched from UX, architecture, and the canonical spec. Inserting additional requirements changes the apparent number of later PRD-derived items—for example, reproducible environments is the twentieth PRD NFR by sequence but appears as NFR21 in the epics.

**Impact:** Story references such as NFR24 or NFR29 cannot be resolved against the PRD alone, weakening cross-document traceability and reviewability.

**Remediation:** Establish a single canonical numbered NFR catalogue, preserve stable IDs across every artifact, and add explicit provenance for UX-/architecture-derived requirements. Update the PRD or publish a normative requirements inventory referenced by PRD, UX, architecture, epics, and tests.

### 🟡 Minor Concerns

#### NQ-1 — Verification stories use artificial end-user framing

Stories 1.6, 3.9, and 4.5 say “As a planner, I want … tested/proved.” Their acceptance criteria are valuable and specific, but the work is a release gate rather than a directly used feature.

**Recommendation:** Either frame them as operator/team quality outcomes or attach their tests to the functional stories whose behavior they verify. Do not remove the criteria.

#### NQ-2 — Some technical enablers need explicit classification

Stories 1.1, 2.1, and 5.1 are legitimate brownfield or architecture enablers but are presented alongside user stories without an enabler designation.

**Recommendation:** Mark technical enablers explicitly, state the user-value story they unblock, and keep them smaller than the vertical capability they support.

#### NQ-3 — “Actionable signals” is not independently measurable

Story 5.4 requires operational conditions to emit “actionable signals,” but does not define required severity, destination, deduplication, runbook link, or testable notification behavior.

**Recommendation:** Define the minimum alert contract and expected test evidence for each release-blocking signal class.

### Brownfield and Starter Assessment

The architecture does not mandate a starter template, so no missing starter-template story exists. This is a brownfield project, and the backlog appropriately includes compatibility seams, a PydanticAI spike, incremental structural convergence, a one-way SQLite-to-PostgreSQL cutover, generated-client replacement, and offline preservation of legacy demo history. CI/CD and AWS delivery appear in Gate B rather than initial project setup, which is consistent with the declared local Gate A cutline but should not defer deterministic local CI evidence required by earlier stories.

### Quality Verdict

The backlog has excellent requirement coverage and acceptance-detail quality, but it is **not fully implementation-ready under strict epic/story standards** until the two critical structural violations are resolved. The oversized stories and late visual foundation should be corrected during the same backlog revision to reduce execution risk.

## Summary and Recommendations

### Overall Readiness Status

**NOT READY for Phase 4 story execution.**

The planning set is substantively mature: all required document types exist, all 24 PRD functional requirements have concrete story coverage, UX and architecture are strongly aligned, and acceptance criteria are unusually detailed and testable. The blocking condition is backlog structure, not missing product intent. Two critical defects violate the required implementation sequencing and user-value standards, and four major issues materially raise execution and traceability risk.

### Critical Issues Requiring Immediate Action

1. **Replace the technical-milestone structure of Epic 5.** Reframe production, operations, recovery, and extensibility work as observable planner/operator outcomes or distribute the relevant NFR work into the vertical epics that first depend on it.
2. **Remove Story 3.4's forward dependency on Epic 4.** Keep Story 3.4 limited to the non-consequential AgentRun/ScheduleRun states used by Epic 3; introduce ApprovalRequest persistence and approval-required transitions in Story 4.1.

Implementation should not begin from the current story sequence until these two issues are corrected and rechecked.

### Recommended Next Steps

1. Revise the epic structure and story ordering for CQ-1, CQ-2, and MQ-1; ensure every active UI control has a complete command path in the same or an earlier story.
2. Split Stories 1.4, 1.5, 2.2, 3.3, and 5.9 at the contract boundaries identified in this report, preserving backward-only dependencies.
3. Establish a single canonical numbered NFR catalogue covering PRD-, UX-, architecture-, and spec-derived requirements; update all story and test references to those stable IDs.
4. Move foundational design tokens and shared evidence/status/authority primitives into Epic 1, then implement component-specific visual contracts with their introducing stories.
5. Add the UX-required `last verified` semantics to `ScenarioProjectionV1` or explicitly define it as non-authoritative client metadata.
6. Define internal portfolio acceptance thresholds for initial scenario load, exact evidence-target resolution, first persisted run event, and SSE reconnect/replay. These need not be customer SLOs.
7. Complete UX traceability for FR-21, declare whether the added accessibility/responsive constraints are normative, and define the supported browser/assistive-technology test matrix.
8. Re-run implementation readiness after the artifact revisions; retain the current 100% FR coverage and detailed BDD acceptance criteria.

### Final Note

This assessment identified **15 findings across two review categories**: 6 UX alignment gaps/warnings and 9 epic-quality findings (2 critical, 4 major, and 3 minor). The requirements and architecture do not need wholesale redesign. A focused backlog and contract-governance revision should be sufficient to reach implementation readiness.

**Assessment date:** 2026-07-22  
**Assessor:** OpenAI Codex using the BMAD Implementation Readiness workflow
