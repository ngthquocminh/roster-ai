# Story 5.12: Prove the Draft Lifecycle in Live Conversations [Corrective Insert]
---
baseline_commit: 3d747f7 (Story 5.11 merged; story created at 8a85f4f, re-verified at 3d747f7)
depends_on: 5-11-keep-one-working-draft-per-conversation (done; merged into feat/draft-lifecycle)
---

Status: in-progress

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

Date: 2026-10-01
Origin: `sprint-change-proposal-2026-09-30.md` (approved by Minh 2026-09-30), implementing
`docs/superpowers/specs/2026-09-28-draft-lifecycle-design.md` §5.2 after Story 5.11.
Priority: Epic 5; before the next Gate B assessment.

> **Re-verified against Story 5.11's code (2026-10-01, `3d747f7`).** The story was first written
> at `8a85f4f`, before 5.11 existed, from the design spec. After 5.11 merged, every 5.11 name used
> here was checked in code (F11, F16) and matched; the updates are listed under "Re-verification
> after 5.11" below. Both stories ship on one branch, `feat/draft-lifecycle`.

## Story

As a planner,
I want real-provider conversations to show that chat edits update one draft and that discard and promotion end it,
so that the lifecycle holds with the configured model, not only in deterministic tests.

[Source: `_bmad-output/planning-artifacts/epics.md` — Story 5.12]

## Acceptance Criteria

Verbatim from `epics.md`. Tasks cite these numbers.

1. **Given** the per-turn expectation grader
   **When** the new code checks `draft_updates_turn: n` and `draft_state_is: <state>[/<ended_by>]` are registered
   **Then** each has unit tests in `tests/test_live_conversation_expectations.py`, and `Bindings.draft` records the version ordinal. (spec §5.2)

2. **Given** scenarios A–D and the new scenario E (7 turns: create, add, remove, "undo that", "start over with just Z", "throw this draft away", then a new request)
   **When** the suite is authored
   **Then** B:6 and C:9 assert `draft_updates_turn`, B:10 asserts `draft_state_is: applied`, every E turn carries authored `expect` checks, and `REQUIRED_SCENARIOS` is `{A: 6, B: 12, C: 12, D: 6, E: 7}`.

3. **Given** the committed code of Stories 5.11 and 5.12
   **When** the suite runs one clean pass per scenario plus three repetitions on the configured provider and the real stack
   **Then** `evidence/story-5.12/live-conversation-journeys.json` is generated through `backend/scripts/evidence_binding.py` and committed separately from the code, and `backend/evals/baselines/live-conversations.json` and the drop-check floor are re-derived from it with `derive_live_conversation_baseline.py` (129 executed turns)
   **And** no counted run makes a false claim, including a claimed undo. Missing, partial or stale evidence blocks Gate B's `live_conversation_journeys` row. (Gate B, EVIDENCE-CONVENTION)

## Facts this story depends on

Each is written down somewhere citable. Read the source, not this paraphrase, when in doubt.

| # | Fact | Source |
|---|---|---|
| F1 | A turn with an `expect` list, under a `typesafe:` judge, is graded only by its checks: code checks over the visible reply, its activity, or the saved draft, plus narrow Jev yes/no questions. Verdict: any `fail` → fail; else any `unbound`/`pending` → incomplete; else any `uncertain` → needs_review; else pass. | `backend/evals/live_conversations/expectations.py` module docstring, `verdict_from_checks`; `handover-live-eval-per-turn-expectations.md` "How grading works now" |
| F2 | Checks run **as of the reply**, before the turn's own `actions_after`. | `runner.py:290` comment, and the `evaluate(...)` call before the `for action in turn.actions_after` loop (`runner.py:302`) |
| F3 | B:10 has no `actions_after`. The `approve` that promotes the run is B:9's action, so at B:10's reply the promotion (and, after 5.11, `applied`) has already committed. | `scenarios.json` B:9/B:10 |
| F4 | The persisted draft is read **only** when the turn's activity is `draft`, through `ApplicationConversation.latest_draft()`, which raises `required_draft_not_current` unless the proposal is `active` and not stale. It therefore cannot read an ended draft. | `http_client.py:103-114`, `runner.py:277-279` |
| F5 | A `draft` activity's visible reply has **no prose**: `visible_activity` returns only ids, approval fields and `consequence_summary`. So draft turns are graded by code checks; a judge question about the reply's wording on a draft turn has nothing to read. B:4, B:6, C:8, C:9 already follow this. | `runner.py:184-195` (`visible_activity`) |
| F6 | `Bindings.draft` is the **last** saved draft (overwritten each draft turn) and is the judge fact `draft`. Nothing records which proposal an earlier turn saved. | `expectations.py:199-202`, `capture_draft` |
| F7 | `behavioral_digest` covers agent model, judge model, reasoning effort and the override's `environment` maps. **It does not cover the agent instructions or the scenarios.** | `backend/evals/live_conversations/configuration.py` — `behavioral_digest` body |
| F8 | The drop check's Tier 3 sums only turns the committed baseline measured, against the hand-set `AGGREGATE_FLOOR` (100 for 108 turns: historical 3/90 rate scaled, λ 3.6, ~1.2% false alarms). Tier 1 and Structural also read only the baseline's turns/scenarios. A new scenario is invisible to the gate until the baseline is re-derived. | `backend/scripts/live_conversation_drop_check.py` — `AGGREGATE_FLOOR` comment, `tier_1`, `tier_3`, `structural_check` |
| F9 | The live-required tool inventory includes `<capability>:invoke` for **every installed module whose feature policy the grant composition accepts**; `chat_grantable_names` grants every installed module's policy. Once 5.11 installs `scheduling_draft_discard`, `scheduling_draft_discard:invoke` is live-required, and only a live discard turn (E:6) can cover it. Its manifest error codes are deterministic-only. | `evals/live_conversations/inventory.py` — `capability_inventory`, `chat_grantable_names`, `_DETERMINISTIC_MARKERS`; `evidence.py` — `build_coverage` |
| F10 | The live stack's override sets no `SCHEDULING_*_ENABLED` key; the stack runs every capability flag at its `settings.py` default. `scheduling_draft_discard_enabled` defaults to **True**, so the live stack grants discard with no override edit. | `evals/live_conversations/compose.override.yml`; `backend/settings.py` — `scheduling_draft_discard_enabled`, `_flag("SCHEDULING_DRAFT_DISCARD_ENABLED", …, True)` |
| F11 | 5.11 contract names used here, as shipped: `ProposalStateV1 = active\|rejected\|applied`; `ProposalEndedByV1 = planner\|assistant\|system`; `GET /api/v1/proposals/{id}` (`ProposalOut`) carries `version_ordinal`, `ended_by`, `applied_version_ordinal`, all **nullable** ("null on rows written before the lifecycle existed"; every fresh read fills `version_ordinal`). An agent discard is applied at finalize **whatever the model finally said**, ends the draft `rejected`/`assistant`, and creates no new activity type. Promotion sets `applied` with `ended_by='system'`. Every agent draft appends a version of the one working draft. | `backend/application/contracts/proposal.py`; `backend/api/schemas.py` — `ProposalOut`; `backend/api/routers/proposals.py:57-59`; `backend/application/use_cases/execute_turn.py` — `resolve_discard`; `finalize_agent_run.py`; spec §2.4 (SQL) |
| F12 | Fixture entities used by scenario E (from `data/contract/sample_tiny_input.projection-v1.json`): Priya Nair `13270C88-FC92-4927-9651-01ED72F79203` (qualified for Main Pick); Arjun Patel `B51E9C83-4170-4DB4-9379-004C44B6B8EA` (qualified for Main Despatch); tasks Main Pick \| Order Picker M02 `31DFD696-06C5-490D-8E09-6E7715EFE3A0`, Chiller Pick \| Order Picker C02 `99260066-B32A-423D-97A1-8A649BABBAAD`, Main Despatch \| Loader M03 `3C1950FE-0C75-48AB-95B7-5C58909A0CCE`. The fixture is governed and immutable (Story 1.1). | the projection file; `_bmad-output/implementation-artifacts/1-1-establish-governed-fixture-history.md` |
| F13 | Evidence order: commit code → measure on a clean tree → generate through `evidence_binding.py` → commit evidence separately. Never hand-type evidence or the baseline. | `docs/EVIDENCE-CONVENTION.md` "The rule" |
| F14 | Precedent for a re-measurement: the evidence commit carries the evidence file **and** the re-derived baseline (`3cc57c2`, `8c06bfb`); the floor and the gate tests' pinned totals follow in a separate code commit (`4922165`). | `git show --stat 3cc57c2 4922165` |
| F16 | 5.11's shipped instructions: "There is no undo tool. When the planner says 'undo': if the request names a constraint, remove or change that constraint with scheduling_draft; otherwise ask which one. Never claim an undo happened." "Start over with just X" is `scheduling_draft` with only X, never discard. After a discard, prose says e.g. "Discarded your draft (v3)". The discard tool's error codes are `no_working_draft`, `draft_changed_this_turn`, `budget_exhausted`, `draft_discard_failed`, all deterministic-only in the inventory, which measures 141 operations, 38 live-required and 103 deterministic at `3d747f7`. | `backend/agent/scheduling_instructions.py` — "Discarding a draft"; `application/capabilities/scheduling_draft_discard.py` — `ERROR_CODES`; `capability_inventory()` run at `3d747f7` |
| F17 | 5.11 authored a live smoke case it did not run: `discard-working-draft` (`scheduling_draft_discard`, precondition `baseline`, "Throw away my current draft.", expected `agent_response`). It states "it is not run until Story 5.12 owns live runs". | `backend/evals/live_conversations/smoke_cases.py`; 5.11 story Decision 6 |
| F15 | **Domain model.** This story touches no metric, demand row or assignment rule. Scenario E's `set_min_workers_per_task` is a draft constraint, not a metric. The metric checks of C:3–C:6 are not edited. If a live failure leads into a metric, read `docs/DOMAIN-MODEL.md` §3 first and do not re-derive the family/unit rule. | `docs/DOMAIN-MODEL.md` §3, §5 |

### Correction to the design spec (F7)

Spec §5.2 says "The §4 instruction changes move `behavioral_digest`, so A–D are re-measured too."
That is not what the code does (F7): the instructions are not in the digest. **A–D are still
re-measured**, for these reasons:

- Gate B's `live_conversation_journeys` row needs evidence bound to the current code, and the 5.7
  evidence binds `8f35907`, which predates 5.11's lifecycle, tools and instructions (AC3: "stale
  evidence blocks").
- 5.11 changes what the agent does on B and C's draft turns (update instead of mint) and the
  wording of B:10's baseline answer.
- The baseline must contain E's turns, or the gate never watches them (F8).

The drop check against the **current** 108-turn baseline therefore still compares (same
`behavioral_digest`), and Task 9 uses that as a free regression signal on A–D. Record this
correction in the completion notes; do not edit the approved spec. Story 5.11 found the same thing
independently (its creation finding C15) and handed the correction to this story in
`deferred-work.md` ("Deferred from: Story 5.11 creation", the `behavioral_digest` entry). Task 11
closes that ledger entry.

## Decisions

Each Decision states what its mechanism does **not** cover.

**D1 — Four new code check kinds, not two.** AC1 names `draft_updates_turn` and `draft_state_is`.
Spec §5.2's own wording for scenario E needs two more that no existing kind can express exactly:
E:3/E:5 "`draft_has` the survivor only" needs a count, and E:7 "a new `proposal_id`" needs a
different-proposal check.

| Check | Fields | Passes when |
|---|---|---|
| `draft_updates_turn` | `turn` (earlier turn) | this turn's persisted draft has the same `proposal_id` as turn *n*'s recorded draft and a strictly higher `version_ordinal` |
| `draft_state_is` | `value`: `"<state>"` or `"<state>/<ended_by>"` | the conversation's newest draft (D3) has that `state`, and, when given, that `ended_by` |
| `draft_constraint_count` | `n` | this turn's persisted draft holds exactly `n` constraints |
| `draft_is_new` | none | this turn's persisted draft has `version_ordinal` 1 and a `proposal_id` that no earlier turn's recorded draft had |

All four are positive checks (none joins `NEGATIVE_CHECKS`). `draft_updates_turn`,
`draft_constraint_count` and `draft_is_new` read this turn's persisted draft (`ctx.draft`), so
they **fail** on a turn whose activity is not a draft. `draft_state_is`'s `value` is validated at
load time: state ∈ {`active`, `rejected`, `applied`}, `ended_by` ∈ {`planner`, `assistant`,
`system`}. An unknown value is refused, like every other authoring slip.
*Does not cover:* whether two versions differ in content (spec D7: no diff), or what an ended
draft's constraints were.

**D2 — Per-turn draft identity in `Bindings`.** `Bindings` gains `drafts: dict[int, dict]`.
`capture_draft` records `{proposal_id, version_ordinal}` under the turn that saved it, and adds
`version_ordinal` to `Bindings.draft` (AC1). `as_of(turn)` carries only the `drafts` entries
recorded before `turn`. Because `capture_draft` runs before `evaluate` in the same turn
(`runner.py:279` before `:291`), `draft_is_new` must compare against `as_of(ctx.turn).drafts`, never
against `drafts` itself. A turn *n* with no recorded draft makes `draft_updates_turn: n` raise
`Unbound('draft_turn_<n>')`, so the turn is `incomplete`. Turn *n*'s own failure already fails
the scenario, so no failure is lost.
A persisted draft without an integer `version_ordinal` is a contract break, not a model error.
`capture_draft` raises `IncompleteConversationRun('draft_version_ordinal_missing')`, following the
`candidate_payload_malformed` precedent (`runner.py:59-81`).
*Does not cover:* a turn that drafted twice. Only the cited draft is persisted (spec §2.1), and
the harness sees one activity per turn.

**D3 — `draft_state_is` reads the newest draft activity's proposal, without the active guard.**
`ApplicationConversation` gains `newest_draft_proposal()`. It reads the timeline, takes the last
`draft` activity, and returns `GET /api/v1/proposals/{proposal_id}`, or `None` when the
conversation has no draft activity. It keeps the existing `timeline_truncated` refusal.
`latest_draft()` becomes `newest_draft_proposal()` plus its existing guards
(`required_draft_missing`, `required_draft_not_current`), and its behaviour is unchanged. The
runner calls `newest_draft_proposal()` only for a turn whose `expect` contains `draft_state_is`.
It passes `{proposal_id, state, ended_by, version_ordinal}` to a new `TurnContext.draft_state`
field and records the same dict as `verified['newest_draft_state']` for diagnosis. `None` fails
the check.
Because checks run before the turn's own actions (F2), `validate_scenarios` refuses a
`draft_state_is` on any turn that has `actions_after`. That closes the gap structurally rather than
documenting it. B:10 and every E turn have no actions, so nothing authored is refused.
*Does not cover:* the state of an older proposal once a newer draft activity exists. At E:7 the
check reads the new draft, not the one discarded at E:6. E:6 is where the discard is proved.

**D4 — Scenario E, authored exactly as below.** The text names fixture entities (F12) so the turn
needs no lookup, and the checks use literal record ids, which `draft_has` already accepts (it
resolves templates only). Each turn's `obligation` is a one-sentence restatement of its intent.
Every E turn except E:4 and E:6 sets `requires_persisted_draft: true`. Judge wording is
**initial**; Task 6 validates it before any paid run.

| Turn | `user` | `expect` |
|---|---|---|
| E:1 | In a draft, keep Priya Nair off the Main Pick task. | `activity_is: draft`; `draft_has` `exclude_worker_from_task` worker Priya, task Main Pick; `draft_constraint_count: 1`; `draft_state_is: active` |
| E:2 | Also cap Priya Nair at 30 hours a week. | `activity_is: draft`; `draft_updates_turn: 1`; `draft_has` the E:1 exclusion; `draft_has` `set_max_hours` worker Priya, `max_hours` 30.0; `draft_constraint_count: 2` |
| E:3 | Remove the Main Pick exclusion and keep only the hours cap. | `activity_is: draft`; `draft_updates_turn: 1`; `draft_has` `set_max_hours` worker Priya, 30.0; `draft_constraint_count: 1` |
| E:4 | Undo that. | per D5 |
| E:5 | Start over with just this: at least two workers on Chiller Pick. | `activity_is: draft`; `draft_updates_turn: 1` (replaced, not discarded); `draft_has` `set_min_workers_per_task` task Chiller Pick, `n` 2; `draft_constraint_count: 1` |
| E:6 | Throw this draft away. | `draft_state_is: rejected/assistant`; judge want=true "Does `reply` tell the planner the draft was discarded?"; judge want=false "Does `reply` say a new draft was created, or that the discarded draft can still be run?" |
| E:7 | Now draft a change keeping Arjun Patel off Main Despatch. | `activity_is: draft`; `draft_is_new`; `draft_state_is: active`; `draft_has` `exclude_worker_from_task` worker Arjun, task Main Despatch; `draft_constraint_count: 1` |

Edits to existing turns (AC2): B:6 adds `draft_updates_turn: 4`; C:9 adds `draft_updates_turn: 8`;
B:10 adds `draft_state_is: applied` and keeps all five existing checks. No other A–D expectation
changes.
*Does not cover:* the planner card's edit path. Card edits create no activity and are 5.11's
deterministic tests. It also does not cover the four finalize races, which a single sequential
harness cannot produce and which are 5.11's AC2.

**D5 — E:4 accepts a clarification or a re-add, never a claimed undo.** The spec contradicts
itself here. §5.2 says "no draft change" for E:4, then accepts "(clarifies, or restores by
re-adding the named constraint)", while §4 instructs "if the request names a constraint, remove or
change that constraint; otherwise ask which one". "Undo that" right after a single removal has one
reasonable reading (put the exclusion back), so failing a re-add would be a false fail on the
behaviour a planner wants. 5.11's shipped instruction (F16) asks for a clarification here, since
"undo that" names no constraint, so a clarification is the expected outcome and a re-add is
tolerated. Graded as:
- judge want=true `handles_undo`, facts `[events, draft]`: "The planner asked to undo their previous
  change, which removed a constraint (see `facts.events`). Does `reply` either ask which constraint
  to restore or change, or is it a saved draft that again contains the removed constraint
  (`facts.draft` is the draft as it now stands)?"
- judge want=false `claims_undo`: "Does `reply` say it undid a change, or that it reverted or
  restored the draft to an earlier version?"
- `mentions_none` `says_undid`: `["undid", "reverted the draft", "rolled back the draft",
  "restored the previous version"]`.

On a re-add, F5 means the reply is a draft activity whose prose is empty, so `handles_undo` decides
from `facts.draft`. **Stop condition:** if Task 6's offline replay cannot separate a correct re-add
from a re-add of the wrong constraint (both must fall outside the 0.30–0.70 band, on the right
sides), stop and ask Minh. Do not loosen the threshold, and do not drop the case.
*Does not cover:* whether the re-added constraint is identical in every argument. The judge checks
that it is the removed constraint, not that its values match exactly.

**D6 — `Bindings.events` is unchanged.** No version numbers and no discard event are added to the
event log. B:12's `claims_unhappened` judge reads `facts.events` and last scored 0.78
(handover "Gotchas"), and no E turn summarizes the conversation. Changing that input would risk a
regression on B:12 for no grading gain.
*Does not cover:* a future summary turn after a discard, which would need a discard event first.

**D7 — Drop-check floor for 129 turns: `AGGREGATE_FLOOR = 120`.** This is the same method as the
existing constant (F8): the historical 3/90 failure rate scaled to 129 turns gives λ 4.3, and
P(≥10 failures) = 1.29%, the nearest to the current 1.17%. Floor 120 means "fail below 120
passed". It holds only if the re-derived baseline records `total_executed` 129. If it records
anything else, recompute it the same way and state the arithmetic in the constant's comment.
*Does not cover:* single-turn breakage. That is Tier 1's job, unchanged.

**D8 — Commit sequence (F13, F14).**
1. Code commit(s): Tasks 1–5, and the doc text that does not depend on measured numbers. The
   default suite is green, and the committed baseline is still the 108-turn one.
2. Measure on a clean tree (Task 8).
3. Evidence commit: `evidence/story-5.12/live-conversation-journeys.json` plus the re-derived
   `backend/evals/baselines/live-conversations.json`.
4. Code commit: `AGGREGATE_FLOOR`, `SOURCE_EVIDENCE` → story-5.12, `evidence.py`'s default
   `--output` → story-5.12, the gate tests' pinned totals, and measured numbers in the docs.

Between 3 and 4 the default suite is red (`baseline_matches_source` still points at the 5.7 file).
That is why 3 and 4 are made together, and nothing is pushed between them (F14 precedent). Story
5.7's evidence file stays untouched as history.
*Does not cover:* resuming after a failed recorded run. Any fix moves HEAD, so the run is
re-measured from step 2. `--resume` refuses mixed code by design (`suite.py`).

**D9 — Product fixes found by live runs are in scope, contracts are not.** When a live E or B
failure traces to 5.11's lifecycle or instruction behaviour, fix the root cause in the owning code
and add a deterministic regression test (the Story 5.6 AC5 pattern). Re-pin `TODAYS_PROMPT_SHA256`
in `tests/test_turn_routing.py` deliberately on any instruction edit. **Stop and ask** before
changing a 5.11 contract (state set, `ProposalViewV1`, RFC 7807 codes, the model view), an approval
rule, or an existing check kind's semantics, or before rewording a judge question that is not
part of this story.
*Does not cover:* reliability flakes with no false claim. Those go through `--accept-finding`, and
only with Minh's explicit approval of the exact turn.

**D10 — Dataset identity stays; binding prose follows the scenario set.** `scenarios.json` keeps
`schema_version` "2" (the loader requires it), `case_id` and `case_version`, because the dataset
binding is a digest of the file. Scenario D was added the same way (`40c29fb`). In `evidence.py`,
the `application` prose names "Story 5.7 live conversation suite, extended by Story 5.12", and the
`solver` prose names Scenarios A, C, D and E as solver-free.
*Does not cover:* historical evidence. It is never rewritten.

**D11 — The discard capability is granted on the live stack with no override edit (F9, F10).**
Verified at `3d747f7`: the flag defaults to True and the override sets no `SCHEDULING_*` key, so
`compose.override.yml` stays unchanged. `behavioral_digest` therefore matches the committed
108-turn baseline, and Task 9's comparison runs rather than being refused. Do not add the flag to
the override, because that would change the digest for no behavioural gain.
*Does not cover:* the flag in `.env.example` or `docs/CONFIGURATION.md`. 5.11 already documented
it there (proposal F5).

## Tasks / Subtasks

Phases are ordered. Do not start a phase before the previous one's exit condition holds.

### Phase A — prerequisites and harness code (keyless)

- [x] **Task 0 — Record the starting point** (all ACs)
  - [x] The 5.11 names in F11, F16 and D11 were verified at `3d747f7`. If HEAD has moved past it in `backend/application/contracts/proposal.py`, `api/schemas.py`, `scheduling_draft_discard.py` or `settings.py`, re-check those names; a mismatch → stop and ask.
  - [x] Starting counts: the backend default suite was 2803 passed / 2 skipped against PostgreSQL 18 (5.11's review record). The live-eval subset (nine `test_live_conversation_*.py` files) was 263 passed at `3d747f7`. Re-run the default suite once and record the counts in the completion notes.

- [x] **Task 1 — Register the four check kinds** (AC1; per D1)
  - [x] `expectations.py`: add to `CODE_CHECKS` and `_FIELDS`. Implement them in `code_check` and validate the `draft_state_is` value vocabulary in `validate_expectation`.
  - [x] `TurnContext` gains `draft_state: dict | None = None` (D3).

- [x] **Task 2 — Per-turn draft identity** (AC1; per D2)
  - [x] `Bindings.drafts`, `capture_draft` recording plus `version_ordinal` on `Bindings.draft`, `as_of` carrying `drafts`, and the `draft_version_ordinal_missing` refusal.

- [x] **Task 3 — Read the newest draft's state** (AC1; per D3)
  - [x] `http_client.py`: `newest_draft_proposal()`, with `latest_draft()` re-expressed over it and its behaviour unchanged.
  - [x] `runner.py`: read it only for turns that carry `draft_state_is`, and fill `TurnContext.draft_state` and `verified['newest_draft_state']`.
  - [x] `cases.py` `validate_scenarios`: refuse `draft_state_is` on a turn with `actions_after` (D3).

- [x] **Task 4 — Author scenario E and the three turn edits** (AC2; per D4, D5)
  - [x] `scenarios.json`: append E, edit B:6, C:9, B:10. Round-trip the file as bytes with `json.dumps(data, indent=2, ensure_ascii=False) + '\n'` so it keeps LF line endings (handover "Gotchas"; on Windows, Python's `write_text` writes CRLF).
  - [x] `cases.py`: `REQUIRED_SCENARIOS = {'A': 6, 'B': 12, 'C': 12, 'D': 6, 'E': 7}`.
  - [x] `evidence.py` binding prose per D10.
  - [x] `scripts/derive_live_conversation_baseline.py`: make the `note` text name no story. For example: "A projection of the committed live-conversation measurement named by source_evidence_path, not a second measurement…". The module docstring follows suit, and `SOURCE_EVIDENCE` stays 5.7 until D8 step 4.

- [x] **Task 5 — Unit tests** (AC1, AC2)
  - [x] `tests/test_live_conversation_expectations.py`: for each new kind, a passing case and each way it fails. Cover `draft_updates_turn` with the same proposal at an equal or lower ordinal, a different proposal, a non-draft turn, and an unrecorded turn *n* → `unbound`. Cover `draft_state_is` with state-only, state/ended_by, a wrong ended_by, and `None`. Cover `draft_is_new` against a proposal recorded earlier, a recording made in the same turn (must not count; D2), and `version_ordinal` ≠ 1. Cover `draft_constraint_count`. Add loader refusals: an unknown state or ended_by, missing fields, extra fields, and `draft_state_is` on a turn with `actions_after`. Add `Bindings.drafts` with `as_of`, the `draft_version_ordinal_missing` refusal, and `Bindings.draft` carrying `version_ordinal`.
  - [x] Runner integration through `_Scripted`/`FakeApp`. `FakeApp` gains `newest_draft_proposal()`, and its `latest_draft()` returns a `version_ordinal`. Prove the state is read only for `draft_state_is` turns, and that an E-like sequence of create, update, discard and new grades as expected.
  - [x] `tests/test_live_conversation_execute_prefix.py`: client tests for `newest_draft_proposal()`: no draft → `None`; an ended proposal is returned, not refused; a truncated timeline still raises. Existing `latest_draft` tests stay green unchanged.
  - [x] Update `test_every_scenario_carries_expectations_on_every_turn` to `'ABCDE'`, and `tests/test_live_conversation_reporting.py`'s pinned `required_scenarios_per_run`/`required_user_turns_per_run`/`clean_scenarios` to 5/43/A–E.
  - [x] Exit: the live-eval subset and the default backend suite are green (at creation, the seven live-eval files gave 253 passed in 24 s at `8a85f4f`). Commit (D8 step 1).

### Phase B — validation before spending (cheap first)

- [x] **Task 6 — Validate the new judge questions offline, with real Jev** (AC3; per D4, D5)
  - [x] Adapt `_bmad-output/implementation-artifacts/live-eval-replay/replay_one_turn_variant.py` (it is B-specific; rebuild E's bindings and events by hand). Each run costs under $0.001.
  - [x] E:4: grade (a) a clarifying question, (b) a re-add whose `facts.draft` holds the exclusion again, (c) a re-add holding a different constraint, (d) prose "I've undone that". (a) and (b) must pass, and (c) and (d) must fail. Otherwise apply D5's stop condition.
  - [x] E:6: a truthful discard confirmation passes; "I've created a fresh draft" fails; "the draft is still available to run" fails.
  - [x] Reword only on evidence: read the full reply and the facts first (handover "Lessons"). Ask about actions, not "anything not in facts".

- [x] **Task 7 — Single-scenario live smokes** (AC3; allowed without asking under the handover rule)
  - [x] Start Docker Desktop. Run `--scenario B --repetitions 1` first: B:10 is the riskiest turn (proposal §3 mitigation). Then run `--scenario E`. Each costs a few cents with the Jev judge.
  - [x] Run 5.11's authored `discard-working-draft` smoke case once (F17): `uv run python -m evals.live_conversations.smoke_suite --case discard-working-draft --prior-spend-usd <spent so far> --override-file evals/live_conversations/compose.override.yml --output ../_bmad-output/test-artifacts/smoke-discard-5-12.json`. Pass `--override-file` explicitly, because the default path is a git-ignored file that may not exist. The result is diagnostic only, not evidence: it proves the discard tool routes on a no-draft conversation.
  - [x] On a failure, read the report's `checks`, `verified` and the reply before changing anything (memory: "noise" had a cause each time). A product fix follows D9. Batch commits during this loop; do not commit every micro-fix (memory `feedback-batch-commits`).
  - [x] An OpenRouter 402 shows up as `provider_error` on every turn; check Logfire for the status code. Background runs can be killed under memory pressure, which leaves a partial report.

### Phase C — the recorded measurement (paid; Minh's go-ahead required)

- [ ] **Task 8 — STOP: ask Minh, then measure** (AC3; per D8)
  - [ ] Ask Minh for one approval covering both runs below. Estimate about $1–1.5 in total: 5.7's run was $0.66 for 108 turns.
  - [ ] Run A–E once (`--repetitions 1`); every scenario must pass clean. Fix (D9) and repeat if needed.
  - [ ] Clean tree, images rebuilt (no `--skip-image-build`): `uv run python -m evals.live_conversations.suite --repetitions 3 --output ../_bmad-output/test-artifacts/live-matrix-5-12.json`. The exit code must be 0.

- [ ] **Task 9 — STOP: ask Minh, then generate evidence and re-derive** (AC3; per D7, D8)
  - [ ] `uv run python -m evals.live_conversations.evidence ../_bmad-output/test-artifacts/live-matrix-5-12.json --output ../evidence/story-5.12/live-conversation-journeys.json`. Pass `--accept-finding` only for a turn Minh approved by name. Required: `live_conversation_journeys: passed`, no `false_claims`, `clean_scenarios` A–E, `complete_repetitions` 3, and `scheduling_draft_discard:invoke` covered live (F9).
  - [ ] Before re-deriving, run the drop check against the **current 108-turn baseline** (`scripts/live_conversation_drop_check.py --report ../evidence/story-5.12/live-conversation-journeys.json`). Record every tier's result, or the refusal (D11), for the commit message and `docs/TESTING.md`.
  - [ ] `uv run --frozen python scripts/derive_live_conversation_baseline.py --source ../evidence/story-5.12/live-conversation-journeys.json`. Expect 129 executed.
  - [ ] Evidence commit (D8 step 3): the evidence file and the baseline only.

- [ ] **Task 10 — Gate follows the new baseline** (AC3; per D7, D8 step 4)
  - [ ] `scripts/live_conversation_drop_check.py`: `AGGREGATE_FLOOR` and its comment per D7, plus the usage example's path.
  - [ ] `scripts/derive_live_conversation_baseline.py`: `SOURCE_EVIDENCE` → story-5.12. `evidence.py`: default `--output` → story-5.12.
  - [ ] `tests/test_live_conversation_drop_check.py`: pinned 108 → 129, the source path, and the Tier 3 arithmetic comments and boundary tests.
  - [ ] Re-run the drop check against the new baseline. It must pass, with Tier 3 at 129/129 or the measured total.
  - [ ] Full default backend suite and Vitest are green. Commit, together with Task 11.

- [ ] **Task 11 — Documentation** (AC3)
  - [ ] `docs/TESTING.md`: the scenario list (five conversations, 43 turns per repetition, E described); "every turn of A–E"; the recorded-result table and run id; the baseline paragraph (129, story-5.12 source); Tier 1 and Tier 3 text with floor 120 and λ 4.3; Structural A–E; inventory counts from the new evidence; the drop-check command path; the D7 correction note that instructions are not in `behavioral_digest`.
  - [ ] `README.md` (around line 109): the recorded result.
  - [ ] `handover-live-eval-per-turn-expectations.md`: a short dated update pointing at this story.
  - [ ] `deferred-work.md`: close 5.11's "For Story 5.12: `behavioral_digest` does not hash instructions" entry, citing this story's F7 correction.
  - [ ] `sprint-status.yaml`: the story's status when it is finished (via code review).

## Dev Notes

### Files touched (UPDATE unless marked NEW)

| File | Change | Must preserve |
|---|---|---|
| `backend/evals/live_conversations/expectations.py` | D1 checks, D2 `drafts`, `TurnContext.draft_state` | every existing check's semantics; the `as_of` look-back rule; `evaluate`'s judge isolation (each question sees only its own facts) |
| `backend/evals/live_conversations/runner.py` | D3 read; pass `draft_state` | grading before actions (F2); the existing `latest_draft` calls for draft turns and `run_optimization` |
| `backend/evals/live_conversations/http_client.py` | `newest_draft_proposal()` | `latest_draft()`'s guards, which `run_optimization`/`reject_draft` rely on |
| `backend/evals/live_conversations/cases.py` | `REQUIRED_SCENARIOS`, the D3 refusal | every existing validation |
| `backend/evals/live_conversations/scenarios.json` | E, B:6, B:10, C:9 | every other turn byte-for-byte; LF endings |
| `backend/evals/live_conversations/evidence.py` | D10 prose, then the D8 default path | coverage logic |
| `backend/scripts/derive_live_conversation_baseline.py` | generic note, then `SOURCE_EVIDENCE` | the clean-source refusals; the `behavioral_digest` derivation from the committed override |
| `backend/scripts/live_conversation_drop_check.py` | `AGGREGATE_FLOOR` | tiers, refusals, vocabulary |
| `backend/tests/test_live_conversation_{expectations,execute_prefix,reporting,drop_check}.py` | Task 5 and Task 10 | — |
| `evidence/story-5.12/live-conversation-journeys.json` | **NEW**, generated only | — |
| `backend/evals/baselines/live-conversations.json` | re-derived only | — |
| `docs/TESTING.md`, `README.md` | Task 11 | — |
| `backend/evals/live_conversations/compose.override.yml` | only if D11 requires it | everything else |

**Do not touch:** `evidence/story-5.7/**` (history), the 5.11 product contracts (D9), the
holistic judges `judge.py`/`jev_judge.py` grading rules, `configuration.py`'s digest rules, or
`Bindings.events` text (D6).

### Out of scope, deliberately

The card edit path and the four finalize races (5.11's AC2, deterministic). Undo, restore, diff
and re-activation (spec §6). Changing the 100-message history bound. A mixed judge mode. Logfire
per-check publication (`deferred-work.md`, logged by the handover). Any change to Gate B
thresholds.

### Testing standards

- Keyless CI only: no test may call OpenRouter or TypeSafe. The `_Scripted`/`FakeApp`
  doubles and canned activities are the pattern (`tests/test_live_conversation_expectations.py:555`).
- Live runs are operator-invoked, never in `ci.yml` (NFR26/AD-16).
- Live-eval subset for fast iteration (≈25 s): `uv run --frozen pytest
  tests/test_live_conversation_*.py tests/test_live_eval_publication.py -q`. The whole backend
  suite takes about 10 minutes and needs Docker PostgreSQL up.

### Environment gotchas (Windows, this machine)

- Scripted edits: Python's `write_text` writes CRLF here. Write bytes, or pass `newline='\n'`.
- An ad-hoc script that imports `settings` exports to the real Logfire. Keep scratch scripts out of
  `settings` or unset the token (memory `windows-scripted-edits-and-env-token`).
- Print replies with `PYTHONIOENCODING=utf-8`. Long `python - <<'EOF'` heredocs with mixed quotes
  fail to parse in the Bash tool, so write the script to a file and run that.
- There is no `pgrep`; watch a run through its report file.

### Previous story intelligence

- **5.11** (done; `5-11-keep-one-working-draft-per-conversation.md`): it owns everything this story
  proves live. Points that matter here:
  - A draft turn has no model prose. The draft output is the reply, and the card shows the
    version (its C6, Decision 12). That is why D4 grades draft turns by code only.
  - `draft_id` in the model view is content-addressed, **not** the proposal id (its C1). The
    harness reads `proposal_id` from the persisted proposal, never from the model's citation.
  - Code-review decision: `scheduling_baseline` refuses after a same-turn draft or discard, and
    the resume path withholds the draft tools. B:9 proposes the baseline in its own turn, so it
    is unaffected. If a B:9 failure shows `scheduling_baseline` refusing, look here first.
  - B:10's instruction step now describes the draft's `applied_version` constraints and says
    "applied to baseline" from the draft's state (`scheduling_instructions.py` "Saying what the
    baseline is now"). B:10's existing checks still hold; Task 7 re-checks it first.
  - Its deterministic proofs are in `tests/test_draft_lifecycle_postgres.py` and
    `tests/test_finalize_agent_run_guard.py`. A live failure that looks like a lifecycle defect
    gets its regression test there (D9).
- **5.7 / per-turn expectations (`ba8c706`)**: per turn, ask first what the planner wants from the
  reply, write required positive checks, then must-nots. Matching is whole-token: author the forms
  you accept (`"40 hours"`, `"40-hour"`). Jev varies by ±0.05–0.16 between runs, so a check near
  0.70 is fragile.
- **5.8**: the baseline is a projection, never hand-typed. `derive_live_conversation_baseline.py`
  refuses a source with blocking reasons, fewer than 3 complete repetitions, or incomplete runs.
- **5.10**: the Logfire publisher is scenario-agnostic and reads the raw run report. It needs no
  change, and publishing the new run is optional (it needs Minh's token).

### Git intelligence

The last five commits are docs only (the design spec, proposal and planning edits). The relevant
code history: `a5dd9d9` (new check kinds and bindings: the pattern to copy), `8f35907`
(`each_item_mentions` reading segment text: a check reading the wrong rendering), `ad89854`
(rebinding a garbled draft citation; 5.11 keeps it compatible, spec §2.1), and
`3cc57c2`/`4922165` (the re-measurement commit split, F14).

### Re-verification after 5.11 (2026-10-01, at `3d747f7`)

- F10/D11: the discard flag defaults to True, so no override edit is needed and the Task 9
  comparison runs rather than being refused.
- F11: `ProposalOut` lifecycle fields are nullable. D2's `draft_version_ordinal_missing` refusal
  is the right handling, since a fresh live database always fills them.
- F16: the undo instruction shipped as clarify-unless-named, which D5 now notes. The discard
  error codes and the measured inventory (141 / 38 / 103) feed Task 11's `docs/TESTING.md` counts.
- F17: 5.11's authored discard smoke case is run once in Task 7.
- F7: 5.11's C15 independently confirms the `behavioral_digest` correction; Task 11 closes its
  ledger entry.
- No AC, Decision mechanism or scenario E turn changed. The live-eval subset is green at
  `3d747f7` (263 passed).

### Self-consistency pass (done at creation)

- Each Task cites a Decision or AC rather than restating it. No Task proof describes a state the
  Decisions make unreachable: D3 refuses `draft_state_is` on turns with actions, and no authored
  turn has both.
- AC1's "two check kinds" against D1's four: AC1 is satisfied as written, and D1 adds two more that
  the spec's own E wording requires. This is recorded here, so it is not a review surprise.
- Spec §5.2's E:4 contradiction is resolved by D5, and its `behavioral_digest` claim is corrected
  under F7. The approved spec is not edited.

### References

- `_bmad-output/planning-artifacts/epics.md` — Story 5.12, Gate B row "Required live conversation journeys"
- `_bmad-output/planning-artifacts/sprint-change-proposal-2026-09-30.md` — F2–F5, §3 mitigation
- `docs/superpowers/specs/2026-09-28-draft-lifecycle-design.md` — §1, §2.1–§2.7, §4, §5.2
- `_bmad-output/implementation-artifacts/handover-live-eval-per-turn-expectations.md`
- `docs/EVIDENCE-CONVENTION.md`, `docs/DOMAIN-MODEL.md` (F15), `docs/TESTING.md` § Required live conversation acceptance

## Dev Agent Record

### Agent Model Used

Claude Opus 5.5 (`claude-opus-5-5`)

### Debug Log References

- Task 6 offline replays (real Jev, hand-written replies, $0.0012 total): scratch script
  `replay_e.py` (adapted from `live-eval-replay/replay_one_turn_variant.py`; E's bindings rebuilt by hand).

### Completion Notes List

- Story created 2026-10-01 at `8a85f4f` (Story 5.11 still in backlog). Ultimate context engine analysis completed - comprehensive developer guide created.
- 2026-10-01: 5.11 (`claude/wizardly-knuth-u7mh15`, done) fast-forward-merged into `feat/draft-lifecycle` at `3d747f7`; story re-verified against its code (see "Re-verification after 5.11").
- **Task 0.** HEAD `0e531b3` has no backend change since `3d747f7`, so F11/F16/D11 names hold. Starting
  default-suite count: 5.11's record (2803 passed / 2 skipped). My own baseline run was invalidated
  because I edited `scenarios.json` while it ran (`test_catalogue_is_four_full_conversations` failed
  on the new scenario E, not a regression).
- **Tasks 1-5.** Four check kinds per D1; `Bindings.drafts` + `version_ordinal` + the
  `draft_version_ordinal_missing` refusal per D2; `newest_draft_proposal()` with `latest_draft()` over
  it, the runner's targeted read and the `actions_after` refusal per D3; scenario E, B:6, B:10, C:9 per
  D4; `REQUIRED_SCENARIOS` with E; D10 binding prose; the baseline `note` names no story.
  - The note is pinned by `test_committed_baseline_is_exactly_what_the_script_derives`, so the baseline
    was re-derived **by the script** from the unchanged 5.7 source in the code commit. Only `note`
    changed (still 108/108, same digests).
  - E's draft-turn obligations start with "Persist" so the existing
    `test_every_turn_that_must_persist_a_draft_says_so_explicitly_and_only_those` invariant still holds.
  - Live-eval subset 519 passed; default suite **2843 passed / 2 skipped** (PostgreSQL 18).
- **F7 correction recorded:** the agent instructions and scenarios are not in `behavioral_digest`
  (spec §5.2 says they are). A-D are still re-measured for the reasons under F7.
- **Task 6 / D5 stop condition hit, resolved by Minh (2026-10-01).** As authored, `handles_undo` could not
  separate a correct re-add (0.59-0.80) from a wrong one (0.43-0.58). A draft reply has no prose (F5), so
  Jev had to judge from `facts.draft`. `claims_undo` also scored ~0.5 on a correct clarification. Minh's
  rule, for **all** tests: *grade the action (right tool, right arguments, non-fabricated result), not the
  reply's wording.* Applied as a generic optional `when: draft | not_draft` field on any expectation. A
  check that does not apply to this reply's kind is `skipped`; each branch must still carry a positive
  check. E:4 now:
  - draft branch, code only: `draft_updates_turn: 1`, `draft_has` the Priya/Main Pick exclusion,
    `draft_has` the 30h cap, `draft_constraint_count: 2`;
  - prose branch: judge `asks_which` (want true), judge `claims_restored` (want false, narrowed to the
    one action that could be faked on this turn);
  - unconditional `mentions_none says_undid`.

  Replayed 3 rounds: (a) clarification passes (0.97-0.98 / 0.91-0.93); (b) correct re-add passes by
  code; (c) wrong re-add fails by code; (d) a claimed undo fails (0.03 / 0.16-0.17). E:6 passes for the
  truthful discard (0.97 / 0.92) and fails for "fresh draft" (0.05-0.06) and "still runnable"
  (0.05-0.06). E:6's wording is unchanged from D4.
- **A-D audit under the same rule (not changed; D9 needs Minh's approval):** D:1 `long_walkthrough`,
  D:2 `is_brief` and A:6 `off_subject` grade style; B:10 `identifies_by_origin` and
  `locates_decision_record` grade explanation quality; C:10 checks the word "ready" but not that the
  demonstration tool ran with the right arguments; B:7 and C:12 rely on the judge where the tool log
  could show no run or approval was created.

- **Task 7, live smokes (diagnostic, not evidence).** Each failure was read from the report and
  fixed at its root cause (D9), with a deterministic regression test:
  - **Harness:** `suite` and `smoke_suite` took `--override-file` as given, but compose runs from
    the repo root, so the story's relative path made every build `isolated_stack_build_failed`
    (`53248e8`, plus the smoke_suite commit).
  - **Runtime, E:6:** after `scheduling_draft_discard`, the model returned the `draft` output citing
    the draft it had just discarded. That citation can never bind, so the turn failed and, by 5.11's
    rule, applied no discard. The draft-output validator now retries into prose when no draft was
    created this run (`fd8eed0`). This is not a 5.11 contract change: such a citation already always
    failed.
  - **Instruction, E:4, two live runs:** 5.11's undo rule ("remove or change that constraint ...
    otherwise ask which one") made the agent read "Undo that." as "remove another constraint". It now
    says undo reverses the previous change, as a full-list revision (`81722bb`, `54e3550`).
    `TODAYS_PROMPT_SHA256` re-pinned. Spec §4 and F16 quote the old wording; neither is edited.
  - **Results:** B 12/12 (B:6 same proposal v1→v2; B:10 `applied/system`). E 7/7 at `54e3550`
    (E:4 v4 = cap + exclusion restored; E:6 `rejected/assistant`, "Discarded your draft (v5).";
    E:7 new proposal v1). 5.11's `discard-working-draft` smoke passed (`no_working_draft`, prose
    reply). Live spend under $0.10 in total.
#### Mutation table (every mutation reverted; tree verified clean after each batch)

| Mutation applied to real code | Guard that should redden | Before | After |
|---|---|---|---|
| M1 `draft_updates_turn`: `>` → `>=` on `version_ordinal` | `test_draft_updates_turn_needs_the_same_proposal_at_a_higher_version` | green | red |
| M2 `draft_updates_turn`: `proposal_id` comparison dropped | same | green | red |
| M3 `draft_updates_turn`: unrecorded turn returns False, not `Unbound` | `test_draft_updates_turn_on_a_turn_that_saved_no_draft_is_unbound` | green | red |
| M4 `draft_state_is`: `ended_by` ignored | `test_draft_state_is_reads_the_newest_drafts_state_and_ender` | green | red |
| M5 `draft_is_new`: compares against `drafts` (incl. this turn), not `as_of` | `test_draft_is_new_needs_version_one_of_a_proposal_no_earlier_turn_saved` | green | red |
| M6 `draft_is_new`: `version_ordinal == 1` dropped | same | green | red |
| M7 `draft_constraint_count`: `==` → `>=` | `test_draft_constraint_count_counts_the_persisted_constraints` | green | red |
| M8 loader: `ended_by` vocabulary not checked | `test_a_malformed_expectation_is_refused_at_load` | green | red |
| M9 `capture_draft`: missing `version_ordinal` not refused | `test_a_persisted_draft_without_an_integer_version_ordinal_is_a_contract_break` | green | red |
| M10 `as_of`: carries every recorded draft | `test_each_draft_turn_records_its_draft_identity_and_the_latest_carries_its_ordinal` | green | red |
| M11 runner: newest draft state read on every turn | `test_an_e_like_lifecycle_grades_update_discard_and_a_new_draft` | green | red |
| M12 runner: `draft_state` not passed to `TurnContext` | same | green | red |
| M13 `validate_scenarios`: `draft_state_is` with `actions_after` not refused | `test_draft_state_is_cannot_grade_a_turn_that_has_actions` | green | red |
| M14 client: `newest_draft_proposal` raises on no draft | `test_the_newest_draft_proposal_is_none_without_a_draft` | green | red |
| M15 client: `latest_draft` active/stale guard dropped | `test_a_draft_that_is_not_current_cannot_be_optimized` | green | red |
| M16 `evaluate`: `when` ignored | `test_each_reply_kind_is_graded_only_by_the_checks_for_it` | green | red |
| M17 loader: per-branch positive requirement dropped | `test_every_reply_kind_needs_a_positive_check_of_its_own` | green | red |
| M18 loader: unknown `when` value accepted | `test_a_malformed_expectation_is_refused_at_load` | green | red |
| M19 `suite._arguments`: relative `--override-file` not resolved | `test_a_relative_override_file_is_resolved_before_compose_runs_elsewhere` | green | red |
| M20 runtime: `draft` output with no draft this run not retried | `test_a_draft_output_with_no_draft_this_turn_is_retried_into_prose` | green | red |
| M21 `smoke_suite._args`: relative `--override-file` not resolved | `test_a_relative_override_file_is_resolved_before_compose_runs_elsewhere` | green | red |
| M22 instruction: undo rule reverted to 5.11's wording | `test_the_scheduling_prompt_teaches_the_one_working_draft_lifecycle` (and the prompt hash pin) | green | red |

### File List

- `backend/evals/live_conversations/expectations.py`
- `backend/evals/live_conversations/runner.py`
- `backend/evals/live_conversations/http_client.py`
- `backend/evals/live_conversations/cases.py`
- `backend/evals/live_conversations/scenarios.json`
- `backend/evals/live_conversations/evidence.py`
- `backend/scripts/derive_live_conversation_baseline.py`
- `backend/evals/baselines/live-conversations.json` (re-derived by script; `note` only)
- `backend/tests/test_live_conversation_expectations.py`
- `backend/tests/test_live_conversation_execute_prefix.py`
- `backend/tests/test_live_conversation_cases.py`
- `backend/tests/test_live_conversation_reporting.py`
- `backend/evals/live_conversations/suite.py`
- `backend/evals/live_conversations/smoke_suite.py`
- `backend/agent/runtime.py`
- `backend/agent/scheduling_instructions.py`
- `backend/tests/test_agent_runtime_adapter.py`
- `backend/tests/test_turn_routing.py`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

### Change Log

- 2026-10-01: Phase A (Tasks 0-5) and Task 6 offline validation; E:4 graded by action per Minh's decision (`when` field).
- 2026-10-01: Task 7 live smokes; harness path fix, discard-turn runtime retry, undo instruction rewritten.
