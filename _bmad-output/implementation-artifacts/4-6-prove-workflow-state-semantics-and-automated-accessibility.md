---
baseline_commit: 3dd2a92
---

# Story 4.6: Prove Workflow State Semantics and Automated Accessibility

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want every workflow state to communicate its literal meaning and remain operable without
manual assistive-technology verification,
So that I can distinguish drafts, progress, outcomes, and decisions correctly across the
completed journey.

**This is a PROOF story, and it is the last story of Epic 4.** Epics 1–4 have shipped every
surface it asserts against. What does not exist is a single enumerable record of *which literal
states the product has*, and a *release-blocking* proof that each one is textually and structurally
distinct, free of the prohibited treatments, and conformant at 100%/200% zoom, under WCAG text
spacing, and under reduced motion — across the whole desktop journey rather than across Epic 1's
Scenario Data surfaces alone.

**It consolidates the former Stories 4.6, 4.8 and 4.9. Former Story 4.7 was CUT**
(`sprint-change-proposal-2026-08-09-epics-2-5.md:151`, root cause 1: "visual-regression fixtures"
was a process artifact that no NFR, UX-DR or AD mandated). **No screenshot baseline, no
Chromatic/Percy runner, and no manual assistive-technology pass is required or accepted as proof.**
A method-defined artifact is exactly what this epic already cut once; do not reintroduce one under
a new name.

**Depends on, and consumes:** Story 1.6's `PRIMITIVE_FIXTURES` state catalogue and its
`fixtures.test.tsx` guards; Story 1.10's two-layer accessibility harness
(`src/test/accessibility*.test.tsx` plus `e2e/{accessibility,layout-accessibility,reduced-motion,responsive}.spec.ts`)
and its `accessibility_and_responsiveness` invariant; Story 2.8's `evidence-accessibility.test.tsx`;
Story 3.12's `e2e/support/apiStubs.ts` and `repairJourneyStubState.ts`, its
`repair-journey-accessibility.spec.ts`, its thin-script evidence generator and its
`repair_browser_journey` invariant; Story 4.2's `[data-approval-panel]`-scoped approval scans;
Story 4.4's provenance zoom scans; Story 4.5's Gate A two-check registration pattern and its
skip-is-not-a-pass rule.

**Unblocks:** the Epic 4 retrospective, and Epic 5's portfolio walkthrough (Story 5.4), which shows
these surfaces to a reader.

**Scope summary:** one new enumerable state-matrix module and its Vitest suite; one new Playwright
journey-accessibility spec extending AC2's four dimensions to Chat, Runs, Results, Approvals and
Provenance; one new evidence generator and its machinery test; one new NFR29 invariant with four
Gate A checks; one line added to the exact registered-evidence-path set; one measurement-gated
shared-Button contrast decision (Decision 10); ledger reconciliation. **No migration, no new route,
no new API contract, no new backend behaviour, no new dependency, and no new golden case.**

---

## Facts this story depends on — each one written down and citable

Retro action **A3** (`epic-1-2-retro-2026-08-16.md` §6.1) requires this pass before decisions.
Every rule below is recorded somewhere citable; none may be re-derived from component code.

| Fact | Where it is written |
|---|---|
| **"The Story 1.6 fixture catalogue" is `PRIMITIVE_FIXTURES` in `frontend/src/components/primitives/fixtures.tsx`** — a flat, deterministic, provider-free array of 27 states across 8 primitives. It is **not** the `/` Fixture Catalogue route (Story 1.3's scenario list). Story 1.6's Task 4 delivered it explicitly as "one module, one exported array", and its Dev Notes name this consumer: "iterate `PRIMITIVE_FIXTURES` and change nothing here". | `1-6-establish-shiftmind-design-tokens-and-shared-primitives.md` — Task 4, Completion Notes, Dev Notes; `frontend/src/components/primitives/fixtures.tsx` |
| Proof method for this story is **automated only**. Manual assistive-technology verification is explicitly descoped for this portfolio MVP; automated coverage alone is the accepted floor. | `epics.md:1322`; `EXPERIENCE.md` — Accessibility Floor; `docs/GATE-A-RUNBOOK.md`; `.claude/CLAUDE.md` |
| Former Story 4.7 (cross-workflow visual regression) is **cut**; 4.8 and 4.9 merged into this story; the Epic 4 Completion Gate was removed and its independence requirement is now internal to AC3. | `sprint-change-proposal-2026-08-09-epics-2-5.md:150-153` |
| **UX-DR32's prohibition list, verbatim:** "prohibit AI glows, gradients, animated avatars, confidence gauges, celebratory effects, pulsing/flashing evidence, and color-only state communication." AC1 adds "invented percentage, ETA, or merged action treatment" from UX-DR10, UX-DR13 and UX-DR35. | `epics.md:240` (UX-DR32), `:196` (UX-DR10), `:202` (UX-DR13), `:246` (UX-DR35) |
| **UX-DR11 makes coverage / overtime / cost percentages legitimate product content** in comparison summaries. UX-DR10's prohibition is on *invented* percentages and ETAs on run progress, not on all `%` characters. | `epics.md:198` (UX-DR11), `:196` (UX-DR10) |
| "Pending, overdue" is **one literal presented state, not a fourth stored one**, and the state matrix — this story — is named as its owner. Reads never write. | Epic 4 `ARCHITECTURE-SPINE.md` — EAD-7 |
| The closed terminal-reason vocabulary the matrix must render is `approval_rejected`, `approval_expired`, `approval_stale`, carried on `agent_run.status_reason` so reconnect renders the literal outcome without replaying events. | Epic 4 spine — EAD-5 |
| Reconnect reconstructs the pause, the exact binding, and **only the currently valid decision controls** from persistence alone, rendered once. | Epic 4 spine — EAD-4; verification obligation 4 |
| Story 4.5 took verification obligations 1, 2, 3, 5, 6, 7 in full plus **the backend half of obligation 4**, and assigned this story **obligation 4's rendering half** (the pause and its identifiers replay once; "pending, overdue" joins the state matrix) and **the presentation half of obligation 3** (only currently valid actions are offered). | `4-5-prove-approval-and-audit-invariants.md` — Decision 2; Epic 4 spine — Story → Architecture Map |
| An evidence file that claims to block release **must** expose a top-level `passed` boolean **and** be registered in `gate_a_checks.py`; no invariant may rest on a stored flag alone; a generator's verdict must require the proof to have RUN (`tests > 0`, `executed > 0`, `skipped == 0`, `failures == 0`, `errors == 0`). | `docs/EVIDENCE-CONVENTION.md` — "A verdict key Gate A can read" |
| Commit the code, then measure, then generate through `resolve_bindings()`, then commit the evidence separately. Never hand-type an evidence file. Every rule over a committed artifact must be **monotone**. | `docs/EVIDENCE-CONVENTION.md` — "The rule"; "Every rule over a committed artifact must be monotone" |
| `outbound` / `inbound` demand is measured in **volume**; `indirect` in **headcount**. `required_headcount_minutes` is answerable **only** for `indirect`, because `headcount` is the only unit that already is a rate. Assignments carry worker identity but **no `family`**. This story computes no metric — it renders claim *fixtures* — and must not enshrine an impossible pairing in a new one (Trap 10). | `docs/DOMAIN-MODEL.md` §1, §2, §3 |
| A `GateACheck` may declare `evidence_path` **or** `test_files`, never both — `__post_init__` raises. `required_projects` is Playwright-only. Vitest-registered files must start with `frontend/src/`; Playwright's with `frontend/e2e/`. | `backend/scripts/gate_a_checks.py` — `GateACheck.__post_init__`; `backend/tests/test_gate_a_readiness.py` — `test_runner_matches_the_file_location` |
| `--reporter=junit` is passed on the Playwright **command line only**; `playwright.config.ts` pins `reporter: "list"` and that committed default must stay put. On Windows use the committed streaming reporter and note the different env var (`PLAYWRIGHT_JUNIT_OUTPUT_FILE`, not `..._NAME`). | `docs/GATE-A-RUNBOOK.md` §3 |

---

## Acceptance Criteria

Verbatim from `epics.md:1316-1339`, including the proof-method note under the story heading.

**Proof-method note.** Consolidates the former Stories 4.6–4.9. Proof method is automated only,
consistent with `EXPERIENCE.md`'s Accessibility Floor: the state matrix is asserted against the
Story 1.6 fixture catalogue and the completed surfaces, and conformance is asserted by the Epic 1
axe/semantic/browser suites. No screenshot baseline and no manual assistive-technology pass is
required or accepted as proof.

**AC1.**
**Given** messages, drafts, runs, comparisons, approvals, terminal outcomes, alerts, skeletons,
empty states, and provenance across Epics 1–4
**When** every literal state renders
**Then** text, structure, and inherited components communicate meaning without color-only status,
and each state is textually and structurally distinct
**And** no confidence gauge, AI glow, gradient, animated avatar, pulse, celebration, invented
percentage, ETA, or merged action treatment appears. (UX-DR10, UX-DR13, UX-DR32, UX-DR35)

**AC2.**
**Given** the complete desktop journey
**When** automated accessibility checks run at 100% and 200% zoom, with increased text spacing and
reduced motion
**Then** WCAG 2.2 AA and the documented focus, overflow, touch-target, table, and state rules pass,
with no page-level horizontal scroll, overlapping sticky text, or unreadable long identifier
**And** any accessibility regression blocks release. (NFR18, NFR20, NFR29, UX-DR31, UX-DR34)

**AC3.**
**Given** the consolidated state-semantics and accessibility suite
**When** its result is persisted
**Then** `evidence/story-4.6/state-semantics-and-accessibility.json` names every tested state and
binds the tested artifact versions
**And** the state matrix and the accessibility pass must each succeed for this story to complete.
(NFR27, NFR29)

---

## Measured at creation — `3dd2a92`, clean tree

Do not re-derive these from component code; re-verify them at Task 1 and record any drift.

| Fact | Measurement |
|---|---|
| Playwright suite | **66 tests / 9 files**, chromium + msedge (`npx playwright test --list`) |
| `PRIMITIVE_FIXTURES` | 27 entries / 8 primitives: StatusBadge ×10, InlineAlert ×4, Skeleton ×2, EmptyState ×2, ReconnectBanner ×3, EvidenceLink ×2, EvidenceHighlight ×2, IdentifierCopyButton ×2 |
| Component-layer axe sweep (`src/test/accessibility.test.tsx`) | covers Fixture catalogue states, every `PRIMITIVE_FIXTURES` entry, Scenario Workspace states, and Scenario Data groups. **It does not cover Chat, Draft, Runs, Results, Approvals, or Provenance.** |
| Browser-layer zoom / text-spacing / reduced-motion | `layout-accessibility.spec.ts` and `reduced-motion.spec.ts` visit `demandUrl` and `/` **only**. `generate_repair_journey_evidence.py` states this in writing: *"NFR20 is deliberately absent … those stay proven on Epic 1's Scenario Data surfaces only."* |
| Browser-layer coverage that DOES exist on Epic 2–4 surfaces | `accessibility.spec.ts`: four approval-review panel states (`pending`, `pending-overdue`, `rejected`, `consumed`) scoped to `[data-approval-panel]`; provenance at 100% and 200% zoom, full page. `repair-journey-accessibility.spec.ts`: Chat/Runs/Results axe plus keyboard, the approval dialog named and focus-restoring at 100%/200% zoom, and one reduced-motion assertion on Results. |
| UX-DR32 prohibition assertions today | **two ad-hoc regexes** in `frontend/src/features/chat/ActivityTimeline.test.tsx:281,430` over `document.body.innerHTML` (`/gradient|animate-pulse|ai-glow/i`, `/gradient|animate-pulse|glow/i`) plus one text regex `/approximately|confidence|%/i`. Nothing enumerates the nine prohibited treatments and nothing applies them beyond that one component. |
| Registered evidence paths | an **exact set of six** in `backend/tests/test_gate_a_readiness.py:265-281` |
| `NFR29_GATES` | four invariants: `accessibility_and_responsiveness`, `recovery_and_idempotency`, `repair_browser_journey`, `approval_and_audit_invariants` |
| Reduced motion | `frontend/src/index.css:151-160` sets `transition-duration: 0.01ms !important` and `animation-duration: 0.01ms !important` globally under `prefers-reduced-motion: reduce` |
| axe-core | single hoisted copy, **4.13.0**. `colorContrastMatches` returns `false` for a disabled or inert node — measured in `node_modules/axe-core/axe.js` |

**Baselines inherited and NOT verified** (Story 4.5 review, 2026-09-01): backend default
`1490 passed, 2 skipped, 7 deselected`; `-m postgres` `156 passed`;
`tests/test_evidence_convention.py` `80 passed`. Frontend Vitest and Playwright counts were not run
by 4.5 (zero-line frontend diff), so the last recorded frontend number is Story 4.4's `575 passed`.
The Playwright figure above (66) **was** measured here and supersedes 4.4's 62.
**Re-derive all of them at Task 1 before attributing any failure to this story.** CI floors in
`.github/workflows/ci.yml` are floors and ceilings — do not edit them.

---

## Twelve decisions were made at story creation — do not re-litigate them

Each decision states its mechanism **and what that mechanism does not cover**. The second half is
load-bearing: Story 4.2's Decision 10 named a goal and a mechanism that blocked only one of two
directions, and the gap shipped.

### Decision 1 — This is a proof story with a bounded, measurement-gated production allowance

Story 4.5's Decision 1 ("it asserts, it does not build") is inherited with one deliberate
difference. AC1's "no color-only status … no gradient/pulse" and AC2's WCAG floor are properties of
**shipped UI**. A conformance proof that finds a real violation and then scopes around it has not
proven conformance. So a production change **is** permitted here, under two conditions, both
recorded in Completion Notes:

1. it is forced by a **specific assertion observed failing** — name the assertion and the measured
   value — and
2. it is the **smallest change** that clears the failure: a token or a shared-primitive class,
   never a new component, a new control, or new copy.

Any change not meeting both is a finding to escalate, not a licence.

**Does NOT cover:** this is not a licence to add product states, controls, copy, or routes; to
retrofit consistency across surfaces the ACs do not name; or to "fix while in here" any of the open
ledger items Decision 12 leaves open. It also does not extend to `backend/` behaviour — Decision
11's zero-line fences are absolute.

### Decision 2 — The state matrix is a NEW enumerable module that COMPOSES `PRIMITIVE_FIXTURES`; it never edits it

New: `frontend/src/test/stateMatrix.tsx`, exporting `STATE_MATRIX` — the same flat, deterministic,
provider-free shape Story 1.6 established, one level up: **feature** states, not primitive states.
Each entry is `{ family, state, render }` where `family` is one of AC1's ten nouns —
`message`, `draft`, `run`, `comparison`, `approval`, `terminal-outcome`, `alert`, `skeleton`,
`empty-state`, `provenance`.

`PRIMITIVE_FIXTURES` is **imported and composed into the matrix, never modified.**
`fixtures.test.tsx` asserts an **exact per-primitive state list** (Trap 1), so adding one entry
reddens a test that reads as unrelated to this story; and Story 1.6's own Dev Notes anticipated
this consumer by name.

The module lives in `frontend/src/test/` because `test_runner_matches_the_file_location` requires
every vitest-registered Gate A file to start with `frontend/src/`, and `vite.config.ts` scopes
`test.include` to `src/**`. Precedent for a non-test module in that directory:
`frontend/src/test/evidenceHighlights.ts`.

**Does NOT cover:** the matrix is a test fixture module. It ships **no route, no gallery page, and
no production import** — AC1 names no surface, and adding one would be product scope. It is also
not the `/` Fixture Catalogue route (Story 1.3's scenario list), which this story does not touch.

### Decision 3 — "Textually and structurally distinct" is asserted pairwise WITHIN a family, and structure is a normalized role/name tree

`fixtures.test.tsx` already proves the shape for text: collect the rendered `textContent` per
group, assert every entry is non-empty and that the set size equals the list length. Reuse it
verbatim for `STATE_MATRIX`, keyed on `family`.

For "structurally", assert a **normalized accessibility tree** per entry — the ordered list of
`(role, accessible name)` pairs reachable in the rendered container — and require those to be
pairwise distinct within a family too. Two states that differ only in a colour class produce an
identical tree and identical text, and that is precisely the color-only failure AC1 forbids. This
is the assertion that can go red on it.

**Does NOT cover:** distinctness is **not** asserted across families — two families may legitimately
share a word (a `run` and an `approval` may both say "cancelled"). It is also not an ARIA snapshot
baseline (Decision 12): nothing is committed to disk and nothing needs updating when copy changes,
because the assertion is *distinctness*, not *equality to a recorded tree*.

### Decision 4 — The prohibited-treatment assertion is ONE shared helper over class tokens plus a NARROW text rule, applied to every matrix entry

AC1 names nine prohibitions. Today three are covered by an ad-hoc regex in one component test.
Replace that scatter with `expectNoProhibitedTreatment(container, { family })` in the matrix
module's own test support, applied to **every** entry:

* **Class-token scan** (not a substring scan of `innerHTML`): reject `bg-gradient-*`,
  `bg-[linear-gradient…]`, `animate-pulse`, `animate-ping`, `animate-bounce`, `animate-spin`
  outside a `motion-reduce:animate-none` pairing, and any class token containing `glow`. A
  class-token scan is used because a substring scan of `innerHTML` matches the word "gradient"
  appearing in copy and cannot distinguish a class from prose.
* **Text rule, family-scoped.** An "invented percentage or ETA" is prohibited on `run` states
  (UX-DR10) — assert no `%`, no `ETA`, no `~`/`approximately`, and no `mm:ss`-shaped
  remaining-time string in a `run` entry. **Do not apply the `%` ban to `comparison`**: UX-DR11
  makes coverage, overtime and cost percentages legitimate product content there. A blanket `%` ban
  would either be wrong or would pass vacuously because no fixture rendered a percentage.
* **Merged action treatment** (UX-DR35): where a family renders more than one action, assert the
  actions' variant-bearing class sets are not identical. Story 3.6 already asserts this for Send vs
  Run optimization (`deferred-work.md:254`, CLOSED); this generalizes it to Approve as baseline.

Then **delete the two ad-hoc regexes** in `ActivityTimeline.test.tsx` only if the `message` family's
matrix entries cover the same ground; otherwise leave them and say why. Do not leave two
uncoordinated copies of the same rule.

**Does NOT cover:** a class-token scan cannot prove the absence of a glow, gradient or pulse
implemented through an inline `style` attribute, a background image, or a CSS rule in `index.css`
targeting an element by tag. The assertion is over class tokens and rendered text only; state that
limit in Completion Notes rather than claiming the prohibition is airtight.

### Decision 5 — AC1's "color-only status" clause is proven by the tree/text assertion, NOT by a colour computation

jsdom does not compute colours, and a real-browser colour comparison would need a second rendering
of every state with the palette perturbed — a runner this epic already cut once. The property AC1
actually makes checkable is the one `sprint-change-proposal-2026-08-09-epics-2-5.md:44-46` names:
the substantive rules "are all DOM-assertable". A state whose meaning survives only in colour has
the *same* text and the *same* role/name tree as its sibling, so Decision 3's pairwise assertion is
what goes red on it.

**Does NOT cover:** this does not prove sufficient colour *contrast*. That is axe's `color-contrast`
rule in AC2's browser layer, and Decision 10 owns the one open defect there.

### Decision 6 — AC2's four dimensions land in ONE new Playwright spec over the Epic 2–4 journey; Epic 1's four specs are not touched

`e2e/journey-accessibility.spec.ts` (new). It walks the completed desktop journey — Chat
(conversation timeline plus draft card), Runs (table plus progress), Results (comparison, approval
panel in its four states, provenance timeline) — and applies the **four dimensions AC2 names**:

1. **100% and 200% zoom** — via `document.documentElement.style.zoom = "2"`, the technique already
   established at `accessibility.spec.ts:110` and in `repair-journey-accessibility.spec.ts`. Not
   `deviceScaleFactor`, which changes rendering resolution rather than CSS zoom.
2. **WCAG text spacing** — reuse `layout-accessibility.spec.ts:102-107`'s exact injected rule
   (`line-height: 1.5`, `letter-spacing: 0.12em`, `word-spacing: 0.16em`) rather than re-deriving it.
3. **Reduced motion** — `page.emulateMedia({ reducedMotion: "reduce" })`.
4. **`expectAxeClean`** at the shared WCAG tag set, plus the three literal AC2 properties: no
   page-level horizontal scroll (`documentElement.scrollWidth <= clientWidth`), no overlapping
   sticky text, and no unreadable long identifier (an identifier element whose `scrollWidth`
   exceeds its `clientWidth` with no contained-scroll ancestor).

Epic 1's `accessibility.spec.ts`, `layout-accessibility.spec.ts`, `reduced-motion.spec.ts` and
`responsive.spec.ts` are **declared test files of Story 1.10's `accessibility_browser_layer`
check**. Adding Epic 2–4 surfaces into them would move this story's proof under 1.10's invariant
and destroy per-story attribution. One new file, registered under this story's own invariant.

**Does NOT cover:** it does not add phone or tablet viewport coverage for the Epic 2–4 surfaces —
AC2's Given clause says "the complete **desktop** journey", and `EXPERIENCE.md` scopes phone to
read-only triage. It also does not re-prove Scenario Data, which Story 1.10 owns.

### Decision 7 — The matrix is proven at BOTH layers, and the browser layer renders the matrix through the app, not through a mounted fixture harness

AC1's proof is the Vitest suite over `STATE_MATRIX` (jsdom plus `jest-axe`, the
`src/test/accessibility.test.tsx` shape). AC2's proof is the browser spec above. They answer
different questions — "is this state legible and distinct?" versus "does the real composed page
conform?" — and AC3 requires *each* to succeed.

Do **not** build a browser-mounted gallery route to render `STATE_MATRIX` in Playwright. That would
prove the fixtures conform, not the product. The browser spec drives real routes through
`installApiStubs`.

**Does NOT cover:** consequently, a state that exists in `STATE_MATRIX` but is unreachable through
the stubs is proven at the component layer only. Where that happens, name those states — do not
quietly claim browser coverage for them.

### Decision 8 — The generator is the thin-script shape, it ingests BOTH report sources, and it reuses `junit_ingest.parse_junit`

Story 4.5's Decision 11 states the fork: a matrix of independently orchestrated **pytest nodes**
becomes a `backend/evals/*_report.py` that runs them; a **pass/fail parsed from an already-produced
JUnit report** becomes a thin `backend/scripts/generate_*_evidence.py`. This story is the second
shape, twice over: AC3's verdict is a conjunction of one Vitest report and one Playwright report.

`backend/scripts/generate_state_semantics_evidence.py`, mirroring
`generate_repair_journey_evidence.py` structurally, with one correction: **parse through
`scripts.junit_ingest.parse_junit(path, runner=…)`, which already handles `pytest`, `vitest` and
`playwright` and already reads Playwright's project out of `hostname`.**
`generate_repair_journey_evidence.py` hand-rolled its own ElementTree parser; do not make that a
third copy.

Verdict rules, both sources, no exceptions: `tests > 0`, `executed > 0`, `skipped == 0`,
`failures == 0`, `errors == 0`, and for the Playwright source both `chromium` and `msedge` present.
Emit a top-level `passed` boolean. Refuse to write — `ValueError`, no file — when a declared binding
is missing or a required spec or test is absent from its report.

**Does NOT cover:** the generator does not run the suites. It parses reports produced by the
commands `docs/GATE-A-RUNBOOK.md` §3 already documents, so Task 12 must name those commands
exactly, including the Windows streaming-reporter variant and its different env var.

### Decision 9 — "Names every tested state" is DERIVED from the Vitest report, never hand-listed

AC3 says the artifact "names every tested state". A hand-written list in the generator is a second
copy of `STATE_MATRIX` with nothing checking it against the first — the drift shape this project
has paid for repeatedly.

Mechanism: the matrix suite iterates `STATE_MATRIX` with the state identity **in the test title**
(`` `${family}/${state}` ``). The generator reads the state names out of the Vitest JUnit report's
case names. A state dropped from the module therefore disappears from the artifact as a *missing
test*, not as a silently shorter list.

Pair it with one guard in the matrix suite asserting that the number of emitted per-state cases
equals `STATE_MATRIX.length`, so a state cannot be present in the module and silently skipped in
the run.

**Does NOT cover:** this proves the artifact names what the suite ran. It does not prove the suite
covers every state the *product* has — no mechanism can, short of enumerating states from source.
State that limit, and record AC1's ten families as the completeness claim actually being made.

### Decision 10 — `deferred-work.md:558` is MEASURED before it is fixed, and the scoped scans widen only on a green measurement

That entry records a `color-contrast` serious finding on `ScenarioResults`' outline Refresh control
— `#858585` on `#ffffff`, **3.69:1** — "during the window where `query.isFetching` is true". Its own
revisit trigger names this story: *"the first story that touches the shared Button disabled
treatment or the Gate A contrast floor; it should widen these three scans back to full-page in the
same change."* AC2 is that contrast floor.

**A correction is recorded at creation.** axe-core 4.13.0's `colorContrastMatches` returns `false`
for a disabled or inert node (measured in `node_modules/axe-core/axe.js`), so the violation cannot
have been produced by that button *while it was disabled*. The plausible mechanism is
`buttonVariants`' base `transition-all` fading `disabled:opacity-50` **after** `disabled` is
removed: for the duration of the transition the element is enabled and still dimmed. That makes the
finding timing-dependent, which matters, because a widened full-page scan would then be
intermittently red rather than reliably red.

Procedure, in this order:

1. Widen `accessibility.spec.ts`'s four `[data-approval-panel]`-scoped scans to full page and run
   them. Record the result and, if red, the exact node, computed colours and ratio.
2. **Green** → close `:558` citing the measurement **and** the axe-source finding above. No
   production change.
3. **Red** → the smallest fix under Decision 1: stop dimming *text that must stay readable* in the
   shared Button's disabled treatment (replace `disabled:opacity-50`'s effect on the foreground
   with a token pair holding ≥ 4.5:1), following the exact precedent of the `destructive` variant
   fix already recorded in `button.tsx`'s own comment (3.82:1 → solid). Add the contrast pair to
   `frontend/src/index.test.ts`'s existing `contrastRatio` assertions so it cannot regress
   unmeasured.
4. Either way, run the reduced-motion arm too: `index.css:151-160` neutralizes
   `transition-duration` under `prefers-reduced-motion: reduce`, so that arm should be
   deterministic. If it is green while the default arm is red, that **confirms** the transition
   mechanism — record it.

**Does NOT cover:** it does not restyle any other Button variant, and it does not touch the `dark:`
arm — no spec applies the `.dark` class and nothing in `src/` sets it, as `button.tsx`'s own comment
already records. It also does not touch `deferred-work.md:512` (the `aria-describedby`-on-a-disabled
-composer entry), which is a different disabled-control question.

### Decision 11 — Zero backend behaviour; the only backend files are registry, generator, and the generator's test

Five Gate A facts — one invariant and four checks — land in `backend/scripts/gate_a_checks.py`:

1. A new `Invariant` in `NFR29_GATES` — key `workflow_state_semantics`. **Not** in
   `AR28_INVARIANTS`: accessibility is deliberately modelled outside AR28's six, and the file says
   so at lines 68-73.
2. `GateACheck(check="state_semantics_matrix", runner="vitest", test_files=("frontend/src/test/stateMatrix.test.tsx",))`.
3. `GateACheck(check="journey_accessibility_browser_layer", runner="playwright", test_files=("frontend/e2e/journey-accessibility.spec.ts",), required_projects=("chromium", "msedge"))`.
4. `GateACheck(check="state_semantics_evidence", evidence_path="evidence/story-4.6/state-semantics-and-accessibility.json")` — **separate**, because `__post_init__` refuses evidence plus test_files on one check.
5. `GateACheck(check="state_semantics_report_machinery", runner="pytest", test_files=("backend/tests/test_state_semantics_evidence.py",))`, so the invariant never rests on a stored flag alone — the rule `test_registry_covers_more_than_the_four_evidence_files` enforces.

Add `"evidence/story-4.6/state-semantics-and-accessibility.json"` to the **exact set** at
`test_gate_a_readiness.py:265-281`, with a comment in the style of the entries already there.

**Zero-line diff fences:** `backend/application/**`, `backend/adapters/**`, `backend/api/**`,
`backend/domain/**`, `backend/engine/**`, `backend/llm/**`, `backend/ingest/**`, `backend/store/**`,
`backend/services/**`, `backend/migrations/**`, `backend/evals/**` (including
`backend/evals/golden/**`), `data/contract/**`, `frontend/openapi.json`,
`frontend/src/api/schema.d.ts`, and every existing `evidence/story-*/` directory other than the new
`story-4.6/`.

**Does NOT cover:** it does not retro-register Story 3.10's `repair-correctness.json`, still bound
to no `GateACheck` and still emitting `result` rather than `passed` (recorded at the top of
`deferred-work.md`). Sweeping it here is unrequested scope, exactly as Story 4.5's Decision 10
concluded.

### Decision 12 — Ledger reconciliation: two close, two re-point, two stay open and untouched

| Entry | Action | Why |
|---|---|---|
| `:294` — `evidence-accessibility.test.tsx` (5 cases) sits outside `accessibility_component_layer`'s declared files, so Gate A would report the invariant green with every evidence-focus assertion red | **CLOSE.** Add the file to that check's `test_files`. | Its trigger is literally *"the next story that already has a legitimate reason to touch `gate_a_checks.py`"* — AC3 forces that touch. |
| `:476` — "No Playwright/axe end-to-end scan covers the Runs workspace" | **CLOSE, citing Story 3.12.** | Stale: `repair-journey-accessibility.spec.ts:30` has covered Chat, **Runs** and Results since 3.12. Verify the premise before closing. |
| `:177` — ARIA-snapshot regression lock, assigned to "**Story 4.9**" | **RE-POINT, do not build.** Owner left open. | The owner string predates the 2026-08-09 consolidation that merged 4.9 into this story. No AC here asks for a regression *lock*: AC1 asks for distinctness, AC2 for conformance. `toMatchAriaSnapshot` introduces committed `.aria.yml` baselines — a **method-defined artifact**, exactly the shape root cause 1 cut from this epic. The frozen AC governs over a ledger owner string (Story 3.11 Trap 2; Story 4.5 Decision 5). |
| `:518` — Chat's SSE `/events` route is unstubbed, so every browser spec measures Chat in permanent `disconnected` fallback | **RE-POINT with the disclosure widened.** See Decision 12b. | |
| `:512` (`aria-describedby` on a disabled composer) and `:524` (`tabTo` forward-only) | **Leave open and untouched. Say so explicitly.** | `:524`'s trigger is "the first story that extends the keyboard suite's helper". If Task 6's spec does not use `tabTo`, the trigger has not fired. |
| `:558` | Per Decision 10 — closed only on a green measurement. | |

**Decision 12b — Chat is proven in its degraded variant in the browser, and that is disclosed.**
`installApiStubs` registers no handler for `GET /api/v1/conversations/{id}/events`, so
`useConversationStream` exhausts `MAX_CONSECUTIVE_FAILURES = 3` and `ChatView` renders
`ReconnectBanner state="disconnected"` for the whole run. AC1 names "alerts" and UX-DR23 names the
reconnect banner, so **the degraded variant is itself a required matrix state** — this is not purely
a defect. The healthy connected variant is proven at the **component layer** in `STATE_MATRIX` (all
three `ReconnectBanner` states plus `ChatView`'s connected rendering) and is marked
`NOT COVERED: chat_sse_healthy_stream:needs_local_sse_server` for the browser layer. **Do not stand
up a local SSE server** — that is the investment Story 3.12's Honest Gap b names, no AC here asks
for it, and it would be new test infrastructure inside a proof story.

**Does NOT cover:** re-pointing is not a judgement that any of these gaps do not matter, and closing
`:294` and `:476` does not audit the rest of the ledger.

---

## Tasks / Subtasks

- [x] **Task 1 — Re-derive every baseline before writing anything** (Decision 1)
  - [x] From `backend/`: `uv run --frozen pytest -q`, `uv run --frozen pytest -m postgres -q`,
        `uv run --frozen pytest tests/test_evidence_convention.py -q`.
  - [x] From `frontend/`: `npm test`, `npx tsc --noEmit`, `npm run lint`, `npm run build`, and
        `npx playwright test` (full run, both projects).
  - [x] Record all counts in Debug Log References, and record the **totals** alongside any pass/skip
        split — Story 3.12's review established that the split is environment-conditional while the
        total is the stable invariant.
  - Acceptance boundary: no code is written until the numbers are in the Debug Log. Any later
    failure is attributed against these numbers, never against Story 4.4's or 4.5's.

- [x] **Task 2 — Read the files this story asserts against and extends** (Decision 1)
  - [x] `frontend/src/components/primitives/fixtures.tsx` and `fixtures.test.tsx` — the exact
        per-primitive state lists Trap 1 names.
  - [x] `frontend/src/test/accessibility.test.tsx`, `accessibility-contract.test.tsx`,
        `evidence-accessibility.test.tsx` — the component-layer harness and its `expectAxeClean`
        configuration.
  - [x] `frontend/e2e/accessibility.spec.ts`, `layout-accessibility.spec.ts`,
        `reduced-motion.spec.ts`, `repair-journey-accessibility.spec.ts`,
        `e2e/support/accessibility.ts`, `e2e/support/apiStubs.ts`,
        `e2e/support/repairJourneyStubState.ts`.
  - [x] `frontend/src/features/chat/ActivityTimeline.tsx`, `chat/DraftCard.tsx`,
        `approvals/ApprovalDecisionPanel.tsx`, `approvals/ApprovalRequestCard.tsx`,
        `provenance/ProvenanceTimeline.tsx`, and `src/components/runs/{RunsTable,ProgressCard,RunStatusBadge}.tsx`
        — the components whose literal states the matrix enumerates.
  - [x] `backend/scripts/generate_repair_journey_evidence.py`, `backend/scripts/junit_ingest.py`,
        `backend/scripts/gate_a_checks.py`, `backend/tests/test_gate_a_readiness.py`,
        `backend/tests/test_repair_journey_evidence.py`.
  - Acceptance boundary: the File List records which of these were read, not merely opened.

- [x] **Task 3 — Build `frontend/src/test/stateMatrix.tsx`** (AC1; Decisions 2, 12b)
  - [x] Export `STATE_MATRIX: readonly StateFixture[]` with `{ family, state, render }`, `family`
        drawn from AC1's ten nouns, and `PRIMITIVE_FIXTURES` composed in unchanged.
  - [x] Cover, at minimum: **message** (planner message, agent response with a grounded claim,
        clarification, refusal, each terminal reason); **draft** (fresh, stale, rejected,
        queued-for-optimization); **run** (queued, running, completed, infeasible, timed out,
        cancelled, failed); **comparison** (populated, and "Not computed" for an absent metric);
        **approval** (pending, pending-overdue, rejected, expired, stale, consumed);
        **terminal-outcome** (each literal final state, plus a non-promotable result whose Approve
        control is absent or disabled per UX-DR13); **alert** (the four `InlineAlert` variants plus
        all three `ReconnectBanner` states); **skeleton**; **empty-state** (intrinsically empty
        versus filtered-empty, UX-DR15); **provenance** (collapsed and expanded item, with and
        without evidence refs).
  - [x] Every entry renders provider-free and deterministically — the `fixtures.tsx` contract. Where
        a component needs a router or a query client, wrap it inside the entry's own `render`, never
        in the consuming test.
  - Acceptance boundary: `fixtures.tsx` and `fixtures.test.tsx` have a **zero-line diff**.

- [x] **Task 4 — Write `frontend/src/test/stateMatrix.test.tsx`** (AC1; Decisions 3, 4, 5, 9)
  - [x] One case **per state**, titled `` `${family}/${state}` `` (Decision 9), each asserting:
        axe-clean at the shared WCAG tag set; the prohibited-treatment helper; non-empty text.
  - [x] Pairwise-within-family assertions: distinct normalized text, and distinct normalized
        `(role, accessible name)` trees (Decision 3).
  - [x] The count guard: emitted per-state cases equal `STATE_MATRIX.length`.
  - [x] The `run`-family text rule and the `comparison` carve-out exactly as Decision 4 states, with
        the UX-DR11 reason in a comment so a later reader does not "tighten" it.
  - [x] The UX-DR35 merged-action assertion for every family rendering more than one action.
  - Acceptance boundary: every new assertion is **demonstrated red once** — weaken the guard or
    corrupt the fixture, observe the failure, restore, and record the RED→GREEN line. A guard that
    cannot be made to fail by a relevant mutation does not count.

- [x] **Task 5 — Reconcile the two ad-hoc prohibition regexes** (Decision 4)
  - [x] If the `message` family's matrix entries cover `ActivityTimeline.test.tsx:281` and `:430`,
        delete those two lines and say so. Otherwise leave them and record why in Completion Notes.
  - Acceptance boundary: the repository ends with **one** statement of the UX-DR32 prohibition rule,
    not two uncoordinated copies.

- [x] **Task 6 — Write `frontend/e2e/journey-accessibility.spec.ts`** (AC2; Decisions 6, 7, 12b)
  - [x] Drive the real desktop journey through `installApiStubs` — Chat (timeline plus draft), Runs
        (table plus progress), Results (comparison, all four approval-panel states, provenance).
  - [x] Apply all four dimensions from Decision 6, reusing `layout-accessibility.spec.ts`'s exact
        text-spacing rule and `accessibility.spec.ts`'s `style.zoom = "2"` technique.
  - [x] Assert the three literal AC2 properties: no page-level horizontal scroll; no overlapping
        sticky text; no unreadable long identifier.
  - [x] Record which `STATE_MATRIX` states are **not** reachable through the stubs (Decision 7), and
        which browser states are measured in the degraded Chat variant (Decision 12b).
  - Acceptance boundary: the spec must pass under **both** `chromium` and `msedge`; a chromium-only
    pass does not satisfy `required_projects`.

- [x] **Task 7 — Execute Decision 10's contrast measurement, in its stated order** (AC2; Decision 10)
  - [x] Widen `accessibility.spec.ts`'s four `[data-approval-panel]`-scoped scans to full page; run
        both the default and the `reducedMotion: "reduce"` arms; record the node, computed colours
        and ratio for anything red.
  - [x] Green → close `deferred-work.md:558` citing the measurement **and** the axe-source finding.
        Red → apply the smallest shared-Button fix and add the contrast pair to
        `frontend/src/index.test.ts`'s `contrastRatio` assertions.
  - Acceptance boundary: whichever branch is taken, Completion Notes state the measured values.
    "It passed now" without numbers is not a measurement.

- [x] **Task 8 — Write `backend/scripts/generate_state_semantics_evidence.py`** (AC3; Decisions 8, 9)
  - [x] Mirror `generate_repair_journey_evidence.py` structurally, but parse through
        `scripts.junit_ingest.parse_junit` for both sources — no third XML parser.
  - [x] Require, per source: `tests > 0`, `executed > 0`, `skipped == 0`, `failures == 0`,
        `errors == 0`; and `chromium` plus `msedge` for the Playwright source.
  - [x] Derive `results.states` from the Vitest report's case names (Decision 9). Never a literal
        list.
  - [x] Emit a top-level `passed` boolean; bind through `resolve_bindings()` supplying only the
        seven prose keys (`evaluator`, `model`, `prompt`, `tool`, `policy`, `application`, `solver`)
        and never `code`, `dataset`, `scenario`, `image` or `schema_version`.
  - [x] Bind `contract_digests` over the modules that decide every asserted value — including
        `e2e/support/apiStubs.ts` and `e2e/support/repairJourneyStubState.ts`. Story 3.12's review
        found exactly this omission.
  - [x] `ValueError` and **no file** when a declared binding is missing or a required spec or test is
        absent from its report.
  - Acceptance boundary: the failure path is reachable and tested, not dead code.

- [x] **Task 9 — Write `backend/tests/test_state_semantics_evidence.py`** (Decision 8)
  - [x] Mirror `test_repair_journey_evidence.py`: all-pass writes `passed: true`; a failing source
        writes `passed: false` and still writes the file; an all-skipped report is **refused**; a
        report missing a required project is refused; a missing declared binding raises `ValueError`
        naming the key and writes nothing.
  - [x] All writes to `tmp_path` with `allow_dirty=True`.
  - Acceptance boundary: `assert not output.exists()` on every refusal case.

- [x] **Task 10 — Register the Gate A invariant and all four checks** (AC2, AC3; Decisions 11, 12)
  - [x] Add the `Invariant` to `NFR29_GATES`, not to `AR28_INVARIANTS`.
  - [x] Add the four checks of Decision 11. Never one check declaring both `evidence_path` and
        `test_files`.
  - [x] Add `frontend/src/test/evidence-accessibility.test.tsx` to `accessibility_component_layer`'s
        `test_files`, and close `deferred-work.md:294`.
  - [x] Add the new evidence path to the **exact set** in `test_gate_a_readiness.py`, with a comment.
  - [x] Confirm `test_every_invariant_has_at_least_one_contributing_check` and
        `test_registry_covers_more_than_the_four_evidence_files` were **seen to fail first** with an
        incomplete registration, then pass.
  - Acceptance boundary: the registry additions are demonstrated-red through both existing guards.

- [x] **Task 11 — Re-run Gate A** (AR28)
  - [x] Produce the three JUnit reports per `docs/GATE-A-RUNBOOK.md` §3 and run
        `gate_a_readiness.py`. Expect `gate_a_passed: true`, `blocking: []`, and the new
        `workflow_state_semantics` invariant present and passing.
  - Acceptance boundary: a green gate that does not list the new invariant means it was registered
    but not contributed to — the unbound-proof failure this repository has already hit twice.

- [x] **Task 12 — Generate the evidence in the convention's order** (AC3; `docs/EVIDENCE-CONVENTION.md`)
  - [x] `git commit` the code. Confirm `git status --porcelain` is empty.
  - [x] Run the two measurement suites with their JUnit reporters, using the exact runbook commands
        (Windows: the committed streaming reporter and `PLAYWRIGHT_JUNIT_OUTPUT_FILE`).
  - [x] Generate through the new script; run
        `uv run --frozen pytest tests/test_evidence_convention.py -q`.
  - [x] `git commit` the evidence **on its own**, and make sure the commit it binds to touches at
        least one code file.
  - Acceptance boundary: no hand-typed field anywhere in the artifact, and no docs-only commit
    between the code commit and the evidence commit.

- [x] **Task 13 — Reconcile the planning record** (Decision 12)
  - [x] Close `:294` and `:476` citing this story (and Story 3.12 for `:476`), verifying `:476`'s
        premise against `repair-journey-accessibility.spec.ts` before closing it.
  - [x] Re-point `:177` (ARIA snapshot) with Decision 12's reasoning and the owner left open.
  - [x] Re-point `:518` with Decision 12b's widened Chat disclosure.
  - [x] Confirm `:512` and `:524` — and `:558` if Task 7 came back red without a fix landing — are
        left open and untouched, and say so.
  - [x] Record for the Epic 4 retrospective: the two items Story 4.5 carried in (the AC4 CloudWatch
        wording defect, and its Decision 3's unreachable `changed policy` fixture), plus anything
        this story raises.
  - Acceptance boundary: no ledger entry is deleted; closure is recorded beside the original
    wording, per the file's own convention.

- [x] **Task 14 — Run every suite and record the deltas**
  - [x] Backend default, `-m postgres`, evidence convention; frontend `npm test`, typecheck, lint,
        build; full `npx playwright test` across both projects.
  - [x] Confirm the CI floors in `.github/workflows/ci.yml` still hold. They are floors and
        ceilings, so added tests never redden them — do **not** edit the numbers.
  - Acceptance boundary: every failure attributed against Task 1's re-derived baseline.

---

## Dev Notes

### Files being modified — read these before editing

| File | State today | This story changes | Must not break |
|---|---|---|---|
| `frontend/src/test/stateMatrix.tsx` | does not exist | NEW — `STATE_MATRIX`, composing `PRIMITIVE_FIXTURES` | — |
| `frontend/src/test/stateMatrix.test.tsx` | does not exist | NEW — AC1's proof, one case per state | — |
| `frontend/e2e/journey-accessibility.spec.ts` | does not exist | NEW — AC2's four dimensions over Epic 2–4 surfaces | — |
| `backend/scripts/generate_state_semantics_evidence.py` | does not exist | NEW — two-source thin-script generator | — |
| `backend/tests/test_state_semantics_evidence.py` | does not exist | NEW — generator machinery gate | — |
| `evidence/story-4.6/state-semantics-and-accessibility.json` | does not exist | NEW — generated, never hand-typed | — |
| `frontend/src/components/primitives/fixtures.tsx` | 194 lines, 27 entries, 8 primitives | **zero-line diff** — composed in, never edited | `fixtures.test.tsx`'s exact per-primitive state lists |
| `frontend/e2e/accessibility.spec.ts` | 127 lines; four approval scans scoped to `[data-approval-panel]`; provenance at 100/200% zoom | Task 7 widens the four scoped scans to full page | its Scenario Data sweep at three viewports, and Story 1.10's `accessibility_browser_layer` registration |
| `frontend/src/features/chat/ActivityTimeline.test.tsx` | two ad-hoc prohibition regexes at `:281`, `:430` | Task 5 removes them only if the matrix covers the same ground | the rest of its timeline coverage |
| `frontend/src/components/ui/button.tsx` | shared base carries `transition-all` plus `disabled:opacity-50`; `destructive` already solid after 3.12's contrast fix | **only if Task 7 measures red** — smallest disabled-foreground fix | every Button variant across Chat, Runs, Evidence, Fixture Catalogue; the `dark:` arm stays untouched |
| `frontend/src/index.test.ts` | 155 lines; token and WCAG `contrastRatio` guards | one contrast pair added **only if** Task 7 fixes the Button | its exact token and dark-theme inline snapshots |
| `backend/scripts/gate_a_checks.py` | `NFR29_GATES` has four invariants; `GATE_A_CHECKS` has 27 checks | one invariant, four checks, one file added to `accessibility_component_layer` | `validate_registry()`; `__post_init__`'s refusal of evidence plus test_files |
| `backend/tests/test_gate_a_readiness.py` | registered evidence paths are an **exact set of six** | one path added, with a comment | every other registry guard in the module |
| `_bmad-output/implementation-artifacts/deferred-work.md` | `:177` `:294` `:476` `:518` `:558` open | two closed, two re-pointed, `:558` per Task 7 | `:512` and `:524` stay open and untouched |

### Traps — the quietest first

1. **`fixtures.test.tsx` asserts an EXACT per-primitive state list.** Adding a single entry to
   `PRIMITIVE_FIXTURES` reddens a test that reads as unrelated to this story. Compose, never edit
   (Decision 2).
2. **A blanket `%` ban is wrong.** UX-DR11 makes coverage, overtime and cost percentages legitimate
   in comparison summaries. The existing `/approximately|confidence|%/i` regex is scoped to a claim
   block; copying it matrix-wide either bans real content or passes vacuously because no fixture
   rendered a percentage (Decision 4).
3. **A substring scan of `innerHTML` cannot distinguish a class from prose.** `/gradient/i` matches
   the word "gradient" in copy. Scan class tokens (Decision 4).
4. **axe-core 4.13.0 skips disabled and inert nodes for `color-contrast`.** An assertion aimed at a
   disabled control cannot go red, and `deferred-work.md:558`'s recorded mechanism is therefore not
   what it says it is (Decision 10). Assert on the enabled state or on the CSS token.
5. **The registered-evidence-path set is an exact equality, not a superset.** Adding the path to
   `gate_a_checks.py` without adding it to the assertion in `test_gate_a_readiness.py` reddens a
   test that reads as unrelated. It is deliberate: the docstring says growth must be a decision.
6. **`GateACheck.__post_init__` raises on one check declaring both `evidence_path` and
   `test_files`.** Two checks, never one.
7. **A skipped run exits 0.** Both report sources need the skip-is-not-a-pass rule, and the
   Playwright source additionally needs both projects present — otherwise a chromium-only run
   satisfies `required_projects` silently.
8. **`--reporter=junit` goes on the Playwright command line only.** `playwright.config.ts` pins
   `reporter: "list"` and `GATE-A-RUNBOOK.md` §3 requires that committed default to stay put. The
   Windows streaming reporter reads a **different** env var (`PLAYWRIGHT_JUNIT_OUTPUT_FILE`).
9. **`e2e/support/apiStubs.ts` returns 405 for every non-GET except three POSTs.** A browser state
   needing a mutation response needs a new branch — and `repairJourneyStubState.ts` is what decides
   the asserted values, so both modules must be bound in `contract_digests` (Story 3.12's review
   found exactly that omission).
10. **`apiStubs.ts`'s timeline fixture pairs `metric: "required_headcount_minutes"` with
    `family: "outbound"`.** `docs/DOMAIN-MODEL.md` §1 and §3 make that pairing impossible in
    production: `headcount` is emitted only for `indirect`, and a `volume` row read as minutes is
    "a wrong number wearing a valid evidence locator". It is a rendering stub and the frontend
    enforces no dimension, so **do not fix it** — that would move an asserted value in existing
    specs and is not this story's — but **do not copy it** into a new `message` fixture either. A
    new claim fixture uses a pairing the domain model permits.
11. **Chat is measured in its `disconnected` variant in every browser spec** (Decision 12b). A
    matrix state claiming "Chat connected, proven in a browser" would be false.
12. **A test that renders `STATE_MATRIX` inside Playwright proves the fixtures, not the product**
    (Decision 7).
13. **`document.documentElement.style.zoom = "2"` is the established 200% technique**, not
    `deviceScaleFactor`, which changes rendering resolution rather than CSS zoom.
14. **A guard that cannot go red.** This project's most expensive recurring defect, named in the
    Epic 1–2 and Epic 3 retrospectives and found again at 4.1, 4.2, 4.4 and 4.5 review. Every new
    assertion here is demonstrated-red once, and the RED→GREEN line recorded.

### Honest gaps this story ships with — state them in Completion Notes

(a) **The prohibition assertion is over class tokens and rendered text only** (Decision 4). A glow,
    gradient or pulse introduced through an inline `style`, a background image, or a tag-targeted
    rule in `index.css` would not redden it.

(b) **Chat's healthy connected stream is not proven in a browser**, only at the component layer —
    `NOT COVERED: chat_sse_healthy_stream:needs_local_sse_server` (Decision 12b,
    `deferred-work.md:518`).

(c) **Completeness of the matrix is a claim about AC1's ten families, not about the product's full
    state space** (Decision 9). No mechanism enumerates states from source.

(d) **The ARIA-snapshot regression lock is re-pointed, not built** (Decision 12). The accessibility
    tree remains protected by distinctness and axe assertions, not by a recorded baseline.

(e) **Phone and tablet coverage for the Epic 2–4 surfaces is out of scope** — AC2 says "the complete
    **desktop** journey", and `EXPERIENCE.md` scopes phone to read-only triage (Decision 6).

(f) **`deferred-work.md:512` and `:524` remain open and untouched**, and `:558` remains open if
    Task 7 measured red without a fix landing.

### Testing requirements

- Frontend unit and component tests live beside or under `frontend/src/`; the matrix module and its
  suite go in `frontend/src/test/`, because `test_runner_matches_the_file_location` requires every
  vitest-registered Gate A file to start with `frontend/src/` and `vite.config.ts` scopes
  `test.include` to `src/**`.
- Browser specs live in `frontend/e2e/` and must pass under **both** `chromium` and `msedge`.
- `oxlint`'s `react/only-export-components` is why the fixture module is separate from its test
  module — the same reason Story 1.6 split `fixtures.tsx` from `fixtures.test.tsx`.
- Backend additions are plain unmarked pytest exercising the generator directly with `tmp_path` and
  `allow_dirty=True`, never through a subprocess.
- **No new golden cases.** This story ships no capability and no model-facing surface, so a golden
  case would be a case about nothing — the conclusion Stories 3.10, 3.11, 3.12 and 4.5 all reached.
  Do not pad toward NFR28's floor; `epics.md:1557` forbids padding explicitly.

### Project structure notes

Every new path matches an established convention: `frontend/src/test/` for cross-feature test
fixtures and sweeps (precedent: `evidenceHighlights.ts`, `accessibility.test.tsx`),
`frontend/e2e/` for browser specs, `backend/scripts/generate_*_evidence.py` for a thin-script proof
generator (Stories 2.4, 3.5, 3.12), `backend/tests/test_*_evidence.py` for its machinery gate,
`evidence/story-4.6/` for the artifact, and `backend/scripts/gate_a_checks.py` as the single
registry. No module is renamed; AR26's structural convergence is unaffected.

### Open questions — neither blocks this story

1. **Should the ARIA-snapshot regression lock ever be built?** Decision 12 re-points it with the
   owner open. Against: it is a method-defined artifact of the class this epic already cut. For:
   distinctness assertions do not lock the tree against silent regression. **Deadline: the Epic 4
   retrospective** — carry it in as input alongside Story 4.5's two.
2. **Should `accessibility_and_responsiveness` and `workflow_state_semantics` eventually merge?**
   Both are NFR29 accessibility invariants split by story ownership. Merging loses per-story
   attribution; keeping them split means Gate A reports two accessibility invariants. **Deadline:
   whichever story next adds a third accessibility invariant.**

### References

- [Source: `_bmad-output/planning-artifacts/epics.md:1316-1339` — Story 4.6 ACs and the proof-method note]
- [Source: `_bmad-output/planning-artifacts/epics.md:196,198,202,238,240,244,246` — UX-DR10, UX-DR11, UX-DR13, UX-DR31, UX-DR32, UX-DR34, UX-DR35]
- [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-08-09-epics-2-5.md:36-73,147,150-153` — root causes 1 and 2; the 4.6–4.9 consolidation; the 4.7 cut]
- [Source: `_bmad-output/planning-artifacts/architecture/architecture-epic-4-2026-08-27/ARCHITECTURE-SPINE.md` — EAD-4, EAD-5, EAD-7; Story → Architecture Map; Verification Obligations 3 and 4]
- [Source: `_bmad-output/planning-artifacts/ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md` — Accessibility Floor; Responsive & Platform]
- [Source: `docs/EVIDENCE-CONVENTION.md` — the rule; the monotone principle; a verdict key Gate A can read]
- [Source: `docs/GATE-A-RUNBOOK.md` §3 — the three JUnit reporter commands and the Windows streaming variant]
- [Source: `docs/DOMAIN-MODEL.md` §1, §2, §3 — family/unit; assignments carry no family (Trap 10)]
- [Source: `_bmad-output/implementation-artifacts/1-6-establish-shiftmind-design-tokens-and-shared-primitives.md` — Task 4; "iterate `PRIMITIVE_FIXTURES` and change nothing here"]
- [Source: `_bmad-output/implementation-artifacts/1-10-prove-scenario-data-accessibility-and-responsiveness.md` — the two-layer harness and its Gate A-only scope boundary]
- [Source: `_bmad-output/implementation-artifacts/3-12-prove-the-repair-browser-journey.md` — the thin-script generator precedent; Decision 2 and Honest Gap b on SSE]
- [Source: `_bmad-output/implementation-artifacts/4-5-prove-approval-and-audit-invariants.md` — Decisions 1, 2, 10, 11; the Gate A two-check pattern]
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md` — `:177`, `:294`, `:476`, `:512`, `:518`, `:524`, `:558`]
- [Source: `frontend/src/components/primitives/fixtures.tsx`, `fixtures.test.tsx` — the Story 1.6 fixture catalogue and its exact-list guards]
- [Source: `frontend/src/test/accessibility.test.tsx`, `accessibility-contract.test.tsx`, `evidence-accessibility.test.tsx` — the component axe layer]
- [Source: `frontend/e2e/accessibility.spec.ts`, `layout-accessibility.spec.ts`, `reduced-motion.spec.ts`, `repair-journey-accessibility.spec.ts`, `e2e/support/accessibility.ts`, `e2e/support/apiStubs.ts` — the browser layer and its stubs]
- [Source: `frontend/src/index.css:151-160` — the global reduced-motion rule; `frontend/src/index.test.ts` — the token and `contrastRatio` guards]
- [Source: `frontend/src/components/ui/button.tsx` — `transition-all`, `disabled:opacity-50`, and the recorded `destructive` contrast-fix precedent]
- [Source: `node_modules/axe-core/axe.js` — `colorContrastMatches` returns false for disabled or inert nodes (axe-core 4.13.0)]
- [Source: `backend/scripts/gate_a_checks.py` — `NFR29_GATES`, `GateACheck.__post_init__`, `accessibility_component_layer`]
- [Source: `backend/tests/test_gate_a_readiness.py:265-281` — the exact registered-evidence-path set]
- [Source: `backend/scripts/junit_ingest.py` — `parse_junit` for pytest/vitest/playwright; project read from `hostname`]
- [Source: `backend/scripts/generate_repair_journey_evidence.py` — the thin-script shape; the "NFR20 is deliberately absent" note]
- [Source: `.github/workflows/ci.yml` — floors and ceilings; the vitest JSON reporter invocation]

---

## Dev Agent Record

### Agent Model Used

OpenAI GPT-5 Codex

### Implementation Plan

Follow Tasks 1–14 in order, with demonstrated RED→GREEN proof for every new assertion, a
measurement before any production change (Decision 1), a code commit before measurement, and a
separately generated evidence commit.

### Debug Log References

- Task 1 baseline (2026-09-02, branch head `8b2b5b1`, PostgreSQL healthy): backend default
  1,499 total = 1,490 passed + 2 skipped + 7 deselected; PostgreSQL marker 1,499 total =
  156 passed + 1,343 deselected; evidence convention 80/80 passed. Frontend Vitest 84 files,
  581/581 tests passed; TypeScript clean; oxlint exited 0 with three pre-existing
  `react/only-export-components` warnings; production build passed. `npm run test:e2e` rebuilt
  `frontend/dist/` and Playwright passed 66/66 across chromium and msedge (9 spec files).
- Tasks 3–4 RED→GREEN: absent `stateMatrix` failed module resolution; the first implementation
  then failed the reduced-motion treatment and provenance role/name distinctness guards (3
  failures), and the corrected composition passed 62/62. The test suite now passes 62 per-state
  and aggregate cases, and the full frontend baseline is 85 files / 643 tests.
- Task 6: after a fresh production build, `journey-accessibility.spec.ts` passed 2/2 (chromium and
  msedge). Browser disclosure: Chat is the disconnected/degraded variant; the healthy SSE stream
  remains component-only.
- Task 7 measurement: widened full-page scans observed the outline Refresh control at `#858585`
  on `#ffffff`, ratio 3.69:1 (required 4.5:1), in msedge under default and reduced-motion runs.
  Replacing shared disabled opacity with muted/foreground (`#252525` on `#f7f7f7`) made all 16
  approval scans pass across both projects and both motion preferences.
- Task 10 RED→GREEN: with `workflow_state_semantics` deliberately registered before its checks,
  both `test_every_invariant_has_at_least_one_contributing_check` and
  `test_registry_covers_more_than_the_four_evidence_files` failed; after four checks, both passed.
- Tasks 11–14: Story evidence `10f1be2` binds code commit `792c031`; the code commit touches
  generator/test code and no docs-only commit intervenes. Gate A report `3ae65a8` records
  `gate_a_passed: true`, `blocking: []`, and `workflow_state_semantics: passed`. Final suites:
  backend 1,511 total = 1,503 passed + 1 skipped + 7 deselected (the pass/skip split is
  environment-conditional), PostgreSQL 156 passed + 1,355 deselected, evidence convention 87
  passed; frontend 85 files / 643 tests, TypeScript clean, oxlint green with three pre-existing
  Fast Refresh warnings, production build green, Playwright 76/76 across 10 files and both projects.
- The streaming reporter wrote all 76 cases with zero failures/skips but exhibited its documented
  no-`onEnd` hang; the run was stopped only after its case count matched `playwright test --list`.
  The CI count floors/skip ceilings remain satisfied and were not edited.
- Honest gaps: (a) prohibited-treatment coverage scans class tokens/rendered text, not inline style,
  background images, or tag-targeted CSS; (b) `NOT COVERED: chat_sse_healthy_stream:needs_local_sse_server`;
  (c) matrix completeness is the ten AC1 families, not source-enumerated product state; (d) the
  ARIA snapshot lock is re-pointed, not built; (e) phone/tablet Epic 2–4 coverage is out of scope;
  (f) deferred-work entries formerly at `:512` and `:524` remain open and untouched. Story 4.5's
  CloudWatch wording defect and unreachable changed-policy fixture remain Epic 4 retrospective input.

### Completion Notes List

### File List

- Read for Task 2: `frontend/src/components/primitives/fixtures.tsx`,
  `frontend/src/components/primitives/fixtures.test.tsx`, `frontend/src/test/accessibility.test.tsx`,
  `frontend/src/test/accessibility-contract.test.tsx`, `frontend/src/test/evidence-accessibility.test.tsx`,
  `frontend/e2e/accessibility.spec.ts`, `frontend/e2e/layout-accessibility.spec.ts`,
  `frontend/e2e/reduced-motion.spec.ts`, `frontend/e2e/repair-journey-accessibility.spec.ts`,
  `frontend/e2e/support/accessibility.ts`, `frontend/e2e/support/apiStubs.ts`,
  `frontend/e2e/support/repairJourneyStubState.ts`, `frontend/src/features/chat/ActivityTimeline.tsx`,
  `frontend/src/features/chat/DraftCard.tsx`, `frontend/src/features/approvals/ApprovalDecisionPanel.tsx`,
  `frontend/src/features/approvals/ApprovalRequestCard.tsx`, `frontend/src/features/provenance/ProvenanceTimeline.tsx`,
  `frontend/src/components/runs/RunsTable.tsx`, `frontend/src/components/runs/ProgressCard.tsx`,
  `frontend/src/components/runs/RunStatusBadge.tsx`, `backend/scripts/generate_repair_journey_evidence.py`,
  `backend/scripts/junit_ingest.py`, `backend/scripts/gate_a_checks.py`,
  `backend/tests/test_gate_a_readiness.py`, `backend/tests/test_repair_journey_evidence.py`.
- Modified: `_bmad-output/implementation-artifacts/4-6-prove-workflow-state-semantics-and-automated-accessibility.md`,
  `_bmad-output/implementation-artifacts/deferred-work.md`, `_bmad-output/implementation-artifacts/sprint-status.yaml`,
  `backend/scripts/gate_a_checks.py`, `backend/tests/test_gate_a_readiness.py`,
  `frontend/e2e/accessibility.spec.ts`, `frontend/src/components/ui/button.tsx`,
  `frontend/src/features/chat/ActivityTimeline.test.tsx`, `frontend/src/index.test.ts`,
  `evidence/story-1.11/gate-a-readiness-report.json`.
- Added: `backend/scripts/generate_state_semantics_evidence.py`,
  `backend/tests/test_state_semantics_evidence.py`, `frontend/e2e/journey-accessibility.spec.ts`,
  `frontend/src/test/stateMatrix.tsx`, `frontend/src/test/stateMatrix.test.tsx`,
  `evidence/story-4.6/state-semantics-and-accessibility.json`.

---

## Change Log

| Date | Change |
|---|---|
| 2026-09-02 | Story created. Twelve decisions recorded; "the Story 1.6 fixture catalogue" pinned to `PRIMITIVE_FIXTURES`; AC2's four dimensions measured as covering Scenario Data only today; `deferred-work.md:558` corrected against axe-core's own source and gated behind a measurement. |
| 2026-09-02 | Implemented the enumerable state matrix, completed-journey accessibility proof, measured shared Button contrast fix, fail-closed two-source evidence generator, four-check NFR29 registration, generated evidence, green Gate A report, and ledger reconciliation. Status moved to review. |
