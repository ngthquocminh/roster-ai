# Final Architecture-Spine Rubric Review

**Target:** `ARCHITECTURE-SPINE.md`  
**Reviewed:** 2026-07-22  
**Intent:** re-review after rubric-gate amendments  
**Verdict:** **NEEDS REVISION — substantially improved, with two remaining high-severity contract conflicts**

The revision resolves most prior omissions. It now fixes canonical cross-epic schemas and hashes, FR-15 comparison fields, persisted-event/SSE cursor behavior, aggregate owners and transaction bundles, RLS/runtime roles, mixed-version deployment, operational alarms and cost controls, current portfolio retention, Cognito self-sign-up, evaluation-report identity, and the one-way brownfield cutover. Those additions materially improve convergence.

The principal unresolved issue is the attempted closure of AD-7: the new graph conflates optimization-run state with agent/approval workflow state and is still incomplete for cancellation and queue-time outcomes. That conflict propagates into AD-22, whose `complete-compute` bundle requires a schedule version for every terminal result despite the ER model and PRD allowing infeasible/timed-out/cancelled/failed runs without candidates. These are architecture-level blockers because independently built worker, governance, Results, and frontend epics would implement incompatible lifecycle and result semantics.

Mechanical lint was rerun against the updated spine and passes with zero findings.

## Prior-finding resolution

| Prior finding | Final status | Assessment |
| --- | --- | --- |
| H-1: AD-7 was vocabulary, not a closed graph | **Not resolved; fix introduced conflict** | A graph now exists, but it mixes approval with solver-run lifecycle, omits valid queued/cancellation-race outcomes, and conflicts with AD-22 ownership. See F-1. |
| H-2: FR-14/FR-15 contracts absent | **Partially resolved** | `RunSnapshotV1` and `ComparisonV1` now fix inputs and all comparison dimensions. The immutable result/output side and candidate-optional atomic bundle remain inconsistent. See F-2. |
| H-3: Cognito public sign-up not prohibited | **Mostly resolved** | AD-17 now disables public/self sign-up. FR-1 sign-out/session invalidation remains implicit rather than contracted. See M-2. |
| H-4: alarm, cost, and evaluation identity absent | **Resolved** | AD-17 adds Budgets/tags, AD-24 owns the required alarms, and AD-16 binds the report version tuple. |
| H-5: current portfolio lifecycle deferred | **Resolved** | AD-17 fixes no in-product delete, persistence through teardown, RDS backup retention, and CloudWatch retention; Deferred now limits itself to customer policy. |
| M-1: inherited UI system not ratified | **Open** | The Stack/Conventions still omit shadcn/Tailwind/Radix and do not make the two UX companions normatively binding. See M-3. |
| M-2: stack provenance/currentness ambiguous | **Partially resolved** | The new Status column distinguishes repository locks from planned seeds. Node and Terraform remain stale, unlocked exact patches. See M-4. |
| M-3: hidden-reasoning product retention open | **Open** | AD-12 excludes it only from audit/provenance; AD-19 still lacks a persisted-content allow-list. See M-5. |
| M-4: evidence return-to-origin partial | **Open** | AD-14 remains Chat-only and does not require the app-owned opaque origin key or prohibit arbitrary/model-authored redirects. Included in M-3. |

## High findings

### F-1 — AD-7 now closes the wrong aggregate and still omits legal outcomes

**Evidence:** AD-7 (`ARCHITECTURE-SPINE.md:84-106`) labels one “run” graph and includes:

- `running -> approval_required: exact action proposed`;
- `approval_required -> running: decision recorded and resume`;
- `approval_required -> cancelled: rejected or expired`;
- only `completed` or `failed` may win a race after `cancellation_requested`.

AD-22 (`:192-196`) separately says conversation owns agent runs, scheduling owns runs/schedule versions, and governance owns approvals. The PRD requires optimization to produce a feasible candidate that remains separate from the baseline, followed by a distinct approval/promotion decision (FR-17–FR-19). The UX likewise treats run outcome, approval request, rejection/expiry, and promotion outcome as distinct records.

**Conflict:** If AD-7 describes a scheduling/solver run, approval cannot precede its completion: a feasible candidate must exist before exact baseline-promotion approval can be bound. A rejected or expired promotion also must not turn the already computed run into `cancelled`. If AD-7 instead describes an agent/workflow run, AD-22 assigns ownership ambiguously and its `complete-compute` bundle operates on a different child aggregate without a named state machine.

The graph is also not complete under its own budget/cancellation rule:

- a run can exhaust total wall time while still `queued`, but `queued -> timed_out` is absent;
- an acceptance/configuration/lease failure has no `queued -> failed` edge;
- a solver can return infeasible or time out after cancellation is requested, but only `completed` and `failed` may win that race;
- no retry command/result semantics are attached to terminal states despite FR-16 being in `Binds`.

**Why this blocks finalization:** API, worker, governance, activity-stream, and UI epics cannot derive one correct status owner or graph. The diagram is enforceable, but it enforces behavior that contradicts the product approval boundary.

**Required resolution:** Split and name the aggregates:

1. a `ScheduleRun` graph for queued/running/cancellation/terminal solver outcomes, with every legal edge and terminal set; and
2. an `AgentRun` or `GovernanceFlow` graph/projection for paused approval, rejection/expiry, resumption, and promotion outcome.

Keep a completed schedule run immutable while approval proceeds against its candidate. If the UI needs a combined `approval_required` state, define it as an application-owned projection, not mutation of the completed schedule run. Add transition-matrix tests and state which aggregate each `ActivityItemV1` status represents.

### F-2 — AD-22 requires a schedule version for terminal runs that must have no candidate

**Evidence:** AD-22 (`ARCHITECTURE-SPINE.md:196`) fixes `complete-compute = terminal run + schedule version + evidence refs + event`. The ER diagram models `SCHEDULE_RUN ||--o| SCHEDULE_VERSION`, correctly making the schedule version optional. AD-7 says infeasible and timed-out runs never contain a promotable candidate; FR-13/FR-14 also require immutable results for infeasible, timed-out, cancelled, and failed runs.

AD-20's `RunSnapshotV1` (`:180-184`) now fixes the full accepted input manifest, but the canonical contract set has no `RunOutcomeV1` or equivalent immutable output/result reference. `ComparisonV1` applies only when a candidate/baseline comparison exists.

**Conflict:** An infeasible/timed-out/cancelled/failed completion cannot satisfy AD-22 without either fabricating an empty `schedule_version` or violating the fixed atomic bundle. Conversely, omitting the version violates AD-22 even though it agrees with AD-7 and the ER model. The source requirement that every run retain its result remains indirect rather than canonical.

**Required resolution:** Branch the completion bundle by outcome:

- feasible candidate: terminal run + immutable `RunOutcomeV1` + candidate schedule version + evidence refs + event;
- no candidate: terminal run + immutable `RunOutcomeV1`/diagnosis + evidence refs + event, with no schedule version.

Make the run reference its immutable input snapshot and immutable outcome explicitly. Define which terminal outcomes may own a candidate and comparison; retain “not computed” fields only where the source UX permits them.

## Medium findings

### M-1 — New audit uniqueness can collapse distinct consequential attempts

**Evidence:** AD-12 (`ARCHITECTURE-SPINE.md:132-136`) uses `(site_id, request_id, outcome)` as the uniqueness key for denied, stale, failed, and cancelled consequential attempts. The same envelope carries tool and approval identifiers because one request/agent turn can contain more than one proposed or evaluated action.

**Risk:** Two distinct denied tool calls, policy evaluations, or consequential attempts sharing one request correlation and outcome would collide, losing one authoritative audit event. That contradicts FR-21's requirement to record every consequential attempt. `request_id` is correlation, not necessarily action-attempt identity.

**Required resolution:** Use a stable action-attempt/effect identity in the uniqueness key—such as `action_attempt_id`, tool-call ID, approval-decision ID, or a derived idempotency/effect key—plus outcome. Keep request ID as correlation only. Add a test with two denied consequential attempts in one request/agent run.

### M-2 — FR-1 sign-out and server-side session invalidation remain implicit

**Evidence:** AD-3/AD-17 now fix PKCE, BFF sessions, current-membership resolution, and self-sign-up disabled, but no Rule states what sign-out invalidates. FR-1 explicitly requires sign-in/sign-out and rejection without a valid application session.

**Risk:** Identity and frontend epics can choose incompatible behavior: deleting only the browser cookie, revoking the opaque application session, or also revoking/ending provider tokens. Cookie-only logout may leave a server session reusable if the cookie is recovered.

**Required resolution:** State that sign-out invalidates the opaque server-side application session before clearing the cookie, and define whether provider refresh/access tokens are revoked or merely become unreachable. Add replay-after-sign-out coverage.

### M-3 — UX companion inheritance and safe evidence return are still not fixed

**Evidence:** `EXPERIENCE.md` declares the existing shadcn/ui, Tailwind, and Radix system inherited and requires evidence return to either an exact Chat claim or Results element via an app-owned origin key, never an arbitrary redirect. The updated Stack and Conventions still omit the UI system. AD-14 (`ARCHITECTURE-SPINE.md:144-148`) still mentions only “chat return context.” Frontmatter lists the UX files as companions but does not state normative precedence for independently built epics.

**Risk:** UI epics may introduce incompatible component/token systems or competing return URL/state contracts; a permissive evidence implementation can accept model-authored or open redirect destinations.

**Required resolution:** Add one UI convention ratifying shadcn/Tailwind/Radix and making `EXPERIENCE.md`/`DESIGN.md` normative for behavior/accessibility/visual deltas. Extend AD-14 to require an authorized app-owned opaque origin key for Chat and Results and prohibit arbitrary/model-authored redirect URLs.

### M-4 — Node and Terraform exact patches remain neither current nor validated locks

**Evidence:** The Status column is a good improvement, but Node `22.22.0` is explicitly “not repository-pinned” and Terraform `1.15.5` is only a planned seed (`ARCHITECTURE-SPINE.md:231-254`). As of 2026-07-22, the supported Node 22 line has a later 22.22.3 patch ([Node releases](https://nodejs.org/en/about/previous-releases)), and HashiCorp lists Terraform 1.15.8 after 1.15.5 ([Terraform releases](https://releases.hashicorp.com/terraform/)). No compatibility rationale grounds the older exact patches.

**Required resolution:** Update planned patches or label a tested compatibility reason. Pin Node and Terraform in authoritative toolchain files at their implementation gates. A deliberately selected supported major/minor is fine; an unexplained stale exact patch is not a verified-current seed.

### M-5 — Product/workflow persistence still lacks a hidden-reasoning/content-retention rule

**Evidence:** AD-12 says audit/provenance never contains hidden reasoning. AD-19 prevents framework messages/checkpoints from becoming product contracts and requires owned-message translation. Neither Rule prohibits the adapter/checkpoint store from persisting provider reasoning/message parts as opaque product/workflow state. The PRD says the product stores concise decision summaries and evidence, not private chain-of-thought.

**Required resolution:** Fix a persisted-content allow-list: user-visible messages, structured tool calls/results, application summaries, required checkpoint metadata, and evidence references. Explicitly prohibit requesting, storing, exposing, or treating hidden reasoning as provenance. Raw provider messages should be absent unless a later governed diagnostic mode explicitly authorizes sanitized retention.

### M-6 — Encryption and TLS remain an undecided security subdimension

**Evidence:** AD-17/AD-23 strongly decide private networking, RLS, least privilege, secrets, and create-only S3 behavior. No Rule or Deferred entry fixes browser-to-edge TLS, CloudFront-to-ALB origin protocol, service-to-RDS TLS, or encryption of RDS/S3/backups and their key ownership. The addendum's Route 53/ACM edge does not appear in the spine.

**Risk:** Separate edge, ECS, RDS, S3, and backup epics can make incompatible security assumptions. `Secure` cookies do not by themselves enforce encrypted origin hops or data-at-rest policy.

**Required resolution:** Add a terse AWS security convention: TLS at the public edge and to origins/data services; provider-managed or customer-managed encryption choice for RDS, backups, and S3; public-access blocks for both buckets; and key/rotation ownership. If provider defaults are intentionally accepted for the portfolio, state that explicitly and give the pre-pilot revisit trigger.

## Rubric result after revision

| Rubric test | Result | Final assessment |
| --- | --- | --- |
| Real divergence points fixed | **Partial** | Canonical contracts, ownership, SSE, RLS, deployment, operations, and cutover are now strong. Run/approval lifecycle and candidate-optional completion remain divergent. |
| Every AD enforceable and prevents stated divergence | **Partial** | New AD-20–AD-25 are mostly enforceable. AD-7 is now explicit but contradicts approval semantics; AD-22 contradicts candidate-optional outcomes; AD-12's non-success uniqueness is too coarse. |
| Deferred safe | **Pass** | Customer policy, scaling, topology, roles, integrations, and distributed technology choices now have appropriate triggers; current portfolio lifecycle is no longer deferred. |
| Technology verified/current or brownfield-grounded | **Partial** | Status provenance is clear and most pins are sound. Node/Terraform exact patches remain unexplained stale seeds. |
| Brownfield ratification | **Pass with one omission** | AD-25 cleanly resolves legacy SQLite/status migration and preserves good domain/solver/client seams. Existing UI-system ratification remains absent. |
| FR-1 through FR-24 | **Partial** | Comparison and most former gaps are covered. FR-13/FR-16 lifecycle semantics, FR-14 result ownership, and FR-1 logout remain incomplete. |
| UX companion | **Partial** | Typed activities, projections, statuses, accessibility gate, and evidence targets land; UI-system inheritance and safe Results/Chat return origin do not. |
| Feature-altitude dimensions | **Partial** | Deployment, environments, infrastructure, operations, data ownership, mutation, and recovery are now well covered. Workflow lifecycle and encryption/TLS remain incomplete; product-state content privacy remains open. |

## What is now strong

- AD-20 provides the missing single contract authority, full FR-15 comparison shape, canonical hashing, and one scheduling-time model.
- AD-21 removes SSE cursor/envelope/proxy divergence.
- AD-22 usefully assigns aggregate owners and names cross-owner atomic bundles, once the completion/approval corrections above are made.
- AD-23 gives RLS, connection-context, lease-selection, and create-only evidence behavior executable enforcement.
- AD-24 fixes expand/migrate/contract deployment and assigns the PRD-required operational alarms.
- AD-25 resolves the brownfield migration honestly: governed history starts fresh, the two status vocabularies never coexist, and the unrecoverable thread-worker path is removed.
- AD-16/AD-17 now cover evaluation identity, Budgets/tags, current portfolio lifecycle, backups, and log retention.

## Final disposition

Resolve F-1 and F-2 before finalizing; both affect the core journey and would otherwise force incompatible worker, approval, evidence, and UI implementations. M-1 through M-6 are targeted amendments to existing Rules/Conventions and do not require a paradigm change. After those corrections, the spine should be close to a passing feature-altitude consistency contract.
