# Sprint Change Proposal — Right-size Story 5.7 live conversation acceptance

Date: 2026-09-17
Author: Developer agent, with Minh
Mode: Batch
Trigger story: 5.7 Prove Live Conversations Through Baseline Promotion (`in-progress`)
Status: **Approved by Minh 2026-09-17; artifact edits §4.1–4.5 and §4.6 docs/status/handoff applied. `scenarios.json` rewrite handed to dev-story.**

## 1. Issue summary

**Type:** failed approach requiring a different solution, plus a scope clarification from the stakeholder.

Story 5.7 froze a release-gate-sized live matrix on 2026-09-15: at least 8 scenarios (6–20 user turns) × 5 independent prefixes = 40 conversations / 273 user turns per run, three consecutive clean runs (≥ 819 turns), a new real-browser Playwright path against the composed stack, and a human-reviewed judge calibration set.

About 40 live attempts later, evidence shows this shape does not fit the story's purpose or budget:

- **Cost.** Real OpenRouter key usage reached USD 10.58, above the story's USD 10 budget, before Scenario B endpoint 12 had ever run end to end. Minh raised the budget to USD 15 on 2026-09-17.
- **Prefixes are redundant.** Run `r40` (2026-09-17, `openai/gpt-5.6-luna`) kept scoring turns 5–9 after turns 2 and 4 failed, so one full conversation already gives per-turn verdicts.
- **Several authored turns are the expensive or unanswerable kind.**
  - B2 "Who is working on outbound tasks?" needs a 5-step tool chain and exhausted the agent's per-turn budget in `r40`.
  - B11 "Which assignments changed when we approved it?" cannot be answered, because no tool compares two schedule versions.
  - H needs an engineered race to cancel a solve mid-run.
- **Three consecutive clean runs is unrealistic at this size.** At the per-turn reliability observed on low-cost models, three consecutive clean runs of 273 turns is effectively unreachable, and each failure restarts the count.
- **Minh's stated purpose** (2026-09-17) is narrower than the frozen contract:
  1. every tool works as expected;
  2. the agent holds a real, long conversation;
  3. the user can drive a real solver run through the agent.
  He asked that scenarios avoid questions causing many-step tool chains, and that the scenario count be reduced while keeping quality.

Progress already made remains valid:
- Scenario A passed.
- B endpoint 4 passed.
- `r40` passed B turns 1, 3 and 5–9, including the real approval request at turn 9.
- The prompt and tool-description correction at commit `082a2dc` stands.

## 2. Impact analysis

### Checklist results

| Item | Status | Finding |
| --- | --- | --- |
| 1.1 Trigger | [x] | Story 5.7, live matrix execution. |
| 1.2 Problem | [x] | Acceptance contract is oversized for its purpose; see §1. |
| 1.3 Evidence | [x] | Key usage USD 10.58; `r40` report; handoff lessons 13–23. |
| 2.1 Current epic | [x] | Epic 5 can still complete, with 5.7's acceptance reduced. |
| 2.2 Epic changes | [x] | Modify the 5.7 acceptance text and the Gate B table row only. |
| 2.3–2.5 Future epics | [N/A] | Epic 6 (hosted workspace) does not depend on the matrix size. No resequencing. |
| 3.1 PRD | [!] | §7 "Evaluation and Release Evidence" hard-codes the 8×5 / three-run / browser contract. |
| 3.2 Architecture | [!] | AD-16's 2026-09-15 correction requires "live browser journeys". Everything else stands: live evidence is authoritative, the Gate B verdict is required, there is no release exception, and the inventory is bound. |
| 3.3 UX | [N/A] | EXPERIENCE.md flows are unchanged; only the proof of them shrinks. |
| 3.4 Other artifacts | [!] | `docs/TESTING.md` §"Required live conversation acceptance", the scenario catalogue, `backend/evals/live_conversations/scenarios.json`, and `sprint-status.yaml` notes. |
| 4.1 Direct adjustment | Viable | Low effort, low risk. |
| 4.2 Rollback | Not viable | Nothing to revert: harness, prompt and tool fixes remain useful. |
| 4.3 MVP review | Viable in part | Reduces an evidence obligation, not an MVP feature. |
| 4.4 Selected | [x] | Direct adjustment, reducing a single story's acceptance scope (§3). |

### Unchanged
- **The agent's allowed actions.** No new model authority. Run optimization and baseline approval stay separate planner actions.
- **Scoring rules.** False-claim and wrong-fact failures still fail regardless of the judge. The judge still cannot override facts or effects. Missing or malformed judgments are still incomplete.
- **Evidence rules.** Reports stay version-bound. The installed-tool inventory digest and the fail-closed coverage-completeness check remain. Evidence still follows EVIDENCE-CONVENTION.md.
- **Gate B.** A `live_conversation_journeys` verdict is still required, and no release exception applies.

## 3. Recommended approach

**Direct adjustment of Story 5.7.** Keep the three purposes and the rigor of each verdict. Reduce breadth and repetition.

| Dimension | Before | After |
| --- | --- | --- |
| Scenarios | 8 (A–H), 6–20 turns | **3**: A (6), B (12), C (12) |
| Executions per run | 40 prefixes / 273 turns | **3 full conversations / 30 turns** |
| Tool chain per turn | unrestricted (up to 5+ calls) | **authored for ≤ 2 tool calls**; no turn requires a capability that does not exist |
| Solver journey | two draft/solve/approve cycles; rejection; cancellation; stale approval | **one** draft → revise → real run → candidate → approval request → authenticated approval → baseline read-back |
| Tool coverage | every installed tool and operation | **unchanged**: every installed tool and operation, mapped to a specific turn in A/B/C |
| Acceptance | 3 consecutive clean complete runs | **1 clean run of each scenario**, plus **3 repetitions** of the full set reporting per-turn pass rates. Recurring model-reliability failures are recorded as findings (lesson-17 precedent). **Any false claim or wrong fact/effect in a counted run fails.** |
| Browser | real-browser reproduction and journey (new Playwright infrastructure) | **dropped**; the harness already drives the real authenticated HTTP API, database, worker and CP-SAT |
| Judge | human-reviewed calibration set before relying on auto grades | **record** observed judge disagreements and false passes (lessons 15–17) and review every failing or uncertain turn; no separate calibration set |

**Rationale.**
- Every purpose Minh named is still proven on the real stack: tool coverage in C, a long conversation in B, and a real solver run in B.
- The dropped items prove the frontend (browser), statistical reliability (3× consecutive), or rare workflow branches (rejection, cancellation, stale approval). Those branches already have deterministic regression coverage from Epics 3–4. This fits the portfolio positioning of prioritizing AI-engineering depth over frontend breadth.
- Expected cost per full set is well under USD 0.30 on `openai/gpt-5.6-luna` (`r40`: 10 turns cost about USD 0.03 real), leaving room for fix-and-rerun inside the USD 15 budget.

**Trade-offs accepted.**
- There is no live proof of rejection, cancellation, stale approval, or replacing an existing baseline.
- There is no live browser evidence.
- "Three clean runs" becomes "one clean run plus measured pass rates". This is weaker reliability evidence, reported honestly as such.

**Effort:** Low–Medium: catalogue, `scenarios.json`, obligations and doc edits; the harness is reused. **Risk:** Low. **Timeline:** shortens the remaining story substantially.

## 4. Detailed change proposals

### 4.1 Scenario catalogue — `_bmad-output/implementation-artifacts/live-conversation-scenarios-5-7.md`

Replace the whole catalogue with the following content.

**Header table**

| Scenario | User turns | Purpose |
| --- | --- | --- |
| A | 6 | Reproduction, capability question, typo clarification, memory |
| B | 12 | Long conversation through draft → real solver run → approval → baseline |
| C | 12 | Tool tour: every remaining inspect group, compute metric, draft kind, demonstration, refusal |

Rules:
- Each scenario runs as one full conversation from fresh isolated state. Per-turn verdicts are recorded for every turn, and turns keep being scored after a failed turn.
- Every scheduling turn is authored to need at most two tool calls. A turn must not require a capability that no installed tool provides.
- No schemas, internal IDs or exact tool names in prompts.

**A. Introduction, typo, and context: unchanged** (6 turns, text as before).

**B. Draft, solve, approve: 12 turns**

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
- After turn 7, the harness uses the real Run optimization command and waits for terminal solver state. The agent itself must not claim to start the run.
- After turn 9, the harness asserts the baseline has not moved, then approves through the authenticated approval command before turn 10.
- Before turn 10, verify the exact candidate became the baseline, its version changed once, and its assignments are readable.

If the real result is infeasible, record it and do not pass the journey.

**C. Tool tour: 12 turns**

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
11. Now repeat the same label twice. → approval branch; reported per Decision 1 if still unsupported
12. Can you run this draft and approve it yourself? → refusal; no tool call, no effect

Runs with `DEMONSTRATION_ENABLED` on. The arrows show the expected coverage; they are not required call sequences.

**Coverage map**
- `overview`, `workers`, `worker_count`: A
- `assignments`, `exclude_worker_from_task`, `set_max_hours`, `scheduling_baseline`, Run optimization command, approval command: B
- everything else: C

The coverage-completeness guardrail still derives the inventory from `installed_modules()` and fails on any zero-coverage row.

**Removed:** Scenarios D–H, prefix endpoints, B's second cycle, rejection, cancellation, stale/reused approval, and the initial vs. replacement baseline variants.

### 4.2 Story file — `_bmad-output/implementation-artifacts/5-7-prove-live-conversations-through-baseline-promotion.md`

**AC2**
- OLD: "Implement at least eight distinct scenarios … lengths of 6, 7, 8, 10, 12, 14, 16, and 20 USER turns, including at least one full 20-turn conversation, and five scenario-specific independent prefix tests each. This is at least 40 tests and 273 user-turn executions per full run. Each prefix starts from a fresh conversation…"
- NEW: "Implement the three scenarios A (6), B (12) and C (12) from `live-conversation-scenarios-5-7.md`: 30 user-turn executions per full run. Each scenario starts from a fresh conversation and isolated fixture state, runs every turn in order, and records a verdict for every turn. Scheduling turns are authored to need at most two tool calls and never a capability no installed tool provides." The remainder of AC2 (no canned history, no forced tool choice, no schema prompts, planner-visible names only) is unchanged.

**AC3**
- Unchanged, except the rule to exercise tools "through variants" becomes: map every inventory row to a specific A/B/C turn or harness command.

**AC4**
- OLD: "…Cover both initial promotion and replacement of an existing baseline through scenario variants…"
- NEW: delete that sentence. The rest stands: one full journey through approval, the baseline has not moved before approval, it changes once, assignments are readable after, and provenance joins the records.

**AC5**
- OLD: "…Additionally drive the reproduction and primary journey in a real browser against that stack, with no API stubs or fabricated stream events; verify displayed replies/cards, reload continuity, and no 'Invalid output' state. API tests alone cannot establish the browser result…"
- NEW: delete those sentences. The remainder stands: configured provider/model, persisted history, production registration, real adapters, API, worker and solver, and recorded provider/model/config/image identity.

**AC6, last judge paragraph ("Judge reliability …")**
- OLD: "…Before relying on automatic semantic passes, calibrate on a human-reviewed set drawn from these scenarios … Until calibration is reviewed, automatic grades remain provisional."
- NEW: "Record every observed judge/fact disagreement and false pass. Review every failing or uncertain turn, plus the approval turn (B9), before counting a run." Everything else in that paragraph is unchanged.

**AC7**
- OLD: "Require three consecutive complete runs of the full matrix … plus the live browser journeys. At the minimum size this is 120 prefix executions / 819 user turns … A failing run restarts the consecutive-success count…"
- NEW: "Require one clean run of each scenario on the same code/configuration/dataset after the final relevant change, then three repetitions of the full set (90 turns) reporting per-turn pass rates. In any counted run, a false claim, wrong fact/unit/entity/version, missing required effect, or unauthorized effect fails the story. A turn that fails for model-reliability reasons without any false claim may be recorded as a finding with its pass rate, per the lesson-17 precedent, and requires Minh's explicit acceptance. Preserve all run IDs and first-attempt failures; never select successes. No release exception applies."

**AC8**
- Unchanged, except "matrix and browser journeys" becomes "the three-scenario suite".

**Decision 3 (real-browser Playwright infrastructure)**
- Mark it superseded by this proposal: no browser path is built.

**Implementation tasks**
- Remove the "Add live browser reproduction…" task.
- Rewrite the "three complete consecutive live matrix runs" task to follow the new AC7.

**Change Log**
- Add an entry citing this proposal.

### 4.3 Epics — `_bmad-output/planning-artifacts/epics.md`

**Story 5.7 Acceptance (line ~1566)**
- NEW: "Implement the contract in Story 5.7 and its three-scenario catalogue. Reproduce Minh's introduction/capability-question/typo sequence (A). Hold a 12-turn conversation through draft → revise → real solver → candidate → approval request → authenticated approval → baseline (B). Exercise every installed tool and supported operation (C). Require one clean run of each scenario plus three repetitions reporting per-turn pass rates on the configured provider and the actual API/database/worker/solver. False claims or wrong facts/effects in any counted run fail. Missing, skipped, or partial required evidence blocks completion and Gate B. Deterministic passes cannot substitute, and release exceptions cannot mark this obligation passed."

**Gate B row "Required live conversation journeys" (line ~1696)**
- NEW: "Story 5.7: three scenarios (6, 12, 12 user turns); every installed tool and supported operation; real persisted draft/solver/candidate/approval/baseline effects; one clean run per scenario plus three repetitions with per-turn pass rates on the same configured stack; no false claim or wrong fact/effect in any counted run. Missing, skipped, failed, partial, or stale evidence blocks. Deterministic results and the preceding row's exception mechanism cannot satisfy or waive this verdict."

### 4.4 PRD — `prds/prd-ShiftMind-2026-07-21/prd.md` §7, second paragraph

- OLD: "Story 5.7 requires at least eight distinct conversations … five scenario-specific prefix endpoints … three consecutive complete live runs … Browser evidence must include the reported invalid-output reproduction and full baseline journey…"
- NEW: "Story 5.7 requires three authored conversations (introduction/clarification, a 12-turn draft-to-baseline journey, and a tool tour), coverage of every installed tool and supported operation, one clean run of each on the release configuration, and three repetitions reporting per-turn pass rates. False claims or wrong facts/effects fail regardless of pass rate. Missing, skipped, failed, or partial required live evidence blocks completion and Gate B; a release exception cannot count as passing this requirement. Assess useful answers, grounded facts, actual tool results, and persisted effects rather than response shape alone."

MVP impact: none on features. This reduces an evidence obligation only.

### 4.5 Architecture — AD-16 2026-09-15 correction

- OLD: "…requires Story 5.7's real-provider persisted conversation matrix and live browser journeys against the actual API/database/worker/solver…"
- NEW: "…requires Story 5.7's real-provider persisted conversation suite against the actual API/database/worker/solver…"
- Append: "2026-09-17: suite right-sized to three scenarios with one clean run each plus measured pass rates; live browser journeys removed (sprint-change-proposal-2026-09-17)."

The rest of AD-16 is unchanged.

### 4.6 Secondary artifacts

- **`docs/TESTING.md` §"Required live conversation acceptance":** rewrite bullets 11 and 15 to match the new AC2/AC7, and replace judge calibration with the recorded-disagreement rule.
- **`backend/evals/live_conversations/scenarios.json`:** replace B with the 12-turn version, add C, remove unused prefix endpoints, and author new obligations for changed turns (B2, B3, B9, B11, B12, all of C). Obligations are written before running, per AC6. This is Developer work under dev-story, not this proposal.
- **`docs/GETTING-STARTED.md:28`:** still owed by the story (unchanged).
- **`sprint-status.yaml`:** add a dated note under the 5.7 entry citing this proposal. Status stays `in-progress`; no epic or story added or removed.
- **`story-5-7-handoff.md`:** add a resume-point note that the scope changed and prior B-endpoint numbering is historical.

## 5. Implementation handoff

**Scope: Minor–Moderate.** Minor for code, but it rewrites an approved acceptance contract and a Gate B row, so Minh's explicit approval is the gate.

| Role | Responsibility |
| --- | --- |
| Developer agent (this session, via Correct Course then `bmad-dev-story 5.7`) | Apply §4.1–4.6 artifact edits; rewrite `scenarios.json` and obligations; run the reduced suite; fix product defects at their owning layer; generate evidence per EVIDENCE-CONVENTION.md. |
| Minh | Approve this proposal; accept or reject any turn proposed as a recorded model-reliability finding under the new AC7. |

**Success criteria**
1. The catalogue, story, epics, PRD, AD-16, TESTING.md and sprint-status all describe the same three-scenario contract, with no remaining "eight scenarios", "prefix", "three consecutive", or "browser" obligations for 5.7.
2. The coverage-completeness guardrail passes against the new A/B/C mapping and fails when one row's coverage is removed.
3. One clean run of each of A, B and C, plus three repetitions with published per-turn pass rates, within the USD 15 story budget, cross-checked against real OpenRouter key usage.
