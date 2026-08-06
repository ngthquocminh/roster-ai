---
baseline_commit: f27bafdccce7e29ae377908154f74d3141c02f2b
---

# Story 1.10: Prove Scenario Data Accessibility and Responsiveness

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the product team,
we want the viewer proven usable with assistive technology across supported viewports,
so that the planner can inspect scenario facts without losing meaning, focus, or orientation.

**This is a proof story with a real implementation tail.** Unlike Story 1.9 (pure test/evidence), this story *will* change shipping code, because two contracted behaviors do not exist yet and cannot be "proven" into existence:

1. **No global `prefers-reduced-motion` handling.** Only `Skeleton` is guarded (`motion-reduce:animate-none`, `frontend/src/components/ui/skeleton.tsx:14`). Radix `dialog`, `select`, `tooltip`, and `tabs` all ship `animate-in`/`animate-out`/`transition-*` with **no** `motion-reduce:` guard — verified directly in `frontend/src/components/ui/{dialog,select,tooltip,tabs,button,badge,input,textarea,table}.tsx`.
2. **No viewport-responsive behavior in Scenario Data.** A repo-wide grep for `sm:`/`md:`/`lg:`/`xl:` across `frontend/src/features/` and `frontend/src/routes/` returns exactly **one** hit: `ScenarioVersionContext.tsx:47` (`sm:grid-cols-3`). AC #2's "tablet stacks controls" and "phone provides read-only triage… compact essential-column default" have no implementation.

Everything else in AC #1 is largely already in place from Stories 1.6–1.8 and must be *proven*, not rebuilt. Read the "Already satisfied — do not rebuild" table in Dev Notes before writing a single line of component code.

**Depends on (all `done`, no blockers):**
- **1.6** — design tokens + shared primitives (`frontend/src/components/primitives/`), including the visual-regression fixture registry `primitives/fixtures.tsx` this story's axe sweep reuses.
- **1.7** — the workspace shell, seven-group Scenario Data surface, `ScenarioDataTable`'s captioned/`role="region"` scroll container, route-change heading focus.
- **1.8** — sort/filter/column-chooser/pagination/copy controls, `aria-sort`, the `aria-live` row-position status.
- **1.9** — proved the *rendered* surface matches the contract. This story proves the same rendered surface is *perceivable and operable*. **Do not weaken any Story 1.9 assertion.** `ScenarioDataParity.test.tsx`, `scenarioDataBoundaries.test.ts`, and `legacyReachability.test.ts` are Gate A guards; if a responsive change (e.g. the phone column default in Task 4) breaks one, fix the change or extend the guard's setup — never delete or relax the assertion.

**Unblocks:** Story 1.11 (Gate A readiness rolls this story's evidence into `evidence/story-1.11/gate-a-readiness-report.json`).

**Scope boundary — this story is Gate A only.** Story 4.9 ("Prove Responsive WCAG Conformance", epics.md:1320) owns the *completed journey* across the full support matrix. Story 4.6 owns approval-journey accessibility; 4.7 owns cross-workflow visual regression; 4.8 owns literal-state semantics. This story covers **only** the surfaces that exist at Gate A: Fixture catalogue (`/`), workspace tabs + scenario/version context, and Scenario Data (all seven groups + their controls). Chat, Runs, and Results are route placeholders — do not write accessibility tests against them, and do not build the phone "direct Maya to desktop" copy for composer/run/approval controls that Epic 2/3 have not created yet.

## Acceptance Criteria

1. **Given** keyboard-only use, screen-reader use, reduced motion, text-spacing changes, and 200% zoom, **when** the planner navigates catalogue, workspace tabs, group controls, filters, tables, copy controls, and exact targets, **then** headings, focus order, captions, `aria-sort`, status text, row position, touch targets, and contained scrolling satisfy WCAG 2.2 AA, **and** no meaning depends on color, hover, motion, or page-level horizontal scrolling. *(NFR18, NFR20, UX-DR26, UX-DR27, UX-DR29)*

2. **Given** desktop, tablet, and phone viewports, **when** Scenario Data is inspected, **then** desktop supports the full wide data workspace, tablet stacks controls with contained scroll, and phone provides read-only triage, **and** server authorization never depends on viewport. *(UX-DR28, UX-DR31)*

## Tasks / Subtasks

- [ ] **Task 1: Stand up the two-layer accessibility harness** (AC: #1, #2)
  - [ ] **Layer A — jsdom (Vitest), already the repo default.** Add `axe-core@4.13.0` and `jest-axe@11.0.0` as `devDependencies` in `frontend/package.json`. Wire the matcher once in `frontend/src/test/setup.ts` via `expect.extend(toHaveNoViolations)` — do **not** add a per-file `expect.extend`. `jest-axe` is Jest-API-shaped but works unmodified under Vitest's `globals: true` (already set in `vite.config.ts:26`); `vitest-axe` is at 0.1.0 and unmaintained — **do not use it**.
  - [ ] **Layer B — real browser (Playwright).** Add `@playwright/test@1.62.1` and `@axe-core/playwright@4.12.1` as `devDependencies`. Create `frontend/playwright.config.ts` + `frontend/e2e/`. **Layer B is mandatory, not optional**: jsdom has no layout engine (`offsetWidth`/`scrollWidth` are always `0`), so 200% zoom, reflow, text-spacing, page-level horizontal scroll, and 44×44 touch targets are *unprovable* in Layer A. A jsdom-only "pass" on those would be a completion lie.
  - [ ] `playwright.config.ts`: `webServer` runs `npm run build && npm run preview` (deterministic built assets, not the dev server); projects `chromium` and `msedge` (`channel: 'msedge'`) to match EXPERIENCE.md:196's declared matrix. Add `npm run test:e2e` (`playwright test`) and `npm run test:a11y` scripts. Do **not** add Playwright to the default `npm test` — keep `vitest run` fast; the e2e gate is a separate command reported in Task 8.
  - [ ] **No live backend in e2e.** Stub every API call with `page.route()` served from the committed Story 1.9 artifacts `data/contract/sample_tiny_input.projection-v1.json` and `data/contract/sample_tiny_input_more_tm.projection-v1.json`. Routes to intercept (exact paths, from `frontend/src/api/`): `GET /api/v1/auth/session` (return a session + `csrf_token` so `RequireSession` admits), `GET /api/v1/scenarios`, `GET /api/v1/scenarios/{id}` (context), `GET /api/v1/scenarios/{id}/projection`, and the six `…/projection/{group}` pages. This keeps CI keyless and Postgres-free, matching the repo's deterministic-first rule (ARCHITECTURE-SPINE.md:184).
  - [ ] **`target-size` is disabled by default in axe-core and must be explicitly enabled.** WCAG 2.5.8 is the *only* WCAG 2.2 rule axe ships, tagged `wcag22aa`, `"enabled": false`. Passing the tag alone will silently not run it. Configure every axe run as:
    ```ts
    new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
      .options({ rules: { 'target-size': { enabled: true } } })
    ```
    Tag matching is strict equality with **no hierarchy** — `wcag2aa` does *not* imply `wcag21aa` or `wcag22aa`. All five tags are required.
  - [ ] `color-contrast` cannot run in jsdom (no computed layout/paint). Run it **only** in Layer B. Do not assert contrast in Vitest.

- [ ] **Task 2: Semantic, ARIA, and keyboard conformance (Layer A)** (AC: #1)
  - [ ] New `frontend/src/test/accessibility.test.tsx`: axe-clean sweep over `FixtureCatalogueView` (loading/empty/error/loaded/stale), `ScenarioWorkspace` (pending/terminal/error/loaded), and `ScenarioDataView` for **all seven groups** in loading/empty/error/loaded states. Mock at the **hook** boundary (`vi.mock("@/hooks/useScenarioProjection")`, `useScenarioContext`, `useFixtureCatalogue`) — never `openapi-fetch`/`client.ts`. This is the repo's fixed convention (Story 1.9 Dev Notes).
  - [ ] Also sweep every entry in `frontend/src/components/primitives/fixtures.tsx` (Story 1.6's VR registry — `StatusBadge`, `InlineAlert`, `Skeleton`, `EmptyState`, `ReconnectBanner`, `EvidenceLink`, `EvidenceHighlight`, `IdentifierCopyButton`, all states). Iterate the exported registry; do not hand-list states, or the sweep silently rots when 1.6's registry grows.
  - [ ] **Explicit assertions axe cannot make** (axe finds violations, not contract conformance — a clean axe run is necessary, not sufficient):
    - Heading hierarchy per surface: catalogue `h1` (`routes/FixtureCatalogue.tsx:26`); workspace `h1` in `ScenarioVersionContext` + `h2` "Scenario Data" (`ScenarioDataView.tsx:41`); no skipped level.
    - Route-change focus lands on the view heading (`ScenarioVersionContext` `h1[tabindex=-1]`, `ScenarioWorkspace` terminal headings) and fires **exactly once** — `ScenarioWorkspace.tsx:22-30` documents a prior bug where two focus calls interrupted a screen reader mid-announcement. Add a regression assertion, do not just re-verify manually.
    - Tab order follows visual reading order across: workspace tabs → group tabs → column chooser → filter fields → Apply/Clear/active-filter chips → sortable headers → in-cell copy buttons → pagination. Assert with `userEvent.tab()` sequences, not by reading the DOM.
    - Data cells are **not** in the tab order (EXPERIENCE.md:136) — only header sort buttons, filters, column controls, links, and copy controls are tabbable.
    - `aria-sort` is `ascending`/`descending` on exactly one column and absent (not `"none"`) on non-sortable columns. `ScenarioDataTable.test.tsx:14-21` already asserts this for `demand` — **extend that file's coverage to all six list groups rather than writing a parallel test.**
    - Every group table has an `sr-only` `<TableCaption>` and a `role="region"` + `aria-label` + `tabIndex={0}` scroll container (`ScenarioDataTable.tsx:32-34`) so keyboard users can scroll it (WCAG 2.1.1).
    - Row position announces through `PaginationControls`' `aria-live="polite" role="status"` sr-only span (`PaginationControls.tsx:44`), including the `itemCount === 0` stale-cursor branch.
    - Copy feedback announces "Copied {identifier type}" and the failure copy through `IdentifierCopyButton`'s polite live region (`IdentifierCopyButton.tsx:60`).
    - Evidence-target reveal: the `ColumnChooser` explanation ("… is shown because an evidence link targets it", `ScenarioDataView.tsx:54`) is present and the revealed column's checkbox is `disabled`, so a revealed evidence target cannot be hidden again mid-navigation.
    - `Escape` closes the `ColumnChooser` and each filter `Select` and returns focus to its trigger, committing nothing (EXPERIENCE.md:138).
  - [ ] **No color-only meaning** (AC #1's "no meaning depends on color, hover, motion"): assert the active workspace tab carries `aria-current` (not only the indigo class) and the active group tab carries `data-state="active"`/`aria-selected`; assert active-filter chips carry text labels (`FilterBar.tsx:52`); assert nothing in Scenario Data is reachable only on hover. **jsdom does not evaluate Tailwind classes** (repeated caveat from Story 1.3/1.8/1.9 reviews) — assert on ARIA/DOM/text, never on class-name presence. Class-level checks belong in Layer B.

- [ ] **Task 3: Implement and prove reduced motion** (AC: #1)
  - [ ] **Implementation.** Add a global guard to `frontend/src/index.css` inside `@layer base`, honoring `@media (prefers-reduced-motion: reduce)`: neutralize `animation-duration`/`transition-duration` (`0.01ms !important`), `animation-iteration-count: 1`, and `scroll-behavior: auto`. This is the minimum that covers the unguarded Radix `data-open:animate-in`/`data-closed:animate-out` on `dialog.tsx:42,64`, `select.tsx:70`, `tooltip.tsx:45` and the `transition-*` on `button.tsx:8`, `badge.tsx:7`, `input.tsx:11`, `select.tsx:45`, `table.tsx:60`, `tabs.tsx:64,67`, `textarea.tsx:10`.
  - [ ] **Do not** remove the animation classes themselves and do not fork the shadcn `ui/` components — `ui/` is vendored shadcn and the project's convention (Story 1.6) is ShiftMind deltas via tokens/global CSS, not component forks. `Skeleton`'s existing `motion-reduce:animate-none` stays; the global rule is additive.
  - [ ] **Status text must survive.** EXPERIENCE.md:193 — reduced motion disables non-essential transition/spin, but every status string stays rendered. Assert in Layer B (with `emulateMedia({ reducedMotion: 'reduce' })`) that the pagination row-position status, the group loading `role="status"` label ("Loading scenario data", `ScenarioDataGroupState.tsx:30`), and the stale banner text are all still present and non-empty.
  - [ ] **Evidence highlight never animates** (DESIGN.md:115 — "reduced-motion and default behavior are visually identical"; EXPERIENCE.md:144 — "evidence targeting never flashes or pulses"). Assert `EvidenceHighlight` renders identically under `reducedMotion: 'reduce'` and `'no-preference'`.

- [ ] **Task 4: Implement and prove responsive behavior** (AC: #2)
  - [ ] **Breakpoints are fixed by EXPERIENCE.md:179-181 — use these exact values, do not invent others:** desktop `≥1024px`, tablet `768–1023px`, phone `<768px`. Tailwind's `md` (768px) and `lg` (1024px) map exactly; use `md:`/`lg:` and never a custom breakpoint.
  - [ ] **Desktop — already correct, verify only.** `ScenarioWorkspace.tsx:121` renders `<main className="px-6 py-8">` with no `max-w-*`, so Scenario Data already expands within the 24px gutter (DESIGN.md:94). Chat/Runs/Results keep the centered reading column. **Do not add a max-width to the workspace main.**
  - [ ] **Tablet — controls stack.** `ScenarioDataView.tsx:52-56` currently emits a fixed `flex justify-end` chooser row + `FilterBar`'s `flex flex-wrap`. Make the control cluster stack below `lg`. Group navigation **already satisfies** the contract: EXPERIENCE.md:180 permits "a Select **or horizontal list**", and `ScenarioDataView.tsx:46-50` is a horizontally scrollable `TabsList` with `min-w-max`. **Do not replace the group Tabs with a Select** — that is unnecessary rework of a compliant surface. Same for `WorkspaceTabs.tsx:16` (`overflow-x-auto` + `min-w-max whitespace-nowrap`), which already keeps labels untruncated per EXPERIENCE.md:180.
  - [ ] **Phone — compact essential-column default.** The only genuinely missing piece. `useColumnVisibility.ts` has no viewport awareness. Add a phone default that hides non-essential columns on first render below `768px`, subject to two hard invariants that already exist and must not be violated:
    - `column.required` columns can never be hidden (`useColumnVisibility.ts:31,36`) — the phone default must go through the same `required` filter, not around it.
    - An evidence-revealed column (`revealedColumn`) always wins over any default (`useColumnVisibility.ts:29-31`), so a phone-hidden field still becomes visible when an evidence locator targets it (UX-DR16 / Story 1.8 AC #2).
    - The default is a **viewing preference, not data configuration** (EXPERIENCE.md:114) — it must remain overridable via the existing `ColumnChooser` and must reuse the existing `sessionStorage` key shape `shiftmind.columns.{group}`. Do **not** add a second persistence mechanism. An explicit user choice already stored for that group wins over the phone default.
    - Add the `essential` flag to `columns.ts`'s `ColumnDef` (beside the existing `required`/`sortKey`) so the essential set is declared once per group, not computed by index or guessed at render time.
    - Use `window.matchMedia("(max-width: 767px)")` behind a small hook; `matchMedia` is **not implemented in jsdom** — add a `matchMedia` polyfill to `frontend/src/test/setup.ts` alongside the existing `hasPointerCapture`/`releasePointerCapture`/`scrollIntoView` no-ops, following that file's documented-comment style.
  - [ ] **Phone read-only triage is otherwise already satisfied** — Scenario Data has no composer, draft, run, cancel, or approval control (Story 1.9's `scenarioDataBoundaries.test.ts` proves it). Do **not** build the "direct Maya to desktop" copy from EXPERIENCE.md:181; there is no consequential control at Gate A for it to gate. Note this scope call in completion notes.
  - [ ] **Server authorization never depends on viewport** (AC #2's second clause — a *backend* obligation, easy to skip). New backend test (extend `backend/tests/test_scenario_projection.py` or the Story 1.9 file `backend/tests/test_gate_a_mutation_audit.py`): issue the same projection request with desktop, tablet, and phone `User-Agent` strings plus `Sec-CH-UA-Mobile: ?1`/`?0` and `Viewport-Width` headers, and assert byte-identical authorized responses **and** identical denial behavior for an unauthenticated/cross-site request. First-party backend code reads no UA or client hints today (verified: the only `user-agent` hits under `backend/` are vendored `authlib`) — this test is the regression lock on that fact.

- [ ] **Task 5: Browser-level proofs — zoom, reflow, text spacing, targets, contained scroll (Layer B)** (AC: #1, #2)
  - [ ] Run the Task-1 axe configuration (all five WCAG tags + `target-size` enabled + `color-contrast`) at each viewport — desktop `1280×800`, tablet `900×1024`, phone `390×844` — over `/` and `/scenarios/:id/data` for **every** group, with a filter applied, a column hidden, and the chooser open. Zero violations.
  - [ ] **200% zoom.** Playwright has no zoom API; the accepted equivalent is halving the CSS viewport at the same content scale (`1280×800` → `640×400`). Assert at that size: no page-level horizontal scroll, no control hidden or clipped, all status text still readable.
  - [ ] **No page-level horizontal scrolling** (AC #1's explicit clause, and DESIGN.md:94/155 "horizontal overflow stays inside the grid region, never on the page"). Assert `document.documentElement.scrollWidth <= document.documentElement.clientWidth` at every viewport above **and** at 320 CSS px, on the widest group (`demand`, 1,547 rows / 7 columns, per Story 1.9's counts). Then assert the *table region itself* does scroll: its `scrollWidth > clientWidth` with the `role="region"` container reachable by keyboard.
  - [ ] **Text spacing (WCAG 1.4.12).** `page.addStyleTag` with the standard bookmarklet values — `line-height: 1.5`, `letter-spacing: 0.12em`, `word-spacing: 0.16em`, paragraph spacing `2em` — applied to `*`. Assert no clipped or overlapped content and no lost control. Pay attention to `whitespace-nowrap` on `WorkspaceTabs.tsx:17` and `badge.tsx`/`button.tsx`, and to the `line-clamp-1` on `select.tsx:45`'s value.
  - [ ] **Touch targets ≥ 44×44 CSS px** (EXPERIENCE.md:183 — stricter than axe's WCAG 2.5.8 threshold of 24px, so axe passing is not enough). Measure `boundingBox()` for every interactive element in Scenario Data. Known-good: `IdentifierCopyButton` (`min-h-11 min-w-11`, `IdentifierCopyButton.tsx:48`), pagination/Apply/Clear/chips/chooser trigger (`min-h-11`). **Known risks to fix, not to explain away:** the sort header `<button className="min-h-11">` (`ScenarioDataTable.tsx:18`) has no min-width — a short header like "Unit" will be under 44px wide; and `DropdownMenuCheckboxItem` (`ui/dropdown-menu.tsx:20`, `py-2 text-sm`) is ~36px tall. Fix by adding width/height at the **call site** (`ScenarioDataTable.tsx`, `ColumnChooser.tsx`), not by editing vendored `ui/` primitives.
  - [ ] **Sticky header opacity** (DESIGN.md:100 — "text never layers visually over scrolled content"). `ScenarioDataTable.tsx:33` sets `[&_thead]:sticky [&_thead]:bg-muted`. Assert the computed `background-color` of the sticky `thead` is fully opaque (alpha `1`) at every viewport.
  - [ ] **Keyboard-only journey, real browser:** sign-in-stubbed load → catalogue row activation → workspace tab → group tab → sort → filter Apply → page Next → copy an identifier → hide a column — entirely via `keyboard.press`, asserting a visible focus indicator at every stop (`focus-visible:ring-3 focus-visible:ring-ring/50` is the established pattern) and that focus is never lost to `<body>`.

- [ ] **Task 6: Manual screen-reader pass (NVDA) — recorded, not automated** (AC: #1)
  - [ ] EXPERIENCE.md:196 names NVDA on Windows in the portfolio-minimum matrix, and AC #1 says "screen-reader use". No automated tool proves this; **do not claim it via axe.** Write `docs/ACCESSIBILITY-NVDA-CHECKLIST.md` (flat, uppercase — matches the existing `docs/TESTING.md`, `docs/API.md` convention; `docs/` has no topic subdirectories) with one row per AC-#1 obligation — heading announcement on route change, table caption + column-header association, `aria-sort` change announcement, row-position announcement on page change, "Copied {identifier type}", the evidence-reveal explanation, and the disabled-Results explanation (`WorkspaceTabs.tsx:33-45`) — each with expected utterance, observed utterance, and pass/fail.
  - [ ] Execute it once against `npm run preview` with NVDA + Chrome and NVDA + Edge, and record the dated result. If NVDA is unavailable in the execution environment, record `"nvda_manual_pass": "not executed — <reason>, <date>"` in Task 7's evidence and flag it in completion notes. **Do not report it as passed, and do not silently omit the field** — same posture Story 1.9 took with `legacy_route_live_flag_state`.

- [ ] **Task 7: Record Gate A evidence** (AC: #1, #2)
  - [ ] Write `evidence/story-1.10/scenario-data-accessibility-and-responsiveness.json`, following the exact shape of `evidence/story-1.9/gate-a-viewer-parity-and-mutation-denial.json` (read it first; it is the template): `story`, `requirements` (`NFR18`, `NFR20`, `UX-DR26`–`UX-DR29`, `UX-DR31`), `measurement_date`, `fixtures` with the two Gate A fixture identities, per-check `results`, `test_evidence` commands + counts, `version_bindings` (NFR27: dataset/evaluator/tool/policy/application/scenario/code/image), and top-level `passed`.
  - [ ] `results` must name each check separately — `axe_jsdom`, `axe_browser`, `keyboard_journey`, `reduced_motion`, `zoom_200`, `text_spacing`, `no_page_horizontal_scroll`, `touch_targets_44px`, `contained_table_scroll`, `responsive_desktop`, `responsive_tablet`, `responsive_phone`, `authorization_viewport_independent`, `nvda_manual_pass` — plus `browsers_tested` and `viewports_tested`. A single aggregate `"passed": true` with no per-check breakdown is not acceptable: NFR29 requires a failure to name the exact gate.
  - [ ] Bind `axe_core_version`, `playwright_version`, and the enabled-rule delta (`target-size: enabled`) so a future axe upgrade that changes rule coverage is visible in the record.

- [ ] **Task 8: Full regression gate**
  - [ ] Frontend: `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`, `npm run test:e2e`. Report file/test counts before and after (baseline at `f27bafd`: **47 files, 200 tests**).
  - [ ] Backend: `uv run --frozen pytest` from `backend/` (baseline **349 passed, 6 deselected**) — Task 4's viewport-independence test is the only backend addition. `uv run --frozen pytest -m postgres` needs a live local PostgreSQL and skips cleanly without one. `alembic check` must show zero diff (this story adds no migration).
  - [ ] **Re-run Story 1.9's Gate A guards explicitly** and report them by name: `ScenarioDataParity.test.tsx`, `scenarioDataBoundaries.test.ts`, `legacyReachability.test.ts`. The phone column default (Task 4) is the most likely thing to perturb the parity test's rendered-cell expectations — if it does, set the parity test's environment to the desktop viewport rather than loosening its assertions.
  - [ ] Record the new `devDependencies` and their versions in completion notes; ARCHITECTURE-SPINE.md:263 requires planned stack rows to be "added to manifests and lockfiles by their implementation gate before use" — commit the `package-lock.json` change.

## Dev Notes

### Already satisfied — verify, do not rebuild

Story 1.6–1.8 already shipped most of AC #1's surface. Re-implementing any of this is wasted work and will fight existing tests.

| AC #1 obligation | Already implemented at | Your job |
|---|---|---|
| Table caption | `ScenarioDataTable.tsx:34` (`sr-only` `TableCaption`) | assert, all 6 groups |
| `aria-sort` | `ScenarioDataTable.tsx:17`; asserted for `demand` in `ScenarioDataTable.test.tsx:14-21` | extend to all 6 groups |
| Contained two-axis scroll | `ScenarioDataTable.tsx:32-33` (`role="region"`, `tabIndex={0}`, `overflow-auto`, `[&_[data-slot=table-container]]:overflow-visible`) | assert real scrollWidth in Layer B |
| Sticky opaque header | `ScenarioDataTable.tsx:33` (`[&_thead]:sticky [&_thead]:bg-muted`) | assert computed alpha = 1 |
| Row-position status | `PaginationControls.tsx:44` (`aria-live="polite" role="status"`) | assert, incl. zero-item branch |
| Copy announcement | `IdentifierCopyButton.tsx:60` + failure copy at `:7` | assert both branches |
| Route-change heading focus | `ScenarioVersionContext.tsx:15` + `ScenarioWorkspace.tsx:22-30` | assert fires exactly once |
| Disabled-Results explanation | `WorkspaceTabs.tsx:33-45` (`aria-describedby`, deliberate — read the comment) | assert, don't "fix" the span |
| Skeleton reduced motion | `ui/skeleton.tsx:14` (`motion-reduce:animate-none`) | keep; add the global rule around it |
| Column-chooser floor | `useColumnVisibility.ts:31,36` (`required` never hidden; revealed column locked) | route the phone default through it |
| Empty-state copy | `ScenarioDataTable.tsx:27` filtered-empty; `ScenarioDataGroupState.tsx:66` intrinsically-empty | assert both, they are different strings by contract |

### Anti-patterns for this story

- **Do not fork `frontend/src/components/ui/*`.** It is vendored shadcn. Reduced motion goes in `index.css`; touch-target sizing goes at the call site via `className`.
- **Do not assert on Tailwind class names in jsdom.** jsdom does not evaluate them (Story 1.3/1.8/1.9 review caveat). Any check that needs computed style or geometry belongs in Layer B.
- **Do not mock `openapi-fetch`/`client.ts` in Vitest.** Mock at the hook boundary — fixed repo convention.
- **Do not add a new state manager or a second column-visibility store.** Extend `useColumnVisibility`.
- **Do not run axe with `.withTags(['wcag22aa'])` alone** and assume WCAG 2.2 AA coverage. It is one rule (`target-size`), disabled by default. See Task 1.
- **Do not treat a clean axe run as proof of AC #1.** Automated tooling catches roughly a third of WCAG issues; the explicit assertions in Task 2 and the manual pass in Task 6 are what make the claim honest.
- **Do not extend scope to Chat/Runs/Results** — placeholders at Gate A, owned by Stories 4.6–4.9.

### Latest tooling facts (verified 2026-08-06 against the npm registry and axe-core docs)

- `axe-core@4.13.0` — `target-size` is the **only** WCAG 2.2 rule, tagged `wcag22aa`, `"enabled": false` by default. Tag matching is strict equality with no version hierarchy (`lib/core/utils/rule-should-run.js`), so all five tags must be listed explicitly.
- `jest-axe@11.0.0` — current; use with Vitest via `expect.extend(toHaveNoViolations)`. `vitest-axe` is 0.1.0 and stale; do not use.
- `@playwright/test@1.62.1`, `@axe-core/playwright@4.12.1` — `page.emulateMedia({ reducedMotion: 'reduce' })` is the supported reduced-motion control (it flips `matchMedia('(prefers-reduced-motion: reduce)')`); `reducedMotion` is also settable in `config.use`. `page.setViewportSize()` / `test.use({ viewport })` covers the viewport matrix.
- Node.js target is **24.18.0 LTS** (ARCHITECTURE-SPINE.md:277); Playwright 1.62 requires Node ≥ 18, so no conflict.

### Open questions for the reviewer (do not block Tasks 2–4 on these)

1. **Is introducing Playwright at Story 1.10 acceptable, or should the browser-dependent half defer to Story 4.9?** The story as written adds it here because AC #1 names 200% zoom and AC #1/#2 name page-level horizontal scroll and touch targets — none of which jsdom can evaluate, so deferring means Gate A ships an accessibility claim it did not test. Story 4.9 then *reuses* this harness across the completed journey rather than building it late. If product prefers to defer, the fallback is: keep Layer A, record every Layer-B check as `"deferred — Story 4.9, no browser harness at Gate A"` in Task 7's evidence, and say so in Story 1.11's readiness report. **Do not silently downgrade to a jsdom-only pass.**
2. **There is no CI workflow in this repo** (`.github/workflows/` does not exist). Task 8's gates are local commands. Whoever owns CI should decide whether `test:e2e` becomes a required check; that is a pipeline decision, not this story's.
3. **The phone essential-column set is authored here.** No planning artifact enumerates which columns are "essential" per group — EXPERIENCE.md:181 says only "a compact essential-column default". The `essential` flag in `columns.ts` makes the choice explicit and reviewable; flag it for product confirmation, same posture Story 1.8 took with its invented column-chooser explanation copy and Story 1.9 took with `data/contract/`.

### Project Structure Notes

- **Frontend, new:** `frontend/playwright.config.ts`; `frontend/e2e/` (accessibility, responsive, keyboard-journey specs + the `page.route()` contract-stub helper); `frontend/src/test/accessibility.test.tsx`.
- **Frontend, modified:** `frontend/package.json` + `package-lock.json` (four devDependencies, two scripts); `frontend/src/test/setup.ts` (axe matcher + `matchMedia` polyfill); `frontend/src/index.css` (global reduced-motion rule); `frontend/src/features/scenario-data/ScenarioDataView.tsx` (tablet control stacking); `useColumnVisibility.ts` + `columns.ts` (phone essential-column default); `ScenarioDataTable.tsx` + `ColumnChooser.tsx` (touch-target sizing at call site); `ScenarioDataTable.test.tsx` (aria-sort across all groups).
- **Frontend, untouched:** `components/ui/**` (vendored shadcn), `api/**`, `hooks/**` except where Task 4 needs the viewport hook. No new route, no new API call.
- **Backend, modified:** one viewport-independence test (Task 4). No production module, no migration, no route change.
- **New:** `evidence/story-1.10/scenario-data-accessibility-and-responsiveness.json`; `docs/ACCESSIBILITY-NVDA-CHECKLIST.md` (flat, uppercase — matches the existing `docs/TESTING.md`, `docs/API.md` convention; `docs/` has no topic subdirectories).
- Placement follows the established `evidence/story-N/`, co-located `*.test.tsx`, and `frontend/src/test/` conventions. `frontend/e2e/` is the one new directory (Playwright's own convention, outside `src/`).
- **TypeScript wiring is not automatic — verified, not assumed.** `tsconfig.app.json:32` includes only `["src"]` and `tsconfig.node.json:22` only `["vite.config.ts"]`, so `e2e/**` and `playwright.config.ts` are covered by **neither** project: they would ship untyped and `npm run typecheck` would pass vacuously over them. Add `playwright.config.ts` to `tsconfig.node.json`'s `include`, and add a `tsconfig.e2e.json` (extending the app config, `include: ["e2e"]`, `types: ["@playwright/test"]`) referenced from the root `tsconfig.json`. Also confirm Vitest does not collect `e2e/**` — its default include glob would otherwise try to run Playwright specs under jsdom; scope `test.include` in `vite.config.ts` to `src/**` if it does.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.10, lines 541-557] — story statement and both acceptance criteria, verbatim
- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.11, lines 559-575] — the Gate A readiness rollup this story's evidence feeds
- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.9, lines 1320-1336; #4.6-4.8, lines 1276-1318] — the later full-journey accessibility/visual/state proofs this story must not absorb
- [Source: _bmad-output/planning-artifacts/requirements-inventory.md, lines 39-41] — NFR18 (WCAG 2.2 AA, keyboard-operable, meaningful status text) and NFR20 (200% zoom, text spacing, reduced motion must not hide controls, create page-level horizontal scroll, or remove status meaning)
- [Source: .../ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md#Accessibility Floor, lines 185-196] — landmarks/headings, route-change focus, caption + `th scope` + `aria-sort`, announced row position, text-not-color status, polite live regions, reduced motion, 200% zoom and text spacing, and the NVDA/Chrome/Edge support matrix
- [Source: .../EXPERIENCE.md#Responsive & Platform, lines 175-183] — the exact `≥1024` / `768–1023` / `<768` breakpoints, tablet stacking, phone read-only triage with compact essential-column default, viewport-independent authorization, and the 44×44 touch-target floor
- [Source: .../EXPERIENCE.md#Interaction Primitives, lines 130-144] — tab/enter/space semantics, data cells not tabbable, `Escape` returns focus to trigger, browser Back/Forward restores state, hover never the only affordance
- [Source: .../EXPERIENCE.md#Large-table contract, lines 109-116] — counts/position/order contract, sticky headers, column visibility as a viewing preference, and the two distinct empty-state strings
- [Source: .../DESIGN.md, lines 94, 100, 115, 155] — horizontal overflow contained in the grid region never the page; opaque sticky surfaces; evidence highlight identical under reduced motion
- [Source: _bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md, lines 184, 263, 277] — accessibility regressions block release; planned stack rows must reach manifests/lockfiles at their implementation gate; Node 24.18.0 LTS target
- [Source: _bmad-output/implementation-artifacts/1-9-prove-viewer-parity-and-mutation-denial.md] — the Gate A guards not to weaken (`ScenarioDataParity.test.tsx`, `scenarioDataBoundaries.test.ts`, `legacyReachability.test.ts`), the hook-boundary mocking convention, the jsdom/Tailwind caveat, and the two committed `data/contract/*.projection-v1.json` artifacts this story's e2e stubs reuse
- [Source: evidence/story-1.9/gate-a-viewer-parity-and-mutation-denial.json] — the exact evidence-file shape Task 7 follows, including per-check `results` and NFR27 `version_bindings`
- [Source: frontend/src/features/scenario-data/ScenarioDataTable.tsx, ScenarioDataView.tsx, FilterBar.tsx, ColumnChooser.tsx, PaginationControls.tsx, useColumnVisibility.ts, ScenarioDataGroupState.tsx] — the exact surfaces under test and the current absence of any breakpoint handling
- [Source: frontend/src/components/ui/{dialog,select,tooltip,tabs,button,badge,input,textarea,table}.tsx] — the unguarded `animate-in`/`animate-out`/`transition-*` declarations Task 3's global rule must cover
- [Source: frontend/src/components/primitives/IdentifierCopyButton.tsx, fixtures.tsx; frontend/src/features/scenario-workspace/WorkspaceTabs.tsx, ScenarioVersionContext.tsx; frontend/src/routes/ScenarioWorkspace.tsx, FixtureCatalogue.tsx] — existing live-region, focus-management, and heading behavior to assert rather than re-implement
- [Source: frontend/vite.config.ts, frontend/src/test/setup.ts] — `globals: true` (jest-axe works unmodified), the jsdom polyfill file and its documented-comment style Task 4's `matchMedia` shim follows
- [Source: axe-core 4.13.0 — lib/rules/target-size.json, lib/core/utils/rule-should-run.js, doc/API.md] — `target-size` is the only `wcag22aa` rule and is disabled by default; tag matching is strict equality with no version hierarchy
- [Source: Playwright 1.62.1 — docs/src/emulation.md, tests/page/page-emulate-media.spec.ts, docs/src/accessibility-testing-js.md] — `emulateMedia({ reducedMotion })`, viewport control via `test.use`/`setViewportSize`, and the `AxeBuilder(...).analyze()` scan pattern

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List

## Change Log

- 2026-08-06: Story created — Gate A accessibility and responsiveness proof scoped to catalogue, workspace shell, and Scenario Data, with the two implementation gaps (global reduced motion, viewport-responsive behavior) identified against the landed 1.6–1.9 surface.
