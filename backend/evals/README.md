# ShiftMind golden evaluation dataset

This directory is the shared, version-controlled regression dataset introduced
by Story 2.2. Cases live as one JSON file per case under
`golden/<capability>/`. The harness loads every `*.json` recursively; a malformed
file fails normal CI rather than being skipped.

## Case shape

Each case records the Story 2.9 fixture shape verbatim: **expected tool, arguments, allow/refuse outcome, evidence IDs, and visible state**. The complete
schema is the frozen `GoldenCase` dataclass in `cases.py`:

- `case_id` is stable; `case_version` versions this dataset case and is distinct
  from any persisted product-contract `schema_version`.
- `capability` is a free-text ownership tag. It is not
  `CapabilityManifestV1` and grants no authority.
- `risk_class` is exactly one of `inspect`, `draft`, `compute`,
  `consequential`, or `prohibited`. These remain dataset tags that grant no
  authority and import their vocabulary from Story 2.5's application registry.
- `prompt` plus `scripted_turns` drives the deterministic model double.
  A scripted turn contains either `tool_name` + JSON `arguments` +
  `tool_call_id`, or `response_text`—never both.
- `expected_outcome` is `allow`, `refuse`, or `clarify`;
  `expected_tool_calls` lists exact tool names and argument objects.
- `expected_evidence_refs` uses the stable
  `scenario_version|group|record|field:start-end` form and carries no per-run
  UUID. A supported grounding case names the locators the calculator must
  emit; a failure case names none, and asserting that emptiness is what
  proves a failed claim never retargets another record or version (AR11).
- `expected_visible_state` and `expected_visible_text` describe the owned
  `AgentRunOutcomeV1` surface. `scenario_fixtures` lists any governed scenario
  identities as `fixture_id:version`; demonstration cases use an empty array.

## Contributing a reviewed failure

1. Review the failure and remove secrets, credentials, personal data, and PII
   from prompts, tool arguments, visible text, and evidence references. NFR4
   applies to evaluation fixtures just as it does to logs and traces.
2. Add a new case file under `golden/<capability>/`; do not edit an unrelated
   case to hide a regression. Give the case its own stable ID and case-level
   version.
3. Run `uv run --frozen pytest tests/test_evaluation_harness.py` from
   `backend/`. The schema guard loads every file, the generated double runs
   through the real `AgentRuntime` adapter, and tool routing is evaluated on
   owned output types.
4. Have the case and sanitization reviewed with the owning story.

Stories 2.9, 3.10–3.12, and 4.5–4.6 contribute their own real cases to this same
directory. Story 2.2 contributes only two `demonstration` cases to prove the
schema and pipeline. They are not padding toward NFR28's 50-case Gate B floor;
that aggregate must be re-verified later against real story contributions.

Story 2.5 contributes scheduling_inspect cases for demand, assignments, workers,
constraints, and locks. They exercise tool routing and argument shape against a
deterministic projection double; the `scenario_fixtures` tag records which
governed fixture each question is *about*, not a fixture the harness loads.

Story 2.7 contributes exactly four scheduling_compute cases: supported,
version-mismatch, missing-evidence, and argument-mismatch. ToolRoutingEvaluator
continues to judge routing while the second GroundingEvaluator independently
judges exact evidence IDs and the authored grounding oracle; these four cases
meet, but do not pad beyond, NFR28's per-capability floor.

These four run against a real projection (`evals/fixture_projection.py`), so
the calculator genuinely computes and the gate verifies locators the
calculator itself produced -- captured on the trusted path through
`deps.tool_result_sink`, exactly as the request route does. Nothing in the
harness constructs a capability result. That matters because the earlier
driver fabricated one and branched its contents on the case's own expected
outcome, which made all four cases pass by construction; a row bound that
fails closed on real data and volume demand multiplied into minutes both
survived review because of it. Three of the four outcomes arise from case
data alone; only `version_mismatch` needs an environmental knob, and it
rotates the PIN the gate checks against rather than editing the result --
the same condition as a scenario re-versioned mid-turn.

Story 2.9 contributes six scheduling_inspect cases: one ambiguity, one bounded
unsupported-request refusal, one provider failure through the real adapter,
and three prompt-injection attempts. The normal inspect cases above are reused
for AC4's normal fixture kind, and Story 2.7's `missing-evidence` case is reused
for the unsupported-number kind.

Story 3.6 contributes five scheduling_optimize cases covering a valid explicit
request, replay-shaped input, a non-default reviewed resource version, the
maximum idempotency-key length, and — added at code review — a refusal for a
request that identifies no proposal. The first four are all `allow`, which left
the module's declared `invalid_query` code with unit coverage but no agent-facing
eval; the refusal case is scoped to this module's own `compute` risk class, so
it is not one of the consequential/prohibited cases Task 3 reserved for Epic 4.
The model-facing view contains only
application-authored identifiers and a version number, so it introduces no new
untrusted content source and owes no additional NFR5 injection case.

**NFR5 coverage is organised by untrusted SOURCE, not by transport.** This MVP
introduces exactly two sources of untrusted content: the planner's own chat
text, and scenario/fixture data. Every installed capability's
`model_facing_view` renders either scenario rows or application-authored copy,
so "rendered tool output" is the *transport* by which scenario data reaches the
model rather than a third source — an earlier revision of this paragraph
claimed three channels and was wrong. The three cases therefore cover:

- **chat text** — `injection-chat-text`, where the prompt itself instructs the
  model to call an ungranted capability;
- **scenario data → capability grant** — `injection-fixture-field`, where a
  worker row's `name` carries the instruction;
- **scenario data → budget and approval** — `injection-tool-output`, where a
  different row attempts to widen the budget and set approval.

The last two share a source deliberately: they attack *different* AC2 nouns
(capabilities versus budget/approval), which is what earns each its place.

`NOT COVERED:` a capability whose model-facing output carries text from any
other source — a live provider, an external integration, or prose the
capability generates itself. No such capability exists in this milestone.
`test_every_capability_meets_the_nfr28_four_case_floor` fails on an
unclassified capability and asks for its untrusted source, so a new one cannot
be added without answering this.

Every injection script attempts the forbidden call — compliance is scripted and
refusal is asserted, never the reverse. The routing evaluator counts the
attempt (it appears in `expected_tool_calls`), and the policy evaluator proves
it produced no application tool result. The authority assertions compare
against expectations recomputed from `installed_modules()` and the configured
budget, not against a snapshot of the runtime under test — a snapshot compares
an immutable attribute with itself and cannot fail.

**NFR28 note.** Four of these cases carry `risk_class: "prohibited"`, which is a
*dataset tag describing the case*, not a claim about `scheduling_inspect`'s
manifest (that is `inspect`). The tag puts them under NFR28's 100% routing rule,
where adversarial cases belong. It also counts them in
`consequential_prohibited_case_count`, so that number is **not** evidence toward
NFR28's ≥10 consequential/prohibited floor by capability risk: no consequential
capability exists yet. Gate B re-verifies the floor once Stories 3.10–3.12 and
4.5–4.6 have contributed. These deterministic cases prove the application
boundary, not live-model instruction-following quality.
