---
baseline_commit: e9449142a2019bc2067c4554bd544c3d4ca17def
---

# Story 4.4: Inspect Complete Decision Provenance

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner or reviewer,
I want one decision timeline from request through resulting baseline,
So that I can reconstruct what happened without access to hidden model reasoning.

**This story is a READ. It is the first Epic 4 story that writes nothing.** 4.1 created the
tables and TX1, 4.2 built the endpoint and TX3, 4.3 landed TX2 and moved the pointer. 4.4 adds
one projection over the rows those three stories already commit, one GET, and one Results
section. It lands **no migration, no table, no activity type, no event, no write path, no
setting, no dependency**.

**Depends on, and consumes:** Story 4.3's `consumed` binding, its `approval_consumed` audit
row, its `site_baseline` row, and its real before/after version pair — 4.3's own "Unblocks"
line names this story as their first consumer; Story 4.1's `approval_request` /
`audit_event` tables, `ApprovalBindingV1`, `AuditEnvelopeV1`, `PostgresAuditWriter`,
`PostgresSiteBaselineReader`; Story 4.2's `ApprovalRepository.get` /
`list_for_schedule_run` and the `_out` EAD-7 purity rule; Story 3.5's
`persisted_event` run stream and `ConversationRepository.timeline`; Story 3.2's
`ScheduleVersionV1.evidence_refs` (the only evidence supply carrying a non-null
`producing_run_version`); Story 2.7's `GroundedResponseV1` claims and their
`EvidenceRefV1` locators; Story 2.8's `frontend/src/features/evidence/` locator, origin, and
availability modules.

**Unblocks:** Story 4.5 (the provenance surface its audit-integrity and
telemetry-independence fixtures assert against), Story 4.6 (the Provenance timeline is one of
the surfaces its state matrix and axe suite sweep, `epics.md:1296`).

**Scope summary:** One new query module (`application/queries/decision_provenance.py` — the
Structural Seed's name). One new read port (`AuditReader`) and its PostgreSQL adapter. One new
contract module. One new `GET` on the **existing** approvals router. One contract-drift fix
(`AuditOutcomeV1`). One new frontend hook, one new component, one Results section. Two AC1
items declared ABSENT with named owners rather than fabricated (Decision 8).

**This story is the first in the repository to:**

1. **create `application/queries/`.** The directory does not exist at `e944914`; the Structural
   Seed reserved `application/queries/decision_provenance.py` and Story 4.3's Project Structure
   Notes explicitly refused to stub it — *"not created here, not even as a stub."*
2. **read `audit_event`.** `adapters/postgres/audit.py` is 25 lines and holds only
   `PostgresAuditWriter.append`; `application/ports/approval.py` declares `AuditWriter` with one
   method and no reader. Every audit row written since 4.1 has been write-only.
3. **join across all four persisted evidence sources in one answer** — `approval_request`,
   `audit_event`, `persisted_event` (both streams), and the scheduling aggregate.
4. **render `parameter_hash` / `consequence_hash` on a read model.** `ApprovalOut` deliberately
   omits them and `api/schemas.py:239-243` plus `docs/API.md:540` both name **this story** as
   the reader that takes them from `audit_event` instead.

---

## Facts this story depends on — each one written down and citable

Retro action **A3** (`epic-1-2-retro-2026-08-16.md` §6.1) requires this pass before decisions.
Every rule below is recorded somewhere citable; none of it may be re-derived from adapter code.

| Fact | Where it is written |
|---|---|
| **The provenance projection's home is `application/queries/decision_provenance.py` and its read is served from the approvals router** | Epic 4 spine *Structural Seed* (`ARCHITECTURE-SPINE.md:183, :186`); Story 4.3 *Project Structure Notes* |
| **Story 4.4 inherits, it does not re-decide.** Its projection reads the three-role identity model and AD-3's non-disclosing not-found | ADR-4 *Consequences* (`ADR-4-consequential-workflow.md:74`) |
| **`actor_id` is always the server-derived authenticated human principal.** Every consequential audit envelope carries `initiated_by_actor_id` and `decided_by_actor_id` as separate fields; the automated executor is represented **only** by worker facts (`lease_owner`, `attempt_id`, `fencing_epoch`) with **no `app_user` row**. Worker-driven persisted events set `actor_id` to the initiating human principal of the enqueuing command | EAD-3; ADR-4 D2, D3 |
| **The consequence-summary text has exactly one persisted home** — an application-owned literal snapshot on the `approval_request` row beside its canonical hash, written at TX1. **Story 4.4 replays it from that same immutable row**, so what was approved, what was hashed, and what provenance shows are one artifact. It is never recomputed at render, never read live from `ProposalV1.consequence_summary`, and never model prose | EAD-11; ADR-4 *Consequences* (`:72`) |
| **Site scope is server-derived and re-resolved on every provenance read; an unauthorized target gets the non-disclosing not-found shape** | AD-3 (Epic 4 spine *Inherited Invariants*) |
| **PostgreSQL owns append-only business audit; the normal application path has no UPDATE or DELETE on `audit_event`; telemetry can never authorize, block, or substitute for it** | AD-12; EAD-1; NFR33 (`epics.md:139`) |
| **Every read path is pure.** A query, render, reconnect, or SSE replay that observes `now() >= expires_at` on a pending binding presents it as expired and **writes nothing** | EAD-7 |
| **Model output may propose a request; it never supplies actor, versions, hashes, or a decision, and hidden reasoning never enters the binding or audit** | AD-15 (Epic 4 spine *Inherited Invariants*); AR15 (`epics.md:1246`) |
| **From Story 4.3 on, any comparison rendering whose frozen `baseline_schedule_version` is non-null while the baseline assignment supply is not authoritatively readable must fail closed with a distinct outcome — never render an empty read as "the baseline is empty."** EAD-8 binds Story 4.4 by name | EAD-8 (`ARCHITECTURE-SPINE.md:97`) |
| **Audit must capture actor/site, request/run/tool/approval/job identifiers, action and policy outcome, safe input/result summaries or hashes, before/after versions, software/model/prompt/tool/policy versions, and immutable evidence references** | NFR32 (`epics.md:137`) |
| **Expose provenance linking request, evidence consulted, concise decision summary, tool proposals/results, guardrail and policy outcomes, solver run, approval, execution result, and before/after versions — without hidden chain-of-thought** | FR20 (`epics.md:63`) |
| **Model-provider or Logfire failure must cause zero product-state corruption and zero authoritative-audit loss while supported deterministic workflows remain available** | NFR10 (`epics.md:93`) |
| **The Provenance timeline lives in Results**, as an ordered request / evidence / concise decision summary / proposals-results / policy outcomes / solver / approval / execution / before-after sequence, and does not expose hidden chain-of-thought | UX-DR22 (`epics.md:220`); `EXPERIENCE.md:102`; `DESIGN.md:96, :140` |
| **An Evidence link carries scenario ID, exact fixture/schedule/run version, evidence group, record ID, and optional field/time range, and opens the exact target without discarding claim position** | `EXPERIENCE.md:86`; UX-DR8 |
| **Terminal outcomes expose only valid next actions; state is text, not colour alone; identifiers use `{typography.identifier}` and a copy control** | UX-DR13 (`epics.md:202`); `EXPERIENCE.md:96`; `DESIGN.md:140` |
| **Manual assistive-technology verification is out of scope; automated coverage is the only accepted proof** | `EXPERIENCE.md:196` (Accessibility Floor) |
| **Every new guard must be observed failing** with its structural assertion removed or a relevant mutation applied, before it is trusted | epic-3 retro §1 *Challenges*, §3 preparation task; EAD-9 |
| **Every contract or guard names its production supplier from the spine's table, or the story extends the table** | EAD-9 |
| Never hand-type an evidence file: commit code → clean tree → measure → generate through a script → commit evidence separately | `docs/EVIDENCE-CONVENTION.md:9-20, 191-199` |

**`docs/DOMAIN-MODEL.md` governs demand families, units, and assignments, and it constrains
exactly one thing here: what this projection may CLAIM.** `outbound`/`inbound` demand is
measured in **volume**, `indirect` in **headcount**, and assignments carry worker identity but
**no family**. **This story computes no metric and derives no demand figure.** Every number it
renders is replayed from a row another story computed and persisted — the binding's
`consequence_summary` (EAD-11), the audit envelope's `safe_summary` and hashes, the candidate's
`MetricSetV1`, and `GroundedClaimV1.value`/`unit`, each of which already carries its own
`EvidenceRefV1`. **The dev agent must not add a calculator to this projection.** If a figure
AC1 seems to ask for is not already persisted, it is Decision 8's territory (declare it absent),
never a new computation. Do not re-derive the family/unit rule from adapter code; cite the
document.

---

## Acceptance Criteria

Verbatim from `epics.md:1236-1256`.

1. **Given** a run and any approval outcome, **When** provenance is queried, **Then** the
   ordered projection links request, evidence consulted, concise application-owned decision
   summary, typed tool proposals/results, guardrail/policy outcomes, solver run, comparison,
   approval, execution, and before/after versions, **And** every item retains site/actor and
   relevant request, attempt, conversation, agent-run, tool, approval, job, solver-run, audit,
   schedule, and evidence IDs. (FR20, NFR32)

2. **Given** the Results view, **When** the Provenance timeline renders, **Then** literal
   outcomes, stable IDs, evidence links, before/after versions, and collapsible safe details
   render with the semantics the Epic 1 automated accessibility suite asserts, **And** hidden
   chain-of-thought, raw prompts/completions, sensitive tool payloads, and credentials never
   appear. (UX-DR22, AR15)

3. **Given** a saved historical result during model or telemetry outage, **When** provenance is
   opened, **Then** authoritative product/audit records and immutable evidence remain
   available, **And** optional model summaries or traces may fail independently without
   removing the decision path. (FR20, NFR10)

4. **Given** unauthorized audit or evidence access, **When** the provenance query resolves a
   target, **Then** site scope is revalidated and protected existence/value is not disclosed,
   **And** the normal application path cannot update or delete audit events. (FR21, NFR33)

---

## Thirteen decisions were made at story creation — do not re-litigate them

> **Authoring rule in force since commit `2cf598f`:** every Decision below states, in one
> sentence, what its mechanism does **not** cover. Tasks cite these Decisions; they do not
> re-argue them.

### Decision 1 — One module, one route, and the route is registered ABOVE `/{approval_id}`

The Structural Seed names both homes: `application/queries/decision_provenance.py` for the
projection and `api/routers/approvals.py` for the "provenance read"
(`ARCHITECTURE-SPINE.md:183, :186`). Honor both. The route is:

```
GET /api/v1/approvals/provenance?schedule_run_id={uuid}
```

**It must be declared before `@router.get("/{approval_id}")` at `approvals.py:337`.** FastAPI
matches routes in registration order, so a `provenance` path segment registered after
`/{approval_id}` is captured by that route's `approval_id: UUID` parameter and answers `422`
for a literal that is not a UUID. The four existing routes are at `:221` (POST create), `:259`
(POST decision), `:337` (GET one), `:345` (GET list) — insert at `:337`.

The key is the **schedule run**, not the approval: AC1 says *"Given a run and any approval
outcome"*, AC2 renders it in the run-scoped Results view, and a run may legitimately carry zero
approvals (never requested), one, or several (rejected then re-requested). Keying on the
approval would make a rejected-and-retried run two disconnected timelines.

**Does not cover:** it does not move, rename, or re-shape any existing approvals route, and it
does not make the approvals router the owner of scheduling data — the projection reads through
ports (Decision 2), and the router does nothing but resolve the session, call the query, and
map the result.

### Decision 2 — Exactly one new port (`AuditReader`), the query module opens no SQL, and nothing gains a writer

`application/ports/approval.py` declares `ApprovalRepository` and `AuditWriter`; there is no
audit reader anywhere. Add `AuditReader` **beside `AuditWriter` in that same file** — one port
file per storage home is the convention `approval.py` already sets and Story 4.3 restated when
it put `SiteBaselineWriter` beside the reader. Implement it as `PostgresAuditReader` in the
existing `adapters/postgres/audit.py`, and register `get_audit_reader` in `api/deps.py`
alongside `get_audit_writer` (`deps.py:149`).

`AuditReader` gets **one** method:

```python
def list_for_schedule_run(self, connection, *, schedule_run_id: UUID, site_id: UUID) -> tuple[AuditEnvelopeV1, ...]: ...
```

Every other source already has a port: `ApprovalRepository.list_for_schedule_run`,
`ScheduleRunRepository.get_run` / `get_candidate` / `load_snapshot`,
`ConversationRepository`, `SiteBaselineReader.get`. `decision_provenance.py` imports
`sqlalchemy` for nothing and composes ports only — the same shape every use case in
`application/use_cases/` already has.

**Does not cover:** it does not give audit an update or delete operation. `AuditReader` has one
read method and `PostgresAuditReader` issues one `SELECT`; AC4's "cannot update or delete" stays
a **database privilege** fact proved in Task 10, not a Python convention.

### Decision 3 — The projection persists nothing, and that is structural, not a promise

No migration, no table, no column, no `ActivityTypeV1` member, no `persisted_event` row, no
`audit_event` row, no idempotency row. EAD-7's *"every read path is pure"* is the governing rule
and it already binds `_out` (`approvals.py:118-123`), which presents an overdue pending binding
as `expired` without writing. Provenance uses **that same function's rule**: an overdue pending
binding appears in the timeline as presented-expired, and the stored state stays `pending`.

**Does not cover:** it does not make provenance idempotent against concurrent writes. Two reads
during an in-flight decision can legitimately return different timelines; the projection is a
snapshot of committed rows at read time, not a versioned resource, and it publishes no
`resource_version` for a caller to pin.

### Decision 4 — What belongs to "a run" is an enumerated closed membership rule

Given `schedule_run_id = R` in site `S`, the projection includes exactly:

| Source | Selector |
|---|---|
| `schedule_run` + `run_snapshot` + candidate `schedule_version` | `id = R` (via `ScheduleRunRepository.get_run` / `load_snapshot` / `get_candidate`) |
| `persisted_event` (run stream) | `schedule_run_id = R` — the `run_progress` transitions |
| `approval_request` | `schedule_run_id = R` — **all** bindings, every state |
| `persisted_event` (conversation stream) | `agent_run_id ∈ {binding.agent_run_id for those bindings, non-null}` |
| `audit_event` | `schedule_run_id = R` — every outcome including `approval_denied` |
| `site_baseline` | the site's single current row, read once, as the "after" side |

Everything is reachable from `R` by an existing index or FK: `ix_persisted_event_schedule_run_id`,
`uq_approval_request_pending_run`'s base columns, and the site predicate RLS forces on every
table. **`audit_event` has no index on `schedule_run_id`** (`schema.py:583-591` creates only
`ix_audit_event_site_id` plus the two uniqueness indexes) — the site predicate plus a
single-site MVP makes the scan bounded; note it, do not add an index in a read story.

**Does not cover:** the rest of the conversation. An investigation turn that cited evidence but
produced no draft or approval for **this** run is Chat's timeline, not this run's provenance.
Record that reduction in `SCOPE_CONTROLS` under `membership:agent_run_bound_conversation_events`
rather than letting a future reader assume the projection is lossy by accident.

### Decision 5 — Ordering is `(occurred_at, source_rank, id)`, because `sequence` cannot order across streams

`persisted_event.sequence` is unique per `(stream_id, sequence)`
(`uq_persisted_event_stream_sequence`) and is minted as `max(sequence) + 1` **within one
stream**. A run's provenance interleaves the conversation stream, the run stream, `audit_event`,
and two plain row timestamps, so sequence numbers from different streams are not comparable and
sorting by them silently produces a plausible-looking wrong order.

Sort by `occurred_at` ascending, tie-broken by a fixed `source_rank`
(`solver_run < run_progress < draft < agent_response < approval_request < audit < baseline`) and
then by the item's own UUID. **`occurred_at` ties are expected, not hypothetical:** TX1, TX2, and
TX3 each write their binding row, audit row, and persisted event inside one transaction with a
single application clock, so a promotion produces three items at the identical timestamp. Without
the tie-break the timeline order is whatever the driver returns.

Every timestamp is `DateTime(timezone=True)` and the site timezone is `Australia/Sydney`, applied
once at the adapter boundary (`docs/DOMAIN-MODEL.md` §1 *Time*). Order in UTC; render with the
existing frontend formatter.

**Does not cover:** it does not give the timeline a resumable cursor or paging. This is a
bounded whole-run read; if a run ever exceeds a sane item count the fix is a cap with a stated
`has_more`, not a cursor contract — and no current run approaches one.

### Decision 6 — One closed discriminated union, and every NFR32 identifier is present-or-`null`, never omitted

The response is `DecisionProvenanceOut { schedule_run_id, site_id, items: [...] }` where each
item is a Pydantic discriminated union on `item_type`, exactly the shape
`ConversationActivityItemOut` already uses (`api/schemas.py:254-262`,
`Field(discriminator="activity_type")`). Discriminants:

`solver_run | run_progress | draft | evidence_claim | tool_proposal | approval_request | approval_decision | audit_record | baseline_promotion`

Every item carries a common base with **all** of NFR32's identifier slots, typed
`UUID | None` / `str | None` and always serialized:

`occurred_at, item_type, site_id, actor_id, initiated_by_actor_id, decided_by_actor_id,
request_id, attempt_id, conversation_id, agent_run_id, tool_call_id, approval_id, job_attempt_id,
schedule_run_id, audit_id, schedule_version_id, scenario_version_id, evidence_refs`

**A slot with no value is `null`, never absent.** An omitted key and a null are the same thing to
a JavaScript client only until the client tries to distinguish "this row never had a tool call"
from "the projection dropped it" — which is exactly the question a reviewer opens provenance to
answer. This mirrors `_context`'s reasoning at `approvals.py:106-115` in the opposite direction:
there an always-present `{}` was wrong because it rendered as data; here an always-present `null`
is right because the slot itself is the claim.

**Does not cover:** it does not add identifiers to the underlying rows. A `null` `tool_call_id`
on a planner-initiated approval means the row genuinely never carried one (the planner path is
keyed by body hash, EAD-3), not that provenance lost it.

### Decision 7 — Attribution renders EAD-3's three roles as three fields, which closes `deferred-work.md:443`

That ledger entry — *"one run's stream interleaves 'who owns this proposal' with 'who pressed the
button', and an Epic 4 audit reader cannot distinguish a human act from an automated one"* — was
re-pointed at Story 4.1 to **"Owner: Stories 4.3/4.4, which read these rows and decide how a
worker-initiated transition should attribute itself."** Story 4.3 wrote no worker-driven audit
row, so the decision lands here, and it is **decided by rendering, not by migration**:

1. `actor_id` is rendered as **"initiated by"** on every item, never as "who did this". EAD-3
   already fixes its meaning as the initiating human principal of the enqueuing command, and
   ADR-4 D3 confirms Story 3.6's fix made `enqueue_compute` supply the run requester.
2. The **executor is named only through `worker_facts`** (`lease_owner`, `attempt_id`,
   `fencing_epoch`), projected from `audit_event.worker_facts` as a distinct, optional block.
   There is no synthetic system-user row and this story creates none.
3. `decided_by_actor_id` appears **only** on `approval_decision` and `audit_record` items.

The remaining honesty gap is that `persisted_event.actor_id` on a run-stream transition is the
proposal creator on enqueue and the session actor on cancellation. Under this rendering that
inconsistency is *narrower than the ledger feared* — both are real human principals and both are
labelled "initiated by" — but it is still a known imprecision. Update the ledger entry: the
identity **model** is settled (EAD-3's three roles, no system user, executor facts only); the
residual `enqueue`-vs-`cancel` inconsistency is re-pointed to **Epic 5**, whose instrumentation
story is the first with a reason to distinguish them.

**Does not cover:** it does not make a worker distinguishable from a human on a *run-stream
event*. `worker_facts` lives on `audit_event`, and no run-stream `persisted_event` carries one —
which is why the residual gap is re-pointed rather than closed.

### Decision 8 — Two of AC1's ten items have no persisted supply; they are declared ABSENT with named owners, never fabricated

EAD-9 requires a named production supplier or a declared gap. Measured at `e944914`:

**(a) Typed tool proposals/results — one supply, and it is narrow.** There is no `tool_call`
table and no tool-call column anywhere in `schema.py`. Exhaustive grep across
`backend/adapters/` and `backend/application/use_cases/` finds `tool_call_id` at exactly two
lines, both in `promote_baseline.py` (`:92`, `:200`), both reading
`approval_request.pending_payload`. So the **only** persisted tool proposal in the repository is
the `AgentApprovalPendingV1.pending_calls[0]` that triggered an agent-initiated approval, and
the only tool *results* are `AgentPartV1(kind="tool_result")` parts inside that payload's
`turn` — which Decision 9 forbids projecting.

Provenance therefore emits **one** `tool_proposal` item per agent-initiated binding, carrying
`tool_name` and `tool_call_id` and nothing else. Planner-initiated bindings emit none. Every
other tool call the agent ever made is unrecoverable. Record it in `SCOPE_CONTROLS` under
`tool_proposals:approval_triggering_call_only` and open a ledger entry — **Owner: Epic 5**,
whose Story 5.1 instruments agent runs and is the first with a reason to persist a tool
transcript.

**(b) Comparison — no persisted row exists, and after promotion it is deliberately refused.**
`ActivityTypeV1` declares eight discriminants (`activity.py:11-20`) but `ActivityItemV1` unions
**seven** (`:162-170`): `comparison` has no dataclass, no `*ActivityOut` schema, and no producer
anywhere. The comparison is recomputed at read time by `calculate_comparison`, and EAD-8 makes
it **fail closed** whenever the frozen `baseline_schedule_version` is non-null while
`get_baseline_assignments` returns the literal `()` at `scenario_projection.py:644` — which,
from the first promotion onward, is every subsequently snapshotted run (Story 4.3's first review
finding).

Provenance therefore links the comparison **by reference, never by recomputation**: the
`solver_run` item carries `candidate_schedule_version_id`,
`run_snapshot.baseline_schedule_version`, and a `comparison_status` of `available` or
`unavailable` with the literal EAD-8 reason. **The projection must not call
`calculate_comparison`.** Doing so would put a computation that raises inside a read whose whole
job is to survive when other things fail, and would recompute a figure Decision 3 says provenance
only replays.

**Does not cover:** it does not create the missing `comparison` activity type or a tool-call
store. Both stay ledger entries with owners; a later story that adds either extends this
projection additively.

### Decision 9 — `pending_payload` is projected as IDENTITY ONLY; its `turn` never crosses the API boundary

`AgentApprovalPendingV1.turn` is the full owned transcript: `AgentTurnV1.messages[].parts[]`
carrying `text`, `tool_args_json`, and `tool_result` content
(`agent_runtime.py:88-101, :104-120, :155-166`). AC2 forbids *"raw prompts/completions,
sensitive tool payloads"* by name. Projecting `pending_payload` — the single most tempting field
in the story, because it is the only place a tool call is persisted at all — ships **exactly
what AC2 forbids, under a field named "provenance"**.

The `tool_proposal` item is built from `pending_calls[0].tool_name` and
`pending_calls[0].tool_call_id`. `tool_args_json` is not read. `turn` is not read. The
projection never returns the payload dict, never nests it, and never passes it to a Pydantic
model that would serialize unknown keys.

**Does not cover:** it does not audit the rest of the codebase for payload leaks. The guard is
one field allowlist in the projection plus one architecture assertion (Task 9) that no
provenance output type declares a `tool_args_json`, `turn`, `payload`, `content`, or `history`
field.

### Decision 10 — AR15 is satisfied by ALLOWLIST CONSTRUCTION, not by stripping

Hidden reasoning cannot reach persisted state in the first place: `AgentPartKindV1` is
`text | tool_call | tool_result` with **no `thinking` kind by construction**
(`agent_runtime.py:88-92`), and `agent/translate.py:8-13, :176` drops every hidden-reasoning
part kind — present and future — at the adapter boundary. So provenance's obligation is **not**
to strip reasoning; it is to never widen the surface.

Concretely: every item is constructed field by field from named columns and named contract
attributes. The projection **never** returns `persisted_event.payload` as a dict, never splats
`vars()`, and never `model_validate`s a JSONB column into a permissive model. This is the same
rule `scenario_catalogue.py:26-29` already states — *"Fields are mapped one by one rather than
splatted from `vars()`"* — applied to a surface where the failure mode is disclosure rather than
a silently missing field.

The one place model-authored text legitimately reaches the timeline is the persisted
`agent_response` / `terminal_outcome` payloads, which are already planner-visible in Chat, already
grounded, and already bounded (`_MODEL_COPY_LIMIT = 200`, `execute_turn.py`). Provenance renders
those unchanged; it adds nothing new.

**Does not cover:** it does not re-verify the agent adapter's translation boundary. That is
`tests/architecture/test_agent_runtime_boundaries.py`'s job and it is unchanged here.

### Decision 11 — `AuditOutcomeV1` gains its sixth member; this story is where the drift closes

Measured at `e944914` — a three-way split:

| Where | Members |
|---|---|
| `ck_audit_event_outcome` in PostgreSQL (widened by migration `e5f6a7b8c9d0`) | **six**, including `approval_denied` |
| `adapters/postgres/schema.py:520` (Story 4.3 review patch) | **six** |
| `application/contracts/audit_envelope.py:12` — `AuditOutcomeV1` | **five** — `approval_denied` missing |
| `api/routers/approvals.py:309` — the denial-audit write | passes `outcome="approval_denied"` |

`AuditEnvelopeV1` is a plain frozen dataclass, so nothing raises at runtime and 4.3's review
patch — which fixed `schema.py` — did not reach the contract. It becomes visible **here**,
because provenance is the first surface to publish `outcome` as a closed vocabulary into a
generated TypeScript union: a five-member `Literal` produces a client type that cannot represent
a row the server already writes.

Add `"approval_denied"` to `AuditOutcomeV1`. Then add one assertion that the contract Literal
and `schema.py`'s CHECK enumerate the same set, so the next widening cannot drift again — the
drift-check shape 4.3's review asked for and got only for `schema.py`.

**Does not cover:** it does not add a new outcome. The sixth member already exists in the
database, in `schema.py`, and in production writes; only the contract is behind, and this is a
contract correction, not an EAD-6 vocabulary change.

### Decision 12 — AC3 and AC4 are PROVEN here, not built

**AC3 (outage independence)** holds because every source is a database row.
`decision_provenance.py` imports nothing from `agent/`, `llm/`, or any provider module, and calls
no calculator (Decision 8b). The clause *"optional model summaries or traces may fail
independently"* is satisfied by the persisted `agent_response` / `terminal_outcome` items already
being durable rows, not live calls. Prove it with an **import assertion** in
`tests/architecture/`, using the precedent at `test_model_outage_boundaries.py`, plus a route
test with the provider forced to fail.

**AC4 (site scope and append-only)** is already structurally true at `e944914` and must be
demonstrated, not re-implemented:

* **Site scope:** `_secure()` in migration `d4e5f6a7b8c9:26-32` sets `ENABLE`/`FORCE ROW LEVEL
  SECURITY` and a `site_id = current_setting('app.site_id')` policy on `approval_request`,
  `site_baseline`, and `audit_event`; every repository statement additionally carries an explicit
  `site_id` predicate.
* **Non-disclosure:** the existing shape is *return `None` → 404 "not visible in this site"*
  (`approvals.py:341`), with the reasoning stated at `conversation.py:286-294` — reading the
  child rows alone would answer with an empty tuple, *"a different and disclosing answer"*. A
  provenance query for a foreign or absent run must be **byte-identical** in both cases.
* **Append-only:** `_secure()` issues `GRANT SELECT, INSERT` then `REVOKE UPDATE, DELETE`.
  `approval_request` and `site_baseline` get column-level `UPDATE` re-grants at `:117-118`;
  **`audit_event` gets none.** Prove it with `has_table_privilege` as `shiftmind_runtime` —
  the technique Story 4.3's Trap 11 established, because reading `GRANT` lines alone misleads.

**Does not cover:** it does not prove a *superuser* or the migration role cannot update audit.
`shiftmind_runtime` is the "normal application path" NFR33 names; role hardening beyond it is
Epic 5/6's.

### Decision 13 — The Provenance section owns its own query and its own failure boundary, in Results only

Story 4.3's most expensive review finding was that **one** failing query removed the whole
Results page: `ScenarioResults.tsx` gates the approval panels on `!query.isError` (`:55`) and the
comparison block on `query.data.comparison` (`:56`), so a single 409 hid controls that had
nothing to do with it. Do not repeat it in the other direction.

`useRunProvenance(runId)` is its own TanStack Query hook with its own key
(`["run-provenance", runId]`, matching `runApprovalsKey`'s shape at `useRunApprovals.ts:4`).
The `<ProvenanceTimeline>` section renders **independently** of `useScheduleRunResult`: a
provenance failure shows one scoped `InlineAlert` inside the provenance section and removes
nothing else; a result failure removes nothing from provenance. It is invalidated on approval
decision, alongside the keys `useDecideApproval.ts` already invalidates.

It renders in **Results only**. `EXPERIENCE.md:102` places the Provenance timeline in Results;
UX-DR22 and `DESIGN.md:96` do the same. Chat's `ActivityTimeline` is a different surface with a
different contract and is not touched.

**Does not cover:** it does not add provenance to Chat, and it does not add an SSE or polling
path. Provenance is a pull-on-open read; the live surface is Chat's stream, which already exists.

---

## Tasks / Subtasks

- [x] **Task 1 — Re-derive the baselines before touching anything (retro §3)**
  - [x] Record backend total collected/passed/failed/skipped, `-m postgres` collected and passed,
        frontend files and tests, and Playwright count, **at `e944914`, before any edit**.
  - [x] Story 4.3's post-review Completion Notes record backend 1426 passed / 3 failed / 7 skipped;
        PostgreSQL 127 passed / 1 failed; frontend 575 passed; Playwright 62 passed. **These are
        inherited, not verified** — 2.7, 2.8, and 3.12 each found an inherited baseline stale.
        Record the total alongside the split; the total is the stable invariant.
  - [x] The three known backend failures are **external and pre-existing** (two live OpenRouter
        cases on a retired free model slug; one temporary-database cleanup fixture importing the
        wrong conftest). Do not attribute them to this story and do not fix them here.

- [x] **Task 2 — Close the `AuditOutcomeV1` drift (AC: 1; Decision 11)**
  - [x] Add `"approval_denied"` to `AuditOutcomeV1` (`application/contracts/audit_envelope.py:12`).
  - [x] Add a test asserting `set(get_args(AuditOutcomeV1))` equals the members parsed from
        `ck_audit_event_outcome` on `adapters/postgres/schema.py`'s `audit_event` table.
  - [x] **Demonstrated-red:** remove `"approval_denied"` from the Literal and observe the new
        assertion fail. Record it.

- [x] **Task 3 — `AuditReader` port and PostgreSQL adapter (AC: 1, 4; Decision 2)**
  - [x] Declare `AuditReader` beside `AuditWriter` in `application/ports/approval.py`, with
        `list_for_schedule_run` only.
  - [x] Implement `PostgresAuditReader` in `adapters/postgres/audit.py`, ordered by
        `(occurred_at, id)`, with an **explicit `site_id` predicate on the statement** — RLS is
        defence in depth, not the only check, matching every other repository in `adapters/postgres/`.
  - [x] Register `get_audit_reader` in `api/deps.py` beside `get_audit_writer` (`:149`).
  - [x] The adapter has **no** update or delete method (Decision 2's "does not cover").

- [x] **Task 4 — Provenance contracts (AC: 1, 2; Decisions 6, 8, 9)**
  - [x] Create `application/contracts/decision_provenance.py`: `DecisionProvenanceV1` plus the
        nine item dataclasses from Decision 6, each frozen, each carrying the full identifier base.
  - [x] `SCOPE_CONTROLS` in that module records, as data:
        `membership:agent_run_bound_conversation_events`,
        `tool_proposals:approval_triggering_call_only`,
        `comparison:linked_by_reference_never_recomputed`,
        `payload:identity_only_never_turn`,
        `audit_evidence_refs:empty_at_every_write_site`.
  - [x] Mirror the union in `api/schemas.py` as `DecisionProvenanceItemOut` with
        `Field(discriminator="item_type")`, following `ConversationActivityItemOut`
        (`api/schemas.py:254-262`). Map fields **one by one**, per Decision 10.

- [x] **Task 5 — The projection (AC: 1, 3; Decisions 3, 4, 5, 7, 8)**
  - [x] Create `application/queries/decision_provenance.py` (and `application/queries/__init__.py`).
  - [x] Implement Decision 4's membership rule and Decision 5's ordering, composing ports only —
        **no `sqlalchemy` import, no calculator call, no `calculate_comparison`.**
  - [x] Apply `_out`'s EAD-7 presented-expired rule to every projected binding (Decision 3);
        import or extract it rather than writing a second copy of the comparison.
  - [x] Attribute per Decision 7: `actor_id` labelled "initiated by"; `worker_facts` as a distinct
        optional block; `decided_by_actor_id` only on decision and audit items.
  - [x] Return `None` for a run not visible in this site, so the router can render the
        non-disclosing 404 (Decision 12).

- [x] **Task 6 — Evidence links (AC: 1, 2)**
  - [x] Project `EvidenceRefV1` tuples onto their items from the two real suppliers:
        `ScheduleVersionV1.evidence_refs` (the candidate — the only supply with a non-null
        `producing_run_version`, set at `finalize_schedule_run.py:82`) and
        `GroundedClaimV1.evidence_refs` on `agent_response` activities.
  - [x] `audit_event.evidence_refs` is `()` at **all four** write sites
        (`request_approval.py:153`, `decide_approval.py:140`, `promote_baseline.py:161`,
        `approvals.py:316`). Project it faithfully as empty, record it in `SCOPE_CONTROLS`, and
        open a ledger entry against NFR32's "immutable evidence references" clause. **Do not
        backfill it by editing a write path** — this story writes nothing (Decision 3).

- [x] **Task 7 — The route (AC: 1, 4; Decisions 1, 12)**
  - [x] Add `GET /approvals/provenance` to `api/routers/approvals.py`, **inserted above
        `@router.get("/{approval_id}")` at `:337`**, with `schedule_run_id: UUID = Query()`.
  - [x] 404 `schedule_run_not_found` with the existing non-disclosing copy for an absent **or**
        foreign run — the two must be byte-identical.
  - [x] **Demonstrated-red:** move the route below `/{approval_id}` and observe the request answer
        `422` instead of `200`. Record it — this is the trap the decision exists for.
  - [x] Regenerate types with `npm run codegen` (never hand-author `schema.d.ts`); confirm
        `openapi.json` changed.

- [x] **Task 8 — Backend tests for the projection (AC: 1, 3)**
  - [x] Fake-port use-case tests in `backend/tests/test_decision_provenance.py`: membership,
        ordering including the same-timestamp tie-break, presented-expired, planner-initiated
        (no `tool_proposal`) vs agent-initiated (exactly one), a rejected-then-re-requested run
        producing one timeline, and a run with zero approvals.
  - [x] Router/HTTP-contract tests in `backend/tests/test_approvals_api.py`.
  - [x] Real-PostgreSQL tests in `backend/tests/test_approval_governance_postgres.py`
        (`@pytest.mark.postgres`) driving a full request → run → approve → promote cycle and
        asserting the timeline links before/after versions from `audit_event`.

- [x] **Task 9 — AR15 disclosure guard (AC: 2; Decisions 9, 10)**
  - [x] Architecture test: no provenance output type declares a field named `tool_args_json`,
        `turn`, `payload`, `content`, `history`, `prompt`, or `completion`.
  - [x] Route test: seed a binding whose `pending_payload` carries a distinctive marker string in
        both `tool_args_json` and a `turn` text part; assert the marker appears **nowhere** in the
        serialized response body.
  - [x] **Demonstrated-red:** add `tool_args_json` to the `tool_proposal` item and observe both
        assertions fail. Record it.

- [x] **Task 10 — AC4 proof (AC: 4; Decision 12)**
  - [x] `@pytest.mark.postgres`: as `shiftmind_runtime`, assert
        `has_table_privilege('audit_event','UPDATE')` and `...,'DELETE')` are both false while
        `SELECT` and `INSERT` are true — and, as the contrast that keeps the assertion meaningful,
        that `has_column_privilege('approval_request','state','UPDATE')` is **true** (the
        column-level re-grant at `d4e5f6a7b8c9:117`). **Use `has_column_privilege` for that half:**
        a column-only grant does not satisfy `has_table_privilege`, so testing both sides with the
        table-level function would report "false, false" and prove a uniformly locked schema
        rather than the real distinction.
  - [x] Attempt an `UPDATE` and a `DELETE` on `audit_event` as `shiftmind_runtime` and assert both
        are refused.
  - [x] Cross-site: a provenance query for a run in another site returns the same 404 body as an
        absent run.

- [x] **Task 11 — AC3 proof (AC: 3; Decision 12)**
  - [x] Import assertion in `tests/architecture/`: `application/queries/decision_provenance.py`
        imports nothing from `agent/`, `llm/`, or a provider module, and calls no calculator.
  - [x] Route test with the model provider forced to fail: provenance for a previously completed,
        promoted run returns the full timeline including audit rows and evidence refs.
  - [x] **Demonstrated-red:** import a provider module into the query module and observe the
        architecture assertion fail. Record it.

- [x] **Task 12 — Frontend (AC: 2; Decision 13)**
  - [x] `frontend/src/api/provenance.ts` (thin typed `openapi-fetch` wrapper) and
        `frontend/src/hooks/useRunProvenance.ts` with an exported `runProvenanceKey`, matching
        `useRunApprovals.ts`.
  - [x] `frontend/src/features/provenance/ProvenanceTimeline.tsx`: an ordered list of items,
        each with literal outcome text, stable identifiers using the identifier copy control,
        `EvidenceLink` reusing `toSearchParams` / `rememberOrigin` from
        `features/evidence/locator.ts` and `origin.ts`, before/after versions on the promotion
        item, and safe details inside a Collapsible (`DESIGN.md:140`).
  - [x] Mount it in `ScenarioResults.tsx` with its **own** query and its own scoped `InlineAlert`
        (Decision 13). Add `runProvenanceKey` to `useDecideApproval.ts`'s invalidations.
  - [x] Co-located Vitest tests asserting accessible names and roles, the independent failure
        boundary in **both** directions, and that a marker string planted in a mocked
        `pending_payload`-derived field never renders.

- [x] **Task 13 — Automated accessibility (AC: 2)**
  - [x] Extend `frontend/e2e/accessibility.spec.ts` to sweep the Results view with the Provenance
        timeline present, expanded and collapsed, at 100% and 200% zoom.
  - [x] Status is **text, not colour alone** (UX-DR13); the timeline is a real list with a heading;
        long identifiers must not force page-level horizontal scroll.
  - [x] No manual assistive-technology verification — automated coverage is the only accepted
        proof (`EXPERIENCE.md:196`).

- [x] **Task 14 — Documentation and ledger reconciliation (retro §3)**
  - [x] `docs/API.md`: add the provenance read to the *Approval requests* section, state that it
        is the reader `:540` already names for the hashes, and list its one problem code.
  - [x] `deferred-work.md`: close the identity-model entry at `:443` per Decision 7 and re-point
        its residual to Epic 5; open three new entries — the tool-transcript gap (Owner: Epic 5),
        the unimplemented `comparison` `ActivityTypeV1` discriminant, and `audit_event.evidence_refs`
        being empty at every write site.
  - [x] `docs/GATE-A-RUNBOOK.md`: no change expected — verify, do not assume.
  - [x] **No evidence file.** This story has no measured threshold, so
        `docs/EVIDENCE-CONVENTION.md` has nothing to bind. Say so in Completion Notes.

- [x] **Task 15 — Full verification**
  - [x] Backend suite, `-m postgres` suite, `npx tsc -b`, `npm run lint`, `npm test`, Playwright,
        Alembic check, and the architecture/changed-surface tests.
  - [x] `npx tsc -b` is what actually type-checks the tree; `npm run typecheck` is inert because
        the root `tsconfig.json` declares `"files": []` (Story 4.3 Trap 13).
  - [x] Report totals against Task 1's re-derived baselines, not against 4.3's recorded numbers.

### Review Findings

Code review 2026-09-01 against `e944914..edcce46`. Suites re-run at review time: backend
**1445 passed, 1 skipped, 7 deselected, 0 failed**; `npx tsc -b` clean; Vitest **581 passed** in
84 files. Findings 1, 2 and 3 were reproduced by execution, not read off the diff.

**All 8 patches applied at review, 2026-09-01.** Post-fix verification: backend **1448 passed,
2 skipped, 7 deselected, 0 failed**; `-m postgres` **131 ran, 131 passed, 0 skipped**;
`npx tsc -b` clean; `npm run lint` clean (three inherited Fast Refresh warnings); Vitest
**581 passed** in 84 files; Playwright **66 passed**. `npm run codegen` regenerated both
`openapi.json` and `schema.d.ts`; `status` is now a closed union in the generated client.

Demonstrated-red recorded for every guard added or repaired (Trap 14, EAD-9) — each was observed
failing against the pre-fix code, then green after:

- Repaired import guard: injecting `from sqlalchemy import select` and `from llm.stub import
  StubProvider` gives `AssertionError: assert not {'llm.stub', 'sqlalchemy'}`. The **pre-fix**
  guard passed that same injection, which is what made it worth fixing.
- `test_same_timestamp_decision_and_audit_order_independently_of_their_uuids`: restoring the
  shared rank `6` gives `timeline order changed with nothing but the approval UUID —
  At index 2 diff: 'approval_decision' != 'audit_record'`. The audit ids are pinned so the
  approval UUID is the only varying input; an earlier draft of this test used random audit ids
  and could not fail.
- `test_request_and_decision_items_take_identifiers_from_their_own_audit_row`: restoring the
  last-wins map gives a `request_id` mismatch on the request item.
- Comparison status: removing the no-candidate branch flips
  `test_projection_keeps_zero_approval_run_...` back to `available`.

- [x] [Review][Patch] **`comparison_status` reports `available` for runs that have no comparison at all** [backend/application/queries/decision_provenance.py:98] — The status is derived from one input only: `comparison_status="unavailable" if baseline_version is not None else "available"` (`decision_provenance.py:98`). It is correct on the EAD-8 axis Decision 8b names, but that is the *only* axis consulted. A run with no snapshot, or a `solver_infeasible`/failed run whose `get_candidate` returns `None`, has `baseline_version is None` and is therefore published as `comparison_status: "available"` alongside `candidate_schedule_version_id: null` and `metrics: null` — a comparison that is not merely unavailable but nonexistent. `test_decision_provenance.py:145` encodes the wrong claim as expected behaviour (`get_candidate` returns `None`, asserts `comparison_status == "available"`). The fix is a contract choice, not a bug fix: a truthful third state (`not_applicable`) widens a closed `Literal` already published into the generated TypeScript union, which Decision 11 classifies as a contract change rather than a refactor. Resolved at review as a patch, not a contract question: adding a third literal is ruled out by Decision 11 (widening a closed `Literal` published into the generated TypeScript union is a contract change) in a story that lands no vocabulary, and accepting it leaves `SafeDetails` rendering `Comparison: available` for a run that produced nothing. Fix inside the existing two-value contract: `unavailable` when `baseline_version is not None` (EAD-8 reason, unchanged), `unavailable` with a **second, distinct** reason when the candidate is `None` — `_COMPARISON_UNAVAILABLE` names the EAD-8 assignment-supply problem and would be a false explanation there — and `available` otherwise, which preserves the genuine first-run case (no frozen baseline, candidate present), where `calculate_comparison` does not raise. Flip the assertion at `test_decision_provenance.py:145`; that assertion is what encoded the wrong claim.

- [x] [Review][Patch] **`approval_request` and `approval_decision` items carry another operation's `request_id` and `attempt_id`** [backend/application/queries/decision_provenance.py:147] — `audits_by_approval = {audit.approval_id: audit for audit in audits if audit.approval_id}` is a last-wins dict over a list the adapter returns ordered by `(occurred_at, id)`. One approval accumulates several audit rows (`approval_requested` at TX1, then `approval_consumed`/`approval_rejected` at TX2/TX3, plus any `approval_denied`), so the surviving entry is always the chronologically **last**, and both the request item and the decision item are stamped from it. Reproduced with fake ports against the real query module: with `approval_requested` carrying `request_id=…0064` and `approval_consumed` carrying `…00c8`, the `approval_request` item is emitted with `request_id=…00c8`, while the `approval_requested` audit item beside it in the same timeline correctly reports `…0064`. The timeline contradicts itself, and a reviewer asking "which request created this binding" — the question NFR32's identifier slots exist to answer — gets a well-formed identifier belonging to a different operation. Decision 6's own reasoning tells against the code: always-present slots exist to separate "never had one" from "provenance lost it", and this is a third case, "provenance substituted another row's". Fix: pair each item with the audit whose `outcome` matches it (`approval_requested` for the request item, `state_outcome[state]` for the decision item) rather than taking the last row per approval.

- [x] [Review][Patch] **Same-timestamp `approval_decision` and `audit_record` items order arbitrarily, defeating Decision 5** [backend/application/queries/decision_provenance.py:20] — `_SOURCE_RANK` assigns rank `6` to **both** `approval_decision` and `audit_record`, and the next tie-break `_sort_id` reads a *different field on each type* (`audit_id` for audits, which is `None` on decisions, so decisions fall through to `approval_id`). Two unrelated UUIDs are then compared as strings. Because `decide_approval` calls `terminalize(..., decided_at=now)` and `audit_writer.append(..., occurred_at=now)` with the same `now` inside one transaction, `occurred_at` is identical for every decided approval — Trap 4 states this is the normal case, not an edge case. Reproduced: changing only the approval's UUID from `int=7` to `int=255`, with all timestamps and all other data held constant, moves `approval_decision` from before both `audit_record`s to between the second audit and `baseline_promotion`. This is precisely the failure Decision 5 exists to prevent — "Without the tie-break the timeline order is whatever the driver returns" — the tie-break relocated the arbitrariness rather than removing it. Fix: give the two types distinct ranks (a decision precedes the audit that records it) and make the final tie-break a single comparable value rather than a per-type field.

- [x] [Review][Patch] **The AC3 / Decision 2 architecture guard cannot fail for `from X import Y`** [backend/tests/architecture/test_provenance_boundaries.py:39] — The guard collects `alias.name` from both `ast.Import` and `ast.ImportFrom`. For `ImportFrom` those aliases are the *imported symbols*, not the module (`node.module` holds the module), so the forbidden-prefix check never sees the module path. Verified by execution: of `from sqlalchemy import select`, `from llm.gemini import GeminiProvider`, `from application.grounding.calculators import calculate_metric` and `import agent.translate`, the assertion flags only the last. Three of the four realistic violation shapes pass silently — including the `from sqlalchemy import ...` form that is the *only* structural proof of Decision 2's "the query module opens no SQL". The recorded demonstrated-red (Debug Log, Task 11) used `import llm`, the one form the guard does catch, so the red was genuine but unrepresentative and left the blindness undetected. This is Trap 14's named defect class — "a guard that cannot fail is the epic's most-repeated defect". Fix: also collect `node.module` for `ast.ImportFrom`, then re-run the demonstrated-red with a `from llm... import ...` form.

- [x] [Review][Patch] **Missing Task 8 coverage is why findings 1 and 2 shipped** [backend/tests/test_decision_provenance.py:105] — Task 8 names "ordering including the same-timestamp tie-break", "presented-expired", and "planner-initiated (no `tool_proposal`) vs agent-initiated (exactly one)". `test_projection_keeps_zero_approval_run_and_uses_timestamp_rank_id_order` asserts only `["solver_run", "run_progress"]` — two items with *different* ranks — so it exercises neither a rank tie nor `_sort_id`, despite its name. `test_rejected_then_rerequested_bindings_share_one_run_timeline` passes an empty `audit_reader`, so the audit-pairing path in finding 1 is never entered. Nothing covers presented-expiry or the planner-vs-agent `tool_proposal` count. The real-PostgreSQL cycle test does produce two audit rows for one approval, so finding 1's data is live there — it simply asserts only the promotion's before/after. Fix: add tie-break and audit-pairing assertions alongside the fixes for findings 1 and 2, plus the two named cases that have no test at all.

- [x] [Review][Patch] **The `site_baseline` read is issued and discarded, and `docs/API.md` claims the response replays it** [backend/application/queries/decision_provenance.py:228] — `baselines.get(connection, site_id)` is called and its result thrown away; the adjacent comment explains that the immutable audit pair is the before/after source, so no current baseline value should be substituted into history. That reasoning is right, which leaves the call itself vestigial: a per-request query whose only effect is to keep a port dependency wired, and whose only possible outcome is to remove provenance on failure rather than add to it. Meanwhile `docs/API.md:527` states the read "replays committed run, conversation, approval, audit, and **current baseline** records", naming a source the response does not carry. Fix: drop the call and the `baselines` parameter (with its `Depends(get_site_baseline_reader)`) and correct that sentence — or, if Decision 4's membership table is to be honoured literally, project the row and say what it renders as.

- [x] [Review][Patch] **`status` is published as bare `str`, losing the closed vocabulary Decision 11 exists to preserve** [backend/api/schemas.py:279] — The contracts type both `SolverRunProvenanceV1.status` and `RunProgressProvenanceV1.status` as `ScheduleRunStatusV1`, but `SolverRunProvenanceOut` and `RunProgressProvenanceOut` widen them to `str`, so the generated client gets `string` where `outcome` correctly gets a union. Decision 11's stated rationale — provenance is the first surface publishing a closed vocabulary into a generated TypeScript union — applies identically to `status`, and Story 4.6's AC1 sweeps each literal run state for textual and structural distinctness. Fix: use `ScheduleRunStatusV1` in both `Out` models and regenerate with `npm run codegen`.

- [x] [Review][Patch] **Typed contract fields are read through `getattr(..., default)`, so a rename degrades provenance silently instead of failing** [backend/application/queries/decision_provenance.py:85] — `snapshot.accepted_at`, `snapshot.scenario_version_id`, `snapshot.baseline_schedule_version`, `candidate.schedule_version_id`, `candidate.evidence_refs` and `candidate.metrics` are all reached with a defaulted `getattr`. Every name currently exists on `RunSnapshotV1` and `ScheduleVersionV1`, so there is no live defect; the cost is that a future rename converts the affected slots to `null`/`()` rather than raising, on the one surface whose entire value is that a `null` means "the row never had one". This is the failure mode `scenario_catalogue.py:26-29` — cited by Decision 10 — was written against. Fix: read the attributes directly, handling `snapshot is None` / `candidate is None` explicitly once.

- [x] [Review][Defer] **The 10,000-item event cap is silent — no `has_more` accompanies it** [backend/application/queries/decision_provenance.py:81] — deferred, matches the specified design. Both `events_after` and `conversations.timeline` are called with `limit=10_000`, and a run exceeding it would be truncated with no signal. Decision 5's "does not cover" clause anticipates exactly this and prescribes the remedy — "a cap with a stated `has_more`, not a cursor contract" — so the cap is right and only its second half is missing. No current run approaches the bound.

---

## Dev Notes

### Files being modified — read these before editing

| File | Current state | What this story changes | What must not break |
|---|---|---|---|
| `backend/api/routers/approvals.py` | four routes: POST create `:221`, POST decision `:259`, GET one `:337`, GET list `:345`; `_out` applies EAD-7 presented-expiry `:118-123` | one GET inserted **above** `:337` | route registration order for the other four; `_out`'s EAD-7 purity on both existing GETs; `_ERROR_STATUS` / `_DECISION_DETAIL` / `_DECISION_RESPONSES` (the decision route's contract — do not extend them for a GET); the `_context` omit-when-empty rule `:106-115` |
| `backend/application/ports/approval.py` | `ApprovalRepository` (7 methods) + `AuditWriter` (1) | `AuditReader` added below `AuditWriter` | every existing signature; the file stays SQL-free |
| `backend/adapters/postgres/audit.py` | 25 lines, `PostgresAuditWriter.append` only | `PostgresAuditReader` added | the writer's exact insert shape — `worker_facts` and `evidence_refs` go through `TypeAdapter(...).dump_python(..., mode="json")` and the reader must reverse that, not assume raw dicts |
| `backend/application/contracts/audit_envelope.py` | `AuditOutcomeV1` has five members `:12` | sixth member (Decision 11) | `AuditEnvelopeV1`'s field order and `WorkerFactsV1`'s optional shape — both are already written into JSONB |
| `backend/api/deps.py` | `get_audit_writer` `:149`, `get_site_baseline_reader` `:165` | `get_audit_reader` added beside `:149` | `get_site_context`'s generator semantics — it commits on return and rolls back only when an exception escapes the **endpoint** (Story 4.3 Trap 1). A GET writes nothing, so this is informational, not a hazard here |
| `backend/api/schemas.py` | `ConversationActivityItemOut` discriminated union `:254-262`; `ApprovalOut` deliberately omits both hashes `:239-243` | provenance item union added | `ApprovalOut`'s omission — provenance is where the hashes surface, exactly as that comment says; do not "fix" `ApprovalOut` |
| `frontend/src/routes/ScenarioResults.tsx` | six independently gated blocks; `comparisonUnavailable` `:29`; approval panels gated on `!query.isError` `:55` | one new section with its own query | the candidate-only branch `:90-112` that 4.3's review added; the fail-closed `pendingApproval` derivation `:74`; every existing gate |
| `frontend/src/hooks/useDecideApproval.ts` | one idempotency holder **per decision intent**; settles on server-answered | one more invalidation key | the per-intent holder (a shared holder was the defect 4.2's review caught) and the settle-on-server-answered rule |
| `docs/API.md` | *Approval requests* section `:527-560`; `:540` names provenance as the hash reader | one route + one problem row | every existing row; 4.3's review found a documented code on a route that could not emit it — do not repeat that class of defect |

### Traps

1. **Route order.** `GET /approvals/provenance` registered after `GET /approvals/{approval_id}`
   is swallowed by the UUID path parameter and answers `422`. FastAPI matches in registration
   order. Decision 1; Task 7 has the demonstrated-red.
2. **`pending_payload` is the honeypot.** It is the only place in the repository a tool call is
   persisted, which makes projecting it feel like the obvious way to satisfy AC1's "typed tool
   proposals/results" — and it is precisely the "sensitive tool payloads" AC2 forbids. Decisions
   8a and 9.
3. **`persisted_event.sequence` cannot order across streams.** It is per-`stream_id`
   (`uq_persisted_event_stream_sequence`). Sorting a merged conversation-plus-run timeline by it
   produces a wrong order that looks right. Decision 5.
4. **Same-timestamp items are the normal case, not an edge case.** TX1/TX2/TX3 each write binding,
   audit, and event in one transaction against one clock. Without Decision 5's tie-break the
   promotion's three items order arbitrarily.
5. **`calculate_comparison` raises.** `BaselineSupplyUnavailableError` fires on every run
   snapshotted after the first promotion (`scenario_projection.py:644` returns the literal `()`).
   Calling it from the projection would make provenance — the surface AC3 requires to survive
   outages — fail on exactly the runs it matters most for. Decision 8b.
6. **`AuditOutcomeV1` will type-check fine while being wrong.** It is a plain dataclass field,
   not a Pydantic model, so the five-member Literal never raised even though
   `approvals.py:309` has been writing the sixth value since 4.3. Decision 11.
7. **`audit_event` has no `schedule_run_id` index.** `schema.py:583-591` creates
   `ix_audit_event_site_id` and the two partial uniqueness indexes, nothing else. Note it; do not
   add an index in a read-only story.
8. **The reader must reverse the writer's JSON coercion.** `PostgresAuditWriter` stores
   `worker_facts` and `evidence_refs` through `TypeAdapter(...).dump_python(..., mode="json")`
   (`audit.py:23-24`), so UUIDs come back as strings and `WorkerFactsV1.attempt_id` will not
   reconstruct by naive `**row` splatting.
9. **`_out`'s presented-expiry rule is not optional for provenance.** EAD-7 makes it a read-path
   invariant, not an approvals-route detail. A timeline that shows a long-overdue binding as
   `pending` contradicts the panel rendered above it on the same page.
10. **Do not gate provenance on the result query, or the result on provenance.** 4.3's review
    finding was one query removing the whole page. Decision 13 — and it must be asserted in both
    directions, because a one-directional test passes while the new failure mode ships.
11. **Regenerate the OpenAPI types; do not hand-author them.** `npm run codegen` runs the backend
    exporter first (`codegen:export` → `codegen:types`); a stale `openapi.json` produces types
    that typecheck and lie. Story 4.3 Trap 12.
12. **`npm run typecheck` is inert.** The root `tsconfig.json` declares `"files": []`; `npx tsc -b`
    is what actually type-checks. Story 4.3 Trap 13.
13. **The consequence summary is hashed and is a contract.** Provenance renders the stored
    `consequence_summary` verbatim (EAD-11). Any edit to its text changes `consequence_hash` and
    marks every live pending binding `stale` at revalidation. 4.1 Trap 7, 4.2 Trap 6, 4.3 Trap 14
    all said this — do not "improve" the wording while replaying it.
14. **A guard that cannot fail is the epic's most-repeated defect.** 4.1's review found two,
    4.2's a third, 4.3's several. Every new assertion in Tasks 2, 7, 9, 11 carries an explicit
    demonstrated-red; a passing test with no recorded red does not count (EAD-9).
15. **A down PostgreSQL makes AC4's entire proof pass by skipping.** `conftest.py:66` calls
    `pytest.skip("PostgreSQL integration service is not available")` when the admin connection
    fails — deliberately, so the suite does not hang. **AC4's only real proof is Task 10, which is
    `@pytest.mark.postgres`.** So with Docker down, `pytest` reports green while the privilege and
    cross-site assertions never executed. This is distinct from the deselection hazard under
    *Testing requirements*: deselection is visible in the summary line, a clean skip is not.
    Bring `docker-compose.yml`'s `postgres` service up first, then assert on the **count** of
    postgres-marked tests that ran — never on the suite being green.

### Honest gaps this story ships with — state them in Completion Notes

- **The agent's tool transcript is unrecoverable.** Only the approval-triggering call is
  persisted, so AC1's "typed tool proposals/results" is satisfied for one call per agent-initiated
  binding and for nothing else. Owner: Epic 5 (Story 5.1). Decision 8a.
- **The comparison is linked by reference, not replayed.** No comparison row has ever been
  persisted and EAD-8 refuses recomputation after the first promotion. Decision 8b.
- **`audit_event.evidence_refs` is empty at every write site**, so NFR32's "immutable evidence
  references" clause is met from the candidate and claim suppliers rather than from audit itself.
  Ledger entry, Task 6.
- **`initiated_by_actor_id` and `decided_by_actor_id` still hold the same principal** in practice
  — the distinction is structural until a second real user exists (EAD-9; parent Deferred).
  Provenance renders both fields regardless, so the surface is correct before the data is
  interesting.
- **A worker-initiated run-stream transition is still not distinguishable from a human one on the
  event itself.** Decision 7 settles the identity model and narrows the consequence; the residual
  `enqueue`-vs-`cancel` `actor_id` inconsistency is re-pointed to Epic 5.
- **A write fault inside TX2 writes no audit row** (Story 4.3's gap, Owner: 4.5), so a rolled-back
  promotion attempt is invisible to provenance. This is inherited, not introduced.
- **`producing_run_version` is `None` on grounding-calculator evidence**
  (`calculators.py:142`) and set only on candidate evidence (`finalize_schedule_run.py:82`), so
  claim-side evidence links carry a scenario version but no run version. Pre-existing.

### Testing requirements

- Backend tests in `backend/tests/`, `test_*.py`, never co-located. PostgreSQL-dependent tests
  carry `@pytest.mark.postgres` (`pyproject.toml:52`).
- Keep the epic's three-file split: fake-port **use-case** tests in a new
  `test_decision_provenance.py`; **router/HTTP-contract** tests in `test_approvals_api.py`;
  **real-PostgreSQL** tests in `test_approval_governance_postgres.py`.
- Assertions that live **only** in the `@pytest.mark.postgres` file are deselected from the
  default suite — Story 4.3's review caught exactly that. Every behavioural claim needs a
  default-suite assertion; the PostgreSQL file proves the **privilege and RLS** claims that
  genuinely need a real database (Task 10).
- Frontend tests co-located, Vitest + Testing Library; assert accessible names and roles, not
  class names.
- Accessibility is proven by automated coverage alone (`EXPERIENCE.md:196`).
- Every new guard needs a recorded demonstrated-red.

### Project structure notes

Additive, matching the Epic 4 Structural Seed and AR26. New files:
`backend/application/queries/__init__.py`,
`backend/application/queries/decision_provenance.py`,
`backend/application/contracts/decision_provenance.py`,
`backend/tests/test_decision_provenance.py`,
`frontend/src/api/provenance.ts`,
`frontend/src/hooks/useRunProvenance.ts`,
`frontend/src/features/provenance/ProvenanceTimeline.tsx` (+ its co-located test).

No renames. `AuditReader` goes **beside** `AuditWriter` in the existing
`application/ports/approval.py`, and `PostgresAuditReader` beside `PostgresAuditWriter` in the
existing `adapters/postgres/audit.py` — one port file and one adapter file per storage home, the
convention `approval.py` set and Story 4.3 restated for `site_baseline`.

`application/queries/` is created here as a real directory with a real module, not a placeholder.
It is the read-side sibling of `application/use_cases/`; if a later story adds a second query it
goes here, not into `use_cases/`.

### Open questions for Winston — neither blocks this story; each has a different answer deadline

Both are raised now so they are not discovered mid-implementation. **Neither may be answered
during 4.4's dev:** Q1 is a write-path change and this story writes nothing (Decision 3), and Q2
is a spine change. Answering either inside 4.4 silently widens its scope.

1. **Should `audit_event.evidence_refs` be populated?** — **Answer before Story 4.5 is created.**
   NFR32 names "immutable evidence references" as an audit obligation, and all four write sites
   pass `()` (`request_approval.py:153`, `decide_approval.py:140`, `promote_baseline.py:161`,
   `approvals.py:316`). **The deadline is set by Story 4.5's AC3** (`epics.md:1276-1279`), which
   asserts *"no audit or provenance link points to unverified evidence"* — an assertion that is
   **vacuously true** against a structurally empty tuple and cannot be made to fail by any
   mutation, which is exactly what the spine's *Verification Obligations* preamble (`:212`) and
   EAD-9 forbid. If the answer is "populate it", the change needs an **owner**: 4.5 is a proof
   story, so it is either a deliberate widening of 4.5 or a correct-course. Backstop, not
   deadline: Gate B's *Blocking regressions* row names authoritative audit (`epics.md:1523`).

2. **Does the unimplemented `comparison` `ActivityTypeV1` discriminant stay?** — **Answer before
   Story 4.6 is created**, with enough lead time to amend the spine if the answer is "implement".
   It has been declared with no dataclass, no producer, and no consumer since Story 2.3. **The
   deadline is set by Story 4.6's AC1** (`epics.md:1296-1299`), which sweeps "messages, drafts,
   runs, **comparisons**, approvals, terminal outcomes … and provenance" and requires each literal
   state to be textually and structurally distinct. The sharper form of the question:
   `EXPERIENCE.md:102`'s component table places the Comparison summary in **Chat and Results**,
   `ComparisonSummary.tsx` implements only the Results half, and the dead discriminant is exactly
   the Chat half's missing carrier. So the real choice is *"is the Chat-side comparison card in
   scope, or is it descoped and the vocabulary removed?"* — implementing it is a spine-level
   addition (a ninth `ActivityTypeV1` member plus its `STREAMED_ACTIVITY_EVENTS` listener), not a
   story change. Provenance links the comparison by reference either way (Decision 8b), so 4.4 is
   unaffected by the outcome.

3. **Carried forward from 4.1/4.2/4.3, still unanswered:** should a decision pin the *scenario*
   version as well as the binding's resource version? Provenance now renders both side by side,
   which makes the question visible to a reviewer for the first time but does not settle it. No
   story is blocked on it today.

### References

- Epic 4 spine:
  `_bmad-output/planning-artifacts/architecture/architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md`
  — *Inherited Invariants* (AD-3, AD-12, AD-15), EAD-1 (storage homes, audit append-only),
  EAD-3 (**three-role identity, attribution**), EAD-7 (**reads never write**),
  EAD-8 (**comparison fails closed**), EAD-9 (**named supplier or declared gap**),
  EAD-11 (**consequence summary replayed from one immutable row**),
  *Structural Seed* `:183, :186`, *Story → Architecture Map* `:206`, *Deferred*
- ADR-4: `.../architecture-epic-4-2026-08-27/ADR-4-consequential-workflow.md` — D2, D3, D8,
  *Consequences* `:72, :74`
- Parent spine: `.../architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` — AD-3, AD-11,
  AD-12 `:154-158`, AD-13 `:162`, AD-15, AD-20 `:208`, AD-22 + Amendment `:216-221`, AR26
- Epic and requirements: `_bmad-output/planning-artifacts/epics.md` — Story 4.4 `:1230-1256`,
  FR20 `:63`, FR21 `:65`, NFR10 `:93`, NFR32 `:137`, NFR33 `:139`, UX-DR13 `:202`,
  UX-DR22 `:220`, Release Gate
- UX: `.../ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md` — Provenance timeline `:102`,
  Evidence link `:86`, Identifier copy control `:96`, Results IA `:38`, Accessibility Floor
  `:185-196`, FR-20 coverage `:221`; `DESIGN.md:96, :140`
- Previous story: `_bmad-output/implementation-artifacts/4-3-promote-the-baseline-atomically-with-audit.md`
  — its *Unblocks* line naming this story, Decision 9 (EAD-8 guard), its **Review Findings**
  (especially the one-query-gates-the-page finding), its Traps 1, 11, 12, 13, 14, its
  *Open questions for Winston*, and its *Project Structure Notes* refusing to stub this module
- Story 4.2: `.../4-2-review-and-decide-the-exact-approval.md` — *"What Story 4.3 inherits"*
  (the inheritance-section pattern), Decision 9 (return-vs-raise), its `_out` / `_context` rules
- Story 4.1: `.../4-1-request-approval-for-one-exact-feasible-candidate.md` — the audit
  `effect_key` defect, the fail-open `pendingApproval`, the ABBA deadlock
- Domain: `docs/DOMAIN-MODEL.md` §1 (family/unit, time), §2 (what an assignment carries), §5
  (checklist) — this story computes no metric; see the note under *Facts* above
- Conventions: `docs/API.md` `:527-560`, `docs/EVIDENCE-CONVENTION.md`, `docs/TESTING.md`,
  `docs/GATE-A-RUNBOOK.md`
- Process: `_bmad-output/implementation-artifacts/epic-3-retro-2026-08-27.md` §1, §3;
  `epic-1-2-retro-2026-08-16.md` §3.2 (A1), §6.1 (A3)
- Ledger: `_bmad-output/implementation-artifacts/deferred-work.md` — the identity-model entry
  `:443` (**Owner: Stories 4.3/4.4**, closed here by Decision 7)

---

## Dev Agent Record

### Agent Model Used

OpenAI Codex (GPT-5)

### Debug Log References

- 2026-08-31 — Task 1 baseline at implementation start (HEAD `63dc6ff`, whose only delta from
  code baseline `e944914` is the already-committed Story 4.4 planning/status artifacts): backend
  default collected 1,440 total / 1,433 selected, with 1,432 passed, 0 failed, 1 skipped, and 7
  live deselected; dedicated `-m postgres` collected and actually ran 129 marked tests, with 129
  passed, 0 failed, and 0 skipped (PostgreSQL container healthy); frontend Vitest 83 files / 579
  tests passed; Playwright `--list` enumerated 62 tests in 9 files. The inherited three external
  failures did not reproduce in the default non-live run and are not attributed to this story.
- 2026-08-31 — Task 2 demonstrated-red: with the production Literal still missing
  `approval_denied`, `test_audit_outcome_contract_matches_the_database_check` failed and reported
  that exact extra database member. After adding the member, the focused file passed 6/6; the
  backend regression gate passed 1,432 with 2 skipped and 7 live deselected (1,441 total).
- 2026-08-31 — Task 3 red began as an import failure because `PostgresAuditReader` did not
  exist. Green proves explicit run/site filtering, deterministic audit ordering, typed JSONB
  rehydration, and the dependency seam; full backend regression passed 1,433 with 2 skipped and
  7 live deselected (1,442 total).
- 2026-08-31 — Task 4 red began with the absent provenance contract module. Green proves the
  nine-member union, full common identifier base, five scope-control declarations, and API
  discriminator; full backend regression passed 1,434 with 2 skipped and 7 live deselected
  (1,443 total).
- 2026-08-31 — Task 5 red began with the absent `application.queries` package. The focused
  projection/route files passed 38 tests; full backend regression passed 1,435 with 2 skipped
  and 7 live deselected (1,444 total).
- 2026-08-31 — Task 6 directly exercised both persisted evidence suppliers: candidate refs kept
  a non-null producing run version and grounded-claim refs kept their claim locator. Full backend
  regression passed 1,436 with 2 skipped and 7 live deselected (1,445 total).
- 2026-08-31 — Task 7 demonstrated-red: after mutating router registration so
  `/approvals/{approval_id}` preceded `/approvals/provenance`, the provenance request returned
  422 instead of 200. Restoring literal-first order passed the focused 40 tests. `npm run codegen`
  regenerated both OpenAPI artifacts; full backend regression passed 1,437 with 2 skipped and
  7 live deselected (1,446 total).
- 2026-08-31 — Task 8 focused fake-port tests passed 5/5 and the real PostgreSQL full-cycle
  projection passed 2/2 initiator variants, including persisted promotion before/after links.
  Full backend regression passed 1,438 with 2 skipped and 7 live deselected (1,447 total).
- 2026-08-31 — Task 9 demonstrated-red: temporarily adding `tool_args_json` to the tool item
  made both the forbidden-field architecture assertion and the route marker assertion fail.
  Restored identity-only output passed both guards; full backend regression passed 1,441 with
  2 skipped and 7 live deselected (1,450 total).
- 2026-08-31 — Task 10 PostgreSQL proof actually ran 3 focused marked tests (3 passed, 0 skipped):
  privilege truth table, refused UPDATE/DELETE attempts, and byte-identical foreign/absent 404.
  Full backend regression passed 1,443 with 2 skipped and 7 live deselected (1,452 total).
- 2026-08-31 — Task 11 demonstrated-red: temporarily importing `llm` into the query made the AST
  architecture guard fail. After restoration, the outage route and boundary tests passed 5/5;
  full backend regression passed 1,444 with 2 skipped and 7 live deselected (1,453 total).
- 2026-08-31 — Tasks 12-13: focused frontend tests passed 7/7, then the full Vitest suite passed
  581 tests in 84 files. The automated accessibility sweep exercised provenance collapsed and
  expanded at 100% and 200% zoom. Full Playwright initially exposed a prohibited `aria-label`
  on an untyped identifier container (64 passed / 2 failed); adding the semantic `group` role,
  rebuilding, and rerunning made all 66 tests pass across Chromium and Edge.
- 2026-08-31 — Task 15 final gates: backend default collected 1,453 total / 1,446 selected and
  finished 1,444 passed, 2 skipped, 0 failed, 7 deselected. With the PostgreSQL service healthy,
  the dedicated marker run collected and **actually ran 131** tests: 131 passed, 0 skipped,
  0 failed, 1,322 deselected. TypeScript build and lint passed (three inherited Fast Refresh
  warnings), architecture/changed-surface passed 99/99, Alembic reported no upgrade operations,
  and Playwright passed 66/66.

### Completion Notes List

- Task 2 closed the existing audit outcome contract drift and bound the Python Literal directly
  to the PostgreSQL CHECK vocabulary so future drift fails in the default suite.
- Task 3 added the sole new read port and a SELECT-only PostgreSQL adapter; no writer method,
  migration, schema object, or audit mutation was introduced.
- Task 4 added frozen application contracts and their explicit Pydantic response mirror without
  widening any persisted vocabulary.
- Task 5 added the pure port-composed projection, including closed membership, deterministic
  cross-stream ordering, presented expiry, three-role attribution, and non-disclosing absence.
- Task 6 replays candidate, claim, and empty audit evidence exactly as persisted and records the
  audit-local evidence gap with its later-story owner; no write site was changed.
- Task 7 added the run-keyed GET above the dynamic UUID route, explicit one-by-one response
  mapping, and the established non-disclosing schedule-run 404.
- Task 8 covers the projection matrix across fake ports, HTTP routing, and the real committed
  PostgreSQL request/decision/promotion chain.
- Task 9 proves the pending payload's arguments and transcript cannot cross the provenance API;
  only tool identity is projected.
- Task 10 proves AC4 against the live database role and RLS-backed route, not against skipped or
  fake tests.
- Task 11 proves the historical provenance path remains database-only and complete when the model
  provider is unavailable.
- Task 12 adds the independently queried Results timeline with literal outcomes, copyable stable
  identifiers, governed evidence navigation, promotion before/after versions, and allowlisted
  collapsible detail; a planted private payload marker is absent from the DOM.
- Task 13 proves list/heading/status semantics and no page-level overflow at both required zooms
  through automated axe coverage; no manual assistive-technology claim is made.
- Task 14 documents the pure provenance read and its sole problem code, closes the identity-model
  question, and records the tool-transcript, comparison-discriminant, and audit-evidence gaps with
  later owners. `docs/GATE-A-RUNBOOK.md` is unchanged.
- Task 15 completed every requested gate against the re-derived Task 1 baselines. No evidence file
  was created because this story has no measured threshold to bind.

### File List

- backend/application/contracts/audit_envelope.py
- backend/tests/test_approval_contracts.py
- backend/application/ports/approval.py
- backend/adapters/postgres/audit.py
- backend/api/deps.py
- backend/tests/test_decision_provenance.py
- backend/application/contracts/decision_provenance.py
- backend/api/schemas.py
- backend/application/contracts/approval_binding.py
- backend/api/routers/approvals.py
- backend/application/queries/__init__.py
- backend/application/queries/decision_provenance.py
- _bmad-output/implementation-artifacts/deferred-work.md
- backend/tests/test_approvals_api.py
- backend/tests/test_approval_governance_postgres.py
- frontend/openapi.json
- frontend/src/api/schema.d.ts
- frontend/src/api/provenance.ts
- frontend/src/components/ui/collapsible.tsx
- frontend/src/components/primitives/IdentifierCopyButton.tsx
- frontend/src/features/provenance/ProvenanceTimeline.tsx
- frontend/src/features/provenance/ProvenanceTimeline.test.tsx
- frontend/src/hooks/useRunProvenance.ts
- frontend/src/hooks/useDecideApproval.ts
- frontend/src/routes/ScenarioResults.tsx
- frontend/src/routes/ScenarioResultsWorkspace.test.tsx
- frontend/e2e/accessibility.spec.ts
- frontend/e2e/support/apiStubs.ts
- docs/API.md
- backend/tests/architecture/test_provenance_boundaries.py
- _bmad-output/implementation-artifacts/4-4-inspect-complete-decision-provenance.md
- _bmad-output/implementation-artifacts/sprint-status.yaml

---

## Change Log

| Date | Change |
|---|---|
| 2026-08-31 | Story created from `epics.md:1230-1256`, the Epic 4 architecture spine (EAD-3, EAD-7, EAD-8, EAD-9, EAD-11, Structural Seed), ADR-4 D2/D3/D8 and its Consequences, Story 4.3's Dev Notes, Review Findings and Open Questions, and a live audit of the codebase at `e944914`. |
| 2026-08-31 | Implemented the read-only decision provenance projection, API, Results timeline, accessibility coverage, documentation, ledger reconciliation, and full verification; moved to review. |
