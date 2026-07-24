# Product and Market Review — ShiftMind PRD

- **Artifacts reviewed:** `prd.md`, `addendum.md`
- **Review lens:** differentiation, user-journey coherence, testability, MVP scope, success/countermetrics, and market-claim support
- **Gate verdict:** **Revise before green-light.** The PRD has a coherent trust thesis, explicit non-goals, and a strong deterministic-authority boundary. It is credible as a production-shaped portfolio brief, but it does not yet prove a market wedge, deliver an operationally consumable end state, or define a measurable MVP cutline.
- **Reviewer-source limitation:** `.agents/skills/bmad-prd/assets/reviewers/default.md` was requested but is absent from the installed skill. This review uses the loaded PRD quality rubric plus the requested product/market lens.

## What holds up

- The PRD does not pretend that conversational scheduling, optimization, explanations, or approvals are novel (§1.2).
- The authority boundary is clear: the model interprets and orchestrates; CP-SAT owns assignments and feasibility (§1, FR-10).
- The single disruption-to-publication journey gives the capability set a coherent spine (§3.3).
- Non-goals are unusually explicit, particularly the exclusions around payroll, forecasting, worker self-service, WMS orchestration, and autonomous publication (§2.2).
- Hard-constraint, stale-approval, idempotency, grounding, and audit gates are materially testable (§6–7).

## Findings

### 1. **High — “Depth and inspectability” is a positioning hypothesis, not established differentiation** (§1.2)

The competitor paragraph is appropriately cautious, but the next sentence still promotes “depth and inspectability” as differentiation without a comparative test. Legion's current assistants already claim schedule-change explanations and cost, coverage, compliance, and employee-experience trade-off analysis; Blue Yonder claims warehouse labor reallocation with approval; Infor documents mathematical optimization and schedule audit history. The cited vendor pages support market convergence, but not the claim that ShiftMind is deeper or more inspectable.

**Exact fix:** Rename §1.2 to **“Positioning hypothesis and proof obligation.”** Replace “Its focused differentiation is…” with: “ShiftMind bets that constraint-level reproducibility and an explicit agent/optimizer authority boundary can earn planner trust in one narrow DC repair workflow. This is unvalidated until planners can compare its evidence and recovery behavior with their current process.” Add a validation condition: at least the target number of planner interviews/usability sessions must identify evidence-level inspection as valuable and distinguishable; until then, call this a design thesis, not a market advantage.

Primary market evidence: [Legion 2026 AI Assistants](https://legion.co/company/press-releases/2026/01/12/legion-ai-workforce-management-innovations/), [Blue Yonder Warehouse Ops Agent](https://media.blueyonder.com/blue-yonder-transforms-supply-chain-management-with-new-ai-agents), [Infor Workforce Scheduling](https://www.infor.com/solutions/human-capital-management/workforce-management/scheduling).

### 2. **High — The journey ends at an “operational baseline” that no operation can consume** (§3.3 step 9, FR-16–18, §12)

The product says it repairs and publishes a schedule, but “publish” only promotes an internal version. WMS integration, worker communication, and every external scheduling system are excluded. Maya therefore finishes with a technically authoritative record that may not be usable on the floor. This weakens the core job-to-be-done and risks presenting an internal state transition as operational value.

**Exact fix:** Add one minimal, non-integrated consumption outcome to the MVP: after approval, Maya can download or print the approved schedule and its effective date/version in a format usable by the demo workflow. Add an FR and testable consequence. If even export is intentionally excluded, rename “publication” to **“approve as ShiftMind baseline”** everywhere and state explicitly in the acceptance statement that operational deployment is not demonstrated.

### 3. **High — The MVP has a vertical journey but no implementation cutline** (§2.1, FR-1–20, §6–8, addendum §9)

The scope combines a new conversational experience, deterministic repair, durable jobs, reconnection, worker-crash recovery, cancellation, exact approvals, provenance, tenant isolation, privacy controls, evaluation infrastructure, AWS deployment, observability, and rollback. Every item is treated as mandatory, even though the stated risk is failure to finish a portfolio milestone. The addendum sequences work but does not say what can be cut while preserving the thesis.

**Exact fix:** Add a **“MVP cutline”** table with three bands: (A) thesis-critical demo, (B) production-shaped trust proofs, and (C) stretch. Put the end-to-end repair, hard constraints, before/after evidence, stale approval, and audit in A; put browser reconnect, worker-kill recovery, telemetry-disabled proof, and AWS rollback in B; explicitly identify any stretch items. Define green-light as completion of A plus a named minimum subset of B. Do not leave all 20 FRs at one priority.

### 4. **High — Success metrics mostly name observations, not success** (§8.2)

“Median time,” “feasible proposal rate,” acceptance/revision rates, and cost are listed without baselines, sample sizes, targets, collection methods, or decisions they trigger. With one seeded account operated by the developer, a median and behavioral rates are not meaningful product metrics. The acceptance statement can therefore be satisfied without proving the value proposition that conversation reduces planner effort while preserving trust.

**Exact fix:** Split §8 into:

1. **Portfolio acceptance gates** with target, test fixture count, repetition count, and pass/fail rule.
2. **Usability-validation measures** collected from named planner sessions, with a baseline workflow and decision threshold.
3. **Future production measures** explicitly marked non-gating.

For every retained metric, add `{baseline, target, sample/protocol, owner, decision if missed}`. Replace developer-only acceptance/revision “rates” with counts until a real cohort exists.

### 5. **High — The user problem and value proposition remain unvalidated assumptions** (§1.1, §3.1–3.3, §13)

The PRD honestly labels Maya fictional, but still asserts that planners currently navigate forms, solver parameters, and raw data and that the selected Wednesday-outbound workflow is the right wedge. No customer, workflow observation, or source supports those claims. Building can proceed as a portfolio exercise, but the document should not blur technical demonstration with discovery evidence.

**Exact fix:** Mark §1.1 and the primary journey as **product hypotheses**. Add a pre-pilot discovery gate covering real planner workflow, current tools/artifacts, disruption frequency, authority to change schedules, required evidence, and handoff after approval. State what findings would invalidate or change the selected journey.

### 6. **High — Model-outage fallback is promised but absent from the product requirements and journey** (§3.4, §6.2, §10, §13)

The PRD repeatedly promises that manual and deterministic workflows remain available when the model is unavailable, yet no FR defines what Maya can actually do, which inputs remain available, or how the fallback reaches optimization and publication. The addendum treats this as an invariant, so it cannot remain an untestable principle.

**Exact fix:** Either add a fallback journey and FR specifying how Maya reviews/edits proposal parameters, starts CP-SAT, compares the result, and requests approval without the model, or remove the fallback claim from MVP acceptance and mark it post-MVP. Add one end-to-end provider-outage acceptance test if retained.

### 7. **High — Draft acceptance and compute authority are contradictory** (§3.3 step 6, FR-11, §5.1)

The journey says Maya accepts draft parameters before optimization. FR-11 says “the planner or agent” can start optimization, and the autonomy table says compute is automatic within budgets. It is unclear whether reviewing a draft is mandatory, whether the agent may run speculative candidates without consent, and whether “accept” is itself an approval or merely a command.

**Exact fix:** Choose one rule and state it consistently. Recommended for this MVP: a draft never runs until Maya invokes **Run optimization**; this is not consequential approval, but it confirms the exact constraint/objective payload. Update the journey, FR-8/9/11, and autonomy table with the same transition and terminology.

### 8. **High — Several requirements cannot yield unambiguous acceptance tests** (FR-5–7, FR-11, FR-14, FR-19; §6.4)

Terms such as “materially ambiguous,” “unsupported,” “over-budget,” “clearly shows,” “safe defaults,” and “reviewer can reconstruct” have no enumerated boundary. Performance requirements instrument latency and cost but set no portfolio-level bound, even for the scripted demo. This pushes product decisions into implementation and test authorship.

**Exact fix:** Add a compact acceptance appendix defining: ambiguity cases, allowed evidence types, grounding coverage, consequence-summary fields, required diff fields, audit completeness fields, default budgets, and scripted-demo response-time bounds. Keep public SLOs deferred, but set local/AWS portfolio thresholds for the journey being accepted.

### 9. **Medium — Failure branches are states, not a coherent user journey** (§3.3, FR-12, §3.4)

The happy path mentions an unresolved gap, but does not show what Maya can do when a run is infeasible, timed out, failed, or cancelled. FR-12 also mixes `approval-required` into run states even though publication approval follows candidate completion. This leaves UX and story authors to invent recovery behavior.

**Exact fix:** Add a short alternate-flow table for infeasible, timed-out, failed, cancelled, stale, and provider-unavailable outcomes. For each, specify what evidence Maya sees, permitted next actions, and whether the candidate can proceed. Separate solver-job state, agent-turn state, candidate state, and publication-approval state in the glossary.

### 10. **Medium — The 90% tool-selection gate is arbitrary and can hide weak slices** (§7)

The golden-dataset threshold lacks dataset size, labeling procedure, confidence interval, and per-intent breakdown. An average can pass while clarification, refusal, or publication-proposal selection performs poorly. The release-blocking deterministic gates help, but they do not define acceptable task-level usefulness.

**Exact fix:** Define dataset version, minimum case count by intent, expected-tool/argument labeling rules, and slice-level thresholds. Require 100% on prohibited/consequential routing cases, and set separate thresholds for read, draft, compute, clarification, and refusal cases. Record why the chosen thresholds are sufficient for a portfolio release.

### 11. **Medium — Countermetrics protect governance but not schedule quality or planner trust** (§8.3)

The countermetrics correctly resist approval-rate and speed gaming, but do not constrain unnecessary assignment churn, soft-constraint/fairness regression, misleading but numerically grounded explanations, or planner correction burden. A feasible, grounded schedule can still be operationally poor.

**Exact fix:** Add countermetrics for changed assignments per repaired gap, soft-constraint/fairness regressions, planner corrections to resolved entities or constraints, proposals rejected for operational implausibility, and explanations rated technically true but decision-misleading. Treat these as usability evidence, not production claims.

## Unsupported or overextended claim audit

- **Supported and appropriately qualified:** competitor convergence in AI scheduling, optimization, assistants, explanations, and approvals (§1.2).
- **Unsupported comparative claim:** ShiftMind's greater “depth and inspectability”; current citations establish competitor capability, not ShiftMind superiority.
- **Unsupported user claim:** the asserted planner burden of navigating forms, solver parameters, and raw data (§1.1).
- **Correctly avoided:** labor savings, ROI, product-market fit, complete DC rule fidelity, and enterprise reliability claims (§8.3, §13).

## Recommended disposition

Do not expand the architecture. Resolve findings 1–8 in the product contract first. After those fixes, the PRD can credibly authorize a portfolio build while remaining explicit that market differentiation and planner value are hypotheses awaiting user evidence.
