# Pitfalls Research

**Domain:** LLM NL-to-constraint layer over a CP-SAT optimization solver (ShiftMind Phase 3)
**Researched:** 2026-06-28
**Confidence:** MEDIUM (CP-SAT patterns from official OR-Tools docs; LLM patterns from cross-checked web sources; project-specific gaps from direct design.md / PROJECT.md reading)

> **Reading guide.** Each pitfall carries one of two design-status tags:
> - `confirm-baseline` — the existing design already mitigates this; verify during implementation.
> - `propose-change` — a gap exists; the design must address this before or during Phase 3.

---

## Critical Pitfalls

### Pitfall 1: Prompt Injection via User NL Input Reaching Solver Args

**What goes wrong:**
A user crafts a natural-language request that causes the LLM to generate tool calls with harmful argument values — for example, `scale_demand(factor=-1)` to invert demand, `lock_worker_shift(member_id="../../admin", shift_id=...)` to inject unexpected strings into downstream lookups, or `set_max_hours(hours=0)` to zero out all capacity. The LLM faithfully translates the user's intent (or a hidden adversarial instruction embedded in a fixture or scenario name) into a structurally valid tool call that passes schema validation but contains unsafe semantics.

**Why it happens:**
LLM tool-use turns prompt injection into a real-world execution risk — once a model can call APIs, adversarial input that redirects those calls has a large blast radius. The LLM sees user text as instruction, not as untrusted data. Schema type constraints (`integer`, `number`) prevent type confusion but do not constrain value ranges. If the solver receives these args without server-side bounds checking, the constraint is added silently.

**How to avoid:**
Apply a server-side argument validation layer **between the LLM response and the solver**, independent of the JSON schema. For each tool:
- `scale_demand`: factor must be in `(0.0, 10.0]` — reject zero and negative
- `set_max_hours`: hours must be >= minimum shift template length (e.g., >= 4h)
- `lock_worker_shift`, `exclude_worker_from_task`: member_id and task_id must exist in scenario (see Pitfall 2)
- `set_min_workers_per_task`: count must be a non-negative integer, not larger than total qualified headcount

This validation is separate from ID validation (Pitfall 2) and addresses value-range injection. Log rejected tool calls with the reason so they're auditable.

**Warning signs:**
- SolveResult returns OPTIMAL with 0 unmet and 0 cost after a NL tweak mentioning "reduce demand"
- A soft constraint is visible in the stored override list but produces no change in the schedule
- `scale_demand` factor in the stored JSON is 0 or negative

**Phase to address:** Phase 3, LLM Provider + validation layer implementation.

**Design status:** `propose-change` — design.md §4 confirms ID validation ("validated against scenario IDs") but does not specify value-range guard for numeric args. This is a gap.

---

### Pitfall 2: Hallucinated Member / Task IDs in Tool Calls

**What goes wrong:**
The LLM generates a tool call with a `member_id` or `task_id` that does not exist in the scenario — for example, `lock_worker_shift(member_id="EMP-9999", ...)` when the scenario has members `EMP-001` through `EMP-011`. If the validation layer silently drops the unknown ID, the override is never applied and the user sees no error but believes the constraint was honored. If the validation raises an exception, the entire NL flow crashes without a useful message.

**Why it happens:**
Claude knows the tool schema (field names, types) but does not know the live scenario data unless it's in the prompt. ID hallucination happens when: (a) entity lists are not in the prompt at all, (b) entity lists are described but IDs are truncated or paraphrased, or (c) the user refers to an entity by name and the LLM maps it to a guess. Hallucinated IDs propagate through agentic systems and cause downstream failures.

**How to avoid:**
1. Always inject the complete list of valid `member_id` values and `task_id` values for the scenario into the system prompt (or tool description context) before the NL parse call. For the current 11-member fixture this is small; for larger scenarios, include at minimum a name→ID map.
2. After receiving the tool call response, validate every ID argument against the scenario's known entity sets before proceeding. Reject with a structured error message that names the invalid ID and lists valid alternatives — return this as a `tool_result` with `is_error: true` so Claude can self-correct in a follow-up turn.
3. Use Claude's tool feedback loop (multi-turn): send the validation error back as a tool result, allow Claude to retry with a corrected ID.

**Warning signs:**
- Tool call `member_id` doesn't appear in any fixture entity list
- Unit test for "unknown member rejection" passes but live Claude returns a different name format than the fixture uses
- User says "I asked to lock Alice but nothing changed"

**Phase to address:** Phase 3, NL constraint parser.

**Design status:** `confirm-baseline` for the rejection requirement — design.md §4 states "validated against scenario IDs (reject unknown member/task refs)." `propose-change` for the feedback loop: the design does not specify whether rejection is terminal or triggers a Claude retry turn. The retry/feedback pattern must be designed explicitly.

---

### Pitfall 3: Trivially Degenerate Solves from Unbounded NL Tweaks

**What goes wrong:**
A structurally valid, ID-validated tool call produces a degenerate solve that appears to succeed but is meaningless:
- `scale_demand(task_id="OB-1", factor=0.0)` → demand drops to zero → solver reports OPTIMAL with 0 unmet and low cost, because there's nothing to cover. The "improvement" is an artifact.
- `set_max_hours(hours=0)` → no valid shifts can be generated → all demand unmet → the schedule is maximally bad, but reported as FEASIBLE.
- `exclude_worker_from_task` applied to ALL qualified workers for a task → same effect: fully unmet for that task, solver treats it as a soft-constraint failure.

These are not infeasible (soft constraints guarantee feasibility), but they produce misleading schedules that downstream insight generation will describe as "improvements."

**Why it happens:**
The "soft constraints never make the model infeasible" guarantee correctly prevents solver crashes but does not prevent semantically empty solutions. The LLM may generate these values in good faith when a user says "ignore outbound demand for now" or "freeze all workers."

**How to avoid:**
1. Add semantic bounds to the argument validation layer (see Pitfall 1): `scale_demand` factor must be > 0.0; `set_max_hours` must be >= minimum shift template length from the scenario; `set_min_workers_per_task` must not exceed qualified headcount.
2. After re-solve, compute a "sanity delta" — if total unmet hours increased by more than X% compared to the baseline run, surface a warning to the caller rather than silently returning the result.
3. Insight generator must include a "degenerate solve" detection step: if coverage for any task family drops to 0% post-override, flag it explicitly in the report rather than narrating it as an optimization success.

**Warning signs:**
- Re-solve after a NL tweak reports lower cost AND lower coverage simultaneously with no explanation
- Any task shows 0% coverage post-override when baseline had > 0%
- `scale_demand` factor in stored overrides equals 0.0

**Phase to address:** Phase 3, arg validation layer + post-solve sanity check.

**Design status:** `propose-change` — soft-constraint safety is confirmed (design says "a bad tweak penalizes, never infeasible"), but degenerate-solution detection is not in the design. This is a gap.

---

### Pitfall 4: Soft Constraint Penalty Miscalibration

**What goes wrong:**
CP-SAT soft constraints work by adding a penalty variable to the objective. If the penalty weight is too low relative to the existing objective scale, the solver treats the override as cost-free to violate and ignores it — the override is stored and looks active but has no effect on the schedule. Conversely, if the penalty is too high, it dominates the lexicographic objective: the cost round (round 2) no longer minimizes labor cost — it minimizes the override deviation instead, distorting cost reporting.

Concretely: the existing model minimizes `unmet_hours` (round 1) then `labor_cost` (round 2). If an override penalty is added to the same objective function at a weight comparable to `labor_cost`, the cost round outcome changes unpredictably based on the penalty, not the actual labor cost.

**Why it happens:**
The existing model uses a lex two-round approach: round-1 locks unmet, round-2 minimizes cost. Adding override penalties to either round's objective without calibrating them against the existing scale is a silent correctness bug — the solver still returns OPTIMAL but the objective meaning has changed.

**How to avoid:**
1. Add override penalty terms to round-2 (cost round) only, not round-1 (unmet round). This preserves the coverage guarantee.
2. Calibrate penalty magnitudes: override penalties should be < 10% of the expected round-2 cost range. Concretely: if average weekly labor cost is ~$50,000 (×100 in integer units = 5,000,000), a single override violation penalty should be at most 50,000 integer units — large enough to push the solver to satisfy it when possible, small enough not to distort the cost objective when it conflicts.
3. Write a test that verifies: (a) applying `set_min_workers_per_task(task, n)` when `n` is satisfiable results in a schedule that actually satisfies it; (b) applying it when `n` exceeds qualified headcount results in the BASELINE coverage (override ignored gracefully, not a crash).
4. Use `add_soft_sum_constraint` / enforcement-literal pattern from OR-Tools rather than adding penalties ad hoc. The OR-Tools shift scheduling notebook (`shift_scheduling_sat.ipynb`) demonstrates this pattern with hard_min/hard_max + soft_min/soft_max and explicit cost coefficients per violation.

**Warning signs:**
- Applying a `set_min_workers_per_task` override produces no visible change in the schedule
- The round-2 (cost) objective value changes significantly after adding an override even when the override doesn't affect shift assignments
- Reported labor cost jumps by an unusual amount when an override is active

**Phase to address:** Phase 3, engine override integration.

**Design status:** `propose-change` — design.md says overrides are applied as soft constraints but does not specify penalty calibration, which objective round they enter, or test criteria for penalty effectiveness. This is a gap.

---

## Moderate Pitfalls

### Pitfall 5: Nondeterminism Breaking Reproducible Solves

**What goes wrong:**
CP-SAT with `num_workers > 1` is nondeterministic by design — different runs of the same model with the same seed may produce different (but equally optimal) schedules. When NL overrides are added, the model structure changes with each tweak, making the nondeterminism more pronounced. A user who runs the same NL constraint twice gets two different schedules and loses confidence in the system.

OR-Tools issue #3590 confirms CP-SAT produces nondeterministic results in versions 9.4+ with multi-worker configurations. The current codebase pins ortools to 9.11 (CONCERNS.md) and sets a fixed seed in Phase 1.

**How to avoid:**
1. For NL-override re-solves, add `solver_params.num_search_workers = 1` to force deterministic search (at a solve-time cost), or explicitly document that re-solves with the same overrides may produce alternate-optimal schedules.
2. Store the full override list in the run record (the `overrides` JSON column already exists in the Phase 2 schema) so runs are identifiable. Two runs with identical override lists that produce different schedules are both correct; the user should understand this.
3. Do NOT rely on the seed alone for determinism with `num_workers > 1` — the OR-Tools docs confirm the seed controls initial diversification but does not guarantee determinism under multi-worker search.

**Warning signs:**
- Re-running "same" NL constraint on same scenario gives a different schedule
- Test suite produces intermittent failures on schedule-content assertions (not on metric assertions)

**Phase to address:** Phase 3, solver configuration for override re-solves.

**Design status:** `propose-change` — Phase 1 sets a fixed seed and achieves determinism for the baseline case. But with multi-worker re-solves under NL overrides, this guarantee weakens. An explicit decision is needed.

---

### Pitfall 6: LLM Call Blocking the FastAPI Event Loop

**What goes wrong:**
The NL constraint parsing call to Claude (`anthropic.messages.create(...)`) adds 1–5 seconds of network I/O latency. If this call is made synchronously on the FastAPI async request handler (`await` inside an `async def` route), it blocks the event loop for the duration of the network call, preventing other requests from being served. This is the classic "blocking async" bug in FastAPI/Python.

More subtly: if the NL parse call is submitted to the existing `ThreadPoolExecutor(max_workers=1)` along with the CP-SAT solve, the thread pool serializes LLM parsing + solving — the effective throughput per user drops to one parse+solve at a time, and a slow Claude response (rate-limiting, cold start) blocks the solve queue entirely.

**Why it happens:**
`asyncio` and `httpx`/`aiohttp` calls are non-blocking at the network level, but the `anthropic` Python SDK's sync client (`Anthropic()`) blocks the thread. Using the async client (`AsyncAnthropic()`) is non-blocking but requires the call to stay on the event loop — which is fine for I/O, but any CPU-bound code (like solver prep) cannot run alongside it.

**How to avoid:**
1. Use `AsyncAnthropic()` for the LLM parse call — this keeps the network wait non-blocking on the event loop.
2. Keep the LLM parse call **on the event loop** (it is I/O-bound), and submit only the CP-SAT solve to the `ThreadPoolExecutor` (it is CPU-bound). The LLM call completes asynchronously, then the validated overrides are passed to the solver thread.
3. Add a timeout to the LLM call (e.g., 30 seconds) so a stuck Claude response doesn't hold up the user indefinitely. Return a 504/timeout error that's distinct from a solve failure.
4. Track LLM call latency in the run record (add `llm_parse_ms` to the result JSON or run metadata) so cost/latency can be monitored.

**Warning signs:**
- All requests serialize even when only one user is active
- `asyncio` event loop lag increases during LLM calls
- A solve times out because the thread pool was blocked by a slow LLM response

**Phase to address:** Phase 3, API wiring for the NL-parse → re-solve flow.

**Design status:** `propose-change` — design.md notes the solve runs in a worker thread, but the LLM parse call's async strategy is not specified. This is a gap that affects the Phase 3 API integration plan.

---

### Pitfall 7: Insight Reports Misstating Metrics

**What goes wrong:**
The insight generator receives `SolveResult` metrics and produces a natural-language report. Without explicit grounding, the LLM may: (a) fabricate plausible-looking numbers ("outbound coverage improved by 12%" when it was actually 7%); (b) swap task names (call "Inbound" "Outbound"); (c) report last-run's numbers from training context rather than the injected metrics; (d) round numbers inconsistently.

Numerical hallucinations are particularly dangerous in a scheduling context because operations managers act on coverage reports. A wrong number reported confidently erodes trust in the entire system.

**Why it happens:**
LLMs have strong priors on "typical" coverage percentages and cost figures from training data. When the prompt structure is loose (e.g., "summarize these metrics"), the model may fill in from priors rather than the injected data. Even reasoning-trained LLMs sometimes bypass the tool-calling / data path and fabricate authoritative-sounding numbers.

**How to avoid:**
1. Inject all metric values as a structured JSON block in the prompt, not as prose descriptions. Example:
   ```
   METRICS (use ONLY these numbers, do not invent):
   {"outbound_coverage_pct": 73.2, "inbound_coverage_pct": 88.5, "total_unmet_hours": 14.2, "labor_cost": 42800.00, "solve_status": "OPTIMAL"}
   ```
2. Add post-generation verification: extract all numbers from the generated report (regex `\d+\.?\d*%?`) and assert each one appears verbatim in the input metrics JSON. Reject and retry if any number is fabricated.
3. Prompt explicitly: "Report only numbers from the METRICS block above. Do not calculate, estimate, or infer any other numbers."
4. Insights are already a separate post-run step (confirmed baseline) — if the verification fails, return a structured error rather than a potentially wrong report.

**Warning signs:**
- Generated insight mentions a percentage not present in `SolveResult.metrics`
- Coverage figure in the report differs from the figure in the API response by more than 0.1%
- Report uses a task name not in the scenario's task list

**Phase to address:** Phase 3, insight generator implementation.

**Design status:** `confirm-baseline` for failure isolation (separate step, LLM failure doesn't fail the schedule). `propose-change` for number grounding and post-verification — not in the design.

---

### Pitfall 8: Stub Provider That Doesn't Match Real Claude Tool-Use Wire Format

**What goes wrong:**
The stub `LLMProvider` returns hard-coded Python dicts that look like tool calls, but they don't match the exact structure Claude's API returns. Tests pass because the stub bypasses schema validation, but when wired to real Claude the response parsing fails — Claude returns `tool_use` content blocks with `id`, `name`, `input` fields, but the stub returns `{"tool": "...", "args": {...}}` (wrong field names). Alternatively, the stub doesn't test error paths: unknown ID rejection, out-of-bounds arg rejection, or multi-turn feedback loops.

**Why it happens:**
Developers write stubs to match what they _expect_ the parser to receive rather than what the API actually returns. The Claude API's tool-use wire format (`content[].type == "tool_use"`, with `id`, `name`, `input` keys) is specific and must be replicated exactly.

**How to avoid:**
1. Base the stub's return format on the actual `anthropic.types.ToolUseBlock` structure: `{"type": "tool_use", "id": "toolu_<uuid>", "name": "<tool_name>", "input": {...}}`.
2. Include at minimum these golden cases in the stub:
   - Happy path: single valid tool call with correct IDs and in-bounds args
   - Unknown member ID: returns a tool call with a non-existent `member_id` — verifies the rejection path
   - Unknown task ID: similar
   - Out-of-bounds arg: `scale_demand(factor=0.0)` — verifies arg validation
   - Multi-tool call (if the design allows multiple overrides in one NL request)
   - Ambiguous NL (no tool call returned, just text) — verifies graceful handling of "no action" responses
3. Test the stub against the real Claude response schema by running a single live integration test (tagged `@pytest.mark.integration`, excluded from CI) to verify schema parity.

**Warning signs:**
- Tests pass with stub but fail immediately when pointed at real Claude
- Stub returns dicts without the `type: "tool_use"` key
- Integration test (run manually) fails on response parsing, not on logic

**Phase to address:** Phase 3, test infrastructure setup.

**Design status:** `confirm-baseline` for the stub concept (PROJECT.md explicitly states "stubbed provider for tests"). `propose-change` for stub wire format fidelity and golden case coverage — not specified in the design.

---

### Pitfall 9: Claude Tool Schema Definition Mistakes

**What goes wrong:**
Errors in the `input_schema` passed to Claude's `tools` parameter cause silent or hard-to-debug failures:
- Missing `required` array → Claude treats all fields as optional and omits them, sending `{"input": {}}`. The parser receives an empty dict and either crashes or silently uses defaults.
- Wrong JSON Schema type strings (e.g., `"int"` instead of `"integer"`, `"float"` instead of `"number"`) → Claude may misinterpret the constraint or fail schema validation on the Anthropic API side.
- No `additionalProperties: false` → Claude may add extra fields that the validator doesn't reject, creating invisible cruft.
- Tool `description` too vague → Claude picks the wrong tool or passes semantically wrong values (e.g., using `exclude_worker_from_task` when the user meant `lock_worker_shift`).
- Tool names with spaces or special characters → Anthropic API rejects with a 400 error that looks like a network issue.

**Why it happens:**
JSON Schema is a large spec and the subset Claude uses (`type`, `properties`, `required`, `description`, `enum`) differs slightly from the full spec. Developers often write schemas by hand without validating them against actual Claude responses. The Anthropic SDK does not validate the `input_schema` client-side before sending.

**How to avoid:**
1. Each tool's `input_schema` must follow this structure exactly:
   ```json
   {
     "type": "object",
     "properties": {
       "member_id": {"type": "string", "description": "The member's contact_id from the scenario"},
       "task_id": {"type": "string", "description": "The task's task_id from the scenario"}
     },
     "required": ["member_id", "task_id"],
     "additionalProperties": false
   }
   ```
2. Use `"type": "integer"` (not `"int"`) for counts; `"type": "number"` (not `"float"`) for scale factors.
3. Add `"enum": [list_of_valid_values]` where the domain is finite (e.g., task family types).
4. Tool names must match `^[a-z_]+$` — use snake_case, no hyphens or spaces.
5. Write a unit test that validates each tool schema against `jsonschema.Draft7Validator` before any Claude call.
6. Add rich `description` fields to tool parameters — Claude uses these to map user intent to the correct parameter. "The scaling factor to apply to the task's demand volume (must be > 0; 1.0 = no change)" is far better than "factor".

**Warning signs:**
- Claude returns `{"input": {}}` for tool calls
- API returns 400 with a schema validation error message
- Claude consistently uses one tool (e.g., `scale_demand`) even when the user's intent clearly calls for another
- Tests fail with `KeyError` on a field that should always be present

**Phase to address:** Phase 3, LLM Provider protocol implementation.

**Design status:** `propose-change` — design.md names the five tools but does not specify their `input_schema` definitions. This is a gap that must be addressed before the LLM Provider implementation begins.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Single-round LLM call (no retry on ID mismatch) | Simpler flow | User gets opaque "no changes made" response; LLM can't self-correct | Never — multi-turn feedback is cheap and critical |
| Hard-code penalty weights as constants | Fast to ship | Miscalibrated weights discovered only after strange schedules in production | Only if covered by calibration tests at each weight value |
| Reuse existing `ThreadPoolExecutor(max_workers=1)` for LLM + solve | No new infrastructure | LLM latency serializes with solve queue; slow LLM response blocks solve for all users | Only if single-user demo with no concurrency requirement |
| Inject only summary metrics into insight prompt | Simpler prompt | LLM invents interpolated numbers not in the summary | Never — always inject all raw metric fields |
| Use sync `Anthropic()` client in async FastAPI route | Simpler code | Blocks event loop; serializes all NL requests; breaks under load | Never in production FastAPI |
| Skip `additionalProperties: false` in tool schemas | Shorter schema | Claude invents fields that silently fail downstream | Acceptable only in early spike; must be fixed before Phase 3 completion |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Claude tool-use | Sending tool schema without `required` array | Always include `required: [list_of_mandatory_fields]` |
| Claude tool-use | Using `tool_choice="auto"` and not handling "no tool call" response | Always handle the case where Claude returns plain text instead of a tool call |
| CP-SAT soft constraints | Adding override penalty to round-1 (unmet) objective | Add to round-2 (cost) objective only to preserve the coverage guarantee |
| CP-SAT override + re-solve | Creating a new `CpModel` from scratch each re-solve | Rebuild from the `SchedulingProblem` + overrides; the model is not stateful across runs |
| Insight generator | Passing `SolveResult` as a Python repr string | Serialize to JSON with all numeric fields explicit; include field names and units |
| Stub provider | Returning raw Python dicts instead of typed `ToolUseBlock` structures | Match Claude's exact wire format: `{"type": "tool_use", "id": "...", "name": "...", "input": {...}}` |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Synchronous LLM call on event loop | All API requests queue behind each other during NL processing | Use `AsyncAnthropic()` client; keep LLM call on event loop, solver in thread pool | At first concurrent user |
| LLM call in the solver thread pool | Slow Claude response blocks the solve queue | Separate LLM I/O from CPU solve: parse first (async), then enqueue solve | Whenever LLM rate-limits or cold-starts (~5% of calls) |
| Re-building full CP-SAT model on every override re-solve | Each NL tweak takes the full 20s baseline solve time | Expected and acceptable for Phase 3 — document it; future work could cache the base model | At >3 concurrent NL tweak requests |
| No timeout on LLM insight call | Insight generation hangs indefinitely if Claude is slow | Set `timeout=30` on the insight API call; return partial metrics if LLM times out | Any time Claude API is degraded |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Injecting scenario fixture names/content into the LLM system prompt without sanitization | Adversarial fixture content could redirect tool calls (indirect prompt injection) | Treat fixture content as untrusted data; inject only structured fields (IDs, numeric values), not raw text blocks from the fixture |
| Logging full NL user input and LLM responses | PII exposure if users include personal details in scheduling requests | Log only tool call names and arg keys (not values) in default mode; full logging opt-in with explicit flag |
| No rate limiting on the `/runs/{id}/nl-tweak` endpoint | Attacker can trigger unlimited Claude API calls, running up cost | Add per-scenario and per-IP rate limits on the NL parse endpoint |
| Storing raw LLM responses in the database | If the LLM is compromised or produces unexpected content, it's persisted | Store only the validated, structured override list (not raw LLM output) in the `overrides` JSON column |

---

## "Looks Done But Isn't" Checklist

- [ ] **NL constraint parser:** Stores overrides as JSON but doesn't verify the re-solve actually incorporated them — verify by comparing schedule coverage with and without the override applied.
- [ ] **ID validation:** Rejects unknown IDs in isolation but hasn't been tested with a multi-tool call where one ID is valid and one is not — verify the mixed case.
- [ ] **Stub provider:** Returns valid JSON in happy-path tests but hasn't been tested against the real Claude wire format — run one live integration test to verify parity.
- [ ] **Penalty calibration:** Overrides appear in the constraint model (builder adds them) but tests haven't verified that a satisfiable override is actually satisfied in the solution — add an assertion on the schedule.
- [ ] **Insight generator:** Produces text with all numbers present in the input, but hasn't been verified for the case where `SolveResult` metrics contain `NaN` (e.g., round-2 timeout degradation) — verify graceful handling.
- [ ] **Async LLM call:** Works in unit tests with a stub but hasn't been load-tested with a real Claude call and a concurrent solve — verify no event loop blocking under concurrency.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Prompt injection reaches solver with bad args | LOW | Add arg validation layer in NL parse service; all existing runs unaffected (overrides are per-run) |
| Hallucinated IDs silently ignored | LOW | Add explicit error response + retry; no data migration needed |
| Degenerate solve shipped to user | MEDIUM | Add post-solve sanity check; may need to re-run affected scenarios if users have saved degenerate overrides |
| Penalty miscalibration distorts cost round | MEDIUM | Recalibrate weight constants + re-run affected scenarios; no schema change needed |
| Insight report with wrong numbers | MEDIUM | Add post-generation verification; retrospectively re-generate insights for affected runs |
| Stub/real format mismatch caught in production | HIGH | Schema mismatch means all live NL calls fail; fix requires parser update + redeployment + re-testing |
| Tool schema missing `required` — Claude sends empty args | MEDIUM | Update schema definition + re-test; impacts all existing NL parse calls until fix is deployed |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Prompt injection / unsafe arg values | Phase 3 (LLM Provider + validation layer) | Test: `scale_demand(factor=0)` rejected with 400-level error |
| Hallucinated member/task IDs | Phase 3 (NL constraint parser) | Test: unknown `member_id` returns `is_error: true` tool result; valid retry succeeds |
| Trivially degenerate solves | Phase 3 (arg validation + post-solve check) | Test: override that zeros demand triggers a warning flag in the response |
| Soft constraint penalty miscalibration | Phase 3 (engine override integration) | Test: satisfiable override is satisfied in schedule; infeasible override doesn't change unmet hours |
| Nondeterminism in re-solves | Phase 3 (solver config decision) | Decision: document determinism guarantee; test: same overrides → same status (not necessarily same schedule if multi-worker) |
| LLM call blocking event loop | Phase 3 (API wiring) | Test: two concurrent NL requests complete without serialization delay |
| Insight misstating numbers | Phase 3 (insight generator) | Test: all numbers in report exist verbatim in input metrics JSON |
| Stub wire format mismatch | Phase 3 (test infrastructure) | Integration test (manual): real Claude call parses with same code path as stub |
| Tool schema mistakes | Phase 3 (LLM Provider implementation) | Test: each tool schema validates against `jsonschema.Draft7Validator`; Claude returns non-empty `input` |

---

## Sources

- OR-Tools CP-SAT soft constraints notebook: `google/or-tools` (official, Context7 / GitHub stable branch)
- OR-Tools shift scheduling example: `shift_scheduling_sat.ipynb` (official, Context7)
- OR-Tools CP-SAT nondeterminism: GitHub issues #3590, #3943 (or-tools-discuss group)
- OWASP LLM01:2025 Prompt Injection: https://genai.owasp.org/llmrisk/llm01-prompt-injection/
- Microsoft ISE DevBlog — LLM Prompt Injection with Tool Use: https://devblogs.microsoft.com/ise/llm-prompt-injection-considerations-for-tool-use/
- Tigera — Stub LLMs for AI Agent Testing: https://www.tigera.ai/blog/how-to-stub-llms-for-ai-agent-security-testing-and-governance/
- Anthropic SDK Python tool-use wire format: `/anthropics/anthropic-sdk-python` (official, Context7)
- Promptfoo — Hallucination prevention: https://www.promptfoo.dev/docs/guides/prevent-llm-hallucinations/
- JetRuby — LLM integration architecture decisions: https://jetruby.com/blog/llm-integration-product-architecture-decisions/
- ShiftMind design artifacts: `docs/design.md`, `.planning/PROJECT.md`, `.planning/codebase/CONCERNS.md`, `.planning/codebase/ARCHITECTURE.md`

---

*Pitfalls research for: LLM NL-to-constraint layer over CP-SAT optimizer (ShiftMind Phase 3)*
*Researched: 2026-06-28*
