# Phase 2: Scenario Detail + Plain-English Constraints - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-17
**Phase:** 2-Scenario Detail + Plain-English Constraints
**Areas discussed:** Overrides source, Display fidelity, Input model, Outcome states

---

## Applied-overrides source (SCEN-03, criterion 1)

Surfaced as the central decision: no HTTP path returns a scenario's persisted
overrides today (`ScenarioOut` omits them; the `overrides` column is never read
back over the API). Satisfying "see every override currently applied" requires a
choice with a scope consequence.

| Option | Description | Selected |
|--------|-------------|----------|
| Add a backend read path | Expose overrides over HTTP (field on `ScenarioOut` or a dedicated `GET /scenarios/{id}/overrides`). Satisfies criterion 1 on load and reload. Cost: a second backend change beyond BE-01 + a `schema.d.ts` regen. | ✓ |
| Session-only accumulation | Show only overrides applied in the current browser session (from `POST /constraints` `applied[]`). No backend change, but pre-existing overrides never appear and the list is empty on reload — arguably fails criterion 1. | |

**User's choice:** Add a backend read path.
**Notes:** Chosen knowingly despite adding a second backend change to a milestone
that scoped BE-01/CORS as the only one — the session-only option cannot meet
criterion 1. Endpoint-vs-field shape left to the planner.

---

## Override display fidelity (CONS-02)

The stored `overrides` column keeps only `{tool, args}` — the human-readable
`parsed_constraint` echo is returned by `POST /constraints` then discarded on
persist. A reloaded override therefore reads as raw tool+args with an internal
task id, unlike a freshly-applied one.

| Option | Description | Selected |
|--------|-------------|----------|
| Persist parsed_constraint too | Store the echo in the overrides column so a reloaded override reads identically to a fresh one. One render path. Small addition to the D-01 backend change. | ✓ |
| Humanize tool+args on the client | Frontend reconstructs readable text from `{tool, args}`. No backend change, but duplicates parser phrasing (drift risk) and only has the task *id*, not the name. | |
| Accept two fidelities | Fresh items show the rich echo; reloaded items show a plainer rendering. Least work, but visibly inconsistent and the reloaded form is the "raw JSON" CONS-02 forbids. | |

**User's choice:** Persist parsed_constraint too.
**Notes:** User asked for a full explanation of the mechanics before deciding;
chose option 1 as the clean single-render-path answer, consistent with already
having picked the backend read path. CONTEXT.md carries a migration note: legacy
overrides stored without the field must degrade gracefully.

---

## Constraint box interaction model (CONS-01, CONS-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Running transcript | Session log of each submission + its parse outcome (chat-like) above the durable overrides list. Makes clarify-and-rephrase natural. More UI. | ✓ |
| Latest-result only | Show only the most recent submission's outcome next to the input; the overrides list is the durable record. Simpler. | |

**User's choice:** Running transcript.
**Notes:** Transcript is session-only (attempts + outcomes); the overrides list is
the durable record of what is applied. The two are kept conceptually separate.

---

## Outcome-state rendering (CONS-03, CONS-04, CONS-05)

| Option | Description | Selected |
|--------|-------------|----------|
| Four fully distinct treatments | Applied (list), rejected (inline reason + options), clarification (question/rephrase), 503 provider-down (distinct banner). Directly satisfies criteria 3/4/5. | ✓ |
| Minimal: success vs error only | Collapse into worked/failed. Simplest, but loses the 503-vs-invalid distinction criterion 5 requires and hides partial-apply detail. | |

**User's choice:** Four fully distinct treatments.
**Notes:** Extended in CONTEXT.md (D-05) to also handle `no_constraint_found: true`
as a neutral fifth outcome — a real response field, not an error and not a success.

---

## Claude's Discretion

- Backend shape for the overrides read (field on `ScenarioOut` vs dedicated endpoint).
- Backfill vs graceful-fallback for legacy overrides missing `parsed_constraint`.
- Editor layout (transcript above overrides) within shadcn/ui + Tailwind.
- TanStack Query keying/invalidation for the overrides read vs scenario-detail query.

## Deferred Ideas

- Override deletion / editing — not in Phase 2 criteria; no backend `DELETE` path exists. Future phase.
- Seeing an override's effect on the schedule — Phase 3 (run trigger + polling); `POST /constraints` does not solve.
