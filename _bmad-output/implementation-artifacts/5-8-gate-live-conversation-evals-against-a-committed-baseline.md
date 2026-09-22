# Story 5.8: Gate Live-Conversation Evals Against a Committed Baseline
---
baseline_commit: ec98efb4d8396244e3471ab7b2b35ec23c577252
---

Status: ready-for-dev

Date: 2026-09-22
Origin: Minh's review of what this repository calls a "golden dataset" and a "regression test", and the four scoping decisions settled in that session.
Priority: Epic 5; precedes the next Gate B assessment. Not a release blocker on its own.

## Story

As the evaluation owner,
I want a committed baseline of the live-conversation suite's per-turn results plus a checker that fails when results drop below it,
so that a prompt, model, or code change that degrades real conversational behaviour is detected instead of merely remembered.

## Outcome

Re-running the live-conversation suite on the same configuration produces a machine-checkable verdict against a recorded known-good result. A turn that never failed and now always fails, a never-accept category, or an aggregate collapse each exit non-zero and name the offending turn.

**What exists today.** `evals/live_conversations/` answers *how good is it right now* (87/90 turns, recorded in `evidence/story-5.7/live-conversation-journeys.json`). `backend/evals/golden/**` answers *did the application's behaviour change* — deterministically, in the default suite. Nothing answers *is it worse than it was*, which is the regression question. Story 5.7 established the measurement; this story turns it into a gate.

## Facts this story depends on

Re-verify each at Task 1 rather than trusting this file. Every row was measured or read at creation (`ec98efb`, clean tree).

| Fact | Citable source / anchor | Consequence |
| --- | --- | --- |
| **No new paid live run is needed to seed the baseline.** `evidence/story-5.7/live-conversation-journeys.json` already carries `turn_pass_rates` for all 30 turns as `{executed, passed}` — **27 turns at 3/3, 3 turns at 2/3 (`B:5`, `B:8`, `C:3`), total 87/90** — plus `measured_configuration`, `measured_at_commit`, `inventory_digest`, `clean_scenarios: [A,B,C]`, `complete_repetitions: 3`, `blocking_reasons: []`. | `evidence/story-5.7/live-conversation-journeys.json` (`schema_version: "3"`) | The baseline is a transform of a committed file, not a measurement. The whole story — comparator, rules, tests — is buildable and provable offline, with zero spend. |
| **The 5.7 baseline is still current.** `git diff 437b63a..HEAD` is 16 files; the only code is `evals/live_conversations/evidence.py`, `scripts/evidence_binding.py` and two of their tests — evidence tooling, not the conversation path. | `git diff --name-only 437b63a HEAD` | The recorded numbers describe today's product. Do not discount them as stale or re-measure "to be safe". |
| **The baseline's `behavioral_digest` is computable today — no git archaeology.** `compose.override.yml`'s current normalised digest is `1aaef51617c502c98525637a6761276fe1833522d7bb2b07d9d706f1ea5b4e9f`, which is EXACTLY the `override_sha256` the Story 5.7 evidence recorded. The file has one commit (`960c2a3`) and has not moved since the measurement. | `evidence/story-5.7/…json` → `measured_configuration.override_sha256`; `backend/evals/live_conversations/compose.override.yml` | Compute the baseline's `behavioral_digest` from the working-tree file. Do NOT reach for `git show 437b63a:backend/evals/live_conversations/compose.override.yml` — re-verify the digest equality first, and only if it has BROKEN does the historical version become necessary. |
| **`regenerate_evidence.py` does not touch the Story 5.7 evidence.** Its `EVIDENCE_FILES` tuple registers stories 1.4 through 3.12 only. | `backend/scripts/regenerate_evidence.py:63-84` | A repo-wide rebinding pass cannot silently move the baseline's source file. The only thing that moves it is an explicit `python -m evals.live_conversations.evidence` regeneration — which is exactly when Decision 3 requires re-deriving the baseline. |
| **LOAD-BEARING TRAP, measured at creation.** `evidence/story-5.7/live-conversation-journeys.json` is **CRLF in the working tree** (47,776 bytes, sha `4ca6215c…`) but **LF in the committed blob** (46,764 bytes, sha `5a760cee…`), because `core.autocrlf=true` is set globally and the generator wrote the file locally after checkout. `.gitattributes` pins `evidence/**/*.json text eol=lf`, which governs checkout, not a locally generated file. Three other evidence files (`story-1.4`, `story-1.5`, `story-2.2`) are in the same state. | `.gitattributes`; `git show HEAD:evidence/story-5.7/live-conversation-journeys.json`; working-tree bytes | A raw `sha256(path.read_bytes())` gives one digest locally and a different one on the Linux CI runner. This is the Story 1.9/1.10/1.11 defect the `.gitattributes` header describes, reproduced in a new place. See Decision 2. |
| **Two normalising digest routines already exist** and both document this hazard: `_dataset_file_digest` (`backend/scripts/evidence_binding.py:629`, private, not in `__all__`) and `_file_digest` (`backend/evals/live_conversations/configuration.py:25`). `file_digest` (`evidence_binding.py:410`) deliberately does NOT normalise — it hashes raw bytes for generated artifacts and Gate A contract fixtures, where raw bytes are the right identity. | `backend/scripts/evidence_binding.py:410,629`; `backend/evals/live_conversations/configuration.py:25` | Reuse, do not re-derive. Picking `file_digest` by name-similarity is the exact wrong choice and its docstring says so. |
| **Evidence-tree membership is decided by LOCATION ALONE.** `_evidence_files()` is `EVIDENCE_ROOT.rglob("*.json")` with `EVIDENCE_ROOT = <repo>/evidence`. There is no flag, marker or schema field. | `backend/tests/test_evidence_convention.py:_evidence_files` | Writing the baseline under `backend/evals/baselines/` is what keeps it outside the NFR27 regime — that is Decision 1's entire mechanism, not a stylistic preference. |
| **The drift audit cannot see a stale dataset path.** `_referenced_paths` collects path strings only from VALUES under keys named `contract`, `checklist`, `path`, `source_path`. Dataset file paths live as dict KEYS under `version_bindings.dataset.files`, so `audit_evidence_drift` never walks them. | `backend/scripts/evidence_binding.py:_PATH_HINT_KEYS`, `_referenced_paths`, `audit_evidence_drift` | Nothing existing will notice the baseline drifting from its source. The `source_evidence_sha256` check added by this story is the only mechanism, so it must not be optional. |
| **`configuration_digest` over-triggers.** It covers agent model, judge model, `reasoning_effort`, and the sha256 of the WHOLE `compose.override.yml` — including its 24-line comment header carrying model-comparison history. Editing a comment invalidates it. | `backend/evals/live_conversations/configuration.py:30-50`; `backend/evals/live_conversations/compose.override.yml:1-24` | A gate that reddens when someone edits a chronology comment is not usable. See Decision 7. |
| **Per-token prices ARE behaviourally coupled**, through the budget, not through the model. `ConversationBudget.admit`/`charge`/`check_complete` accumulate `spend_usd` from those rates and raise `IncompleteConversationRun('aggregate_budget_exhausted')` / `'case_budget_exhausted'`. | `backend/evals/live_conversations/protocol.py:36-76` | Excluding price keys from the behavioural digest is sound only while the budget never truncates a run. See Decision 8. |
| **CORRECTION — the truncation signal is NOT `stopped_reason`/`spend_measured`.** Those are the Story 5.6 multi-turn report's fields (`evals/report.py`). This suite records truncation as a per-execution `incomplete_reason`, rolled up into `runs[].complete` / `executed_user_turns`, `complete_repetitions`, and the closed `blocking_reasons` vocabulary (`three_complete_repetitions_missing`, `unaccepted_turn_failure`, `clean_run_missing_for_scenario`, `false_claim_or_effect_failure`, `tool_operation_coverage_incomplete_or_stale`, `blocking_tool_implementation_gap`, `clean_version_binding_missing`). | `backend/evals/live_conversations/reporting.py:38-125`; `protocol.py:16,48,52,75` | Do not invent a `stopped_reason` field. Decision 8's refusal reuses this existing vocabulary. |
| **`turn_pass_rates` is NOT in a raw run report.** It is built by `reporting.py:119-127`, which `evidence.generate` calls with raw run reports (`live-matrix.json`) as input. `turn_pass_rates`, `blocking_reasons`, `complete_repetitions` and `clean_scenarios` exist together only in the document that builder returns. `generate` additionally refuses a dirty tree and requires every run to record the same code binding. | `backend/evals/live_conversations/reporting.py:119-127`; `evidence.py:242-268` | The comparator's "new run" side is the builder's document, not `live-matrix.json`. Pointing it at a raw run report yields a missing key, not a comparison. See Decision 11. |
| **The paid suite may NEVER run in `ci.yml`.** `docs/CI-SECRETS-CHECKLIST.md` has a "Secrets that must NOT be added" section naming `GEMINI_API_KEY`, `OPENROUTER_API_KEY` and `ANTHROPIC_API_KEY`: they "must not be configured as repository secrets or exposed to any job in this workflow" (NFR26, AD-16). `ci.yml`'s `backend` job actively asserts the `-m "not live"` exclusion is still in force, and the workflow is designed to run green on a fresh fork with zero secrets. | `docs/CI-SECRETS-CHECKLIST.md`; `.github/workflows/ci.yml` (`default-suite-excludes-live-tests` step); epics.md NFR26 (:125) | A live-conversation run cannot be produced inside GitHub Actions, so "wire the checker into CI" is only possible for the half that needs no credential. See Decision 6, which splits accordingly. Do not add a secret, a cron entry, or a workflow job for the paid half. |
| **Gate B has no aggregator.** No `gate_b_checks.py` exists and nothing generates `evidence/epic-5/release-gate-report.json`; `docs/WALKTHROUGH.md:88` states plainly "Gate B has not passed." The suite is paid, so it cannot run per-PR. | `docs/WALKTHROUGH.md:88`; repo-wide absence of `gate_b_checks.py`; `docs/TESTING.md` ("The suite is opt-in and paid: it is never selected by `pytest`") | "Fail red" means the `workflow_dispatch`/weekly-cron job exits non-zero. It does not mean building the Gate B aggregator — that stays out of scope (Decision 6). |
| **`PyYAML` is not installed.** `backend/pyproject.toml` has `[dependency-groups] dev`, and `Dockerfile:13` builds with `uv sync --no-dev`, so the dev group never ships. `opentelemetry-sdk` is the established TEST-ONLY precedent with its rationale written inline. | `backend/pyproject.toml`; `Dockerfile:13` | The "separate env for tests" mechanism already exists. Add to `dev`, never `[project].dependencies`; CI uses `--frozen`, so `uv.lock` must be regenerated in the same change. |
| **`backend/evals/README.md` has four pinned substrings.** `test_readme_documents_exact_contribution_shape_and_owners` asserts: `"expected tool, arguments, allow/refuse outcome, evidence IDs, and visible state"`, `"Stories 2.9, 3.10–3.12, and 4.5–4.6"`, `"Story 2.5 contributes scheduling_inspect"`, `"Story 2.7 contributes exactly four scheduling_compute cases"`, `"Story 2.9 contributes six scheduling_inspect cases"`, plus `"secrets"` and `"PII"`. None of them is line 3's "regression dataset" phrase. | `backend/tests/test_evaluation_harness.py:693-700` | AC6's wording correction is safe as long as those substrings survive; the test does not constrain the sentence being fixed. |
| **Demand/unit dimensional rules are normative and documented.** `outbound`/`inbound` demand is `volume`; `indirect` is `headcount`; staffed time comes from assignments and is family-agnostic. | `docs/DOMAIN-MODEL.md` (normative; do not re-derive) | This story READS recorded verdicts; it never recomputes a metric. The never-accept category "wrong value/unit/entity/version" is already enforced by the existing fact/effect layer that depends on this document. The comparator must not re-implement or second-guess that judgement. |
| Measured at creation (`ec98efb`, clean tree): backend default suite **2160 passed, 2 failed, 1 skipped, 10 deselected** in 194s. Recorded CI floors in `.github/workflows/ci.yml` (864 backend / 45 postgres / 400 vitest / 48 playwright) are from `faf22eb` (2026-08-16) and are far below the suite's current real size. | `.github/workflows/ci.yml` header; this session's measurement | This is a floor to diff against, not a target. Re-derive before attributing any red test to this story, and do not treat the CI comment block as the current baseline. |
| **The two failures are PRE-EXISTING and are not this story's.** `test_walkthrough_claims.py::test_reviewer_facing_relative_links_resolve` fails for `DEVELOPMENT.md` and `TESTING.md`: both link into `.planning/codebase/`, which HEAD itself (`ec98efb "chore: remove remaining GSD framework traces from the repo"`) deleted. The dangling links are `docs/TESTING.md:70` → `../.planning/codebase/TESTING.md` and `docs/DEVELOPMENT.md:195` → `../.planning/codebase/CONVENTIONS.md`. | `backend/tests/test_walkthrough_claims.py:98`; `git log --diff-filter=D -- .planning/codebase/TESTING.md` | `docs/TESTING.md` is a file AC6 edits anyway, so removing its dangling link belongs to that edit. `docs/DEVELOPMENT.md` is not in this story's scope and stays a recorded pre-existing failure — say so rather than silently fixing or silently inheriting it. |

## Acceptance criteria

1. **A committed baseline artifact.** `backend/evals/baselines/live-conversations.json` records, per turn, the `{executed, passed}` counts from the committed Story 5.7 evidence, plus `source_evidence_path`, `source_evidence_sha256`, `measured_at_commit`, the agent/judge models, `reasoning_effort`, and the behavioural configuration digest. It is derived by a committed script, never hand-typed. It does NOT live under `evidence/`.

2. **A comparison rule with three tiers plus a structural check**, applied to a fresh reporting-builder document (per Decision 11) against the baseline:
   - **Tier 1** — any turn recorded at `passed == executed` in the baseline that scores `passed == 0` in the new run FAILS, naming the turn. Turns not at full marks in the baseline are exempt from this tier.
   - **Tier 2** — any never-accept occurrence FAILS on a single instance: wrong value, unit, entity or version; missing or unauthorized effect; false success claim.
   - **Tier 3** — the aggregate FAILS when total passed turns fall below **83 of 90**.
   - **Structural** — `clean_scenarios` must still contain `A`, `B` and `C`.
   Each tier's verdict is reported separately; a pass on one never masks a failure on another.

3. **Configuration matching.** The comparison is refused, not silently performed, when the new run's behavioural configuration differs from the baseline's, or when either side's run was truncated. Refusal is a distinct outcome from failure and says which condition fired.

4. **Fail red, with a Gate-B-shaped result.** Every tier failure and every refusal exits non-zero from the operator-invoked drop check, which emits a per-check result using the same status vocabulary as the Gate A readiness report so a future Gate B assessment consumes it as one more row. Separately, the default pytest suite fails when the committed baseline no longer matches the committed Story 5.7 evidence. No repository secret, workflow job or cron entry is added.

5. **Provable offline.** Every assertion this story adds is exercised by the default `pytest` suite with no network access and no spend, using the committed Story 5.7 evidence as a fixture. Each new guard is demonstrated failing first: mutate a copy of the baseline or report, observe the specific named failure, restore, re-prove green.

6. **Documentation states what each suite is.** `backend/evals/README.md` no longer calls the scripted corpus a "regression dataset"; it says the corpus is a scripted conformance suite whose model output is authored, names what it therefore does not prove (model routing quality — that belongs to the live counterpart), and the four pinned substrings still pass. `docs/TESTING.md` matches, and documents the new checker's runnable command.

7. **Bounded scope.** No directory under `backend/evals/` is renamed. No Gate B aggregator is built and `evidence/epic-5/release-gate-report.json` is not created. `configuration_digest` and every committed evidence file keep their current values.

## Decisions and developer guardrails

Each decision states its mechanism and, in one sentence, what that mechanism does **not** cover.

1. **The baseline is ordinary tracked config, not evidence — enforced by where it is written.** Put it at `backend/evals/baselines/live-conversations.json`. Per the Facts table, membership in the NFR27 regime is decided by `evidence/**/*.json` location alone, so this placement is the enforcement, and a `source_evidence_sha256` check supplies the tamper-evidence the regime would otherwise have given. This does NOT cover giving the file NFR27 bindings, a `git_commit` of its own, or any framing that presents it as a second independent measurement — it is a projection of one measurement, and the tree must not imply otherwise.

2. **Hash through a normalising routine, reused rather than rewritten.** Promote `_dataset_file_digest` (`evidence_binding.py:629`) out of private scope and call it, per the Facts table's CRLF/LF row. This does NOT cover changing `file_digest` or any of its existing call sites, whose raw-byte identity is correct for generated artifacts and Gate A contract fixtures and whose retroactive rebinding of Story 1.4/1.5/1.9/1.10/1.11 evidence is explicitly forbidden by its docstring.

3. **The source digest covers the whole evidence file.** Simplest correct scope; a regeneration of the Story 5.7 evidence therefore requires re-deriving the baseline, and that re-derivation is part of regenerating that evidence. This does NOT cover a subtree or canonicalised digest over `turn_pass_rates` alone — that would need a canonicalisation contract, which is where this repository has already been bitten once.

4. **Tier 1 is the primary detector and applies only to full-marks turns.** A turn at `3/3` falling to `0/3` is ~0.07% likely by chance across the 27 qualifying turns; a turn at `2/3` reaching `0/3` is ~3.6% likely, which is too high for a hard block. This does NOT cover the three turns at `2/3` (`B:5`, `B:8`, `C:3`) — they are watched by Tier 3 only, and a rule that blocks on their movement would be a false-alarm generator, not a tighter gate.

5. **Tier 3's floor is 83 of 90, chosen against the measured distribution.** Poisson around the baseline's 3 failures puts a drop to ≤82 at ~1.2% per run, versus ~8.4% at a floor of 85. This does NOT cover making the aggregate the primary detector — it exists to catch broad degradation such as a model swap making everything slightly worse, and a single broken turn is Tier 1's job.

6. **Fail red splits across two homes, because the paid half may never enter `ci.yml`.** Per the Facts table's CI-credential row, the live suite cannot run in GitHub Actions at all. So: (a) the **drop check** is operator-invoked on the machine that just ran the paid suite, exits non-zero on any tier failure or refusal, and emits results in the Gate A readiness status vocabulary (`passed` / `failed` / `skipped` / `missing`, the last three non-proving); (b) a **free consistency check** — the committed baseline's `source_evidence_sha256` still matches the committed Story 5.7 evidence — runs in the DEFAULT pytest suite on every CI run, which is what makes baseline tampering or drift visible without a credential. This does NOT cover adding any workflow job, secret, or cron entry to `.github/workflows/ci.yml`: (b) needs no new job because the default suite already runs there, and (a) cannot have one.

7. **Add `behavioral_digest` beside `configuration_digest`; change neither the existing field nor any committed evidence.** Compute it from `compose.override.yml`'s parsed `environment` maps for BOTH the `api` and `worker` service blocks compared separately, excluding keys matching `*_USD_PER_MTOK`, serialised with `json.dumps(sort_keys=True)` exactly as `measured_configuration()`'s own `digest = hashlib.sha256(json.dumps(body, sort_keys=True)...)` line already does (`configuration.py`, near :49 before this story edits that function). Compare on `behavioral_digest`; keep recording `configuration_digest` so the audit trail still shows price and comment changes. This does NOT cover an allow-list of "behavioural" keys — the rule is an EXCLUSION of price keys, so any newly added key is included by default and fails closed.

8. **Refuse a truncated comparison using the vocabulary that already exists.** Per the Facts table's correction row, require `blocking_reasons == []`, `complete_repetitions >= 3`, and `runs[].complete` true for every counted execution on both sides; a budget-truncated run already fails these. This does NOT cover inventing a `stopped_reason` or `spend_measured` field on this suite's report — those belong to the Story 5.6 multi-turn report and naming them here would produce a check that silently never fires.

9. **`PyYAML` goes in the `dev` dependency group, following the `opentelemetry-sdk` precedent** including its inline TEST-ONLY rationale, with the regenerated `uv.lock` committed in the same change. This does NOT cover adding it to `[project].dependencies` or importing `yaml` anywhere outside `backend/evals/` — `Dockerfile:16` copies `backend/` wholesale, so eval code is present in the image even though its dependency is not, and an import from `api/` or `worker/` would fail at runtime.

10. **The documentation correction is a wording fix, not a rename.** Per AC6 and AC7. This does NOT cover moving `backend/evals/golden/` or `golden_multi_turn/`: 40+ files reference those paths, including three committed evidence files that hold them as dict keys under `version_bindings.dataset.files` and ~20 historical story artifacts that must not be rewritten, and renaming `golden_multi_turn/` would additionally force a paid re-measurement of Story 5.6's live evidence.

11. **Both sides of the comparison are reporting-builder documents.** Per the Facts table's `turn_pass_rates` row, the comparator takes the document `evals.live_conversations.reporting` returns — read from a committed `evidence/**` file for the baseline side, and built from fresh run reports through the existing `evidence.generate` path for the new-run side. This does NOT cover the comparator building that document itself from raw run reports: re-implementing the rollup would put a second, unchecked copy of the pass-counting rule next to the one that produced the baseline, which is how the two would drift.

## Implementation tasks

- [ ] Re-derive the Facts table at HEAD: confirm the Story 5.7 evidence's per-turn counts and digests, re-measure the backend/frontend suite baselines, and confirm the CRLF/LF divergence still holds on this machine. Record the numbers; do not trust this file's. (AC: 1 — per the Facts table's final row.)
- [ ] Add `behavioral_digest` to `measured_configuration`, and `PyYAML` to the `dev` group with a regenerated `uv.lock`. (AC: 3 — per Decisions 7 and 9.)
- [ ] Promote the normalising digest routine and derive `backend/evals/baselines/live-conversations.json` from the committed Story 5.7 evidence through a committed script. (AC: 1 — per Decisions 1, 2 and 3.)
- [ ] Implement the comparator: three tiers, the `clean_scenarios` structural check, the configuration and truncation refusals, and the Gate-A-shaped per-check result. (AC: 2, 3, 4 — per Decisions 4, 5, 6, 8 and 11.)
- [ ] Write the offline test suite using the committed evidence as a fixture, and demonstrate every new guard failing first before it passes. (AC: 5)
- [ ] Add the free consistency check to the default pytest suite, and publish the operator-invoked drop-check command. Add no workflow job, cron entry or secret. (AC: 4 — per Decision 6.)
- [ ] Correct `backend/evals/README.md` and `docs/TESTING.md`, and publish the checker's runnable command. Remove `docs/TESTING.md:70`'s dangling `.planning/codebase/` link in the same edit. (AC: 6 — per Decision 10; the pinned substrings in `test_evaluation_harness.py:693` must still pass, and the dangling link is per the Facts table's pre-existing-failures row.)
- [ ] Run the full default backend and frontend suites and confirm no regression against Task 1's re-measured floors. State the `DEVELOPMENT.md` link failure as pre-existing and out of scope rather than inheriting it silently. (AC: 5, 7 — per the Facts table's pre-existing-failures row.)

### Project Structure Notes

- `backend/evals/baselines/` does not exist. It is a new sibling of `golden/` and `golden_multi_turn/`, deliberately NOT inside either — both have strict loaders that reject unrecognised shapes, the same reasoning that put `live_conversations/` in its own directory (Story 5.7's Project Structure Notes, carried from Story 5.6's recorded deviation).
- Backend tests are `test_*.py` under `backend/tests/`, named for what they prove rather than for a story number, per `docs/TESTING.md`.
- The checker is a `backend/scripts/` module, matching `gate_a_readiness.py`'s placement, not an `evals/` module — it consumes reports rather than producing them.
- `backend/scripts/` names its evidence producers `generate_<what>_evidence.py` (`generate_sse_replay_evidence.py`, `generate_run_event_latency_evidence.py`, `generate_repair_journey_evidence.py`, `generate_state_semantics_evidence.py`). The baseline deriver must NOT take that name — it produces config, not evidence, and borrowing the evidence naming would assert exactly the membership Decision 1 spends its whole mechanism denying. Name it for what it does, e.g. `derive_live_conversation_baseline.py`.
- Promoting `_dataset_file_digest` is safe: `backend/tests/test_evidence_binding.py` pins neither `__all__` nor that symbol, so no existing test constrains the rename. Verified at creation — re-check before assuming.
- `backend/tests/compose_proof.py` is the established exception to `test_*.py` collection for opt-in stack-building proofs. Nothing in this story needs that shape: every new test is offline and belongs in default collection.
- No conflicts detected. The one structural gap — no Gate B aggregator to plug into — is recorded in the Facts table and deliberately left open by Decision 6.

## Boundaries and handoff

Reuse `backend/evals/live_conversations/` (`configuration.py`, `reporting.py`, `evidence.py`, `protocol.py`), `backend/scripts/evidence_binding.py`, and `backend/scripts/gate_a_readiness.py`'s result shape. Locate the actual files during implementation; this is an investigation map, not a diagnosis.

No live provider call, no spend, no new measurement, no directory rename, no Gate B aggregator, and no change to `configuration_digest` or any committed evidence file is authorized by this story. If the work appears to require a paid run, stop — the Facts table's first row says it does not, and a run appearing necessary means a decision has drifted.

Product/backlog handoff: this story precedes the next Gate B assessment and strengthens the epics' "Blocking regressions" Gate B row (`epics.md:1701`) by making a live-conversation regression detectable rather than only assertable. It does not satisfy that row, and it does not satisfy the `live_conversation_journeys` row (`epics.md:1696`), which Story 5.7 owns.

## Previous-story intelligence

From Story 5.7 (`5-7-prove-live-conversations-through-baseline-promotion.md`), the immediately preceding eval story:

- **Every new guard owes a mutation demonstration.** 5.7 carried 5.6's Task 4 rule forward: mutate already-green code, observe the specific failure, restore, re-prove green. AC5 states it for this story's guards; it is the reason a comparator whose tiers have never been seen to fire is not finished.
- **A check that compares something with itself cannot fail.** 5.7's review found authority assertions comparing an immutable attribute against a snapshot of the same runtime. The analogous trap here is a comparator that recomputes the baseline from the report it is checking; the baseline must be read from the committed file.
- **Redaction discipline survives failure paths.** `_safe_diagnostic_record` keeps names and counts only, never prompts, arguments or bodies. The comparator's failure messages name turns and counts — never transcript text.
- **A live pass is necessary but never sufficient.** 5.7's own record states it and this story inherits it: a green baseline check neither satisfies nor weakens the deterministic suite.
- **Corrective-story numbering carries no epic-status side effect.** Like 5.5, 5.6 and 5.7, this story does not flip `epic-5`, which is already `in-progress`; only its own key changes.

From the session that produced this story: three assertions made during scoping were wrong and were corrected by reading code — the truncation field names, the claim that a rename would redden CI, and the claim that an exclusion list would go stale. Each correction is recorded in the Facts table or a Decision. Treat this file's cited line numbers as claims to re-verify, not as facts.

## Verification commands

```bash
cd backend
uv run --frozen pytest -q                                   # default suite, no network, no spend
uv run --frozen pytest tests/test_evaluation_harness.py     # the four pinned README substrings
uv run --frozen pytest tests/test_evidence_convention.py    # evidence tree unaffected
uv run --frozen pytest -m postgres                          # requires local PostgreSQL 18
```

```bash
cd frontend
npm run test -- --run
```

The live-conversation suite itself is opt-in and paid and is NOT run by this story. Its command stays as documented in `docs/TESTING.md`.

## References

- [Source: `_bmad-output/planning-artifacts/epics.md` — Gate B table rows "Required live conversation journeys" (:1696) and "Blocking regressions" (:1701); NFR27 (:127), NFR28 (:129)]
- [Source: `evidence/story-5.7/live-conversation-journeys.json` — the baseline's source data]
- [Source: `_bmad-output/implementation-artifacts/5-7-prove-live-conversations-through-baseline-promotion.md` — previous-story intelligence; Decision 4's Gate B scoping precedent]
- [Source: `docs/EVIDENCE-CONVENTION.md` — why the baseline is deliberately outside `evidence/`]
- [Source: `docs/TESTING.md` — the live suite's command, measured results, and the never-accept rule under the "What blocks" heading ("A wrong value, unit, entity or version, a missing or unauthorized effect, or a false success claim blocks regardless of pass rates")]
- [Source: `docs/WALKTHROUGH.md:88` — "Gate B has not passed"; no aggregator exists]
- [Source: `docs/DOMAIN-MODEL.md` — normative demand family/unit rules the existing fact/effect layer depends on]
- [Source: `backend/scripts/evidence_binding.py` — `file_digest` vs `_dataset_file_digest`; `audit_evidence_drift`; `_referenced_paths`]
- [Source: `backend/scripts/gate_a_readiness.py`, `gate_a_checks.py` — the per-check result shape and status vocabulary]
- [Source: `backend/evals/live_conversations/configuration.py`, `protocol.py`, `reporting.py`, `evidence.py`, `compose.override.yml`]
- [Source: `backend/tests/test_evidence_convention.py` — `_evidence_files()`, the location-only membership rule]
- [Source: `backend/tests/test_evaluation_harness.py:693` — the pinned README substrings]
- [Source: `backend/pyproject.toml`; `Dockerfile:13,16`; `.gitattributes`]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
