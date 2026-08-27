# Review — Brownfield Claim Verification (versions/reality-check lens)

**Target:** `_bmad-output/planning-artifacts/architecture/architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md`
**Lens:** every committed brownfield claim must be reality-checked against the actual repo, not asserted from training data or stale belief. This spine names no new tech (stack inherited), so the check is entirely against `backend/` source.

## Verdict

All eight brownfield claims verified true against the current codebase. No contradiction found. One load-bearing item the spine itself flags as "open" was fully verifiable right now with the files already in scope, and verification confirms the convention is compatible — the spine should not have left it open.

## Findings

### 1. [medium] Open Question #2 (persisted_event stream CHECK vs. conversation-stream convention) was resolvable now, not deferred to Story 4.3

The spine's Open Questions section says: *"the exact CHECK arms must be verified against `schema.py` at Story 4.3 creation before the promotion event shape is frozen."* But `schema.py` already exists today and the answer is available now.

`backend/adapters/postgres/schema.py:328-334`, constraint `ck_persisted_event_stream_owner`:

```
(conversation_id IS NOT NULL AND schedule_run_id IS NULL AND stream_id = conversation_id) OR
(schedule_run_id IS NOT NULL AND conversation_id IS NULL AND stream_id = schedule_run_id)
```

This permits exactly two arms, keyed only on `conversation_id`/`schedule_run_id`. `agent_run_id` (line 319, nullable FK to `agent_run`) is **not** part of the CHECK at all — it can be set freely alongside either arm. So the spine's Consistency Convention — *"approval lifecycle events ride the conversation stream anchored to the paused agent run (`stream_id = conversation_id`, `agent_run_id` set)"* — satisfies the first arm cleanly (conversation_id set, schedule_run_id null, stream_id = conversation_id, agent_run_id set independently). **The convention is compatible with the CHECK as written today.** This is a real, present-tense verifiable fact, not a Story-4.3-time unknown. Recommend either closing this Open Question now (with this evidence) or explicitly noting it was checked and re-flagging only if the CHECK is expected to change before 4.3.

### 2. [low] `policy_version` constant attribution checks out including its origin story

`backend/application/capabilities/registry.py:11`: `POLICY_VERSION = "one-user-mvp-v1"`. `git log` on that file traces the constant to commit `05a9094 feat(2-5): add governed scheduling inspection capability`, matching the spine's "(Story 2.5)" attribution exactly. No issue — flagged only as a positive confirmation since provenance claims are easy to get wrong.

### 3. [low] EAD-3 attribution rule (worker-driven events use the run requester, not the proposal author) traced end-to-end and confirmed

`backend/api/routers/schedule_runs.py:399-409` calls `enqueue_compute(..., actor_id=validated.actor_id, ...)` where `validated.actor_id` is set from `session.app_user_id` (line 386) — the authenticated session actor issuing the enqueue command, not `proposal.created_by_actor_id`. That actor_id is stored on `job_queue.actor_id` (`enqueue_compute.py` → `JobLeaseV1(..., actor_id=actor_id, ...)` → `run_repository.enqueue_job`). Later worker-driven transitions resolve their event `actor_id` via `backend/adapters/postgres/schedule_run.py:404-421` (`_actor_for_run`): it reads `job_queue.actor_id` first, falling back to the stream's first `persisted_event.actor_id` only if the job row's actor is somehow null. This confirms the run requester (not the proposal author) is what ends up on worker-driven `persisted_event.actor_id` today — exactly what EAD-3 claims as already-matching Story 3.6's fix.

## Per-item verification log

| # | Spine claim | File(s) checked | Result |
| --- | --- | --- | --- |
| 1 | `agent_run` status CHECK already contains `approval_required` and `agent_cancelled`; table has no reason column | `backend/adapters/postgres/schema.py:298-308` | Confirmed. `ck_agent_run_status` = `'agent_queued','agent_running','approval_required','agent_completed','agent_timed_out','agent_cancelled','agent_failed'`. Table columns: id, site_id, conversation_id, message_id, status, created_at — no reason/status_reason column. |
| 2 | `persisted_event.actor_id` is `NOT NULL` FK to `app_user` | `schema.py:321` | Confirmed: `Column("actor_id", UUID, ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False)`. |
| 2b | Full stream CHECK arms vs. conversation-stream convention | `schema.py:328-334` | Read in full (quoted above). Convention is compatible with the CHECK as written today — see Finding 1. |
| 3 | Baseline pointer served as `literal(None)` with no storage | `backend/adapters/postgres/scenario_catalogue.py:114-118,140`; `backend/application/contracts/scenario_projection.py:33` | Confirmed: `literal(None, type_=String).label("baseline_schedule_version")`; contract field is `baseline_schedule_version: str \| None` with no backing table. No `site_baseline` table exists anywhere in `schema.py`. |
| 4 | No approval/audit table and no `ApprovalBindingV1`/`AuditEnvelopeV1` contract module | `schema.py` (full read); `backend/application/contracts/` (glob) | Confirmed: no `approval_request`, `site_baseline`, or `audit_event` tables in schema.py; no `approval_binding.py` or `audit_envelope.py` in contracts/. Only mentions of "audit"/"approval" repo-wide are comments explicitly stating these don't exist yet (`enqueue_compute.py`'s `SCOPE_CONTROLS`: *"`AuditEnvelopeV1` does not exist in `backend/` at all"*). |
| 5 | Story 3.6 fix: worker-driven events attribute the run requester, not the proposal author | `backend/api/routers/schedule_runs.py:383-409`; `backend/application/use_cases/enqueue_compute.py`; `backend/adapters/postgres/schedule_run.py:404-421` | Confirmed — traced end-to-end, see Finding 3. |
| 6 | `policy_version` constant `one-user-mvp-v1` (Story 2.5) | `backend/application/capabilities/registry.py:11`; `git log` | Confirmed, including story attribution — see Finding 2. |
| 7 | `auth.resolve_session` exists as session→actor supplier | `backend/adapters/postgres/identity.py:106-113` | Confirmed: `resolve_session()` calls `SELECT ... FROM auth.resolve_session(:token_hash)`, an in-transaction Postgres function call. |
| 8 | `ck_schedule_run_candidate_completed` enforces candidate-only-when-completed | `schema.py:449` | Confirmed: `CheckConstraint("candidate_schedule_version_id IS NULL OR status = 'solver_completed'", ...)`. |
| bonus | EAD-8: `get_baseline_assignments` has no authoritative production supplier today | `backend/adapters/postgres/scenario_projection.py:632-647` | Confirmed: hardcoded to return an empty tuple `()` regardless of scenario, matching "none — guarded by EAD-8" / "seeded readers only". |

## Load-bearing items NOT independently confirmable from code (design intent, not brownfield fact)

These are forward-looking design decisions for tables/columns that don't exist yet, so they are not "reality checks" against current code — flagged only so they aren't mistaken for verified facts:
- `approval_request`'s partial unique index (`at most one pending per agent run`) — table doesn't exist yet.
- `agent_run.status_reason` nullable additive column — doesn't exist yet (spine correctly describes it as future, "gains").
- `site_baseline`'s CAS-by-`resource_version` mechanics — table doesn't exist yet.
These are appropriately scoped as decisions-to-implement, not misstated as present-tense fact, so no finding is raised against them.
