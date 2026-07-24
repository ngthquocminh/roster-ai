# Architecture-Spine Rubric Review

**Target:** `ARCHITECTURE-SPINE.md`  
**Reviewed:** 2026-07-22  
**Lens:** feature-altitude convergence for independently implemented epics  
**Verdict:** **NEEDS REVISION**

The spine has a strong paradigm and resolves most of the dangerous authority, durability, tenancy, idempotency, approval, evidence, deployment, and brownfield-migration seams. It is not yet a complete consistency contract. Five high-severity gaps can still produce source-incompatible or mutually incompatible epics: the run state machine is named but not closed, FR-14/FR-15 do not have enforceable payload contracts, Cognito self-registration is not prohibited, the required operational alarm/cost-control contract is absent, and MVP data-lifecycle behavior is deferred without a current portfolio rule.

Mechanical lint already passes (`reviews/lint.json`: zero findings). The findings below are semantic.

## Evidence reviewed

- `ARCHITECTURE-SPINE.md`, including AD-1 through AD-19, Stack, Structural Seed, Capability Map, and Deferred.
- Final PRD `prd.md`, especially FR-1 through FR-24, §§5–7, §9, and Deferred Product Decisions.
- Final technical addendum `addendum.md`, especially technology decisions, durable workflow, data model, AWS target, evaluations, and implementation sequence.
- UX companions `EXPERIENCE.md` and `DESIGN.md`.
- Brownfield manifests/locks and representative structure: `backend/pyproject.toml`, `backend/uv.lock`, `frontend/package.json`, `frontend/package-lock.json`, `backend/domain`, `backend/engine`, `backend/services`, `backend/store`, `frontend/src/api`, `frontend/src/components/ui`, and `frontend/src/hooks`.
- Official package/release indexes as of 2026-07-22 for planned pins.

## Rubric result

| Rubric test | Result | Assessment |
| --- | --- | --- |
| Fixes real divergence points for independently built epics | **Partial** | Authority, persistence, approval, tenancy, evidence, and API boundaries are strong; lifecycle edges, run-evidence/comparison schemas, operations, current retention, and inherited UI system remain divergent. |
| Every AD Rule is enforceable and prevents its stated divergence | **Partial** | Most Rules are testable. AD-7 claims a closed state machine without declaring legal transitions or terminal membership; AD-17 names CloudWatch/backups without the source-required alarm/cost contract. |
| Deferred contains nothing that can cause incompatible epics | **Fail** | Customer policy can wait, but current MVP retention/deletion and store-by-store lifecycle behavior cannot be wholly undecided. |
| Named technology verified/current or grounded in brownfield locks | **Partial** | Existing Python/frontend pins and most planned pins are grounded. Terraform and Node exact patches are neither current nor repository-locked; the table does not identify lock vs planned status per row. |
| Ratifies rather than contradicts brownfield code | **Pass with caveat** | The target correctly preserves the pure domain, `SchedulerEngine`, provider seam, generated client, TanStack Query, and repository transaction participation while acknowledging migration. It fails to ratify the existing shadcn/Tailwind/Radix UI system. |
| Covers FR-1 through FR-24 | **Partial** | All FR ranges appear in the capability map, but FR-1, FR-14, and FR-15 lack required enforceable details. A map entry is not coverage when the governing Rule omits the source contract. |
| Covers the UX companion | **Partial** | Peer surfaces, typed activities, evidence targeting, read-only data, and cache ownership land. The inherited UI system and the full safe return-to-origin contract do not. |
| Every feature-altitude dimension decided/deferred/open | **Partial** | Deployment, environments, infrastructure, authority, mutation, and workflow recovery are decided. Operations, current data lifecycle, product-state privacy, and some security details are incomplete. |

## High findings

### H-1 — AD-7 does not define a closed run state machine

**Evidence:** AD-7 (`ARCHITECTURE-SPINE.md:84-88`) enumerates state names, says application commands own “legal” compare-and-set transitions, and says terminal states are immutable. It never enumerates the legal edges, identifies the terminal-state set, assigns which commands may cause each edge, or distinguishes a solver/schedule-run state from an agent/approval workflow state.

**Why this fails the rubric:** The stated prevention is “contradictory retry, cancellation, terminal-state, and presentation behavior,” but separate API, worker, agent, and frontend epics can all comply with the prose while choosing incompatible graphs. For example, one can implement `queued -> cancelled`, another `queued -> cancellation_requested -> cancelled`; one can resume `approval_required` to `running`, another to `completed`; and a UI cannot derive whether `approval_required` is terminal, paused, or a different aggregate's state. The PRD requires exact visible distinctions and cancellation safety (FR-13/FR-16), so this is a real level-below divergence.

**Required resolution:** Put the transition table/diagram in the Rule or bind one named, versioned state-machine contract. Define initial, paused, and terminal states; command/event ownership; allowed cancellation edges; recovery/retry behavior; and whether `approval_required` belongs to `schedule_run`, `agent_run`, or a shared presentation projection. Add transition-matrix tests as the enforcement mechanism.

### H-2 — FR-14 immutable run evidence and FR-15 comparison are mapped but not contracted

**Evidence:** The PRD requires every run to retain exact immutable references to scenario inputs, active constraints, locks, solver configuration, relevant component versions, and result (`prd.md:158`), and requires comparison by affected worker, shift, role/task, interval coverage, overtime, cost/objective components, constraint status, and unresolved infeasibility (`prd.md:161`). AD-9 (`ARCHITECTURE-SPINE.md:96-100`) only says solver inputs/outputs are immutable. AD-11 (`:108-112`) only requires calculators for numerical claims and deltas. The capability map (`:299`) cannot supply the missing schema.

**Why this fails the rubric:** Independently built solver, evidence, Results, and provenance epics can omit different portions of the rerun tuple or return different comparison dimensions while each claiming immutable inputs and calculated deltas. That breaks reproducibility, the Results UX, and cross-epic contract generation.

**Required resolution:** Fix an application-owned `RunEvidence` manifest that binds all FR-14 references (including explicit absence/result status), and a versioned comparison projection that contains every FR-15 dimension with defined “not computed” semantics. Make Results, Chat comparison cards, evidence links, provenance, and reproducibility tests consume the same contracts.

### H-3 — The identity Rule does not prohibit Cognito public/self sign-up

**Evidence:** FR-1 requires public registration disabled and a self-registration attempt unable to create an account (`prd.md:113-114`). The addendum explicitly says “Public sign-up off” (`addendum.md:51`). AD-3 (`ARCHITECTURE-SPINE.md:60-64`) constrains BFF sessions, membership resolution, provisioning, and the one-user database invariant, but says nothing about Cognito user-pool self-registration.

**Why this fails the rubric:** A database membership constraint can deny application access but cannot prevent an extra authenticatable identity from being created in Cognito. An identity epic could enable Cognito self-sign-up yet still satisfy every written AD-3 sentence. This directly misses FR-1 and weakens the stated one-authenticatable-user boundary.

**Required resolution:** Amend AD-3 to require Cognito self/public sign-up disabled, prohibit any application session unless the subject maps to the sole active user/membership, and require sign-out/session revocation behavior. Gate it with an automated registration-denial and unmapped-subject test.

### H-4 — Operations are named, but the required alarm and cost-control contract is absent

**Evidence:** PRD §6.6 requires AWS cost, queue health, budget cutoff/failure, tool denial/timeout, guardrail denial, approval age/outcome, solver duration/failure, evaluation regression, audit-write failure, model failure, and telemetry-export health to be observable and alertable (`prd.md:284`). The addendum requires CloudWatch logs/alarms, AWS Budgets, and cost-allocation tags (`addendum.md:52`, `:171`). AD-17 (`ARCHITECTURE-SPINE.md:144-148`) names CloudWatch, backups, drills, deploys, and rollback but fixes none of those operational signals, alarms, Budgets, or tagging ownership. AD-16 also omits the PRD's required evaluation-report identity tuple (`prd.md:305`).

**Why this fails the rubric:** Infrastructure, agent, worker, solver, audit, and evaluation epics can each assume another epic owns these signals. A deployed stack could satisfy AD-17 while lacking the alerts and cost controls the authoritative inputs make part of the MVP.

**Required resolution:** Bind an application/infrastructure-owned operational signal catalogue with the source-required signals, CloudWatch alarm ownership, Budgets, cost-allocation tags, and alarm proof tests. Extend AD-16 so every report binds dataset, evaluator, model, prompt, tool, policy, and application versions; explicitly ratify Pydantic Evals/pytest/Playwright from the addendum or explicitly supersede that tool choice.

### H-5 — Deferred data lifecycle is too broad for independently built MVP epics

**Evidence:** Deferred (`ARCHITECTURE-SPINE.md:316`) postpones “Retention, deletion, residency, regulatory WORM” as one unit. The PRD permits customer-specific policy to wait, but requires the portfolio's current settings and limitations to be documented (`prd.md`, Data Governance and Deferred Product Decisions). The current spine provides no MVP rule for PostgreSQL product/audit rows, S3 evidence, RDS backups, CloudWatch logs, hosted Logfire, or evaluation artifacts.

**Why this fails the rubric:** Residency and regulatory WORM can wait, but current retention and deletion behavior shape foreign keys, object lifecycle, backups, audit immutability, privacy disclosures, and restore semantics now. Separate epics can choose indefinite retention, automatic expiry, or cascading deletion incompatibly. “No customer contract” does not remove the need for one portfolio behavior.

**Required resolution:** Decide the portfolio defaults per record-of-truth now: whether user deletion exists (the MVP likely has none), current retention/lifecycle settings, backup retention, audit/evidence non-deletion behavior, and how those limitations are disclosed. Keep only customer-specific duration, export/erasure, residency, and regulatory WORM policy deferred.

## Medium findings

### M-1 — The spine does not ratify the inherited UI system or make companion precedence enforceable

**Evidence:** The UX companion fixes React/Vite with shadcn/ui, Tailwind, Radix, React Router, and TanStack Query and says the UI system is inherited unless a ShiftMind delta is named (`EXPERIENCE.md:14`). The brownfield manifest and `frontend/src/components/ui` confirm that system. The Stack lists React, Router, Query, TypeScript, and Vite but omits shadcn, Tailwind, and Radix. Frontmatter calls the UX files “companions,” and AD-14 says it binds “the UX companion,” but no Rule says those documents are normative or that new UI epics must extend the existing component/token system.

**Impact:** Independent Chat, Scenario Data, Runs, and Results epics can introduce incompatible primitives, tokens, accessibility behavior, and styling frameworks without violating the spine.

**Required resolution:** Add a concise UI-system convention ratifying the existing shadcn/Tailwind/Radix primitives and naming `EXPERIENCE.md` and `DESIGN.md` as normative for behavior/accessibility and visual deltas. Do not duplicate their detail.

### M-2 — Two exact stack pins are not current or brownfield-locked, and row provenance is ambiguous

**Evidence:** Stack (`ARCHITECTURE-SPINE.md:175-198`) says some rows are repository locks and others are planned, but does not label individual rows. `frontend/package-lock.json` and `backend/uv.lock` ground the existing library pins, while neither Node nor Terraform has a repository toolchain lock. Official indexes on 2026-07-22 show Node 22 remains a supported LTS line but its latest 22.x patch is 22.22.3, not 22.22.0 ([Node releases](https://nodejs.org/en/about/previous-releases)); HashiCorp lists Terraform 1.15.8 after 1.15.5 ([Terraform releases](https://releases.hashicorp.com/terraform/)). The memlog's claim that Terraform 1.15.5 is “latest stable” is therefore stale at review time.

**Impact:** An exact pin can be deliberately older when tested, but these two are neither identified as compatibility locks nor present in toolchain files. Builders cannot tell whether to preserve, update, or reverify them.

**Required resolution:** Add a `Status/source` column (`brownfield lock`, `validated compatibility pin`, `planned verified seed`) and a verification date/link. Update current planned patches or document the compatibility reason, then put Node and Terraform into authoritative toolchain/lock files at their implementation gate.

### M-3 — “Never hidden reasoning” applies to audit/provenance, not product-state retention

**Evidence:** The PRD says the product stores concise decision summaries and evidence, not private chain-of-thought (`prd.md:239`). AD-12 (`ARCHITECTURE-SPINE.md:118`) says audit/provenance envelopes contain “never hidden reasoning,” and AD-19 prevents framework messages becoming product contracts. Neither prohibits an AgentRuntime adapter or checkpoint store from persisting provider reasoning/message parts in product/workflow state.

**Impact:** Agent-runtime and persistence epics can make incompatible privacy and resumption choices, and one can retain data explicitly excluded by the product contract.

**Required resolution:** Fix the persisted-content allow-list: user-visible messages, structured tool calls/results, application summaries, checkpoint metadata, and required evidence only; never request, store, expose, or treat hidden reasoning as provenance. Define raw provider-message retention as absent unless a later explicitly governed diagnostic mode permits sanitized content.

### M-4 — The evidence-return contract is only partially represented

**Evidence:** AD-14 (`ARCHITECTURE-SPINE.md:130`) says evidence links preserve “chat return context.” The UX contract requires return to the exact originating Chat claim **or Results element**, restoration of scroll/focus, and an app-owned opaque origin key rather than an arbitrary redirect (`EXPERIENCE.md:98`, `:148-161`).

**Impact:** Chat, Results, and Scenario Data epics can invent incompatible return URL/state shapes; a permissive implementation can accept open redirects or model-authored navigation state.

**Required resolution:** Amend AD-14 to bind the app-owned origin-key contract for Chat and Results, prohibit arbitrary/model-authored redirect URLs, and require the same authorized locator/return contract across all evidence surfaces.

## AD enforceability notes

The following Rules are particularly strong and directly testable:

- AD-1/AD-2 fix inward dependencies and the model/application/CP-SAT authority partition.
- AD-4 fixes one immutable normalized projection, prohibits every scenario-source mutation surface, and imposes an enforceable Gate A ordering.
- AD-5 fixes a complete capability-module declaration contract and deny-by-absence policy.
- AD-6/AD-8 fix persist-before-acknowledgement, leases/fencing, SSE replay, and database-backed idempotency.
- AD-9/AD-10 fix immutable versions, stale failure, exact approval binding, and atomic baseline promotion.
- AD-11/AD-12 fix version-bound evidence, numerical grounding, record-of-truth separation, and authoritative audit continuity.
- AD-13/AD-14 fix one OpenAPI client and one remote-state owner.
- AD-15/AD-19 isolate untrusted content, model outage, and the new agent framework boundary.
- AD-17/AD-18 fix the major AWS topology and PostgreSQL-first coordination choice.

Apart from H-1, the main enforceability weakness is wording such as “where practical” in AD-3's non-enumeration rule. Security behavior should have deterministic exception criteria; otherwise each endpoint can decide that disclosure is “practical.”

## FR-1 through FR-24 coverage

| FR range | Status | Notes |
| --- | --- | --- |
| FR-1–FR-3 | **Partial** | BFF/session/site/RLS/one-user scope is strong; public self-registration prohibition is missing (H-3). |
| FR-4–FR-8 | **Covered** | Durable messages/events, grounded inspection, refusal policy, evidence, and model-only outage containment are fixed. |
| FR-9–FR-11 | **Covered** | Typed governed capabilities, reversible versioned drafts, and CP-SAT-only accepted schedule construction are fixed. |
| FR-12–FR-13 | **Partial** | Durability and bounded work are strong; legal lifecycle transitions are not closed (H-1). |
| FR-14–FR-15 | **Partial** | Immutability and calculators are present, but the mandatory manifest and comparison dimensions are absent (H-2). |
| FR-16 | **Partial** | Idempotency, leases, fencing, and cooperative cancellation are strong; exact transition semantics remain open (H-1). |
| FR-17–FR-19 | **Covered** | Candidate/baseline separation, exact-action approval, atomic promotion, and immutable prior versions converge. |
| FR-20–FR-21 | **Covered** | The full authoritative audit/provenance envelope and non-success outcomes are now explicit. |
| FR-22–FR-24 | **Covered** | Fixture-only catalogue, no mutation path, one projection, viewer/agent parity, deterministic windows, and exact-target lookup converge. |

## Feature-altitude dimension audit

| Dimension | Status | Decision or gap |
| --- | --- | --- |
| Paradigm and boundaries | **Decided** | Hexagonal modular monolith; separately runnable API/worker; owned ports and inward dependencies. |
| Deployment | **Decided** | CloudFront/private SPA S3, ALB, ECS API/worker, RDS, evidence S3, ECR. |
| Environments | **Decided** | Local developer, ephemeral CI, and one production-shaped portfolio AWS environment; customer staging/production correctly deferred. |
| Infrastructure/provider | **Decided** | Terraform, GitHub Actions OIDC, Cognito, AWS managed services; planned version provenance needs correction (M-2). |
| Operations | **Incomplete** | Logs/traces are separated, but required alarms, budgets, tags, signal ownership, and evaluation identity are absent (H-4). |
| Data ownership | **Mostly decided** | PostgreSQL product/audit, independent immutable EvidenceSnapshot, S3 large evidence, CloudWatch/Logfire/evals separated; current lifecycle and persisted model-content policy remain open (H-5, M-3). |
| State mutation | **Decided** | Command handlers own units of work; expected versions, idempotency, immutable proposals/schedules, exact approval, and atomic promotion. |
| Workflow state | **Incomplete** | State vocabulary exists, but the graph/aggregate ownership is not closed (H-1). |
| Security/privacy | **Incomplete** | Site authority, RLS, BFF/PKCE/CSRF, least privilege, secrets, and untrusted content are strong; self-sign-up and product-state reasoning retention are not fixed (H-3, M-3). TLS/at-rest encryption should also be stated or explicitly inherited from the AWS baseline rather than assumed. |
| Recovery | **Decided at MVP mechanism level** | Durable jobs, leases/fencing, replay, cancellation, backups, restore drills, health-gated deploy, schema-compatible rollback. Numeric customer RTO/RPO is appropriately deferred. |
| UX/system contract | **Incomplete** | Main state/evidence/authority seams land, but inherited UI-system and safe return-origin contracts remain open (M-1, M-4). |
| Evaluation/release | **Incomplete** | Deterministic-first blocking gates land; report identity and named evaluation/tooling contract do not (H-4). |

## Brownfield ratification assessment

The spine is appropriately a target contract rather than a false description of today's runtime. It preserves the codebase's strongest seams: pure scheduling domain dataclasses, the `SchedulerEngine` port and CP-SAT implementation, provider-neutral LLM translation, service/repository separation, repository participation in caller transactions, generated OpenAPI client, TanStack Query ownership, and deterministic tests. It explicitly treats SQLite, mutable fixture paths/overrides, the in-process executor, uppercase four-state run statuses, missing tenancy, and hand-maintained result types as migration work.

No load-bearing AD contradicts those good seams. The principal ratification omission is the existing UI component/style system (M-1). The Structural Seed's migration warning is useful, but downstream planning must still enforce the prerequisite order in AD-4 so governed agent epics do not build on the disposable SQLite/thread-worker lifecycle.

## Final disposition

Do not finalize the spine until H-1 through H-5 are resolved. M-1 through M-4 are compact amendments to existing Rules/Conventions rather than reasons to change the paradigm. After amendment, rerun lint and this rubric with special attention to the state transition table, exact FR-14/FR-15 contracts, Cognito registration denial, operational alarms/cost controls, store-specific lifecycle defaults, and the UX companion's normative status.
