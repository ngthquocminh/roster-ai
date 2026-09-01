# Sprint Change Proposal — Story 4.5 AC3 Cannot Be Proven As Written

- **Date:** 2026-09-01
- **Project:** ShiftMind
- **Raised by:** Minh
- **Workflow:** `bmad-correct-course` (incremental mode)
- **Codebase state at analysis:** `a8412b2` (Story 4.4 merged), backend sources clean
- **Scope classification:** **Moderate** — backlog reorganization (one inserted story, one AC rewrite). No PRD change, no architecture change, no rollback.

---

## 1. Issue Summary

Story 4.5's AC3 (`epics.md:1276-1279`) cannot be proven as written. It carries **two independent vacuities**, both verified against the code.

### Vacuity 1 — the object-storage premise has no subject

AC3 requires proof against *"the local create-only evidence adapter"*, with failure modes around *"object-storage evidence failure"* and *"a non-authoritative unreferenced object"*.

No such subject exists:

- `backend/application/ports/` holds 12 ports; none is an evidence or object-storage port.
- `backend/adapters/` holds `cognito`, `oidc`, `postgres`. Nothing else.
- A case-insensitive search for `s3`, `object_storage`, `ObjectStore`, `EvidenceWriter`, and `EvidenceStore` across `application/` and `adapters/` returns **zero hits**.

In this codebase evidence is a **version-bound projection locator**, not a stored object: `EvidenceRefV1` (`application/contracts/evidence_ref.py:31-43`) is `scenario_version_id` plus a checksum triple plus `group`/`record_id`/`field`/minute-range. It has no URI, no key, no bucket.

AR12 (`epics.md:158`) and AR23 (`epics.md:169`) do name *"checksummed create-only S3 evidence"* and *"create-only versioned S3 evidence permissions"* — but as **hosted-deployment** requirements. They are already owned by **Story 6.2** (`epics.md:1463`: *"S3 application roles cannot delete or overwrite evidence objects. (AR23)"*). AC3 duplicated a hosted requirement into a local proof story.

**This is a second-order failure.** `sprint-change-proposal-2026-08-09-epics-2-5.md:149` already corrected this same AC once: *"AC3 restated from S3-specific to the object-storage evidence adapter, provable locally. Removes an accidental Epic 4 → Epic 5 dependency."* That correction removed the **hosted** dependency but preserved the **object-storage premise** without checking that a subject for it existed. Softening the premise a third time would repeat the error; the premise must be removed.

### Vacuity 2 — the third clause is unfalsifiable on its audit half

AC3's *"no audit or provenance link points to unverified evidence"* cannot fail, because `audit_event.evidence_refs` is a literal empty tuple at **all four** production write sites:

| Write site | Line |
|---|---|
| `application/use_cases/request_approval.py` | `:153` |
| `application/use_cases/decide_approval.py` | `:140` |
| `application/use_cases/promote_baseline.py` | `:161` |
| `api/routers/approvals.py` | `:382` |

`AuditEnvelopeV1.evidence_refs` (`application/contracts/audit_envelope.py:50`) has **no default**, so each site passes `()` explicitly — a decision repeated four times, not an oversight. The column is `nullable=False` JSONB.

**Precision — it is half vacuous, not wholly.** `application/queries/decision_provenance.py:127` already sets `evidence_refs=candidate_refs` from the candidate schedule version: non-empty and checksum-bound. It is `:251` and `:266`, the **audit-sourced** items, that replay the empty tuple. *"No provenance link points to unverified evidence"* is therefore already a live, falsifiable assertion; only the audit half is dead.

### The supplier already exists

`finalize_schedule_run.py:81-83` stamps `producing_run_version` onto each ref, and the full `ScheduleVersionV1` is persisted to `schedule_version.payload` as JSONB (`adapters/postgres/schedule_run.py:1082`) under `canonical_hash` with `checksum_algorithm='sha256'` and `checksum_schema_version='rfc8785-v1'`. The row is immutable and FK-pinned by `approval_request.candidate_schedule_version_id`.

### It was foreseen

Story 4.4 recorded this as a declared gap — `SCOPE_CONTROLS[4] = "audit_evidence_refs:empty_at_every_write_site"` (`application/contracts/decision_provenance.py:18`) — with the ledger entry at `deferred-work.md:590-595` naming the trigger explicitly: *"Owner/revisit trigger: decide before Story 4.5 is created, because 4.5 AC3 must not prove evidence integrity vacuously against a structurally empty audit field."* **This proposal is that trigger firing on time.**

---

## 2. Impact Analysis

### Epic impact

| Epic | Impact |
|---|---|
| **Epic 4** | Completes as planned. One story inserted (4.4a), one AC rewritten (4.5 AC3). 4.1–4.4 ship correct code — nothing built is wrong. |
| **Epic 6** | None. Story 6.2 already owns the S3 half; AC3 now cites it instead of duplicating it. |
| **Epics 1–3, 5** | None. |

**No rollback candidate exists.** Checklist option 4.2 evaluated and rejected: the defect is in an unwritten story's acceptance criteria, not in shipped code.

### Story impact

- **Story 4.5** — AC3 replaced. AC1, AC2, AC4 untouched. Remains a pure proof story.
- **Story 4.4a** (new) — carries the write-path change so 4.5 does not author both mechanism and oracle.
- **Story 4.6** — no AC change, but its state matrix must expect evidence links to appear on audit-sourced Provenance items once 4.4a lands.
- **Stories 4.1–4.4** — no change. Story 4.4's `SCOPE_CONTROLS` loses its fifth member when 4.4a lands, by 4.4a's own AC4.

### Artifact conflicts

| Artifact | Conflict |
|---|---|
| PRD + addendum | **None** |
| `ARCHITECTURE-SPINE.md` (root and Epic 4) | **None** — no spine invariant names an evidence adapter |
| `EXPERIENCE.md` / `DESIGN.md` | **None** |
| `docs/DOMAIN-MODEL.md` | **None** — no demand family/unit dimension involved |
| `docs/GATE-A-RUNBOOK.md` | **None** — no new Gate A write path |
| AR12 / AR23 (`epics.md:158`, `:169`) | **No edit** — both remain true as hosted requirements |
| `epics.md` | AC3 rewrite + Story 4.4a insertion |
| `sprint-status.yaml` | New story entry |
| `deferred-work.md` | Entry re-pointed |

### Technical impact

Four files change in implementation, no schema change:

```
request_approval.py:153      evidence_refs=() -> candidate.evidence_refs
decide_approval.py:68        RevalidationV1 surfaces the candidate it already loads at :75
decide_approval.py:113       promote_baseline(..., candidate=...)
promote_baseline.py:104,161  signature gains candidate; audit row uses it
approvals.py:382             denial row reads via the already-injected ScheduleRunRepository
decision_provenance.py:18    SCOPE_CONTROLS[4] removed
```

**No migration. No new column. No new port. No new contract field.**

---

## 3. Recommended Approach

**Direct Adjustment** (checklist option 4.1). Effort: **Low**. Risk: **Low**.

Options 4.2 (rollback) and 4.3 (MVP review) were both evaluated and rejected — nothing shipped is wrong, and MVP scope is unchanged.

### Three decisions taken

**Decision 1 — mechanism: supply from the candidate at each write site.**

The trigger proposed snapshotting `evidence_refs` onto `ApprovalBindingV1` at request time, mirroring `parameter_hash`/`consequence_hash`. **Rejected as heavier than the code requires.** Three of the four sites already hold the candidate:

- `request_approval.py:104` already binds `candidate = schedule_runs.get_candidate(...)` and reads `.scenario_version_id`/`.assignments` at `:117-133`. One-line change.
- `revalidate_binding` (`decide_approval.py:75`) already loads the full candidate on **every** decision path, approve and reject alike, then discards it.
- `promote_baseline` (`:104-116`) has no `schedule_runs` port, but its **only** caller is `decide_approval.py:113`, which just revalidated. One passed parameter.
- The denial site needs no new dependency either: `decide_approval_route` already injects `ScheduleRunRepository` (`approvals.py:327`).

The pinning argument for a snapshot is weaker than it appears. `parameter_hash`/`consequence_hash` are snapshotted because they are **derived over mutable inputs** that `revalidate_binding:91` re-derives and compares. `evidence_refs` are not derived — they sit inside an immutable, `canonical_hash`-sealed `schedule_version` row that `candidate_schedule_version_id` already FK-pins. Re-reading yields a byte-identical tuple by construction, so a snapshot adds a second copy that cannot diverge, plus a migration, a contract field, an adapter round-trip, and a near-tautological drift test.

**Decision 2 — the denial row is populated too. Settled by spec, not preference.**

FR21 (`epics.md:65`) names *"successful, **denied**, stale, failed, and cancelled"* consequential actions. NFR32 (`:137`) requires audit to capture *"immutable evidence references"* unqualified, per row. Two precisions the carrier story must state:

1. `get_candidate` returns `ScheduleVersionV1 | None`, so the expression is `candidate.evidence_refs if candidate is not None else ()`. That residual `()` is **honest absence** (a stale binding whose candidate is gone), and AC3 must not assert non-empty on denial rows unconditionally.
2. `AuditEnvelopeV1` documents no "evidence *consulted*" semantics (`audit_envelope.py:1-15` merely enumerates the field), and the denial fires at the admission check *before* `revalidate_binding` runs. The refs identify **what the refused attempt targeted**, not what it consulted. Without this stated, the denial row reads as a false consultation claim.

**Decision 3 — the carrier is numbered 4.4a, not 4.5-with-renumbering.**

Renumbering would falsify *"4.5–4.6"* in nine places across seven **already-shipped** story files — including Story 2.2's `Unblocks:` contract (`2-2-...md:21`) and four verbatim quotes of the NFR28 Gate-B floor rationale (`2-2`, `2-9`, `3-1`, `3-10`). Editing them rewrites history; leaving them makes them wrong. Both conflict with the Epic 3 retro action item *"Reconcile sprint status and deferred-work wording with current code without erasing historical context."* A suffix falsifies zero frozen references.

**Carrier separate from 4.5 — validated as proposed.** 4.5 is a proof story; a story that authors both the mechanism and its oracle cannot fail. This is the pattern `.claude/CLAUDE.md` already warns about from Story 2.7.

---

## 4. Detailed Change Proposals

### 4.1 — `epics.md:1276-1279`, Story 4.5 AC3

**OLD**

```
**Given** object-storage evidence failure before snapshot metadata commits, or database failure after an object write
**When** promotion evidence is prepared
**Then** storage failure causes no mutation, while database failure leaves only a non-authoritative unreferenced object retained until teardown
**And** no audit or provenance link points to unverified evidence, proven against the local create-only evidence adapter without requiring hosted infrastructure. (AR12, AR23)
```

**NEW**

```
**Given** promoted, rejected, expired, stale, and denied decisions, plus an evidence locator whose pinned scenario version no longer resolves
**When** each audit event and provenance item for those decisions is resolved through the evidence locator contract
**Then** every EvidenceRefV1 resolves `resolved` against its pinned scenario_version_id, or reports `not_found` or `version_mismatch` explicitly, and no record presents an unresolvable locator as valid
**And** each audit row for an attempt that resolved a candidate carries that candidate's checksum-bound references, while a row whose candidate is absent carries an empty set asserted as absence rather than assumed. (AR12, AR23)
```

**Plus a scope note under the Story 4.5 heading (`epics.md:1258`):**

> **Evidence scope note.** In this codebase evidence is a version-bound projection locator (`EvidenceRefV1` — `scenario_version_id` plus the checksum triple plus a record locator), not a stored object; no evidence port and no object-storage adapter exists. AR12's and AR23's create-only S3 evidence permissions are hosted-deployment requirements discharged by **Story 6.2** (`epics.md:1463`), not by this proof story. The earlier restatement at `sprint-change-proposal-2026-08-09-epics-2-5.md:149` removed the *hosted* dependency but kept an object-storage premise that has no subject here; this AC removes the premise rather than softening it a third time.

**Rationale.** Both vacuities die. The first clause gains a real subject (`EvidenceRefV1` + `ResolutionOutcomeV1`, both shipped). The second becomes falsifiable once 4.4a lands, and its "asserted as absence rather than assumed" wording prevents the denial-row `()` being read as a regression. AR12/AR23 tags retained — the locator property genuinely serves both.

### 4.2 — `epics.md`, new Story 4.4a inserted at line 1257

```
### Story 4.4a: Supply Audit Evidence References [Technical Enabler]

As the product team,
we want every consequential audit row to carry the checksum-bound evidence locators of the
candidate its attempt targeted,
So that NFR32's evidence clause rests on a record that can actually fail, and Story 4.5 has a
real oracle rather than a structurally empty field.

**Acceptance Criteria:**

**Given** a consequential attempt that resolves a candidate schedule version — request, promotion,
terminal decision, or pre-write denial
**When** its audit event is written
**Then** the row carries that candidate's evidence references unchanged from the sealed
schedule_version row, with no re-derivation, no re-checksumming, and no backfill of any prior row
**And** an attempt whose candidate does not resolve writes an empty set, proven by a demonstrated-red
test rather than assumed. (FR21, NFR32)

**Given** the existing contracts and schema
**When** this story lands
**Then** no migration, no new column, no new port, and no new field on ApprovalBindingV1 is
introduced — the candidate is supplied from the get_candidate call that request_approval and
revalidate_binding already make, on the repository decide_approval_route already injects
**And** promote_baseline receives the candidate as a parameter from its only caller, never by
acquiring a repository of its own. (AD-1, AD-2)

**Given** a denial row written at the admission check, before revalidation runs
**When** its evidence references are read
**Then** they identify the candidate the refused attempt targeted, not evidence the attempt
consulted, and both the story and the code state that distinction
**And** audit-sourced provenance items render these references with the semantics Story 4.4 already
ships, without a new contract field. (FR20, NFR32)

**Given** the scope control declared by Story 4.4
**When** this story lands
**Then** "audit_evidence_refs:empty_at_every_write_site" is removed from SCOPE_CONTROLS in
application/contracts/decision_provenance.py, because it is no longer true
**And** the corresponding deferred-work ledger entry is closed in the same commit, citing this
story. (FR21, NFR32)
```

**Rationale.** Four falsifiable ACs. AC2 encodes Decision 1 as a **constraint**, forbidding the migration and the port by name so a dev agent cannot quietly reach for either — the `ApprovalBindingV1` snapshot is the more obvious design and is what the trigger itself proposed. AC1's second clause and AC3 pre-empt the two review findings this change would otherwise attract. AC4 makes closing the ledger part of done.

Marked `[Technical Enabler]` to match Story 1.5 *Resolve Exact Evidence Targets*, the closest analog.

### 4.3 — `sprint-status.yaml`, `development_status:`

Insert `4-4a-supply-audit-evidence-references: backlog` after `4-4-inspect-complete-decision-provenance: done`, preceded by a `# NOTE (2026-09-01):` block recording: the suffix rationale; both vacuities with their verifying evidence; the rejected `ApprovalBindingV1` snapshot and why; the spec basis for populating the denial row; the two precisions; and the expected visible consequence in the Provenance section.

**Rationale.** This file is where `bmad-create-story` reads its context. Without the note, a fresh reading of Epic 4 reaches for the snapshot design.

### 4.4 — `deferred-work.md:590-595`

Original bullet left **untouched** — its trigger fired exactly as written and is a true historical record. A `**DECIDED 2026-09-01**` paragraph is appended, re-pointing the owner to Story 4.4a and correcting two of the entry's own claims: that "provenance faithfully replays the empty tuple" is true only of the audit-sourced items, and that "populating it is a write-path decision" understated how cheap it is. Not marked `CLOSED` — nothing has changed in the code yet; 4.4a's AC4 closes it.

---

## 5. Implementation Handoff

**Scope: Moderate** — backlog reorganization, no strategic replan.

| Recipient | Responsibility |
|---|---|
| **Course-correct session (now)** | Apply edits 4.1–4.4 to `epics.md`, `sprint-status.yaml`, `deferred-work.md` |
| **`/bmad-create-story`** | Author `4-4a-supply-audit-evidence-references.md` from this proposal. Must carry Decisions 1–3 and both precisions verbatim, and re-derive test baselines at Task 1 |
| **`/bmad-dev-story`** | Implement 4.4a. Demonstrated-red required in both directions: a populated row for a resolved candidate, and an honest `()` for an absent one |
| **`/bmad-create-story` → 4.5** | Only after 4.4a is `done`. AC3's oracle does not exist until then |

### Success criteria

1. `epics.md:1276-1279` names no object store, and every noun in it resolves to a shipped type.
2. Story 4.4a lands with **zero** files under `backend/alembic/versions/`.
3. `SCOPE_CONTROLS` has four members; `deferred-work.md`'s entry is struck through and marked `CLOSED`.
4. A test asserts a promoted decision's audit row carries at least one ref resolving `resolved`, and **fails** if the write site reverts to `()`.
5. Story 4.5 is created only after 4.4a is `done`.

### Explicitly out of scope

- Any S3 or object-storage adapter — Story 6.2 owns it.
- Backfilling `evidence_refs` on existing audit rows — audit is append-only (NFR33); AC1 forbids it.
- Widening `audit_event.evidence_refs` beyond the candidate's own references.
- Epic 4's other declared gaps: the absent tool-call transcript (Epic 5), the `comparison` discriminant, the silent 10,000-item provenance cap.

### Retro action items partially served

- *"Reconcile sprint status and deferred-work wording with current code without erasing historical context"* — advanced, not closed.
- *"Require every Epic 4 contract or guard to name its production supplier or an explicit seeded proof and production gap before implementation"* — this correction is that requirement applied to 4.5's AC3 at planning time rather than at review.
