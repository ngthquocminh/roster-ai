# Feature Research

**Domain:** LLM layer over a constraint-based workforce scheduler (Phase 3 — NL constraint editing + insight generation)
**Researched:** 2026-06-28
**Confidence:** MEDIUM

> **Mandate:** design.md / PLAN.md define the baseline feature set. Each feature is tagged
> `confirm-baseline` (research validates the plan) or `propose-change` (research suggests
> a gap or adjustment). Phase 4 (frontend) and Phase 5 (what-if/deploy) are explicitly
> out of scope and appear only in the Anti-Features section.

---

## Research Basis

The following bodies of evidence inform this analysis:

- **MeetMate** (arxiv 2312.06908): LLM + CP-SAT meeting scheduler with 5 constraint action
  types; NL → structured constraint calls with interactive confirmation.
- **ConstraintLLM / OptiMUS**: multi-stage NL→constraint pipelines with entity extraction,
  schema validation, and solver injection.
- **SMILO** (arxiv 2511.02364): LLM-to-MILP translation for workforce scheduling; 90%
  correctness using a 3-stage pipeline (component ID → info extraction → template injection).
- **OR-Tools CP-SAT soft-constraint examples**: enforcement literals (`only_enforce_if`),
  linear slack variables, and soft-sum constraints are the validated patterns for
  NL-derived overrides that must never make the model infeasible.
- **Agentic tool-use research** (SAGE-Agent, CoVe, AWARE-US): ambiguity handling, ID
  validation, and error-feedback-to-LLM are table stakes in production tool-calling agents.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features the LLM layer must have to feel complete. Missing any of these makes the
layer feel broken or untrustworthy.

| Feature | Tag | Why Expected | Complexity | Notes |
|---------|-----|--------------|------------|-------|
| NL → validated tool call (parse NL into one of the 5 solver hooks) | confirm-baseline | Core value proposition; every comparable system uses structured function calling as the primary mechanism | MEDIUM | JSON schema per tool; LLM emits typed call; application validates before applying |
| `lock_worker_shift` tool | confirm-baseline | "Fix Alice to Monday morning" is the archetypal scheduling constraint; found in every comparable system | LOW | Soft via enforcement literal on the shift variable |
| `set_min_workers_per_task` tool | confirm-baseline | "We need at least 3 people on Outbound" — minimum staffing is a universal manager concern | LOW | Soft via linear slack on coverage constraint |
| `exclude_worker_from_task` tool | confirm-baseline | "Bob can't do Receiving this week" — exclusion/restriction is table stakes | LOW | Soft via enforcement literal gating the task variable |
| `scale_demand` tool | confirm-baseline | Managers adjust demand estimates mid-week; exposing this as an NL target is appropriate for a system built on materialized demand tables | MEDIUM | Scales `OutboundDemand`/`InboundDemand` volume; triggers re-solve |
| `set_max_hours` tool | confirm-baseline | Labor compliance, fatigue management — hour caps are a near-universal regulatory requirement | LOW | Soft via weekly-hours cap override; penalty weight above cost |
| ID validation before solver application | confirm-baseline | All reviewed production systems validate entity refs against the domain before executing tool calls; unknown IDs fed back to LLM as error | LOW | Validate member/task IDs against real scenario data; return structured error to LLM |
| Plain-English error when parsing fails or ID is unknown | propose-change | Users need to know WHY their request failed; raw exceptions or silent no-ops destroy trust | LOW | Not explicitly in current spec; should be in API response contract |
| Soft-constraint application (never infeasibility) | confirm-baseline | Prevents the solver from becoming unsolvable due to a bad NL tweak; enforcement literals and linear slack vars are the validated CP-SAT pattern | MEDIUM | Extends existing penalty pattern already in the model |
| `LLMProvider` Protocol + Claude implementation | confirm-baseline | Vendor-swap seam is standard in production LLM integrations | LOW | Already planned; Claude default; Gemini behind same seam later |
| Stubbed LLMProvider for CI tests | confirm-baseline | No live LLM in CI is universal practice; stubs drive deterministic test suites | LOW | Already planned |
| Insight report: run metrics → structured NL | confirm-baseline | Post-run plain-language summary is the standard "explain what happened" feature in every scheduling assistant reviewed | MEDIUM | Structured JSON metrics input → sectioned NL output via prompt |
| Insight citing specific numbers | propose-change | Generic "coverage improved" is insufficient; users need "OB Picking: 65% → 78% (+13pp)" to act on the report | LOW | Add to insight prompt: require concrete metric values, not relative language |
| Insights generated as a separate post-run step | confirm-baseline | LLM failure must not invalidate a successfully computed schedule; this decoupling is industry standard | LOW | Already planned; schedule marked COMPLETED before insight generation starts |

### Differentiators (Competitive Advantage)

Features that raise trust and usability above a bare-bones NL→solver integration.
Not strictly required for Phase 3 to function, but meaningfully differentiate
a production assistant from a prototype.

| Feature | Tag | Value Proposition | Complexity | Notes |
|---------|-----|-------------------|------------|-------|
| Confirmation/preview of parsed constraint before re-solve | propose-change | System echoes "I understood: lock Alice to OB Picking, Tuesday 06:00–14:00. Apply?" — prevents silent misinterpretation and builds user trust; found in MeetMate and subsequent CP+LLM systems | MEDIUM | Adds a confirmation round-trip to the constraint API endpoint; requires frontend in Phase 4 to be actionable, but the API contract should expose the parsed-intent string now |
| Ambiguity clarification flow | propose-change | When NL is ambiguous ("reduce hours for overnight staff" — which staff?), the LLM returns a clarification question rather than a best guess; SAGE-Agent research shows 7–39% coverage improvement with this pattern | MEDIUM | Requires multi-turn API design; at minimum the response should include a `clarification_needed` field and a question string |
| Constraint acknowledgment in insight report | propose-change | Insight should note "1 override active — excluded Bob from Receiving" so the user understands results in context of applied tweaks | LOW | Add a `applied_overrides` section to the insight prompt |
| Active constraint list endpoint | propose-change | Users need to see what overrides are currently on the scenario ("what have I asked for so far?"); analogous to MeetMate's ListConstraints action | LOW | `GET /scenarios/{id}/overrides` already implied by the `overrides` JSON column but not explicitly spec'd as a readable endpoint |

### Anti-Features (Deliberately Not Building in Phase 3)

Features that are commonly requested but explicitly out of scope for this milestone.
Documenting them prevents scope creep.

| Feature | Tag | Why Requested | Why Out of Scope | What Phase Handles It |
|---------|-----|---------------|------------------|----------------------|
| Frontend NL constraint input box | out-of-scope | Users want to type constraints in a UI | Phase 4 only; Phase 3 is API + engine | Phase 4 |
| What-if delta explanation (compare two runs) | out-of-scope | "What changed between the baseline and the tweaked schedule?" is high value | Depends on LLM layer landing first; design.md explicitly defers | Phase 5 |
| Hard/infeasibility-inducing constraints from NL | by-design | Managers may phrase absolute requirements ("Alice MUST work Monday") | Never making the model infeasible is a safety guarantee; all overrides are soft | N/A — use penalty weight tuning |
| Live LLM API in CI | by-design | Would catch real parsing regressions | Cost, flakiness, and latency make live LLM calls unsuitable for CI | Stub provider handles this |
| Streaming solve feedback | not-now | Real-time progress during a long solve is useful UX | Over-engineering for Phase 3; solve runs in a thread and status is polled | Phase 4/5 |
| Constraint ranking / priority management | not-now | Advanced users want to order which override wins if two conflict | Over-engineering; fixed penalty weights handle priority implicitly | Phase 5+ |
| Multi-user constraint ownership / auth | not-now | "Who added this constraint?" matters in team workflows | No auth yet; single-tenant for now | Phase 5+ |
| Autonomous re-solve without user confirmation | by-design | Fully automated loops are tempting to implement | Removes human oversight; a bad NL parse re-solves silently with wrong constraints | Confirmation flow (above) is the answer |
| Free-form insight editing | not-now | Users wanting to annotate or edit the NL report | Out of scope; insights are read-only generated artifacts | Phase 4+ |

---

## Feature Dependencies

```
NL → tool call (parser)
    └──requires──> ID validation gate
                       └──requires──> real scenario member/task list

Soft constraint application
    └──requires──> NL → tool call (parser)
    └──requires──> CP-SAT penalty pattern (already in model)

Insight report
    └──requires──> completed run + SummaryMetrics
    └──requires──> LLMProvider Protocol

Confirmation/preview (differentiator)
    └──requires──> NL → tool call (parser)
    └──enhances──> User trust in re-solve

Ambiguity clarification flow (differentiator)
    └──requires──> NL → tool call (parser)
    └──requires──> multi-turn API design

LLMProvider Protocol
    └──enables──> Stub provider (for CI)
    └──enables──> Claude implementation
    └──enables──> Insight report
    └──enables──> NL parser
```

### Dependency Notes

- **ID validation requires real scenario data:** The validator must load the actual
  `members` and `tasks` from the scenario before calling the solver. This implies
  the parse endpoint receives `scenario_id` and loads context.
- **Insight report requires SummaryMetrics:** The run must reach `COMPLETED` status
  before insight generation starts. Never trigger insights inside the solve path.
- **Confirmation/preview requires the parsed-intent string to be returned in the
  API response:** The Phase 3 API contract should expose `parsed_constraint` (human-
  readable interpretation) alongside `tool_call` (the structured call). Phase 4 will
  surface this in the UI; Phase 3 makes it available.
- **Ambiguity flow requires multi-turn design:** The `/runs/{id}/constrain` endpoint
  should return either `{status: "applied", ...}` or `{status: "clarification_needed",
  question: "..."}` — the caller decides whether to proceed or ask the user.

---

## MVP Definition for Phase 3

### Launch With (Phase 3 v1 — this milestone)

The baseline plan is the right MVP. These are the must-haves:

- [x] `LLMProvider` Protocol + Claude implementation — enables all LLM features
- [x] NL parser → 5 solver-hook tool calls — core value
- [x] ID validation against scenario data — safety gate; table stakes
- [x] Plain-English error response on validation failure — **proposed addition, low cost**
- [x] Soft-constraint application in CP-SAT engine — safety guarantee
- [x] Insight generator: `SummaryMetrics` → NL report with specific metric values — **ensure numbers are cited, not just relative language**
- [x] Insights as a separate post-run step — resilience guarantee
- [x] Stubbed LLMProvider for CI — deterministic test coverage

### Add After Initial Validation (Phase 3 v1.x or Phase 4 setup)

Meaningful improvements that don't block the core but raise production quality:

- [ ] `parsed_constraint` field in the constrain API response — low cost; enables Phase 4 confirmation UI
- [ ] `clarification_needed` / `question` field in response for ambiguous input — enables multi-turn UX
- [ ] `GET /scenarios/{id}/overrides` readable endpoint — surfaces active constraints
- [ ] `applied_overrides` section in the insight prompt — contextualizes results

### Future Consideration (Phase 4/5)

- [ ] Frontend confirmation/preview UI — Phase 4
- [ ] What-if delta explanation — Phase 5
- [ ] Constraint priority/ranking management — Phase 5+

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| NL → 5 tool calls (parser) | HIGH | MEDIUM | P1 |
| ID validation + plain-English error | HIGH | LOW | P1 |
| Soft-constraint application | HIGH | MEDIUM | P1 |
| LLMProvider Protocol + Claude | HIGH | LOW | P1 |
| Stub provider for CI | HIGH | LOW | P1 |
| Insight generator (with specific numbers) | HIGH | MEDIUM | P1 |
| Post-run insight decoupling | HIGH | LOW | P1 |
| `parsed_constraint` in API response | MEDIUM | LOW | P2 |
| `clarification_needed` response field | MEDIUM | MEDIUM | P2 |
| Active constraint list endpoint | MEDIUM | LOW | P2 |
| `applied_overrides` in insight prompt | MEDIUM | LOW | P2 |
| Confirmation/preview UI | HIGH | HIGH | P3 (Phase 4) |
| What-if delta explanation | HIGH | HIGH | P3 (Phase 5) |

**Priority key:**
- P1: Must have for Phase 3 launch
- P2: Should have; add before Phase 4 frontend consumes the API
- P3: Future phase

---

## Validation of the 5 Solver-Hook Tools

Each tool is assessed against comparable published systems and domain logic.

| Tool | Verdict | Rationale | Soft-Constraint Mechanism |
|------|---------|-----------|--------------------------|
| `lock_worker_shift` | confirm-baseline | Analogous to "fix assignment" in MeetMate and every published scheduling assistant; archetypal manager action | Enforcement literal on shift variable; violation incurs penalty in objective |
| `set_min_workers_per_task` | confirm-baseline | Minimum staffing level is universal; found in all workforce scheduling tools | Linear slack on coverage constraint; `add(coverage + slack >= min)` with penalty on slack |
| `exclude_worker_from_task` | confirm-baseline | Exclusion/restriction constraints are table stakes; all reviewed systems include this | Enforcement literal gating task variable; equivalent to soft qualification gate |
| `scale_demand` | confirm-baseline | Less common than the assignment tools but appropriate here given the system ingests materialized demand tables; demand scaling is the mechanism managers use to simulate "higher activity weeks" | Scale demand volume before solve; compatible with existing `OutboundDemand`/`InboundDemand` structure |
| `set_max_hours` | confirm-baseline | Weekly hour caps are a labor/EBA compliance requirement; extending the existing `contracted_hours` cap with a per-override cap is the right pattern | Override the per-member weekly cap; penalty weight should exceed cost objective to ensure it's respected |

**Gap identified:** No `remove_override` / `reset_constraint` tool exists in the current plan. Without it, users cannot undo a bad NL constraint without cloning or resetting the scenario. Research (MeetMate had a RemoveConstraint action) shows this is a practical requirement once multiple overrides accumulate. **Proposed addition (low complexity):** a 6th tool `remove_override(override_id)` that removes a previously applied override by ID. This requires the overrides JSON column to store IDs, which is straightforward.

---

## Expected Behaviors: Requirements to Capture

These are concrete behaviors requirements must specify, derived from research on
comparable NL constraint assistants:

### NL Parsing Behavior

1. **Happy path:** User submits NL text → LLM emits a single tool call → application validates IDs → applies soft constraint → triggers re-solve → returns `{status: "applied", parsed_constraint: "Lock Alice to OB Picking Tuesday 06:00–14:00", tool_call: {...}, run_id: "..."}`.

2. **Unknown entity:** Tool call references a member/task ID not in the scenario → application (not the LLM) rejects with `{status: "error", error_type: "unknown_entity", message: "No worker named 'Alice' found. Available workers: Bob, Carol, Dave."}`. LLM can then produce a clarification question.

3. **Ambiguous input:** LLM cannot confidently resolve which worker/task/shift is meant → returns `{status: "clarification_needed", question: "Did you mean OB Picking or IB Receiving? Both are active tasks."}`. Application does not call the solver.

4. **Unparseable input:** NL does not map to any of the 5 tools → returns `{status: "error", error_type: "unparseable", message: "I couldn't translate that into a scheduling constraint. Try: 'Lock [worker] to [task] on [day]', 'Require at least N workers on [task]', or 'Exclude [worker] from [task]'."}`.

5. **Multiple constraints in one utterance:** Out of scope for Phase 3. Specify that the parser handles one constraint per call; multi-constraint utterances should return an error or pick the first parseable one and note the rest were ignored.

### Insight Generator Behavior

6. **Always cite specific numbers:** Every metric mentioned must include its value: "Outbound Picking coverage: 78.3% (6.2 unmet hours)." Generic statements like "coverage was acceptable" are not acceptable output.

7. **Structure per function/task family:** Report should have sections aligned with the domain's task families (Outbound, Inbound, Indirect) so managers can scan to their area.

8. **Override acknowledgment:** If any overrides are active on the scenario, the insight should note them: "Note: 1 override applied — excluded Carol from Indirect tasks. This reduced available headcount by 1."

9. **Resilient to LLM failure:** If insight generation fails, the run stays `COMPLETED` and the insights field is `null`. No retry in Phase 3; caller can re-request insights independently.

10. **Separation from solve path:** Insights are generated by a separate API call or background step after the run reaches `COMPLETED`. Never triggered inside the solver thread.

---

## Sources

- MeetMate: "I Want It That Way" — Enabling Interactive Decision Support Using LLMs and Constraint Programming (arxiv 2312.06908)
- SMILO: LLM-powered MILP modelling engine for workforce scheduling (arxiv 2511.02364)
- Structured Uncertainty guided Clarification (arxiv 2511.08798) — SAGE-Agent ambiguity handling
- CoVe: Training Interactive Tool-Use Agents via Constraint-Guided Verification (arxiv 2603.01940)
- AWARE-US: Preference-Aware Infeasibility Resolution (arxiv 2601.02643)
- OR-Tools CP-SAT soft-constraint examples (github.com/google/or-tools: soft_constraints_sat.ipynb, shift_scheduling_sat.ipynb)
- Error Handling for LLM Agent Tools — apxml.com
- Taming LLM Outputs — structured output patterns (medium.com/data-from-the-trenches)

---
*Feature research for: ShiftMind Phase 3 LLM layer (NL constraint editing + insight generation)*
*Researched: 2026-06-28*
*Confidence: MEDIUM — research cross-checks published NL+CP scheduling systems; specific production data on workforce scheduling LLM layers is sparse; patterns are drawn from analogous domains.*
