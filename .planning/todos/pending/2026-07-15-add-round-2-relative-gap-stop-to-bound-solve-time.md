---
created: 2026-07-15T15:32:34.487Z
title: Add round-2 relative-gap stop to bound solve time
area: engine
files:
  - backend/engine/cpsat/objective.py:43
  - backend/engine/cpsat/objective.py:47
  - backend/engine/cpsat/objective.py:63
---

## Problem

The lexicographic solve runs unmet-optimal (round 1) then locks it and minimises
cost (round 2, `objective.py:63`). Proving cost-optimality over the full week is
the expensive tail — roughly 2 minutes — while round 1 finishes in ~20s. Today the
only bound is `solver.parameters.max_time_in_seconds` (`objective.py:47`), a wall-clock
cap passed as `time_limit_s` (`objective.py:43`). A wall-clock cap is a blunt
instrument: it stops the solve without telling you how close to optimal you got,
and the round-1 snapshot exists precisely so a round-2 timeout degrades gracefully.

This matters now that the API/UI drive runs interactively — a user waiting on an
HTTP poll doesn't want to sit through a 2-minute optimality proof for a solution
that was within a fraction of a percent of optimal after 15 seconds.

Also tracked as an open decision in `docs/design.md` §5 ("Solve-time vs.
optimality"), which survives as the engineering design record. This todo is the
actionable half; §5 holds the rationale.

Carried over from `docs/PLAN.md` Phase 1 follow-ups (marked deferred/optional),
migrated into GSD when that hand-written tracker was retired at the v0.3/v0.4
boundary.

## Solution

TBD. The CP-SAT-native approach is
`solver.parameters.relative_gap_limit = <e.g. 0.01>` on the round-2 solve only,
so it stops once provably within 1% of optimal rather than proving exactness.
Leave round 1 (unmet) exact — that's the lexicographic guarantee and it's cheap.
Consider surfacing the achieved gap in `SolveResult` metrics so the API can report
"within X% of optimal" instead of silently returning a degraded answer. Interacts
with the existing `time_limit_s` cap — decide whether gap-stop replaces or
complements it.
