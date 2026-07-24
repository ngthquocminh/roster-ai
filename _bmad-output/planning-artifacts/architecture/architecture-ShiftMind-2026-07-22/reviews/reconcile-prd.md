# PRD and Technical Addendum Reconciliation

## Verdict

**NEEDS REVISION — substantively aligned, but four load-bearing source constraints are not yet fixed by the spine and one data-ownership relationship conflicts with the addendum.**

The draft preserves the central product thesis: a hexagonal modular monolith, a strict model/application/CP-SAT authority partition, site-scoped server authority, immutable scenario and schedule versions, durable workflow state, exact-action approval, deterministic grounding, separate records of truth, a governed capability registry, and a production-shaped AWS deployment. There is no paradigm-level conflict with the PRD. The gaps below are narrower, but several are precisely the kind of cross-epic invariant that the spine exists to settle.

## Sources Compared

- `prd.md` (final, 2026-07-22), including FR-1–FR-24, delivery gates, autonomy contract, NFRs, release evidence, data governance, assumptions, and deferred decisions.
- `addendum.md` (final, 2026-07-22), including the architecture thesis, runtime/tool contract, durable workflow, logical data model, observability boundaries, AWS target, and implementation sequence.
- `ARCHITECTURE-SPINE.md` (draft, 2026-07-22), AD-1–AD-18, conventions, stack, structural seed, capability map, and Deferred table.

## Findings

### R-1 — High: authoritative audit and provenance completeness is not an invariant

**Source contract.** FR-20 requires the inspectable provenance chain to link request, consulted evidence, concise decision summary, tool proposals/results, guardrail and policy outcomes, solver run, approval, execution result, and before/after versions. FR-21 requires successful, denied, stale, failed, and cancelled consequential actions to produce unsampled, append-only, site-scoped audit evidence. PRD §9 further fixes the audit envelope: actor/site; request/run/tool/approval/job IDs; action and policy outcome; safe summaries or hashes; before/after versions; software/model/prompt/tool/policy versions; and immutable evidence references. The addendum says successful mutation and audit commit together while denial/failure are recorded reliably.

**Spine state.** AD-12 correctly separates product state, audit, evidence, operational logs, traces, and evaluation records. AD-10 atomically couples successful promotion and audit. The capability map assigns FR-20–FR-21 to AD-10–AD-12. However, no rule fixes the minimum provenance/audit envelope or guarantees authoritative records for non-success outcomes. Two epics could therefore emit mutually incompatible partial timelines while both appearing compliant with “append-only audit.”

**Required reconciliation.** Add or amend an AD to bind the complete provenance envelope, all consequential outcome classes, stable version/correlation fields, and the different consistency rule for success versus denial/failure. Keep the record free of private chain-of-thought (see R-6).

### R-2 — High: model-outage fallback lacks an independent application entry point

**Source contract.** FR-8 and the recovery journey require saved scenarios/results and the existing manual deterministic solver workflow to remain available when the model is unavailable. PRD §5.2 makes observability failure and model unavailability unable to disable the manual fallback. The addendum places `AgentRuntime` at an adapter boundary rather than in the deterministic scheduling path.

**Spine state.** The hexagonal diagram permits HTTP to call application use cases, and the FR map mentions “fallback,” but none of AD-1, AD-2, AD-5, or AD-15 requires a non-agent command path to start the same bounded deterministic solver workflow. A delivery unit could accidentally make run creation reachable only through the agent/capability adapter.

**Required reconciliation.** Fix the manual solver command/query surface as an application-owned path independent of `AgentRuntime` and the model provider, sharing the same authorization, versions, budgets, job state machine, evidence, and audit contracts as agent-initiated work.

### R-3 — High: the mandatory Gate A sequencing constraint did not land

**Source contract.** PRD §4.10 requires Gate A to begin with authentication/site scope, fixture catalogue, normalized scenario read contract, and the read-only Scenario Data viewer. The viewer plus read-only/parity tests must be complete before agent runtime or tool orchestration implementation begins. The addendum §9 repeats this order and says every stage ends with executable evidence.

**Spine state.** AD-4 correctly requires viewer and agent inspection to share one normalized projection. AD-16 requires viewer/agent parity to block release. The spine does not preserve the pre-agent dependency or the Gate A/Gate B cutline. Independent epics could start agent orchestration before the parity seam exists, defeating the explicit delivery-risk control.

**Required reconciliation.** Add the pre-agent dependency to the structural seed or an AD (viewer/read contract/read-only proofs precede `AgentRuntime` and tool orchestration). Preserve Gate A and Gate B as delivery constraints or explicitly defer the cutline to a named companion artifact that downstream planning must consume.

### R-4 — High: cross-cutting budget ownership and terminal semantics are underspecified

**Source contract.** FR-12 requires positive application-owned ceilings for solver time, agent iterations, model calls, tool calls, retries, tokens, concurrency, and total elapsed time, with each exceeded ceiling ending in a distinct bounded state. PRD §6.4 states that the model never chooses these budgets. The addendum places the budget and clock in trusted `AgentDeps` and validates each tool against budget.

**Spine state.** AD-5 requires each capability module to declare a budget/timeout, and AD-7 supplies run statuses. That does not bind orchestration-wide ceilings (iterations, aggregate calls/tokens/retries/elapsed time/concurrency), trusted ownership, or how each budget exhaustion is represented without collapsing into generic `failed`/`timed_out`. Implementations can therefore choose incompatible accounting scopes and exhaustion behavior.

**Required reconciliation.** Establish one application-owned budget ledger/envelope spanning agent run, tool calls, worker job, and solver, with positive configured ceilings, atomic consumption where duplication matters, model-independent ownership, and stable exhaustion reasons mapped to the closed state machine.

### R-5 — Medium: evidence-snapshot ownership conflicts with the addendum’s logical model

**Source contract.** The addendum §5 depicts `scenario_version -> schedule_run -> schedule_version -> evidence_snapshot`, while its prose also states that a run points to the exact object version. FR-14 makes the run retain immutable references to inputs, configuration, component versions, and result, including runs that may be infeasible or timed out and produce no candidate.

**Spine state.** The ER diagram makes `SCHEDULE_RUN ||--|{ EVIDENCE_SNAPSHOT`, not `SCHEDULE_VERSION -> EVIDENCE_SNAPSHOT`. AD-11 describes version-bound evidence references but does not settle aggregate ownership or cardinality.

**Impact.** This is a direct shape discrepancy. Run ownership is arguably better aligned with infeasible/timed-out evidence, but the override is not explicit, and schedule-level comparison evidence still needs a stable relation.

**Required reconciliation.** Decide and record whether evidence snapshots are run-owned, schedule-version-owned, or independent immutable artifacts referenced by both. Then align the diagram and source addendum if this spine intentionally supersedes it.

### R-6 — Medium: private reasoning and persisted model content boundaries are incomplete

**Source contract.** PRD §5.2 says the product stores concise decision summaries and supporting evidence, not private chain-of-thought. PRD §6.1 and §9 require minimal explicitly configured disclosure to model/observability providers. The addendum permits persisting model messages and structured outcomes as needed for resumption, but exposes application-owned summaries rather than hidden reasoning.

**Spine state.** AD-15 excludes prompt/tool/workforce/schedule content from external telemetry by default and keeps secrets server-side, but it does not prohibit chain-of-thought persistence/exposure in product records or state what model-conversation content is retained for recovery. AD-12 separates stores without a content contract.

**Required reconciliation.** Add a persistence/privacy rule: retain only user-visible messages, structured tool/outcome state, application-owned summaries, and required evidence; never request, store, expose, or treat hidden reasoning as provenance. Distinguish model-provider disclosure from external telemetry disclosure.

### R-7 — Medium: one-user identity enforcement remains ambiguous at the Cognito boundary

**Source contract.** FR-1 disables public registration. FR-2 permits only one authenticatable application user and one active membership; a second authenticatable user must be rejected. The addendum requires Cognito public sign-up off, subject-to-membership mapping, and portfolio provisioning/database invariants.

**Spine state.** AD-3 says provisioning plus database constraints enforce one authenticatable user and one active membership, and AD-17 chooses Cognito/BFF. It never explicitly disables Cognito self-sign-up. A PostgreSQL constraint can prevent a second application user or membership but cannot by itself prevent an additional identity from existing and being authenticatable at Cognito.

**Required reconciliation.** State that public/self sign-up is disabled and that the only provisioned Cognito subject must map to the sole active application user/membership; authentication without that current mapping grants no application session.

### R-8 — Medium: release-evidence provenance is weaker than the product contract

**Source contract.** PRD §7 requires every evaluation report to bind dataset, evaluator, model, prompt, tool, policy, and application versions. It also makes regressions in authorization, approval, tenant isolation, hard constraints, grounding, idempotency, or authoritative audit release-blocking regardless of aggregate helpfulness.

**Spine state.** AD-16 strongly captures deterministic-first gates and the release-blocking dimensions, but only says “versioned datasets/reports”; it does not bind the report to the full executable-input/version tuple. This weakens reproducibility across model, prompt, tool, and policy changes.

**Required reconciliation.** Extend AD-16 so each report records the complete evaluation identity tuple required by PRD §7.

### R-9 — Low: AWS cost-control and alert ownership are only implied

**Source contract.** The addendum requires AWS Budgets and cost-allocation tags. PRD §6.6 requires AWS cost, queue health, budget cutoff/failure, tool denial/timeout, guardrail denial, approval age/outcome, solver failure, evaluation regression, audit-write failure, model failure, and telemetry-export health to be observable and alertable.

**Spine state.** AD-17 fixes CloudWatch, backups, restore drills, deployment and rollback mechanics, but does not name cost controls or the required operational signals. AD-12 separates diagnosis from product truth. The capability map only assigns “AWS release and operations” generally.

**Required reconciliation.** Either extend AD-17 with cost allocation/Budgets and an owned alerting surface, or explicitly bind a named operational companion contract so implementation epics cannot omit it.

## Adequately Landed Constraints

- The model/application/CP-SAT authority boundary and prohibition on model-created accepted assignments are explicit in AD-2.
- Site and actor context are server-derived for requests, jobs, tools, approvals, audit, and evidence; RLS is defense in depth (AD-3).
- Fixture immutability, no mutation surface, and viewer/agent normalized-projection parity are structurally fixed (AD-4).
- Capability modules declare contracts, scope, policy, budgets, versions, safe evidence/audit mapping, errors, and evaluation cases without agent-loop branching (AD-5).
- Durable accepted work, worker leases, persisted progress, SSE replay, and non-authoritative process memory are fixed (AD-6–AD-8, AD-18).
- Proposals, solver results, schedules, and baselines use immutable/versioned boundaries; stale inputs fail closed (AD-9).
- Approval is exact, one-time, version/hash/policy/expiry bound, and promotion is atomic with successful audit (AD-10).
- Numerical grounding and evidence references are deterministic and version-bound (AD-11).
- Audit, evidence, logs, traces, and evaluations remain separate records with shared correlation IDs (AD-12).
- Browser/API contracts and client remote-state ownership are convergent (AD-13–AD-14).
- Prompt injection and arbitrary SQL/shell/network/credential/runtime capability installation are excluded (AD-15).
- Deterministic release gates, recovery/rollback proofs, and production-shaped AWS API/worker/data boundaries are captured (AD-16–AD-18).
- MVP scope remains fixture-only, single-site/single-user, without WMS execution, broad SaaS administration, multi-agent orchestration, generalized RAG, or premature distributed infrastructure.

## Assumptions and Deferred Scope Check

The spine preserves or appropriately defers the major source assumptions: a single seeded planner may self-approve; synthetic/permitted portfolio data; desktop web; pooled future SaaS isolation; one low-cost AWS portfolio environment; no enterprise SLO claim before measurement; no retention/residency/regulatory WORM claim; and no WMS/HR/demand/custom-scenario writes in the MVP. No deferred entry improperly pulls a PRD non-goal into the MVP.

The source’s “at least 50” golden-set size, product interview gate, demo rehearsal count, and exact seeded-fixture outcomes remain product/release requirements rather than architecture decisions. Their absence from the terse spine is acceptable as long as downstream planning continues to consume the final PRD; they should not be redefined by architecture epics.

## Recommended Disposition

Resolve R-1 through R-4 before finalizing the spine. Resolve the ownership choice in R-5 and align the addendum if necessary. R-6 through R-9 can be handled as concise amendments to existing ADs rather than new structural sections. After amendment, rerun deterministic lint and the reviewer gate, then repeat this reconciliation to confirm every high finding is closed.
