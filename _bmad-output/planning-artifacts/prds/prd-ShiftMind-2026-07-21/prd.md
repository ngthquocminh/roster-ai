---
title: "Product Requirements Document: ShiftMind Governed Scheduling Agent MVP"
status: final
created: 2026-07-21
updated: 2026-07-23
source_brief: "../../briefs/brief-ShiftMind-2026-07-21/brief.md"
source_research: "../../research/technical-production-shaped-agent-architecture-for-shiftmind-research-2026-07-21.md"
review_gate: passed
---

# Product Requirements Document: ShiftMind Governed Scheduling Agent MVP

## 1. Vision and Product Thesis

ShiftMind is a governed scheduling assistant for distribution-centre planners. A planner describes an operational problem in natural language; the agent gathers current evidence, proposes a bounded course of action, invokes typed scheduling capabilities, runs the deterministic CP-SAT optimizer, and explains exact coverage, cost, and constraint trade-offs. The language model interprets and orchestrates. It never becomes the scheduling authority.

The portfolio MVP proves that an AI agent can act usefully inside a consequential workflow without hiding uncertainty or bypassing control. Every material recommendation links to versioned inputs, solver evidence, policy outcomes, approval, and the resulting schedule version. The product is designed for one planner at one site today while establishing the product boundaries needed for a future multi-tenant SaaS.

### 1.1 Value proposition

For a DC planner responding to a coverage problem, ShiftMind replaces navigation across forms, solver parameters, and raw data with a conversational decision surface while preserving deterministic feasibility, human authority, and reproducibility.

### 1.2 Positioning hypothesis and proof obligation

AI-assisted scheduling, conversational workforce tools, optimization, explanations, and configurable approvals are already present in products from [Legion](https://legion.co/products/schedule-optimization/), [Manhattan Associates](https://www.manh.com/solutions/manhattan-active-platform/ai-agents-for-supply-chain-productivity), [Blue Yonder](https://media.blueyonder.com/blue-yonder-transforms-supply-chain-management-with-new-ai-agents), [UKG](https://www.ukg.com/products/features/scheduling), [Quinyx](https://www.quinyx.com/solutions/workforce-management-ai), and [Infor](https://www.infor.com/solutions/human-capital-management/workforce-management/scheduling). ShiftMind therefore does not claim those concepts as novel. Its positioning hypothesis is that DC planners will value greater depth and inspectability in one disruption-repair workflow:

- the agent and optimizer have an explicit authority boundary;
- every proposal includes constraint-level and KPI evidence rather than an opaque confidence score;
- schedule decisions are reproducible from versioned inputs and solver outputs;
- stale or mismatched approvals fail closed;
- the complete decision path is inspectable without storing hidden model reasoning.

ShiftMind is a planner decision layer. It is not payroll, time and attendance, employee engagement, demand forecasting, or a WMS replacement.

## 2. Goals and Non-Goals

### 2.1 MVP goals

1. Let one authenticated planner inspect the normalized inputs of a predefined scenario, then complete a schedule-disruption workflow through chat: investigate, propose a change, optimize, compare, and approve a candidate as the ShiftMind operational baseline.
2. Demonstrate bounded multi-step agent behavior with typed tools, durable state, deterministic guardrails, and graceful failure.
3. Make every numerical explanation and consequential decision evidence-linked and auditable.
4. Prove that solver work can resume after disconnect or worker interruption without duplicate effects.
5. Deploy the product reproducibly to AWS with visible evaluation, monitoring, logging, backup/restore, and rollback evidence.
6. Preserve site and membership boundaries that can later support a real SaaS without implementing SaaS administration now.

### 2.2 Explicit non-goals

- Self-service organization or DC registration, invitations, and onboarding.
- More than one active user, complete role administration, or separation of duties.
- Billing, subscriptions, quotas administration, or customer-support tooling.
- Proprietary demand forecasting or real-time WMS task orchestration.
- Payroll, time and attendance, mobile worker self-service, or a shift marketplace.
- Network-wide or cross-site labor optimization.
- Autonomous promotion of a candidate to the operational baseline or any unrestricted agent action.
- Multi-agent orchestration, generalized RAG/vector memory, arbitrary SQL, shell access, credential access, or unrestricted network tools.
- Production fidelity for every union, labor, contract, fairness, and customer-specific scheduling rule.
- Uploading, creating, or directly editing custom scenarios, workforce rosters, demand, or DC configuration; the MVP uses predefined fixtures only.
- Dedicated AWS infrastructure for every DC; pooled logical isolation is the future default.

## 3. Users, Jobs, and Experience

### 3.1 Primary persona

**[ASSUMPTION] Maya — DC Planner (fictional representative persona).** Maya understands outbound operations, qualifications, shifts, coverage, and overtime. She can judge whether a recommendation is operationally sensible, but should not need to edit JSON, solver code, or infrastructure. The persona is a design aid, not evidence of completed customer research.

The MVP has one seeded Maya-like planner account and one DC site. Public registration is disabled, and the product prevents a second authenticatable user or active membership.

### 3.2 Jobs to be done

- When coverage looks weak, help me identify the affected interval, work area, demand, assignments, qualifications, and binding constraints.
- Before I rely on an agent answer, let me inspect the selected scenario data in an understandable read-only view and verify what the agent can use.
- When I describe an operational preference, translate it into a clear, valid, reversible draft rather than making a silent change.
- When a schedule must change, run the optimizer and show whether the result is feasible.
- Before I commit, show exactly who and what changed, plus the effects on coverage, overtime, cost, and constraints.
- When I approve a schedule, make sure I am approving the exact current proposal and let me recover the full decision record later.
- When a run is slow or interrupted, let me leave and return without losing state or creating duplicate work.

### 3.3 Primary journey: repair Wednesday outbound coverage

1. Maya signs in and selects a scenario from the predefined fixture catalogue.
2. She opens **Scenario Data** and inspects the fixture's normalized workforce, demand, baseline assignments, locks, and scheduling rules. The view identifies the exact fixture version and exposes no upload or edit action.
3. She asks, “Why is outbound coverage weak on Wednesday afternoon?”
4. The agent inspects the same normalized scenario data plus the latest solver evidence. It answers with cited values and calls out missing or ambiguous information.
5. Maya asks the agent to keep a named worker off a task, preserve locked assignments, and reduce overtime while repairing the gap.
6. The agent resolves the entities, summarizes the intended constraints and objectives, and creates a reversible proposal. Maya reviews or revises its parameters. No operational schedule changes.
7. Maya selects **Run optimization** (or gives an equivalent explicit request) after reviewing the draft. The agent starts a bounded asynchronous CP-SAT run and returns durable progress. She may disconnect and later resume.
8. The agent presents feasibility, hard-constraint status, a worker/shift/role diff, coverage and overtime deltas, objective trade-offs, and any unresolved gap.
9. Maya rejects and revises, or requests approval as the ShiftMind operational baseline. This is a separate approval over the exact candidate and current baseline version.
10. After valid approval, ShiftMind promotes the candidate to the site's internal operational baseline and records the full provenance. It does not export to or execute in a WMS. Repeating the request does not repeat the effect.

### 3.4 Recovery and exception journeys

- **Agent/model unavailable:** ShiftMind reports that conversational assistance is unavailable without implying the schedule is lost; Maya can still inspect Scenario Data and saved results and start the existing deterministic solver workflow manually.
- **Solver infeasible or timed out:** the candidate remains non-promotable; Maya receives the distinct status, binding evidence available, and choices to revise the draft, retry within policy, or abandon it.
- **Worker or browser interrupted:** accepted work remains visible by run ID and resumes/replays persisted state without a second effect.
- **Candidate becomes stale:** comparison and approval are blocked until Maya refreshes the baseline and reruns or explicitly revises the proposal.
- **Approval rejected or expired:** no baseline change occurs; the conversation records the outcome and offers refresh or revision rather than silently resubmitting.

### 3.5 Experience principles

- Evidence before confidence: show facts, constraints, and deltas instead of an AI confidence score.
- Make the agent's scenario context inspectable: present the same normalized fixture facts and stable identifiers in Scenario Data that ground agent investigation.
- Separate analysis, proposal, solver execution, approval, and baseline promotion visibly.
- Make consequence and approval state understandable without exposing internal chain-of-thought.
- Preserve planner locks and explicit decisions.
- Distinguish infeasible, timed-out, failed, cancelled, and successful outcomes.
- Keep the manual schedule and solver workflow available if the model service is unavailable.

## 4. Product Scope and Functional Requirements

### 4.1 Secure single-site workspace

**FR-1 — Seeded planner authentication.** The system shall authenticate one pre-provisioned planner, support sign-in/sign-out, disable public registration, and reject access without a valid application session.  
*Testable consequence:* unauthenticated API and page access is denied; attempts to self-register cannot create an account.

**FR-2 — One-user MVP enforcement.** The system shall permit only one authenticatable application user and one active site membership in the portfolio environment.  
*Testable consequence:* an attempt to provision a second authenticatable user or activate a second membership fails without changing the seeded planner.

**FR-3 — Site-scoped authorization.** Every conversation, scenario, schedule, run, approval, tool call, audit record, and evidence reference shall be authorized from server-derived actor and site context.  
*Testable consequence:* changing a URL, payload, model argument, or browser-held site value cannot access another site's resource.

### 4.2 Conversation and investigation

**FR-4 — Durable conversations.** The planner shall create and revisit conversations whose messages, turns, status, tool summaries, and outcomes persist across browser reconnects.  
*Testable consequence:* reloading or reconnecting reconstructs the same ordered conversation and pending state.

**FR-5 — Grounded schedule investigation.** The agent shall inspect the selected scenario, current schedule, demand intervals, workforce qualifications and availability, locks, constraints, runs, and stored metrics through allow-listed read capabilities.  
*Testable consequence:* the primary journey can be answered without direct database access or fabricated context.

**FR-6 — Clarification and refusal.** The agent shall request clarification when an entity, intent, or consequence is materially ambiguous and shall refuse unsupported, unauthorized, out-of-scope, or over-budget requests.  
*Testable consequence:* ambiguous worker names do not resolve arbitrarily, and prompt instructions cannot add tools or authority.

**FR-7 — Evidence-linked explanations.** Numerical and schedule-specific claims shall reference facts or computed values tied to the selected scenario and schedule/run version.  
*Testable consequence:* every displayed KPI can be recomputed from saved evidence, and an unsupported number fails the grounding gate.

**FR-8 — Model-outage fallback.** When the conversational model is unavailable, the product shall preserve access to saved scenarios/results and the existing manual deterministic solver workflow while identifying agent features as unavailable.  
*Testable consequence:* disabling the model provider cannot block an authenticated planner from viewing existing work or starting a manual solver run.

### 4.3 Governed schedule proposals

**FR-9 — Typed proposal creation.** The agent shall translate planner intent into a validated proposal containing resolved entities, proposed constraints or objectives, preserved locks, expected version, and a human-readable consequence summary.  
*Testable consequence:* invalid workers, tasks, ranges, or combinations are rejected before solver execution.

**FR-10 — Reversible draft boundary.** Draft constraints and optimization goals shall be reviewable, editable, and rejectable without changing the current operational schedule.  
*Testable consequence:* abandoning a draft leaves the operational baseline and its version unchanged.

**FR-11 — Deterministic schedule generation.** New assignments and feasibility claims shall be produced or validated only by the CP-SAT scheduling engine using the versioned proposal inputs.  
*Testable consequence:* the model cannot directly create an accepted assignment, and no completed candidate contains a hard-constraint violation.

### 4.4 Durable optimization and comparison

**FR-12 — Bounded asynchronous run.** The agent shall start optimization as a durable job only as direct fulfillment of the planner's current explicit request or **Run optimization** transition, with explicit limits for solver time, agent iterations, model/tool calls, retries, tokens, concurrency, and total elapsed time.  
*Testable consequence:* the request returns a durable run identifier; every listed limit has a positive application-owned ceiling in the release configuration; exceeding any ceiling ends in a distinct bounded state.

**FR-13 — Progress and recovery.** The product shall show persisted queued, running, approval-required, completed, infeasible, timed-out, cancelled, and failed states and resume event delivery after reconnect.  
*Testable consequence:* browser disconnect and worker restart do not lose an accepted run or duplicate its effects.

**FR-14 — Immutable run evidence.** Each run shall retain an immutable reference to its scenario inputs, active constraints, locks, solver configuration, relevant component versions, and result.  
*Testable consequence:* rerunning the saved inputs can reproduce feasibility and recompute displayed KPIs.

**FR-15 — Before/after comparison.** The system shall compare a candidate with its baseline by affected worker, shift, role/task, interval coverage, overtime, cost/objective components, constraint status, and unresolved infeasibility.  
*Testable consequence:* the demo clearly shows what moved, why, and the measurable benefit or regression.

**FR-16 — Retry and cancellation safety.** The product shall accept planner cancellation requests for queued or running work, and repeated commands shall return the same semantic result rather than duplicate work or baseline promotion.  
*Testable consequence:* retries and worker lease recovery produce zero duplicate effects.

### 4.5 Approval and operational-baseline promotion

**FR-17 — Baseline-promotion proposal.** The agent may propose approving a feasible candidate as the site's internal operational baseline but shall not promote it as an implicit part of optimization.  
*Testable consequence:* a completed candidate remains separate from the operational baseline until an approval decision is recorded.

**FR-18 — Exact-action approval.** Baseline promotion or replacement shall require an explicit authenticated decision bound to the candidate, current baseline, material parameters, consequence summary, and their versions.  
*Testable consequence:* expired, reused, mismatched, altered, or stale approval attempts are rejected and require a refreshed proposal.

**FR-19 — Atomic baseline promotion and recovery.** A valid approval shall promote one schedule version and preserve prior versions for inspection and approval-gated re-promotion.  
*Testable consequence:* baseline promotion and its authoritative audit record either both succeed or neither succeeds; a retry cannot create a second effect.

### 4.6 Provenance and review

**FR-20 — Complete decision provenance.** The planner shall inspect a timeline linking the request, evidence consulted, concise decision summary, tool proposals and results, guardrail/policy outcomes, solver run, approval, execution result, and before/after versions.  
*Testable consequence:* a reviewer can reconstruct who requested and approved a change, what evidence and versions governed it, and what changed without access to hidden chain-of-thought.

**FR-21 — Complete authoritative audit.** Successful, denied, stale, failed, and cancelled consequential actions shall produce unsampled, append-only, site-scoped business audit evidence.  
*Testable consequence:* disabling observability does not remove or prevent the authoritative record.

### 4.7 Predefined fixture catalogue

**FR-22 — Predefined scenario selection.** The planner shall select the active scenario from an application-provided fixture catalogue; the MVP shall not accept scenario uploads or creation/modification of source workforce, demand, or DC configuration data.  
*Testable consequence:* every agent run references an immutable predefined fixture version, and no chat, page, or API path can introduce custom scenario source data.

### 4.8 MVP capability catalogue

The agent's initial allow-listed capability surface is intentionally small and grouped around business outcomes rather than many low-level optimizer operations:

1. inspect the selected scenario, including schedule, demand, workforce, coverage, locks, and constraint evidence;
2. create or revise a reversible schedule-change draft;
3. start bounded CP-SAT optimization;
4. inspect durable run status, feasibility, and result evidence;
5. compare candidate and baseline schedule versions;
6. propose approval as the ShiftMind operational baseline.

The implementation may combine read operations internally, but it may not add general-purpose database, code-execution, credential, administrative, or network capabilities to satisfy an MVP request.

**FR-23 — Extensible governed capability model.** New agent capabilities shall be addable as versioned modules that declare typed contracts, permissions, site/resource scope, risk and approval policy, budgets, audit summaries, and evaluation cases without changing the core agent loop.  
*Testable consequence:* a demonstration capability can be registered and removed without editing orchestration control flow, remains unavailable by default, and cannot execute until its policy and evaluation contract are present.

### 4.9 Read-only Scenario Data viewer

**FR-24 — Read-only Scenario Data viewer.** For the selected predefined fixture version, the authenticated planner shall be able to open a read-only Scenario Data viewer that exposes the agent-relevant normalized data: stable identifiers and version metadata; work areas and tasks; workers, qualifications, and availability; demand intervals; operational-baseline assignments; locks; and active scheduling constraints and objectives. Values and identifiers shown in the viewer shall match those available to the agent's allow-listed scenario inspection capability for that fixture version. The viewer shall provide no upload, create, edit, delete, or import action.  
*Testable consequence:* an automated browser/API test verifies the normalized viewer payload against the agent inspection payload for the same fixture version and confirms that the viewer surface exposes no data-mutation control or supported mutation endpoint.

### 4.10 Delivery cutline

The portfolio is built through two required gates, not as one undifferentiated backlog:

- **Gate A — Inspectable agent thesis:** FR-1 through FR-11, FR-15, and FR-17 through FR-24 prove one secure, grounded inspect–investigate–draft–optimize–compare–approve journey using a deterministic local test environment. Gate A begins with a pre-orchestration foundation: authentication and site scope, the predefined fixture catalogue, the normalized scenario read contract, and the read-only Scenario Data viewer. The viewer and its read-only/parity tests shall be complete before implementation of the agent runtime or tool orchestration begins. This is the earliest credible interview demonstration.
- **Gate B — Production-shaped proof:** FR-12 through FR-14, FR-16, the quality/evaluation requirements, AWS deployment, backup/restore, observability independence, and rollback complete the declared portfolio MVP.
- **Beyond the cutline:** every non-goal in §2.2 and future capability in §11 remains post-MVP. If schedule pressure threatens Gate A or Gate B, reduce polish or defer future work; do not weaken an agent invariant or silently add SaaS breadth.

## 5. Agent Guardrails and Autonomy Contract

### 5.1 Autonomy tiers

| Tier | Agent may do | Human control |
|---|---|---|
| Inspect | Read site-scoped schedule evidence, explain, compare, and clarify | Automatic |
| Draft | Create reversible constraints, goals, and candidate parameters | Planner reviews or revises |
| Compute | Launch bounded solver work and report durable progress | Requires the planner's current explicit run request; no separate consequential approval |
| Consequential | Promote or replace the internal operational baseline | Exact-action approval required |
| Prohibited | Identity/role administration, arbitrary SQL/shell/network/credential access, bypass of policy or optimizer | Never available |

Reviewing or accepting draft parameters authorizes a bounded computation, not a change to the operational schedule. In this PRD, a “schedule-affecting change” means promotion or replacement of the internal operational baseline and therefore requires the formal exact-action approval in FR-18.

### 5.2 Invariants

- No model output, model memory, uploaded content, browser-supplied tenant value, or client-supplied approval flag can authorize an action.
- Identity, current membership, resource ownership, versions, risk class, budgets, approval validity, domain invariants, and idempotency are checked by application-owned controls for every tool execution.
- Prompts, notes, uploads, and tool output are untrusted content and cannot redefine tool policy.
- The product stores concise decision summaries and supporting evidence, not private chain-of-thought.
- A stale proposal fails closed; it is not silently rebased.
- Observability failure cannot disable scheduling, approval, baseline-promotion audit, or the manual fallback.

## 6. Quality and Non-Functional Requirements

### 6.1 Security and privacy

- Zero cross-site reads or writes in the tenant-isolation test suite.
- One hundred percent of mutating tool calls include current authorization, expected resource version, idempotency protection, and audit evidence.
- Workforce, prompt, schedule, and credential content is excluded from external telemetry by default; only explicitly allow-listed sanitized metadata may leave the application boundary.
- Secrets never appear in prompts, browser payloads, audit summaries, logs, traces, or evaluation fixtures.
- Prompt-injection tests cover chat messages and every untrusted data channel introduced by the MVP.

### 6.2 Reliability and consistency

- Worker termination and recovery produce zero duplicate effects.
- Accepted work remains discoverable after browser, API, or worker interruption.
- One hundred percent of operational-baseline promotions require a valid parameter- and version-bound approval.
- Baseline promotion, schedule versioning, and its successful audit evidence share one consistency boundary.
- Model-provider or Logfire failure produces zero corruption and zero loss of authoritative audit; supported manual and deterministic workflows remain available.

### 6.3 Scheduling correctness and explanation quality

- One hundred percent of completed feasible schedules satisfy deterministic hard constraints.
- One hundred percent of numerical agent claims pass the grounding evaluator before release.
- Infeasible, timed-out, cancelled, failed, and successful runs are never presented as equivalent.
- Planner locks remain satisfied or the run returns a clear infeasibility diagnosis.

### 6.4 Performance and cost control

- The product records API acknowledgement latency, time to first persisted event, end-to-end agent duration, model/tool latency, solver duration, queue age, approval age, token use, and cost per completed task.
- All agent and solver budgets are explicit configuration with safe defaults; they are not chosen by the model.
- Public-launch latency, availability, recovery, concurrency, retention, and cost objectives shall be set from measured portfolio traffic before accepting a customer. No unsupported enterprise service-level claim is part of the MVP.

### 6.5 Accessibility and usability

- The primary desktop-web journey is operable by keyboard, exposes meaningful status text rather than color alone, and announces durable progress and approval state to assistive technology.
- Consequences and approval controls use plain operational language and keep “review,” “run optimization,” and “approve as baseline” as distinct actions.

### 6.6 Deployability and operations

- Every environment is reproducible from reviewed infrastructure code and immutable application images.
- Every agent run is searchable by a stable run identifier across product records, audit, operational logs, and available traces.
- An unhealthy AWS release can be rolled back to the prior image and schema-compatible version through a tested procedure.
- AWS costs, queue health, agent budget cutoffs/failures, tool denials/timeouts, guardrail denials, approval age/outcomes, solver duration/failure, evaluation regressions, audit write failures, model failures, and telemetry-export health are observable and alertable.

## 7. Evaluation and Release Evidence

Release evaluation is deterministic-first. A live model demonstration supplements but does not replace automated evidence.

Required suites cover:

- correct tool selection and argument resolution;
- authorization refusal and cross-site/resource denial;
- forbidden-tool and excessive-agency attempts;
- approval required, mismatch, expiry, replay, and stale-version cases;
- grounded versus fabricated schedule and KPI claims;
- prompt injection through all supported untrusted inputs;
- Scenario Data viewer read-only enforcement and viewer-to-agent normalized-data parity for every Gate A fixture;
- malformed model responses, provider timeout, and exhausted budgets;
- solver feasibility, infeasibility, timeout, locks, and constraint edges;
- worker crash, lease recovery, replay, cancellation, and idempotency;
- telemetry-disabled product operation and authoritative audit continuity;
- keyboard-complete primary journey and repeatable browser demonstration.

Every evaluation report binds the dataset, evaluator, model, prompt, tool, policy, and application versions used. Sanitized production or demonstration failures become version-controlled regression cases after review.

**[ASSUMPTION]** The initial curated golden dataset contains at least 50 versioned cases, covers every allowed capability with at least four cases, and includes at least ten consequential or prohibited-action cases. It must achieve at least 90% correct tool selection overall and 100% correct consequential/prohibited routing before release. Any regression in authorization, approval, tenant isolation, hard constraints, grounding, idempotency, or authoritative audit is release-blocking regardless of average helpfulness scores. Human-rated usefulness and explanation quality are reviewed only after deterministic gates pass.

## 8. Success Metrics and Countermetrics

### 8.1 MVP acceptance statement

The MVP is complete when one authenticated planner can inspect the selected fixture's normalized Scenario Data, investigate and safely repair its schedule through chat, and verify that agent explanations use the same versioned facts; solver work survives interruption; operational-baseline promotion requires valid approval; every action is attributable and evidence-linked; deterministic and agent evaluations pass; sanitized hosted observability is available without becoming a dependency; and the system deploys reproducibly to AWS with tested backup/restore and rollback.

### 8.2 Product and demonstration metrics

| Measure | Protocol and baseline | MVP target / decision rule | Owner |
|---|---|---|---|
| Seeded disruption repair | Deterministic feasible fixture versus its saved baseline | Close the seeded gap, preserve locks, create zero hard violations, and keep overtime at or below baseline in every CI run; any miss blocks release | Scheduling/QA |
| Scenario Data integrity | Each Gate A fixture rendered through the viewer and agent inspection contracts | 100% value and identifier parity for agent-relevant normalized fields, with no supported viewer mutation path; any mismatch or mutation path blocks Gate A | Backend/QA |
| Infeasibility honesty | Deterministic infeasible fixture | Diagnose as infeasible without a promotable candidate in every CI run; any false success blocks release | Scheduling/QA |
| Numerical grounding | Versioned factual and adversarial claims | 100% verified against saved evidence; any unsupported number blocks release | AI/QA |
| Tool routing | Versioned golden set described in §7 | At least 90% overall and 100% on consequential/prohibited cases; otherwise block release | AI/QA |
| Stale and repeated actions | Version/approval/idempotency suites | 100% stale conflicts rejected and zero duplicate effects; otherwise block release | Backend/security |
| Primary journey completion | Automated browser test plus ten recorded portfolio rehearsals | Browser suite passes every run; report rehearsal completion time and failures, but do not claim an external-user benchmark | Product/QA |
| Runtime and cost | Instrument every completed task | Report tokens, agent/solver duration, queue and approval age, and estimated cost; set a customer target only after measured AWS traffic | Platform/product |
| Planner behavior | Not available in synthetic portfolio operation | Record acceptance, rejection, revision, manual override, and time-to-decision only in a consented pilot; no MVP target | Product |

### 8.3 Countermetrics

- Do not maximize tool-call count, conversational length, or autonomous action; lower bounded effort is preferable for the same correct outcome.
- Do not treat approval rate as success; rejection and revision are healthy when consequences are not acceptable.
- Do not reduce completion time by skipping evidence, validation, or approval.
- Do not improve average feasibility by hiding infeasible or timed-out cases.
- Do not improve coverage by excessive assignment churn, unfair workload movement, ignored preferences, or unexplained manual corrections; report these deltas with the proposal.
- Track misleading-explanation and planner-correction rates separately from conversational satisfaction.
- Do not claim labor savings, ROI, or enterprise reliability without real-user and production evidence.

## 9. Data Governance and Audit Policy

- The MVP processes workforce identity references, qualifications, availability, assignments, demand, schedules, conversation content, and decision evidence as sensitive operational data.
- Product data and authoritative audit remain under ShiftMind's controlled persistence. External model and observability providers receive the minimum necessary content under explicit configuration.
- Successful mutations record audit evidence in the same business transaction where possible. Denied and failed consequential attempts are recorded reliably and separately.
- Audit captures actor/site, request/run/tool/approval/job identifiers, action and policy outcome, safe input/result summaries or hashes, before/after versions, software/model/prompt/tool/policy versions, and immutable evidence references.
- Audit access is site-scoped. The normal application path cannot update or delete audit events.
- Customer-specific retention, export, deletion, residency, and legal requirements are deferred until before the first external production pilot; the portfolio must document its current settings and limitations.

## 10. Dependencies and Risks

| Risk | Product response |
|---|---|
| Scope exceeds a finishable portfolio milestone | Gate work by one vertical journey and defer SaaS administration and broad WFM features |
| Agent attempts unauthorized or excessive action | Narrow capabilities, trusted context, deterministic policy, budgets, exact approval, and audit |
| Tenant or employee data leaks | Site scope everywhere, deny-by-default tests, telemetry minimization, secret scanning |
| Retry or recovery duplicates effects | Durable state, idempotent commands, leases, versions, and atomic transitions |
| State changes while a proposal is pending | Bind proposal and approval to current versions; reject stale state |
| Explanation fabricates a schedule fact | Evidence references, recomputation, deterministic grounding evaluation |
| Approval UX creates automation bias | Separate proposal, evidence, explicit run, baseline approval, and promotion; never pre-authorize |
| Framework or provider changes leak into product behavior | Own the product contract and evaluate adapters against versioned fixtures |
| Cloud or telemetry costs become uncontrolled | Explicit budgets, usage measurement, alerts, and correctness-independent telemetry |
| Architecture remains only a diagram | Require executable failure demonstrations and release evidence |

External dependencies include a model provider, the CP-SAT optimizer, authentication, durable persistence, object evidence storage, AWS hosting, and optional hosted observability. The product shall expose failure state and preserve supported workflows when a non-authoritative dependency is unavailable.

## 11. Future SaaS Direction

### 11.1 Pre-pilot product-discovery gate

The architecture may proceed as a portfolio proof, but ShiftMind shall not claim validated product differentiation or begin an external production pilot until at least five DC planners or managers have been interviewed using the journey and evidence prototype. **[ASSUMPTION]** Revisit the product thesis if fewer than three identify disruption repair as a top-three planning pain, cannot understand the draft/run/approve boundary, or prefer their existing workflow after reviewing the proof. Record workflow duration, current tools, trust concerns, required integrations, and which evidence changes a decision; do not treat interview enthusiasm as proof of ROI.

After the portfolio milestone, a DC manager may create an organization, register one or more DC sites, invite members, and assign planner, viewer, approver, and manager roles. The default product model is pooled infrastructure with strict logical site isolation. Dedicated customer infrastructure is an exceptional enterprise/compliance option, not the standard architecture.

Likely post-MVP capabilities are invitation onboarding, multi-user roles, separation of duties, customer-configurable policies, quotas and billing, data-import integrations, retention controls, stronger availability, and measured scaling. DC-management features will let authorized users manage team members, site configuration, and uploaded or editable scenarios. The agent may later access those functions only through explicit read/write capability modules with role, site, risk, approval, and audit policy; they never become implicit model authority. These additions are not allowed to weaken the MVP's site boundary or agent invariants.

## 12. Deferred Product Decisions

| Question | Current MVP decision | Owner and revisit point |
|---|---|---|
| What does “approve as baseline” mean? | Promote a candidate to the versioned ShiftMind operational baseline only; no WMS export or execution | Product owner before any WMS/export integration |
| May the planner approve their own proposal? | [ASSUMPTION] Yes for the one-user portfolio, through a distinct approval step | Product/security before activating a second user |
| What is the exact demo dataset and target before/after result? | [ASSUMPTION] Use a seeded Wednesday outbound fixture whose known-feasible repair closes its coverage gap, preserves locks, introduces no hard-constraint violation, and does not increase overtime; preserve the infeasible variant as a separate evaluation case | Product owner verifies generated fixture before portfolio-demo freeze |
| What latency, availability, recovery, and concurrency targets apply? | Instrument first; make no enterprise SLO claim | Architecture/product after AWS benchmark and before external pilot |
| How long are conversations, audit, and snapshots retained? | Document portfolio configuration; no customer policy claim | Security/product before external production data |
| Which roles can approve a baseline, view audit, or manage sites? | Only the seeded planner is active | Product/security during multi-user milestone |
| Which WMS, HR, demand, or identity systems integrate first? | None beyond managed identity in the MVP | Product discovery before customer pilot |
| How will custom scenario and DC-management actions be exposed to the agent? | Defer the functions, but require versioned permissioned capability modules now | Architecture/product during the DC-management milestone |
| Which residency, compliance, and model-provider restrictions apply? | No customer-specific claim | Legal/security when a target customer or region is selected |

## 13. Assumptions

- **[ASSUMPTION]** Maya is a fictional representative persona, not validated user-research evidence.
- **[ASSUMPTION]** The portfolio is operated initially by its developer for demonstrations with synthetic or explicitly permitted data.
- **[ASSUMPTION]** Desktop web is the primary experience; mobile worker workflows are out of scope.
- **[ASSUMPTION]** The seeded planner may self-approve, but approval remains explicit, exact, authenticated, and version-bound.
- **[ASSUMPTION]** Existing manual and deterministic solver workflows remain available when the AI agent cannot operate.
- **[ASSUMPTION]** The future SaaS normally uses pooled infrastructure with logical organization/site isolation; a dedicated stack is exceptional.
- **[ASSUMPTION]** Real customer discovery is required before claiming product-market fit, labor savings, or complete DC rule fidelity.
- **[ASSUMPTION]** The initial golden evaluation set contains at least 50 cases with the coverage described in §7; revise its size from observed failure diversity rather than treating case count as quality.

## 14. Glossary

| Term | Meaning in ShiftMind |
|---|---|
| DC | Distribution centre represented as a site-scoped workspace |
| Planner | User who investigates, drafts, explicitly starts optimization, and—only in the single-user MVP—approves a candidate as the operational baseline |
| Scenario | Versioned scheduling inputs, demand, workforce data, locks, constraints, and objectives |
| Scenario Data | Read-only planner view of the selected predefined fixture's agent-relevant normalized data and version metadata |
| Schedule version | Immutable candidate or operational-baseline assignment set derived from a scenario/run |
| Operational baseline | The schedule version currently promoted for internal operational use |
| Run | Durable CP-SAT execution with versioned inputs, state, result, and evidence |
| Draft | Reversible proposed constraints/objectives that do not change the operational baseline |
| Baseline promotion | Approval-gated promotion of one candidate schedule version to ShiftMind's internal operational baseline; not WMS export/execution |
| Constraint | Hard or soft scheduling rule, including planner locks and preferences |
| Material ambiguity | Missing or conflicting identity, scope, time, action, consequence, or version information that could change the selected capability or result |
| Evidence-linked | Bound to identifiers for saved facts or reproducible computations from the stated scenario/schedule/run version |
| Schedule diff | Affected workers, shifts, roles/tasks, interval coverage, overtime, objective components, constraints, and unresolved infeasibility between two named versions |
| Budget | Application-owned positive ceiling for model calls, tool calls, tokens, retries, solver time, concurrency, or elapsed time |
| Authoritative audit | Unsampled append-only business evidence independent of operational logs and traces |
| Grounding | Linking a claim to saved product facts or reproducible computations |
| Approval | Authenticated decision over an exact action, consequence summary, and current resource versions |
| Provenance | Evidence chain from request and policy through solver, approval, and resulting state |
