# Story 5.7 continuation handoff

Updated: 2026-09-16 (Scenario B endpoint 4 complete)

## Resume point

Story 5.7 remains `in-progress`. Scenario A is complete. Scenario B endpoint 4 (the shortest independent prefix) now passes after a routing-prompt fix. Resume with Scenario B endpoint 8, then 12, 16, 20, one prefix at a time.

Suggested fresh-session instruction:

> Continue `$bmad-dev-story 5.7` from `_bmad-output/implementation-artifacts/story-5-7-handoff.md`; start Scenario B endpoint 8 and keep total story spend under USD 10.

## Current live configuration and budget

- Application agent: `openrouter:~deepseek/deepseek-flash-latest`
- Independent judge: `openrouter:google/gemini-2.5-flash-lite`
- Total story API budget: USD 10; minimize spend.
- Conservative prior-spend reserve for the next invocation: USD 1.30 (bumped from 1.25 after USD 0.046262 measured spend across three B4 runs on 2026-09-16).
- Keep secrets in `backend/.env`; never print them. An ignored `backend/.env.before-story-5-7` backup exists.
- Baseline assignment context is temporarily capped at 10, as requested.

The application agent and judge must remain separate. DeepSeek Flash was unreliable as its own judge because it frequently returned malformed structured output. Gemini 2.5 Flash Lite was the cheapest probed judge that was accessible with the configured OpenRouter key and reliably supported the required JSON response shape.

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

## Continue with Scenario B endpoint 8

From `backend`:

```powershell
uv run python -m evals.live_conversations.suite --scenario B --endpoint 8 --agent-model 'openrouter:~deepseek/deepseek-flash-latest' --judge-model 'openrouter:google/gemini-2.5-flash-lite' --reasoning-effort low --repetitions 1 --spend-limit-usd 10 --prior-spend-usd 1.30 --output '../_bmad-output/test-artifacts/live-scenario-B-endpoint8-r1.json'
```

Scenario B prefixes end at turns 4, 8, 12, 16, and 20. Endpoint 4 is green; advance one prefix at a time. Run the full Scenario B only after the individual prefixes are green. The runner already fails fast, so preserve each failed JSON report and fix the earliest failure before spending on later turns.

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
14. **A false "draft saved" claim in a prose-only response is a real, still-open failure mode — the existing instruction against it is not reliably followed.** Endpoint 8's `r7` run: turn 4 (initial draft) returned a proper `activity_type: "draft"` and passed; turn 6 ("Revise the draft to cap that worker at 40 hours as well") returned `activity_type: "agent_response"` — pure prose confidently describing the draft update ("Updated the draft. It now holds two reversible constraints...") with **no** draft segment and **no** persisted mutation (`app.latest_draft()` shows nothing new). The harness correctly flags this as `required_persisted_draft_missing` per this story's own AC6 example ("'The draft is saved' without a persisted proposal: fail even if the tool was attempted"). `agent/scheduling_instructions.py` already says "never claim draft success only in prose," so this is a genuine model instruction-following gap at low reasoning effort, not a missing instruction — matches the same class of failure the 2026-09-16 model-suitability-gate note first flagged. Turn 7 then compounds it (the agent contradicts its own prior turn about the cap's presence). Not yet fixed; candidates for next session: (i) retry via more repetitions/higher reasoning effort (cheap, matches Scenario A's precedent of needing up to 5 reps), or (ii) a defensive application-layer guard in `agent/runtime.py`/`application/use_cases/execute_turn.py` that refuses to surface a state-changing turn as prose-only when its own tool call was a mutation (bigger, needs its own scoping decision — do not start this without explicit sign-off, per this story's Boundaries section).

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

- Latest implementation commit before this handoff: `a24d075 test: verify summarized worker attributes`.
- No `shiftmind-live-*` containers remain.
- Preserve unrelated untracked `.1devtool/` and `rosterai-schema.sql`.
- Development JSON under `_bmad-output/test-artifacts/` is intentionally ignored.
