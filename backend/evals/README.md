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
  UUID. It is non-empty for Story 2.7 grounding cases.
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
