---
id: SPEC-ShiftMind
companions:
  - acceptance-contract.md
  - ../../planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md
  - ../../planning-artifacts/ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md
  - ../../planning-artifacts/ux-designs/ux-ShiftMind-2026-07-22/DESIGN.md
sources:
  - ../../planning-artifacts/prds/prd-ShiftMind-2026-07-21/prd.md
  - ../../planning-artifacts/prds/prd-ShiftMind-2026-07-21/addendum.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability only — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# ShiftMind Governed Scheduling Agent MVP

## Why

Distribution-centre planners need to repair coverage disruptions without trusting opaque automation or navigating raw solver controls. ShiftMind must prove that conversational assistance can investigate and propose inside a consequential scheduling workflow while deterministic optimization, human authority, versioned evidence, and reproducible audit remain in control. The MVP serves one planner at one site and establishes boundaries that a future SaaS can extend without claiming novelty, product-market fit, labor savings, or enterprise reliability.

## Capabilities

- **CAP-1**
  - **intent:** An authenticated seeded planner can enter one site-scoped workspace and select an immutable predefined fixture.
  - **success:** Unauthenticated or cross-site access and any second user or active membership are rejected, while the selected fixture, scenario version, and baseline version remain explicit.

- **CAP-2**
  - **intent:** The planner can inspect the normalized scenario facts and stable identifiers available to agent investigation.
  - **success:** The read-only viewer and agent inspection projection match for every Gate A fixture and expose no supported mutation path.

- **CAP-3**
  - **intent:** The planner can create, revisit, and use durable conversations to investigate schedule problems with grounded agent assistance.
  - **success:** Reconnect reconstructs ordered state, ambiguous or unauthorized requests clarify or refuse, and every numerical or schedule claim resolves to saved version-bound evidence.

- **CAP-4**
  - **intent:** The planner can turn operational intent into a validated, reversible schedule-change draft.
  - **success:** Resolved entities, constraints or objectives, preserved locks, expected versions, and consequences are reviewable or rejectable without changing the baseline; invalid inputs fail before computation.

- **CAP-5**
  - **intent:** The planner can obtain deterministic schedule candidates and feasibility decisions from versioned proposal inputs.
  - **success:** CP-SAT alone constructs or validates accepted assignments, every completed feasible candidate satisfies hard constraints and locks, and infeasible work creates no promotable candidate.

- **CAP-6**
  - **intent:** The planner can explicitly start, monitor, cancel, leave, and resume bounded optimization work.
  - **success:** Accepted work has one durable run ID, survives browser or worker interruption, exposes distinct terminal states, enforces positive application-owned budgets, and retries create no duplicate effect.

- **CAP-7**
  - **intent:** The planner can compare a candidate with its exact baseline before deciding.
  - **success:** The comparison shows worker, shift, task, interval coverage, overtime, cost or objective, constraint, version, and unresolved-gap deltas without substituting missing evidence.

- **CAP-8**
  - **intent:** The planner can explicitly approve an exact feasible candidate as the ShiftMind operational baseline.
  - **success:** Stale, expired, replayed, altered, or mismatched approval fails closed; a valid decision atomically consumes approval, changes the baseline pointer once, writes audit evidence, and preserves prior versions.

- **CAP-9**
  - **intent:** The planner and reviewer can reconstruct the complete governed decision path.
  - **success:** Provenance links request, evidence, concise decision summary, tool and policy outcomes, solver run, approval, execution, and before/after versions without hidden chain-of-thought; consequential outcomes are unsampled and append-only.

- **CAP-10**
  - **intent:** Product engineers can add governed agent capabilities without widening core orchestration authority.
  - **success:** A versioned module can be registered and removed without editing the agent loop, remains unavailable by default, and cannot execute without typed contracts, scope, risk, budgets, audit mapping, policy, and evaluations.

- **CAP-11**
  - **intent:** The planner can keep using inspectable saved work and the manual deterministic solver path when the model or optional telemetry is unavailable.
  - **success:** Model or Logfire failure causes no state or audit corruption and disables only the dependent assistance or export surface.

- **CAP-12**
  - **intent:** The team can release and operate the portfolio MVP reproducibly with executable evidence.
  - **success:** Deterministic, browser, security, recovery, accessibility, backup/restore, and rollback gates pass against version-bound reports before the AWS portfolio release.

## Constraints

- The model interprets and orchestrates only; application controls own identity, site scope, authorization, policy, versions, budgets, approval, idempotency, persistence, and audit, while CP-SAT owns accepted schedule construction and feasibility.
- The MVP permits one pre-provisioned planner and one active site membership, disables public registration, and derives authority from the authenticated server session rather than client or model values.
- Scenario source data is limited to immutable predefined fixtures; no upload, create, import, edit, or delete path is allowed.
- Analysis, draft, explicit run, comparison, exact approval, and baseline promotion remain distinct states and controls; stale state is never silently rebased.
- Accepted work, events, versions, evidence, and effects are durable and idempotent; browser streams, process memory, model SDKs, and telemetry are not recovery boundaries.
- Numerical or schedule-specific claims and comparisons are recomputable from immutable version-bound evidence; unsupported numbers fail the grounding gate.
- Authoritative product state and business audit remain unsampled under ShiftMind control and separate from sanitized operational logs and optional external traces.
- Sensitive workforce, prompt, schedule, approval, and credential content is excluded from external telemetry by default; secrets never enter prompts, browser payloads, audit summaries, logs, traces, or evaluation fixtures.
- `ARCHITECTURE-SPINE.md` governs the architecture, stack, contract shapes, state machines, persistence roles, brownfield cutover, AWS boundaries, and migration rules.
- `EXPERIENCE.md` governs routes, interaction states, evidence navigation, responsive behavior, keyboard behavior, and the accessibility floor; `DESIGN.md` governs visual identity and component deltas.
- Gate A completes the tenant and fixture spine plus read-only viewer and parity tests before AgentRuntime or tool orchestration; Gate B adds production-shaped durability and AWS proof without weakening invariants.
- Deterministic-first release gates block on any authorization, approval, isolation, hard-constraint, grounding, idempotency, audit-continuity, viewer-parity, recovery, accessibility, backup/restore, or rollback regression.
- Customer-grade latency, availability, concurrency, recovery, retention, residency, compliance, and cost claims remain unset until measured traffic or a target customer makes them concrete.

## Non-goals

- SaaS registration, invitations, administration, billing, multiple active users, separation of duties, or dedicated infrastructure per site.
- Payroll, time and attendance, worker self-service, shift marketplaces, proprietary forecasting, WMS execution, or network-wide optimization.
- Autonomous baseline promotion, unrestricted model action, arbitrary SQL, shell, credentials, network access, runtime capability installation, generalized RAG, or multi-agent orchestration.
- Custom scenario, roster, demand, or site-configuration mutation and production fidelity for every labor, union, contract, fairness, or customer-specific rule.
- Claims of validated differentiation, product-market fit, ROI, labor savings, complete rule fidelity, or enterprise service levels before the stated discovery and measurement gates.

## Success signal

- In every release run, one authenticated planner can inspect the seeded fixture, investigate and repair the Wednesday outbound disruption through the governed flow, close its coverage gap without breaking locks, hard constraints, or baseline overtime, approve the exact feasible candidate once, and recover the complete evidence-linked decision record after interruption. The infeasible fixture remains non-promotable, all deterministic and agent gates pass, and the same build deploys to AWS with demonstrated backup/restore and rollback.

## Assumptions

- Maya is a fictional representative planner, not validated customer-research evidence.
- Desktop web is primary; tablet stacks panels and phone supports read-only triage rather than full planning actions.
- The seeded planner may self-approve only through the distinct exact-action approval flow.
- The seeded Wednesday outbound fixture has the known feasible outcome in the success signal; an infeasible variant remains a separate case.
- The initial golden dataset has at least 50 versioned cases, at least four per allowed capability, at least ten consequential or prohibited cases, at least 90% overall routing accuracy, and 100% consequential/prohibited routing accuracy.
- The low-cost AWS portfolio may use one API task, one worker task, small RDS capacity, and disclosed portfolio networking while still enabling backups and a restore drill.
- The existing manual deterministic solver workflow remains available when AgentRuntime is unavailable.
