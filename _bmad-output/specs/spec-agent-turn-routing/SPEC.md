---
id: SPEC-agent-turn-routing
companions:
  - routing-paths.md
  - brownfield.md
sources: []
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability only — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Agent Turn Routing

## Why

A mandate and a pain. FR-6 requires the agent to refuse out-of-scope requests, yet in conversation `f0cdeca6` the live agent sang a song and wrote quadratic-equation Python: `RefusalV1` with reason `out_of_scope` exists, but nothing in the prompt triggers it. Separately, every turn — even "hi" — pays for the full ~270-line prompt and every tool. A cheap routing decision before each turn fixes both, and must stay simple and revertible: rare edge cases are deferred.

## Capabilities

- **CAP-1**
  - **intent:** Each new planner message is classified as `scheduling`, `direct` or `out_of_scope` before the agent runs.
  - **success:** The route label and its probability appear on the turn's trace span; a router error, timeout, below-threshold probability, missing key or `off` mode yields `scheduling` and the turn proceeds.

- **CAP-2**
  - **intent:** Off-topic requests get a refusal that points the planner back to scheduling instead of an answer.
  - **success:** Replaying `f0cdeca6`, the song and Python messages end as a refusal with reason `out_of_scope` and no off-topic content reaches the planner; a mixed message ("how many workers are there, and write me Python") gets the scheduling answer without the off-topic part.

- **CAP-3**
  - **intent:** Greetings, thanks and capability questions get a short answer without the full prompt or any tool.
  - **success:** Such a turn is granted zero tools, uses the direct prompt, and states no schedule facts, numbers, or features the app lacks.

- **CAP-4**
  - **intent:** Scheduling requests keep today's behaviour.
  - **success:** The full-path prompt minus the added scope section equals today's `SCHEDULING_ASSISTANT_INSTRUCTIONS` (pinned by a test); existing tests pass unchanged; the live-eval scheduling journeys pass at their committed baseline.

- **CAP-5**
  - **intent:** An operator can switch routing off with one setting.
  - **success:** With `AGENT_ROUTER_MODE=off` no routing request is made and every turn takes the `scheduling` path.

## Constraints

- Special paths grant no tools: `direct` returns only a grounded answer, `out_of_scope` only a refusal. A misroute can weaken an answer, never add capability.
- Fail-open: router error, timeout, probability below threshold, missing key or mode `off` → `scheduling`. The router never fails a turn.
- Jev receives message text only — the latest planner message and the previous exchange — never scenario records, tool results or the workflow snapshot.
- Reuse the tier-1 claim checker's Jev provider, endpoint and key resolution; no new vendor or key.
- Approval-resume turns bypass the router.
- CI stays keyless: default test settings resolve no Jev key, so every turn routes to `scheduling` and existing tests are unchanged.
- `direct` and `out_of_scope` turns still pass through `execute_turn` and the grounding gate; no exemption path.
- No DB migration and no new activity type: routes surface through the existing agent response and `refused` terminal outcome (the UI already labels `out_of_scope`).

## Non-goals

- Escalating a `direct` turn to the full path.
- Multi-question decision tables, deterministic pre-rules, greeting fast-paths, route caching, running Jev in parallel with other reads.
- Shadow mode, circuit breaker, threshold tuning from data.
- Further paths: `planner_control`, `prompt_attack`, `explain_concept`, `workflow_status`, tool-scoped paths.
- Multilingual routing evals and a large routing dataset.
- Answering "which model are you?" with provider disclosure.

## Success signal

- Replaying `f0cdeca6` on the live stack with routing on: the five small-talk messages get short tool-free replies, the song and Python requests end as "Out of scope" refusals pointing back to scheduling, and the live-eval scheduling journeys still pass. Setting `AGENT_ROUTER_MODE=off` sends every turn down the full path again.

## Assumptions

- The prompt split is lossless; the added scope section is the only change to the full-path prompt (resolves "byte-identical" vs "scope rule in the shared core").
- `AGENT_ROUTER_MODE` defaults to `on` when a Jev key resolves, like the tier-1 checker; with no key it is off with one warning.
- Threshold 0.85 and router timeout 2 s are validated settings; tuning is deferred.
- "Previous exchange" means the last two planner messages and the last two agent replies, each truncated to a fixed length.
- The full-prompt change requires a paid live-eval rerun to refresh the committed Story 5.8 baseline.
