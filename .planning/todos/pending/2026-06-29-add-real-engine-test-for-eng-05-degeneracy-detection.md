---
created: 2026-06-29T16:06:51.278Z
title: Add real-engine test for ENG-05 degeneracy detection (WR-05)
area: testing
source: 02-REVIEW.md (WR-05), 02-VALIDATION.md (Manual-Only)
severity: info
files:
  - backend/tests/test_engine_degenerate.py:20-33
  - backend/engine/cpsat/engine.py:116-124
---

## Problem

`backend/tests/test_engine_degenerate.py` validates a **hand-copied `_detect_warnings`
mirror** (test file lines 20-33), not the real ENG-05 detection loop in
`backend/engine/cpsat/engine.py:116-124`. The production detection path and the
`status=lex.status` invariant therefore have **zero direct automated coverage** — a
drift between the copy and the real loop would pass green while production breaks.

Recorded as manual-only in `02-VALIDATION.md` (user decision 2026-06-29), so Phase 2
is "validated (partial)", not nyquist-compliant. This todo tracks promoting it to an
automated test.

## Solution

Add a real-engine test:
1. Build a `SchedulingProblem` with a task family that has real demand but **no
   qualified/available workers** (zero supply for that family).
2. Call `create_engine("cpsat").solve(problem, config)`.
3. Assert: (a) `result.warnings` contains an entry naming the starved family + its
   required hours, and (b) `result.status` equals the solver's own status (detection
   did not alter it).

Once added, update `02-VALIDATION.md` to mark ENG-05 fully covered and flip
`nyquist_compliant` accordingly. Reproduction steps already in the VALIDATION.md
Manual-Only section.
