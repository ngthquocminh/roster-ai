# Sprint Change Proposal — Epic 5 Multi-Turn Live-Provider Golden Evaluations

**Date:** 2026-09-14  
**Project:** ShiftMind  
**Change scope:** Moderate — additive corrective story; backlog reorganisation only

## 1. Issue Summary

Story 5.5 made the live-provider golden suite real and explicitly non-authoritative. Its final evidence covers 26 live-eligible, primarily single-turn cases. It does not exercise the real provider across the application-owned multi-turn paths that are central to the product: history-aware routing, use of a preceding trusted tool result, dependent tool-call sequencing, durable conversation rehydration, and the bounded history window.

This is an evaluation coverage gap, not evidence that the existing durable-history or tool controls are defective. Existing deterministic tests already cover rehydration and the 100-message owned-history bound; their release authority remains unchanged. The proposed story adds opt-in live observation of those behaviors, with finite application-owned budgets and complete version binding.

A deterministic pass alone is insufficient to claim that the AI feature is ready for the provider/model configuration actually deployed. A live pass is therefore **necessary but not sufficient** for AI-feature release: it proves no safety or correctness invariant on its own, but a failing release-eligible live scenario is a readiness failure that blocks the AI feature until it is fixed or a time-bounded, owned release exception is explicitly approved.

## 2. Impact Analysis

### Epic and story impact

Add **Story 5.6: Evaluate Real-Provider Multi-Turn History and Tool Continuity [Corrective Insert]** after completed Story 5.5. Epic 5 returns/remains `in-progress` until Story 5.6 and the existing Gate B decisions are resolved. No completed story is changed or rolled back.

### Artifact impact

| Artifact | Impact |
| --- | --- |
| `epics.md` | Add Story 5.6 after Story 5.5’s recorded corrective insert/reference; add it to the Epic 5 sequence; clarify the Gate B live-evaluation row as necessary-but-not-sufficient evidence for the configured release model. |
| `sprint-status.yaml` | Add Story 5.6 as `backlog`; retain Story 5.5 as `done`. |
| Story artifact | Create `5-6-evaluate-real-provider-multi-turn-history-and-tool-continuity.md` with the approved acceptance criteria and implementation guardrails. |
| Evaluation harness/cases | Add a versioned multi-turn case shape and deterministic counterparts; extend the opt-in runner and diagnostics to record turn order and safe per-turn verdicts. |
| `docs/TESTING.md` | Document the explicit command/configuration, finite budgets, non-authoritative status, and no-secret handling for the multi-turn live suite. |

### PRD, architecture, and UX

The PRD (§7), architecture spine (AD-16), and UX specifications already require deterministic-first, version-bound, budgeted live evaluation and durable application-owned history. No PRD, architecture, or UX wording revision is necessary: NFR26’s “never the sole release evidence” permits a live pass to be required alongside deterministic evidence. The Epic 5 release-gate wording must make that joint rule explicit. No capability authority, provider access, API surface, or persistence schema is widened.

## 3. Recommended Approach

**Direct adjustment — recommended.** Add the corrective story to Epic 5 and implement it on the existing deterministic harness and live diagnostics runner.

This preserves the authority boundary: deterministic equivalents remain the authority for correctness and safety, while a live pass for the pinned release configuration is a necessary readiness condition and can never replace deterministic evidence. It is preferable to rollback (no completed behavior needs reversal) or an MVP review (the MVP scope is unchanged).

**Estimated effort:** Medium (roughly 2–4 engineering days, excluding optional provider-diagnostic reruns).  
**Risk:** Medium. Provider variability, cost, and unavailable credentials are contained by an explicit opt-in marker/configuration, finite application-owned limits, safe partial diagnostics, and versioned case eligibility.  
**Timeline impact:** One corrective Epic 5 story; it should be sequenced before the next Gate B release-gate assessment.

## 4. Detailed Change Proposals

### Epics — add Story 5.6

**OLD**

Epic 5 contains the existing Story 5.5 live-provider routing correction, but no Epic 5 story makes real-provider multi-turn behavior a named, versioned evaluation obligation.

**NEW**

```md
### Story 5.6: Evaluate Real-Provider Multi-Turn History and Tool Continuity [Corrective Insert]

As a portfolio reviewer,
I want opt-in, version-bound live-provider evaluations that exercise multi-turn
conversation continuity,
So that real-provider behavior is observable across the history and tool-result
paths that deterministic release evidence already protects.

Acceptance Criteria:

Given a versioned multi-turn golden scenario
When its deterministic equivalent runs in normal CI
Then it remains the authoritative correctness-and-safety release-gate evidence
And the scenario asserts history-aware routing, use of prior tool results,
ordered dependent tool calls, durable conversation rehydration, and the
100-activity history-window boundary.

Given explicitly enabled live evaluation with a configured provider and
application-owned finite limits for cases, requests, tool calls, tokens,
elapsed time, and spend
When the same scenario runs
Then each turn receives only application-owned history and trusted prior tool
results
And the report records ordered calls and per-turn outcomes without persisting
sensitive prompt or tool-result content.

Given a history-aware routing scenario
When a later prompt depends on an earlier tool result or clarified entity
Then the live provider selects only currently granted tools and uses the prior
trusted result where required
And an absent, stale, unauthorized, or truncated antecedent fails closed rather
than being silently invented or retargeted.

Given a long conversation
When persisted activities exceed the owned history-window bound
Then the live run proves the provider receives only the newest bounded window,
the older activities remain durable but are not supplied, and the outcome makes
no claim that omitted history was retained.

Given a release-candidate model, prompt, tool, policy, application, and image version
When every release-eligible live multi-turn scenario runs under its explicit
application-owned budget
Then every scenario must pass before the AI feature is released
And a live failure blocks that release until its root cause is fixed and rerun,
or an explicitly approved exception names its owner, rationale, scope, expiry,
and compensating user-facing limitation.

Given a live report
When its evidence is written
Then it binds dataset, evaluator, provider/model, prompts, tools, policy,
application, scenario, solver, code, and image versions
And it is marked opt-in and budgeted; a live pass is necessary but never
sufficient, and can neither satisfy nor weaken the deterministic release gate.
```

**Rationale:** Covers the live-provider boundary omitted by Story 5.5 while preserving NFR26/NFR27 and AR16. It prevents the AI feature from being released with a known live failure, without treating a variable provider result as proof that deterministic safety and correctness controls work.

### Epic 5 release gate — make joint evidence explicit

**OLD**

```md
No live-provider result satisfies any gate on its own; live suites are named,
gated, budgeted, non-authoritative.
```

**NEW**

```md
Deterministic evidence is mandatory and authoritative for safety and correctness.
For the pinned release provider/model configuration, every release-eligible live
scenario must also pass under its explicit application-owned budget. A live pass
is necessary but never sufficient: it cannot satisfy, weaken, or replace a
deterministic gate. A live failure blocks the AI feature unless an explicit,
time-bounded release exception records owner, rationale, scope, expiry, and
user-facing limitation.
```

**Rationale:** Makes “gated” operationally meaningful and avoids releasing an AI feature known to fail with its configured real provider.

### Sprint status — add backlog item

**OLD**

`5-5-make-the-live-agent-route-the-golden-dataset: done`

**NEW**

```yaml
5-5-make-the-live-agent-route-the-golden-dataset: done
5-6-evaluate-real-provider-multi-turn-history-and-tool-continuity: backlog
```

**Rationale:** The new corrective story is planned work; it must not rewrite Story 5.5’s completed evidence.

### Architecture and PRD — no edit

The implementation must conform to existing NFR26, NFR27, AR16, and AD-16. This proposal deliberately does not make live-provider verdicts authoritative for safety/correctness, introduce provider-controlled history, or change the 100-message application-owned bound. It does make a passing release-eligible live suite a necessary, jointly evaluated AI-release condition.

## 5. Implementation Handoff

**Classification:** Moderate.

| Recipient | Responsibility |
| --- | --- |
| Product Owner / backlog maintainer | Apply the approved `epics.md` and `sprint-status.yaml` changes; preserve the corrective-story provenance. |
| Developer | Create Story 5.6; implement the versioned multi-turn evaluation contract, deterministic equivalents, opt-in live execution, bounds, diagnostics, and documentation. |
| Evaluation/QA owner | Verify deterministic counterparts remain authoritative, live runs are opt-in and budgeted, report bindings are complete, and every release-eligible live case passes for the pinned release model before the AI feature ships. |

### Success criteria

1. A multi-turn golden scenario has deterministic release-gate coverage for every named behavior.
2. The live suite is impossible to run by default, has finite application-owned limits, and every release-eligible case passes for the pinned release configuration.
3. Each live report records complete version bindings, explicit `live`/non-authoritative provenance, and safe per-turn diagnostics.
4. The live suite proves no provider receives browser-supplied or unbounded history, and no history-window omission is misrepresented as retained memory.
5. Gate B requires both deterministic authority and a passing release-eligible live suite; a live pass is necessary but never sufficient.

## Checklist Record

| Item | Status | Finding |
| --- | --- | --- |
| 1.1–1.3 Trigger and evidence | Done | Story 5.5 is the triggering story; its 26-case live suite exposes a multi-turn coverage gap. |
| 2.1–2.5 Epic impact | Done | Add one corrective Epic 5 story; do not reorder or invalidate other epics. |
| 3.1 PRD | Done | Fully aligned; no change required. |
| 3.2 Architecture | Done | Fully aligned; no change required. |
| 3.3 UX | N/A | No user-interface or journey change. |
| 3.4 Other artifacts | Done | Evaluation case/runner contracts, testing documentation, and sprint status change. |
| 4.1 Direct adjustment | Viable | Medium effort/risk; recommended. |
| 4.2 Rollback | Not viable | No completed implementation needs reversal. |
| 4.3 MVP review | Not viable | MVP scope and release authority are unchanged. |
| 5.1–5.5 Proposal/handoff | Done | Defined above. |
| 6.1–6.2 Review | Done | Proposal is internally consistent with the authoritative deterministic-first boundary. |
| 6.3–6.5 Approval/status/handoff | Action-needed | Await explicit approval before modifying epics or sprint status. |
