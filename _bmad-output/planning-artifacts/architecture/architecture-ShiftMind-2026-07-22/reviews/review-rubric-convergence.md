# Architecture-Spine Convergence Verification

**Target:** `ARCHITECTURE-SPINE.md`  
**Reviewed:** 2026-07-22  
**Verdict:** **REMAINING HOLES**

The focused revisions resolve the major semantic conflicts from the prior gate:

- AD-7 now separates `AgentRun`, `ScheduleRun`, and `ApprovalRequest`; stored status types cannot be merged.
- AD-22 makes the candidate schedule version conditional on a feasible completed result; no-candidate terminal runs retain evidence without fabricating a schedule version.
- AD-12 uses a server-generated `attempt_id` and attempt-scoped non-success uniqueness, so distinct consequential attempts no longer collide on request correlation.
- AD-14 now persists an evidence reference plus source activity and restores exact route/scroll/focus; AD-15 explicitly discards provider thinking parts and allow-lists durable content.
- AD-17 now binds TLS for public/origin/database hops, encryption at rest, bucket public-access blocking, and CloudFront OAC.

Two concrete holes remain.

## 1. Queued work cannot reach the Rule's required timeout/failure outcomes

**Evidence:** AD-7 says application-owned wall-time exhaustion becomes `timed_out` and the PRD's bounded run includes total elapsed time. However:

- `AgentRun` permits `agent_queued -> agent_running|agent_cancelled` only (`ARCHITECTURE-SPINE.md:92-103`);
- `ScheduleRun` permits `solver_queued -> solver_running|solver_cancelled` only (`:104-118`).

An accepted run can remain queued beyond total elapsed time during capacity exhaustion or an unavailable worker. The state machine then cannot persist the mandated timeout. It likewise has no queued failure edge for an unrecoverable pre-lease failure after acceptance.

**Required closure:** Add the applicable `*_queued -> *_timed_out` transition(s), and either add `*_queued -> *_failed` with stable reasons or state that all pre-lease failures are validated before acceptance and therefore cannot occur. Fix which clock starts at acceptance versus lease so the timeout is executable and testable.

## 2. Node and Terraform exact patches remain neither current nor authoritative compatibility locks

**Evidence:** Stack marks Node `22.22.0` as an observed/planned build target to be pinned later and Terraform `1.15.5` as a verified planned seed (`ARCHITECTURE-SPINE.md:252-275`). Neither is currently committed in a toolchain/IaC constraint. As of this review, the supported Node 22 line has a later 22.22.3 patch ([Node releases](https://nodejs.org/en/about/previous-releases)), and HashiCorp lists Terraform 1.15.8 after 1.15.5 ([Terraform releases](https://releases.hashicorp.com/terraform/)). No compatibility evidence explains the older exact patches.

**Required closure:** Either update to verified-current patches or record the tested compatibility reason and commit the exact versions in authoritative toolchain files (`engines`/version file/container and Terraform `required_version`) before treating them as spine pins. A future implementation-gate promise does not yet satisfy the rubric's current-or-brownfield-lock requirement.

No additional gap was found in the focused areas of state-machine separation, no-candidate result ownership, audit-attempt uniqueness, evidence-return behavior, hidden-reasoning retention, or TLS/encryption.
