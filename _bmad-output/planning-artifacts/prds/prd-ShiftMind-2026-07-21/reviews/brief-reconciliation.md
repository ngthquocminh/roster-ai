# ShiftMind PRD — Product-Brief Reconciliation and Structural Review

## Overall verdict

The PRD is unusually coherent, test-oriented, and usable by architecture and story workflows. Its authority boundary, single-planner journey, typed capabilities, grounding, audit, and SaaS non-goals faithfully preserve the product brief. It is not yet cleanly reconciled, however: it converts several brief-level open questions and explicit exclusions into unmarked MVP commitments—most materially publication, PostgreSQL/worker recovery, cancellation, persisted SSE, and full AWS deployment—and it changes the brief's confirmation boundary.

## Source reconciliation

### Findings

- **High — Confirmation semantics changed without an explicit product decision** (§3.3 steps 5–8; §5.1; FR-9, FR-11, FR-16–FR-18) — The brief assumes schedule-affecting changes are previewed and explicitly confirmed, and its representative flow confirms before applying the change and starting the solve. The PRD allows draft creation and solver launch automatically, reserving exact-action approval for publication. This may be a better model, but it is a different consequence boundary and is not marked as an assumption or reconciled decision. *Fix:* state explicitly whether draft parameters require a planner acceptance before compute, define what counts as a “schedule mutation,” and log the selected boundary; align the journey, autonomy table, FRs, and success criteria.

- **High — Publication is a new MVP capability, not a brief requirement** (§2.1 goal 1; §3.3 steps 8–9; FR-16–FR-18; §8.1; §12 “What does publish mean?”) — The brief's polished workflow ends with candidate/baseline comparison and expressly prohibits autonomous publication; it never requires publication or promotion to an operational baseline. The PRD adds a publication state model, approval workflow, atomic promotion, re-promotion, provenance, and demo acceptance around publication. This is substantial scope and is presented as settled rather than as an assumption or option. *Fix:* either obtain/log the product decision that publication is necessary to prove consequential-action governance, or cut publication from MVP and make approval cover the exact schedule-affecting draft/run action described by the brief.

- **High — Durable production-shaped infrastructure overrides an explicit MVP exclusion** (§2.1 goals 4–5; FR-11–FR-15; §6.6; technical addendum §§2, 4, 5, 7, 9) — The brief explicitly excludes distributed job infrastructure and production SRE maturity and says SQLite/local worker may remain if boundaries are clean. The PRD/addendum require PostgreSQL, restart-safe leased work, cancellation, persisted event replay, separate API/worker processes, ECS/RDS/S3/CloudFront, telemetry alarms, deployment rollback, and infrastructure-as-code. This is a major expansion of the portfolio milestone, even if supported by the technical research. *Fix:* record this as a deliberate brief override with reason and delivery trade-off, or separate “required product MVP” from “portfolio deployment proof” and retain only the infrastructure needed for observable acceptance.

- **Medium — Open transport and authentication questions are silently resolved** (FR-1, FR-4, FR-12; technical addendum §§1–2, 4, 7) — The brief asks whether streaming is worth the scope and what minimum authentication mechanism is appropriate. The addendum commits to Cognito+BFF and persisted SSE with `Last-Event-ID` replay without an assumption/decision marker. *Fix:* log these as resolved decisions with rationale, or keep the PRD capability-level (managed authentication; reconnectable durable status) and defer mechanism selection to architecture.

- **Medium — Cancellation entered scope from an architecture-gap observation** (FR-12, FR-15; §7) — The source addendum says the current worker lacks cancellation; the brief's required lifecycle is pending/completed/failed and does not select cancellation for MVP. FR-15 and the evaluation suite make cancellation release-critical. *Fix:* justify cancellation as essential to the user job or move it to post-MVP; do not infer scope solely from a current-system gap.

- **Medium — The capability catalogue exceeds the brief's intended tool envelope because of publication** (§4.7) — The brief asks which five to eight tools form the strongest demo and says selection should follow the job rather than a target count. The PRD lists nine user-facing capabilities, with publication as the ninth. *Fix:* after resolving the publication decision, consolidate the catalogue to the minimum complete set and make clear these are product capabilities, not necessarily one-to-one model tools.

- **Medium — Demo fixture and outcome are chosen from an open question without assumption marking** (§12 “exact demo dataset”) — The brief leaves the scenario and measurable before/after result open. The PRD selects a Wednesday fixture that closes the gap, preserves locks, adds no hard violations, and does not increase overtime. This is useful, but the known-feasible data and achievable no-overtime outcome have not been evidenced in the supplied source. *Fix:* mark as `[ASSUMPTION]` until the generated fixture is verified, then convert it to a decided acceptance target and cite the fixture/evaluation evidence.

- **Low — The fictional named persona is appropriately disclosed but not source-derived** (§3.1; §13) — The brief only identifies a generic authenticated planner. “Maya” is clearly labeled fictional and is structurally useful, so this is not harmful invention, but it remains an assumption. *Fix:* add the inline `[ASSUMPTION]` marker at first introduction so the Assumptions section round-trips.

### Faithfully retained source content

- Vision/value proposition and the explicit LLM/optimizer authority boundary.
- One authenticated planner and one site, with SaaS administration out of scope.
- The Wednesday outbound investigation/change/solve/compare journey.
- Typed narrow capabilities, server-derived identity/site scope, no general SQL/repository tool.
- Grounded numerical explanations, immutable/versioned evidence, audit, deterministic tests, provider-failure containment, and honest non-production scheduling fidelity.
- Future organization/site/membership model and the need for real customer discovery before commercial claims.

## Structural PRD review

## Decision-readiness — adequate

The PRD makes strong decisions on authority, autonomy tiers, non-goals, publication semantics, and release-blocking invariants. Trade-offs are most explicit around pooled versus dedicated infrastructure and deterministic release gates. Decision-readiness is reduced because several decisions that materially change the source brief are presented as established requirements rather than as explicit overrides, especially publication and the production-shaped infrastructure milestone.

### Findings

- **High — Brief overrides are not exposed as overrides** (§2.1; FR-11–FR-18; technical addendum §§2, 7) — A reviewer cannot tell whether the expanded deployment/durability/publication scope was approved or simply inferred from research. *Fix:* identify and log each override, including what was given up (smaller SQLite/local-worker MVP and comparison-only journey) and why.

- **Medium — Some “deferred decisions” already contain substantive product decisions** (§12) — The table format makes choices visible, but publication semantics, self-approval, and fixture outcome are current decisions rather than unresolved questions. *Fix:* split “Decisions and trade-offs” from genuinely deferred/open questions; mark evidence-pending decisions as assumptions.

## Substance over theater — strong

The single fictional persona drives an actual journey and is explicitly disclaimed as research evidence. Differentiation is honest rather than novelty theater. Security, reliability, grounding, and approval requirements contain product-specific invariants and tests; the document does not rely on generic “secure/scalable/user-friendly” language.

### Findings

- **Low — Operations depth risks becoming portfolio theater if not tied to the central demo** (§6.6; technical addendum §§7–9) — AWS rollback, budgets, telemetry-export health, and numerous executable architecture proofs are credible, but together can overtake the planner-value slice. *Fix:* retain only proofs required to demonstrate the thesis and label the rest stretch/deferred if they threaten completion.

## Strategic coherence — strong

The thesis is clear: probabilistic interpretation around deterministic scheduling, with application-owned control and inspectable evidence. Functional requirements, guardrails, release evaluation, and countermetrics reinforce that thesis. The main strategic risk is scope, not incoherence.

### Findings

- **Medium — Most product/demo metrics lack pass/fail thresholds** (§8.2) — Median journey time, feasible proposal rate, approval/revision rates, and cost are observations rather than success criteria. The document does provide hard release gates elsewhere, so this does not make the PRD unusable. *Fix:* distinguish “instrument now/baseline later” measures from MVP acceptance metrics and set a pass condition for the repeatable interview journey.

## Done-ness clarity — adequate

Every numbered FR has a testable consequence, and the cross-cutting NFRs use strong zero/100% invariants where correctness matters. The release evidence section is detailed enough to seed acceptance and adversarial tests. Some boundedness and performance requirements remain intentionally configuration-based rather than quantitatively bounded.

### Findings

- **Medium — Budget boundedness is not fully testable from the PRD** (FR-11; §6.4) — The requirement lists solver, iteration, tool, retry, token, concurrency, and elapsed-time limits but defines no values or profile that stories can verify as the MVP default. “Safe defaults” is not a bound. *Fix:* require a versioned MVP budget profile with explicit values, while leaving tuning to architecture/configuration.

- **Medium — Reconnect/recovery acceptance combines several failure boundaries** (FR-12, FR-15) — Browser reconnect, event replay, worker restart, lease recovery, cancellation, and duplicate-effect prevention are bundled across two FRs, which can obscure partial completion. *Fix:* retain stable IDs but specify separate acceptance examples for client reconnect, worker interruption, cancellation race, and replay/idempotency.

## Scope honesty — thin

The non-goals are excellent and the product is candid about synthetic data, fictional persona, model fidelity, and unsupported commercial claims. However, scope honesty is weakened by material new commitments relative to the brief and by an Assumptions section that does not use the required inline `[ASSUMPTION]` convention.

### Findings

- **High — Assumptions do not round-trip to their claim sites** (§3.1; §11; §12; §13) — Seven assumptions are collected in §13, but none is tagged inline; other inferred decisions (publication, infrastructure, transport, fixture outcome) are absent from the assumptions list. *Fix:* mark each assumption at first material use, ensure every inline tag appears in §13, and log confirmed assumptions as decisions rather than leaving stale tags.

- **High — MVP scope is internally honest but not source-honest** (§2 versus source brief MVP scope) — The PRD clearly states its own scope, yet it does not reveal that cancellation, restart durability, deployment, and publication expand the approved brief boundary. *Fix:* reconcile these before finalization through explicit override decisions or scope cuts.

## Downstream usability — strong

The journey has a named protagonist, FR IDs are contiguous and unique (FR-1 through FR-20), domain terms are defined, and requirements are grouped coherently. The technical addendum cleanly carries mechanisms that should not dominate the product contract. Architecture and story creation can extract from this document with little ambiguity once scope reconciliation is complete.

### Findings

- **Low — “Schedule,” “candidate,” “schedule version,” and “operational baseline” need disciplined use in downstream stories** (§3.3; FR-9–FR-18; §14) — Definitions exist, but “operational schedule” appears where the glossary term is “operational baseline,” and “candidate” is defined only indirectly under schedule version. *Fix:* use the glossary term consistently and add an explicit `Candidate schedule` entry if it remains a first-class state.

## Shape fit — strong

The capability-spec shape with one load-bearing journey fits a single-operator, meaningful-UX portfolio product. It avoids persona proliferation and traceability-matrix overhead while providing enough product, governance, evaluation, and NFR detail for a chain-top artifact feeding UX, architecture, and stories.

### Findings

- **Low — Technical depth is correctly separated but unusually large for the MVP stakes** (technical addendum overall) — This is justified by the portfolio's AI-engineering thesis, provided the addendum remains guidance and does not silently become a second mandatory requirements contract. *Fix:* keep substitutions explicitly allowed and have stories trace to observable PRD requirements rather than every implementation recommendation.

## Mechanical notes

- FR IDs are contiguous and unique: FR-1 through FR-20.
- The single primary journey has a named protagonist.
- No unresolved `[NOTE FOR PM]` callouts or inline `[ASSUMPTION]` tags appear; the absence of inline tags is itself the assumptions-roundtrip defect noted above.
- Glossary coverage is strong; add `Candidate schedule` and standardize `operational baseline` versus `operational schedule`.
- The PRD includes the expected essential spine for a launch-shaped portfolio MVP: thesis, goals/non-goals, user/job/journey, grouped FRs, cross-cutting NFRs, evaluation, metrics/countermetrics, governance, risks, future scope, deferred decisions, assumptions, and glossary.
- The technical addendum appropriately houses technology, transport, persistence, deployment, instrumentation, and workflow mechanisms, but its mandatory language should be treated as architecture guidance unless an observable PRD requirement requires the exact mechanism.
