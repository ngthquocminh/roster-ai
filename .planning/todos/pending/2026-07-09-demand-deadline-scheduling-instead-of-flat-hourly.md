---
created: 2026-07-09T00:00:00.000Z
title: Demand scheduling should target deadline fill, not flat hourly distribution
area: engine
severity: improvement
files:
  - backend/engine/cpsat/builder.py (_aggregate_demand, ~line 111)
---

## Problem

`CpSatBuilder._aggregate_demand` flattens each demand band into per-hour buckets
(lines 125–137). For VOLUME demand it proportionally spreads `amount` across the
overlapping hours (`ov / dur`). This implicitly models demand as "serve X units
each hour" — but the real business requirement is to accumulate enough labour
output before the band's deadline (`b.end_h`), not to distribute effort evenly
across every hour inside the window.

Consequence: the coverage penalty is computed hour-by-hour, so the solver is
incentivised to spread workers uniformly across the window rather than front-load
or batch them optimally toward the deadline. A demand band that runs 08:00–16:00
with amount=8 is treated as "need 1 unit/hour" rather than "need 8 units done
by 16:00", which penalises valid schedules that concentrate work early and leaves
the last hour lightly covered.

## Solution Idea

Model each demand band as a **cumulative deadline constraint** rather than an
hourly slice:

- Track total labour-units (worker-hours × rate) assigned to the task across the
  entire band window.
- Penalise shortfall against the full `amount` at `end_h` rather than per-hour
  sub-shortfalls.
- For INDIRECT (headcount) demand the current per-hour model is still correct
  (headcount is an instantaneous requirement), so keep that path unchanged.

This is a non-trivial change to the objective structure — coverage_terms,
round1_cost (unmet), and round2_cost (shortfall) all reference the per-hour
structure. Approach: add a `demand_deadline_mode` flag to `SolverConfig` so the
old and new formulations can coexist during transition.
