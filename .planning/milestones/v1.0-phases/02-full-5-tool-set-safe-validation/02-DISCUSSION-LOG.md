# Phase 2: Full 5-Tool Set + Safe Validation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-28
**Phase:** 2-Full 5-Tool Set + Safe Validation
**Areas discussed:** Multi-tool response contract, Clarification vs no-constraint, Semantics of the 4 new tools, Degenerate-solve detection

---

## Multi-tool response contract

| Option | Description | Selected |
|--------|-------------|----------|
| Partial-apply + report | Apply every valid tool call, return 200 with `applied[]` + `rejected[]` (+ clarification + no_constraint_found). A single typo never discards good constraints. | ✓ |
| Atomic (all-or-nothing) | Any failure → 400, persist nothing, user resubmits. Simplest, extends Phase 1's raise-on-first-error. | |

**User's choice:** Partial-apply + report
**Notes:** Matches criterion 5's intent of surfacing a mixed valid/invalid call. 404 reserved for unknown scenario_id (whole request can't proceed). → D-01.

---

## Clarification vs no-constraint

| Option | Description | Selected |
|--------|-------------|----------|
| Recognized-but-incomplete asks | Known constraint shape but missing/ambiguous arg → clarification_needed; nothing recognized → no_constraint_found. Reroutes today's ambiguous-match 400 into clarification. | ✓ |
| Only multi-match asks | Reserve clarification strictly for 2+ ref matches; everything else → no constraint found. | |
| No clarification in stub | Skip clarification entirely until Phase 4. (Would under-deliver NLC-05/criterion 2.) | |

**User's choice:** Recognized-but-incomplete asks
**Notes:** Ambiguous task match moves from `_resolve_task` 400 ValueError to a `clarification_needed` question. → D-03/D-04.

---

## Semantics of the 4 new tools

**`scale_demand` target:**

| Option | Description | Selected |
|--------|-------------|----------|
| Per-task factor | `scale_demand(task_id, factor)` multiplies one task's demand by factor; factor > 0. | ✓ |
| Per-family factor | Scale a whole demand family (outbound/inbound/indirect). | |
| Let me describe it | Different meaning. | |

**`lock_worker_shift` target:**

| Option | Description | Selected |
|--------|-------------|----------|
| Member + day (soft prefer) | Soft penalty if member works zero shifts on the named day; robust against exact-var brittleness. | ✓ |
| Member + shift template | Soft-penalize unless assigned a specific template. | |
| Member + time window | Soft-penalize unless working a shift overlapping a time window. | |
| Let me describe it | Specific meaning in mind. | |

**`exclude_worker_from_task` + `set_max_hours` approach:**

| Option | Description | Selected |
|--------|-------------|----------|
| Standard soft penalties | exclude = soft penalty on any member-produces-task assignment; set_max_hours = soft penalty per hour above max, layered on the existing hard cap. Both > 0 validated. | ✓ |
| Let me adjust one | One should behave differently. | |

**Clarify vs apply interaction:**

| Option | Description | Selected |
|--------|-------------|----------|
| Apply clear + ask on ambiguous | Persist the clear constraint AND return clarification for the ambiguous fragment in the same 200; all three buckets can be non-null together. | ✓ |
| Clarification short-circuits | Any clarification → apply nothing, return only the question. | |

**User's choice:** Per-task `scale_demand` · member+day `lock_worker_shift` · standard soft penalties for exclude/set_max_hours · apply-clear-and-ask.
**Notes:** All soft round-2, never infeasible. `scale_demand` is the one input-reshaping override (D-10) — flagged for researcher. → D-05…D-12.

---

## Degenerate-solve detection

| Option | Description | Selected |
|--------|-------------|----------|
| Zero supply on demanded family | Flag when a demanded task family ends up with literally zero assigned supply; surface as structured `result.warnings[]`. | ✓ |
| Below-threshold coverage | Flag below a configurable fraction (catches near-collapse); needs a tunable threshold. | |
| Let me describe it | Different trigger/surface. | |

**User's choice:** Zero supply on demanded family
**Notes:** Detection-and-flag only; never changes solver status. Phase 3 insight step consumes the warnings surface. → D-13.

---

## Claude's Discretion

- Stub multi-tool extraction (conjunction splitting) + per-tool keyword/regex patterns.
- Placeholder penalty-weight constants for the new tools (empirical calibration is Phase 4 / ENG-04).
- `parsed_constraint` echo wording per tool.
- `OverrideCall.args` per-tool dict shapes (loose typing stays).

## Deferred Ideas

- `remove_override` (NLC-07) and multi-turn auto-retry (NLC-08) — v2.
- Empirical penalty-weight calibration (ENG-04) — Phase 4.
- Insight reports (INS-*) — Phase 3 (consumes the warnings surface).
- Forbidding `scale_demand` down-scaling (factor < 1.0) — allowed for now; revisit if confusing.
