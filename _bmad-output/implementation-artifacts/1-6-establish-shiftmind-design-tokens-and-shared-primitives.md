---
baseline_commit: e925c07965a363f7f0a6aae73b4bfddcd3842e4d
---

# Story 1.6: Establish ShiftMind Design Tokens and Shared Primitives

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a product engineer,
I want the ShiftMind visual tokens and shared workspace primitives established before the first data UI,
so that every later story implements its visual contract once instead of retrofitting consistency.

**[Technical Enabler] — no new planner-visible surface.** This story adds no route, no query hook, no API call, and no backend code. It changes `frontend/src/index.css`, adds seven reusable presentational components plus their state fixtures, and adopts three of them in the two surfaces Story 1.3 already shipped. **`frontend/` is the only directory this story touches.**

**Depends on:** Story 1.3 (done) — created `frontend/src/features/`, the live route tree (`FixtureCatalogue`, `ScenarioWorkspace`), the shadcn `Skeleton` copy-in, `USER_ERROR_COPY`, and the co-located Vitest/RTL test convention. Its Task 4 explicitly deferred token work here: *"Do not build the ShiftMind token layer… If you need a Skeleton, add the standard shadcn primitive — Story 1.6 will govern it, not replace it."*
**Unblocks:** Story 1.7 (workspace shell + seven Scenario Data groups), 1.8 (table controls), 1.10 (accessibility/responsive proof), 2.8 (evidence navigation consumes `EvidenceLink`/`EvidenceHighlight`), 3.12 and 4.7 (both name *"the Story 1.6 shared primitives"* and render *"visual-regression fixtures"* built here).

## Acceptance Criteria

1. **Given** the existing shadcn/Tailwind/Radix theme, **when** ShiftMind design tokens are consolidated, **then** primary/evidence/focus colors, evidence/data radii, 24px workspace gutter, 8px table-cell spacing, system typography, metric ramp, and identifier monospace match `DESIGN.md`, **and** inherited neutral, destructive, card, popover, input, muted, border, chart, elevation, radius, and optional dark-theme tokens remain unchanged. *(UX-DR30, UX-DR33)*

2. **Given** the shared Status badge, Inline alert, Skeleton, Empty state, Reconnect banner, Evidence link, and quiet highlight primitives, **when** they are implemented as reusable components, **then** each has visual-regression fixtures covering its states without color-only meaning, **and** each subsequent UI story implements its component-specific visual contract in that story rather than deferring it. *(UX-DR23, UX-DR32, UX-DR34)*

## Tasks / Subtasks

- [ ] Task 1: Consolidate ShiftMind tokens into `frontend/src/index.css` (AC: #1)
  - [ ] **Mechanism — follow the file's existing two-part pattern exactly:** raw values as CSS custom properties in `:root`, then mapped into the `@theme inline` block so Tailwind generates utilities. Do not invent a second mechanism, do not add a `tailwind.config.js` (Tailwind 4.3.2 via `@tailwindcss/vite` is config-file-free; `components.json` sets `"tailwind.config": ""`), and do not add a package.
  - [ ] **Colors — write the `DESIGN.md` hex values verbatim.** The inherited palette is `oklch`; do **not** convert these to `oklch` (a hand-converted value silently drifts from the design contract and from the contrast test in Task 5). New `:root` vars: `--evidence-link: #4338CA`, `--evidence-surface: #EEF2FF`, `--evidence-border: #C7D2FE`, `--evidence-foreground: #1E1B4B`.
  - [ ] **Changed inherited vars — exactly three, in `:root` only:** `--primary: #4F46E5`, `--primary-foreground: #FFFFFF`, `--ring: #4F46E5` (`DESIGN.md`'s `{colors.focus-ring}`). AC #1's "inherited … remain unchanged" list names neutral, destructive, card, popover, input, muted, border, chart, elevation, radius, and dark-theme — `primary`, `primary-foreground`, and the focus ring are **not** on it, and `DESIGN.md`'s "inherit unchanged" sentence omits them too. `DESIGN.md`: *"Primary indigo (`#4F46E5`) retains the implemented scenario-tab accent."*
  - [ ] **Do not touch the `.dark` block.** AC #1 requires "optional dark-theme tokens remain unchanged" and UX-DR33 says dark mode is not an MVP requirement. `.dark` keeps its inverted near-white `--primary`; the four new evidence vars are declared once in `:root` and cascade into `.dark` unchanged, so `.dark` needs no edit. If you find yourself editing `.dark`, stop — you are outside AC #1.
  - [ ] **Do not touch `--radius`** (`0.625rem`) or the seven derived `--radius-sm…4xl` entries. `DESIGN.md`: *"Inherit the current shadcn radius scale."* Add only the two ShiftMind-specific radii.
  - [ ] `@theme inline` additions (Tailwind v4 namespaces — verified against current Tailwind CSS docs):
    ```css
    --color-evidence-link: var(--evidence-link);
    --color-evidence-surface: var(--evidence-surface);
    --color-evidence-border: var(--evidence-border);
    --color-evidence-foreground: var(--evidence-foreground);

    --radius-evidence: 6px;        /* {rounded.evidence} */
    --radius-data-region: 6px;     /* {rounded.data-region} */

    --spacing-evidence-inset: 12px;      /* {spacing.evidence-inset} */
    --spacing-data-cell-x: 8px;          /* {spacing.data-cell-x} */
    --spacing-workspace-gutter: 24px;    /* {spacing.workspace-gutter} */

    --text-page-title: 20px;
    --text-page-title--line-height: 1.2;
    --text-page-title--font-weight: 600;
    --text-metric: 28px;
    --text-metric--line-height: 1.2;
    --text-metric--font-weight: 600;
    --text-identifier: 12px;
    --text-identifier--line-height: 1.5;
    --text-identifier--font-weight: 400;

    --font-mono: ui-monospace, SFMono-Regular, Consolas, monospace;
    ```
    These yield `text-evidence-link`, `bg-evidence-surface`, `border-evidence-border`, `rounded-evidence`, `rounded-data-region`, `p-evidence-inset`, `px-data-cell-x`, `px-workspace-gutter`, `text-page-title`, `text-metric`, `text-identifier`.
  - [ ] **`--font-mono`, not a new font utility.** `DESIGN.md`'s `{typography.identifier.fontFamily}` is delivered by redefining `--font-mono` so every existing `font-mono` class picks it up. **Three shipped assertions depend on the literal class name** (`ScenarioVersionContext.test.tsx:29,35,57` assert `toHaveClass("font-mono")`) — introducing an `identifier` font utility and renaming those call sites breaks them for no gain. Leave the `font-sans` body default alone; `DESIGN.md`: *"The system sans stack remains the default."*
  - [ ] **Leave the `@import` lines and the `UI-SPEC` comment block at the top untouched.** That comment is a stale reference to a previous milestone's tooling, not a live contract; it correctly forbids reintroducing a web-font import, which still holds.

- [ ] Task 2: Replace the two live literal-hex usages with tokens (AC: #1)
  - [ ] `frontend/src/components/layout/AppBar.tsx:50` — `text-[#4F46E5]` becomes `text-evidence-link`, not `text-primary`. `DESIGN.md`: *"ordinary inline links use `{colors.evidence-link}`"*; the primary/white pair is reserved for controls with verified contrast. "Consolidated" in AC #1 means the literal hex leaves the codebase.
  - [ ] `frontend/src/features/fixture-catalogue/FixtureCatalogueView.tsx:71` — the row link's `text-primary` becomes `text-evidence-link` for the same reason. Copy, href, focus ring, and `min-h-11` are unchanged; only the color class changes.
  - [ ] **Leave `frontend/src/components/results/DemandVsServedChart.tsx:59` alone.** It is inside the frozen legacy tree (AD-25) and unreachable from the shipped route table.
  - [ ] **Leave `AppBar.tsx`'s `bg-[#F5F5F5]` alone.** It is not a `DESIGN.md` token; retokenizing it is not in either AC.

- [ ] Task 3: Build the seven shared primitives (AC: #2)
  - [ ] **Location: a new `frontend/src/components/primitives/` directory**, one file per primitive, `PascalCase.tsx`, named exports. Rationale: `components/ui/` is reserved for unmodified shadcn copy-ins (`components.json` points shadcn's CLI there — a ShiftMind component placed among them will be silently clobbered by a future `shadcn add`); `features/` is for feature surfaces per AR26; `components/{editor,runs,results,scenarios}/` is frozen legacy. `components/primitives/` sits beside the live `components/layout/`.
  - [ ] **Every primitive is pure presentational.** No TanStack Query, no `useNavigate`, no `fetch`, no route knowledge, no import from `@/features/**` or `@/hooks/**`. AD-14 keeps remote cache in the hooks layer; these components take props only. This is what makes them fixture-renderable without a router or query client.
  - [ ] **Compose the inherited shadcn components — do not restyle or fork them.** `DESIGN.md`'s "Inherited visual coverage" table assigns Status badge → shadcn Badge, Inline alert → shadcn Alert default/destructive, Skeleton → shadcn Skeleton, Empty state → system typography + shadcn Button/Link, Reconnect banner → shadcn Alert.
  - [ ] `StatusBadge.tsx` — **`frontend/src/components/ui/badge.tsx` does not exist yet**; add the standard shadcn Badge copy-in first (a copy-in of the already-installed system, not a package — same precedent as Story 1.3 adding `skeleton.tsx`; AR27 is not triggered, `package.json`/`package-lock.json` must be untouched). `StatusBadge` requires a literal status **string** prop — it must be structurally impossible to render a badge whose meaning is carried only by variant/color (UX-DR32, NFR18, EXPERIENCE.md: *"Always includes literal status text and accessible name; color/icon are secondary"*). Icon is optional and never the sole carrier.
  - [ ] `InlineAlert.tsx` — wraps shadcn `Alert`/`AlertTitle`/`AlertDescription`. Props: concise `title`, optional `description`, optional single recovery `action`, `variant: "default" | "destructive"`. EXPERIENCE.md: *"Persistent within the affected surface. Gives one concise cause and recovery action when safe. Does not erase valid saved content."* Any interactive action must carry `min-h-11` (44px, UX-DR29).
  - [ ] `EmptyState.tsx` — one explanation, **at most one** recovery action (`DESIGN.md`; EXPERIENCE.md). Make the "at most one" a type-level constraint (a single optional `action` prop, not an array), so a later story cannot grow it into a CTA row.
  - [ ] `ReconnectBanner.tsx` — three literal states: `disconnected` → `reconnecting` → `reconnected` (EXPERIENCE.md line 107). Non-modal, never covers saved content, and each state's meaning is in its text. **No consumer exists yet** — SSE arrives in Epic 2/3 — so this ships fixture-covered and unmounted. That is intended, not dead code: 3.12 renders it.
  - [ ] `EvidenceLink.tsx` — **presentational only.** Renders a conventionally link-identifiable inline control (underlined, `text-evidence-link`, `rounded-evidence`, `focus-visible` ring from `--ring`) whose **accessible text names group, record, optional field/range, and version** — e.g. `Evidence: Demand DEM-204, 13:00–17:00, fixture v7` (EXPERIENCE.md line 154). Take the locator fields as props and compose the label here so every call site produces the same string. Colour alone is never the affordance (UX-DR34). **Do not build navigation:** no `EvidenceRefV1` URL/history-state serialization, no exact-target fetching, no origin-key capture, no `ReturnToClaim`. All of that is Story 2.8's acceptance boundary, over Story 1.5's already-shipped resolver endpoints. Accept an `onActivate`/`href` prop and stop.
  - [ ] `EvidenceHighlight.tsx` — the quiet highlight: `bg-evidence-surface`, `text-evidence-foreground`, `border-evidence-border`, `rounded-evidence`, `p-evidence-inset`. **Zero animation, zero shadow, zero pulse** — `DESIGN.md`: *"No animation is required; reduced-motion and default behavior are visually identical"*; UX-DR32/UX-DR34 forbid pulsing/flashing. It must be usable as a wrapper on a row/cell/record card and accept `tabIndex={-1}` + a ref so Story 2.8 can focus it; it does not focus itself here.
  - [ ] `Skeleton` — **already exists** at `frontend/src/components/ui/skeleton.tsx` with `motion-reduce:animate-none`. **Do not move, fork, or restyle it.** Story 1.3 Task 4: *"Story 1.6 will govern it, not replace it."* Governing it here means giving it fixtures (Task 4) and asserting the reduced-motion class stays; re-export it from the primitives barrel if you add one, nothing more.
  - [ ] **Out of scope — do not build:** Workspace tabs, Scenario/version context deltas, Scenario Data grid, Return to claim, Filter bar, Column chooser, Identifier copy control, Evidence exception panel, Draft/Run-progress/Comparison/Approval/Terminal-outcome cards. AC #2 lists exactly seven primitives. `DESIGN.md`'s delta table also names Workspace tabs / Scenario-version context / Scenario Data grid / Return to claim — those belong to Stories 1.7, 1.8, and 2.8, which the epic requires to *"implement its component-specific visual contract in that story."*

- [ ] Task 4: State fixtures for visual regression (AC: #2)
  - [ ] **Judgment call — flag this in completion notes.** AC #2 requires "visual-regression fixtures", and Stories 3.12 and 4.7 say those fixtures *"render"* states, implying a screenshot runner. **Playwright is not installed and is not in the architecture Stack table** (it appears only in `prd/addendum.md`; `ARCHITECTURE-SPINE.md`'s review-rubric asked for it to be ratified or superseded and the final spine did not add it). AR27 forbids adding an unlocked dependency before its implementation gate. **Therefore this story delivers the fixtures — the enumerable, deterministic state catalogue — and not a screenshot runner.** The runner lands with the story that owns a browser proof (1.10 / 3.12 / 4.7) and consumes this module unchanged. Do not `npm install` anything.
  - [ ] `frontend/src/components/primitives/fixtures.tsx` — **one module, one exported array**, e.g.:
    ```tsx
    export type PrimitiveFixture = {
      primitive: string;   // "StatusBadge" | "InlineAlert" | ...
      state: string;       // "queued" | "destructive" | "reconnecting" | ...
      render: () => ReactNode;
    };
    export const PRIMITIVE_FIXTURES: readonly PrimitiveFixture[] = [ /* … */ ];
    ```
    Flat and enumerable so Task 5's tests and a later screenshot runner both iterate the same source. **All seven primitives must appear**, with every state each one declares — at minimum: StatusBadge across the literal AD-7 vocabularies it will carry (`queued`, `running`, `completed`, `infeasible`, `timed out`, `cancelled`, `failed`, `rejected`, `expired`, `stale`); InlineAlert default + destructive, with and without an action; Skeleton for a text line and a table region; EmptyState with and without an action; ReconnectBanner all three states; EvidenceLink with and without a field/range; EvidenceHighlight wrapping a row and a record card.
  - [ ] **Put fixtures in their own module, not inside a component file.** `.oxlintrc.json` enables `react/only-export-components` (warn) — exporting a non-component const beside a component trips it, and the repo currently carries exactly four such warnings that a reviewer will read as pre-existing.
  - [ ] Fixture render functions must be **deterministic**: no `Date.now()`, no `Math.random()`, no incrementing counters. A screenshot baseline taken in a later story is worthless otherwise.

- [ ] Task 5: Tests (AC: #1, #2)
  - [ ] **Token contrast — the one check `DESIGN.md` explicitly demands** (*"controls whose shipped contrast is verified before use"*). Pure-TS test (no DOM): parse the four evidence hexes plus `#4F46E5`/`#FFFFFF` out of `index.css`, compute WCAG relative luminance and contrast ratio, and assert: `evidence-foreground` on `evidence-surface` ≥ 4.5, `evidence-link` on `#FFFFFF` ≥ 4.5, `primary-foreground` on `primary` ≥ 4.5. Expected values ≈ 14.3, 8.0, and 6.3 — assert the `≥ 4.5` floor, not the exact number. Read the values *from the stylesheet*, so editing a token without re-checking contrast fails the build.
  - [ ] **Token presence** — assert `index.css` declares every token named in Task 1, and assert the **negative** half of AC #1 that a reviewer cannot eyeball: `--radius: 0.625rem` is unchanged, and the `.dark` block is byte-identical to its baseline (snapshot the block's text). This is the only cheap guard against a well-meaning "dark mode consistency" edit.
  - [ ] **No color-only meaning (AC #2's operative clause)** — iterate `PRIMITIVE_FIXTURES`, render each, and assert that within one primitive every state's visible text content is **distinct**. A regression that distinguishes `completed` from `failed` by variant alone collapses two fixtures to the same string and fails. This is what makes the assertion real rather than a class-name check.
  - [ ] **Every fixture renders** — iterate `PRIMITIVE_FIXTURES` and assert each `render()` mounts without throwing and without a router or `QueryClientProvider` in scope. That last part is the enforceable form of "pure presentational" and is what a later screenshot runner needs.
  - [ ] **Fixture coverage** — assert `PRIMITIVE_FIXTURES` contains at least one entry for each of the seven primitive names, driven by a hard-coded list of the seven. Adding a primitive without fixtures then fails.
  - [ ] **Reduced motion / no theatrics** — assert `EvidenceHighlight`'s rendered root carries no `animate-` class and no `shadow-` class, and that `Skeleton` still carries `motion-reduce:animate-none`.
  - [ ] **Touch targets** — every interactive element inside a fixture (`button`, `a`) carries `min-h-11` (UX-DR29's 44px floor as this repo already expresses it). Note Story 1.3's review deferred the *width* axis as needing a UX call; hold the same line here, do not widen scope.
  - [ ] **Regression** — the two Story 1.3 surfaces keep passing unchanged. `ScenarioVersionContext.test.tsx`'s three `toHaveClass("font-mono")` assertions and `FixtureCatalogueView.test.tsx`'s class assertions must survive Tasks 1–2 and 6 untouched. If one fails, you changed something Task 1/2/6 said not to.
  - [ ] **Full gate before done:** `npm test`, `npm run typecheck`, `npm run lint`, `npm run build` from `frontend/`. Backend is untouched — no `pytest`, no `alembic check`, no `npm run codegen` (no OpenAPI change). Report the frontend test count before and after.

- [ ] Task 6: Adopt three primitives in the two shipped surfaces (AC: #2)
  - [ ] **Why this is in scope:** AC #2's "so that" is *"every later story implements its visual contract once instead of retrofitting consistency."* `FixtureCatalogueView` and `ScenarioWorkspace` each hand-roll an inline alert and an empty state today; leaving two treatments in the tree is precisely the drift Story 4.7 will audit.
  - [ ] `FixtureCatalogueView.tsx`: `UnavailableCatalogue` → `InlineAlert` (variant `destructive`, title/description from `USER_ERROR_COPY.connection`, Retry as the action). `EmptyCatalogue` → `EmptyState`.
  - [ ] `ScenarioWorkspace.tsx`: the `query.isError && !query.data` alert block → `InlineAlert` with its existing Retry button and "Return to catalogue" link preserved as-is.
  - [ ] **Preserve every user-visible string byte-for-byte** — including `"Saved catalogue — refresh unavailable"`, `"No predefined scenarios are available."`, `"Stale — last verified at {timestamp}"`, and `USER_ERROR_COPY.connection`. These were settled by Story 1.3's review (see its two 2026-07-29 follow-ups on invented stale copy); re-deriving them here re-opens a closed UX decision.
  - [ ] **Preserve the live-region structure exactly.** `FixtureCatalogueView`'s outer `aria-live="polite"` wrapper is never unmounted (a live region only announces mutations to an *existing* region), and the stale label puts only the message — not the Retry button — inside `role="status"`. Both are fixes from Story 1.3's review. Wrapping either in a new component that remounts them re-introduces a defect that has already been paid for once.
  - [ ] **Do not touch the cached-stale banner markup itself, the skeleton, the `COLUMNS` descriptor, focus handling, or `useRedirectOnUnauthorized`.** Nothing else in these two files changes.
  - [ ] **Do not** adopt `StatusBadge`, `EvidenceLink`, `EvidenceHighlight`, or `ReconnectBanner` anywhere — no surface exists yet that legitimately carries them.

## Dev Notes

- **What NOT to build.** No backend change of any kind. No route, no hook, no API wrapper, no `npm run codegen` (the OpenAPI document is unchanged, so `frontend/openapi.json` and `frontend/src/api/schema.d.ts` must not appear in the diff). No new npm dependency — `package.json` and `package-lock.json` are untouched (AR27). No `tailwind.config.js`. No Storybook, no Playwright, no screenshot baselines. No dark-theme work. No evidence *navigation* (Story 2.8). No workspace tabs or Scenario Data grid (Stories 1.7/1.8).
- **The `--primary` change is the one visually broad edit — know its blast radius before you make it.** `bg-primary` appears in shadcn `Button`'s `default` variant and in `routes/SignIn.tsx:23`; `text-primary` in `Button`'s `link` variant. After Task 1 those render indigo instead of near-black. That is the intended reading of `DESIGN.md` (`colors.primary: '#4F46E5'`, and the token is absent from the "inherit unchanged" list). White-on-`#4F46E5` measures ≈ 6.3:1, which clears AA for normal text, so no control needs a foreground fix — Task 5's contrast test is what proves that rather than asserting it.
- **Fixtures are the deliverable, a screenshot runner is not.** See Task 4's judgment call. The property AC #2 actually makes checkable is *"without color-only meaning"* — a textual/structural property that RTL proves and a screenshot cannot. Build the fixture catalogue so that when 1.10/3.12/4.7 add a browser runner they iterate `PRIMITIVE_FIXTURES` and change nothing here.
- **Primitives are not a design system rewrite.** `DESIGN.md`'s "Inherited visual coverage" table is explicit that 21 of the named components have **no ShiftMind visual override**. The delta surface is small: indigo accent, the evidence treatment, identifier monospace, dense data regions. If a primitive you are writing needs more than composition + a token class or two, re-read the table before adding CSS.
- **`components/ui/` is shadcn's territory.** `components.json` aliases `"ui": "@/components/ui"`, so `npx shadcn add …` writes there and will overwrite a same-named file. `badge.tsx` goes there (it *is* a shadcn copy-in); `StatusBadge.tsx` and the other six ShiftMind primitives go in `components/primitives/`.
- **The frozen legacy tree is a trap for a token story.** `frontend/src/components/{editor,runs,results,scenarios}/**` plus `lib/runStatus.ts`, `lib/formatShiftWindow.ts`, and `components/layout/ErrorBanner.tsx` are orphaned but still compiled and still tested (see `deferred-work.md`'s Story 1.3 entries). A repo-wide "replace every hardcoded color" sweep will edit them, inflate the diff, and touch AD-25-frozen code. Scope colour edits to the two files named in Task 2.
- **Class-name assertions are a known weak spot here.** Story 1.3's review deferred a finding that jsdom never evaluates Tailwind classes, so `toHaveClass("min-h-11")` proves only that a string was typed. Task 5 deliberately puts the load-bearing assertions on *rendered text* (distinct state strings, contrast computed from the stylesheet source) rather than class names; keep the few class assertions that remain as cheap structural guards, not as the proof.
- **Copy discipline (UX-DR5) applies to fixture text too.** Fixture labels are operational and literal — `"Run R-1842 is queued."`, not `"Processing…"`. `EXPERIENCE.md`'s Voice and Tone table is the reference; a fixture string that would fail review on a real surface fails here too, because 3.12/4.7 will screenshot exactly these strings.
- **Test conventions:** Vitest + Testing Library, tests co-located with implementation (`Component.test.tsx`), `npm test` from `frontend/`. `vite.config.ts` is the single source for the `@` alias and the jsdom environment; `src/test/setup.ts` holds the pointer-capture polyfills Radix needs. Do not add a second config or a second setup file.

### Project Structure Notes

- **New directory:** `frontend/src/components/primitives/` — `StatusBadge.tsx`, `InlineAlert.tsx`, `EmptyState.tsx`, `ReconnectBanner.tsx`, `EvidenceLink.tsx`, `EvidenceHighlight.tsx`, plus `fixtures.tsx` and co-located `*.test.tsx`. (`Skeleton` stays in `components/ui/`.)
- **New shadcn copy-in:** `frontend/src/components/ui/badge.tsx`.
- **Modified:** `frontend/src/index.css` (tokens), `frontend/src/components/layout/AppBar.tsx` (one class), `frontend/src/features/fixture-catalogue/FixtureCatalogueView.tsx` (one class + two primitive adoptions), `frontend/src/routes/ScenarioWorkspace.tsx` (one primitive adoption).
- **Untouched:** all of `backend/**`, `frontend/openapi.json`, `frontend/src/api/**`, `frontend/package.json`, `frontend/package-lock.json`, `frontend/src/components/{editor,runs,results,scenarios}/**` (AD-25 frozen legacy), `frontend/src/index.css`'s `.dark` block, `frontend/src/App.tsx`.
- AR26's Structural Seed names `frontend/src/{api,features,routes}` for *new* work; shared cross-feature presentational components are not one of those three roles, and `components/{layout,ui}` are the established live homes for that kind of code. `components/primitives/` is a peer of `components/layout/`, not a variance from the seed.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 1.6: Establish ShiftMind Design Tokens and Shared Primitives, lines 461-479] — story statement, "Unblocks: Story 1.7 and every subsequent UI story", and the two acceptance criteria
- [Source: epics.md#UX-DR23, UX-DR30, UX-DR32, UX-DR33, UX-DR34, lines 223, 237, 241, 243, 245] — shared Status badge/Inline alert/Skeleton/Empty state/Reconnect banner patterns; retain shadcn/Tailwind/Radix + indigo and add the named evidence/gutter/cell/radius/monospace tokens; prohibited AI glows, gradients, pulsing, colour-only state; preserve inherited elevation/neutral/status/radius and optional dark theme with no new palette; evidence links link-identifiable with a non-animated quiet highlight
- [Source: epics.md#UX-DR29, NFR18, NFR20, lines 235, 110, 114] — 44×44 targets, no hover-only actions, visible focus, reduced motion; status meaning in text not colour
- [Source: epics.md#Story 3.12, lines 1114-1119 and #Story 4.7, lines 1284-1300] — the two downstream stories that render "the Story 1.6 shared primitives" through visual-regression fixtures; the reason Task 4's fixture module must be enumerable and deterministic
- [Source: epics.md, line 318] — "No Epic 6": visual-regression auditing is a definition of done attached to the epic it protects, with aggregate release-blocking thresholds held in the Release Gate section
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-07-23.md, line 132] — the provenance of this story: relocated from old Story 5.2 AC 1 plus the new shared-primitive criterion; "token/primitive work now lives in Story 1.6"
- [Source: .../ux-designs/ux-ShiftMind-2026-07-22/DESIGN.md, frontmatter lines 9-67] — the normative token values: `colors`, `typography` (page-title/metric/identifier), `rounded` (evidence/data-region), `spacing` (evidence-inset/data-cell-x/workspace-gutter), and the per-component token references
- [Source: DESIGN.md, lines 77-104] — Colors ("Primary indigo retains the implemented scenario-tab accent"; the inherit-unchanged list; "ordinary inline links use `{colors.evidence-link}`"; AA targets), Typography, Layout & Spacing, Elevation ("hierarchy comes from borders, background tone, headings, and placement"), Shapes ("inherit the current shadcn radius scale")
- [Source: DESIGN.md, lines 110-146] — the ShiftMind delta table (Evidence link, Evidence highlight — "no animation is required; reduced-motion and default behavior are visually identical") and the Inherited visual coverage table naming the shadcn source for Status badge, Inline alert, Skeleton, Empty state, and Reconnect banner
- [Source: DESIGN.md, lines 149-158] — Do's and Don'ts: text/icon/structure for every state, stable non-pulsing evidence highlight, separated action treatments
- [Source: .../ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md, lines 103-107] — behavioural contracts for Status badge, Inline alert, Skeleton, Empty state, Reconnect banner
- [Source: EXPERIENCE.md, lines 86, 97, 150-154] — Evidence link and Evidence highlight behaviour, and the exact visible-label form "Evidence: Demand `DEM-204`, 13:00–17:00, fixture `v7`"
- [Source: EXPERIENCE.md, lines 58-73] — Voice and Tone: literal operational copy for fixture strings
- [Source: EXPERIENCE.md, lines 185-196] — accessibility floor: text-not-colour status, visible focus, reduced motion, 44×44 targets, supported test matrix
- [Source: .../architecture/.../ARCHITECTURE-SPINE.md#AD-14, lines 168-172] — TanStack Query owns remote cache; route/component state owns only navigation and presentation (why the primitives take props only)
- [Source: ARCHITECTURE-SPINE.md#Structural Seed, lines 286-309] — `frontend/src/{api,features,routes}` ownership boundaries; "not a mandate for an all-at-once brownfield rename"
- [Source: ARCHITECTURE-SPINE.md#Stack, lines 261-284 and #AD-25, lines 234-238] — repository locks (React 19.2.7, TypeScript 5.9.3, Vite 8.1.x, Tailwind 4.3.2 via the existing `@tailwindcss/vite`); Playwright is absent from the table; frozen legacy tree
- [Source: epics.md#AR26, AR27, lines 173-174] — converge new frontend work on `frontend/src/{api,features,routes}` without an all-at-once rename; "add and lock each planned dependency only at its implementation gate" — the rule Task 4's no-Playwright decision rests on
- [Source: _bmad-output/implementation-artifacts/1-3-choose-an-immutable-fixture.md, Task 4 and Dev Notes] — "Do not build the ShiftMind token layer… Story 1.6 will govern [Skeleton], not replace it"; the shadcn-copy-in-is-not-a-dependency precedent; the five-state TanStack shapes behind the surfaces Task 6 touches
- [Source: 1-3-choose-an-immutable-fixture.md#Review Findings, chunk 2 + the two 2026-07-29 follow-ups] — the live-region fixes, the `role="status"` scoping, the settled stale-label copy, and the deferred "class-name assertions prove nothing in jsdom" finding that shapes Task 5
- [Source: _bmad-output/implementation-artifacts/deferred-work.md, Story 1.3 entries] — the orphaned legacy component/hook inventory, including the three shared modules outside the four legacy directories, that a repo-wide colour sweep would wrongly edit
- [Source: frontend/src/index.css] — the `@theme inline` + `:root` + `.dark` structure to extend, the derived `--radius-*` scale, and the `@layer base` defaults
- [Source: frontend/components.json] — `"ui": "@/components/ui"`, `"tailwind.config": ""`, `baseColor: neutral`, `style: radix-nova` — why ShiftMind primitives must not live in `components/ui/`
- [Source: frontend/src/components/ui/{alert,skeleton,button,tabs}.tsx] — the inherited components to compose; `Skeleton`'s `motion-reduce:animate-none`; `Button`'s `bg-primary`/`text-primary` variants affected by the token change
- [Source: frontend/src/features/fixture-catalogue/FixtureCatalogueView.tsx, frontend/src/routes/ScenarioWorkspace.tsx] — the two surfaces Task 6 adopts primitives into, and the exact live-region/stale-label structure to preserve
- [Source: frontend/src/components/layout/AppBar.tsx:50, frontend/src/components/results/DemandVsServedChart.tsx:59] — the only two literal `#4F46E5` usages; the first is live and retokenized, the second is frozen legacy and left alone
- [Source: frontend/.oxlintrc.json, frontend/vite.config.ts, frontend/src/test/setup.ts] — `react/only-export-components` (why fixtures get their own module); the single test config and setup file

## Dev Agent Record

### Agent Model Used

### Implementation Plan

### Debug Log References

### Completion Notes List

### File List
