# Story 5.6: Evaluate Real-Provider Multi-Turn History and Tool Continuity

**Status:** backlog  
**Type:** Corrective insert  
**Origin:** Approved `sprint-change-proposal-2026-09-14.md`

## Story

As a portfolio reviewer,
I want opt-in, version-bound live-provider evaluations that exercise multi-turn conversation
continuity,
so that real-provider behavior is observable across the history and tool-result paths that
deterministic release evidence already protects.

## Context

Story 5.5 made the live golden suite functional for its eligible cases, but its cases do not prove
that a real provider follows application-owned multi-turn history, uses a prior trusted tool
result, preserves dependent call order, survives durable rehydration, or handles the owned
history window honestly. Existing deterministic tests remain the stable release authority for
these product invariants.

A live pass is a necessary AI-feature readiness condition for the exact pinned release
provider/model configuration, but is never sufficient: it cannot prove deterministic safety or
correctness controls. Conversely, a known failure in a release-eligible live scenario must not be
silently accepted as an MVP-ready AI feature.

## Acceptance Criteria

1. A versioned multi-turn golden scenario has a deterministic equivalent in normal CI. It asserts
   history-aware routing, prior trusted tool-result use, ordered dependent calls, durable
   rehydration, and the 100-activity history window. Its deterministic verdict remains the
   authoritative safety/correctness release evidence.
2. The live counterpart is impossible to run by default and has application-owned finite limits
   for case count, requests, tool calls, tokens, elapsed time, and spend. It does not read model
   credentials or enable network calls outside its explicit invocation path.
3. Every live turn is constructed from application-owned `AgentTurnV1` history and trusted prior
   result state only. No browser-provided transcript, provider-owned memory, or unbounded durable
   transcript becomes an authority or bypasses the history bound.
4. A scenario whose later request depends on a prior result or clarified entity proves the live
   provider selects only currently granted capabilities and uses that trusted antecedent. Missing,
   stale, unauthorized, or truncated antecedents fail closed; they are not guessed, silently
   retargeted, or replaced with a new authority.
5. A long-history scenario proves that activities older than the application-owned window remain
   durably stored but are absent from the provider input. Output/reporting makes no claim that
   omitted history was retained.
6. Reports contain ordered per-turn calls and outcomes while excluding raw sensitive prompts and
   tool-result bodies. They bind the dataset, evaluator, provider/model, prompts, tools, policy,
   application, scenario, solver, code, and image versions.
7. For the pinned release provider/model, every release-eligible live scenario passes before the
   AI feature ships. A live pass is necessary but never sufficient and cannot weaken or replace a
   deterministic gate. A failure blocks the AI feature until fixed and rerun, unless an explicit
   time-bounded exception records owner, rationale, scope, expiry, and compensating user-facing
   limitation.
8. When a failure reveals an application defect in history handling, trusted result propagation,
   sequencing, persistence, or truncation, fix the owning code and add a deterministic regression
   test. When it instead reveals prompt ambiguity, an unrealistic case, or provider variability,
   correct or classify that cause without falsely labelling it an application defect; retain the
   diagnostic evidence.

## Implementation Boundaries

- Extend the versioned evaluation-case and runner contracts only as needed to represent ordered
  multi-turn interactions and their deterministic counterparts.
- Reuse the existing opt-in live runner, diagnostic persistence approach, `RunSource`, and report
  version-binding path; do not create a second evaluation authority.
- Update `docs/TESTING.md` with the explicit invocation/configuration and readiness rule.
- Do not change the 100-message owned-history bound, capability grants, authority partition,
  durable public contracts, provider credentials, or release semantics beyond the approved joint
  deterministic-plus-live readiness rule.
- If remediation requires any excluded change, stop and route it through Correct Course.

## Handoff Verification

1. Run deterministic multi-turn regressions in the normal suite with no provider access.
2. Run the bounded live suite only through its explicit configuration against the pinned release
   provider/model; retain safe, version-bound results.
3. Demonstrate that a live-only pass cannot pass the release gate when the deterministic
   counterpart fails, and that a live failure produces a blocked AI-readiness outcome unless an
   approved exception is present.
4. Confirm no raw prompts, credentials, or tool-result content appears in diagnostics or reports.
