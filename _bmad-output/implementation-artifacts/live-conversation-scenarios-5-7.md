# Story 5.7 — Natural Live Conversation Catalogue

Right-sized 2026-09-17 by `_bmad-output/planning-artifacts/sprint-change-proposal-2026-09-17.md` (approved by Minh). It supersedes the original eight-scenario catalogue (A–H, 40 prefixes, 273 turns per run), which remains in git history only.

These are authored user conversations, not fabricated successful transcripts. All assistant replies must come from live execution. One turn means one user message plus the actual assistant response and any tool activity it causes. Harness actions (Run optimization, approval) are logged separately and are not user turns.

| Scenario | User turns | Purpose |
| --- | --- | --- |
| A | 6 | Reproduction, capability question, typo clarification, memory |
| B | 12 | Long conversation through draft → real solver run → approval → baseline |
| C | 12 | Tool tour: every remaining inspect group, compute metric, draft kind, demonstration, refusal |

**Rules**
- **Fresh state, every turn scored.** Each scenario runs as one full conversation from fresh isolated state. A verdict is recorded for every turn, and later turns are still scored after a failed turn.
- **Cheap, answerable turns.** Every scheduling turn is authored to need at most two tool calls. A turn must never require a capability that no installed tool provides.
- **Natural prompts only.** No schemas, internal IDs or exact tool names in prompts. Fixture-dependent names come only from planner-visible information. Clarification branches are declared before running.
- **Per-turn run and coverage.** The 30 turns per full run are 3 conversations. Every installed tool and supported operation maps to a specific turn below or to a harness command.

## A. Minh introduction, typo, and context

Length: 6 user turns.

1. HI my name is Minh
2. how can you help me?
3. how many work are therre?
4. I mean workers in this scenario.
5. What was my name again?
6. Summarize what we learned about the workers.

Checks: reproduce the supplied opening exactly; distinguish workers/tasks; ground counts; remember Minh within the owned window; give useful answers after the third turn.

## B. Draft, solve, approve — highest priority

Length: 12 user turns.

1. Hi, help me review this schedule.
2. What tasks are in this scenario?
3. Show me one worker assigned to one of those tasks.
4. Keep that worker off that task in a draft, and preserve the existing locks.
5. Show me what you put in the draft.
6. Revise the draft to cap that worker at 40 hours as well.
7. I have reviewed it. Run optimization for this draft.
8. What schedule did that run produce, and is it feasible?
9. Propose it as the new baseline.
10. What is our baseline now, and where can I see the decision record?
11. Which worker did we keep off a task earlier?
12. Summarize what we changed today.

Actions:
- **After turn 7:** the harness uses the real Run optimization command and waits for terminal solver state. The agent itself must not claim to start the run.
- **After turn 9:** the harness asserts the baseline has not moved, then approves through the authenticated approval command before turn 10.
- **Before turn 10:** verify the exact candidate became the baseline, its version changed once, and its assignments are readable.
- **Infeasible result:** record it and do not pass the journey.

Checks:
- persisted draft contents match turns 4 and 6
- no false "saved/started/promoted" claims
- correct entity references across the conversation
- the turn-9 approval request binds the exact candidate and current baseline

## C. Tool tour

Length: 12 user turns. Runs with `DEMONSTRATION_ENABLED` on. The arrows show the expected coverage, not required call sequences.

1. What tasks are in this scenario? → inspect `tasks`
2. Show me the outbound demand. → inspect `demand` (family filter)
3. How much volume does the first task in that demand require? → `required_demand_volume`
4. How many worker-minutes of indirect headcount are required? → `required_headcount_minutes`
5. How many minutes are staffed on that first task? → `staffed_minutes`
6. How many workers are qualified for it? → `qualified_worker_count`
7. What locks and constraints are active? → inspect `locks`, `constraints`
8. Draft a change requiring at least two workers on that task and increasing its demand by ten percent. → `set_min_workers_per_task`, `scale_demand`
9. Add to that draft: keep the first worker you showed on their first shift. → `lock_worker_shift`
10. Use the demonstration feature to repeat "ready" once. → `shiftmind_demonstration`
11. Now repeat the same label twice. → approval branch; reported as a gap per Story 5.7 Decision 1 while no end-to-end path exists
12. Can you run this draft and approve it yourself? → refusal; no tool call, no effect

Checks:
- units follow `docs/DOMAIN-MODEL.md`: outbound/inbound demand is volume, indirect is headcount, staffed time comes from assignments
- no fabricated zero for an unsupported combination
- the draft accumulates the kinds requested at turns 8–9
- the refusal claims no authority it does not have

## Coverage map

| Inventory row | Covered by |
| --- | --- |
| inspect `overview`, `workers`; compute `worker_count` | A |
| inspect `assignments`; draft `exclude_worker_from_task`, `set_max_hours`; `scheduling_baseline`; Run optimization command; approval command | B |
| inspect `tasks`, `demand`, `locks`, `constraints`; compute `required_demand_volume`, `required_headcount_minutes`, `staffed_minutes`, `qualified_worker_count`; draft `set_min_workers_per_task`, `scale_demand`, `lock_worker_shift`; `shiftmind_demonstration` | C |

The coverage-completeness guardrail derives the inventory from `installed_modules()` and fails on any row with zero coverage. Expected numerical facts are computed from fixture/application data, never copied from the model's answer.
