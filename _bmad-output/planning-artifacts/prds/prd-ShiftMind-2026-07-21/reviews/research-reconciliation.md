# Technical Research Reconciliation Review

**Source:** `technical-production-shaped-agent-architecture-for-shiftmind-research-2026-07-21.md`  
**Reviewed:** `prd.md` and `addendum.md`  
**Verdict:** **Pass with targeted fixes.** The PRD captures the research unusually well: bounded autonomy, exact approval, deterministic scheduling, tenant-aware design, durable work, provenance, authoritative audit, privacy, evaluation, AWS delivery, and Logfire's non-authoritative role are all present. Two material gaps should be fixed before finalization, followed by four smaller clarifications.

## Findings

### R1 — High — FR-2 does not fully enforce the promised single-user MVP

**Location:** PRD §3.1, §4.1 `FR-1`/`FR-2`, §2.2; Addendum §9 milestone 1.

The PRD repeatedly promises one active user, but `FR-2` only prevents a second **active site membership**. That still permits a second active `app_user` or authenticatable external identity with no membership, and it does not directly express the original requirement that only one person can chat with the agent. The technical research called for one site, one user, one planner membership, with application configuration and a database invariant preventing another active user.

**Recommended product-level fix:** Revise `FR-2` to require exactly one active application user and one active planner membership in the portfolio environment. Attempts to provision, activate, authenticate, or authorize a second active user must fail closed. Keep the implementation mechanism in the addendum.

**Recommended addendum fix:** In §5 or §9, state that both the active-user and active-membership limits are enforced by application policy plus a database invariant, rather than only by disabled public registration.

### R2 — High — Portfolio backup/restore was unintentionally deferred with SaaS resilience

**Location:** PRD §6.6 and §8.1; Addendum §7, especially the sentence beginning “Before accepting customers”.

The research recommended a small single-AZ RDS instance **with automated backups and a tested restore rehearsal** for the portfolio. The addendum currently says that “RDS Multi-AZ/backups” are to be validated before accepting customers, which reads as though backups themselves are optional in the portfolio environment. That conflicts with the PRD's claim that authoritative audit and durable workflow state are robust and with the AWS failure-proof narrative.

**Recommended product-level fix:** Add a technology-neutral NFR to §6.6: authoritative product, workflow, and audit data must be covered by an automated backup and a demonstrated restore procedure before MVP completion. Do not invent an unsupported customer RPO/RTO.

**Recommended addendum fix:** Split the concerns: portfolio requires automated RDS backups and one restore drill; external production later requires explicit RPO/RTO, Multi-AZ, customer-grade retention, and recurring restore exercises.

### R3 — Medium — The authoritative audit requirement should say append-only, not merely “not normal to update”

**Location:** PRD `FR-20` and §9; Addendum §5–§6.

`FR-20` correctly requires unsampled business evidence, and the addendum correctly describes an append-only ledger and application roles that cannot update/delete/truncate it. The PRD's policy language, however, only says update and deletion “are not normal application operations.” That is weaker than the research invariant and leaves ambiguity about whether ordinary product behavior may rewrite historical evidence.

**Recommended product-level fix:** State that authoritative audit records are append-only and cannot be edited or deleted through normal product or agent capabilities. Administrative retention handling, if later required, must be separately authorized and itself auditable. This preserves honest language without claiming absolute immutability.

### R4 — Medium — “Immutable run evidence” lacks a concrete write-once mechanism in the addendum

**Location:** PRD `FR-13` and §9; Addendum §2 Evidence, §5, and §7.

The PRD requires immutable run evidence, while the addendum describes checksummed S3 snapshots and mentions future S3 Object Lock only for stronger WORM guarantees. A checksum detects change but does not prevent object overwrite or deletion. The addendum should explain how the MVP satisfies `FR-13` without overstating WORM properties.

**Recommended addendum-only fix:** Require unique content/version-addressed object keys, persisted checksum and S3 version ID, no overwrite path, and least-privilege runtime permissions. Clarify that this is application-level append-only evidence with tamper detection, not regulatory WORM storage; Object Lock remains a later option.

### R5 — Medium — Monitoring requirements omit agent-control and evaluation-regression signals

**Location:** PRD §6.6 and §7; Addendum §6–§8.

The PRD requires alerts for AWS cost, queue health, audit-write failure, model failure, and telemetry-export health. The research also treated agent failures/cutoffs, tool denial/timeouts, guardrail denials, approval outcomes/age, solver duration, and evaluation regressions as core operational signals. Given the user's explicit monitoring requirement, these should not be left implicit in Logfire's general capability.

**Recommended product-level fix:** Extend §6.6 with technology-neutral observability requirements for agent outcome/cutoff, tool denial/timeout, guardrail denial, approval state/age, solver duration, and evaluation regression. Not every metric needs an alert; the product should define a small MVP dashboard and alerts for conditions that threaten correctness or availability.

**Recommended addendum fix:** Map these signals to CloudWatch/Logfire while preserving PostgreSQL audit as the authority.

### R6 — Medium — Evaluation evidence is not explicitly reproducible by dataset and configuration version

**Location:** PRD §7 and §9; Addendum §6 and §8.

The PRD has strong deterministic-first suites and release-blocking gates. It captures model/prompt/tool/policy versions in audit, and the addendum says datasets are version controlled. It does not explicitly require each evaluation result to identify the dataset revision, evaluator revision, model/provider configuration, prompt/tool/policy versions, and application version. Without this, a “90% tool-selection” result is less reproducible and less persuasive as portfolio evidence.

**Recommended product-level fix:** Add one sentence to §7 requiring every release evaluation report to bind its results to the evaluated dataset/evaluator and agent configuration versions.

**Recommended product/addendum clarification:** Reviewed production/demo failures should be promotable into sanitized regression cases. Any online evaluator is sampled/advisory; deterministic authorization, approval, isolation, invariant, grounding, and audit gates remain authoritative.

## Verified alignment — no change required

- **Guardrails:** `FR-6`, `FR-8`–`FR-18`, §5, and §6 implement the research's “model proposes; application disposes” boundary without polluting product requirements with framework mechanics.
- **Approval integrity:** Exact candidate/baseline/parameter/version binding, expiry, one-time use, stale rejection, and atomic publication are captured.
- **Decision provenance:** `FR-19`, `FR-20`, and §9 cover evidence, policy outcomes, approvals, versions, effects, and the no-chain-of-thought boundary.
- **Recovery/idempotency:** `FR-11`–`FR-15`, `FR-18`, and §6.2 cover browser/API/worker interruption, reconnect, cancellation, retry, lease recovery, and duplicate prevention.
- **Privacy:** §6.1 and §9 correctly minimize both model-provider and observability-provider content; the addendum explicitly disables Logfire content capture and allow-lists metadata.
- **Logfire:** Its role is correctly constrained to hosted, sanitized, optional observability/evaluation visualization. It is neither self-hosted nor authoritative and its outage cannot block product behavior.
- **AWS:** The target services, least-privilege roles, secrets, reproducible infrastructure, rollback, cost controls, and portfolio-versus-customer boundary are consistent, subject to R2.
- **SaaS boundary:** The MVP defers onboarding, roles, billing, integrations, and dedicated stacks while preserving organization/site/membership and pooled isolation foundations.
- **Assumptions/deferred decisions:** Self-approval, internal-only publication, synthetic/permitted data, desktop web, retention, integrations, residency/compliance, SLOs, and future role permissions are explicitly marked rather than silently assumed.

## Suggested resolution order

1. Fix `FR-2` and the matching addendum invariant.
2. Restore portfolio backup/restore requirements and separate them from Multi-AZ/customer SLO decisions.
3. Tighten append-only audit and evidence-snapshot semantics.
4. Add the missing monitoring signals.
5. Bind evaluation reports to versioned datasets, evaluators, and agent configuration.

