---
created: 2026-07-15T15:32:34.487Z
title: Add per-scenario engine selection
area: api
files:
  - backend/engine/base.py:33
  - backend/engine/base.py:38
---

## Problem

The solver engine is always `cpsat`. `create_engine(name)` (`base.py:33`) is a
working factory that raises on anything else (`base.py:38`:
`Available: ['cpsat']`), and the API has no way to choose an engine per scenario —
it's a `get_engine` dependency that always resolves the same way.

The `SchedulerEngine` Protocol seam exists and is honest — tests inject a stub
engine through it, which is a real (if narrow) exercise of the abstraction. But it
has never been exercised by a *second real solver*, so its adequacy as a swap
boundary is unproven. Contrast the `LLMProvider` seam, which was validated by two
genuine vendor swaps (Gemini, then OpenRouter) with zero service/route changes —
that's what a proven seam looks like.

Low urgency: there is no second engine to select, and building selection before
having something to select is speculative. The value is diagnostic — attempting a
real second backend is what would reveal whether the Protocol is actually the
right shape, or whether it leaks CP-SAT assumptions (e.g. the lexicographic
solve-and-lock structure, integer-only scaling, `solver_status` semantics).

Carried over from `docs/PLAN.md` Phase 2 follow-ups (marked deferred/optional),
migrated into GSD when that hand-written tracker was retired at the v0.3/v0.4
boundary.

## Solution

TBD. Mechanically small: add an `engine` column to `scenarios`, thread it through
`get_engine`, validate against the factory's known names. The real question is
what to select — PuLP and CPLEX are named in `design.md` as hypothetical future
backends, but neither is a committed need. Don't build the selection UI/column
until a second engine is a real requirement; the seam already exists and can
absorb it when it is.
