---
baseline_commit: 8ebc34f49c0e23aba167c3aebc2e8a32cdfe4ace
---

# Story 4.4a: Supply Audit Evidence References

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the product team,
we want every consequential audit row to carry the checksum-bound evidence locators of the
candidate its attempt targeted,
So that NFR32's evidence clause rests on a record that can actually fail, and Story 4.5 has a
real oracle rather than a structurally empty field.

**This story is a WRITE-PATH CARRIER, inserted by course correction, and it is deliberately
small.** It exists because Story 4.5's AC3 could not be proven as written: `audit_event.evidence_refs`
is the literal `()` at all four production write sites, so *"no audit or provenance link points
to unverified evidence"* is unfalsifiable on its audit half. 4.5 is a proof story; a story that
authors both the mechanism and its own oracle cannot fail. The mechanism therefore lands here.
Full analysis, including both vacuities and the rejected designs:
`_bmad-output/planning-artifacts/sprint-change-proposal-2026-09-01.md`.

**It lands no migration, no new table, no new column, no new port, no new field on
`ApprovalBindingV1`, no new setting, and no new dependency.** Four production statements change,
one dataclass in `application/use_cases/` gains a field, one function signature gains a
parameter, one `SCOPE_CONTROLS` member is removed, and one ledger entry closes.

**Depends on, and consumes:** Story 3.2's `ScheduleVersionV1.evidence_refs`, stamped with
`producing_run_version` at `finalize_schedule_run.py:81-83` and sealed into
`schedule_version.payload` under `canonical_hash`; Story 4.1's `AuditEnvelopeV1`,
`PostgresAuditWriter`, and the `approval_request.candidate_schedule_version_id` FK pin; Story
4.2's `revalidate_binding` and its admission-check denial arm; Story 4.3's TX2; Story 4.4's
`PostgresAuditReader`, `SCOPE_CONTROLS`, and the `ProvenanceTimeline` rendering it already ships.

**Unblocks:** Story 4.5 — its rewritten AC3 (`epics.md:1276-1279`) asserts against audit rows
this story populates and **cannot be created until this story is `done`**.

**Scope summary:** Four audit write statements begin passing the candidate's `evidence_refs`
instead of `()`. `RevalidationV1` gains a `candidate` field and `revalidate_binding` moves one
side-effect-free read two lines up, so the expired arm reports honest absence rather than an
unlooked-at one. `promote_baseline` gains a `candidate` parameter supplied by its only caller.
`SCOPE_CONTROLS` loses its fifth member and `deferred-work.md`'s entry closes in the same commit.
Tests prove the new invariant in both directions. **No frontend component changes** —
`ProvenanceTimeline` already renders `item.evidence_refs` for every item type
(`ProvenanceTimeline.tsx:109`), so audit-sourced items begin rendering evidence links with no
code change; only coverage is added.

---

## Facts this story depends on — each one written down and citable

Retro action **A3** (`epic-1-2-retro-2026-08-16.md` §6.1) requires this pass before decisions.
Every rule below is recorded somewhere citable; none of it may be re-derived from adapter code.

| Fact | Where it is written |
|---|---|
| **Audit must capture immutable evidence references** — unqualified, per row, alongside actor/site, the identifier set, outcome, summaries/hashes, before/after and software versions | NFR32 (`epics.md:137`) |
| **Authoritative evidence is produced for successful, DENIED, stale, failed, and cancelled consequential actions** — the denied row is named by the requirement, not chosen by preference | FR21 (`epics.md:65`) |
| **Provenance links the request, the evidence consulted, and the decision path without hidden chain-of-thought** | FR20 (`epics.md:63`) |
| **Every Epic 4 contract or guard names its production supplier from the spine's table, or the story extends the table; a guard proven only against a stub is not production behaviour** | EAD-9 (Epic 4 `ARCHITECTURE-SPINE.md:101`) |
| **A passing guard that cannot be made to fail by a relevant mutation does not count** | Epic 4 spine *Verification Obligations* preamble (`:212`); epic-3 retro §1, §3 |
| **There is exactly one decision endpoint and one shared revalidation fork.** Any business mismatch terminalizes; only a transactional or infrastructure fault rolls the bundle back and leaves the binding `pending`. `revalidate_binding` must not grow a second decision path | EAD-10 (Epic 4 `ARCHITECTURE-SPINE.md:110`); `decide_approval.py:1-5, :69-72` |
| **Every read path is pure** — a read never writes | EAD-7 |
| **Domain and application code must not import SQLAlchemy, FastAPI, or a concrete provider; adapters call ports** | AD-1 (parent `ARCHITECTURE-SPINE.md:48`) |
| **Application code owns identity, site scope, versions, approvals, state transitions, persistence, and audit; no model output or client value grants authority** | AD-2 (parent `ARCHITECTURE-SPINE.md:54`) |
| **PostgreSQL owns append-only business audit; the normal application path has no UPDATE or DELETE on `audit_event`** | AD-12; EAD-1; NFR33 (`epics.md:139`) |
| **`EvidenceRefV1` is a version-bound projection locator** — `scenario_version_id`, the checksum triple, `producing_run_version`, `baseline_schedule_version`, `group`, `record_id`, and an optional field/minute range. It has no URI, no key, and no bucket; there is no evidence port and no object-storage adapter in this codebase | `application/contracts/evidence_ref.py:30-43`; Story 4.5 *Evidence scope note* (`epics.md:1292`) |
| **AR12's and AR23's create-only S3 evidence permissions are HOSTED requirements owned by Story 6.2**, not by any Epic 4 story | `epics.md:158`, `:169`, `:1463`; Story 4.5 *Evidence scope note* |
| **The candidate's evidence references are sealed and FK-pinned.** `schedule_version.payload` is immutable JSONB carrying `canonical_hash` with `checksum_algorithm='sha256'` and `checksum_schema_version='rfc8785-v1'`; `approval_request.candidate_schedule_version_id` pins the exact row | `adapters/postgres/schedule_run.py:1082`; `ApprovalBindingV1.candidate_schedule_version_id` (`approval_binding.py:36`) |
| **`ScheduleVersionV1.evidence_refs` is the only supply carrying a non-null `producing_run_version`**, stamped once at finalize | `finalize_schedule_run.py:81-83`; Story 4.4 *Honest gaps* |
| **The declared gap this story closes** — `audit_event.evidence_refs` empty at every write site, `SCOPE_CONTROLS[4]`, revisit trigger *"decide before Story 4.5 is created"* | `application/contracts/decision_provenance.py:18`; `deferred-work.md:590-608` (**DECIDED 2026-09-01**) |
| Never hand-type an evidence file: commit code → clean tree → measure → generate through a script → commit evidence separately | `docs/EVIDENCE-CONVENTION.md:9-20, 191-199` |
| **Manual assistive-technology verification is out of scope**; automated coverage is the only accepted proof | `EXPERIENCE.md:196` (Accessibility Floor) |

**`docs/DOMAIN-MODEL.md` governs demand families, units, and assignments, and it constrains
exactly one thing here: this story must not read inside an evidence reference.** An
`EvidenceRefV1` may carry `group="demand"` and locate a demand row, but this story **copies
tuples opaquely** — it reads no `family`, no `unit`, no `amount`, computes no metric, derives no
demand figure, and performs no conversion. §1's rule that `unit` is a property of the source
table and not a choice a metric may make is therefore satisfied vacuously, and must stay that
way: **do not add a calculator, a filter, a family predicate, or a unit check to any write site
in this story.** Cite the document; do not re-derive the family/unit rule from adapter code.

---

## Acceptance Criteria

Verbatim from `epics.md:1258-1284`.

1. **Given** a consequential attempt that resolves a candidate schedule version — request,
   promotion, terminal decision, or pre-write denial, **When** its audit event is written,
   **Then** the row carries that candidate's evidence references unchanged from the sealed
   `schedule_version` row, with no re-derivation, no re-checksumming, and no backfill of any
   prior row, **And** an attempt whose candidate does not resolve writes an empty set, proven by
   a demonstrated-red test rather than assumed. (FR21, NFR32)

2. **Given** the existing contracts and schema, **When** this story lands, **Then** no migration,
   no new column, no new port, and no new field on `ApprovalBindingV1` is introduced — the
   candidate is supplied from the `get_candidate` call that `request_approval` and
   `revalidate_binding` already make, on the repository `decide_approval_route` already injects,
   **And** `promote_baseline` receives the candidate as a parameter from its only caller, never
   by acquiring a repository of its own. (AD-1, AD-2)

3. **Given** a denial row written at the admission check, before revalidation runs, **When** its
   evidence references are read, **Then** they identify the candidate the refused attempt
   targeted, not evidence the attempt consulted, and both the story and the code state that
   distinction, **And** audit-sourced provenance items render these references with the semantics
   Story 4.4 already ships, without a new contract field. (FR20, NFR32)

4. **Given** the scope control declared by Story 4.4, **When** this story lands, **Then**
   `"audit_evidence_refs:empty_at_every_write_site"` is removed from `SCOPE_CONTROLS` in
   `application/contracts/decision_provenance.py`, because it is no longer true, **And** the
   corresponding deferred-work ledger entry is closed in the same commit, citing this story.
   (FR21, NFR32)

---

## Eight decisions were made at story creation — do not re-litigate them

> **Authoring rule in force since commit `2cf598f`:** every Decision below states, in one
> sentence, what its mechanism does **not** cover. Tasks cite these Decisions; they do not
> re-argue them.

### Decision 1 — Supply from the candidate at each write site; the `ApprovalBindingV1` snapshot is rejected

The correction's own trigger proposed snapshotting `evidence_refs` onto `ApprovalBindingV1` at
request time, mirroring `parameter_hash` / `consequence_hash`. **Rejected as heavier than the
code requires**, and AC2 forbids it by name. Three of the four sites already hold the candidate:

| Write site | Line at `8ebc34f` | Where its candidate comes from |
|---|---|---|
| `application/use_cases/request_approval.py` | `:153` | `candidate` already bound at `:104` and read at `:117-133` |
| `application/use_cases/promote_baseline.py` | `:161` | a new parameter from its only caller (Decision 5) |
| `application/use_cases/decide_approval.py` | `:140` | `check.candidate`, surfaced by Decision 2 |
| `api/routers/approvals.py` | `:382` | `schedule_runs`, already injected at `:326` |

The pinning argument for a snapshot is weaker than it appears. `parameter_hash` and
`consequence_hash` are snapshotted **because they are derived over mutable inputs** that
`revalidate_binding:91` re-derives and compares. `evidence_refs` are not derived: they sit inside
an immutable, `canonical_hash`-sealed `schedule_version` row that
`approval_request.candidate_schedule_version_id` already FK-pins, so re-reading yields a
byte-identical tuple by construction. A snapshot would add a second copy that cannot diverge,
plus a migration, a contract field, an adapter round-trip, and a near-tautological drift test.

**Does not cover:** it does not make the stored audit row independently verifiable at read time.
Nothing re-checksums the copied tuple; its integrity rests on the immutability of the
`schedule_version` row and the FK pin, and **resolving each locator against its pinned
`scenario_version_id` is Story 4.5's AC3**, not this story's.

### Decision 2 — `revalidate_binding` loads the candidate BEFORE the expiry fork and surfaces it on `RevalidationV1`

The correction states that `revalidate_binding` "loads the full candidate on **every** decision
path, approve and reject alike." **That is true of approve, reject and stale, and false of
expired.** `decide_approval.py:73-74` returns `RevalidationV1("expired", ...)` and `get_candidate`
is not called until `:75`. Leaving it there would make an expired row's `()` mean *"the function
returned before looking"* — precisely the *assumed* absence Story 4.5's rewritten AC3 refuses
(`epics.md:1279`: *"asserted as absence rather than assumed"*).

Move the `get_candidate` call above the expiry check and add `candidate: Any` to
`RevalidationV1`, returned from **all three** constructions (`:74`, `:93`, `:94`).
`decide_approval` then reads `check.candidate` for its TX3 audit row at `:140` and passes it to
`promote_baseline` at `:113`. **One read, one source of truth, no second decision path** —
EAD-10's prohibition is on a second revalidation path, not on the shape of its result.

EAD-10's fork is preserved exactly: expiry is still evaluated first and still returns first; only
a side-effect-free read moves, which EAD-7 permits on any path. The cost is one extra
`get_candidate` on the expired path.

**Does not cover:** it does not change any outcome, any `expected`/`current` context, or the
order of the fork's arms. It does have one consequence worth stating rather than discovering: a
transactional read fault inside `get_candidate` can now surface on the **expired** path, where
before that path issued no read. Under EAD-10 and `revalidate_binding`'s own docstring
(*"Transactional/infrastructure read faults propagate as the second arm"*) that fault correctly
rolls the bundle back and leaves the binding `pending` for an honest retry — it is the specified
behaviour of the second arm, not a new failure mode.

### Decision 3 — The denial row carries the candidate the refused attempt TARGETED, never evidence it consulted

FR21 (`epics.md:65`) names *"denied"* among the consequential actions requiring authoritative
evidence, and NFR32 (`:137`) requires immutable evidence references unqualified, per row. The
denial row is populated. **This is settled by spec, not by preference.**

But the denial fires at the admission check in `approvals.py:367-383`, **before**
`revalidate_binding` runs, and `AuditEnvelopeV1` documents no "evidence consulted" semantics —
`audit_envelope.py:26-52` merely enumerates the field. Without the distinction stated, a
populated denial row reads as a false consultation claim. **State it in two places and only those
two:** a comment at the denial write site, and one sentence in `docs/API.md`'s existing denial
paragraph (`:575-578`). The references identify *what the refused attempt targeted*.

The denial site resolves the candidate through the **already-injected** `ScheduleRunRepository`
(`approvals.py:326`) keyed on `denied.schedule_run_id`, which is non-nullable on
`ApprovalBindingV1` (`approval_binding.py:35`). `get_candidate` returns `ScheduleVersionV1 | None`,
so the expression is `candidate.evidence_refs if candidate is not None else ()` — a stale binding
whose candidate is gone writes honest absence.

**Does not cover:** it does not add a "consulted vs targeted" discriminant to `AuditEnvelopeV1`
or to any provenance item. The distinction is documentation and a comment; nothing in the data
distinguishes a targeted reference from a consulted one, and no consumer may infer one.

### Decision 4 — The load-bearing invariant is IDENTITY with the candidate's tuple, not non-emptiness

A resolved candidate can legitimately carry **zero** evidence references. `_input_evidence`
(`create_run_snapshot.py:34-55`) derives the snapshot's refs from `proposal.resolved_entities`
plus `proposal.preserved_locks`; a proposal with neither produces `()`,
`finalize_schedule_run.py:81-83` stamps an empty tuple, and the candidate is still valid and
promotable. AC1's two named cases are therefore not exhaustive, and:

* The assertion that carries the guarantee is
  **`audit_row.evidence_refs == candidate.evidence_refs`** — identity with the sealed row, which
  fails the moment a write site reverts to `()`.
* A **non-empty** assertion is valid only against a fixture whose proposal carries resolved
  entities, and every test making one must construct that fixture explicitly rather than inherit
  it. A non-empty assertion over an inherited fixture asserts a property of the fixture, not of
  the code — the "guard that cannot fail" defect class in its mirror image.

**Does not cover:** it does not guarantee that any production audit row is non-empty. A run whose
proposal touched no resolved entity and preserved no lock produces an empty candidate tuple and
therefore an empty audit tuple, which is honest and correct. Story 4.5's AC3 must not assert
non-empty unconditionally either; its wording (*"each audit row for an attempt that **resolved a
candidate** carries that candidate's checksum-bound references"*) already accommodates this, and
this story must not tighten it.

### Decision 5 — `promote_baseline` takes the candidate as a parameter and never acquires a repository

`promote_baseline` has exactly two callers in the repository: `decide_approval.py:113` and
`tests/test_promote_baseline.py:51`. The production caller has just revalidated and therefore
holds `check.candidate` (Decision 2). Add `candidate: Any` as a keyword-only parameter and use it
at `:161`. **Do not give TX2 a `schedule_runs` port** — AC2 forbids it, and a second read inside
the bundle could observe a different row than the one revalidation validated.

**Does not cover:** it does not make `promote_baseline` verify the candidate it is handed.
Nothing inside TX2 re-reads or re-checks it; the caller is responsible for passing the candidate
revalidation just resolved, and the `AssertionError` precondition at `:118-119` remains the only
check.

### Decision 6 — The JSONB round-trip goes live here for the first time; prove it against real PostgreSQL

`PostgresAuditWriter.append` serializes with a **bare** `TypeAdapter(tuple).dump_python(..., mode="json")`
(`adapters/postgres/audit.py:42`) — items typed `Any`, serialization inferred — and
`PostgresAuditReader._envelope` rehydrates with the typed
`TypeAdapter(tuple[EvidenceRefV1, ...]).validate_python` (`:26`). **That path has never carried a
non-empty tuple**, in production or in any test, because every write site passed `()`.

Verified at story creation against the installed pydantic: a fully-populated `EvidenceRefV1`
round-trips losslessly through the bare-tuple dump and the typed validate — all twelve fields
survive, `scenario_version_id` goes `UUID → str → UUID`, and the reconstructed tuple compares
equal. That is an in-process check; **prove it through real JSONB** in the
`@pytest.mark.postgres` file (Task 6), because the in-process check never touches the column.

**Does not cover:** it does not tighten the writer's `TypeAdapter(tuple)` to the typed form.
Considered and rejected: the round-trip is verified lossless, `worker_facts` on the same
statement uses the same inferred shape, and changing a serializer on an append-only table's write
path risks changing stored bytes for a type annotation and no behavioural gain.

### Decision 7 — There are exactly four audit write sites, and `grounding/gate.py:175` is not a fifth

A repository-wide grep for `evidence_refs=()` in `backend/` returns six hits. Two are **not**
audit write sites and must not be touched:

* `application/grounding/gate.py:175` constructs a `GroundedClaimV1` — the supported-zero claim
  path, a different contract with its own evidence semantics (Story 2.7).
* `application/queries/decision_provenance.py:48` is the `_common` helper's **default parameter**
  in the read-side projection Story 4.4 ships. It is not a write.

The four to change are exactly the rows in Decision 1's table.

**Does not cover:** it does not audit the rest of the codebase for other empty-evidence
constructions. Two names were checked and excluded; nothing else was surveyed.

### Decision 8 — AC4 closes the ledger and removes the scope control, and one existing test is the guard

`SCOPE_CONTROLS` (`application/contracts/decision_provenance.py:13-19`) loses its fifth member.
`backend/tests/test_decision_provenance.py:96-102` asserts `set(SCOPE_CONTROLS)` equals an exact
five-member set, so **it fails the moment the member is removed** — it is a real guard, not
scenery, and updating it to the four-member set is part of the same change.

`deferred-work.md`'s entry (`:590-608`) already carries its **DECIDED 2026-09-01** paragraph
naming this story as the closer. Strike the original bullet through and mark it **CLOSED**,
citing this story, per the correction's success criterion 3. Do **not** rewrite the historical
wording — the corrections it already carries are the record.

**Does not cover:** it does not close Story 4.4's other three ledger entries (the absent tool
transcript, the unimplemented `comparison` discriminant, the silent 10,000-item provenance cap).
All three keep their own owners and triggers.

---

## Tasks / Subtasks

- [ ] **Task 1 — Re-derive the baselines before touching anything (retro §3)**
  - [ ] Record backend total collected/selected/passed/failed/skipped/deselected, `-m postgres`
        collected **and actually ran**, Vitest files and tests, and the Playwright count, at
        `8ebc34f`, **before any edit**.
  - [ ] Story 4.4's post-review Completion Notes record backend 1,453 collected / 1,446 selected,
        1,444 passed, 2 skipped, 0 failed, 7 deselected; `-m postgres` 131 ran / 131 passed;
        Vitest 581 in 84 files; Playwright 66; `npx tsc -b` clean. **These are inherited, not
        verified** — 2.7, 2.8, 3.12 and 4.4 each found an inherited baseline stale. Record the
        total alongside the split.
  - [ ] Bring `docker-compose.yml`'s `postgres` service up first and assert on the **count** of
        postgres-marked tests that ran, never on the suite being green (Trap 6).

- [ ] **Task 2 — Surface the candidate on the revalidation result (AC: 1, 2; Decision 2)**
  - [ ] Add `candidate: Any` to `RevalidationV1` (`decide_approval.py:43-47`).
  - [ ] Move the `get_candidate` call above the expiry check and return the candidate from all
        three `RevalidationV1` constructions (`:74`, `:93`, `:94`), per Decision 2.
  - [ ] **Demonstrated-red:** with the read left below the expiry check, assert that an expired
        decision's audit row carries the candidate's references **while that candidate resolves in
        the same transaction** — observe the test fail, then move the read and observe it pass.
        Record it. This is the assertion Decision 2 exists for; a test that exercises only the
        approve path cannot fail here.

- [ ] **Task 3 — The four write sites (AC: 1, 2, 3; Decisions 1, 3, 5, 7)**
  - [ ] `request_approval.py:153` — use the `candidate` already bound at `:104`.
  - [ ] `decide_approval.py:140` — use `check.candidate`, with the
        `candidate.evidence_refs if candidate is not None else ()` shape per Decision 3.
  - [ ] `promote_baseline.py:104, :161` — add the keyword-only `candidate` parameter and use it;
        pass it from `decide_approval.py:113`, per Decision 5. **No `schedule_runs` port on TX2.**
  - [ ] `approvals.py:382` — resolve through the already-injected `schedule_runs`, keyed on
        `denied.schedule_run_id`, and add the comment Decision 3 requires stating that the
        references identify what the refused attempt **targeted**, not what it consulted.
  - [ ] Change nothing at `grounding/gate.py:175` or `queries/decision_provenance.py:48`
        (Decision 7).

- [ ] **Task 4 — Remove the scope control and close the ledger (AC: 4; Decision 8)**
  - [ ] Remove `"audit_evidence_refs:empty_at_every_write_site"` from `SCOPE_CONTROLS`
        (`contracts/decision_provenance.py:18`).
  - [ ] Update the set assertion at `tests/test_decision_provenance.py:96-102` to four members.
  - [ ] Strike through the `deferred-work.md:590` bullet and mark it **CLOSED**, citing this
        story. Leave its historical wording and its **DECIDED 2026-09-01** paragraph intact.

- [ ] **Task 5 — Default-suite tests for all four sites (AC: 1, 2; Decisions 4, 5)**
  - [ ] Fake-port tests in `tests/test_request_approval.py`, `tests/test_decide_approval.py` and
        `tests/test_promote_baseline.py`: for each site assert
        `audit_row.evidence_refs == candidate.evidence_refs` against a candidate fixture built
        with at least one `EvidenceRefV1`, per Decision 4. Update `test_promote_baseline.py:51`'s
        `_promote` helper for the new parameter.
  - [ ] Router test in `tests/test_approvals_api.py` for the denial row: a pre-write
        `approval_not_pending` or `stale_resource_version` refusal against a binding whose
        candidate resolves writes a denial row carrying that candidate's references.
  - [ ] The honest-absence direction, on its own fixture: a site whose `get_candidate` returns
        `None` writes `()`. Assert the empty set **and** that the candidate genuinely does not
        resolve, so the test cannot pass for the wrong reason.
  - [ ] **Demonstrated-red for every new assertion:** revert each write site to `()` in turn and
        observe the matching test fail. Record each (Trap 5).
  - [ ] Do **not** add a non-empty assertion over an inherited fixture (Decision 4).

- [ ] **Task 6 — Real-PostgreSQL round-trip proof (AC: 1; Decision 6)**
  - [ ] In `tests/test_approval_governance_postgres.py` (`@pytest.mark.postgres`), drive a full
        request → run → approve → promote cycle whose candidate carries at least one populated
        `EvidenceRefV1`, then read the rows back through `PostgresAuditReader` and assert the
        rehydrated tuples equal the candidate's, field for field including `scenario_version_id`,
        `producing_run_version`, and the checksum triple.
  - [ ] This is the first non-empty traversal of `audit.py:42` → JSONB → `audit.py:26`
        (Decision 6). Assert on the reconstructed `EvidenceRefV1` objects, not on raw JSON.
  - [ ] No backfill of existing rows — audit is append-only (NFR33) and AC1 forbids it.

- [ ] **Task 7 — Provenance and rendering coverage (AC: 3)**
  - [ ] Backend: assert that `query_decision_provenance` emits `audit_record` and
        `baseline_promotion` items carrying the populated references
        (`queries/decision_provenance.py:251`, `:266`) — the two lines the correction identified
        as the dead half. **No change to the query module is expected**; if one seems necessary,
        stop, because it means a write site is wrong (Trap 9).
  - [ ] Frontend: extend `ProvenanceTimeline.test.tsx` to assert an `audit_record` item with
        references renders its evidence links. **No component change is expected** —
        `ProvenanceTimeline.tsx:109` already renders `item.evidence_refs` for every item type.
  - [ ] Give the `audit_record` item in `frontend/e2e/support/apiStubs.ts:216-233` one populated
        reference so the existing accessibility sweep covers the newly-rendered links; re-run
        Playwright and confirm no page-level horizontal scroll and no new axe finding
        (NFR20, `EXPERIENCE.md:196`).

- [ ] **Task 8 — Documentation (AC: 3)**
  - [ ] `docs/API.md`: extend the existing denial paragraph (`:575-578`) with the one sentence
        Decision 3 requires. No new route, no new problem code, no new table row.
  - [ ] `docs/GATE-A-RUNBOOK.md` and `docs/DOMAIN-MODEL.md`: no change expected — verify, do not
        assume.
  - [ ] **No evidence file.** This story has no measured threshold, so
        `docs/EVIDENCE-CONVENTION.md` has nothing to bind. Say so in Completion Notes.

- [ ] **Task 9 — Full verification**
  - [ ] Backend suite, `-m postgres` suite, `npx tsc -b`, `npm run lint`, `npm test`, Playwright,
        Alembic check, and the architecture/changed-surface tests.
  - [ ] **Alembic must report no upgrade operations** — AC2's "no migration" is proven by that
        check, not by inspection. Confirm `backend/alembic/versions/` gains zero files.
  - [ ] `npx tsc -b` is what actually type-checks the tree; `npm run typecheck` is inert because
        the root `tsconfig.json` declares `"files": []` (Trap 7).
  - [ ] **`npm run codegen` is not expected to change anything** — this story publishes no new or
        widened API field. If `openapi.json` or `schema.d.ts` changes, a contract widened by
        accident; stop and find it.
  - [ ] Report totals against Task 1's re-derived baselines, not against 4.4's recorded numbers.

---

## Dev Notes

### Files being modified — read these before editing

| File | Current state | What this story changes | What must not break |
|---|---|---|---|
| `backend/application/use_cases/decide_approval.py` | `RevalidationV1` has 3 fields `:43-47`; `revalidate_binding` returns at `:74` **before** the `get_candidate` at `:75`; three `RevalidationV1` constructions `:74`, `:93`, `:94`; TX3 audit `:140`; calls `promote_baseline` `:113` | `candidate` field on `RevalidationV1`; the read moves above the expiry check; `:140` and `:113` consume it | the EAD-10 fork's arm **order and outcomes** — expiry still evaluated and returned first; the `valid` conjunction at `:91`; the `stale` context dict at `:94`; the three-way error hierarchy (`ApprovalNotPendingError` / `PostWriteApprovalNotPendingError` / `ConcurrentDecisionError`) the router discriminates by **type**, never by code (`approvals.py:347-365`) |
| `backend/application/use_cases/promote_baseline.py` | signature `:104-116`; TX2 audit `:161`; no `schedule_runs` port | one keyword-only `candidate` parameter; `:161` uses it | the module docstring's raise-vs-return contract `:1-45` — every post-write failure must still **escape** so the bundle rolls back; the `AssertionError` precondition `:118-119`; the `PromotionResultV1` shape |
| `backend/application/use_cases/request_approval.py` | `candidate` bound `:104`, guarded `:105-106`, read `:117-133`; TX1 audit `:153` | `:153` uses `candidate.evidence_refs` | the `effect_key` being `command.request_effect_key` and **not** `str(approval_id)` — 4.1's audit defect, reasoned at `:145-149`; the `CandidateNotPromotableError` guard order |
| `backend/api/routers/approvals.py` | `decide_approval_route` `:326` already injects `schedule_runs`; denial arm `:347-383` discriminates by exception **type**; `evidence_refs=()` `:382` | `:382` resolves through `schedule_runs`; one comment added | the type-based discrimination and the `PostWriteApprovalNotPendingError` re-raise at `:348-349`; the denial arm running **before** any `_store_idempotent_result`; `_ERROR_STATUS` / `_DECISION_DETAIL`; the provenance route's registration above `/{approval_id}` |
| `backend/application/contracts/decision_provenance.py` | `SCOPE_CONTROLS` has five members `:13-19` | fifth member removed | the other four members and the nine item dataclasses; `ProvenanceCommonV1`'s **field order**, asserted at `tests/test_decision_provenance.py:88-95` |
| `backend/adapters/postgres/audit.py` | writer dumps with bare `TypeAdapter(tuple)` `:42`; reader rehydrates with `TypeAdapter(tuple[EvidenceRefV1, ...])` `:26` | **nothing** — it goes live unchanged (Decision 6) | both coercions exactly as written; the reader's explicit `site_id` predicate `:52`; the absence of any update or delete method |
| `backend/tests/test_decision_provenance.py` | five-member `SCOPE_CONTROLS` set assertion `:96-102` | four-member set | the `ProvenanceCommonV1` field-order assertion `:88-95` and the discriminator assertion `:104` |
| `backend/tests/test_promote_baseline.py` | `_promote` helper calls `promote_baseline` `:49-56` | one argument | `_tx`'s fault-injection arms (`fail_at="audit"` / `"event"`), which prove TX2's rollback contract |
| `docs/API.md` | denial paragraph `:575-578`; provenance route `:527-533` | one sentence in the denial paragraph | every existing row and code — 4.3's review found a documented code on a route that could not emit it |
| `frontend/e2e/support/apiStubs.ts` | provenance stub `:216-233`, every item `evidence_refs: []` | one populated reference on the `audit_record` item | the other two items and the deliberately long identifier at `:230`, which is what the no-horizontal-scroll assertion exercises |

### Traps

1. **`revalidate_binding` does NOT load the candidate on the expired path.** It returns at
   `:73-74`, two lines before the `get_candidate` at `:75`. The correction's summary says "every
   decision path"; the code says otherwise. Decision 2 — and Task 2's demonstrated-red is the
   only test that catches it.
2. **A resolved candidate can carry zero evidence references.** `_input_evidence`
   (`create_run_snapshot.py:34-55`) derives them from `proposal.resolved_entities` plus
   `preserved_locks`; neither is guaranteed. Decision 4 — assert **identity**, and build any
   non-empty fixture explicitly.
3. **TX2 must not acquire a `schedule_runs` port.** AC2 forbids it by name, and a second read
   inside the bundle could observe a different row than the one revalidation validated.
   Decision 5.
4. **The denial row is a pre-write refusal.** It commits precisely because nothing was written
   (`decide_approval.py:100-104`; `approvals.py:347-383`). Do not move it, do not make it
   conditional on revalidation, and do not let the new `get_candidate` call raise past it — a
   read fault there converts a clean 409 into a rolled-back request.
5. **A guard that cannot fail is this epic's most-repeated defect.** 4.1's review found two,
   4.2's a third, 4.3's several, 4.4's a fourth — an import guard blind to `from X import Y`.
   Every assertion added in Tasks 2, 5, 6 and 7 carries an explicit demonstrated-red; a passing
   test with no recorded red does not count (EAD-9; spine *Verification Obligations* `:212`).
6. **A down PostgreSQL makes Task 6's proof pass by skipping.** `conftest.py:66` calls
   `pytest.skip` when the admin connection fails — deliberately, so the suite does not hang. With
   Docker down, `pytest` reports green while the round-trip never executed. Assert on the
   **count** of postgres-marked tests that ran.
7. **`npm run typecheck` is inert.** The root `tsconfig.json` declares `"files": []`;
   `npx tsc -b` is what actually type-checks (Story 4.3 Trap 13, 4.4 Trap 12).
8. **The consequence summary is hashed and is a contract.** Nothing in this story touches it — but
   the write sites being edited sit beside it. Any edit to `consequence_summary` text changes
   `consequence_hash` and marks every live pending binding `stale` at revalidation. 4.1 Trap 7,
   4.2 Trap 6, 4.3 Trap 14, 4.4 Trap 13 all said this.
9. **Provenance must need no change.** `queries/decision_provenance.py:251` and `:266` already
   pass `evidence_refs=audit.evidence_refs` straight through. If the projection appears to need
   editing to show the new references, a write site is wrong — fix the write site.

### Honest gaps this story ships with — state them in Completion Notes

- **The copied references are not independently verified at write time.** Nothing re-checksums
  them; integrity rests on the `schedule_version` row's immutability and the FK pin. Resolving
  each locator against its pinned `scenario_version_id` is **Story 4.5's AC3**. Decision 1.
- **A production audit row can still be legitimately empty** — a proposal that resolved no entity
  and preserved no lock produces an empty candidate tuple. Decision 4.
- **Nothing distinguishes a targeted reference from a consulted one in the data.** The distinction
  is a comment and one documentation sentence; no contract field encodes it. Decision 3.
- **A write fault inside TX2 still writes no audit row** (Story 4.3's gap, Owner: 4.5), so a
  rolled-back promotion attempt remains invisible to provenance and carries no references.
  Inherited, not introduced.
- **`producing_run_version` is `None` on grounding-calculator evidence** (`calculators.py:142`)
  and set only on candidate evidence (`finalize_schedule_run.py:82`). Audit rows take the
  candidate supply, so they carry it; claim-side evidence still does not. Pre-existing.

### Testing requirements

- Backend tests in `backend/tests/`, `test_*.py`, never co-located. PostgreSQL-dependent tests
  carry `@pytest.mark.postgres` (`pyproject.toml:52`).
- Keep the epic's three-file split: fake-port **use-case** tests beside each use case's existing
  file; **router/HTTP-contract** tests in `test_approvals_api.py`; **real-PostgreSQL** tests in
  `test_approval_governance_postgres.py`.
- Assertions that live **only** in the `@pytest.mark.postgres` file are deselected from the
  default suite — Story 4.3's review caught exactly that. Every behavioural claim in AC1 needs a
  default-suite assertion; the PostgreSQL file proves the **JSONB round-trip** (Task 6), which
  genuinely needs a real column.
- Frontend tests co-located, Vitest + Testing Library; assert accessible names and roles, not
  class names.
- Accessibility is proven by automated coverage alone (`EXPERIENCE.md:196`).
- Every new guard needs a recorded demonstrated-red.

### Project structure notes

**No new files in `backend/` or `frontend/src/`.** Every change is an edit to a file that already
exists, listed in the table above. `backend/alembic/versions/` gains **zero** files — Task 9's
Alembic check is what proves it.

The one structural addition is a field on `RevalidationV1`, which lives in
`application/use_cases/decide_approval.py`. It is a use-case-local dataclass: never persisted,
never serialized, and absent from `api/schemas.py`. Adding to it is not a contract change, and it
is explicitly **not** the `ApprovalBindingV1` field AC2 forbids.

### Open questions — neither blocks this story

1. **Should the audit row's references be re-resolved at read time?** Story 4.5's AC3 resolves
   each locator through the evidence-locator contract and reports `resolved` / `not_found` /
   `version_mismatch`. Whether that resolution belongs in the provenance projection or only in
   4.5's proof harness is 4.5's to decide. Do not pre-empt it here — adding resolution to the
   projection would put a fallible call inside the read Story 4.4's AC3 requires to survive
   outages.
2. **Carried forward from 4.1–4.4, still unanswered:** should a decision pin the *scenario*
   version as well as the binding's resource version? Populating audit evidence makes the
   scenario version visible on a second surface but does not settle it. No story is blocked on it.

### References

- Correction: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-09-01.md` — both
  vacuities, the rejected `ApprovalBindingV1` snapshot, its Decisions 1–3, the two precisions,
  and the five success criteria
- Epic and requirements: `_bmad-output/planning-artifacts/epics.md` — Story 4.4a `:1258-1284`,
  Story 4.5 *Evidence scope note* `:1292` and AC3 `:1276-1279`, FR20 `:63`, FR21 `:65`,
  NFR20 `:113`, NFR32 `:137`, NFR33 `:139`, AR12 `:158`, AR23 `:169`, Story 6.2 `:1463`
- Epic 4 spine:
  `_bmad-output/planning-artifacts/architecture/architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md`
  — EAD-1, EAD-7 (**reads never write**), EAD-9 (**named supplier or declared gap**, `:101`),
  EAD-10 (**one revalidation fork**, `:110`), EAD-11, *Verification Obligations* `:212`
- Parent spine: `.../architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` — AD-1 `:48`,
  AD-2 `:54`, AD-3, AD-12, AD-13
- Previous story: `_bmad-output/implementation-artifacts/4-4-inspect-complete-decision-provenance.md`
  — its Decision 6 (identifier slots), Decision 8 (declared absence), its **Review Findings**
  (especially the guard that could not fail), Traps 8, 14, 15, and *Open questions for Winston*
  Q1, which this story answers
- Ledger: `_bmad-output/implementation-artifacts/deferred-work.md:590-608` — the entry this story
  closes, with its **DECIDED 2026-09-01** paragraph
- Domain: `docs/DOMAIN-MODEL.md` §1 (family/unit), §2 (what an assignment carries), §5
  (checklist) — this story reads no field inside an evidence reference; see the note under
  *Facts* above
- Conventions: `docs/API.md:575-578`, `docs/EVIDENCE-CONVENTION.md`, `docs/TESTING.md`,
  `docs/GATE-A-RUNBOOK.md`
- Process: `_bmad-output/implementation-artifacts/epic-3-retro-2026-08-27.md` §1, §3;
  `epic-1-2-retro-2026-08-16.md` §3.2 (A1), §6.1 (A3)

---

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

---

## Change Log

| Date | Change |
|---|---|
| 2026-09-01 | Story created from `epics.md:1258-1284`, `sprint-change-proposal-2026-09-01.md`, the Epic 4 spine (EAD-7, EAD-9, EAD-10), Story 4.4's Dev Notes, Review Findings and Open Question 1, and a live audit of the codebase at `8ebc34f`. |
