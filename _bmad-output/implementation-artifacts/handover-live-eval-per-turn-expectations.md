# Handover: live eval, per-turn expectations

## Update 2026-09-30: done through evidence

Minh chose option 1 below. A, C and D now carry expectations; every live turn is graded by
them. Recorded run at `8f35907` (clean tree, images rebuilt): **108/108**, readiness eligible,
drop check passes. Evidence and the re-derived baseline are committed (`8c06bfb`). Nothing is
pushed; the PR is Minh's call. Commits since the note below, oldest first:

- `a5dd9d9` A/C/D expectations; new checks `claims_metric`, `draft_has_roster_lock`,
  `each_item_mentions`, bindings `worker_count`/`worker_names`/`first_task`/`indirect_task`.
- `49523ec` suite budgets a case slot per retry; C:4 family and D:2 wording relaxed.
- `ad89854` agent: a garbled `draft` citation binds to the draft this run created (the model
  copied the 64-hex id truncated; 3 turns failed as invalid_output).
- `46cd04f` grounding: an unterminated `<claim` opener is repaired, plus a corrective retry.
- `c4b619c` agent: keep a summary to the subject asked (A:6 added the planner's name).
- `9b8dad2` evals: raw `<claim` markup fails any turn; A:6 asks about off-subject content.
- `4067750` agent: pass a named demand family into metric arguments (C:3 used family=null).
- `a9cc7bf` evals: the approval event names the baseline it replaced (B:12 false needs_review).
- `8f35907` evals: `each_item_mentions` reads lines from segment text (it had read a lone `-`
  per bullet); A:6 drops it; B:2's `invents_task` judge replaced by it (Minh approved).

Lessons worth keeping:
- Most "judge noise" had a cause: an incomplete `events` log (B:12), a check reading the
  wrong rendering (A:6), or a real agent slip Jev half-saw (B:2 raw markup, A:6 name).
  Read the full reply and the judge's facts before rewording a question.
- An OpenRouter 402 (out of credit) shows as `provider_error` on every turn and charges the
  full reservation per turn, cutting later prefixes. Check Logfire for the status code.
- Background runs here are killed under memory pressure; the report is then partial.
- A:6 can still miss the count claim (1 of 3 on one run); watch it.

The original note follows, kept for its authoring rules and gotchas.

Written 2026-09-29 at the end of the session. Read this first. Everything here that isn't in the
specs or the code is listed on purpose.

## Where things are

- **Branch:** `claude/live-judge-typesafe`, from `main` at `8932cc8`. **Nothing is pushed.** Commits,
  oldest first:
  1. `778b318` feat(evals): judge live conversations with TypeSafe Jev
  2. `2f31ae3` feat(evals): grade Scenario B by authored per-turn expectations
  3. `5294725` fix(agent): answer "what is our baseline now" the way a planner needs
  4. (this note and the replay tools, committed with it)
- **Specs**, all `status: done`:
  - `spec-live-judge-typesafe-jev.md` (commit 1)
  - `spec-live-eval-per-turn-expectations-b.md` (commit 2)
  - Commit 3 had no spec; it was a small instructions change agreed in conversation.
- **Live reports** (git-ignored, on this disk only, in `_bmad-output/test-artifacts/`):
  - `live-jev-smoke-B.json`: B graded by the holistic Jev judge. 7 pass, 2 needs_review, 3 false fails.
  - `live-expect-smoke-B.json`: B graded by per-turn expectations. 11 pass; B:10 needs_review
    because of an agent gap.
  - `live-b10-fix-smoke-B.json`: the same after the agent fix. **12/12 pass.**
- **Replay tools:** `_bmad-output/implementation-artifacts/live-eval-replay/*.py` (see "How to
  validate" below).
- **Memory:** `project-live-eval-per-turn-expectations`.

## How grading works now (one paragraph)

The runner (`backend/evals/live_conversations/runner.py`) picks per turn. A turn with an `expect`
list **and** a `typesafe:` judge model is graded by `expectations.py`:
- code checks over the reply's visible text, its activity type, or the saved draft;
- narrow Jev `noul` yes/no questions for what code can't decide.

Each judge question sees only `{user_message, reply}` plus the facts it names, which ride inside its
own instructions. Expected values are **bindings** captured from app state as the run goes: the
saved draft, the run result, the approval. They are set once, and a check only sees values bound
**before** its own turn. An unbound value makes the turn `incomplete`, never `fail`. The verdict is:
- `fail` on any failed code check, factual failure, or judge P(wanted) < 0.30;
- otherwise `incomplete` on any unbound value;
- otherwise `needs_review` on any judge P(wanted) < 0.70;
- otherwise `pass`.

A turn **without** `expect` uses the holistic judge of the chosen provider.

## Open decision: ask Minh before a full run

A full run right now grades **A, C and D with the holistic Jev judge**. That judge false-failed B
before; expect the same there. The default judge is `typesafe:jev-1.13.0` because Minh's `.env`
sets no `LIVE_CONVERSATION_JUDGE_MODEL`. `--judge-model openrouter:<m>` switches **every**
scenario, B included, back to the old OpenRouter judge. There is no mixed mode. Options put to
Minh:
1. **Convert A, C and D to expectations first.** Recommended. Needed for a clean baseline.
2. Add a mixed mode: `expect` turns go to Jev, other turns to OpenRouter. A small runner change
   plus a second judge model/key. It's a bridge only, not a clean baseline.
3. Run everything with `openrouter:`. That's the old judgment, comparable with the old 108/108.

## Next steps (after Minh picks)

1. Convert A, C and D (24 turns) following B's pattern in `scenarios.json`. Per turn, **first ask
   what the planner wants from this reply** (Minh's framing). Write that as required positive
   checks, then add must-not checks.
2. Validate each scenario offline (below), then run one live smoke per scenario. Each costs about
   $0.005 with the Jev judge.
3. Full run, 3 repetitions, then re-derive the baseline with
   `backend/scripts/derive_live_conversation_baseline.py`. Follow `docs/EVIDENCE-CONVENTION.md`:
   commit code, then measure, then generate through `evidence_binding.py`, then commit the
   evidence. **The committed 108/108 baseline is stale** because the judge model feeds
   `behavioral_digest`, so `drop_check` refuses until then.
4. Push and open a PR, when Minh says so.

## Authoring expectations: rules and lessons

- **Check kinds:** `mentions`, `mentions_all` (the only kind that takes a list binding such as
  `{task_names}`), `mentions_any`, `mentions_none`, `activity_is`, `activity_field_equals`,
  `draft_has`, `draft_preserves_locks`, `names_assigned_pair`, `draft_matches_turn` (earlier turns
  only), and `judge` (`question`, `want`, optional `facts`).
- **Allowed values:** bindings are listed in `BINDING_NAMES` and facts in `FACT_NAMES`. The loader
  refuses unknown or irrelevant fields, a turn without a positive check, and a `facts.x` a question
  uses without declaring it.
- **Wording matters more than thresholds.** Ask about *actions*, not "anything not in facts".
  B:12 went from about 0.5 to about 0.85 once descriptive remarks were excluded. Give a question
  the **whole** fact it needs; B:5 needed the draft's consequence line, not just its constraints.
- **Keep `events` complete.** The harness's own event log includes the draft consequence summaries
  and the agent's approval request. A summary judged against an incomplete log fails truthful
  replies.
- **Matching is whole-token.** A bare "40" doesn't match "40-hour", and "76" doesn't match "0.76",
  so author the forms you accept (`"40 hours"`, `"40-hour"`, …) or use `"{assignment_count} assignments"`.
- **Jev is not deterministic.** The same input varies by ±0.05–0.16, so treat any check sitting
  near 0.70 as fragile. B:12's `claims_unhappened` came in at 0.78 on the last run.

## How to validate offline (real Jev, under $0.001 per scenario)

From `backend/`, with `PYTHONPATH=.`:
- `replay_expectations.py <report.json>` grades a recorded run's real replies. It should give the
  verdicts you expect.
- `replay_broken_replies.py <report.json>` swaps in deliberately wrong replies (its `BAD` dict).
  **Every one must fail.**
- `IDEAL_B10="…" replay_one_turn_variant.py <report.json>` tests one turn's checks on a
  hand-written reply.

They are B-specific: they rebuild bindings from B's recorded report. For A, C and D, adapt the
binding reconstruction.

## Stop and ask Minh when

- Any paid live run beyond a single-scenario smoke, or a full run.
- Re-deriving the baseline or writing evidence.
- Pushing, or opening a PR.
- A spec's `<frozen-after-approval>` block would need to change.

## Deferred work logged this session (`deferred-work.md`)

- The Jev price is a code constant, not part of the hashed override file.
- Publishing to Logfire doesn't carry the per-check results of expectation-graded turns.
- The agent can't say when or by whom the baseline was approved; there is no approval data in the
  workflow snapshot.
- The agent-side B:10 gap is now **fixed** (commit 3). Its ledger entry can be closed.
- A UX note, not logged: the planner's decision record sits under "Debug details … for
  troubleshooting".

## Gotchas found this session

- The prompt is hash-pinned in `backend/tests/test_turn_routing.py` (`TODAYS_PROMPT_SHA256`). Any
  edit to the agent instructions must re-pin it deliberately.
- In the Bash tool, long `python - <<'EOF'` heredocs with mixed quotes sometimes fail to parse.
  Write the script to a file and run that instead.
- Windows: print replies with `PYTHONIOENCODING=utf-8` (the → character breaks cp1252). There's no
  `pgrep`, so watch runs via their report file. Start Docker Desktop before the suite.
- Scripted edits: read and write **bytes** to keep LF endings (`scenarios.json` round-trips
  byte-identically through `json.dumps(indent=2, ensure_ascii=False) + '\n'`).
- The chat UI renders prose as plain text, so the agent can't give links, only directions.
- The whole backend suite takes about 10 minutes. The live-eval subset (`tests/test_live_conversation_*.py
  tests/test_live_eval_publication.py`) takes about 75 s: 471 pass, plus the prompt tests.
