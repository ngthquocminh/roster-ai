---
title: 'Epic 5 retro hygiene bundle (action 2)'
type: 'chore'
created: '2026-10-05'
status: 'done'
baseline_commit: '94e6fe2fd959f53c73ca2efc61bd50ab024aab34'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-5-retro-2026-10-05.md'
  - '{project-root}/docs/EVIDENCE-CONVENTION.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Three small defects from the Epic 5 second-half retro: `agent_cancelled` has no stated meaning and a comment that is now false (Story 5.7 added a second path in); three application ports still import SQLAlchemy and sit in `ALLOWED_LEAKS`; a real `backend/.env` reddens the default pytest session.

**Approach:** Documentation and annotation fixes plus one conftest pin. No behaviour change, no migration, no new `status_reason`.

## Boundaries & Constraints

**Always:** `agent_cancelled` means "a run that stopped without failing: an approval outcome, or a suspended call with no approval path". Match `ports/approval.py` for `connection: Any`. Live-marked tests keep reading the real `.env` values. Mutation table for the conftest pin in this spec's Dev Agent Record, every mutation reverted, tree left clean.

**Ask First:** Anything that needs a schema, status or `status_reason` change.

**Never:** Touch `agent_run` status handling code. Print or read `backend/.env` values into logs. Edit evidence files. Extend legacy `backend/llm|services|store`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected | Error Handling |
|---|---|---|---|
| Default session, real `.env` | `AGENT_RUNTIME_MODEL=<real>`, `AGENT_RUNTIME_API_KEY=<key>` | `default_settings()` sees `deterministic`, key `None` | N/A |
| Live session | `pytest -m live` | real values untouched | N/A |
| Env set by the shell, not `.env` | exported before pytest | pinned the same (default session) | N/A |

</frozen-after-approval>

## Code Map

- `backend/adapters/postgres/conversation.py:59-63` -- false comment above `APPROVAL_CANCELLATION_REASONS`.
- `_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md:84-103` -- AD-7 rule text and the `approval_required --> agent_cancelled: rejected or expired` edge.
- `_bmad-output/planning-artifacts/architecture/architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md` -- EAD-5, where half (i) is recorded.
- `backend/api/routers/conversations.py:470-490, 540-552` -- the two non-approval routes into `agent_cancelled` (5.7 unapprovable capability; 4.1 policy refusal), both `status_reason` NULL. Read-only.
- `backend/api/routers/approvals.py:208, 295-298` -- resumed turn: `RESUME_WITHHELD_CAPABILITIES`, `ResumedTurnSuspendedError` finalizes `agent_failed`. Read-only.
- `backend/application/ports/{membership,site_baseline,scenario_catalogue}.py` -- the three SQLAlchemy imports.
- `backend/tests/architecture/test_conversation_boundaries.py:42-53, 101-113` -- `ALLOWED_LEAKS` and its companion test.
- `docs/ARCHITECTURE.md:11-15` -- leak sentence. `docs/TESTING.md:166-171` -- conftest description.
- `backend/conftest.py:45-63` -- env pins; `settings.py:433-434` reads the two vars.
- `_bmad-output/implementation-artifacts/{sprint-status.yaml,deferred-work.md}` -- ledger.

## Tasks & Acceptance

**Execution:**
- [x] `backend/adapters/postgres/conversation.py` -- rewrite the comment: approval outcomes carry a reason; two other routes (suspended call with no approval path; policy-refused request) land `agent_cancelled` with `status_reason` NULL -- per the definition above.
- [x] AD-7 in the main spine -- state the `agent_cancelled` meaning in the Rule; relabel the edge `rejected, expired or stale`; add a dated amendment line in the file's existing amendment style.
- [x] Epic 4 spine EAD-5 -- record A2 half (i): Story 5.7 does NOT settle it (different route, first turn in `conversations.py`; the resumed turn refuses a second suspension as `agent_failed`, Story 4.3 option A, and is unreachable today because `RESUME_WITHHELD_CAPABILITIES` withholds the baseline capability). EAD-5 still does not say whether a resumed turn may suspend again. Owner Winston; check point: the first story that gives a second capability an approval path or shrinks `RESUME_WITHHELD_CAPABILITIES`.
- [x] `sprint-status.yaml` -- Epic 4 A2 `done`; 2026-09-10 epic "5" SQLAlchemy action `done`; 2026-10-05 action 2 `done`; each with a dated note.
- [x] The three `ports/*.py` -- drop `from sqlalchemy import Connection`, add `Any`, `connection: Any`.
- [x] `test_conversation_boundaries.py` -- empty `ALLOWED_LEAKS` and refresh its comment; keep the companion test (vacuous when empty, still the mechanism).
- [x] `docs/ARCHITECTURE.md` -- replace the "Three ports ... currently import" sentence with the empty-list fact.
- [x] `backend/conftest.py` -- after the `settings` import, pin `AGENT_RUNTIME_MODEL=deterministic` and pop `AGENT_RUNTIME_API_KEY` unless the session selects `live`. Decide in `pytest_configure` from `config.getoption("markexpr")`; keep the real values captured before the pin so a live session restores them.
- [x] `docs/TESTING.md` -- one sentence on the pin beside the existing conftest paragraph.
- [x] `deferred-work.md` -- close the story-5.5 and story-5.6 entries, and the story-2-3 `ScenarioCatalogueReader` and story-5.4 two-port entries, striking through per ledger style with date and this spec.
- [x] Verify the mutation table by running each mutation, then revert.

**Acceptance Criteria:**
- Given the three ports, when `pytest tests/architecture` runs, then `ALLOWED_LEAKS` is empty and all architecture tests pass.
- Given a backend `.env` with a real `AGENT_RUNTIME_MODEL` and key, when the default suite runs, then it passes.
- Given `pytest -m live`, when the session starts, then `AGENT_RUNTIME_MODEL`/`AGENT_RUNTIME_API_KEY` hold the real values.

## Spec Change Log

## Design Notes

The first draft said the pin needed no bespoke test because `test_agent_deterministic_model.py` and `test_conversations_api.py` already redden under a leaked model. Mutating the real code disproved it: with a fake model and key exported, those suites stay green with both pins deleted (`test_agent_deterministic_model.py` already calls `monkeypatch.delenv`). The guard is therefore `backend/tests/test_agent_runtime_env_isolation.py`, added in this change. The pin lives in `pytest_configure` (not at import) because only the parsed `-m` expression says whether the session is live.

## Verification

**Commands:**
- `cd backend && uv run pytest tests/architecture -q` -- expected: all pass
- `cd backend && AGENT_RUNTIME_MODEL=openrouter:x AGENT_RUNTIME_API_KEY=k uv run pytest -q` -- expected: pass (Postgres tests may skip)
- `cd backend && uv run python -m pytest -m live --collect-only -q` with the vars exported -- expected: live gate sees real values

## Dev Agent Record

Mutation table for the conftest pin. Env exported in the shell (`AGENT_RUNTIME_MODEL=openrouter:x AGENT_RUNTIME_API_KEY=k`), no `.env` read. Each mutation applied to `backend/conftest.py`, run against `tests/test_agent_runtime_env_isolation.py`, then restored from a saved copy; `git diff` after each showed the file back to its delivered state.

| mutation applied to real code | guard that should redden | before | after |
|---|---|---|---|
| delete `os.environ["AGENT_RUNTIME_MODEL"] = "deterministic"` | `test_default_session_runs_against_the_keyless_deterministic_double`, `test_a_default_session_overrides_real_agent_runtime_values` | 9 passed | 2 failed, 7 passed (both named) |
| delete `os.environ.pop("AGENT_RUNTIME_API_KEY", None)` | the same two (`agent_runtime_api_key is None`) | 9 passed | 2 failed, 7 passed (both named) |
| invert `if _selects_live(...)` to `if not _selects_live(...)` | the two above plus `test_a_live_session_keeps_the_real_agent_runtime_values` | 9 passed | 3 failed, 6 passed (all three named) |
| drop the `not live` stripping in `_selects_live` | `not live` and `postgres and not live` rows of `test_only_a_mark_expression_that_selects_live_counts_as_a_live_session`, plus the default-session pair | 9 passed | 4 failed, 5 passed (all named) |
| re-add `from sqlalchemy import Connection` to `application/ports/membership.py` (with `ALLOWED_LEAKS` empty) | `test_new_conversation_application_modules_are_framework_free` | 4 passed | 1 failed, 3 passed (that test); port restored, 90 architecture tests pass |
| remove the empty-expression early return in `_selects_live` | `test_only_a_mark_expression_that_selects_live_counts_as_a_live_session[-True]` | 9 passed | 1 failed, 8 passed (that row) |

An earlier attempt at the fourth conftest row with `sed` did not apply (no diff) and is not counted. Results of the delivered state: `tests/architecture` 90 passed; full default suite with `AGENT_RUNTIME_MODEL=openrouter:x AGENT_RUNTIME_API_KEY=k` exported: 2662 passed, 209 skipped (no PostgreSQL service here), 10 deselected, 0 failed.

Also found: the ledger's 5.5 entry named `test_agent_deterministic_model.py` as exposed, but it already deletes the variable itself.

Review (inline, no subagents) found one patch, fixed: `_selects_live("")` returned False, but `-m ""` drops `addopts`' `not live` filter so live tests run; the pin would have cleared the key and silently skipped them. It now returns True, with a test row and the mutation above. Final: isolation file plus `tests/architecture` 99 passed.

## Suggested Review Order

**Test isolation (the one behavioural change)**

- Decide the pin in `pytest_configure`: only the parsed `-m` expression says whether a session is live.
  [`conftest.py:78`](../../backend/conftest.py#L78)

- The live check strips `not live` and treats an empty `-m` as live; both were review-driven.
  [`conftest.py:67`](../../backend/conftest.py#L67)

- The dedicated guard: the existing suites could not prove the pin, so this one can go red.
  [`test_agent_runtime_env_isolation.py:19`](../../backend/tests/test_agent_runtime_env_isolation.py#L19)

**AD-1 leak closed**

- Typing `connection: Any` matches `approval.py` and removes the vendor import.
  [`membership.py:11`](../../backend/application/ports/membership.py#L11)

- `ALLOWED_LEAKS` is now empty; the sweep over `application/ports` is what keeps it so.
  [`test_conversation_boundaries.py:50`](../../backend/tests/architecture/test_conversation_boundaries.py#L50)

- The docs sentence now states the empty list instead of the three named ports.
  [`ARCHITECTURE.md:13`](../../docs/ARCHITECTURE.md#L13)

**`agent_cancelled` meaning and A2**

- The spine's definition: stopped without failing, with or without an approval binding.
  [`ARCHITECTURE-SPINE.md:89`](../planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md#L89)

- The edge label now includes stale.
  [`ARCHITECTURE-SPINE.md:101`](../planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md#L101)

- A2 half (i) stays open here with owner and check point; 5.7 does not settle it.
  [`ARCHITECTURE-SPINE.md:82`](../planning-artifacts/architecture/architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md#L82)

- The previously false comment, now matching both paths into the status.
  [`conversation.py:59`](../../backend/adapters/postgres/conversation.py#L59)

**Ledgers and docs**

- Epic 4 A2 marked done, with the half (i) disposition recorded.
  [`sprint-status.yaml:2947`](sprint-status.yaml#L2947)

- The pin's behaviour for readers of the test docs.
  [`TESTING.md:174`](../../docs/TESTING.md#L174)
