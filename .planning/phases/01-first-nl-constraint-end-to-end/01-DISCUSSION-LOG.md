# Phase 1: First NL Constraint End-to-End - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-28
**Phase:** 1-First NL Constraint End-to-End
**Areas discussed:** Which tool to prove with, Override JSON shape + IDs, Parse endpoint contract, Stub provider behavior

---

## Which tool to prove with

| Option | Description | Selected |
|--------|-------------|----------|
| set_min_workers_per_task | Additive soft shortfall-penalty in round2_cost; can't break feasibility; effect obvious in schedule | ✓ |
| lock_worker_shift | Soft reward for a specific member/window; brittle — must pin an exact generated shift var | |
| set_max_hours | Soft tightening of an existing hard weekly-hours cap; overlaps existing logic, less visible | |

**User's choice:** set_min_workers_per_task

### Follow-up: scope of the floor

| Option | Description | Selected |
|--------|-------------|----------|
| Per demanded hour | Floor of N on the task each demanded hour; reuses per-(task,hour) coverage_terms | ✓ |
| Distinct members over week | N distinct members touch the task somewhere in the week; coarse, needs new indicator vars | |

**User's choice:** Per demanded hour
**Notes:** Penalty term: for each (task,hour) with demand, `shortfall_h = max(0, N - assigned_h)`, `round2_cost += W * sum(shortfall_h)`.

---

## Override JSON shape + IDs

| Option | Description | Selected |
|--------|-------------|----------|
| List of override objects | JSON list, append-friendly, natural for multiple constraints | |
| Dict keyed by id | id → override object; O(1) lookup/removal, natural dedup | ✓ |

**User's choice:** Dict keyed by id

### Follow-up: id minting

| Option | Description | Selected |
|--------|-------------|----------|
| Random short uuid | `ov_` + uuid4 hex slice; matches existing id style; no dedup | |
| Content hash | `ov_` + sha256(tool+canonical(args)); idempotent re-submit; dedups identical constraints | ✓ |
| Sequential index | ov_1, ov_2…; human-readable but read-modify-write race under WAL | |

**User's choice:** Content hash
**Notes:** Pairs with dict-keyed store for idempotent re-submits — same constraint → same key → overwrite. Hash must use canonicalized (sorted-key) args.

---

## Parse endpoint contract

| Option | Description | Selected |
|--------|-------------|----------|
| Parse + store only | Parse/validate/store; re-solve via existing run trigger reading overrides into SolverConfig | ✓ |
| Parse + store + auto-run | Same POST also kicks a re-solve and returns a run id; couples parse to solve | |

**User's choice:** Parse + store only

### Follow-up: route path

| Option | Description | Selected |
|--------|-------------|----------|
| Nested under scenario | POST /scenarios/{id}/constraints; mirrors runs hanging off scenarios | |
| Top-level constraints route | POST /constraints with scenario_id in body; flatter | ✓ |

**User's choice:** Top-level constraints route

---

## Stub provider behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Keyword-routed | Light keyword/regex extraction → real tool_use; tests exercise text→args logic | ✓ |
| Fixed single tool_use | Always same canned block; only proves wiring | |
| Scripted by test | Stub returns pre-loaded queue; max control, no stub logic | |

**User's choice:** Keyword-routed

### Follow-up: wire-format fidelity (conflict surfaced + resolved)

| Option | Description | Selected |
|--------|-------------|----------|
| Full tool_use block now | Real {type,id,name,input}; Phase 4 Claude drops in with zero parse changes | |
| Minimal dict now | Simplified {tool,args}; full shape deferred to Phase 4 | (initially) |

**User's choice:** Initially "Minimal dict now" — but flagged as conflicting with locked TEST-01 / Success Criterion 4 ("Claude-faithful tool_use blocks"). User clarified (free text) they wanted minimal *for extensibility to other LLMs*, worried full fidelity would couple to Anthropic.

**Resolution (layered design, locked):** The earlier question conflated two layers.
- Protocol contract `LLMProvider.parse_constraints(text) -> list[OverrideCall]` stays **provider-neutral** (the extensibility seam; future Gemini etc. return the same domain type).
- Claude-faithful `tool_use` blocks `{type,id,name,input}` are an **internal detail** of the Claude/Stub provider's parse step, translated → OverrideCall.

This satisfies TEST-01/SC4 AND the user's vendor-agnostic goal — no requirement change needed. User confirmed: "Yes, lock it."

---

## Claude's Discretion

- Phase-1 placeholder penalty weight `W` (calibration is Phase 4 / ENG-04) — pick a sensible constant that's honored without dominating round-2 cost.
- Exact `OverrideCall` dataclass field shape (kept in `domain/`).
- How `run_service._execute` threads `scenario["overrides"]` into `SolverConfig`.

## Deferred Ideas

- v2 `remove_override` tool (NLC-07) — dict-keyed-by-id store chosen partly to ease this later; not built now.
- Real Claude provider + full wire-format across the boundary — Phase 4.
- Other four tools, parse-UX fields, broad validation, insight reports — later phases.
