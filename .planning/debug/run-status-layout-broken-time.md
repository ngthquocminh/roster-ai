---
status: diagnosed
trigger: "the run status layout is broken due to the time format is long"
created: 2026-07-18T16:00:03Z
updated: 2026-07-18T16:00:03Z
---

## Current Focus

hypothesis: CONFIRMED — see Resolution below.
test: n/a (goal: find_root_cause_only — diagnosis handed off, no fix applied here)
expecting: n/a
next_action: none — return ROOT CAUSE FOUND to caller for gap-closure planning

## Symptoms

expected: The Run History table's Created/Started/Finished columns render each run's timestamp cleanly within the table's `table-fixed` layout with explicit column widths (RUN-04).
actual: Created/Started/Finished cells render raw values like `2026-07-18T15:53:53.702354+00:00` that overflow their column widths, visually collide/overlap with each other, and force the whole table into horizontal scroll.
errors: None reported (visual/layout defect, not a crash or exception).
reproduction: Test 1 in `.planning/phases/03-run-execution-history/03-UAT.md` — trigger a run in the Run History view, let it complete, observe the history table row.
started: Discovered during UAT of Phase 03 (Run Execution & History), 2026-07-19. Introduced when RunHistoryTable.tsx was authored in plan 03-03 (Task 2).

## Eliminated

(none — root cause found on first pass via direct code read, no false starts)

## Evidence

- timestamp: 2026-07-18T16:00:03Z
  checked: frontend/src/components/runs/RunHistoryTable.tsx (full file)
  found: |
    Table header (lines 107-114) uses `<Table className="table-fixed">` with
    `<TableHead className="w-[22%]">` for each of Created/Started/Finished
    (Status gets w-[34%]). Each of the three timestamp `TableCell`s (lines
    138, 141, 144) carries `className="align-top whitespace-nowrap"` and
    renders the raw value verbatim: `{run.created_at}` / `<TimestampCell
    value={run.started_at} />` / `<TimestampCell value={run.finished_at} />`.
    `TimestampCell` (lines 47-52) does zero formatting — it only substitutes
    a muted "—" when the value is null/undefined; a non-null value is
    returned as-is via `<>{value}</>`. No date-formatting utility (no
    `toLocaleString`, `Intl.DateTimeFormat`, truncation, or `date-fns` call)
    exists anywhere in this file.
  implication: |
    Three independent facts compound: (1) content cannot wrap
    (`whitespace-nowrap`), (2) the column cannot grow to fit content
    (`table-fixed` layout strictly honors the declared `w-[22%]` widths
    regardless of cell content length), (3) the string itself is never
    shortened/formatted. Any string wider than 22% of the table's rendered
    width will overflow its cell box under these three conditions.

- timestamp: 2026-07-18T16:00:03Z
  checked: backend/services/run_service.py:43, backend/services/scenario_service.py:14
  found: |
    `_now()` returns `datetime.now(timezone.utc).isoformat()`. Python's
    `isoformat()` on a timezone-aware `datetime` with non-zero microseconds
    produces the full `YYYY-MM-DDTHH:MM:SS.ffffff+HH:MM` form — e.g.
    `2026-07-18T15:53:53.702354+00:00` (32 characters), NOT the shorter
    `Z`-suffixed or whole-second form. `created_at`/`started_at`/
    `finished_at` are all stamped via this same `_now()` helper
    (run_service.py:63 and elsewhere) and passed through to the API as
    plain `str` fields (backend/api/schemas.py:20,27) with no formatting.
  implication: |
    This exactly reproduces the string shown in the user's screenshot,
    confirming the backend is the origin of the 32-character un-shortened
    timestamp and the frontend is the layer responsible for (and failing
    at) making it fit.

- timestamp: 2026-07-18T16:00:03Z
  checked: frontend/src/components/runs/RunHistoryTable.tsx:106 (table wrapper div)
  found: |
    The scroll wrapper is `<div className="max-h-[420px] overflow-y-auto
    rounded-md border border-border">` — `overflow-y-auto` is set but
    `overflow-x` is left at its CSS default (`visible`). Per the CSS
    Overflow spec, when one axis is set to a non-`visible` value and the
    other is left `visible`, the UA computes the `visible` axis as `auto`
    too (so a scrollbar can appear on that axis instead of clipping). This
    matches the reported "forces the whole table into horizontal scroll"
    symptom: the wrapper becomes horizontally scrollable once cell content
    overflows its `table-fixed` column box.
  implication: |
    The horizontal-scroll and cell-overlap symptoms are two faces of the
    same root defect (un-wrappable, unformatted, too-long content inside a
    fixed-width, nowrap cell) rather than two separate bugs.

- timestamp: 2026-07-18T16:00:03Z
  checked: frontend/src/components/runs/RunHistoryTable.test.tsx (full file) and .planning/phases/03-run-execution-history/03-UI-SPEC.md (E2/E5 UI-consideration rows)
  found: |
    All test fixtures in the test file use short, whole-second, `Z`-suffixed
    timestamps (e.g. `"2026-07-18T10:00:00Z"`, 20 chars) — never the real
    32-char microsecond+offset form the backend actually emits. jsdom (the
    test renderer) also does not compute real CSS layout/overflow, so even
    a realistic-length fixture would not have failed a DOM-assertion test.
    In the UI-SPEC, the only "long-text" backstop row (E2/E5) is scoped
    explicitly to the FAILED row's `error` message column — the
    Created/Started/Finished timestamp columns have no long-text row at
    all, covered or backstopped. RUN-04's flagged_assumptions note in
    03-03-PLAN.md explicitly says "created_at rendered verbatim" was the
    planner's assumption with no length/format constraint considered.
  implication: |
    This is a genuine spec-and-test coverage gap, not a regression from
    working code: the real-world length of the timestamp string was never
    modeled at any point in the plan → build → test chain, so nothing
    caught it before UAT.

## Resolution

root_cause: |
  `RunHistoryTable.tsx`'s Created/Started/Finished `TableCell`s render
  `run.created_at`/`started_at`/`finished_at` verbatim (via `TimestampCell`,
  which only substitutes "—" for null — no date formatting) inside cells
  styled `whitespace-nowrap`, within a `<Table className="table-fixed">`
  whose three timestamp columns are pinned to `w-[22%]` each. The backend
  (`_now()` in `run_service.py`/`scenario_service.py`) stamps these fields
  with Python's `datetime.now(timezone.utc).isoformat()`, which for a
  timezone-aware datetime with microseconds produces the full
  `YYYY-MM-DDTHH:MM:SS.ffffff+HH:MM` form — a 32-character string (e.g.
  `2026-07-18T15:53:53.702354+00:00`), not the shorter `Z`-suffixed/
  whole-second form the plan's test fixtures assumed. Because the cell
  can't wrap the text (`whitespace-nowrap`) and the column can't grow to
  fit it (`table-fixed`), the un-shortened 32-char string overflows its
  22%-wide cell box, visually overlapping the neighboring column. The
  overflow then trips the wrapper div's mixed-overflow-axis CSS behavior
  (`overflow-y-auto` set, `overflow-x` left `visible` → UA promotes it to
  `auto`), producing the reported horizontal scroll on the whole table.
  This is a genuine coverage gap: no formatting/truncation utility for
  timestamps exists anywhere in the frontend, and neither the UI-SPEC's
  long-text backstop nor RunHistoryTable.test.tsx's fixtures modeled the
  real 32-character ISO-8601-with-microseconds-and-offset length the
  backend actually emits.
fix: (not applied — goal is find_root_cause_only; a gap-closure plan will implement the fix)
verification: (not applicable — no fix applied)
files_changed: []
