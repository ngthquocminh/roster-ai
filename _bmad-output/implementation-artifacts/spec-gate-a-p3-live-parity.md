---
title: 'Gate A P3 — replace the circular 1.9 guard with live proof'
type: 'chore'
created: '2026-08-18'
status: 'done'
baseline_commit: 'ff0ac3bb60242535789a9f0824dfa2383fb731c0'
review_loop_iteration: 0
context:
  - '{project-root}/docs/GATE-A-RUNBOOK.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Two Story 1.9 artifacts prove nothing about the running system. The
third test in `test_gate_a_mutation_audit.py` only asserts string literals inside
`evidence/story-1.9/gate-a-viewer-parity-and-mutation-denial.json`, and the
`viewer_parity_evidence` registry check reads that same file's `passed` flag as a
present-tense verdict. Neither has ever issued a mutating HTTP request. Story 3.1
has now added three write routes that carry **zero** auth negative tests.

**Approach:** State the read-only invariant positively in writing, replace the
circular test with real denied write requests against those three routes, and
swap `viewer_parity_evidence` onto the live API-parity test that already exists.
Static-evidence checks drop from 4 to 3.

## Boundaries & Constraints

**Always:**
- Write the invariant statement **before** touching any test — it is a design
  decision, not a test fix.
- Red-then-green for every new guard (standard A2): show each assertion failing
  for the right reason before it passes.
- Each check stays filed under the invariant it actually proves.
- `evidence/story-1.9/gate-a-viewer-parity-and-mutation-denial.json` stays on
  disk unmodified — a true record of commit `e2ecdb6`. We stop consuming it as a
  present-tense verdict; we do not delete or edit it.

**Ask First:**
- Any change to `test_gate_a_scenario_openapi_surface_is_get_only`.
- Any registry change that reduces what a check proves.

**Never:**
- No `subject_paths` machinery across the 20 checks (rejected 2026-08-17).
- No expiry mechanism on evidence files — the monotone audit rule in
  `evidence_binding.py` is correct by design.
- Do not touch `test_gate_a_postgres_read_adapters_contain_no_mutating_sql_literals`.
- No application-level "viewer role" — none exists; `role` here means a
  PostgreSQL role.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output | Error Handling |
|----------|--------------|-----------------|----------------|
| No session | `POST /api/v1/proposals`, no session cookie | `401`, `code == "authentication_required"` | Repository never called |
| No CSRF header | `POST /{id}/revisions`, valid session, no `X-CSRF-Token` | `403`, `code == "csrf_validation_failed"` | Repository never called |
| Wrong site | `POST /{id}/rejection`, session for site B, proposal in site A | `404`, `code == "proposal_not_found"` — invisible, not merely forbidden | No write attempted |
| Authorized | session + CSRF + `Idempotency-Key` | reaches the handler | unchanged |

</frozen-after-approval>

## Code Map

- `docs/GATE-A-RUNBOOK.md` -- intro block, lines 1-21. Put the statement here, unnumbered, so sections 1-4 are not renumbered.
- `_bmad-output/implementation-artifacts/deferred-work.md` -- ~line 103 holds the `CORRECTED 2026-08-18` entry and its `Direction:` line.
- `backend/tests/test_gate_a_mutation_audit.py` -- test #3 at lines 52-70 is the target; #1 and #2 stay byte-identical. Already registered under `backend_mutation_denial`, so the new tests need **no** registry change.
- `backend/tests/test_conversations_api.py:274-316` -- `conversation_client` fixture + `_headers()`: the dependency-override + `TestClient` pattern to copy. No PostgreSQL needed.
- `backend/tests/test_conversations_api.py:361-388` -- the 401/403 assertion shape to follow.
- `backend/api/routers/proposals.py:30` -- router prefix `/proposals`; the three write routes all take `Depends(get_site_context)` and a required `Idempotency-Key` header.
- `backend/api/deps.py:153-231` -- `get_session` / `get_site_context`: session + membership + RLS `app.site_id`. That is the entire auth model.
- `backend/scripts/gate_a_checks.py:331-339` -- `viewer_parity_evidence`. `__post_init__` (120-135) forbids `evidence_path` and `test_files` together, so this is a swap.
- `backend/tests/test_postgres_integration.py:840` -- the live API-parity test the evidence file's `api_parity: "passed"` stood in for.

## Tasks & Acceptance

**Execution:**
- [x] `docs/GATE-A-RUNBOOK.md` -- add a dated subsection stating the invariant positively: Gate A read-only means **no write path mutates governed scenario data or the operational baseline pointer**; a proposal is new state, not a mutation of `scenario`/`scenario_version`; every write route is authenticated, CSRF-guarded and site-scoped. Name the three Story 3.1 routes as approved write paths, with reasons. -- closes the "invariant lives only in someone's head" gap.
- [x] `deferred-work.md` -- append a dated `CLOSED 2026-08-18` note under the existing `Direction:` line, pointing at the runbook subsection and the new tests. Do not rewrite existing entries. -- keeps the ledger the index of what was decided.
- [x] `backend/tests/test_gate_a_mutation_audit.py` -- delete test #3 and its `EVIDENCE_PATH` constant; add a fixture-backed negative-request suite covering every matrix row across all three write routes, asserting the repository was never reached. -- live proof, and it closes Story 3.1's missing auth coverage.
- [x] `backend/scripts/gate_a_checks.py` -- replace `viewer_parity_evidence` with `api_parity` (story `1.9`, invariant `parity_tests`, `runner="pytest"`, `test_files=("backend/tests/test_postgres_integration.py",)`). -- the invariant is measured every push instead of read from a frozen file.

**Acceptance Criteria:**
- Given the runbook, when a reader asks what "read-only" means now that drafts are writable, then a dated positive statement answers it without inferring from test code.
- Given `GATE_A_CHECKS`, when counting non-`None` `evidence_path` entries, then the count is 3 and none is a Story 1.9 check.
- Given `validate_registry()`, when it runs, then `parity_tests` still has a contributing check and nothing declares both artifact kinds.
- Given `test_gate_a_scenario_openapi_surface_is_get_only` and the SQL-literal test, when the diff is inspected, then both are byte-identical to `HEAD`.
- Given `evidence/story-1.9/...json`, when the diff is inspected, then it is unmodified and still present.

## Spec Change Log

**2026-08-18 — implementation-time correction, "three write routes" → two (then six).**
The frozen Intent and I/O Matrix say Story 3.1 added *three* write routes and
name `POST /api/v1/proposals` as one of them. Measured: `proposals.py` mounts
exactly three routes and only **two** are writes (`/{id}/revisions`,
`/{id}/rejection`). There is no HTTP create route — proposals are created inside
the conversation turn by `finalize_agent_run`, per Story 3.1 Decision 1. The
matrix row keyed to `POST /api/v1/proposals` was therefore unimplementable as
written. Rather than drop it, the guard was generalized: the denial tests are
parametrized over **every** mutating route the live OpenAPI document exposes
under `/api/v1` — six today, including two conversation routes and
`auth/logout` that the spec never contemplated. Known-bad state avoided: a
hand-listed set of routes that silently stops covering the next write path
someone mounts. KEEP: the derive-from-OpenAPI approach, and
`test_gate_a_write_surface_is_exactly_the_approved_paths`, which forces a human
to record a reason in the runbook before a new write route can land.

**2026-08-18 — "wrong site → 404" row not implemented as a request test.**
Proving cross-site invisibility needs real RLS; with the repository stubbed, the
assertion would only be reading its own stub — the circularity this whole item
exists to remove. Replaced by `test_proposal_write_routes_resolve_site_context_and_session`,
a structural assertion that neither write handler can run without
`get_site_context` and `get_session`. The behavioural side stays with
`test_proposal_persistence.py` on PostgreSQL. A cross-origin denial test was
added in its place, which the stubbed client *can* prove.

**2026-08-18 — adversarial review pass (Blind Hunter + Edge Case Hunter).**
Twelve findings, deduplicated; every one verified against the code before
acting. Applied in place rather than through a revert-and-re-derive loop,
because none invalidated the approach — they were corrections *to* it, and
reverting working, mutation-tested code would have cost the red-then-green
evidence for no gain. What changed:

- *Registry binding was weaker than claimed.* `api_parity` binds a whole file,
  and `declared_pytest_cases()` recovers expectations from that same source, so
  deleting the parity test would have removed the alarm with the proof. Pinned
  by name in `test_api_parity_binds_a_test_that_still_exists`.
- *A deletion with a live dependant.* `regenerate_evidence.py` names the removed
  test as the guard on 1.9's `legacy_route_*` fields. Those two assertions were
  re-homed to `test_evidence_convention.py` — the guard was sound; only its use
  as a stand-in for live proof was not.
- *The write-surface test ignored three open write routes.* `POST /scenarios`,
  `/scenarios/{id}/runs`, `/constraints` live outside `/api/v1`, unauthenticated,
  gated only by a filesystem flag. A test named "the write surface is exactly the
  approved paths" that skipped them was worse than none; it now covers the whole
  app and names them explicitly.
- *Three runbook overclaims.* "Every one of these is site-scoped" is false for
  `auth/logout` (no site-scoped row) and imprecise for `agent-runs/execute`
  (opener, not per-request context); and the table does not mechanically enforce
  anything. All three rewritten to what the code actually does.
- *Two blind spots closed:* a write verb on an already-public path, and a route
  hidden with `include_in_schema=False`.
- *Vacuous assertions made falsifiable:* `repository.calls == []` was true by
  construction, so a positive control now proves an authorized write does reach
  the repository. Fixture isolation was nominal — `lifespan` reads module-level
  settings — so it sets the environment instead.
- *Stale counts* in `gate_a_readiness._evidence_result`'s docstring (four→three,
  sixteen→seventeen) and in `deferred-work.md`'s "4 of 20".

Five findings were recorded as deferred rather than fixed; see
`deferred-work.md`, "Deferred from: review of spec-gate-a-p3-live-parity".
KEEP: the derive-from-OpenAPI discovery, the positive control, and the practice
of red-checking each new guard by mutating production code and reverting.

## Design Notes

**Why the negative tests do NOT fill `viewer_parity_evidence`'s slot.** The
literal instruction was to repoint that check at the new test. But it sits under
the **`parity_tests`** invariant, and a mutation-denial test filed there would
recreate the exact mis-filing defect the ledger already records — an invariant
that "would still roll up `passed` with every authorization test removed from
its bucket". No compromise is needed: `test_gate_a_mutation_audit.py` is already
registered under `backend_mutation_denial` / `negative_mutation_tests`, so the
new tests land correctly for free, and the vacated slot is filled by the one
thing the evidence file claimed that still has no live check — `api_parity`.

**Cost of the swap, stated plainly.** `test_postgres_integration.py` is
`@pytest.mark.postgres`. Once `parity_tests` depends on it, a readiness run with
no Docker service reports `skipped`, which `_NON_PROVING` treats as blocking.
That is the intended trade — the check gains the ability to say no. The same
file already backs `postgresql_site_membership`, so the postgres suite was
already required for a green gate; no new step in runbook section 3.

## Verification

**Commands:**
- `cd backend && uv run --frozen pytest tests/test_gate_a_mutation_audit.py -v` -- new negative tests pass; #1 and #2 still pass.
- `cd backend && uv run --frozen pytest tests/test_gate_a_readiness.py tests/test_evidence_convention.py` -- registry validation and the repo-wide evidence sweep stay green.
- `cd backend && uv run --frozen python -c "from scripts.gate_a_checks import GATE_A_CHECKS, validate_registry; validate_registry(); print(sum(1 for c in GATE_A_CHECKS if c.evidence_path))"` -- prints `3`.
- `git diff HEAD --stat -- evidence/` -- empty.

**Manual checks:**
- Red-then-green log for each new assertion, captured in the implementation notes.

## Suggested Review Order

**The decision (read this first)**

- The invariant, stated positively and dated — everything else follows from it.
  [`GATE-A-RUNBOOK.md:20`](../../docs/GATE-A-RUNBOOK.md#L20)

- Approved write paths with per-route reasons; site scoping is deliberately not uniform.
  [`GATE-A-RUNBOOK.md:38`](../../docs/GATE-A-RUNBOOK.md#L38)

- The three unauthenticated legacy routes, named rather than quietly skipped.
  [`GATE-A-RUNBOOK.md:69`](../../docs/GATE-A-RUNBOOK.md#L69)

**The registry swap**

- Why `viewer_parity_evidence` was circular and what replaced it.
  [`gate_a_checks.py:332`](../../backend/scripts/gate_a_checks.py#L332)

- File-granularity binding can't see a deleted test, so the name is pinned.
  [`test_gate_a_readiness.py:194`](../../backend/tests/test_gate_a_readiness.py#L194)

- The evidence-backed set shrank 4 → 3; growth is now a decision.
  [`test_gate_a_readiness.py:218`](../../backend/tests/test_gate_a_readiness.py#L218)

**Live denial, replacing the circular test**

- Routes derived from OpenAPI, never hand-listed — future writes covered on mount.
  [`test_gate_a_mutation_audit.py:178`](../../backend/tests/test_gate_a_mutation_audit.py#L178)

- Whole-app write surface, legacy routes included; a new route turns this red.
  [`test_gate_a_mutation_audit.py:243`](../../backend/tests/test_gate_a_mutation_audit.py#L243)

- The three denial assertions: no session, no CSRF, cross-origin.
  [`test_gate_a_mutation_audit.py:291`](../../backend/tests/test_gate_a_mutation_audit.py#L291)

- Positive control — without it, every denial assertion is true by construction.
  [`test_gate_a_mutation_audit.py:420`](../../backend/tests/test_gate_a_mutation_audit.py#L420)

**Blind spots closed by review**

- A write verb on an already-public path would have escaped the filter.
  [`test_gate_a_mutation_audit.py:274`](../../backend/tests/test_gate_a_mutation_audit.py#L274)

- `include_in_schema=False` would have hidden a route from every guard at once.
  [`test_gate_a_mutation_audit.py:452`](../../backend/tests/test_gate_a_mutation_audit.py#L452)

- The proposal-creating run route scopes differently, so it is asserted separately.
  [`test_gate_a_mutation_audit.py:390`](../../backend/tests/test_gate_a_mutation_audit.py#L390)

**Supporting**

- Re-homed guard: the deleted test was `regenerate_evidence.py`'s only dependant.
  [`test_evidence_convention.py:287`](../../backend/tests/test_evidence_convention.py#L287)

- Isolation via environment, because `lifespan` never sees dependency overrides.
  [`test_gate_a_mutation_audit.py:201`](../../backend/tests/test_gate_a_mutation_audit.py#L201)

- Structural site-scoping for the two proposal write routes.
  [`test_gate_a_mutation_audit.py:353`](../../backend/tests/test_gate_a_mutation_audit.py#L353)
