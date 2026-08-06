---
baseline_commit: e925c07965a363f7f0a6aae73b4bfddcd3842e4d
---

# Story 1.8: Control Scenario Data Tables

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want sorting, filtering, bounded navigation, column visibility, and identifier copying on Scenario Data tables,
so that I can locate exact records in large groups without losing orientation.

**This is a full-stack story — read this before planning.** Story 1.7's Dev Notes describe it as a frontend layer "directly on top of this story's group panels and API hooks," which is true of the *controls*, but the sorting and filtering behind them do **not** exist server-side yet. Story 1.4 shipped `cursor`/`limit` only and said so explicitly in its own Task 2: *"`matching_count` = `total_count` in this story (no filter capability exists until Story 1.8 — keep the field now so the response shape doesn't have to change later, but don't build filtering logic to populate it differently)"* and *"Do not invent a 'smarter' default sort; explicit sorting is Story 1.8's acceptance boundary, not this one's."* Verified directly against `backend/api/routers/scenario_projection.py` (six list endpoints, `cursor`/`limit` only) and `backend/adapters/postgres/scenario_projection.py:428-540` (every `*PageV1` is constructed with `total, total` for the count pair). **This story owns the backend half.**

**Sorting and filtering are server-side, not client-side over one page.** This is not a preference — three separate contracts force it: AD-4 (*"Lists use deterministic stable ordering, bounded cursor windows with counts, and exact-target lookup"*), UX-DR24 / EXPERIENCE.md's Large-table contract (*"total and matching row counts… Deep links retrieve the target page/window before focus; they never report 'missing' merely because the row was not currently rendered"*), and AC #1's own "total/matching counts." Filtering 50 rows in the browser cannot produce a truthful matching count over a 1,200-row group, and would make Story 2.8's exact-target navigation unimplementable.

**Depends on:**
- **Story 1.7 — hard blocker for the frontend half.** Story 1.7 is `ready-for-dev`, *not* done: `frontend/src/features/scenario-data/`, `frontend/src/routes/ScenarioData.tsx`, `frontend/src/api/scenarioProjection.ts`, `frontend/src/hooks/useScenarioProjection.ts`, and `WorkspaceTabs.tsx` do not exist on disk today (verified). Every frontend task below edits or extends files 1.7 creates. **Tasks 1–3 (backend) have no such dependency and should be built first** — they are pure `backend/` work over already-shipped endpoints.
- **Story 1.4 (done)** — the cursor contract, the `record_id` scheme, the `*PageV1` port dataclasses, and the seven endpoints this story extends.
- **Story 1.5 (done)** — not consumed here, but its exact-target resolve endpoints are the eventual consumer of AC #2's revealed-field mechanism.
- **Story 1.6 (`ready-for-dev`, may or may not have landed)** — supplies `components/primitives/`, `InlineAlert`, `EmptyState`, `badge.tsx`, and the indigo `--primary` token. See Dev Notes "Story 1.6 ordering" for what to check and how to stay correct either way.

**Unblocks:** Story 1.9 (mutation-denial audit must see the filter/sort/chooser/copy controls and confirm none of them mutate), Story 1.10 (accessibility proof over `aria-sort`, filter controls, copy announcements, row position), Story 2.8 (evidence navigation deep-links into the exact page/window and targets a possibly-hidden field — this story builds the `?field=` reveal mechanism it will use).

**Sizing note — sequence it, do not split it.** High implementation breadth across two stacks. epics.md line 1637's rule is that a story is only split when each slice stays independently testable without a forward dependency; the filter bar cannot be accepted without server filtering, and server filtering has no planner-visible outcome alone. Build in task order: backend contract (Tasks 1–3) → codegen (Task 4) → frontend controls (Tasks 5–9) → tests (Task 10). One owner per stack is fine; one acceptance boundary.

## Acceptance Criteria

1. **Given** any Scenario Data group, **when** the planner sorts, filters, or pages it, **then** explicit sorting and field-aware filtering with Apply/Clear, active-filter and total/matching counts, URL serialization, and bounded navigation behave deterministically with stable-ID tie-breaks, **and** copyable stable identifiers announce "Copied {identifier type}" without implying row selection or editability. *(UX-DR14, UX-DR15, UX-DR17, UX-DR24)*

2. **Given** a field is hidden through the session-scoped column chooser, **when** an exact evidence locator targets that field, **then** the field becomes temporarily visible with an explanation, **and** the chooser can never hide every stable ID, evidence target, and key context column. *(UX-DR16)*

## Tasks / Subtasks

- [x] Task 1: Extend the projection port with one query object (AC: #1)
  - [x] In `backend/application/ports/scenario_projection.py`, add one frozen dataclass beside the existing `*PageV1` types:
    ```python
    @dataclass(frozen=True)
    class GroupQueryV1:
        cursor: int = 0
        limit: int = 50
        sort: str | None = None          # None = the Story 1.4 source order
        order: str = "asc"               # "asc" | "desc"
        filters: tuple[tuple[str, str | int], ...] = ()
    ```
    `filters` is a tuple of `(param_name, coerced_value)` pairs, **not** a dict — the repo's port dataclasses are frozen and the existing `*PageV1` types all use tuples for collections (`items: tuple[TaskV1, ...]`). Values arrive already coerced by FastAPI's typed `Query(...)` declarations in Task 3, so the adapter never parses strings.
  - [x] Change the six windowed `ScenarioProjectionReader` methods from `(self, connection, scenario_id, cursor, limit)` to `(self, connection, scenario_id, query: GroupQueryV1)`. Do **not** add five positional parameters per method — six methods × five params is the shape that guarantees a call-site mistake. `get_overview` and the six `resolve_*` methods are unchanged.
  - [x] **Do not add a `filters` field to any `*PageV1` response dataclass.** The response already carries `total_count` (unfiltered group size) and `matching_count` (post-filter size); echoing the request back is not in either AC and would need a matching `api/schemas.py` field, a codegen cycle, and a contract test for no gain. The client already knows what it asked for — it is in the URL.
  - [x] `application/` must not import FastAPI (AD-1). `order` and `sort` are plain `str` here; the `Literal[...]` enums live in the router (Task 3), which is where the 422 boundary belongs.

- [x] Task 2: Implement filter → sort → window in the Postgres adapter (AC: #1)
  - [x] All six groups are normalized in memory from one immutable JSONB `payload` (`_normalize_tasks`, `_normalize_workers`, `_normalize_demand`, `_normalize_constraints`; baseline-assignments and locks return `()`). Filtering and sorting therefore happen **in Python over the normalized tuples, before `_slice_window`** — do not push predicates into SQL. There is nothing to push them into: `_projection_row` selects one row and the group lists are derived from its `payload`.
  - [x] **Keep `_slice_window` exactly as it is.** `backend/tests/test_scenario_projection.py` imports it directly (line ~36) and unit-tests it. Add a new `_apply_query(items, query, sorts, filters) -> tuple[tuple[T, ...], int | None, int, int]` that filters, sorts, then *calls* `_slice_window`, returning `(page, next_cursor, total_count, matching_count)`.
  - [x] **Order of operations is load-bearing:** `total_count = len(items)` is captured **before** filtering; `matching_count = len(filtered)`; `next_cursor` and the window are computed over the **filtered, sorted** list. `total_count` is the unfiltered group size in every response — that is what makes EXPERIENCE.md's "total and matching row counts" two different numbers.
  - [x] **Descending sort must not reverse the tie-break.** The obvious one-liner is wrong:
    ```python
    # WRONG — reverses record_id too, so equal keys page non-deterministically
    sorted(items, key=lambda i: (key(i), i.record_id), reverse=True)

    # RIGHT — Python's sort is stable, including with reverse=True
    ordered = sorted(items, key=lambda i: i.record_id)
    ordered = sorted(ordered, key=key, reverse=(query.order == "desc"))
    ```
    With `sort=None` (the default) do **neither** — return source order untouched, exactly as Story 1.4 shipped it. `record_id` is already unique per group, so the tie-break only ever matters for equal primary keys, which is precisely where a non-deterministic page boundary would silently drop or duplicate a row.
  - [x] **Nullable sort keys.** `unit_type_id`, `area_id`, `shift_id`, and `value_type` are `str | None`; `sorted` over mixed `None`/`str` raises `TypeError`. Wrap every nullable key as `(1, "") if value is None else (0, value)`. Consequence to document in a comment: nulls sort last ascending and first descending. Mirror the intent of the adapter's existing `nulls_last(...)` on `_VERSION_ORDINAL`.
  - [x] Declare the allowed sort keys and filter predicates as module-level tables next to each normalizer, so the router, the adapter, and the tests read one source:
    | Group | Sort keys | Filter params (kind) |
    |---|---|---|
    | `work-areas-and-tasks` | `task_id`, `name`, `function`, `area_id`, `area_name` | `task_id` (exact), `name_contains` (case-insensitive substring), `function` (exact), `area_id` (exact) |
    | `workers` | `contact_id`, `name`, `employment_type`, `grade`, `contracted_hours` | `contact_id` (exact), `name_contains` (ci substring), `employment_type` (exact), `grade` (exact), `qualified_task_id` (membership in `qualifications[].task_id`) |
    | `demand` | `start_minute`, `end_minute`, `task_id`, `family`, `amount` | `family` (exact, enum), `task_id` (exact), `area_id` (exact), `start_minute_gte` (int, `>=`), `end_minute_lte` (int, `<=`) |
    | `baseline-assignments` | `start_minute`, `worker_id`, `task_id` | `worker_id`, `task_id`, `shift_id` (all exact) |
    | `locks` | `target_type`, `target_ref`, `scope`, `source` | `target_type`, `target_ref`, `scope`, `source` (all exact) |
    | `constraints-and-objectives` | `constraint_type`, `value_type` | `constraint_type` (exact), `value_type` (exact) |
    Exact matches are case-sensitive equality on the normalized value; `*_contains` is `value.casefold() in field.casefold()`. Multiple filters combine with AND. An absent/`None` param is not a filter.
  - [x] **`baseline-assignments` and `locks` still return `()` unconditionally.** Story 1.4 made them permanently empty until Epic 3/4 exist and its review recorded that as directed, not a defect. They accept and validate the same params (so the contract is uniform and the frontend needs no special case) and answer `items=(), next_cursor=None, total_count=0, matching_count=0`. Do not add a data source for them here.
  - [x] `_apply_query` is one shared helper used by all six methods — do not write six near-identical filter loops.

- [x] Task 3: Publish typed query parameters on the six list endpoints (AC: #1)
  - [x] In `backend/api/routers/scenario_projection.py`, add per-endpoint `sort` and `order` parameters typed as `Literal[...]` over exactly that group's sort keys (plus `order: Literal["asc", "desc"] = "asc"`), and one optional parameter per filter param from Task 2's table. FastAPI then publishes them as OpenAPI enums and rejects an unknown value with 422 automatically — that is the "behaves deterministically" boundary, and it keeps `application/` free of FastAPI (AD-1).
  - [x] Each handler builds a `GroupQueryV1` and passes it to the reader. Build `filters` by dropping `None` values, in a fixed declaration order, so two requests with the same filters produce the same tuple.
  - [x] `cursor: int = Query(default=0, ge=0)` and `limit: int = Query(default=50, ge=1, le=200)` keep their current declarations verbatim. Do not change the defaults; Story 1.4's NFR35 evidence was measured against them.
  - [x] The seven `resolve_*` endpoints and `GET .../projection` (overview) are **untouched** — no sort, no filter, no pagination. Exact-target resolution deliberately ignores the current window (Story 1.5's whole point).
  - [x] Errors stay RFC 7807 (AD-13, `api/problems.py`): an unknown `sort` value, a bad `order`, or a non-integer `start_minute_gte` is a 422 `invalid_request` via FastAPI's existing validation handler. Do not hand-roll a new error code or silently coerce a bad value to a default — "invalid" must stay distinct from "no filter" (Consistency Conventions: *"Denied, stale, missing, invalid… remain distinct"*).
  - [x] `cursor` beyond `matching_count` returns an empty page, not an error — the existing Story 1.4 behavior, reaffirmed in its review as deliberate. Do not "fix" it here.

- [x] Task 4: Regenerate contracts (AC: #1)
  - [x] `npm run codegen` from `frontend/` (exports `frontend/openapi.json`, regenerates `frontend/src/api/schema.d.ts`). The new query params must appear under each path's `get.parameters.query`. Both generated files belong in this story's diff — unlike Stories 1.6/1.7, this story *does* change the OpenAPI document.
  - [x] Do not hand-edit `schema.d.ts`.

- [x] Task 5: Thread sort/filter/cursor through the frontend API + hooks (AC: #1)
  - [x] `frontend/src/api/scenarioProjection.ts` (created by Story 1.7): widen the six list functions from `(scenarioId, cursor?, limit?)` to `(scenarioId, params)` where `params` is a small object carrying `cursor`, `limit`, `sort`, `order`, and the group's filter params. Derive the param type from the generated schema — `paths["/api/v1/scenarios/{scenario_id}/projection/demand"]["get"]["parameters"]["query"]` — never hand-author it (the repo's stated rule: *"No hand-authored interfaces; derive from generated OpenAPI schema"*). `openapi-fetch` takes them as `{ params: { path: {...}, query: {...} } }`; omit `undefined` keys rather than sending empty strings.
  - [x] `frontend/src/hooks/useScenarioProjection.ts` (created by Story 1.7): the six list hooks take the same params object and **must include it in the query key** — `["scenario-projection", scenarioId, "<group-slug>", params] as const`. A key that ignores sort/filter/cursor serves the previous page's rows for the new URL, which reads as a broken filter. Keep `retry: false` and keep the existing no-`staleTime` decision and its comment.
  - [x] Add `placeholderData: keepPreviousData` (from `@tanstack/react-query`) to the six list hooks so paging and re-sorting do not flash the skeleton over already-loaded data. Pair it with the loading affordance in Task 8 — a stale-but-visible table with no busy signal is worse than a skeleton.
  - [x] `useScenarioOverview` is unchanged (no window, no filters).

- [x] Task 6: One descriptor module per group for columns and filters (AC: #1, #2)
  - [x] New `frontend/src/features/scenario-data/columns.ts` — for each of the six list groups, an ordered array of column descriptors:
    ```ts
    type ColumnDef = {
      key: string;          // stable column key; also the ?field= value (Task 9)
      header: string;       // visible <th> text
      required: boolean;    // true => never hideable (AC #2)
      monospace?: boolean;  // identifier typography
      sortKey?: string;     // maps to the backend `sort` enum; absent => not sortable
      copyType?: string;    // presence => render an identifier copy control; the
                            // literal noun in "Copied {identifier type}" (Task 7)
    };
    ```
    Column keys, headers, and cell content must match exactly what Story 1.7 shipped for that panel — this task **extracts** the descriptors from the panels, it does not redesign them. Overview is a key/value table with no window: it gets no descriptor, no controls, no chooser, no pagination.
  - [x] **`required: true` on exactly two columns per group** — the stable record identifier and the group's primary context column. This is AC #2's *"can never hide every stable ID, evidence target, and key context column"* expressed as a type/data invariant rather than a runtime check:
    | Group | Required columns |
    |---|---|
    | `work-areas-and-tasks` | Task ID, Name |
    | `workers` | Contact ID, Name |
    | `demand` | Record ID, Window |
    | `baseline-assignments` | Record ID, Window |
    | `locks` | Record ID, Target ref |
    | `constraints-and-objectives` | Record ID, Constraint type |
    A required column has no checkbox to clear in the chooser — render it checked and `disabled`, not merely "the click is ignored."
  - [x] `sortKey` is present only on columns whose key appears in Task 2's sort table for that group. A column with no `sortKey` renders a plain `<th>` with `aria-sort` absent — not a disabled button.
  - [x] New `frontend/src/features/scenario-data/filters.ts` — per group, an ordered array of `{ param, label, kind: "text" | "number" | "select", options?: readonly string[] }` matching Task 2's filter table one-for-one. `demand.family` is the only `select` (`outbound` / `inbound` / `indirect` — the exact `Literal` values in `DemandIntervalOut`); `start_minute_gte` / `end_minute_lte` are `number`; everything else is `text`.
  - [x] Keep both modules pure data with no JSX and no imports from `@/hooks` or `@/api` — they are read by the panels, the filter bar, the chooser, and the tests.

- [x] Task 7: Identifier copy control (AC: #1)
  - [x] New `frontend/src/components/primitives/IdentifierCopyButton.tsx`. Props: `{ value: string; identifierType: string }`. Renders the value (monospace, `title={value}`) plus a shadcn **ghost** `Button` with `Copy` from `lucide-react` and an accessible name naming the type and value, e.g. `Copy Task ID T-104`. DESIGN.md: *"Identifier copy control — Inherits shadcn ghost Button and Tooltip. Copied feedback is text/assistive announcement, not only an icon swap."*
  - [x] On click: `navigator.clipboard.writeText(value)`, then put the literal string `Copied {identifierType}` into a `role="status"` polite region **that is already mounted** (a live region only announces mutations to an existing region — this exact defect was fixed once in Story 1.3's review; do not reintroduce it by conditionally rendering the region). Clear the message after a short timeout; the timeout must be cancelled on unmount.
  - [x] If the write rejects or `navigator.clipboard` is unavailable, announce a literal failure instead — never announce a copy that did not happen. Keep it in EXPERIENCE.md's voice, e.g. `Copy unavailable. Select the identifier to copy it manually.`
  - [x] **Must not imply row selection or editability** (AC #1, UX-DR17, FR24): no checkbox, no row-level click handler, no `contentEditable`, no `<input readonly>`, no focus ring on the row. The button is the only interactive element added to a cell, and it carries `min-h-11` (the repo's expression of UX-DR29's 44px floor).
  - [x] Attach it to every column carrying a `copyType` in Task 6's descriptors — the stable identifier columns (`task_id`, `contact_id`/`worker_id`, `area_id`, `record_id`, `shift_id`, `target_ref`). Story 1.7 explicitly deferred this: *"No copy-to-clipboard control yet (UX-DR17, Story 1.8's scope)."*
  - [x] **Location check before you write the file:** if Story 1.6 has landed, `frontend/src/components/primitives/` already exists with `InlineAlert.tsx`/`EmptyState.tsx`/`fixtures.tsx` — add the file there and add its two states (idle, copied) to `PRIMITIVE_FIXTURES`. If 1.6 has not landed, create the directory with this one file and **do not** create `fixtures.tsx` (that module is 1.6's deliverable and 3.12/4.7 consume its exact shape). Story 1.6 explicitly lists "Identifier copy control" in its out-of-scope list, deferred to the story that owns it — this one.

- [x] Task 8: Filter bar, sortable headers, and bounded navigation (AC: #1)
  - [x] New `frontend/src/features/scenario-data/useGroupControls.ts` — the single owner of URL control state, over `useSearchParams()`:
    - Reads `sort`, `order`, `cursor`, and the active group's filter params from the URL; validates each against Task 6's descriptors and **falls back to the default without crashing** on a hand-edited/garbage value (same defensive posture Story 1.7 used for `?group=`).
    - **On group change, drop every control param and keep only `group`.** `?family=outbound` must not survive a switch to `workers`, where that param does not exist. This is the deterministic rule; do not try to namespace params per group.
    - Apply, Clear, a sort change, and a page change each **push** a history entry (not `replace`), because EXPERIENCE.md requires *"Browser Back/Forward restores surface, filters, evidence target, and origin."* Draft filter input lives in local `useState` and only reaches the URL on Apply — that is what makes Apply explicit rather than debounced.
    - **Any filter or sort change resets `cursor` to 0.** Keeping a cursor across a filter change points into a list that no longer exists.
  - [x] New `frontend/src/features/scenario-data/FilterBar.tsx` — renders the active group's `filters.ts` descriptors as shadcn `Input`/`Select` controls with an explicit **Apply** and **Clear** button pair (EXPERIENCE.md: *"Apply and Clear are explicit"*). Shows the **active filter count** as a shadcn `Badge` and lists each active filter as removable text (DESIGN.md: *"Active filters are text-labelled and removable; no edit iconography"*). Clear removes all filter params at once and resets the cursor. `badge.tsx` is a Story 1.6 copy-in — if it is absent, add the standard shadcn Badge copy-in to `components/ui/` (a copy-in of the already-installed system, not a dependency; same precedent as Story 1.3 adding `skeleton.tsx`, and `package.json`/`package-lock.json` stay untouched per AR27).
  - [x] Sortable headers: extend Story 1.7's `ScenarioDataTable.tsx` so a column with a `sortKey` renders its `<th scope="col">` containing a `<button>` that toggles `asc → desc → asc`, and the `<th>` carries `aria-sort="ascending" | "descending" | "none"` (EXPERIENCE.md Accessibility Floor: *"sort state via `aria-sort`"*). Exactly one column may be sorted at a time — the backend `sort` param is single-valued, so do not build a multi-column UI it cannot express. Keep every existing `scope="col"` and the sticky/opaque header treatment 1.7 shipped.
  - [x] New `frontend/src/features/scenario-data/PaginationControls.tsx` — **First / Previous / Next / Last** plus a literal position line. UX-DR24 forbids infinite scroll and requires *"an explicit route to the first/previous/next/last segment."* All four are computable from the response: `first = 0`, `previous = max(0, cursor - PAGE_SIZE)`, `next = next_cursor` (disabled when `null`), `last = Math.max(0, Math.floor((matching_count - 1) / PAGE_SIZE) * PAGE_SIZE)`. Define `PAGE_SIZE = 50` once (the server default Story 1.4 shipped) and send it explicitly as `limit`.
  - [x] Position and counts copy — EXPERIENCE.md requires *"total and matching row counts, current position/range"* as visible text, not a tooltip. Render both numbers literally, e.g. `Showing 51–100 of 214 matching (1,203 total)`; when no filter is active `matching_count === total_count` and one number suffices, e.g. `Showing 51–100 of 1,203`. Mirror this into a mounted `role="status"` polite region on the view so a screen-reader user hears the new range after paging (EXPERIENCE.md: *"Virtualized implementations must preserve announced row position/total"* — the same obligation applies to the paginated mode we chose).
  - [x] **Filtered-empty vs intrinsically-empty copy are different strings.** Story 1.7 shipped `"This fixture has no records in this group."` for an intrinsically empty group. When filters are active and `matching_count === 0`, keep the headers and the filter bar mounted and show EXPERIENCE.md's other literal: `"No records in this group match these filters."` Branch on "are any filters active," not on `total_count`, so a genuinely empty group with a filter applied still reads as a filter result.
  - [x] While a page/sort/filter request is in flight over already-visible rows (Task 5's `keepPreviousData`), mark the table region `aria-busy="true"` and dim it — do not swap in the skeleton, and do not leave a stale table looking current with no signal.
  - [x] Mutation denial still holds (FR24, UX-DR4): every control added here is a filter/sort/visibility/copy affordance. No checkbox that selects a *row*, no bulk action, no "…" overflow menu on a row, no editable cell. The column chooser's checkboxes act on columns, never rows.

- [x] Task 9: Session-scoped column chooser and the evidence-reveal path (AC: #2)
  - [x] New `frontend/src/features/scenario-data/useColumnVisibility.ts` — per-group hidden-column state in **`sessionStorage`** (UX-DR16 says *"session-scoped"*, and EXPERIENCE.md says *"Column visibility is a viewing preference, not data configuration"* — so it is deliberately **not** in the URL, unlike filters and sort). One key per group, e.g. `shiftmind.columns.<group-slug>`. Guard the read: unparseable JSON, an unknown column key, or a `required` key present in the hidden set is discarded silently and the default (all visible) is used.
  - [x] Visibility is **derived, never stored merged**:
    ```
    visible(column) = column.required
                   || !hidden.has(column.key)
                   || column.key === revealedField
    ```
    where `revealedField` is the `?field=` search param. Writing the reveal into stored visibility would make it permanent; deriving it makes it *temporary* exactly as AC #2 requires — it disappears when the param leaves the URL.
  - [x] **`?field=` is the evidence-locator hook Story 2.8 will use.** `EvidenceRefV1`'s required shape is *"group, record ID, optional field and minute interval"* (AD-20 / Structural Seed) and AD-14 requires evidence navigation to persist the locator in URL/history state. This story builds and tests the reveal mechanism against a directly-navigated `?group=<slug>&field=<column-key>` URL; it does **not** build evidence links, highlight, focus management, origin capture, or Return to claim — all of that is Story 2.8's acceptance boundary over Story 1.5's already-shipped resolver endpoints. Reuse Task 6's column `key` as the `field` vocabulary so 2.8 needs no translation layer (the same reasoning that made Story 1.7 reuse the backend's group slugs).
  - [x] An unknown `?field=` value reveals nothing and does not crash or error — it is not an evidence *exception* (those are Story 2.8/UX-DR20 and require a resolver round-trip); it is just a param naming no column here.
  - [x] New `frontend/src/features/scenario-data/ColumnChooser.tsx` — shadcn `DropdownMenu` with `DropdownMenuCheckboxItem` per column (DESIGN.md: *"Inherits shadcn DropdownMenu/Popover with Checkbox items. It controls visibility only."*). **`dropdown-menu.tsx` and `checkbox.tsx` do not exist in `frontend/src/components/ui/` yet** — add the standard shadcn copy-ins (the `radix-ui` umbrella package at `^1.6.2` already ships `react-dropdown-menu` and `react-checkbox`; verified in `frontend/node_modules/@radix-ui/`, so this is a copy-in, not an install — `package.json` must not change). Follow `tabs.tsx`'s import style: `import { DropdownMenu as DropdownMenuPrimitive } from "radix-ui"`, not `@radix-ui/react-dropdown-menu`. Use `DropdownMenu` only; do not also add `popover.tsx`.
  - [x] Required columns render checked and `disabled`. A column revealed by `?field=` also renders checked and disabled, with the reason as its item description.
  - [x] **Explanation copy (AC #2's "with an explanation") — authored here, flag it in completion notes.** Neither EXPERIENCE.md nor DESIGN.md gives a literal for this string; the nearest normative sentence is *"If a link targets a hidden field, that field becomes temporarily visible and the chooser states why."* Ship exactly two strings, in EXPERIENCE.md's operational voice, and do not improvise past them: beside the table — `"{Column} is shown because an evidence link targets it."`; in the chooser item — `"Shown for the linked evidence target."` See the Open Questions note at the end of Dev Notes.
  - [x] Wire the chooser and filter bar into Story 1.7's `ScenarioDataView.tsx` above the active group's panel, and pass the visible-column set down to the panels so a hidden column's `<th>` **and** its `<td>`s are both omitted (never `display:none` — a hidden-by-CSS cell still reaches the accessibility tree and still lands in native browser find).

- [x] Task 10: Tests
  - [x] **Backend — adapter unit tests** (`backend/tests/test_scenario_projection.py`, extend; fixture-backed, no Postgres marker needed for the pure normalizer paths):
    - `_apply_query` with no `sort`: returns Story 1.4's source order byte-for-byte (guard against a silent default-ordering change).
    - Descending sort on a key with **deliberate duplicates** (e.g. two demand rows sharing `start_minute`, two tasks sharing `function`): assert `record_id` stays *ascending* within the tie group. This is the one assertion that catches the wrong-one-liner in Task 2; write it before the implementation.
    - Nullable sort key (`unit_type_id`, `value_type`, `area_id`, `shift_id`): sorts without raising; nulls last ascending, first descending.
    - Each filter kind: exact match, case-insensitive `*_contains`, `qualified_task_id` array membership, `start_minute_gte`/`end_minute_lte` bounds (assert the boundary value is **included** — `>=`/`<=`, not `>`/`<`).
    - Two filters AND together; a filter matching nothing yields `items=()`, `matching_count=0`, `total_count` unchanged and non-zero.
    - `total_count` is the unfiltered size and `matching_count` the filtered size **in the same response**.
    - Paging a filtered+sorted group with `limit=5` reconstructs exactly the same ordered `record_id` sequence as one large-`limit` call, with no duplicate and no gap (extend the Story 1.4 pattern already in `test_postgres_integration.py`).
    - `baseline-assignments`/`locks` accept every param and still answer empty with zero counts.
  - [x] **Backend — API contract tests** (`test_scenario_projection.py`, `TestClient` + the existing stub-reader override pattern): each of the six endpoints accepts its declared `sort`/`order`/filter params and forwards a correctly-populated `GroupQueryV1` to the reader (assert on the captured query object, not just the status code); an unknown `sort` value and a bad `order` each return **422** RFC 7807 problem details; `cursor` past the end returns an empty page with 200.
  - [x] **Backend — NFR35 regression.** `test_nfr35_projection_initial_windows_meet_two_second_threshold` and `test_nfr35_exact_evidence_targets_meet_two_second_threshold` (`tests/test_postgres_integration.py:202,273`) re-measure live on every run against the largest Gate A fixture. They must still pass unchanged — this story adds no AC of its own under NFR35, but AD-26's *"a threshold miss blocks acceptance of its owning story"* means a regression here fails Story 1.4's already-recorded evidence. Do not edit the committed `evidence/story-1.4/` or `evidence/story-1.5/` JSON. Adding one measured filtered+sorted request alongside them is cheap and welcome; it is not required by either AC.
  - [x] **Frontend — API/hooks** (`scenarioProjection.test.ts`, `useScenarioProjection.test.tsx`, extend Story 1.7's files): params serialize into the query string; `undefined` params are omitted entirely rather than sent empty; the query key changes when sort/filter/cursor change (a fixed key here is the specific bug this test exists to catch).
  - [x] **Frontend — `useGroupControls.test.tsx`** (new): reads sort/order/cursor/filters from the URL; a garbage `sort` or `order` falls back without crashing; changing group strips every control param; Apply/Clear/sort/page each push history so Back restores the previous control state; any filter or sort change resets `cursor` to 0.
  - [x] **Frontend — `FilterBar.test.tsx`** (new): typing does not change the URL until Apply; Apply serializes exactly the non-empty fields; the active-filter count matches; each active filter is individually removable; Clear removes all of them and resets the cursor.
  - [x] **Frontend — sortable header tests** (extend `ScenarioDataTable.test.tsx` / the panel tests): a sortable `<th>` carries `aria-sort="none"` until sorted, then `"ascending"`/`"descending"`; clicking toggles; a non-sortable column has no button and no `aria-sort`; every `<th>` still carries `scope="col"`; only one column is sorted at a time.
  - [x] **Frontend — `PaginationControls.test.tsx`** (new): First/Previous disabled on the first page; Next disabled when `next_cursor` is `null`; Last computes the final offset from `matching_count`; the position line renders both counts when filtered and one when not; the polite region announces the new range after paging.
  - [x] **Frontend — `IdentifierCopyButton.test.tsx`** (new): clicking writes the **full** value (not a truncated display form) via a mocked `navigator.clipboard.writeText`; the live region receives the literal `Copied {identifier type}`; a rejected write announces the failure and never the success; the region is mounted before the click; no `<input>`, checkbox, or row-level handler exists in the rendered output.
  - [x] **Frontend — `ColumnChooser.test.tsx` / `useColumnVisibility.test.ts`** (new): hiding a column removes its `<th>` *and* its `<td>`s from the DOM; visibility survives a remount within the session and is scoped per group; required columns render checked+disabled and cannot be hidden through any code path (drive it by writing a hostile `sessionStorage` value listing a required key and asserting it is discarded); **AC #2's core case** — with a column hidden, navigating to `?group=<slug>&field=<that column key>` renders the column *and* the explanation string, the chooser item shows the reason, and removing `?field=` hides it again (proving "temporarily"); an unknown `?field=` value is a no-op.
  - [x] **Frontend — empty-state branching** (extend the panel tests): filters active + zero matches renders `"No records in this group match these filters."` with the filter bar and headers still present; no filters + zero rows keeps Story 1.7's `"This fixture has no records in this group."`
  - [x] **Frontend — Story 1.7 regression:** every `ScenarioDataView`/panel/`router` test Story 1.7 shipped must still pass. If one needs updating because a control was added to the surface, update the assertion deliberately and say so in completion notes — do not delete it.
  - [x] **Full gate before marking done:** `npm run typecheck`, `npm run lint`, `npm run build`, `npm test` (from `frontend/`); `uv run --frozen pytest` and `alembic check` (from `backend/` — `alembic check` must show zero diff; this story adds **no migration**, it changes no table). Report backend and frontend test counts before and after.

## Change Log

- 2026-08-06: Implemented full-stack server filtering/sorting, generated contracts, URL-backed table controls, identifier copy, session column visibility, evidence-field reveal, and comprehensive regression coverage.

## Dev Notes

- **What this story does NOT build.** No migration and no schema change — every filter and sort operates on the existing immutable `payload`. No evidence links, no `EvidenceHighlight`, no focus-on-target, no Return to claim, no origin key, no evidence *exception* panel (version mismatch / missing / unauthorized) — Story 2.8 owns all of it over Story 1.5's shipped resolvers; this story only builds the `?field=` reveal it will use. No multi-column sort (the backend `sort` param is single-valued by design). No virtualization (UX-DR24 permits bounded pagination *or* virtualization; pagination is the accessible-by-default choice and the one this contract already fits). No export or bulk download (EXPERIENCE.md: *"Export is not implied"*). No page-size control. No sort/filter/pagination on the Overview group (it is a key/value table, not a list). No `AgentRuntime` anything.
- **Story 1.7 must land first for Tasks 5–9.** Its files do not exist yet. If you are running these stories back-to-back, do the backend half (Tasks 1–4) first: it is self-contained, testable on its own, and leaves the frontend half a pure consumption task. If 1.7's implementation diverged from its plan (different file names, different panel props), follow what actually shipped and note the divergence — the descriptors in Task 6 must match the columns 1.7 really rendered, not the ones its plan predicted.
- **Story 1.6 ordering — check `frontend/src/components/primitives/` and `frontend/src/components/ui/badge.tsx` before writing Task 7/8 files.** If 1.6 has landed: `IdentifierCopyButton` joins the existing primitives directory and registers its states in `PRIMITIVE_FIXTURES`; `badge.tsx` already exists; `--primary` is `#4F46E5` so `text-primary`/`border-primary` render indigo. If it has not: create `components/primitives/` with just this one file (no `fixtures.tsx` — that is 1.6's deliverable and 3.12/4.7 depend on its exact shape), add the shadcn `badge.tsx` copy-in yourself, and mirror `AppBar.tsx`'s hardcoded `#4F46E5` workaround rather than assuming `text-primary` is indigo. Either way `dropdown-menu.tsx` and `checkbox.tsx` are this story's copy-ins — 1.6 does not add them.
- **`components/ui/` is shadcn's territory.** `components.json` aliases `"ui": "@/components/ui"`, so a future `npx shadcn add` overwrites same-named files there. Unmodified shadcn copy-ins (`badge`, `dropdown-menu`, `checkbox`) go there; ShiftMind-specific components (`IdentifierCopyButton`) go in `components/primitives/`; Scenario-Data-specific components (`FilterBar`, `ColumnChooser`, `PaginationControls`) go in `features/scenario-data/` per AR26's structural seed.
- **Three different "counts" — keep them straight.** `total_count` = the whole group, ignoring filters. `matching_count` = rows passing the current filters. The visible *position range* is derived from `cursor`, `items.length`, and `matching_count`. Story 1.4 shipped `matching_count === total_count` for every group; this story is what makes them diverge, and the count pair is a published contract field, not a UI detail.
- **The filter/sort contract is a cross-story vocabulary, not local UI config.** Task 6's column `key` values become the `?field=` values Story 2.8 links to, and the backend `sort` enum values are published in OpenAPI. Pick each name once and use the same string in the router `Literal`, the adapter's sort table, `columns.ts`, and the URL. Story 1.7 set this precedent for group slugs and it is the reason evidence navigation will not need a translation layer.
- **Domain purity (AD-1).** `application/ports/scenario_projection.py` may not import FastAPI, SQLAlchemy, or Pydantic — `GroupQueryV1` is a plain frozen dataclass with `str`/`int` fields. The `Literal[...]` enums that produce 422s live in `api/routers/`; the predicates that interpret them live in `adapters/postgres/`. Note the port already types `connection: Any` deliberately (Story 1.4's review recorded this as the *more* compliant choice versus its sibling catalogue port, which leaks `sqlalchemy.Connection` into `application/`) — do not "fix" that here.
- **Known limitation you will read about and should not solve here.** `deferred-work.md` (Story 1.4 review, 2026-08-05) records that the cursor is a bare integer offset not pinned to a `scenario_version`, so a fixture re-import mid-pagination can silently shift pages. It was accepted as a decision-needed finding and deferred; adding sort/filter does not change its likelihood and this story is not the place to re-open it. If you touch it, you are out of scope.
- **Deterministic ordering is the load-bearing property, not the sort UI.** AD-4's rule and AC #1's "stable-ID tie-breaks" exist so that a record cited by an agent in Epic 2 can be found on a specific page later. The tie-break assertion in Task 10 is the single most valuable test in this story; a passing filter bar with non-deterministic paging is a worse outcome than no filter bar.
- **Live regions have a specific failure mode this repo has already paid for.** Story 1.3's review fixed two: a live region that is conditionally rendered never announces (it must be mounted first, then mutated), and putting a *button* inside `role="status"` announces the control text along with the message. Task 7's copy announcement and Task 8's position announcement both hit this exact pattern — mount the region unconditionally and put only the message text inside it.
- **jsdom does not evaluate Tailwind classes.** Story 1.3's review deferred a finding that `toHaveClass("min-h-11")` proves only that a string was typed. Put the load-bearing assertions on rendered text, DOM structure, `aria-*` attributes, and the URL — keep class assertions as cheap structural guards, not as the proof.
- **Test conventions:** backend — pytest, `uv run --frozen pytest` from `backend/`, `@pytest.mark.postgres` only for tests that genuinely need a live database (they skip cleanly without one, so a pure-normalizer test must not carry the marker). Frontend — Vitest + React Testing Library, co-located `*.test.tsx`/`*.test.ts`, mock at the **hook** boundary (`vi.mock("@/hooks/useScenarioProjection")`) not at `openapi-fetch`/`client.ts`, exactly as `ScenarioWorkspace.test.tsx`/`router.test.tsx` already do. `vite.config.ts` and `src/test/setup.ts` are the single test config and setup — Radix's pointer-capture polyfills already live there, which is what makes the `DropdownMenu` in Task 9 testable.
- **Open question for the reviewer (do not block on it).** AC #2's "explanation" copy is authored in Task 9, not quoted from a spec — `EXPERIENCE.md` and `DESIGN.md` describe the behavior (*"the chooser states why"*) without giving a literal. Story 1.3's review pushed back on invented copy once already, so flag both strings in completion notes for a UX confirmation rather than treating them as settled. Every other user-visible string in this story is quoted verbatim from `EXPERIENCE.md`.

### Project Structure Notes

- **Backend, modified:** `backend/application/ports/scenario_projection.py` (add `GroupQueryV1`, change six method signatures), `backend/adapters/postgres/scenario_projection.py` (add `_apply_query` + the per-group sort/filter tables; `_slice_window` untouched), `backend/api/routers/scenario_projection.py` (typed query params on six endpoints). No new backend file, no migration, no `backend/domain/` change.
- **Backend, untouched:** `backend/migrations/**` (`alembic check` must show zero diff), `backend/api/schemas.py` (the response shape is unchanged — `total_count`/`matching_count` already exist), the seven `resolve_*` endpoints, `GET .../projection`, and the frozen legacy `store/`, `services/`, `llm/`, `ingest/` seams.
- **Generated, regenerated:** `frontend/openapi.json`, `frontend/src/api/schema.d.ts` — both in the diff, both via `npm run codegen`, neither hand-edited.
- **Frontend, new:** `frontend/src/features/scenario-data/{columns.ts,filters.ts,useGroupControls.ts,useColumnVisibility.ts,FilterBar.tsx,ColumnChooser.tsx,PaginationControls.tsx}` plus co-located tests; `frontend/src/components/primitives/IdentifierCopyButton.tsx`; shadcn copy-ins `frontend/src/components/ui/{dropdown-menu.tsx,checkbox.tsx}` (and `badge.tsx` if Story 1.6 has not already added it).
- **Frontend, modified (all created by Story 1.7):** `frontend/src/api/scenarioProjection.ts`, `frontend/src/hooks/useScenarioProjection.ts`, `frontend/src/features/scenario-data/{ScenarioDataView.tsx,ScenarioDataTable.tsx,ScenarioDataGroupState.tsx}`, `frontend/src/features/scenario-data/groups/*Panel.tsx` (six list panels adopt the descriptors + visible-column set; `OverviewPanel.tsx` is unchanged).
- **Frontend, untouched:** `frontend/package.json`, `frontend/package-lock.json` (AR27 — every Radix primitive needed is already inside the installed `radix-ui@^1.6.2` umbrella), `frontend/src/components/{editor,runs,results,scenarios}/**` (AD-25 frozen legacy), `frontend/src/App.tsx` (the route tree is Story 1.7's; this story adds only search params).
- Placement follows AR26's structural seed: `frontend/src/api` for the generated contract and client wrappers, `features/scenario-data` for this surface's components and state, `routes/` for composition only. `components/primitives/` is a peer of `components/layout/` established by Story 1.6 for cross-feature presentational components — `IdentifierCopyButton` qualifies because DESIGN.md assigns it to *"Scenario Data, Runs, Results, provenance."*

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.8: Control Scenario Data Tables, lines 504-520] — story statement and the two acceptance criteria
- [Source: epics.md#UX-DR14, UX-DR15, UX-DR16, UX-DR17, UX-DR24, lines 205, 207, 209, 211, 225] — semantic tables with visible sort/filter state and stable tie-break ordering; field-aware filters with Apply/Clear, active-filter and total/matching counts, URL serialization, and distinct filtered-empty vs intrinsically-empty copy; session-scoped chooser that cannot hide every stable ID/evidence/context column and temporarily reveals a linked hidden field; copy controls announcing "Copied {identifier type}" without implying selection or editability; no unbounded infinite scroll — bounded pagination with counts, position/range, stable-ID tie-breaks, and exact-target loading
- [Source: epics.md#UX-DR26, UX-DR29, lines 229, 235] — native keyboard/focus for sort and filter controls, Back/Forward restoration, data cells not made tabbable merely for viewing; 44×44 targets and no hover-only meaning
- [Source: epics.md#Story 1.4, lines 407-434 and #Story 1.9, lines 522-539] — the cursor/count contract this story completes; the mutation-denial audit that will inspect these controls
- [Source: .../ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md, lines 109-116] — the Large-table contract: no infinite scroll, total/matching counts, position/range, deterministic order with stable-ID tie-break, explicit first/previous/next/last, explicit header sorting, sticky headers, visibility-is-a-preference, the two literal empty strings, "Export is not implied"
- [Source: EXPERIENCE.md, lines 93-97] — behavioral contracts for Scenario Data grid, Filter bar ("Apply and Clear are explicit… serialize to the URL without mutating data"), Column chooser, and Identifier copy control
- [Source: EXPERIENCE.md, lines 124, 136-140, 189, 195] — Scenario Data state patterns; keyboard rules (header sort buttons, filters, column controls, and copy controls are tabbable; data cells are not); `<th scope>` + `aria-sort` + announced row position/total; "copy-to-clipboard feedback is announced"
- [Source: EXPERIENCE.md, lines 44-56, 58-73, 241-249] — the fixed seven-group order and vocabulary; Voice and Tone; Flow 2 ("uses Filter bar to find Wednesday outbound demand, and sorts by interval while the stable-ID tie-break remains deterministic… copies the demand and task identifiers… and clears the filters") — the concrete journey these controls must support
- [Source: .../ux-designs/ux-ShiftMind-2026-07-22/DESIGN.md, lines 134-136] — Filter bar inherits Input/Button/Popover/Select/Badge with text-labelled removable filters and no edit iconography; Column chooser inherits DropdownMenu/Popover with Checkbox items and controls visibility only; Identifier copy control inherits ghost Button + Tooltip with text/assistive copied feedback
- [Source: DESIGN.md, lines 92-96, 116, 154-155] — 24px gutters and full-width Scenario Data, `{spacing.data-cell-x}` cell padding, sticky opaque headers; the Scenario Data grid delta ("visible sort state, and no selection/edit styling"); "make read-only tables look inspectable but not editable" and "keep large-table scrolling inside a bordered region"
- [Source: .../architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md#AD-4, lines 66-70] — one immutable projection: deterministic stable ordering, bounded cursor windows with counts, exact-target lookup outside the current window, no scenario-source mutation control
- [Source: ARCHITECTURE-SPINE.md#AD-1, AD-13, AD-14, AD-20, AD-26] — hexagonal boundary (no FastAPI/SQLAlchemy in `application/`); versioned OpenAPI generating frontend types through one `openapi-fetch` client with RFC 7807 errors; TanStack Query as sole remote-cache owner and evidence navigation persisting the locator in URL/history state; `EvidenceRefV1`'s "group, record ID, optional field and minute interval"; NFR35's 2 s scenario-read allocation and "a threshold miss blocks acceptance of its owning story"
- [Source: ARCHITECTURE-SPINE.md#Consistency Conventions, Structural Seed, lines 246-309] — "Denied, stale, missing, invalid… remain distinct"; `frontend/src/{api,features,routes}` ownership; `ScenarioProjectionV1` normative minimum
- [Source: backend/api/routers/scenario_projection.py, lines 196-355] — the six list endpoints this story extends and the two the resolve path owns; the exact `Query(default=0, ge=0)` / `Query(default=50, ge=1, le=200)` declarations to preserve
- [Source: backend/application/ports/scenario_projection.py, lines 27-120] — the six `*PageV1` dataclasses (already carrying `total_count`/`matching_count`) and the reader Protocol signatures this story changes
- [Source: backend/adapters/postgres/scenario_projection.py, lines 115-330, 428-540] — the four in-memory normalizers whose output is filtered/sorted here; `_slice_window` (imported by tests — keep it); the `total, total` count pairs to replace; `nulls_last(_VERSION_ORDINAL...)` as the repo's existing null-ordering precedent
- [Source: backend/api/schemas.py, lines 182-240] — `DemandIntervalOut.family` / `.unit` `Literal` values (the exact `select` options for the demand filter) and the `*PageOut` shapes that stay unchanged
- [Source: backend/tests/test_scenario_projection.py, lines 1-80, 608-640 and backend/tests/test_postgres_integration.py, lines 202, 273] — the fixture-backed stub-reader and `TestClient` conventions to extend; the two live NFR35 measurements that must keep passing
- [Source: _bmad-output/implementation-artifacts/1-4-serve-the-normalized-scenario-read-contract.md, Task 2 and Dev Notes] — "explicit sorting is Story 1.8's acceptance boundary"; "`matching_count` = `total_count` in this story… don't build filtering logic to populate it differently"; the `record_id` schemes (`outbound:{i}`, `inbound:{i}:{k}`, `indirect:{i}`, `constraint:{i}`) that are the tie-break values
- [Source: _bmad-output/implementation-artifacts/1-7-open-the-read-only-scenario-data-workspace.md, Tasks 3-4 and Dev Notes] — the exact files, hooks, query keys, group slugs, panel columns, and `ScenarioDataTable`/`ScenarioDataGroupState` wrappers this story extends; its explicit deferrals ("No pagination/next-prev controls, no sorting, no filtering, no column chooser, no identifier copy-to-clipboard control… all named Story 1.8")
- [Source: _bmad-output/implementation-artifacts/1-6-establish-shiftmind-design-tokens-and-shared-primitives.md, Tasks 3-4 and Dev Notes] — `components/primitives/` conventions, `PRIMITIVE_FIXTURES`, the `badge.tsx` copy-in, the `--primary` token change, the "copy-in is not a dependency" precedent, and its explicit deferral of "Identifier copy control", "Filter bar", and "Column chooser" to this story
- [Source: _bmad-output/implementation-artifacts/deferred-work.md, Story 1.3 and Story 1.4 entries] — the live-region and `role="status"` fixes to preserve; the jsdom class-assertion caveat; the accepted version-unpinned-cursor limitation this story must not re-open
- [Source: frontend/src/api/scenarioCatalogue.ts, frontend/src/hooks/useScenarioContext.ts] — the thin-wrapper and `useQuery` conventions Task 5 extends, including the documented no-`staleTime` rationale
- [Source: frontend/src/components/ui/tabs.tsx, frontend/package.json, frontend/node_modules/@radix-ui/] — the `import { X as XPrimitive } from "radix-ui"` copy-in style; `radix-ui@^1.6.2` already ships `react-dropdown-menu` and `react-checkbox`, so Task 9 adds no dependency
- [Source: frontend/components.json, frontend/.oxlintrc.json, frontend/vite.config.ts, frontend/src/test/setup.ts] — why copy-ins go in `components/ui/` and ShiftMind components do not; the lint rules; the single test config and the Radix pointer-capture polyfills that make the chooser testable

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Implementation Plan

- Extend the application port, prove the server query semantics in pure unit tests, and publish typed FastAPI query parameters.
- Regenerate the OpenAPI contract, then derive frontend request/control types from that generated schema.
- Build descriptor-driven table controls, session visibility, evidence-field reveal, and identifier-copy feedback before the full cross-stack gate.

### Debug Log References

- RED: `GroupQueryV1` import failed before the port contract existed.
- RED: six projection API tests failed while handlers still passed positional cursor/limit arguments.
- GREEN: final backend regression suite — 327 passed, 6 deselected.
- GREEN: final frontend regression suite — 77 files, 367 tests.
- GREEN: typecheck, lint, production build, and Alembic no-drift check passed.

### Completion Notes List

- Added one frozen `GroupQueryV1` contract and threaded it through all six windowed projection readers.
- Added shared in-memory filter/sort/window processing with stable ascending record-ID tie-breaks and truthful total/matching counts.
- Added typed per-group API query parameters with RFC 7807 validation and fixed-order filter forwarding.
- Regenerated the OpenAPI JSON and TypeScript schema from the live backend contract.
- Derived all six frontend query types from generated OpenAPI, omitted undefined params, and keyed TanStack Query by the full control object with previous-page placeholders.
- Extracted descriptor data matching all shipped panel headers, with two required columns per group and a one-for-one backend filter vocabulary.
- Added truthful identifier-copy controls and idle/copied primitive fixtures; updated Story 1.7 panel assertions to permit copy-only interactivity.
- Added URL-owned explicit filters, sortable semantic headers, bounded paging, count/range announcements, filtered-empty branching, and in-flight table busy state.
- Added guarded per-group session column visibility and temporary `?field=` reveal; UX confirmation requested for `"{Column} is shown because an evidence link targets it."` and `"Shown for the linked evidence target."`.
- Expanded test counts from 311 to 327 backend tests and from 342 to 367 frontend tests; NFR35 live PostgreSQL proofs remained green.
- Deliberately updated Story 1.7 read-only panel assertions to allow only the new copy, sort, and pagination controls; no regression test was removed.
- Published `frontend/openapi.json` for this story by retiring its prior intermediate-only ignore rule, alongside the regenerated `schema.d.ts`.

### File List

- .gitignore
- _bmad-output/implementation-artifacts/1-8-control-scenario-data-tables.md
- _bmad-output/implementation-artifacts/sprint-status.yaml
- backend/application/ports/scenario_projection.py
- backend/adapters/postgres/scenario_projection.py
- backend/api/routers/scenario_projection.py
- backend/tests/test_scenario_projection.py
- backend/tests/test_evidence_ref.py
- backend/tests/test_postgres_integration.py
- frontend/openapi.json
- frontend/src/api/schema.d.ts
- frontend/src/api/scenarioProjection.ts
- frontend/src/api/scenarioProjection.test.ts
- frontend/src/hooks/useScenarioProjection.ts
- frontend/src/hooks/useScenarioProjection.test.tsx
- frontend/src/features/scenario-data/columns.ts
- frontend/src/features/scenario-data/columns.test.ts
- frontend/src/features/scenario-data/filters.ts
- frontend/src/features/scenario-data/filters.test.ts
- frontend/src/components/primitives/IdentifierCopyButton.tsx
- frontend/src/components/primitives/IdentifierCopyButton.test.tsx
- frontend/src/components/primitives/fixtures.tsx
- frontend/src/components/primitives/fixtures.test.tsx
- frontend/src/features/scenario-data/groups/WorkAreasAndTasksPanel.tsx
- frontend/src/features/scenario-data/groups/WorkersPanel.tsx
- frontend/src/features/scenario-data/groups/DemandPanel.tsx
- frontend/src/features/scenario-data/groups/BaselineAssignmentsPanel.tsx
- frontend/src/features/scenario-data/groups/LocksPanel.tsx
- frontend/src/features/scenario-data/groups/ConstraintsPanel.tsx
- frontend/src/features/scenario-data/groups/panelTestContract.tsx
- frontend/src/features/scenario-data/useGroupControls.ts
- frontend/src/features/scenario-data/useGroupControls.test.tsx
- frontend/src/features/scenario-data/FilterBar.tsx
- frontend/src/features/scenario-data/FilterBar.test.tsx
- frontend/src/features/scenario-data/PaginationControls.tsx
- frontend/src/features/scenario-data/PaginationControls.test.tsx
- frontend/src/features/scenario-data/ScenarioDataTable.tsx
- frontend/src/features/scenario-data/ScenarioDataTable.test.tsx
- frontend/src/features/scenario-data/ScenarioDataView.tsx
- frontend/src/features/scenario-data/ScenarioDataView.test.tsx
- frontend/src/features/scenario-data/useColumnVisibility.ts
- frontend/src/features/scenario-data/useColumnVisibility.test.tsx
- frontend/src/features/scenario-data/ColumnChooser.tsx
- frontend/src/features/scenario-data/ColumnChooser.test.tsx
- frontend/src/components/ui/dropdown-menu.tsx
- frontend/src/components/ui/checkbox.tsx
