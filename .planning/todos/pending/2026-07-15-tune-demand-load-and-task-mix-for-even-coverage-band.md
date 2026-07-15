---
created: 2026-07-15T15:32:34.487Z
title: Tune DEMAND_LOAD and task mix for even coverage band
area: engine
files:
  - backend/fixtures/build_short_input.py:49
  - backend/fixtures/build_short_input.py:269
---

## Problem

On the committed tiny fixture, coverage lands very unevenly across functions —
Receiving comes out around 10% and Pick around 35%, while others land far higher.
This is a fixture-shape artifact, not an engine bug: `DEMAND_LOAD = 1.3`
(`build_short_input.py:49`) scales OB/IB demand to ~1.3x the kept workforce's
weekly capacity, and the resulting `demand_scale`
(`build_short_input.py:269`) doesn't distribute that load evenly across the task mix.

Cosmetic / demo-quality only. Nothing is blocked by it and no test depends on the
current spread. It matters if a demo or screenshot needs to show a plausible,
evenly-utilised distribution centre rather than two visibly starved functions.

Carried over from `docs/PLAN.md` Phase 1 follow-ups (marked deferred/optional),
migrated into GSD when that hand-written tracker was retired at the v0.3/v0.4
boundary. It had never existed anywhere in `.planning/`.

## Solution

TBD. Likely either lower `DEMAND_LOAD` so total required hours sit closer to real
supply capacity, or rebalance how demand is apportioned across the task mix so
per-function required hours track each function's qualified-member supply. Worth
checking whether the unevenness is actually qualification coverage in the
subsampled workforce rather than demand scaling — if so, the fix belongs in member
subsampling, not `DEMAND_LOAD`.
