# Story 5.7 continuation handoff

Updated: 2026-09-17 (model swap to Haiku 4.5/Gemini 2.5 Flash; endpoint 8 effectively solved bar one recorded finding; resume at endpoint 12)

## Resume point

Story 5.7 remains `in-progress`. Scenario A is complete. Scenario B endpoint 4 passes. Endpoint 8 passes 7 of 8 turns consistently with the new model pairing (see "Model swap" below); the 8th (turn 2's task-name-suffix drop) is a recorded, reproducible model-reliability finding (lesson 17), not a defect to keep chasing. Minh explicitly decided to record it and move on rather than keep retrying or escalate further. Resume with Scenario B endpoint 12, using the NEW model configuration below (not the old DeepSeek one still shown in stale text elsewhere in this file's history).

Suggested fresh-session instruction:

> Continue `$bmad-dev-story 5.7` from `_bmad-output/implementation-artifacts/story-5-7-handoff.md`; start Scenario B endpoint 12 with the Haiku 4.5 / Gemini 2.5 Flash pairing and keep total story spend under USD 10.

## Current live configuration and budget

- Application agent: `openrouter:anthropic/claude-haiku-4.5` (switched from `openrouter:~deepseek/deepseek-flash-latest` on 2026-09-17 — see "Model swap" below). This is also the actual pinned production model (`anthropic:claude-haiku-4-5-20251001` direct / `anthropic/claude-haiku-4.5` via OpenRouter per `docs/GETTING-STARTED.md`), not a cost-driven substitute.
- Independent judge: `openrouter:google/gemini-2.5-flash` (switched from `openrouter:google/gemini-2.5-flash-lite` on 2026-09-17 — the non-lite tier reliably applies rubric rules the lite tier missed 3/3 times; see lesson 15).
- Total story API budget: USD 10; minimize spend.
- Conservative prior-spend reserve for the next invocation: USD 1.98 (bumped from 1.55 after USD 0.719405 combined measured spend across all B4/B8 runs, both pairings, on 2026-09-16/17).
- Keep secrets in `backend/.env`; never print them. An ignored `backend/.env.before-story-5-7` backup exists.
- Baseline assignment context is temporarily capped at 10, as requested.

The application agent and judge must remain separate. DeepSeek Flash was unreliable as its own judge because it frequently returned malformed structured output. Gemini 2.5 Flash Lite was the cheapest probed judge that was accessible with the configured OpenRouter key and reliably supported the required JSON response shape, but proved unreliable at applying explicit rubric rules (lesson 15) — Gemini 2.5 Flash (non-lite) replaced it and has not reproduced that specific failure.

## Model swap: Anthropic Haiku 4.5 / Gemini 2.5 Flash

Minh asked to try a stronger agent+judge pairing on Scenario B endpoint 8 after DeepSeek Flash kept hitting a wall around 3-6 of 8 turns passing per attempt. Both models are on OpenRouter (the only configured credential this session — no `ANTHROPIC_API_KEY`/`GEMINI_API_KEY` set, so a direct-provider pairing was not available without new credentials).

Result: 7 of 8 turns pass consistently (`live-scenario-B-endpoint8-haiku-r1.json` through `-r9-medium.json`). The stronger pairing also surfaced three further harness bugs DeepSeek's noisier failures had been masking, all now fixed (see lesson 16). The 8th turn's failure (lesson 17) is a recorded model-reliability finding, not a harness bug.

**Recommendation for the rest of this story:** keep the Haiku 4.5 / Gemini 2.5 Flash pairing for Scenarios C-H unless a similar wall is hit again. It costs roughly 3x DeepSeek Flash per turn (an 8-turn prefix runs ~USD 0.05-0.06 vs. DeepSeek's ~USD 0.02) but the quality difference more than pays for itself in avoided debugging cycles, and the total story budget has enormous headroom (USD 0.72 spent of USD 10 after this entire session, including two full model-comparison experiments).

## Scenario A result

Scenario A passed.

- A2 through A5 passed together in `_bmad-output/test-artifacts/live-scenario-A-final.json`.
- A6 passed all six user turns and all judge verdicts in `_bmad-output/test-artifacts/live-scenario-A-endpoint6-r5.json`.
- A6 recorded spend: USD 0.00661903.
- A6 used a conservative USD 1.24 prior-spend reserve and stayed within the USD 10 story ceiling.
- No factual failures remained.

The two files are ignored development evidence. They establish the continuation point but are not final version-bound release evidence. The full matrix, three consecutive final runs, and real-browser evidence are still outstanding.

## Scenario B endpoint 4 result

Passed on the third attempt (`live-scenario-B-endpoint4-r3.json`, run `dca2e4de-9c42-4434-99df-6b6e2489290e`): all four turns pass, `incomplete_reason: None`. See lesson 13 below for the root cause and fix; `r1`/`r2` are retained as before/after diagnostics.

## Scenario B endpoint 8 result

Effectively solved with the Haiku 4.5 / Gemini 2.5 Flash pairing: 7 of 8 turns pass consistently across `live-scenario-B-endpoint8-haiku-r1.json` through `-r9-medium.json`. The remaining turn (turn 2's task-name-suffix drop) is recorded as a model-reliability finding, not chased further (lesson 17). Do not spend more on this specific prefix unless new evidence changes the picture.

## Continue with Scenario B endpoint 12

From `backend`:

```powershell
uv run python -m evals.live_conversations.suite --scenario B --endpoint 12 --agent-model 'openrouter:anthropic/claude-haiku-4.5' --judge-model 'openrouter:google/gemini-2.5-flash' --reasoning-effort low --repetitions 1 --spend-limit-usd 10 --prior-spend-usd 1.98 --output '../_bmad-output/test-artifacts/live-scenario-B-endpoint12-r1.json'
```

Scenario B prefixes end at turns 4, 8, 12, 16, and 20. Endpoints 4 and 8 are green (or recorded-finding green); advance one prefix at a time. Run the full Scenario B only after the individual prefixes are green. The runner already fails fast, so preserve each failed JSON report and fix the earliest failure before spending on later turns.

## Fast path learned from Scenario A

1. **Prove each tool in a two-turn live smoke conversation first.** Use a greeting followed by one direct question that should invoke exactly one tool. All five chat-facing tools have passed this gate: `scheduling_inspect`, `scheduling_compute`, `scheduling_draft`, `scheduling_baseline`, and `shiftmind_demonstration`. `scheduling_optimize` is exercised through the explicit command endpoint because ordinary chat cannot grant run authority.
2. **Make routing rules literal.** The agent prompt now maps question types to tools, makes greetings and capability questions tool-free, and tells the model to use trusted workflow snapshot IDs and versions directly.
3. **Do not overload context.** The full assignment set caused poor routing and wasted calls. Keep the temporary assignment context cap at 10 unless a scenario specifically proves that more is required.
4. **Reject invented evidence at the boundary.** The agent may not emit guessed, empty, placeholder, or failed result IDs. Numeric claims must come from a successful `scheduling_compute` result. If an exact earlier result is unavailable, recompute it.
5. **Judge alternatives independently.** A turn that permits either clarification or a grounded answer passes when either allowed branch is complete. Do not accidentally require both.
6. **Judge only applicable dimensions.** Ignore placeholder scores for non-applicable dimensions and allow their citations to be empty. Bind each judgment to the exact stable obligation ID.
7. **Normalize provider JSON defensively.** The judge client accepts a JSON string, decoded object, a single OpenAI text block, and one double-encoded JSON layer. Requests use portable `json_object`; the owned schema is included in the prompt.
8. **Give the judge verified facts it can actually assess.** Worker verification now includes employment type, grade, EBA, contracted hours, qualification IDs, and roster/extra-availability counts.
9. **Allow bounded nondeterminism.** The fixture permits a second solver attempt and retains every attempt because CP-SAT can return `UNKNOWN` nondeterministically.
10. **Keep reasons useful but bounded.** Judge reason length is capped at 1,000 characters, enough for multi-fact worker summaries.
11. **Use the correct demo flag.** The environment setting is `DEMONSTRATION_ENABLED`, not `SHIFTMIND_DEMONSTRATION_ENABLED`.
12. **Fix the first failing prefix, then rerun it.** This saved most of the cost during Scenario A. Preserve failures as diagnostics rather than weakening scenario obligations.
13. **Family-scoped questions need explicit routing, grounded answers must name their entities verbatim, and the judge needs family grounding data too.** `family` (outbound/inbound/indirect) lives only on demand records — `TaskV1`/`AssignmentV1` carry no family field, and `scheduling_inspect`'s assignment filter is single-value equality only (no `task_id` list). Without being told this, the agent falls back to broad unbounded inspection and burns its tool-call budget (Scenario B endpoint 4 turn 2 hit `budget_exhausted` at 12 tool calls this way). Three layered fixes were needed, in this order: (a) `agent/scheduling_instructions.py` — inspect demand filtered by family once, collect distinct task_ids, then inspect assignments per distinct task_id (capped, report partial coverage rather than exhausting budget silently); (b) same file — copy each resolved task's/worker's exact name field **verbatim**, not a paraphrase ("C Fork | Grid P 8GR", never "a Chiller fork/putaway task") — a paraphrase leaves the harness's literal-name grounding (`evals/live_conversations/runner.py::relevant_entities`) with nothing to match; (c) `evals/live_conversations/runner.py` — `relevant_entities` never attached demand family to a named task at all, so even a fully correct, fully-named answer was ungroundable; added a `demand_families` field per named task (demand is now loaded eagerly like workers/tasks) and taught `judge.py`'s RUBRIC to treat a claimed family as grounded when it appears in that field, plus a citation-ID tightening after the judge cited a bare fact-group key (`"candidate_solver_status"`) as if it were an ID. After all three fixes, endpoint 4 and endpoint 8's turn 2 both pass consistently across reruns (`r7`).
14. **A false "draft saved" claim in a prose-only response is a real, still-open failure mode — the existing instruction against it is not reliably followed.** Endpoint 8's `r7` run: turn 4 (initial draft) returned a proper `activity_type: "draft"` and passed; turn 6 ("Revise the draft to cap that worker at 40 hours as well") returned `activity_type: "agent_response"` — pure prose confidently describing the draft update ("Updated the draft. It now holds two reversible constraints...") with **no** draft segment and **no** persisted mutation (`app.latest_draft()` shows nothing new). The harness correctly flags this as `required_persisted_draft_missing` per this story's own AC6 example ("'The draft is saved' without a persisted proposal: fail even if the tool was attempted"). `agent/scheduling_instructions.py` already says "never claim draft success only in prose," so this is a genuine model instruction-following gap at low reasoning effort, not a missing instruction — matches the same class of failure the 2026-09-16 model-suitability-gate note first flagged. Turn 7 then compounds it (the agent contradicts its own prior turn about the cap's presence). Not yet fixed; candidates for next session: (i) retry via more repetitions/higher reasoning effort (cheap, matches Scenario A's precedent of needing up to 5 reps), or (ii) a defensive application-layer guard in `agent/runtime.py`/`application/use_cases/execute_turn.py` that refuses to surface a state-changing turn as prose-only when its own tool call was a mutation (bigger, needs its own scoping decision — do not start this without explicit sign-off, per this story's Boundaries section). Recurred again in `r10` after unrelated fixes, confirming it is not transient.
15. **A recurring judge false-negative on "preserve existing X" obligations, from the DeepSeek/flash-lite pairing — did not reproduce after the model swap.** Scenario B endpoint 8 turn 4 ("preserve the existing locks") failed identically three times (`r7`, `r9`, `r10`) even after an explicit rubric rule was added saying a zero-count preservation of a genuinely-empty set is complete; the cheap judge (`google/gemini-2.5-flash-lite`) simply did not reliably apply a rule it had already been given. Turn 4 has passed consistently in every Haiku/Gemini-2.5-Flash (non-lite) rerun since. Kept here as a record that a "stronger judge" escalation is a real, working option for a stuck rubric-compliance finding, not just a theoretical one.
16. **The stronger pairing surfaced (and let us fix) three more citation-ID gate gaps and a temporal-ordering rubric bug — fix the general pattern, not each string.** Once DeepSeek's noisier, more varied failures stopped dominating, three MORE variants of "the judge cited real, correct evidence but in a form the strict evidence-ID allow-list didn't recognize" surfaced in quick succession: a bare fact-group key (`persisted_draft`, `candidate_solver_status` — fixed in `runner.py`'s `known_citation_ids()`, commit `3ab5ef2`), the judge payload's own wrapper key (`current_obligation` — fixed via `judge.py`'s new `PAYLOAD_STRUCTURE_KEYS`, commit `c3d0ae2`), and a dotted JSON-path into a known key (`verified_facts_and_effects.persisted_draft.constraints` — fixed generally in `protocol.py`'s `ConversationJudgment.passes()`, accepting any dotted path rooted at a known ID, commit `be24978`). After the third occurrence it became clear this needed a general fix (accept the whole class of reasonable citation forms) rather than another one-string allow-list entry — do the same if a fourth variant appears. Separately, turn 7's correct refusal ("do not claim a run before the authenticated action") was scored 0 because the judge compared it against `effects_after_reply`, which by construction only contains what the harness scripted strictly AFTER that reply — fixed by telling the rubric a reply cannot be judged against its own future (commit `13186dc`). Watch for the same effects_after_reply shape in Scenarios D/F/G, which also drive real solver runs through scripted `actions_after`.
17. **A specific task's name loses its trailing suffix token 4/4 times, resistant to explicit correction — recorded, not chased further.** Turn 2 keeps naming the resolved task `"C Fork | Grid P"` instead of its real stored name `"C Fork | Grid P 8GR"`, across four reruns at two reasoning-effort levels, despite `agent/scheduling_instructions.py` explicitly forbidding this exact truncation with this exact string as a counter-example (commit `4819feb`). Independently verified via direct DB query that the family claim is factually correct (TaskID `1E5596F1-C9AD-43F1-8DC4-7CF8013C9D0B`: 106 `Outbound Workload` rows, 0 `Inbound Workload` rows) and that no truncation exists anywhere in the pipeline (`_normalize_tasks` reads the raw `"Task"` field verbatim). This rules out a data/product bug. Minh's explicit decision (2026-09-17): record this as a model-reliability finding per the same AC6 provision used for lesson 15, rather than spend a fifth prompt iteration or escalate to a still-stronger model for this one case. Any future run touching this exact task should expect this specific failure to recur; do not treat it as a newly discovered defect.

## Verification already completed

- Full backend suite after the major implementation: `1862 passed, 2 skipped, 10 deselected`.
- Frontend `npm run typecheck`: passed.
- Latest focused worker-verifier tests: `7 passed`.
- Scenario A endpoint 6 live run: all six turns and judgments passed.

Small verifier/protocol changes were made after the last full backend run. Run the focused tests needed by the first Scenario B diagnosis, then run the full suite once before producing the final matrix evidence.

## Remaining Story 5.7 work

- Execute and repair Scenarios B through H.
- Complete tool/operation coverage and its fail-closed completeness assertion.
- Run three complete consecutive live matrices after the final relevant change.
- Add the real composed-stack browser journey and reload evidence.
- Generate version-bound Story 5.7 evidence and wire the Gate B evidence field.
- Update testing documentation and only then assess the story for completion.

Do not mark the story or any remaining acceptance criterion complete based on Scenario A alone.

## Repository state at handoff

- Latest implementation commit before this handoff: `4819feb fix: forbid dropping a task name's trailing suffix token`.
- No `shiftmind-live-*` containers remain (each live suite run tears down its own isolated compose project via `isolated_stack`'s context manager); the persistent `rosterai-*` dev stack on port 8080 is unrelated and was left running.
- Preserve unrelated untracked `.1devtool/` and `rosterai-schema.sql`.
- Development JSON under `_bmad-output/test-artifacts/` is intentionally ignored.
