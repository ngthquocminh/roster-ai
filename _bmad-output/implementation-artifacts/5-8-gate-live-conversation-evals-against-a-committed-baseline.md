# Story 5.8: Gate Live-Conversation Evals Against a Committed Baseline
---
baseline_commit: ec98efb4d8396244e3471ab7b2b35ec23c577252
---

Status: done

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
| ~~**`PyYAML` is not installed.**~~ **CORRECTED AT REVIEW (2026-09-22): this claim was false.** `uv tree --no-dev --frozen` shows `pyyaml` already resolved as a transitive dependency of `uvicorn[standard]`'s `standard` extra, so it was already present in the production (`--no-dev`) image before this story. `backend/pyproject.toml` has `[dependency-groups] dev`, and `Dockerfile:13` builds with `uv sync --no-dev`, but that only means the explicit `dev`-group entry doesn't ship — an unrelated package was already pulling `pyyaml` in regardless. `opentelemetry-sdk` is the established TEST-ONLY precedent with its rationale written inline. | `backend/pyproject.toml`; `Dockerfile:13`; `uv tree --no-dev --frozen` (re-verified at review) | The "separate env for tests" mechanism is still the right pattern, but not because `yaml` would otherwise be absent — it's because production code should never depend on an unrelated package's transitive pull-in, which is fragile if that dependency's extras ever change. Add to `dev`, never `[project].dependencies`; CI uses `--frozen`, so `uv.lock` must be regenerated in the same change. |
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

9. **`PyYAML` goes in the `dev` dependency group, following the `opentelemetry-sdk` precedent** including its inline TEST-ONLY rationale, with the regenerated `uv.lock` committed in the same change. This does NOT cover adding it to `[project].dependencies` or importing `yaml` anywhere outside `backend/evals/`. **CORRECTED AT REVIEW (2026-09-22):** the original rationale here — "`Dockerfile:16` copies `backend/` wholesale, so eval code is present in the image even though its dependency is not, and an import from `api/` or `worker/` would fail at runtime" — was wrong: `pyyaml` already arrives transitively via `uvicorn[standard]`, so it was already present at runtime and such an import would already have succeeded. The decision's OUTCOME is unchanged and still correct: `api`/`worker` code must not import `yaml` directly, not because it would fail today, but because relying on an unrelated package's transitive dependency is fragile — if `uvicorn[standard]`'s extras ever change, that reliance breaks silently. See the corrected Facts table row.

10. **The documentation correction is a wording fix, not a rename.** Per AC6 and AC7. This does NOT cover moving `backend/evals/golden/` or `golden_multi_turn/`: 40+ files reference those paths, including three committed evidence files that hold them as dict keys under `version_bindings.dataset.files` and ~20 historical story artifacts that must not be rewritten, and renaming `golden_multi_turn/` would additionally force a paid re-measurement of Story 5.6's live evidence.

11. **Both sides of the comparison are reporting-builder documents.** Per the Facts table's `turn_pass_rates` row, the comparator takes the document `evals.live_conversations.reporting` returns — read from a committed `evidence/**` file for the baseline side, and built from fresh run reports through the existing `evidence.generate` path for the new-run side. This does NOT cover the comparator building that document itself from raw run reports: re-implementing the rollup would put a second, unchecked copy of the pass-counting rule next to the one that produced the baseline, which is how the two would drift.

## Implementation tasks

- [x] Re-derive the Facts table at HEAD: confirm the Story 5.7 evidence's per-turn counts and digests, re-measure the backend/frontend suite baselines, and confirm the CRLF/LF divergence still holds on this machine. Record the numbers; do not trust this file's. (AC: 1 — per the Facts table's final row.)
- [x] Add `behavioral_digest` to `measured_configuration`, and `PyYAML` to the `dev` group with a regenerated `uv.lock`. (AC: 3 — per Decisions 7 and 9.)
- [x] Promote the normalising digest routine and derive `backend/evals/baselines/live-conversations.json` from the committed Story 5.7 evidence through a committed script. (AC: 1 — per Decisions 1, 2 and 3.)
- [x] Implement the comparator: three tiers, the `clean_scenarios` structural check, the configuration and truncation refusals, and the Gate-A-shaped per-check result. (AC: 2, 3, 4 — per Decisions 4, 5, 6, 8 and 11.)
- [x] Write the offline test suite using the committed evidence as a fixture, and demonstrate every new guard failing first before it passes. (AC: 5)
- [x] Add the free consistency check to the default pytest suite, and publish the operator-invoked drop-check command. Add no workflow job, cron entry or secret. (AC: 4 — per Decision 6.)
- [x] Correct `backend/evals/README.md` and `docs/TESTING.md`, and publish the checker's runnable command. Remove `docs/TESTING.md:70`'s dangling `.planning/codebase/` link in the same edit. (AC: 6 — per Decision 10; the pinned substrings in `test_evaluation_harness.py:693` must still pass, and the dangling link is per the Facts table's pre-existing-failures row.)
- [x] Run the full default backend and frontend suites and confirm no regression against Task 1's re-measured floors. State the `DEVELOPMENT.md` link failure as pre-existing and out of scope rather than inheriting it silently. (AC: 5, 7 — per the Facts table's pre-existing-failures row.)

### Review Findings

Reviewed 2026-09-22 against `d1905fd` (`ec98efb..HEAD`, 13 files, 1618+/13-). Three parallel layers (Blind Hunter, Edge Case Hunter, Acceptance Auditor) plus an independent mutation-table spot-check (re-mutated `tier_1`'s qualifying-turn filter myself, confirmed it reddens `test_tier_1_exempts_the_three_turns_the_baseline_never_scored_full` for the stated reason, reverted — table's mechanism holds for at least this row). All claims below were independently re-verified against the working tree, not taken from subagent prose.

- [x] [Review][Patch] **(resolved: accept the gap, document it)** `behavioral_digest` cannot see the real value behind a docker-compose `${VAR}` placeholder, so it is blind to `DEMONSTRATION_ENABLED` — `yaml.safe_load` in `behavioral_environment()` (`backend/evals/live_conversations/configuration.py:45`) parses `compose.override.yml`'s literal `${DEMONSTRATION_ENABLED:-false}` text, never the resolved runtime value; `DEMONSTRATION_ENABLED` is a real `settings.py:447` toggle the suite's own `stack.py:33` varies per invocation, and unlike `reasoning_effort` (also `${...}`-substituted but separately captured as its own explicit field) it has no other capture point. Two runs with different actual `DEMONSTRATION_ENABLED` values get an identical `behavioral_digest` and AC3's configuration-refusal silently treats them as matching — contradicts Decision 7's "fails closed" claim for this key. Minh's call: doesn't affect these conversation paths in practice — add a code comment documenting the gap as deliberate scope, no functional fix. **Applied:** docstring note added to `behavioral_environment()`. [backend/evals/live_conversations/configuration.py:45]
- [x] [Review][Patch] **(resolved: validate at derive time)** Decision 8's "on both sides" truncation refusal is structurally asymmetric — `truncation_refusal()` (`backend/scripts/live_conversation_drop_check.py:153`) checks `blocking_reasons`/`complete_repetitions`/`runs[].complete` for the fresh report but only `complete_repetitions` for the baseline, because `derive_baseline()` (`backend/scripts/derive_live_conversation_baseline.py:87`) never carries the other two fields into the baseline doc AND never validates them (or even `complete_repetitions`) against the source evidence at derive time. Minh's call: make `derive_live_conversation_baseline.py` refuse (raise, like its existing digest-mismatch check) if the source evidence's `blocking_reasons` isn't empty or any run isn't complete. **Applied:** `_ensure_source_is_clean()` added, called first in `derive_baseline()`; 3 new tests, each demonstrated failing first (see mutation table). [backend/scripts/derive_live_conversation_baseline.py:87]
- [x] [Review][Patch] **(resolved: correct the story record)** The Facts table's "`PyYAML` is not installed" claim (`Task 1`, "re-verified at HEAD") — the entire stated basis for Decision 9's TEST-ONLY/lazy-import guardrail — is false. `uv tree --no-dev --frozen` shows `pyyaml v6.0.3` already resolved as a transitive dependency of `uvicorn[standard]` (verified directly), so `api`/`worker` could already `import yaml` successfully before this diff. Outcome is harmless (adding pyyaml explicitly to `dev`, lazy-importing only in `backend/evals/` is still correct practice), but a "confirmed" row in a load-bearing Facts table was wrong, and `measured_configuration()` — which now unconditionally calls into the yaml path — sits on the live paid-suite's run-report path, not just tests, which cuts against the "TEST-ONLY" framing too. Minh's call: amend the Facts table row and soften Decision 9's rationale in this story file now. **Applied:** Facts table row and Decision 9 both corrected in place, struck through and annotated rather than silently rewritten. [_bmad-output/implementation-artifacts/5-8-gate-live-conversation-evals-against-a-committed-baseline.md — Facts table row 44, Decision 9]
- [x] [Review][Patch] No check confirms all 30 baseline turns are present in a new report — `tier_1`'s `missing` list (`backend/scripts/live_conversation_drop_check.py:184` `qualifying`) only watches the 27 full-marks turns; if one of the 3 tier-1-exempt partial turns (`B:5`/`B:8`/`C:3`) vanishes entirely from a report while the aggregate stays ≥83, neither `tier_1`, `tier_3`, nor `structural_check` names it. **Applied:** `tier_1`'s presence check now covers all baseline turns (score-collapse check stays scoped to full-marks-qualifying turns, per Decision 4); demonstrated failing first. [backend/scripts/live_conversation_drop_check.py:184]
- [x] [Review][Patch] `baseline_matches_source()` (`backend/scripts/live_conversation_drop_check.py:326`) defaults `source` to the hardcoded `SOURCE_EVIDENCE` constant, and `main()`'s call site (`:366`) never passes the loaded baseline's own `source_evidence_path` — so pointing `--baseline` at any file whose declared source differs from the hardcoded default silently checks consistency against the wrong file (and the pass message misreports which file it checked). Not reachable today (the one baseline's source equals the constant) but a live trap for the next baseline. **Applied:** `main()` now resolves and passes the loaded baseline's own `source_evidence_path`; demonstrated failing first at both the function and CLI level. [backend/scripts/live_conversation_drop_check.py:326,366]
- [x] [Review][Patch] Three tests proving real, distinct AC-level behavior have no row in the Dev Agent Record's mutation table, which AC5 presents as the "demonstrated failing first" evidence for every guard: `test_a_pass_on_one_tier_never_masks_a_failure_on_another` (AC2's non-masking clause), `test_refusal_is_a_distinct_outcome_from_failure` (AC3's refusal/failure distinction), `test_the_drop_check_exits_non_zero_on_a_refusal` (AC4's refusal exit-code clause). All three pass and assert real composition-level behavior not covered by any atomic per-tier test. **Applied:** all three mutated and confirmed reddening at review; rows added to the mutation table below. [backend/tests/test_live_conversation_drop_check.py:253,334,399]
- [x] [Review][Patch] `backend/pyproject.toml:54`'s dev-group comment states the yaml-import boundary as "outside `backend/evals/` and `backend/scripts/`" — wider than Decision 9's literal text, which authorizes only `backend/evals/`. No live violation today (the one call site in `backend/scripts/` goes through `configuration.behavioral_digest()`, never imports yaml directly), but the comment licenses more than Decision 9 does. **Applied:** comment narrowed to `backend/evals/` only, and corrected per the PyYAML finding above. [backend/pyproject.toml:54]
- [x] [Review][Patch] The published drop-check command (`docs/TESTING.md:34-37`, matching the module's own `Usage::` docstring) exits 1 with `outcome: "refused"` when run exactly as written against the real Story 5.7 evidence (verified by running it) — that frozen file predates `behavioral_digest` and can never gain one. AC6 asks the doc to publish a runnable command; the one published always refuses with no caveat telling a first-time reader that's expected. **Applied:** caveat added after the command block in `docs/TESTING.md`. [docs/TESTING.md:34]
- [x] [Review][Patch] A `--report` pointed at the wrong document shape (e.g. the raw `live-matrix.json` the docstring explicitly warns against) produces the same generic "records no behavioral_digest" message as any other missing-field case, rather than detecting and naming the shape mismatch directly. **Applied:** new `document_shape_refusal()` check names the shape mismatch directly; demonstrated failing first. [backend/scripts/live_conversation_drop_check.py:94]
- [x] [Review][Patch] `AGGREGATE_FLOOR = 83` (`backend/scripts/live_conversation_drop_check.py:54`) is a bare constant decoupled from `backend/evals/baselines/live-conversations.json`'s own totals; Decision 5's Poisson justification is tied to the current 87/90 baseline and nothing flags staleness if a future re-derivation changes the totals. **Applied:** staleness-warning comment added next to the constant. [backend/scripts/live_conversation_drop_check.py:54]

**Review mutation table** (additional guards demonstrated failing first, same convention as the Dev Agent Record's original table):

| Mutation applied | Guard that should redden | Before | After |
| --- | --- | --- | --- |
| `tier_1`'s `qualifying`-only filter (spot-check of the ORIGINAL table, not a new guard) | `test_tier_1_exempts_the_three_turns_the_baseline_never_scored_full` | 1 passed | 1 failed |
| `compare()`'s tier composition short-circuits after the first failure | `test_a_pass_on_one_tier_never_masks_a_failure_on_another` | 1 passed | 1 failed (KeyError) |
| `_refused()` returns `outcome="fail"` instead of `"refused"` | `test_refusal_is_a_distinct_outcome_from_failure` | 1 passed | 1 failed |
| `main()`'s final `return 0 if result["passed"] else 1` → `return 0` | `test_the_drop_check_exits_non_zero_on_a_refusal` + `test_the_drop_check_exits_non_zero_on_a_tier_failure` | 2 passed | 2 failed |
| `tier_1`'s `missing` computation reverted to `qualifying`-only | `test_tier_1_fails_when_an_exempt_partial_turn_vanishes_entirely` | 1 passed | 1 failed |
| `main()`'s consistency check reverted to `baseline_matches_source(baseline)` (no explicit source) | `test_the_drop_check_uses_the_loaded_baselines_own_source_path` | 1 passed | 1 failed |
| `document_shape_refusal(report)` call removed from `compare()`'s refusals tuple | `test_the_wrong_shaped_report_is_refused_by_name_not_misdiagnosed` | 1 passed | 1 failed |
| `_ensure_source_is_clean()` call removed from `derive_baseline()` | `test_a_baseline_cannot_be_derived_from_evidence_with_blocking_reasons`, `..._an_incomplete_run`, `..._too_few_complete_repetitions` | 3 passed | 3 failed |

**Verification after applying all patches:** `backend/tests/test_live_conversation_drop_check.py` 42 passed (34 original + 8 new). Full backend default suite: 2202 passed, 1 pre-existing failure (`DEVELOPMENT.md` dangling link, unchanged and out of scope), 2 skipped (dirty tree; returns to 1 on commit), 10 deselected — no regressions.

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

claude-opus-5 (Claude Code, bmad-dev-story)

### Debug Log References

**Task 1 — Facts re-derived at HEAD (`ec98efb`), not trusted from this file.**

| Fact | Re-measured value | Verdict |
| --- | --- | --- |
| Story 5.7 per-turn counts | 30 turns, 87/90; partials exactly `B:5`, `B:8`, `C:3` at 2/3 | confirmed |
| `measured_at_commit` | `db0a5dd0e5ace0929b8115299f57b10fb73c6c90`; `clean_scenarios [A,B,C]`, `complete_repetitions 3`, `blocking_reasons []`, `schema_version "3"` | confirmed |
| CRLF/LF divergence | working tree 47,776 B sha `4ca6215c…`; LF-normalised 46,764 B sha `5a760cee…` (= committed blob) | confirmed, still live on this machine |
| `compose.override.yml` digest equality | `_file_digest` → `1aaef516…` == the recorded `override_sha256` | confirmed; the baseline's `behavioral_digest` is computed from the working tree, no git archaeology |
| `_dataset_file_digest` call sites | 3, all inside `evidence_binding.py`; no test pins `__all__` or the symbol | confirmed, promotion safe |
| Backend default suite floor | 2160 passed, 2 failed, 1 skipped, 10 deselected (193s) | confirmed as the diff floor |
| Frontend suite floor | 85 files, 648 tests passed | measured |

Derived `behavioral_digest` for the baseline configuration: `c065dd87f5aa8ef0311dfea7fdb1dc7a9525e6389231b7c0f63c01dedbc73bec`.
Baseline `source_evidence_sha256`: `5a760cee43b6f95b5f22c68953a83a30265de9aae32d3a02d1c910a022f35609` (LF-normalised; equals the committed blob).

**Mutation table (AC5).** Every row mutated FINISHED product code, observed the named guard fail, then restored; the tree was left clean. No red came from an unresolved import or an unwritten module.

| Mutation applied to real code | Guard that should redden | Before | After |
| --- | --- | --- | --- |
| `tier_1` qualifier drops `passed == executed` | `test_tier_1_exempts_the_three_turns_the_baseline_never_scored_full` | 1 passed | 1 failed |
| `tier_1` collapse test `== 0` → `< 0` | `test_tier_1_names_a_collapsed_full_marks_turn` | 1 passed | 1 failed |
| `tier_1` missing-turn detection → `[]` | `test_tier_1_fails_when_a_watched_turn_is_missing_from_the_run` | 1 passed | 1 failed |
| `tier_2` reads `[]` instead of `false_claims` | `test_tier_2_fails_on_a_single_never_accept_occurrence` | 1 passed | 1 failed |
| `tier_2` detail renders the whole claim dict | `test_tier_2_failure_names_turns_and_categories_only` | 1 passed | 1 failed |
| `AGGREGATE_FLOOR` 83 → 0 | `test_tier_3_fails_one_turn_below_the_floor` | 1 passed | 1 failed |
| `AGGREGATE_FLOOR` 83 → 84 | `test_tier_3_passes_exactly_at_the_floor` | 1 passed | 1 failed |
| `structural_check` missing set → `[]` | `test_structural_check_fails_when_a_scenario_lost_its_clean_run` | 1 passed | 1 failed |
| `configuration_refusal` digest-mismatch branch disabled | `test_a_changed_behavioural_configuration_is_refused_not_compared` | 1 passed | 1 failed |
| `configuration_refusal` absent-digest branch disabled | `test_a_report_without_a_behavioural_digest_is_refused` | 1 passed | 1 failed |
| `_truncation_reasons` ignores `blocking_reasons` | `test_a_truncated_run_is_refused_…` | 3 passed | 1 failed, 2 passed |
| `_truncation_reasons` ignores `complete_repetitions` | `test_a_truncated_run_is_refused_…` | 3 passed | 1 failed, 2 passed |
| `_truncation_reasons` ignores `runs[].complete` | `test_a_truncated_run_is_refused_…` | 3 passed | 1 failed, 2 passed |
| `compare` emits real tier verdicts under a refusal | `test_a_changed_behavioural_configuration_is_refused_not_compared` | 1 passed | 1 failed |
| `baseline_matches_source` digest branch disabled | `test_consistency_check_names_the_drift_when_the_source_moves` | 1 passed | 1 failed |
| `baseline_matches_source` missing-file branch disabled | `test_consistency_check_fails_when_the_source_is_absent` | 1 passed | 1 failed |
| `main` always returns 0 | `test_the_drop_check_exits_non_zero_on_a_tier_failure` | 1 passed | 1 failed |
| `NON_PROVING` drops `"skipped"` | `test_every_check_uses_the_gate_a_status_vocabulary` | 1 passed | 1 failed |
| `main` stops folding consistency into `passed` | `test_a_drifted_baseline_makes_the_drop_check_exit_non_zero` | 1 passed | 1 failed |
| `behavioral_environment` keeps the price keys | `test_behavioral_digest_is_stable_across_a_price_or_comment_edit` | 1 passed | 1 failed |
| `behavioral_environment` becomes an allow-list | `test_a_newly_added_environment_key_is_included_by_default` | 1 passed | 1 failed |
| `behavioral_environment` keeps only the `api` block | `test_behavioral_digest_excludes_only_the_price_keys` | 1 passed | 1 failed |
| deriver hashes raw bytes instead of LF-normalised | `test_committed_baseline_is_exactly_what_the_script_derives` | 1 passed | 1 failed |
| deriver hard-codes `total_passed: 90` | `test_committed_baseline_is_exactly_what_the_script_derives` | 1 passed | 1 failed |
| `BASELINE_PATH` moved under `evidence/story-5.8/` | `test_baseline_is_not_in_the_evidence_tree` | 1 passed | 1 failed |
| `measured_configuration` changes the digested body | `test_adding_behavioral_digest_left_configuration_digest_untouched` | 1 passed | 1 failed |

Two mutations initially did NOT redden. Both are recorded rather than quietly dropped:

1. Disabling `main`'s `result["passed"] = result["passed"] and consistent` changed nothing, because the only test over that row asserted the row EXISTED, not that a drifted baseline fails the gate — a real gap. **Fixed** by adding `test_a_drifted_baseline_makes_the_drop_check_exit_non_zero`, which the same mutation now reddens.
2. Mutating the deriver's digest to raw bytes was aimed at `test_baseline_source_digest_is_line_ending_normalised`, which reads the committed file and therefore cannot see a deriver change. The guard that actually covers it is `test_committed_baseline_is_exactly_what_the_script_derives`; re-pointed and confirmed red. This revealed no coverage gap — the normalisation is guarded — only a mis-stated claim, corrected here.

**Pre-existing failure, not inherited silently.** `test_walkthrough_claims.py::test_reviewer_facing_relative_links_resolve[DEVELOPMENT.md]` fails at HEAD and still fails: `docs/DEVELOPMENT.md:195` links to `../.planning/codebase/CONVENTIONS.md`, which `ec98efb` deleted. `docs/DEVELOPMENT.md` is outside this story's scope, so the link is left in place and recorded here. The sibling `[TESTING.md]` case WAS in scope (AC6 edits that file) and is now green.

**Skip count.** The suite reports 2 skipped rather than the floor's 1 while the tree is dirty: `test_evidence_binding.py:592` skips with "binding realism check needs a clean tree". It returns to 1 skipped once the work is committed, which the final clean-tree run confirms.

### Completion Notes List

- **AC1** — `backend/evals/baselines/live-conversations.json` is derived by `backend/scripts/derive_live_conversation_baseline.py` and is byte-identical to what that script re-derives (asserted, not claimed). It carries per-turn `{executed, passed}`, `source_evidence_path`, `source_evidence_sha256`, `measured_at_commit`, both models, `reasoning_effort`, `configuration_digest` and `behavioral_digest`. It sits outside `evidence/`, which is Decision 1's entire mechanism; `test_baseline_is_not_in_the_evidence_tree` asserts the location rather than the intent.
- **AC2** — three tiers plus the structural check, each a separate result row. Tier 1 watches the 27 full-marks turns and exempts `B:5`/`B:8`/`C:3`; Tier 2 READS the existing fact/effect layer's `false_claims` verdict and never re-derives a metric (per `docs/DOMAIN-MODEL.md`); Tier 3's floor is 83/90; the structural check requires `A`, `B`, `C`. `test_a_pass_on_one_tier_never_masks_a_failure_on_another` proves the non-masking directly.
- **AC3** — a behavioural-configuration mismatch or a truncated run on either side yields `outcome: "refused"` with a non-proving `skipped` status, and the tiers then report no verdict at all. Truncation is detected through this suite's own vocabulary (`blocking_reasons`, `complete_repetitions`, `runs[].complete`), never an invented `stopped_reason`.
- **AC4** — the operator-invoked drop check exits 1 on any tier failure, any refusal, and on a drifted baseline (all three proved through a real subprocess, not a function call). Results use the Gate A vocabulary, asserted equal to `gate_a_readiness._NON_PROVING` by import rather than by transcription. The free half — committed baseline still matches committed Story 5.7 evidence — runs in the default suite. **No workflow job, secret or cron entry added**; `.github/` is untouched.
- **AC5** — 34 new tests, all offline, all using the committed evidence as fixture; the mutation table above demonstrates each guard failing first.
- **AC6** — `backend/evals/README.md` and `docs/TESTING.md` now call the scripted corpus a conformance suite whose model output is authored, name what it therefore cannot prove (model routing quality), and point at the live counterpart. The four pinned substrings in `test_evaluation_harness.py:693` still pass. `docs/TESTING.md`'s dangling `.planning/codebase/` link is removed in the same edit and the drop check's runnable command published.
- **AC7** — no directory renamed, no Gate B aggregator built, `evidence/epic-5/release-gate-report.json` not created. No file under `evidence/` is modified. `configuration_digest` is unchanged: `behavioral_digest` is added to the RETURNED dict after the digest is computed over the original body, and `test_adding_behavioral_digest_left_configuration_digest_untouched` re-derives the Story 5.7 value and asserts equality.
- **Deviation worth naming.** `test_live_conversation_configuration.py::test_the_record_holds_no_credential_field` asserts a CLOSED key set on `measured_configuration`, so the new field correctly reddened it. The set was extended with `behavioral_digest`; the guard's purpose (no credential ever appears) is unchanged and the closed-set mechanism was preserved rather than loosened to a subset check.
- **`PyYAML`** is in the `dev` group with the `opentelemetry-sdk` TEST-ONLY rationale written inline, `uv.lock` regenerated in the same change, and `yaml` imported only inside `backend/evals/` — lazily, inside the function, so importing the module in an image built with `uv sync --no-dev` does not fail.

### File List

- `backend/evals/baselines/live-conversations.json` (new)
- `backend/scripts/derive_live_conversation_baseline.py` (new)
- `backend/scripts/live_conversation_drop_check.py` (new)
- `backend/tests/test_live_conversation_drop_check.py` (new)
- `backend/evals/live_conversations/configuration.py` (modified)
- `backend/scripts/evidence_binding.py` (modified)
- `backend/tests/test_live_conversation_configuration.py` (modified)
- `backend/evals/README.md` (modified)
- `backend/pyproject.toml` (modified)
- `backend/uv.lock` (modified)
- `docs/TESTING.md` (modified)

## Change Log

| Date | Change |
| --- | --- |
| 2026-09-22 | Story 5.8 implemented: committed live-conversation baseline, three-tier + structural comparator with configuration and truncation refusals, Gate-A-shaped operator drop check, free default-suite consistency check, `behavioral_digest`, and the README/TESTING wording correction. Backend 2195 passed / 1 pre-existing failure; frontend 648 passed. |
| 2026-09-23 | Code review (3 layers + independent verification): 3 decision-needed findings resolved with Minh and applied, 7 patch findings applied, 9 dismissed as noise. Added `document_shape_refusal`, derive-time source-cleanliness validation, `tier_1` turn-set-parity coverage, `baseline_matches_source`'s own-source-path fix, a documented `DEMONSTRATION_ENABLED` digest gap, an `AGGREGATE_FLOOR` staleness comment, and corrected the Facts table's false "PyYAML is not installed" claim plus Decision 9's rationale. 8 new tests, each demonstrated failing first, then reverted. Backend 2202 passed / 1 pre-existing failure (unchanged) / 2 skipped (dirty tree). Status → `done`. |
