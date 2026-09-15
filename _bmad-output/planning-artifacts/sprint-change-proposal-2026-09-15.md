# Sprint Change Proposal — Live Conversation Acceptance

Date: 2026-09-15
Project: ShiftMind
Scope: Moderate — corrective Epic 5 story and release-acceptance changes.
Mode: Batch, using the requirements already supplied by Minh.
Authorization: Minh replied “ok” to the offered correction: create a corrective story and update testing guidance for progressive real conversations, all tool calls, and draft-to-baseline execution. This authorizes the planning edits below; it is not a claim that implementation or live verification has occurred.

## 1. Issue summary

Minh reports that ShiftMind returns “Invalid output: The model returned an invalid response” during an ordinary conversation. The supplied sequence is `HI my name is Minh`, `how can you help me?`, then `how many work are therre?`. The concrete example reaches three user messages, while the wider report describes four or more turns. Root cause and reproducibility remain unverified.

The evidence gap is verified by repository inspection: all six files in `backend/evals/golden_multi_turn/history_and_tools/` contain two user turns. `dependent-call-success.json` supplies exact tool names and JSON instructions; `long-history-window.json` inserts 105 filler activities. These can test narrow routing/history behaviors, but they do not establish sustained natural conversation or the full proposal/optimization/baseline outcome. Existing story completion must not be presented as evidence for that broader claim.

## 2. Impact analysis

| Area | Impact and disposition |
| --- | --- |
| Epic 5 / Stories 5.5–5.6 | Keep historical completed work; add Story 5.7 as backlog and require it before the next Gate B assessment. Epic 5 is already in progress. |
| Epics 1–4 | Their capabilities, persistence, solver, approval and browser paths are dependencies to exercise; fix defects there if live evidence identifies them. No rollback or redesign is currently justified. |
| Epic 6 | Remains backlog. Hosted work is not obsolete, but cannot establish the local conversational acceptance missing from Epic 5. |
| PRD §7 | Replace the implication that live behavior is merely a supplemental demonstration with mandatory real-conversation acceptance. Core MVP scope and planner journey remain unchanged. |
| Architecture AD-16 | Keep deterministic invariant evidence and require separate live conversational acceptance. Bind the installed-tool inventory and a mandatory Gate B verdict. Preserve application-owned history, explicit run grants, authenticated approval, and finite budgets. |
| UX EXPERIENCE Flow 1 and recovery flows | Existing draft/run/approval/reload semantics already match the requested workflow. No visual redesign needed. Test actual visible replies and actions; UI fixes are driven by observed failures. |
| Testing docs and release aggregation | Document the new unimplemented obligation. Story 5.7 owns its executable command, matrix, coverage and required `live_conversation_journeys` verdict. Merely documenting the gate does not implement it. |
| Evidence handling | Permit sanitized planner-visible transcripts for authored test conversations in dedicated evidence; maintain content-disabled production telemetry and exclude secrets/provider internals. |

Technical investigation touches the existing agent runtime/translation, persisted conversation use case, capability registry, proposal/run/approval commands, worker, solver, and browser surfaces. No defect is attributed to one layer before reproduction. Six installed modules were found: scheduling inspect, compute, draft, optimize, baseline, and demonstration. Coverage must re-derive operations from current code and include actual executed effects, not assume this static list is sufficient.

## 3. Recommended approach

**Direct adjustment:** add Story 5.7 and strengthen the existing Gate B acceptance. Use existing evaluation/report mechanisms and real application paths, extending them where necessary for durable multi-turn journeys. Start implementation with live reproduction; prioritize the draft → solver → candidate → approval → baseline outcome.

The selected work is to fix conversational failures and prove the existing full workflow live. The Correct Course template also asks whether to undo earlier changes (“rollback”) or reduce/replan MVP features. Neither is selected; they do not add tasks or reduce the requested coverage.

Estimated effort: medium-to-high; actual duration depends on reproduced defects and tool reachability. Timeline impact: the next AI-readiness/Gate B claim waits for live acceptance. Provider latency/spend and nondeterminism require bounded runs and honest partial outcomes, not reduced scope disguised as success. The initial minimum is eight narratives × five prefixes × three complete repetitions: 120 prefix executions, 819 user turns, plus browser runs and coverage variants. This is a planning floor, not a measured runtime or cost estimate.

## 4. Detailed changes — before → after

| Artifact / section | Before | After | Rationale |
| --- | --- | --- | --- |
| PRD §7 opening | “Release evaluation is deterministic-first. A live model demonstration supplements but does not replace automated evidence.” | Live conversations on the configured provider, all tools/operations, real baseline journey, and three complete runs are mandatory acceptance; deterministic checks protect their own invariants. | The actual AI experience must work to call it ready. |
| Architecture AD-16 | Deterministic-first release evidence; live runs explicit and budgeted. | Live conversation acceptance plus deterministic invariant evidence; required current `live_conversation_journeys` verdict, inventory binding, and safe authored-test transcripts. | Keeps authority boundaries while making live evidence actionable. |
| Epic 5 story sequence | Corrective sequence ends at 5.6. | Add 5.7, linking its complete story and eight-scenario catalogue; prioritize before Gate B. | Makes the missing outcome owned implementation work. |
| Gate B table | General live readiness permits time-bounded exceptions. | Add an independent mandatory natural-conversation gate; missing/failing evidence and exceptions cannot make it pass. | Prevents a waived or partial suite being called complete. |
| Sprint status | 5.6 done; no owner for this failure/coverage gap. | 5.7 backlog; comment distinguishes the two-turn evidence from natural readiness; update date. | Preserve history and expose outstanding work. |
| `docs/TESTING.md` | Existing commands describe deterministic and narrow live suites. | Lead with required live acceptance, exact reproduction, actual coverage/effects, budgets and evidence rules; explicitly state the new runner/gate is unimplemented. | Avoid a false completion claim or misleading runnable command. |
| New Story 5.7 | Absent. | Eight concrete acceptance criteria, implementation tasks, known inventory, boundaries, and QA handoff. | Gives development a reviewable execution contract. |
| New scenario catalogue | Absent. | Eight varied-length natural conversations (6–20 user turns, including a complete 20-turn conversation), explicit real application actions, semantic checks, clarification/fixture rules, and coverage-growth requirements. | Supplies real conversation content rather than another abstract test plan. |

Exact resulting files:

- `../implementation-artifacts/5-7-prove-live-conversations-through-baseline-promotion.md`
- `../implementation-artifacts/live-conversation-scenarios-5-7.md`
- `../implementation-artifacts/sprint-status.yaml`
- `epics.md`
- `prds/prd-ShiftMind-2026-07-21/prd.md`
- `architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md`
- `../../docs/TESTING.md`

The minimum of eight narratives and three runs are implementation planning choices that make Minh's accepted requirements measurable. Add scenarios/variants to achieve complete operation coverage; never count prefixes or repeats as distinct narratives. Real user clarifications can extend a conversation beyond its declared length and must be recorded.

## 5. Implementation handoff

**User refinement:** Minh requested varied conversation lengths and at least one 20-turn conversation. The catalogue now has lengths 6, 7, 8, 10, 12, 14, 16 and 20, with five scenario-specific prefix endpoints each. The 20-turn journey performs two connected proposal/solve/approval cycles. Answer scoring is specified in Story 5.7: independent factual/effect checks plus a calibrated LLM-as-judge rubric, with uncertain semantic grades reviewed by a human. This remains planned implementation work.

- Product/backlog: the planning changes above are applied; Story 5.7 remains backlog, with priority before the next Gate B assessment.
- Developer: implement Story 5.7 and its catalogue; first reproduce the supplied live sequence. Discover the configured model and supported startup/authentication path without exposing credentials. Fix actual failures, build complete coverage and execute the real stack.
- QA/reviewer: assess all runs, first failing turns, retries, useful answers, grounded facts and actual effects. Verify no mocked replies or grants replaced production behavior; verify the current tool inventory and the real baseline pointer/assignments/audit after approval.
- Release owner: require current bound passing evidence for `live_conversation_journeys` in Gate B. Do not claim this correction closes unrelated Gate B issues such as the existing golden-dataset floor.

Success: eight or more varied-length natural conversations, including at least one full 20-turn conversation, five independent prefixes each, complete installed-tool/operation coverage, three consecutive complete live runs plus browser evidence, and verified draft-to-baseline effects. Known failures and incomplete evidence block completion. Historical deterministic evidence cannot satisfy this outcome.

## 6. Checklist and execution record

- [x] 1.1–1.3: trigger, problem and supplied failure recorded; limited existing test evidence inspected. Live root cause remains an implementation task.
- [x] 2.1–2.5: current/future epic impacts and priority assessed; additive Epic 5 correction selected.
- [x] 3.1–3.4: PRD, architecture, UX and testing/release impacts assessed. No visual redesign needed.
- [x] 4.1–4.4: direct adjustment selected; template alternatives evaluated and explicitly excluded from the selected work above.
- [x] 5.1–5.5: summary, impacts, exact changes, MVP impact and handoff documented.
- [x] 6.1–6.3: requirements checked against the accepted direction; authorization comes from Minh's “ok” to the concrete six-point recommendation in the preceding turn. No new permission requested for the already-authorized planning edits.
- [x] 6.4: sprint entry added as backlog; historical completion retained.
- [x] 6.5: responsibilities and next execution step recorded here.
- [!] Runtime implementation, live reproduction, complete live results, and executable gate integration remain outstanding under Story 5.7. No live tests were run during this planning correction.

Validation: check document links, story identifiers, scenario/turn counts, changed-file whitespace, and consistency between story, sprint, PRD, AD-16, testing guidance and Gate B. Documentation verification is not live acceptance evidence.
