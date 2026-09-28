---
title: 'Site timezone, time-horizon text, and grounded-answer evidence UI polish'
type: 'bugfix'
created: '2026-09-28'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'f15be7011fb2b30106ef5ce4f2b260e4f3b205ce'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Three small but visible rough edges: (1) the site's timezone is
hardcoded to `Australia/Sydney`, a leftover foreign-client detail on an
anonymisation branch that should be Vietnam/Ho Chi Minh City; (2) the Scenario
Overview's "Time horizon" row reads as raw plumbing (`starts 2026-05-31 14:00,
10080 minutes`); (3) a grounded chat answer's evidence UI is functionally
correct but visually noisy — a `Verified: field: value` text label sits beside
a *separate* full-text Evidence link, and a claim backed by many rows (e.g.
`worker_count`) renders one link chip per row instead of one summary.

**Approach:** Change the one hardcoded timezone constant; add a small
deterministic formatter for the horizon row; and consolidate each supported
fact/single-ref claim's "Verified" text + evidence link into one compact
control (a small check icon + one evidence link). A claim backed by many rows
(e.g. `worker_count`) drops the per-row link list entirely and shows only a
check icon meaning "verified" — no link, since there is no one sensible record
to jump to.

## Boundaries & Constraints

**Always:**
- Every currently-supported claim/fact keeps a keyboard-focusable, self-describing
  evidence control (EXPERIENCE.md's accessibility floor) — consolidating the UI
  must not silently drop the group/record/field/version detail, only move it.
- `EvidenceRefV1`/`evidence_refs` stay exactly as computed today; this is a
  rendering change only, never a change to what the backend calculates or cites.
- Any new duration/range formatter stays deterministic (no `toLocaleString`/
  `Intl`/host-timezone reads) — `formatTimestamp.ts`'s existing comment explains
  why: jsdom tests must not become machine-dependent.
- Failed and `wording_flagged` fact states, and empty-evidence claim states,
  render exactly as they do today — only the SUPPORTED path's success
  indicator is being consolidated.

**Ask First:**
- If the "small green circle check" needs a genuinely new design token (not an
  ad-hoc Tailwind utility color, matching the existing ad-hoc `text-amber-700`
  pattern already used for `wording_flagged`), stop and ask before adding one.

**Never:**
- Do not add a `task_count` metric/tool or touch `application/grounding/**`'s
  metric vocabulary — deferred separately (see `deferred-work.md`, entry
  "quick-dev intent 'chat UI polish'").
- Do not localize displayed timestamps to the site timezone (keep showing the
  stored UTC wall-clock via `formatTimestamp`) — only the constant that
  interprets *fixture input* times changes, not how the UI displays computed
  UTC output.
- Do not change `worker_count`/`qualified_worker_count`'s backend evidence_refs
  shape (still one ref per row) — only how the frontend renders that list.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Horizon, exact days | `horizon_minutes=10080` | "2026-05-31 14:00 → 2026-06-07 14:00 (7 days)" | N/A |
| Horizon, non-day-aligned | `horizon_minutes=90` | Readable range with hours/minutes remainder, never raw "N minutes" alone | N/A |
| Single-ref supported claim/fact | 1 `evidence_ref` | One check icon + one evidence link; link's accessible name still names group/record/field/version | N/A |
| Multi-ref supported claim (e.g. `worker_count`, N=23) | 23 `evidence_refs` | One check icon only, no link (accessibly labelled "Verified", not merely decorative) — never 23 separate links | N/A |
| Zero-ref supported claim | 0 `evidence_refs` (empty-match case) | Unchanged: existing "No matching records" path, no check icon | N/A |
| Failed / wording-flagged fact | `verdict: "failed"` or `wording_flagged: true` | Unchanged rendering (destructive/amber text as today) | N/A |

</frozen-after-approval>

## Code Map

- `backend/adapters/postgres/scenario_projection.py:47` -- `SITE_TIMEZONE` constant; drives real fixture-local-time → UTC conversion via `_SITE_ZONE`/`_as_utc`. Only 4 real (non-vendored) references repo-wide; no test asserts an absolute UTC value derived from it (verified: `test_scenario_projection.py:182,462` hardcode `"Australia/Sydney"` as unrelated dataclass test literals, not the constant).
- `backend/scripts/export_contract_fixture.py` -- imports `SITE_TIMEZONE` by reference; regenerating its output was required (discovered during implementation, see Tasks).
- `data/contract/sample_tiny_input.projection-v1.json`, `data/contract/sample_tiny_input_more_tm.projection-v1.json` -- committed byte-pinned snapshots of the production projection functions' output (including `horizon_start`/`site_timezone`); `backend/tests/test_export_contract_fixture.py::test_committed_contract_fixtures_are_current_and_deterministic` diffs these against a fresh regen, so the `SITE_TIMEZONE` change required regenerating them via `export_contract_fixture.py`, not hand-editing.
- `frontend/src/lib/formatTimestamp.ts` -- existing deterministic UTC-slice formatter; add a sibling duration/range helper here or in a new co-located file, following its no-`Intl` convention.
- `frontend/src/features/scenario-data/groups/OverviewPanel.tsx:21` -- composes the "Time horizon" row string; swap in the new formatter.
- `frontend/src/components/primitives/EvidenceLink.tsx` -- existing evidence-link primitive (self-describing accessible name); reused once per claim/fact instead of once per ref.
- `frontend/src/features/chat/ActivityTimeline.tsx` -- `FactSegment` (supported path, ~L153-166), `ClaimSegment` (supported path, ~L199-216), and `EvidenceRefLinks` (~L63-109) render the current "Verified: field: value" text + per-ref link list; consolidate to one control.
- `frontend/src/features/chat/ActivityTimeline.test.tsx` -- asserts `toHaveTextContent("Verified: qualifications: pick")` and per-ref `Evidence: workers w1, qualifications` button names; update to the new combined control.
- `frontend/src/test/accessibility-contract.test.tsx:297-304` -- asserts the single-ref evidence control's exact accessible name and keyboard focusability; update the expected name if the consolidated control's label format changes.

## Tasks & Acceptance

**Execution:**
- [x] `backend/adapters/postgres/scenario_projection.py` -- change `SITE_TIMEZONE` from `"Australia/Sydney"` to `"Asia/Ho_Chi_Minh"` -- makes the site's timezone match its actual location.
- [x] Regenerate `data/contract/sample_tiny_input.projection-v1.json` and `data/contract/sample_tiny_input_more_tm.projection-v1.json` via `uv run --directory backend python scripts/export_contract_fixture.py` -- discovered during implementation: these byte-pinned committed snapshots embed `SITE_TIMEZONE`-derived `horizon_start`, and `test_export_contract_fixture.py::test_committed_contract_fixtures_are_current_and_deterministic` fails otherwise. Only `horizon_start`/`site_timezone` shifted (+3h, Sydney AEST → ICT); every relative-minute field was unaffected, confirming the constant only anchors the absolute instant.
- [x] `frontend/src/lib/formatTimestamp.ts` -- add a deterministic `formatHorizon(start, minutes)` (or similar) helper: renders a start→end range plus a humanized duration (whole days when evenly divisible, else days/hours/minutes remainder), with a unit test covering both branches of the I/O matrix.
- [x] `frontend/src/features/scenario-data/groups/OverviewPanel.tsx` -- use the new helper for the "Time horizon" row instead of the raw `starts X, N minutes` string; update `OverviewPanel.test.tsx` if it asserts the old string (it didn't -- only `ScenarioDataParity.test.tsx` independently reconstructed the old format and needed updating).
- [x] `frontend/src/components/primitives/EvidenceLink.tsx` -- add a compact "verified" rendering mode (small `aria-hidden` check icon, e.g. lucide-react's `CheckIcon` per the existing `checkbox.tsx` convention, immediately preceding the link) without changing its existing activation/label contract for other call sites. Also export a `VerifiedMark` sibling (check icon only, `role="img" aria-label="Verified"`, no link) for the multi-ref case.
- [x] `frontend/src/features/chat/ActivityTimeline.tsx` -- `FactSegment`'s supported branch (always 1 ref) and `ClaimSegment`'s supported branch: for exactly 1 evidence ref, replace the separate "Verified: field: value" text node + single-item `EvidenceRefLinks` with one combined check+link control, folding the field/value detail into the link's accessible name/visible text. For N>1 refs (e.g. `worker_count`), drop `EvidenceRefLinks` entirely and render only `VerifiedMark` — no link.
- [x] `frontend/src/features/chat/ActivityTimeline.test.tsx`, `frontend/src/test/accessibility-contract.test.tsx`, `frontend/src/components/primitives/EvidenceLink.test.tsx`, and `frontend/src/features/scenario-data/ScenarioDataParity.test.tsx` -- update assertions to match the new combined control's text/role/name and the new horizon format; added a case covering the multi-ref (`worker_count`, N>1) check-only (no link) behavior.

**Acceptance Criteria:**
- Given a scenario fixture with local wall-clock timestamps, when the projection reads them, then they are interpreted as `Asia/Ho_Chi_Minh` and converted to UTC (previously `Australia/Sydney`).
- Given the Scenario Overview panel, when `horizon_start`/`horizon_minutes` render, then the "Time horizon" row shows a readable start→end range with a human duration, never the raw `starts X, N minutes` phrasing.
- Given a supported fact or single-ref claim segment, when it renders, then exactly one compact check+link control appears (no separate "Verified: ..." text, no per-record link list), and that control's accessible name still discloses group/record/field/version.
- Given a claim with N>1 evidence refs, when it renders, then only a check icon appears (accessibly labelled "Verified"), with no link and no per-record list.
- Given a failed, wording-flagged, or zero-evidence segment, when it renders, then its existing markup and text are unchanged.

## Spec Change Log

## Design Notes

For a single evidence ref, the consolidated control is `EvidenceLink` itself
(extended, not replaced) with a small `aria-hidden` check icon rendered
immediately before it — the link keeps carrying the full "group record,
field/range, fixture version" as its accessible name, so nothing already
covered by `accessibility-contract.test.tsx` loses information, it just stops
being duplicated as adjacent plain text.

For N>1 evidence refs, do not render `EvidenceLink` at all — the mechanism
that produced the count (e.g. `calculate_metric`'s `worker_count`, which drains
and counts every worker row server-side) is itself the verification; a per-row
link list added nothing a planner could act on. Render just the check icon
with an accessible "Verified" label (e.g. `role="img" aria-label="Verified"`,
or equivalent visually-hidden text) so screen reader users still get the
verified state, not a purely decorative glyph. `claim.evidence_refs` stays
untouched in the data model — only the render path stops iterating it.

## Verification

**Commands:**
- `cd backend && uv run pytest tests/test_scenario_projection.py tests/test_postgres_integration.py -k "not postgres or postgres"` -- expected: unchanged pass (timezone constant swap touches no asserted absolute value).
- `cd frontend && npm test -- ActivityTimeline OverviewPanel accessibility-contract formatTimestamp` -- expected: updated suite passes, covering the new formatter and consolidated evidence control.
- `cd frontend && npm run lint` -- expected: clean (no unused `EvidenceRefLinks` remnants if fully replaced).

**Manual checks (if no CLI):**
- Open a scenario with a `worker_count`-style answer in the browser and confirm one check icon (no link) renders, not one link per worker.

## Suggested Review Order

**Site timezone**

- The one real behavior change: fixture-local wall-clock times now interpret as `Asia/Ho_Chi_Minh`, not `Australia/Sydney`.
  [`scenario_projection.py:47`](../../backend/adapters/postgres/scenario_projection.py#L47)

- Mechanical, required follow-up: these committed snapshots are byte-pinned to the constant above.
  [`sample_tiny_input.projection-v1.json:8`](../../data/contract/sample_tiny_input.projection-v1.json#L8)

- Doc drift caught by review: the domain model cited the old zone as fact.
  [`DOMAIN-MODEL.md:62`](../../docs/DOMAIN-MODEL.md#L62)

**Time horizon formatting**

- Deterministic UTC-epoch parsing (regex + `Date.UTC`, never `new Date(string)`) so a zone-naive input can't silently read host-local time.
  [`formatTimestamp.ts:81`](../../frontend/src/lib/formatTimestamp.ts#L81)

- Wired into the Overview panel in place of the raw "starts X, N minutes" string.
  [`OverviewPanel.tsx:21`](../../frontend/src/features/scenario-data/groups/OverviewPanel.tsx#L21)

**Grounded-answer evidence UI consolidation**

- `verified` mode folds the check icon into the link's own accessible name; `VerifiedMark` is the no-link, check-only sibling for multi-ref claims.
  [`EvidenceLink.tsx:26`](../../frontend/src/components/primitives/EvidenceLink.tsx#L26)

- Shared single-ref control reused by both fact states (`verified` toggles the check) and the single-ref claim path.
  [`ActivityTimeline.tsx:70`](../../frontend/src/features/chat/ActivityTimeline.tsx#L70)

- The N=1 vs N>1 branch point: one link for a single ref, `VerifiedMark` only (no link, no per-record drill-down) once a claim carries more than one — a deliberate, human-approved tradeoff, not an oversight (see `deferred-work.md`).
  [`ActivityTimeline.tsx:206`](../../frontend/src/features/chat/ActivityTimeline.tsx#L206)

**Tests and peripherals**

- New edge-case coverage from review: negative/non-integer/zone-naive horizon inputs.
  [`formatTimestamp.test.ts:54`](../../frontend/src/lib/formatTimestamp.test.ts#L54)

- New boundary coverage from review: N=2 renders identically to N=23 (check only, no link).
  [`ActivityTimeline.test.tsx:311`](../../frontend/src/features/chat/ActivityTimeline.test.tsx#L311)

- Updated accessible-name expectations across the consolidated control.
  [`accessibility-contract.test.tsx:297`](../../frontend/src/test/accessibility-contract.test.tsx#L297)
