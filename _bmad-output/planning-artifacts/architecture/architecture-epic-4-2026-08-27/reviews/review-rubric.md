# Rubric Review — Epic 4 Architecture Spine

- **Artifact:** `_bmad-output/planning-artifacts/architecture/architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md` (draft, updated 2026-08-27)
- **Parent:** `_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` (final)
- **Companion:** `ADR-4-consequential-workflow.md` (same folder) — cross-checked, does not resolve findings below
- **Stories judged against:** Epic 4 Stories 4.1–4.6, `_bmad-output/planning-artifacts/epics.md` lines 1136–1310
- **Verdict:** **Sound spine, approve after revision.** Divergence coverage for Stories 4.1–4.6 is strong, all spot-checked brownfield claims are true against `backend/`, and no EAD weakens a parent AD. One AD-22 bundle-widening conflict is not surfaced despite the spine's own rule requiring it, and one real cross-story divergence point (where consequence-summary *text*, not just its hash, lives) is silent.

---

## 1. Divergence coverage for Stories 4.1–4.6

| Divergence risk two independent stories could resolve incompatibly | Covered by | Assessment |
| --- | --- | --- |
| Where the three new records live; who owns them | EAD-1 | Covered; enforceable via named tables, owner modules, a partial unique index, and "no other module reads/writes the pointer" |
| First promotion vs. replacement ("no baseline") semantics | EAD-2 | Covered; `null = expects absence` with bidirectional revalidation is precise and testable |
| Actor attribution across human / worker / proposal-author | EAD-3 | Covered; also correctly discharges the Epic-4-owned Story 3.5 attribution deferral |
| Approval pause surviving reconnect/replay | EAD-4 | Covered; consistent with AD-6 and Story 4.1 AC2 |
| Terminal binding → run outcome mapping | EAD-5 | Covered; closed reason vocabulary plus additive `status_reason` is the right epic-level fix |
| Transaction bundles / double promotion | EAD-6 | Covered for promotion; gaps below (request-approval's effect key; unsurfaced AD-22 widening) |
| Expiry without a scheduler | EAD-7 | Covered in intent; enforceability gap below |
| Comparison lying after the first real promotion | EAD-8 | Covered; the hazard is real (verified in §4) and fail-closed is the right epic decision |
| Stub-proof vs. production-supplier drift | EAD-9 | Covered; the supplier table is a genuinely good device against the Epic 3 retro's recurring failure mode |

Every dimension this epic altitude owns is decided, deferred with a trigger, or an open question. Deployment/hosting absence is correct (explicit Epic 5/6 non-goal, and the Deferred table says so). Nothing in Deferred lets two Epic 4 stories diverge: each item is either guarded by a fail-closed EAD in the meantime (EAD-8), excluded by an adopted decision (no general cancellation, no revert command), or owned by a later epic.

**Missed divergence points**, detailed below: consequence-summary content home (F-2); effect key for the non-promotion bundles (F-3); rendered state of an overdue-but-untouched binding (F-4).

## 2. Findings

### F-1 (HIGH) — A third AD-22 bundle widening is not surfaced — EAD-6 / Open Questions

Parent AD-22 fixes: *"request-approval = binding + agent pause + event"* — four elements, no audit write. Epic 4's EAD-6 defines TX1 as *"pending binding + `approval_required` transition + audit + event"* — it adds an audit write the parent bundle does not enumerate. The spine's own rule states *"a local rule that weakens one is a conflict to surface, never an override"* (Inherited Invariants preamble), and Open Questions does surface two AD-22 divergences (the promote-baseline run-resume, and the unenumerated decide-rejection bundle) — but not this one. The audit addition is almost certainly correct (AD-12 requires auditing accepted mutation attempts), but per the spine's own discipline it must be listed for the parent owner to ratify, not left as a silent third divergence next to two that were caught.

### F-2 (HIGH) — Consequence-summary *content* has no decided home — EAD-1/EAD-4, Stories 4.1/4.2/4.4

The parent's normative minimum for `ApprovalBindingV1` carries only a **consequence-summary hash**, and EAD-1 restates governance's table as holding "the full `ApprovalBindingV1`" — i.e., still only the hash. But three stories need the summary's actual text: Story 4.2 must render it before Approve/Reject; EAD-4 requires reconnect to reconstruct "the exact binding" and its presentation from persistence *alone*; Story 4.4 must replay the "concise application-owned decision summary" in provenance. Where the text lives is unstated. Note this is **not** the same field as `ProposalV1.consequence_summary` (verified at `backend/application/contracts/proposal.py:87` and `activity.py:82,99`) — that field describes the constraint-change proposal, not the specific "candidate X replaces baseline Y" consequence a promotion binding names. Three independently-built stories could each pick a different, incompatible home: 4.1 could embed it in the persisted-event payload, 4.2 could recompute it from the live comparison at render time (breaking the hash guarantee the moment inputs shift), 4.4 could expect it verbatim on the audit envelope. ADR-4 does not resolve this either (checked in full — its D1–D8 and Open Questions are silent on summary content, only ever the hash). Decide one home (e.g., a summary column/payload on `approval_request` beside its hash, verified against the hash on write) or promote this to an explicit Open Question with an owner.

### F-3 (MEDIUM) — Effect key is fixed only for the promotion bundle — EAD-6

EAD-6's title promises "one effect key each" for the three bundles but only names one: `approval_id` for decide-approve. On inspection, reusing `approval_id` for **decide-reject/expire/stale** is actually safe — AD-12's success-audit uniqueness is on the triple `(site_id, effect_key, outcome)`, and `outcome` (`consumed` vs. `rejected`/`expired`/`stale`) already disambiguates those bundles from promotion and from each other, so this part of the "gap" resolves once you trace the uniqueness rule (worth a one-line note in the spine so a story author doesn't have to re-derive it). The real gap is narrower than it first appears but still real: **request-approval** creates the pending binding, so `approval_id` cannot be its effect key at the moment that transaction runs (the row is being created inside it) — EAD-6 never names what does serve as TX1's effect key for its own success-audit row. Story 4.1 built independently could pick the command's own idempotency key, a client-supplied token, or something else, with no fixed answer to check against.

### F-4 (MEDIUM) — EAD-7's rule is not enforceable exactly as written — EAD-7, Stories 4.2/4.6

Two soft spots: (a) *"render-time state read that mutates"* — nothing elsewhere in the spine or parent describes a read endpoint that opens a write transaction, so a story author cannot tell which reads this phrase is supposed to apply to; as written it either quietly mandates a new class of endpoint or is unenforceable filler. (b) The overdue-but-untouched limbo case has no rendered identity: the rule says such a binding "must present as expired," but the paused `agent_run.status` is still literally `approval_required` with `status_reason` still null (materialization happens only on first touch). Story 4.2's decision surface and Story 4.6's literal-state matrix — built independently — can disagree on what to show for that run: still-pending, already-expired, or an invented third label the accessibility floor is supposed to prevent. Name the concrete touch points that trigger materialization, and add the limbo presentation explicitly to the closed state vocabulary (or to the 4.6 matrix) so it isn't invented per-surface.

### F-5 (LOW) — Reference hygiene

- **Story→Architecture Map vs. frontmatter/Inherited Invariants.** The map cites parent AD-3 and AD-14 for Story 4.2, and AD-3, AD-11, AD-12, AD-15 for Story 4.4 (lines 179, 181) — but the frontmatter `binds` list (line 11) and the Inherited Invariants table (lines 34–46) include neither AD-3, AD-14, nor AD-15. A story author following only the Inherited Invariants table would miss all three.
- **EAD-5's `approval_stale` reason vs. AD-7's drawn edge.** Parent AD-7's diagram labels the `approval_required → agent_cancelled` edge "rejected or expired" (line 100). EAD-5 correctly uses the edge but extends its cancellation-reason space to include `approval_stale` too. The transition itself is unchanged ("used exactly as drawn" holds), so this is annotation-only, but given the spine's discipline about surfacing anything that isn't a pure restatement of the parent, it deserves a one-line mention in Open Questions rather than silence.

## 3. Parent-conflict check

- The two conflicts the spine claims to surface **are** surfaced in Open Questions — verified by direct comparison of AD-22's text against EAD-6's promote-baseline bundle (missing run-resume) and against the absent decide-rejection enumeration.
- No EAD weakens a parent AD: EAD-2 refines AD-9/AD-10's null-baseline semantics without loosening them; EAD-5 stays inside AD-7's drawn graph; EAD-6 implements AD-8/AD-10/AD-12's revalidation, rollback-to-pending, and both audit-uniqueness rules faithfully; EAD-7 respects AD-10's terminal-expired outcome without introducing a runtime AD-18 would forbid. The only contradiction-class issues found are the unsurfaced widenings in F-1 and F-5b.

## 4. Brownfield spot-checks (all pass)

| Spine claim | Verified at |
| --- | --- |
| `scenario_catalogue`'s baseline field is `literal(None, type_=String)` with no backing storage | `backend/adapters/postgres/scenario_catalogue.py:116-118,140` |
| `ck_schedule_run_candidate_completed` guards candidate-only-when-`solver_completed` | `backend/adapters/postgres/schema.py:449` |
| `policy_version` constant is `one-user-mvp-v1` (Story 2.5) | `backend/application/capabilities/registry.py:11` |
| `persisted_event` stream CHECK (`ck_persisted_event_stream_owner`) has exactly two arms, keyed on `conversation_id`/`schedule_run_id`; `agent_run_id` is a separate nullable column not part of the CHECK | `backend/adapters/postgres/schema.py:310-334` — the spine's conversation-stream convention (`stream_id = conversation_id`, `agent_run_id` set) is compatible with the CHECK as written *today*; the Open Question asking to re-verify at Story 4.3 is honest (nothing changes it before then) but was actually resolvable now |
| `agent_run` status CHECK already contains `approval_required` and `agent_cancelled`; no reason column exists yet | `backend/adapters/postgres/schema.py:298-308` — confirms EAD-5 is additive (only `status_reason` is new) |
| `persisted_event.actor_id` is `NOT NULL` FK to `app_user` (no fabricated system-user identity) | `backend/adapters/postgres/schema.py:321` |
| `auth.resolve_session` exists as the in-transaction session→actor supplier | `backend/adapters/postgres/identity.py` (`resolve_session()` calling `auth.resolve_session`) |
| Worker-driven events attribute the run *requester*, not the proposal author (Story 3.6 fix EAD-3 cites) | `backend/api/routers/schedule_runs.py` (enqueue uses session actor) → `backend/adapters/postgres/schedule_run.py` (`_actor_for_run` reads `job_queue.actor_id` first) |
| EAD-8's hazard is real: `get_baseline_assignments` is hardcoded to return `()` regardless of scenario, and `calculate_comparison` drains it as the baseline side of every comparison | `backend/application/scheduling/comparison.py:171`; `backend/adapters/postgres/scenario_projection.py` |
| No `approval_request`, `site_baseline`, or `audit_event` table, and no `ApprovalBindingV1`/`AuditEnvelopeV1` contract module exist yet | full `schema.py` read; `backend/application/contracts/` glob |

No contradiction found between any spine claim and the current codebase.

## 5. Over-specification check

Largely clean for an epic-altitude spine. The bundle contents (EAD-6), the `status_reason` column (EAD-5), and the supplier table (EAD-9) are genuine cross-story invariants and belong here. The Structural Seed file list and the two diagrams stay at "converge on these homes" granularity, not per-story detail. The Verification Obligations section reads like a Story 4.5 test plan, but 4.5 *is* the dedicated proof story and the Epic 3 retro explicitly mandates a proof matrix as a Story 4.1 prerequisite — acceptable at this altitude provided story files reference it rather than re-copy it verbatim.

## 6. Required changes before adoption

1. Add the TX1 audit-write widening (F-1) and the EAD-5 stale-edge annotation (F-5b) to the surfaced AD-22/AD-7 conflict list in Open Questions.
2. Decide, or explicitly open-question with an owner, the consequence-summary *content* home (F-2) — distinct from the existing `ProposalV1.consequence_summary` field.
3. Name the effect key for the request-approval bundle's own success-audit row (F-3); the decide-bundles' shared reliance on `approval_id` + differing `outcome` is already sound and just needs a one-line note.
4. Make EAD-7's materialization touch points concrete, and add the overdue-but-untouched presentation to the closed state vocabulary or the Story 4.6 matrix (F-4).
5. Reconcile the Story→Architecture Map's AD-3/AD-14/AD-15 references with `binds` and Inherited Invariants (F-5a).
