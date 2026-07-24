---
stepsCompleted:
  - 1
  - 2
  - 3
  - 4
  - 5
  - 6
assessmentStatus: NEEDS_WORK
assessor: Codex using BMad Implementation Readiness
completedDate: 2026-07-23
includedFiles:
  prd:
    - prds/prd-ShiftMind-2026-07-21/prd.md
    - prds/prd-ShiftMind-2026-07-21/addendum.md
    - requirements-inventory.md
  architecture:
    - architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md
  epics:
    - epics.md
  ux:
    - ux-designs/ux-ShiftMind-2026-07-22/DESIGN.md
    - ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md
---

# Implementation Readiness Assessment Report

**Date:** 2026-07-23
**Project:** ShiftMind

## Document Discovery

### PRD Files Found

**Whole documents selected:**

- `prds/prd-ShiftMind-2026-07-21/prd.md` (41,660 bytes; modified 2026-07-23 12:50:10 +07:00)
- `prds/prd-ShiftMind-2026-07-21/addendum.md` (17,469 bytes; modified 2026-07-23 12:50:11 +07:00)

**Supporting documents not selected as competing PRD sources:**

- `prds/prd-ShiftMind-2026-07-21/reconcile-scenario-data-viewer.md`
- `prds/prd-ShiftMind-2026-07-21/review-rubric.md`
- `prds/prd-ShiftMind-2026-07-21/reviews/brief-reconciliation.md`
- `prds/prd-ShiftMind-2026-07-21/reviews/product-market-review.md`
- `prds/prd-ShiftMind-2026-07-21/reviews/research-reconciliation.md`
- `prds/prd-ShiftMind-2026-07-21/reviews/review-resolution.md`

No `index.md` sharded entry point and no competing whole PRD were found.

### Architecture Files Found

**Whole document selected:**

- `architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` (42,019 bytes; modified 2026-07-23 12:50:13 +07:00)

The folder also contains architecture review and reconciliation evidence under `reviews/`. These files were not selected as competing architecture sources. No `index.md` sharded entry point and no competing whole architecture were found.

### Epics & Stories Files Found

**Whole document selected:**

- `epics.md` (114,297 bytes; modified 2026-07-23 17:56:31 +07:00)

No sharded epics folder and no competing whole epics document were found.

### UX Design Files Found

**Complementary documents selected:**

- `ux-designs/ux-ShiftMind-2026-07-22/DESIGN.md` (12,150 bytes; modified 2026-07-23 12:50:14 +07:00)
- `ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md` (32,172 bytes; modified 2026-07-23 12:50:15 +07:00)

The UX folder also contains a memory log and working/import directories. No competing whole UX document or `index.md` sharded entry point was found.

### Discovery Issues

- Duplicate whole-versus-sharded formats: none.
- Missing required document types: none.
- Structural note: the versioned PRD, architecture, and UX collections do not use `index.md`, but their primary documents are unambiguous.

Selection was confirmed by the user's autonomous `-A` invocation.

## PRD Analysis

### Functional Requirements

FR1: The system shall authenticate one pre-provisioned planner, support sign-in/sign-out, disable public registration, and reject access without a valid application session.

FR2: The system shall permit only one authenticatable application user and one active site membership in the portfolio environment.

FR3: Every conversation, scenario, schedule, run, approval, tool call, audit record, and evidence reference shall be authorized from server-derived actor and site context.

FR4: The planner shall create and revisit conversations whose messages, turns, status, tool summaries, and outcomes persist across browser reconnects.

FR5: The agent shall inspect the selected scenario, current schedule, demand intervals, workforce qualifications and availability, locks, constraints, runs, and stored metrics through allow-listed read capabilities.

FR6: The agent shall request clarification when an entity, intent, or consequence is materially ambiguous and shall refuse unsupported, unauthorized, out-of-scope, or over-budget requests.

FR7: Numerical and schedule-specific claims shall reference facts or computed values tied to the selected scenario and schedule/run version.

FR8: When the conversational model is unavailable, the product shall preserve access to saved scenarios/results and the existing manual deterministic solver workflow while identifying agent features as unavailable.

FR9: The agent shall translate planner intent into a validated proposal containing resolved entities, proposed constraints or objectives, preserved locks, expected version, and a human-readable consequence summary.

FR10: Draft constraints and optimization goals shall be reviewable, editable, and rejectable without changing the current operational schedule.

FR11: New assignments and feasibility claims shall be produced or validated only by the CP-SAT scheduling engine using the versioned proposal inputs.

FR12: The agent shall start optimization as a durable job only as direct fulfillment of the planner's current explicit request or **Run optimization** transition, with explicit limits for solver time, agent iterations, model/tool calls, retries, tokens, concurrency, and total elapsed time.

FR13: The product shall show persisted queued, running, approval-required, completed, infeasible, timed-out, cancelled, and failed states and resume event delivery after reconnect.

FR14: Each run shall retain an immutable reference to its scenario inputs, active constraints, locks, solver configuration, relevant component versions, and result.

FR15: The system shall compare a candidate with its baseline by affected worker, shift, role/task, interval coverage, overtime, cost/objective components, constraint status, and unresolved infeasibility.

FR16: The product shall accept planner cancellation requests for queued or running work, and repeated commands shall return the same semantic result rather than duplicate work or baseline promotion.

FR17: The agent may propose approving a feasible candidate as the site's internal operational baseline but shall not promote it as an implicit part of optimization.

FR18: Baseline promotion or replacement shall require an explicit authenticated decision bound to the candidate, current baseline, material parameters, consequence summary, and their versions.

FR19: A valid approval shall promote one schedule version and preserve prior versions for inspection and approval-gated re-promotion.

FR20: The planner shall inspect a timeline linking the request, evidence consulted, concise decision summary, tool proposals and results, guardrail/policy outcomes, solver run, approval, execution result, and before/after versions.

FR21: Successful, denied, stale, failed, and cancelled consequential actions shall produce unsampled, append-only, site-scoped business audit evidence.

FR22: The planner shall select the active scenario from an application-provided fixture catalogue; the MVP shall not accept scenario uploads or creation/modification of source workforce, demand, or DC configuration data.

FR23: New agent capabilities shall be addable as versioned modules that declare typed contracts, permissions, site/resource scope, risk and approval policy, budgets, audit summaries, and evaluation cases without changing the core agent loop.

FR24: For the selected predefined fixture version, the authenticated planner shall be able to open a read-only Scenario Data viewer that exposes the agent-relevant normalized data: stable identifiers and version metadata; work areas and tasks; workers, qualifications, and availability; demand intervals; operational-baseline assignments; locks; and active scheduling constraints and objectives. Values and identifiers shown in the viewer shall match those available to the agent's allow-listed scenario inspection capability for that fixture version. The viewer shall provide no upload, create, edit, delete, or import action.

**Total FRs: 24**

### Non-Functional Requirements

NFR1: Tenant-isolation tests permit zero cross-site reads or writes.

NFR2: Every mutating tool call uses current authorization, expected resource version, idempotency protection, deterministic invariants, and authoritative audit evidence.

NFR3: Workforce, prompt, schedule, approval, and credential content is excluded from external telemetry by default; only allow-listed sanitized metadata leaves the boundary.

NFR4: Secrets never appear in prompts, browser payloads, audit summaries, logs, traces, or evaluation fixtures.

NFR5: Prompt-injection tests cover chat and every untrusted data channel introduced by the MVP.

NFR6: Worker termination, lease expiry, replay, and recovery create zero duplicate effects.

NFR7: Accepted work remains discoverable after browser, API, stream, or worker interruption.

NFR8: 100% of operational-baseline promotions require valid parameter- and version-bound approval.

NFR9: Baseline promotion, schedule versioning, successful authoritative audit, and the resulting persisted event share one consistency boundary.

NFR10: Model-provider or Logfire failure causes zero product-state corruption and zero authoritative-audit loss; manual and deterministic workflows remain available.

NFR11: 100% of completed feasible schedules satisfy deterministic hard constraints.

NFR12: 100% of numerical agent claims pass the grounding evaluator before release.

NFR13: Infeasible, timed-out, cancelled, failed, and successful outcomes are never represented as equivalent.

NFR14: Planner locks remain satisfied or the run returns a clear infeasibility diagnosis.

NFR15: The product records API acknowledgement latency, first-persisted-event latency, end-to-end agent duration, model/tool latency, solver duration, queue age, approval age, token use, and cost per completed task.

NFR16: Agent and solver budgets are explicit positive application configuration with safe defaults, never chosen by the model.

NFR17: Public-launch service objectives are set from measured portfolio traffic before accepting a customer; no unsupported enterprise service-level claim is made.

NFR18: The primary desktop journey and read-only responsive views meet WCAG 2.2 AA, remain keyboard-operable, use meaningful status text, and announce durable progress/approval state.

NFR19: Review, Run optimization, and Approve as baseline remain distinct in language, control, consequence, and visual treatment.

NFR20: 200% zoom, text-spacing changes, and reduced-motion preferences must not hide controls, create page-level horizontal scrolling, or remove status meaning.

NFR21: Every environment is reproducible from reviewed infrastructure code and immutable application images.

NFR22: Every agent run is searchable by one stable run identifier across product records, audit, operational logs, and traces, without high-cardinality IDs as metric labels.

NFR23: An unhealthy AWS release is recoverable to the prior schema-compatible image through a tested rollback procedure.

NFR24: Automated RDS backups, a demonstrated restore drill, and documented recovery limitations are required for the portfolio environment.

NFR25: AWS cost, queue health, lease expiry, budget cutoffs, tool/guardrail denials, approval age/outcomes, solver duration/failure, evaluation regressions, audit-write failure, model failure, and telemetry-export health are observable and alertable.

NFR26: Normal CI is deterministic-first; live-provider tests are explicit, gated, budgeted, and never the sole release evidence.

NFR27: Every evaluation report binds dataset, evaluator, model, prompt, tool, policy, application, scenario, solver, code, and image versions.

NFR28: The initial golden dataset contains at least 50 versioned cases, at least four per allowed capability, and at least ten consequential/prohibited cases; it achieves at least 90% overall tool routing and 100% consequential/prohibited routing.

NFR29: Any regression in authorization, approval, isolation, hard constraints, grounding, idempotency, authoritative audit, viewer parity, recovery, accessibility, backup/restore, or rollback blocks release regardless of aggregate helpfulness.

NFR30: Product data and authoritative audit remain in ShiftMind-controlled persistence; external providers receive only the minimum explicitly configured content.

NFR31: Successful mutations write audit evidence in the business transaction where possible; denied and failed consequential attempts are recorded reliably and separately.

NFR32: Audit captures actor/site, request/run/tool/approval/job identifiers, action and policy outcome, safe summaries or hashes, before/after versions, software/model/prompt/tool/policy versions, and immutable evidence references.

NFR33: Audit access is site-scoped; the normal application path cannot update or delete audit events.

NFR34: The portfolio documents current retention settings and limitations without implying a customer deletion, residency, compliance, or regulatory-WORM policy.

NFR35: Internal demonstration thresholds, final as of 2026-07-23 and governed by the canonical measurement protocol, are: initial Scenario Data group-window load ≤ 2 seconds; exact evidence-target resolution ≤ 2 seconds; first persisted run event after acknowledgement ≤ 5 seconds; and SSE reconnect replay to current state ≤ 5 seconds. These are internal acceptance thresholds, never customer service-level objectives.

**Total NFRs: 35**

### Additional Requirements

- **Authority boundary:** The language model may interpret and orchestrate but may not authorize action, create accepted assignments, bypass application policy, or promote a schedule implicitly. CP-SAT owns construction and feasibility; application controls own identity, scope, policy, versions, budgets, idempotency, approval, persistence, and audit.
- **Autonomy tiers:** Inspect is automatic; Draft is reversible and planner-reviewable; Compute requires the planner's current explicit request; Consequential baseline promotion requires exact-action approval; identity administration and arbitrary SQL, shell, network, credential, or policy-bypass capabilities are prohibited.
- **Fail-closed invariants:** Browser/model-supplied tenant or approval values are untrusted, tool output cannot redefine policy, stale proposals are rejected rather than silently rebased, and observability failure cannot disable supported workflows or authoritative audit.
- **MVP boundary:** One seeded planner, one active membership, one site, predefined immutable fixtures, no source-data mutation, no WMS export/execution, no broad workforce-management or SaaS administration, and no multi-agent or general-purpose tool surface.
- **Delivery gates:** Gate A proves the inspect–investigate–draft–optimize–compare–approve thesis in a deterministic local environment; the Scenario Data viewer and normalized read contract must precede agent runtime/tool orchestration. Gate B adds durable work, production-shaped operations, AWS deployment, backup/restore, observability independence, and rollback.
- **Architecture-shaping constraints:** Use a production-shaped modular monolith with separately runnable API and worker processes; keep a ShiftMind-owned runtime abstraction around the model framework; use typed allow-listed capability modules, durable product state, persisted event replay, versioned evidence, and transactional/idempotent state transitions. Technology substitutions are allowed only when observable PRD requirements and invariants remain intact.
- **Data governance:** Workforce and scheduling data are sensitive operational data. Authoritative product/audit state remains in ShiftMind-controlled PostgreSQL/S3 persistence; external telemetry is minimized and non-authoritative; the normal application path cannot update or delete audit events.
- **Evaluation gates:** Deterministic suites cover authorization, prohibited agency, approval mismatch/expiry/replay/staleness, grounding, prompt injection, viewer parity/read-only enforcement, solver outcomes, crash recovery, cancellation/idempotency, telemetry independence, accessibility, and browser demonstration.
- **NFR35 protocol:** Tests use the largest Gate A fixture, a documented CI-reference environment, warm process and connection pool after one discarded warm-up, three consecutive all-pass runs, defined server/client clock boundaries, and version-bound dated evidence.
- **External dependencies:** Model provider, CP-SAT, authentication, durable persistence, evidence storage, AWS hosting, and optional hosted observability must expose failure clearly; failure of a non-authoritative dependency must preserve supported deterministic/manual workflows.
- **Product-discovery gate:** No validated differentiation or external production pilot claim until at least five DC planners/managers are interviewed with the journey/evidence prototype. The thesis is revisited under the PRD's stated fewer-than-three/understanding/preference criteria.
- **Normative companion sets:** UX-DR1–UX-DR35 and AR1–AR28 are additional binding requirements defined in `epics.md` and sourced from the selected UX and architecture documents; later readiness steps must validate them without renumbering.
- **Assumptions and deferred decisions:** Self-approval by the seeded planner, the exact demo fixture, the ≥50-case golden set, desktop-first use, and pooled future SaaS tenancy remain explicit assumptions. Customer SLOs, retention/deletion/residency/compliance, production roles, integrations, and custom scenario administration require decisions before an external pilot.

### PRD Completeness Assessment

The PRD is comprehensive, test-oriented, and internally explicit about scope, authority, failure behavior, release evidence, assumptions, and post-MVP boundaries. Its 24 FRs are individually numbered and include observable test consequences. Its unnumbered NFR section is normalized by the incorporated canonical register into NFR1–NFR35, with a binding protocol for the four performance thresholds.

The main readiness risk is contract distribution: normative text spans `prd.md`, `addendum.md`, `requirements-inventory.md`, and companion UX/architecture requirement sets in `epics.md`. The canonical inventory resolves numbering and precedence, but implementation must preserve those pointers and prevent drift. External-pilot readiness remains intentionally blocked by unresolved customer SLO, retention/compliance, role-separation, integration, and product-discovery decisions; these are not blockers for the declared single-user portfolio MVP.

## Epic Coverage Validation

### Epic FR Coverage Extracted

- Epic 1 — Inspectable Single-Site Scenario Workspace: FR1, FR2, FR3, FR22, FR24.
- Epic 2 — Grounded Conversational Investigation: FR4, FR5, FR6, FR7, FR23.
- Epic 3 — Governed and Recoverable Schedule Repair: FR8, FR9, FR10, FR11, FR12, FR14, FR15, FR16, and FR13's optimization progress/recovery behavior.
- Epic 4 — Exact Baseline Decision and Decision Record: FR17, FR18, FR19, FR20, FR21, and FR13's approval-required behavior.
- Epic 5 — Reliable Hosted Planner Workspace: no new FRs; hardens and re-proves relevant FR1–FR24 outcomes in the hosted environment.

**Total unique FRs claimed in epics: 24**

### Coverage Matrix

| FR | PRD requirement | Epic/story coverage | Status |
|---|---|---|---|
| FR1 | Authenticate one seeded planner; support sign-in/out; disable public registration; deny unauthenticated access. | Epic 1, Story 1.2 | ✓ Covered |
| FR2 | Enforce one authenticatable user and one active membership. | Epic 1, Story 1.2 | ✓ Covered |
| FR3 | Authorize all resources and actions from server-derived actor/site context. | Epic 1, Story 1.2; reinforced in Story 2.5 | ✓ Covered |
| FR4 | Persist and reconstruct durable conversations across reconnects. | Epic 2, Stories 2.3–2.4 | ✓ Covered |
| FR5 | Inspect authorized normalized scheduling facts through allow-listed reads. | Epic 2, Story 2.5 | ✓ Covered |
| FR6 | Clarify material ambiguity and refuse unsupported, unauthorized, out-of-scope, injection-driven, or over-budget requests. | Epic 2, Story 2.9; bounded-run failures in Story 3.6 | ✓ Covered |
| FR7 | Ground numerical and schedule claims in version-bound recomputable evidence. | Epic 2, Stories 2.7–2.8 | ✓ Covered |
| FR8 | Preserve saved work and manual deterministic optimization during model outage. | Epic 3, Story 3.9; supporting states in Stories 1.7 and 3.7 | ✓ Covered |
| FR9 | Translate intent into a typed, validated, version-bound proposal. | Epic 3, Story 3.1 | ✓ Covered |
| FR10 | Keep drafts reviewable, revisable, rejectable, and non-operational. | Epic 3, Story 3.1 | ✓ Covered |
| FR11 | Make CP-SAT the sole authority for accepted assignments and feasibility. | Epic 3, Story 3.2 | ✓ Covered |
| FR12 | Start explicit bounded asynchronous optimization with a durable run ID and application-owned ceilings. | Epic 3, Stories 3.3, 3.5, and 3.6 | ✓ Covered |
| FR13 | Persist literal run/approval states and resume event delivery without loss or duplication. | Epic 3, Story 3.5 (optimization states/recovery); Epic 4, Story 4.1 (approval-required state/replay) | ✓ Covered |
| FR14 | Preserve immutable versioned run inputs, configuration, component versions, and results. | Epic 3, Story 3.2 | ✓ Covered |
| FR15 | Compare exact candidate and baseline versions across people, work, coverage, cost, constraints, and gaps. | Epic 3, Story 3.8 | ✓ Covered |
| FR16 | Support safe cancellation and replay/retry/lease recovery without duplicate effects. | Epic 3, Stories 3.3–3.7 and 3.11 | ✓ Covered |
| FR17 | Separate feasible-candidate approval proposal from optimization completion and baseline change. | Epic 4, Story 4.1 | ✓ Covered |
| FR18 | Require explicit exact-action, version-bound, authenticated approval and reject stale/replayed/mismatched attempts. | Epic 4, Stories 4.1–4.3 and 4.5 | ✓ Covered |
| FR19 | Promote exactly one candidate atomically while preserving prior versions. | Epic 4, Story 4.3 | ✓ Covered |
| FR20 | Expose complete decision provenance without hidden chain-of-thought. | Epic 4, Story 4.4 | ✓ Covered |
| FR21 | Create unsampled append-only authoritative audit for all consequential outcomes. | Epic 4, Stories 4.3–4.5 | ✓ Covered |
| FR22 | Restrict the MVP to immutable predefined fixtures with no source-data mutation path. | Epic 1, Stories 1.1, 1.3, and 1.9; hosted re-proof in Story 5.12 | ✓ Covered |
| FR23 | Support governed versioned capability modules without core-loop branching or implicit authority. | Epic 2, Stories 2.5–2.6 | ✓ Covered |
| FR24 | Provide a read-only Scenario Data viewer using the same normalized projection as agent inspection. | Epic 1, Stories 1.4, 1.7, and 1.9; hosted re-proof in Story 5.12 | ✓ Covered |

### Missing Requirements

None. Every PRD FR from FR1 through FR24 has an explicit epic ownership path. No FR appears in the epics document without a corresponding PRD FR.

### Coverage Statistics

- Total PRD FRs: 24
- FRs covered in epics: 24
- FRs missing from epics: 0
- Extra epic FRs not present in PRD: 0
- Coverage: 100%

The split ownership of FR13 is explicitly documented and non-overlapping: Story 3.5 owns optimization progress and recovery, while Story 4.1 independently owns the approval-required transition, presentation, and replay.

## UX Alignment Assessment

### UX Document Status

**Found and final:**

- `ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md` — information architecture, behavior, states, interactions, accessibility, responsiveness, evidence navigation, and six key journeys.
- `ux-designs/ux-ShiftMind-2026-07-22/DESIGN.md` — visual identity, tokens, hierarchy, layout, component treatments, and visual prohibitions.

The two UX spines are complementary and state that they govern future mock/wireframe conflicts. Their UX-DR1–UX-DR35 requirements are incorporated into the canonical requirement model through the PRD addendum, requirements inventory, and epics document.

### UX ↔ PRD Alignment

- **Primary journey:** UX Flow 1 matches the PRD's Wednesday disruption-repair journey from fixture selection and direct inspection through grounded chat, reversible draft, explicit optimization, exact comparison, separate approval, baseline promotion, and provenance.
- **Authority separation:** Send, Draft, Run optimization, Approval, and baseline promotion remain distinct in wording, control, visual treatment, and consequence, matching FR9–FR19 and NFR19.
- **Evidence and trust:** Adjacent exact Evidence links, deterministic target resolution, Return to claim, distinct missing/unauthorized/version-mismatch behavior, and no confidence score align with FR5, FR7, FR14, FR15, and FR20.
- **Read-only fixture boundary:** The seven fixed Scenario Data groups expose the agent-relevant normalized projection without upload/create/edit/delete/import or mutation-looking affordances, matching FR22 and FR24.
- **Durability and failures:** Literal queued/running/approval-required/completed/infeasible/timed-out/cancelled/failed states, reconnect replay, duplicate suppression, stale approval handling, and model-outage fallback align with FR4, FR8, FR12, FR13, FR16, FR18, and FR19.
- **Accessibility and responsive scope:** WCAG 2.2 AA, keyboard operation, live status announcements, 200% zoom, text spacing, reduced motion, 44×44 CSS-pixel targets, and phone read-only triage are explicitly adopted by NFR18/NFR20 and the PRD addendum.
- **Coverage exception:** The UX source map does not list FR23. This is appropriate because governed capability-module extensibility is an internal platform contract with no required planner-facing surface. Epic 2 and the architecture retain its implementation and conformance coverage.

### UX ↔ Architecture Alignment

| UX need | Architectural support | Assessment |
|---|---|---|
| Shared viewer/agent facts and immutable versions | AD-4 `ScenarioProjectionV1`, immutable fixture versions, parity and mutation-denial gates | Aligned |
| Exact evidence links, out-of-window targets, no retargeting | AD-4 bounded exact-target lookup; AD-11 version-bound evidence; AD-14 route/history restoration | Aligned |
| Durable conversation/run state and reconnect replay | AD-6 persisted recovery boundary; AD-7 separate closed state machines; AD-21 SSE cursor/heartbeat contract | Aligned |
| Distinct Send, Compute, and Approval authority | AD-2 authority partition; AD-5 risk classes; AD-10 exact-action approval; AD-14 explicit commands | Aligned |
| Literal failure/stale/terminal states | AD-7 closed graphs and consistency conventions for distinct errors | Aligned |
| Read-only Scenario Data tables at fixture scale | AD-4 deterministic bounded cursor windows/counts; AD-13 versioned API; AD-14 client-state ownership | Aligned |
| Model-outage continuity | AD-15 isolates AgentRuntime and preserves Scenario Data, saved results, and manual solver path | Aligned |
| Results/provenance independent of traces/model | AD-12 separate records of truth and authoritative product/audit evidence | Aligned |
| Real routes, Back/Forward, generated client contracts | AD-13 REST/OpenAPI chain; AD-14 peer scenario surfaces and URL/history state | Aligned |
| NFR35 response/replay thresholds | AD-26 allocates ≤2 s scenario-window and evidence lookup plus ≤5 s first-event and reconnect-replay thresholds to concrete components | Aligned |
| Accessibility and responsive release proof | AD-16 makes accessibility regressions release-blocking; epic proof stories provide the executable browser evidence | Aligned |
| Existing React/shadcn/Tailwind/Radix visual system | Architecture stack and frontend structural seed support the declared UX system without a competing UI framework | Aligned |

### Alignment Issues

No blocking contradiction or unsupported UX requirement was found.

One terminology boundary requires implementation discipline: UX presents an aggregate run-progress experience that may include `approval-required`, while AD-7 requires `AgentRun`, `ScheduleRun`, and `ApprovalRequest` to remain separate persisted state machines. The architecture explicitly permits a combined timeline projection, and the epics assign optimization-state behavior to Story 3.5 and approval-required behavior to Story 4.1. The UI must preserve that distinction in contracts and persistence.

### Warnings

- The `#4F46E5` primary/white treatment is conditionally allowed by `DESIGN.md`; shipped control/text contrast must be verified before use. Inline evidence links use the separately specified accessible evidence-link tone.
- WCAG 2.2 AA claims are scoped to the declared portfolio matrix (latest Chrome/Edge on Windows, keyboard, NVDA, zoom/text spacing/reduced motion) until that matrix is deliberately expanded.
- Phone mode is a UX limitation, not authorization. Write/run/cancel/approve controls may direct the user to desktop, but the server must continue enforcing permissions independently of viewport.
- NFR35 timings do not appear as visual design tokens, but they are fully allocated by the canonical inventory, AD-26, and Stories 1.4, 1.5, 2.4, and 3.5; implementation evidence must preserve that linkage.

## Epic Quality Review

### Review Scope and Evidence

All five epics and all 54 stories were reviewed against user-value, independence, dependency direction, sizing, acceptance-criteria, brownfield, database-timing, and traceability standards. A mechanical structure check confirmed that every story contains matched Given/When/Then blocks.

### Epic Structure Validation

| Epic | User outcome | Standalone incremental value | Dependency direction | Result |
|---|---|---|---|---|
| 1 — Inspectable Single-Site Scenario Workspace | Planner signs in, selects an immutable fixture, and inspects exact normalized data. | Useful without agent or solver orchestration. | None; establishes Gate A substrate. | Pass |
| 2 — Grounded Conversational Investigation | Planner conducts durable, evidence-linked investigation with clarification/refusal. | Useful using Epic 1 only; no repair or approval required. | Depends backward on Epic 1. | Pass at epic level |
| 3 — Governed and Recoverable Schedule Repair | Planner drafts, explicitly computes, recovers, and compares a candidate without baseline change. | Useful using Epics 1–2; approval is not required. | Depends backward on Epics 1–2. | Pass at epic level; internal ordering issue |
| 4 — Exact Baseline Decision and Decision Record | Planner approves an exact feasible candidate and inspects the complete decision record. | Uses the candidate produced by Epic 3 and does not require hosting work. | Depends backward on Epics 1–3. | Pass |
| 5 — Reliable Hosted Planner Workspace | Planner/operator receives a reproducibly hosted, diagnosable, recoverable workspace. | Hardens the complete workflow without becoming a dependency of earlier epics. | Depends backward on Epics 1–4. | Pass |

No epic is a technical milestone disguised as an epic. Epic 5 contains substantial infrastructure work, but its declared outcome is hosted planner availability, privacy-safe diagnosis, recovery, and rollback; those are observable user/operator outcomes. Technical stories are generally labelled `[Technical Enabler]` and kept inside outcome-oriented epics.

### Dependency Analysis

The cross-epic dependency chain is backward-only: Epic 1 → Epic 2 → Epic 3 → Epic 4 → Epic 5. No circular or later-epic dependency was found.

Valid enabling relationships include Story 1.1 → 1.3, Story 1.6 → 1.7, Story 2.1 → 2.2/2.3, and Story 2.2 → later proof suites. Gate and hosted proof stories consume only already-delivered behavior.

### 🔴 Critical Violations

None.

### 🟠 Major Issues

#### MQ-1 — Story 2.5 defers part of its acceptance contract to future Story 2.6

Story 2.5's capability-manifest acceptance criterion cites “FR23 partial” and says the general manifest contract “is completed and proven in Story 2.6.” This is the only explicit forward story reference found outside an `Unblocks` declaration. A story must not depend on a future story to complete an acceptance claim.

**Impact:** Story 2.5 cannot be read as independently complete for every requirement cited by its own acceptance criteria. This weakens sprint acceptance and makes FR23 ownership conditional on future work.

**Recommendation:** Make Story 2.5 complete only for FR5 and the scheduling inspect capability, removing the partial FR23 completion claim from its AC. Keep full FR23 conformance wholly in Story 2.6. Alternatively, move the complete manifest contract into Story 2.5 and make Story 2.6 solely an independent add/remove conformance proof.

#### MQ-2 — Epic 3's planner-visible sequence contains forward usability dependencies

Stories 3.2–3.5 describe candidate production, leased work, planner cancellation, and persisted progress before Story 3.6 introduces the complete planner-visible **Run optimization** control and command. Story 3.4 promises planner cancellation, but the Runs workspace and Cancel control are not delivered until Story 3.7.

**Impact:** Stories 3.4 and 3.5 can be exercised through seeded/API tests, but they do not independently deliver the planner value claimed by their “As a planner” statements at their current positions. Story 3.2 similarly behaves as an unlabelled backend enabler until a run can be started.

**Recommendation:** Move Story 3.6 immediately after the minimum compute foundation in Story 3.3, before cancellation and progress UX; then place progress/replay and cancel/monitor stories after a planner can create a run. Prefer delivering the cancellation command and its visible control in one vertical story (merge Story 3.4 into 3.7 or split 3.7 so the first slice is complete). If service-only sequencing must remain, label Stories 3.2–3.5 clearly as technical enablers and change their persona/outcome statements accordingly.

### 🟡 Minor Concerns

#### MN-1 — Several service-contract stories are unlabelled technical enablers

Stories 1.4 and 1.5 deliver normalized-read and exact-target backend contracts before the Scenario Data UI in Story 1.7 and evidence navigation in Story 2.8. Their contracts are valid and independently testable, but the immediate planner outcome is indirect.

**Recommendation:** Mark them `[Technical Enabler]` or reshape them as vertical slices with a minimal planner-visible query/target outcome. Apply the same test to Story 2.5 and Story 3.2 if MQ-1/MQ-2 are remediated without reordering.

#### MN-2 — A few stories carry high implementation breadth

The principal sizing risks are Story 1.2 (OIDC/BFF session, sign-out, one-user/membership persistence, CSRF/origin enforcement, RLS isolation), Story 2.1 (framework spike, owned port, dependency boundaries, brownfield seams, hidden-reasoning discard), Story 3.2 (snapshot, solver adapter, candidate creation, all terminal outcomes), and Story 5.7 (CI/CD, immutable multi-process deployment, edge SSE proof, correlation, environment limitations).

**Recommendation:** Before sprint commitment, break each into implementation tasks with one demonstrable acceptance boundary and one owner per cross-stack concern. Split a story only if each resulting slice remains independently testable and does not create a forward dependency.

#### MN-3 — Two gate/proof stories lack the explicit evidence-artifact precision used elsewhere

Story 1.11 and Story 5.10 are testable, but they do not name a persisted evidence artifact and owner as precisely as Stories 4.6–4.9 and 5.11–5.13.

**Recommendation:** Add an evidence path, required version bindings, and accountable owner to each gate so “Confirm Gate A Readiness” and “Prove Rollback” have objective completion records.

### Acceptance Criteria Assessment

- 54 of 54 stories contain matched Given/When/Then blocks.
- Criteria are predominantly specific and independently verifiable, with explicit error, stale, denial, replay, accessibility, and recovery cases.
- Quantitative acceptance exists for NFR35 and release dataset/routing thresholds.
- Status vocabulary, versions, authority boundaries, and evidence outputs are consistently named.
- The issues above concern dependency direction and vertical story completion, not vague prose.

### Database and Entity Timing

No “create all tables up front” violation was found. Story 1.1 explicitly creates only fixture/history structures required at that point; Story 1.2 adds only identity/session/membership structures; later aggregates are owned by the stories/modules that first use them. AD-22 fixes aggregate ownership and atomic bundles, supporting just-in-time persistence changes.

### Starter and Brownfield Checks

The architecture does not mandate a starter template, so no starter-cloning Story 1 requirement applies. This is a brownfield project: AD-25 and Story 1.1 provide a one-way maintenance-window cutover, compatibility adapters preserve existing seams during incremental migration, legacy SQLite history remains explicitly offline, and the V1 OpenAPI/client switch is coordinated.

### Best-Practices Compliance Summary

| Check | Result |
|---|---|
| Epics deliver user/operator value | Pass |
| Epic dependency direction and independence | Pass |
| FR traceability | Pass — 24/24 |
| BDD acceptance structure | Pass — 54/54 |
| Error/recovery specificity | Pass |
| Just-in-time database/entity creation | Pass |
| Brownfield integration/migration strategy | Pass |
| No within-epic forward dependency | **Fail — MQ-1 and MQ-2** |
| Story verticality and independent planner value | **Needs remediation — MQ-2 and MN-1** |
| Story sizing | Caution — MN-2 |

## Summary and Recommendations

### Overall Readiness Status

**NEEDS WORK**

The planning set is complete and unusually well aligned: all required artifacts exist; 24/24 FRs are mapped; 35 NFRs are canonicalized; UX and architecture support the same user journey, authority boundaries, evidence model, failure states, accessibility scope, and performance thresholds; and every one of the 54 stories has testable BDD acceptance criteria.

Implementation readiness is withheld because two story-structure defects violate the workflow's no-forward-dependency and independent-value standards. These are localized backlog defects, not product-definition or architecture failures.

### Critical Issues Requiring Immediate Action

No critical-severity issue was found.

Before Phase 4 implementation begins, resolve these two major issues:

1. **MQ-1:** Remove Story 2.5's partial FR23 acceptance dependency on future Story 2.6. Give each story a complete, non-forward acceptance boundary.
2. **MQ-2:** Reorder or reshape Epic 3 so the planner-accessible run trigger exists before cancellation and progress stories claim planner value, and ship cancellation behavior with a reachable control.

### Recommended Next Steps

1. Edit Stories 2.5 and 2.6 so FR5 inspection and FR23 general module conformance have separate, complete ownership.
2. Reorder Epic 3 to place the complete Run optimization trigger immediately after its minimum compute foundation, then deliver progress/replay and cancellation/monitoring as reachable vertical slices.
3. Mark Stories 1.4 and 1.5—and any retained service-only Epic 3 slices—as `[Technical Enabler]`, or add a planner-visible completion boundary.
4. Create implementation task breakdowns for the high-breadth Stories 1.2, 2.1, 3.2, and 5.7 before sprint commitment.
5. Add version-bound evidence artifact paths and accountable owners to Stories 1.11 and 5.10.
6. Re-run implementation readiness after the epics document is updated. The PRD, UX, architecture, FR coverage, and canonical NFR register do not otherwise require rework.

### Final Note

This assessment identified **5 actionable planning issues across 3 categories**: dependency/verticality (2 major), sizing/technical-enabler clarity (2 minor), and gate-evidence precision (1 minor). It also recorded four non-blocking UX implementation cautions.

The project should not enter unrestricted Phase 4 implementation with the current story order. The remediation is narrow and can be completed entirely in `epics.md`; after that edit and a clean readiness rerun, the artifact set is positioned to receive a **READY** verdict.

**Assessment date:** 2026-07-23  
**Assessor:** Codex using the BMad Implementation Readiness workflow
