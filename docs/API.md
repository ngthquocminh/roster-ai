# ShiftMind API

The running application is the API contract. With the composed stack running,
use its OpenAPI interfaces: `/docs` for Swagger UI, `/redoc` for Redoc, and
`/openapi.json` for the machine-readable schema. Do not maintain a second,
hand-written route contract here.

## Approval and provenance semantics

An approval request binds one feasible candidate schedule to its scenario,
policy, and expected resource version. Creating a request requires an
`Idempotency-Key`; a replay returns the existing binding. A decision also
requires an idempotency key and expected resource version. A successful
approval consumes the binding, promotes the candidate schedule version exactly
once, and appends the corresponding audit records. Rejection, expiry, and
staleness are distinct terminal outcomes.

The provenance reader is the authoritative, site-scoped timeline for a
schedule run. It joins committed run, conversation, approval, and audit facts
without recomputing figures. Before/after baseline versions come from the
immutable audit pair, not from the current baseline pointer. A protected or
unknown run returns the same not-found response.

### Problem codes

RFC 7807 bodies carry a literal `code`. The generated schema types it as a bare
string with no enum, so these codes, their statuses and their meanings exist
nowhere in `/openapi.json` — which is why they are kept here.

| Code | Status | Meaning |
|---|---|---|
| `approval_not_granted` | 403 | Policy does not grant baseline approval |
| `candidate_not_found` | 404 | No candidate is visible in this site |
| `candidate_not_promotable` | 409 | The run is not `solver_completed`, or has no feasible candidate |
| `stale_resource_version` | 409 | The run changed since the version you pinned |
| `stale_baseline_version` | 409 | The current baseline is not the one you expected, or it moved during consumption — the promotion bundle rolls back and the binding stays `pending` |
| `approval_already_pending` | 409 | A pending binding already exists for this candidate |
| `approval_not_found` | 404 | No approval binding is visible in this site |
| `approval_not_pending` | 409 | The binding already reached a terminal state |
| `approval_expired` | 409 | The decision attempt committed expiry terminalization |
| `approval_stale` | 409 | The decision attempt committed stale terminalization |
| `agent_run_not_cancellable` | 409 | The agent run awaiting this approval left `approval_required`; nothing was written |
| `approval_payload_unreadable` | 500 | An agent-backed binding's stored `pending_payload` is absent or does not carry exactly one pending call; the promotion rolled back |
| `idempotency_key_conflict` | 409 | The key was reused with a different body |
| `invalid_approval_command` | 422 | The command is otherwise unusable |
| `schedule_run_not_found` | 404 | Provenance: no such run is visible in the current site |

**`expected` and `current` are omitted, not emptied.** AD-13's literal `expected`
and `current` objects appear only when there is context to compare — a version,
state, or policy. Codes describing a condition with nothing to compare
(`approval_not_found`, `approval_not_granted`) omit both keys rather than
publishing an empty object. Both are declared optional and generated into the
client types.

**`ApprovalOut` deliberately withholds the digests.** It publishes identifiers,
versions, consequence summary, `created_at` and `expires_at` — not
`parameter_hash` / `consequence_hash`. The material parameters are the run,
candidate and baseline versions, which it already carries; provenance reads the
digests from `audit_event`, which carries both.

**Refusals leave an audit trail of their own.** Pre-write `approval_not_pending`
and `stale_resource_version` refusals against a binding resolved in the current
site append an authoritative `approval_denied` row (`success=false`), keyed
independently by `(site_id, attempt_id)`. Missing or cross-site bindings and the
feature-policy pre-check write no denial row. The row's evidence references
identify the candidate the refused attempt targeted, not evidence the admission
check consulted.

### Comparison unavailable: the three reasons

If a frozen baseline cannot be authoritatively read, is for another scenario
version, or has no persisted metrics, the endpoint returns `200` with
`comparison: null` and a literal `comparison_unavailable_reason`; the run,
candidate schedule and pending approval remain readable. An unavailable baseline
is never represented as an empty baseline. The reason names which of the three
happened and always embeds the affected version id:

- "Baseline schedule version `<id>` is not authoritatively readable, so this candidate cannot be compared against it." — missing row, malformed pointer, or a payload that no longer matches the schedule-version contract
- "The promoted baseline `<id>` belongs to a different scenario version, so this candidate cannot be compared against it."
- "The promoted baseline `<id>` has no authoritative metrics, so this candidate cannot be compared against it."

An **absent** baseline pointer is a different case from an **unreadable** one: it
produces a *present* comparison whose baseline metrics and assignment diff are
null.

### Expiry is presented, not stored

A binding whose `expires_at` has passed is presented as `expired` by every read
path while the stored row stays `pending`. The terminal `expired` state is
materialised only inside a decision transaction. Reads never write.

### Enforced by

This page carries semantics the schema cannot express; these suites hold them to
the implementation:

- `backend/tests/test_approvals_api.py` — problem codes, statuses, the
  `expected`/`current` omission rule, and the `approval_denied` audit rows
- `backend/tests/test_schedule_runs_api.py:299,409,438` — the three literal
  `comparison_unavailable_reason` strings

## Route inventory

Generated from the running composed application on 2026-09-09 with:

```bash
docker compose exec -T api python -c "from api.main import app; print('\\n'.join(sorted(app.openapi()['paths'])))"
```

That command lists the paths; counting the methods on each gives the operations.
At the commit this page was written the schema held **37 paths / 40 operations**
under `/api/v1` — auth, scenario catalogue and projections, conversations,
proposals, schedule runs, approvals and provenance — and **13 paths / 15
operations** outside it: `health`, `fixtures`, the fake OIDC endpoints, and the
v0.3 compatibility routes (`/scenarios`, `/runs`, `/constraints`) that are still
mounted and still served from the legacy store. Those legacy routes are taken
offline by the Gate A cutover described in
[`GATE-A-RUNBOOK.md`](GATE-A-RUNBOOK.md), not by this milestone.

These counts are a dated observation, not a maintained inventory — re-run the
command rather than trusting them. The generated schema is the authoritative
route list; this page carries only the approval and provenance semantics above,
which a schema cannot express.
