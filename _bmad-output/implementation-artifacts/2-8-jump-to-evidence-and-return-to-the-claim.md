---
baseline_commit: fa18cf1f5e3e74c87fef4578a8867c4a0a9e11a0
---

# Story 2.8: Jump to Evidence and Return to the Claim

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a planner,
I want to move from an agent claim to its exact source record and back,
so that verification does not make me lose my place or conversation context.

**Unblocks:** nothing structurally — this is the last planner-visible piece of FR-7. Story 2.9
(clarify/refuse/fail) is independent of it.

**Depends on, and consumes:** Story 1.5's six exact-target resolve endpoints (built for this story by
name and still having **zero frontend consumers**), Story 1.6's `EvidenceHighlight` primitive and
evidence design tokens (built for this story and still unused in product code), Story 1.8's
`useColumnVisibility` field-reveal mechanism (already reads `?field=`), and Story 2.7's persisted
`EvidenceRefV1` locators and inert `EvidenceLink` activation seam.

---

## Six decisions were made at story creation — do not re-litigate them

### Decision 1 — The evidence target is **resolved**, never **paged to**

The cited record is fetched from Story 1.5's resolve endpoint for its group
(`GET /api/v1/scenarios/{scenario_id}/projection/{group}/{record_id}?scenario_version_id=…`). The
story does **not** compute which page the record falls on and does **not** add a "locate cursor"
endpoint.

Why this is settled:

- Story 1.5's own header states it: *"The evidence navigation UI that consumes this resolver is
  Story 2.8's acceptance boundary … There is no frontend UI work in this story"*
  (`1-5-resolve-exact-evidence-targets.md:17`), and its AC1 is *"exact-target lookup reveals that
  record **without retargeting**"*. Six endpoints exist, fully tested, with an NFR35 measurement
  already recorded against them — and **not one line of frontend code calls them.**
- AR4 names *"bounded cursor windows/counts, **and** exact-target lookup"* as two mechanisms.
  UX-DR24 lists both. Paging is for browsing; resolving is for citations.
- The pagination cursor is a bare integer offset **not pinned to a `scenario_version`**
  (`deferred-work.md:59`, accepted as a known limitation). A jump built on paging would inherit that
  fact-drift hazard on the one surface whose entire purpose is exactness.

**Cost:** six thin client wrappers plus one group→resolver dispatch map. **Consequence: this story
has a ZERO-LINE `backend/` diff.** See the fences in Task 8.

### Decision 2 — The target renders as **one focused record region above the grid**, not as a highlighted row inside it

`EvidenceHighlight` (`frontend/src/components/primitives/EvidenceHighlight.tsx`, Story 1.6) is a
`div` with `tabIndex={-1}` and `EVIDENCE_HIGHLIGHT_CLASS`. It was built for this and has no product
call site today. The resolved record renders inside it, above the group's grid; the grid stays
mounted, unfiltered, so the planner can inspect neighbouring rows (EXPERIENCE Flow 3 step 4).

Why not a row highlight:

1. The resolved record is usually **not on the current page** — that is the whole point of resolving
   it — so there is frequently no row to highlight, and "highlight it only when it happens to be
   rendered" is exactly the *"report missing merely because the row was not currently rendered"*
   failure `EXPERIENCE.md:112` forbids.
2. Two of the six groups render **no `record_id` column at all** (`workers` shows `contact_id`,
   `work-areas-and-tasks` shows `task_id` — `columns.ts:20-37`). A row highlight in those groups
   cannot name the cited record.
3. UX-DR18 requires *"focus and highlight exactly **one** target"*, and UX-DR34 permits the
   highlight treatment on *"the resolved row/cell/**record**"*. A record region is one of the three
   named forms and is the only one that is always available.

**Corollary (assert it):** exactly one element carrying `EVIDENCE_HIGHLIGHT_CLASS` exists on the
page. If the resolved record also happens to be on the rendered page, **do not** highlight the row
too.

### Decision 3 — The **origin** is app-owned history/session state. The **target** is in the URL. Neither is ever model-produced

- **Target half** (`group`, `record`, `version`, optional `field`, optional `start`/`end`) → URL
  search params on `/scenarios/:scenarioId/data`. Required by UX-DR24 and
  `EXPERIENCE.md:140` (*"Browser Back/Forward restores surface, filters, **evidence target**, and
  origin"*), and `ScenarioDataView` already reads `?group=` and `?field=` from search params.
- **Origin half** (`conversationId`, `activityId`, `segmentIndex`, `refIndex`) → react-router
  `navigate(to, { state })` **plus** one read-once `sessionStorage` slot. Never the URL, never a
  query param, never a redirect target.

AC3's invariant — *"the full locator is owned by the application and never entrusted to a
model-generated URL"* (AR15) — is satisfied structurally: every part of both halves is read from the
typed `EvidenceRefV1` the grounding gate persisted. **The model produces no string that becomes a
route, an `href`, or a DOM attribute.** Prose segments render as text nodes only.

The `sessionStorage` mirror exists because AC1 names **browser Back** as an equal path to *Return to
claim*, and a Back navigation lands on the Chat history entry whose own `state` predates the jump.
Read-once (consume on restore) so an unrelated later Chat visit cannot steal focus.

**Guard (Task 8):** a test asserting no `href`, `to`, `src`, or `navigate()` argument anywhere under
`frontend/src/features/chat/` or `frontend/src/features/evidence/` is derived from a
`GroundedProseSegmentV1.text` value or any other free-text model output.

### Decision 4 — Claim identity is `(activity_id, segment index, ref index)`. This story adds **no** `claim_id`

`GroundedClaimV1` has no claim identifier. `result_id` is content-addressed and deliberately **not**
unique per claim — two claims citing one calculation share it, which is why
`ActivityTimeline.tsx:119` already keys on `claim-${result_id}-${index}`.

Adding a `claim_id` to `GroundedResponseV1` would be a breaking change to a **persisted** contract
with no compat alias and no migration — precisely the hazard `deferred-work.md:194` records against
`MetricV1`. `ActivityCommonOut` already ships `activity_id`, `conversation_id`, `scenario_id` and
`scenario_version_id` on every item (`api/schemas.py:122-135`), so the origin key is composable from
data already on the wire.

One consequence, stated so it is not discovered late: the origin key is **positional**. It is stable
for the lifetime of a persisted activity (the payload is immutable) and that is all it needs to be.

### Decision 5 — Exception states branch on the RFC 7807 **`code`**, not on the HTTP status

Story 1.5 already returns three discriminable outcomes
(`api/routers/scenario_projection.py:475-501`):

| Server outcome | Status | `code` | Panel |
|---|---|---|---|
| Cited version ≠ current version | 404 | `evidence_version_mismatch` | **Version mismatch** |
| Authorized scenario, no such record | 404 | `evidence_not_found` | **Missing evidence** |
| Scenario invisible to this session (RLS) | 404 | `resource_not_found` | **Unauthorized** |
| Forbidden | 403 | `request_forbidden` | **Unauthorized** |
| No session | 401 | `authentication_required` | existing `useRedirectOnUnauthorized` |

**Non-disclosure is already correct and must not be "fixed".** `evidence_not_found` is only ever
reachable by a caller already authorized for that scenario; an unauthorized prober receives the bare
`resource_not_found` for every locator alike. Collapsing the two would destroy the distinction an
*authorized* planner needs (UX-DR20 requires four distinct states) without adding any protection.

`lib/errors.ts` gains `getErrorCode(error)` beside `getErrorStatus`. Do not re-cast inline.

**Version mismatch offers no "Open cited version" action.** EXPERIENCE.md:167 makes it conditional
(*"If authorized, offer…"*) and every fixture import produces exactly **one** governed
`scenario_version` per `scenario_id` (Story 1.5 Dev Notes) — there is no other version to open, so
the control would be an affordance that cannot work. The panel states the cited and the selected
version and offers **Return to claim**. Record the reduction in the `scheduling_inspect.py:36-60`
scope-as-data style (`NOT COVERED: …`).

### Decision 6 — "Evidence unavailable" is derived at render time and **never written back**

AC2's closing clause — *"historical claims with lost evidence remain visible but marked 'Evidence
unavailable'"* — has two sources:

1. Claims persisted with `verdict="failed"`. **Already shipped**: `ActivityTimeline.tsx:47-53`
   renders `Claim unavailable: <failure>`. Nothing to build; reuse the same treatment.
2. A claim persisted `supported` whose locator does not resolve at jump time. This is the new case.

The marking for (2) is **session-scoped client state**, keyed by the origin key. It is **not** a
write to `persisted_event`: that row is an immutable audit record, no `UPDATE` grant exists for it
(the only grant this milestone added is `agent_run(status)`, revision `c7d6e5f4a3b2`), and inventing
one here would be an Epic 4 audit decision taken by a rendering story.

State the reduction plainly in the story's Completion Notes: the mark survives the jump→return trip
that AC2 describes, and does not survive a reload. Do not describe it as durable.

---

## Acceptance Criteria

1. **Given** an Evidence link in Chat, **when** the planner activates it and then activates *Return
   to claim* or browser Back, **then** app-owned navigation records the originating conversation,
   message, and claim; opens the cited Scenario Data version/group; loads the exact target window;
   focuses one highlighted record; and on return restores the originating message and focused
   Evidence link, **and** returning does not resend, regenerate, or silently switch the scenario.
   *(UX-DR2, UX-DR18, UX-DR19, UX-DR34)*

2. **Given** a version mismatch, missing locator, unauthorized target, or stale cached record,
   **when** evidence navigation resolves the exception, **then** it uses the distinct required safe
   panel and recovery actions, never substitutes current/similar data, and never reveals an
   unauthorized record's existence or value, **and** historical claims with lost evidence remain
   visible but marked "Evidence unavailable." *(UX-DR20)*

3. **Given** an evidence jump and return, **when** focus behavior is tested, **then** focus moves to
   the exact evidence target on jump and returns to the invoking Evidence link on return, proven by
   the automated accessibility suite established in Epic 1, **and** the full locator is owned by the
   application and never entrusted to a model-generated URL. *(UX-DR27, UX-DR34, AR15)*

> **Scope note carried from correct-course 2026-08-09**
> (`sprint-change-proposal-2026-08-09-epics-2-5.md:132`): the original AC1+AC2 were merged into AC1
> and **the "ordinary user filters preserved separately for restoration" clause was dropped**. Do
> not build filter save/restore. The zoom/reduced-motion matrix was also dropped (the existing
> `e2e/reduced-motion.spec.ts` already reads `EVIDENCE_HIGHLIGHT_CLASS`). The
> model-generated-URL and non-disclosure invariants were **explicitly preserved** and are AC3 and
> AC2 above.

---

## One honest gap, raised rather than papered over

**AC1 says "opens the cited Scenario Data _or Results_ version/group". Results does not exist.**

Verified at creation:

- `frontend/src/routes/ScenarioResults.tsx` renders `WorkspaceTabPlaceholder` — *"Run results are
  not available yet."* The `Results` workspace tab is a non-interactive `<span aria-disabled>`
  (`WorkspaceTabs.tsx:27-45`).
- `EvidenceRefV1.producing_run_version` is **always `None`** (Story 1.5 and Story 2.7 both state and
  enforce this; no `schedule_run` / `schedule_version` table exists). **No locator this repository
  can produce names a Results target.**

**Required posture.** Build the Scenario Data destination only. Do **not** build a Results evidence
region, a run-scoped locator branch, or a placeholder route for one — that pre-empts Epic 3. Do
**also** not hard-code the string `"data"` as the only possible destination inside the locator
module in a way that forces a rewrite: the destination is derived from `EvidenceRefV1.group`, and
every current group maps to Scenario Data because every current group *is* a Scenario Data group
(`EvidenceGroupV1` and the `ScenarioDataView` tab slugs are the same six strings — verified
identical at creation). Record the reduction in the `NOT COVERED:` form.

Same posture Story 2.5 took for the audit/evidence declaration and Story 2.7 took for
`producing_run_version`. Declaration and correct shape; no speculative construction.

---

## Tasks / Subtasks

- [x] **Task 1** — App-owned locator and origin contract (AC: 1, 3)
- [x] **Task 2** — `EvidenceLink` becomes a real, identifiable navigation control (AC: 1, 3)
- [x] **Task 3** — Resolve-endpoint client, dispatcher, and hook (AC: 1, 2)
- [x] **Task 4** — The evidence target region (AC: 1, 3)
- [x] **Task 5** — Wire the jump (AC: 1)
- [x] **Task 6** — Return to claim and browser Back (AC: 1, 3)
- [x] **Task 7** — The four exception states (AC: 2)
- [ ] **Task 8** — Accessibility proof, fences, ledger, Gate A (AC: 3)

New feature home: **`frontend/src/features/evidence/`** (AR26's `frontend/src/features` structural
seed). It is deliberately *not* `features/scenario-data/`, whose whole directory is swept by
`src/test/scenarioDataBoundaries.test.ts` for mutation affordances and agent-API imports; Scenario
Data *composes* the evidence panel, it does not own it. It is also not `features/chat/`, because
Scenario Data must not import from the chat feature.

---

### Task 1 — App-owned locator and origin contract (AC: 1, 3)

- [x] Create `frontend/src/features/evidence/locator.ts`.
  - [x] `EvidenceTarget` derived from the **generated** schema, never hand-authored — follow
        `src/api/scenarioProjection.ts:5-17`'s `paths[…]` derivation convention. The `group` union
        must come from the generated `EvidenceRefV1`.
  - [x] `EVIDENCE_GROUP_TO_TAB: Record<EvidenceGroup, ScenarioDataListGroup>` with
        `satisfies` so `tsc --noEmit` fails if the backend ever adds a seventh group. This is the
        frontend half of Story 2.7's trap #2 (two ad-hoc group translations, *"the Evidence link
        names a group the planner cannot find in Scenario Data; nothing in the backend notices"*).
        **One mapping, exhaustive, compile-checked.**
  - [x] `toSearchParams(ref)` → `URLSearchParams` with `group`, `record`, `version`, and `field`
        only when present. `field` **must** use the key `field` — `useColumnVisibility` already
        reads `searchParams.get("field")` (`ScenarioDataView.tsx:38`) and reveals a hidden targeted
        column with the explanation *"… is shown because an evidence link targets it."* Reusing that
        param is free; inventing `?column=` silently disables a shipped mechanism.
  - [x] `readTarget(searchParams)` → `EvidenceTarget | null`. Validate `group` against the closed
        vocabulary and `version` as a UUID shape. **An unknown group returns `null` — never a
        guess, never a fallback to `overview`.**
- [x] Create `frontend/src/features/evidence/origin.ts`.
  - [x] `EvidenceOrigin = { conversationId, activityId, segmentIndex, refIndex }`.
  - [x] `originElementId(origin)` — one function, used by **both** the link's `id` and the return
        focus lookup, so the two cannot drift.
  - [x] `rememberOrigin(origin)` / `consumeOrigin()` over a single `sessionStorage` key, wrapped in
        `try/catch` (match `useColumnVisibility.ts:49-52`'s storage-unavailable posture: the feature
        degrades, it never throws). `consumeOrigin` removes the entry.
- [x] Tests: round-trip `toSearchParams`→`readTarget`; unknown group → `null`; malformed version →
      `null`; `consumeOrigin` returns once then `null`; storage-disabled path does not throw.

### Task 2 — `EvidenceLink` becomes a real, identifiable navigation control (AC: 1, 3)

- [x] `frontend/src/components/primitives/EvidenceLink.tsx`:
  - [x] Add an `id` prop (required for the return focus target).
  - [x] Make the activation props a discriminated union so **neither-prop is a type error**. This
        closes `deferred-work.md:78` (*"renders an inert focusable control … becomes relevant when
        Story 2.8 wires real usage"*) properly — by making the state unrepresentable, not by adding
        a runtime warning.
  - [x] Everything else stays byte-identical: the label format, the `min-h-11` target, the
        `text-evidence-link underline` treatment (UX-DR34 "conventionally link-identifiable"), the
        `focus-visible:ring-3` ring.
- [x] `ActivityTimeline.tsx`: replace `onActivate={() => undefined}` (line 83, the comment there
      already names this story) with the real handler from Task 5, and pass
      `id={originElementId(...)}`. The `key` stays as-is.
- [x] **Do not** change `fieldOrRange`, `claimSubject`, `formatClaimValue`, the empty-claim state, or
      the failed-claim state. Those are Story 2.7 review outcomes with tests behind them.

### Task 3 — Resolve-endpoint client, dispatcher, and hook (AC: 1, 2)

- [x] `src/api/scenarioProjection.ts`: six wrappers, one per group, matching the file's existing
      shape exactly — `client.GET(...)`, `if (error) throw { ...error, status: response.status }`,
      types derived from `paths[…]`. **GET-only**: `scenarioDataBoundaries.test.ts:47-53` asserts
      this file never calls `client.POST|PUT|PATCH|DELETE`.
- [x] `src/features/evidence/resolve.ts`: `RESOLVERS: Record<EvidenceGroup, Resolver>` — a **map,
      not a `switch`/`isinstance` chain**. Same posture as Story 2.6 Decision 4 (`_RENDERERS` was
      deleted for being a per-capability branch); a chain here reads as cleanup and reintroduces the
      shape, and exhaustiveness stops being compile-checked.
- [x] `src/hooks/useEvidenceRecord.ts`: thin TanStack Query wrapper (`useScenarioProjection.ts` is
      the model). `enabled: Boolean(target)`, `retry: false` (an exception state is a real answer,
      not a transient failure). **The query key must include `target.version`** — a cited version is
      part of the record's identity, and a key that omits it serves a different version's cached row
      as the answer to a version-pinned citation.

### Task 4 — The evidence target region (AC: 1, 3)

- [x] `src/features/evidence/EvidenceTargetPanel.tsx`.
  - [x] Renders `EvidenceHighlight` with a `ref`, its default `tabIndex={-1}`, and **exactly**
        `EVIDENCE_HIGHLIGHT_CLASS` — no `transition`, `animate`, or `pulse` utility classes
        (UX-DR32 prohibits pulsing/flashing evidence; UX-DR34 requires reduced-motion equivalence,
        and `e2e/reduced-motion.spec.ts` reads that exported constant).
  - [x] Accessible name states **group, record, field/range, and cited version** — the same four
        facts `EvidenceLink`'s label states (`EvidenceLink.tsx:22`) and what
        `EXPERIENCE.md:137` requires the target to announce.
  - [x] Renders the resolved record's fields read-only. Reuse `IdentifierCopyButton` for identifiers
        and `formatMinuteWindow` for windows — the group panels already do
        (`DemandPanel.tsx:40-47`); do not hand-format either.
  - [x] Renders **Return to claim** only when an origin exists. A pasted deep link with no origin
        shows the target and no return control — correct, and it must not render a dead button.
  - [x] **Focus moves exactly once, after the query settles** — not on mount. `EXPERIENCE.md:137`:
        *"receives programmatic focus with `tabindex=-1` **after its row/window loads**"*. Focusing
        an empty box first loses the announcement. `ScenarioWorkspace.tsx:26-30` is the in-repo
        precedent for a settled-state single focus effect, including why: *"previously both fired
        and a screen reader was interrupted mid-announcement."*
- [x] `ScenarioDataView.tsx` composes it above the `Tabs` region when `readTarget(searchParams)` is
      non-null, and forces the selected tab to `EVIDENCE_GROUP_TO_TAB[target.group]`.
- [x] Loading state: the panel's own skeleton, matching the region's expected shape (UX-DR25 /
      `EXPERIENCE.md:105` — *"No fake values"*). Do **not** render an empty highlight.
- [x] **Field-key correspondence guard.** `useColumnVisibility` silently ignores a `field` that is
      not a column key of the group — so an evidence link targeting an unknown field reveals
      nothing and nothing goes red. Two mechanical defences, both required:
  - [x] A test parsing every `expected_evidence_refs` entry in
        `backend/evals/golden/scheduling_compute/*.json` (format:
        `<version>|<group>|<record_id>|<field>:<start>-<end>`) and asserting each `<group>` is a
        real tab slug and each `<field>` is a column key of that group. Thin today (one case carries
        `demand|amount`) and it grows automatically as cases are added.
  - [x] The panel names the targeted field in its own output regardless of column visibility, so an
        unmatched field degrades to *visible and stated* rather than *silently ignored*.

  Verified at creation: the three `field` values any calculator can emit today —
  `qualifications` (workers), `amount` (demand), `task_id` (baseline-assignments), from
  `application/grounding/calculators.py:339,415,422` — are all real column keys of their mapped
  group. That is currently true **by coincidence**, and these guards are what make it true by
  construction.

### Task 5 — Wire the jump (AC: 1)

- [x] The handler in `ActivityTimeline` navigates to
      `/scenarios/${item.scenario_id}/data?${toSearchParams(ref)}` with
      `{ state: { evidenceOrigin } }`, and calls `rememberOrigin(origin)` first.
- [x] **The scenario id comes from `item.scenario_id`** (on `ActivityCommonOut`), not from a route
      param and not from anything the model produced. UX-DR2: *"never switch scenario implicitly
      from an evidence link."*
- [x] The origin captures the currently selected `?conversation=` value so the return trip lands on
      the same conversation — Chat's selection lives in the URL for exactly this reason
      (`ChatView.tsx:55-62`).
- [x] Test: a locator whose `scenario_version_id` differs from the workspace context does **not**
      change the workspace scenario or version — it renders the version-mismatch panel (Task 7).

### Task 6 — Return to claim and browser Back (AC: 1, 3)

- [x] *Return to claim* navigates to `/scenarios/${scenarioId}?conversation=${conversationId}`.
- [x] Chat restores focus to `originElementId(origin)` once, from `consumeOrigin()`, after the
      timeline has data. **The same code path serves both** *Return to claim* and browser Back —
      that is why the origin is mirrored in `sessionStorage` (Decision 3). One restoration path, two
      entry points; do not write two.
- [x] Required assertions:
  - [x] `sendMessage`, `executeTurn`, and `createConversation` are **never called** on the return
        trip. AC1's *"does not resend, regenerate"*. Spy the module, assert zero calls.
  - [x] The `?conversation=` value is byte-identical before the jump and after the return.
  - [x] The scenario id in the path is unchanged.
  - [x] Focus lands on the exact invoking `EvidenceLink`, not on the message, the timeline, or the
        first link in the list.
  - [x] A second Back does **not** re-steal focus (`consumeOrigin` is read-once).

### Task 7 — The four exception states (AC: 2)

- [x] Add `getErrorCode(error): string | undefined` to `src/lib/errors.ts`, beside `getErrorStatus`
      and with the same rationale in its docstring (one typed accessor, no repeated casts).
- [x] Four states, per Decision 5's table:
  - [x] **Version mismatch** — names the cited version and the selected version. Actions: *Return to
        claim*. No *Open cited version* (Decision 5). Does not switch the workspace.
  - [x] **Missing evidence** — confirms the locator could not resolve **in the exact cited
        version**, shows the safe locator fields, offers **Retry** and *Return to claim*, and marks
        the originating claim "Evidence unavailable" (Decision 6).
  - [x] **Unauthorized** — copy is exactly *"Evidence is not available to this session."* It states
        no value and makes **no claim about whether the record exists**. Action: *Return to claim*.
  - [x] **Stale cached record** — labelled *"Stale — last verified at {timestamp}"* with a refresh
        action. Reuse the existing pattern and copy from `ScenarioWorkspace.tsx:118-137`
        (`role="status"` on the message only, control outside it); do not invent second wording for
        a state EXPERIENCE.md already fixed.
- [x] Use `InlineAlert` — the shared primitive with the persistent-within-surface contract. Do not
      hand-roll a panel.
- [x] Required assertions:
  - [x] Each of the four states is **distinct** in rendered output (UX-DR20).
  - [x] On every exception, the resolver is called **exactly once, with the cited locator** — no
        retry against a different record, a different version, or the current version. AR11's
        no-retarget rule, and Story 2.7's trap #4 (*"Picking the nearest row … reads as helpful, is
        the exact thing AR11 forbids, and is invisible unless asserted"*).
  - [x] No exception state renders any record inside `EvidenceHighlight`.
  - [x] The unauthorized panel's rendered text is **byte-identical** whether the underlying record
        exists or not — drive both and compare.
  - [x] The originating claim remains **visible** in the timeline when marked "Evidence unavailable"
        (AC2's own word), and no request mutates the persisted activity.

### Task 8 — Accessibility proof, fences, ledger, Gate A (AC: 3)

- [ ] **jsdom / axe proof** — extend `src/test/accessibility-contract.test.tsx` or add a sibling in
      the same directory (Epic 1's established suite):
  - [ ] Focus moves to the evidence target on jump, and only after the record resolves.
  - [ ] Focus returns to the invoking Evidence link on return.
  - [ ] The target's accessible name contains group, record, field/range, and version.
  - [ ] Exactly one `EVIDENCE_HIGHLIGHT_CLASS` element exists.
  - [ ] axe clean on the target state and on all four exception states.
- [ ] **Playwright browser proof** — jsdom cannot verify a real focus ring, which is why Epic 1's
      `e2e/keyboard-journey.spec.ts` exists and uses `expectKeyboardFocus`. Add a keyboard-only
      jump-and-return journey:
  - [ ] Extend `e2e/support/apiStubs.ts` with **GET-only** stubs: the conversation list, the
        conversation timeline (containing one `agent_response` with one supported claim and one
        `EvidenceRefV1`), and the six resolve paths. The stub's non-GET 405 guard
        (`apiStubs.ts:105`) is deliberate — **do not relax it.** Enter the journey by deep-linking
        `/scenarios/:id?conversation=<id>`; nothing in the journey needs to create anything.
  - [ ] The SSE endpoint has no stub, so the stream degrades to the labelled-polling banner. That is
        acceptable and the journey must not depend on the stream either way.
  - [ ] Tab to the Evidence link → `expectKeyboardFocus` → Enter → target focused with a real ring →
        Tab to *Return to claim* → Enter → the Evidence link is focused again.
- [ ] **Model-generated-URL guard** (AC3, AR15): a source-level test asserting no navigation target,
      `href`, or DOM attribute under `features/chat/` or `features/evidence/` derives from prose
      segment text or any other free-text model output. Read the modules' own source — Story 2.7's
      second review found a guard that *"watched a helper and left the tautology re-addable"*, so
      point it at the files that actually navigate.
- [ ] **Zero-line-diff fences** — verify each with `git diff --stat` and record the result:
  - [ ] **All of `backend/`.** This story has no backend change (Decision 1 + Decision 4). If you
        find yourself editing a Python file, stop and re-read those two decisions.
  - [ ] `frontend/openapi.json` and `frontend/src/api/schema.d.ts` — no contract moved, so **no
        codegen run**. A regenerated-but-identical file still shows a diff if formatting drifts.
  - [ ] `frontend/src/features/scenario-data/groups/**` — the six panels are untouched.
  - [ ] `frontend/src/features/chat/{ChatView,Composer,ConversationList}.tsx` — only
        `ActivityTimeline.tsx` changes in that directory, plus whatever Task 6's focus restoration
        genuinely requires in `ChatView.tsx`. If `ChatView.tsx` must change, keep it to the
        restoration effect.
- [ ] **Ledger** (`_bmad-output/implementation-artifacts/deferred-work.md`) — three Story 1.6 review
      items name this story by name. Judge each honestly; annotate in place rather than deleting,
      following the Story 2.4/2.5 precedent for a false premise:
  - [ ] `:78` (inert `EvidenceLink` with neither prop) — **closed** by Task 2's discriminated union.
  - [ ] `:76` (no contrast test for `EvidenceLink` on `evidence-surface`) — its trigger is *"once
        Story 2.8 actually composes `EvidenceLink` inside `EvidenceHighlight`"*. Under Decision 2
        the highlight contains the record and a *Return to claim* button, **not** an `EvidenceLink`.
        If that holds in your implementation, re-annotate with the corrected premise and restate the
        owner. If you do compose one inside, add the contrast test and close it.
  - [ ] `:81` (no truncation handling for long locator labels — *"Story 2.8's dense grid is where
        this becomes visible"*) — under Decision 2 the link lives in Chat's reading column and the
        target is a record region, so the dense-grid premise is false. Re-annotate and restate;
        do **not** close it silently and do **not** add truncation nothing asks for.
- [ ] **Regression + Gate A**:
  - [ ] Re-derive every baseline on a clean tree — do **not** trust the numbers in Dev Notes.
  - [ ] `alembic check` from the **repository root** (`deferred-work.md:132-143`) — expect zero
        operations and zero migration files.
  - [ ] Gate A re-run per AR28. Expect the two-commit dance: the readiness gate cannot run twice in
        a row because it dirties `evidence/` (`deferred-work.md:107`). See `docs/GATE-A-RUNBOOK.md`.
  - [ ] **No evidence file is owed.** No AC here carries a measured threshold, and NFR35's four rows
        belong to Stories 1.4, 1.5, 2.4 and 3.5 — 1.5's row already measured *evidence-target
        resolution* against these very endpoints. Do **not** regenerate
        `evidence/story-2.2/evaluation-harness-demonstration.json`.
  - [ ] **No new golden cases.** NFR28's floor is per *capability*; this story adds no capability and
        no evaluator. `epics.md:1527` — never pad the dataset.

---

## Dev Notes

### What this story is, and what it is not

| In scope | Out of scope | Owner |
|---|---|---|
| Evidence jump/return, origin keys, focus restoration, exception panels | The grounding gate, calculators, `EvidenceRefV1` emission | **Shipped** (2.7) |
| Scenario Data as the evidence destination | A Results evidence region, run-scoped locators | Epic 3 |
| Client-side "Evidence unavailable" marking | Persisting it; any `persisted_event` write | Epic 4 (AD-12) |
| Consuming the six resolve endpoints | Any backend change, migration, or contract move | — (none owed) |
| Version-mismatch / missing / unauthorized / stale panels | Clarification, refusal, injection, the failure taxonomy | Story 2.9 |
| Focus and highlight proof | Filter save/restore; a zoom/reduced-motion matrix | **Cut** 2026-08-09 |

**No backend change. No migration. No new dependency. No new route. No codegen.** If you reach for
a package, a Python file, or `npm run codegen`, stop — the mechanism you want almost certainly
already exists and is named in these notes.

### Deliberately not built — four things that will look like omissions

- **A jump path from a failed claim.** A claim with `verdict="failed"` carries **no**
  `evidence_refs` — that is AR11's non-retargeting rule, asserted by `GroundingEvaluator` on every
  failure branch — so no `EvidenceLink` renders beside it and there is nothing to activate.
  `ActivityTimeline.tsx:47-53` already renders those claims. Do not synthesise a locator for them.
- **A jump path from a proven-empty claim.** Same reason: `data-claim-state="empty"` exists
  precisely because `EvidenceRefV1` addresses records and absence has none
  (`ActivityTimeline.tsx:55-65`).
- **Filter save/restore around a jump.** Cut by correct-course 2026-08-09. The grid keeps whatever
  filters it had; nothing is stashed and nothing is reapplied.
- **A "back to top of conversation" or scroll-offset store.** AC1 asks for the originating *message
  and focused Evidence link*. Focusing the link scrolls it into view natively. Do not build a
  scroll-position cache.

### The traps, ranked by how quietly they fail

1. **Silently ignoring a `field` that is not a column key.** `useColumnVisibility.ts:37-38` looks the
   field up and, on a miss, `revealedColumn` is `undefined` and *nothing happens* — no error, no
   log, no red test. The Evidence link promised to reveal a field and the planner sees an ordinary
   grid. Task 4's two guards exist for this; it is the trap most likely to survive to review.
2. **Retargeting on a miss.** Refetching the current version, or the "nearest" record, when the
   cited one fails to resolve. Reads as helpful, is exactly what AR11 forbids, invisible unless
   asserted. Story 2.7 ranked this fourth; here it is second, because this story is the first that
   can actually do it.
3. **Building a "locate the record's page" path** (Decision 1). Reads like the obvious
   implementation of *"loads the exact target window"*, needs an endpoint that does not exist, and
   inherits the unpinned-cursor drift hazard on the one surface whose purpose is exactness.
4. **Putting the origin in the URL** because it is simpler than history state. Fails AC3's own
   invariant structurally, and no functional test notices — the jump and the return both still work.
5. **Focusing the target before the record resolves.** The announcement is lost and the planner
   hears an empty region. `ScenarioWorkspace.tsx:26-30` documents this exact regression from a
   previous story.
6. **Adding a `claim_id` to `GroundedResponseV1`** because positional identity feels fragile
   (Decision 4). Breaks deserialization of every already-persisted `agent_response` row with no
   compat alias — `deferred-work.md:194` records this failure mode in detail from Story 2.7's own
   `MetricV1` rename.
7. **Collapsing `evidence_not_found` into the unauthorized response** in the name of
   non-disclosure (Decision 5). Destroys the distinction UX-DR20 requires for an authorized planner
   and protects nothing, because an unauthorized prober never reaches that branch.
8. **Two highlights.** Highlighting the row *and* the record region when the record happens to be on
   the current page. UX-DR18 says exactly one target.
9. **A `switch` over the six groups** in the resolver dispatch. Reads as clean, loses compile-time
   exhaustiveness, and is the shape Story 2.6 Decision 4 deleted.
10. **Writing "Evidence unavailable" back to `persisted_event`** (Decision 6). No grant exists, the
    row is an audit record, and the migration would be an Epic 4 decision taken by a rendering
    story.
11. **Relaxing the Playwright stub's 405 guard** to make the journey easier to set up. The guard is
    the deterministic read-only property of the whole e2e harness.

### Existing conventions to match, not reinvent

- **Query hooks** — `src/hooks/useScenarioProjection.ts`: thin TanStack Query wrappers, no business
  logic, query key as a cross-module contract.
- **API wrappers** — `src/api/scenarioProjection.ts`: types derived from `paths[…]`, `client.GET`,
  `throw { ...error, status: response.status }`. Never hand-author a response interface.
- **Typed error accessors** — `src/lib/errors.ts`: one exported function per concern, docstring
  explaining why the cast is centralized. `getErrorCode` joins `getErrorStatus`.
- **Settled-state single focus effect** — `ScenarioWorkspace.tsx:22-30`, including its comment about
  interrupting a screen reader.
- **Stale labelling** — `ScenarioWorkspace.tsx:118-137`. Message in `role="status"`, control outside.
- **Storage access** — `useColumnVisibility.ts:10-25,49-52`: `try/catch`, malformed entries fall
  through to a safe default, never a truthy-but-wrong value.
- **URL as state** — `useGroupControls.ts`: read through `useSearchParams`, validate against a known
  vocabulary, ignore anything unrecognized.
- **Comment style** — explain *why the shape is this shape*, cite the UX-DR/AR number. See
  `ActivityTimeline.tsx:9-12,23-24,55-58`.
- **Test doubles** — `vi.mock` the hook module, drive real components. `accessibility-contract.test.tsx`
  and `panelTestContract.tsx` are the models. A skipped test is not a passed test (Story 1.11).

### Latest technical information (verified against the repo at creation, commit `6e19ef3`)

- **All six resolve endpoints exist and have zero frontend consumers.** Paths:
  `/api/v1/scenarios/{scenario_id}/projection/{group}/{record_id}?scenario_version_id=…` for
  `work-areas-and-tasks`, `workers`, `demand`, `baseline-assignments`, `locks`,
  `constraints-and-objectives` (`api/routers/scenario_projection.py:504-609`). Generated types are
  already current in `frontend/src/api/schema.d.ts` — Story 1.5 ran codegen for this story
  specifically.
- **`EvidenceGroupV1`'s six values are byte-identical to `ScenarioDataView`'s six list-group tab
  slugs and to the resolve URL segments.** Confirmed by direct comparison of
  `application/contracts/evidence_ref.py:19-26`, `ScenarioDataView.tsx:19-27`, and the router paths.
  The mapping in Task 1 is therefore an identity map today — write it anyway, `satisfies`-checked, so
  a divergence fails the build instead of failing silently.
- **`EvidenceHighlight` and the four evidence design tokens ship and are unused in product code.**
  `EVIDENCE_HIGHLIGHT_CLASS` is exported precisely so `e2e/reduced-motion.spec.ts` can read the real
  class list; the only current renders are in `components/primitives/fixtures.tsx:164-175`.
- **Every record contract carries `record_id`** (`TaskV1`, `WorkerV1`, `DemandIntervalV1`,
  `AssignmentV1`, `LockV1`, `ConstraintV1`) — but `workers` and `work-areas-and-tasks` do **not**
  render it as a column. See Decision 2 reason 2.
- **`ActivityCommonOut` carries `activity_id`, `conversation_id`, `scenario_id`,
  `scenario_version_id`** on both variants (`api/schemas.py:122-151`) — the origin key needs nothing
  new on the wire.
- **`GroundedClaimV1` has `result_id` but no claim id**, and `result_id` is deliberately
  content-addressed and non-unique per claim. See Decision 4.
- **Bare `HTTPException(404)` becomes `code: "resource_not_found"`**; the two evidence-specific
  outcomes carry `evidence_not_found` / `evidence_version_mismatch`
  (`api/main.py:67-90`, `api/problems.py`, `scenario_projection.py:475-501`).
- **jsdom does not implement `EventSource`** (`useConversationStream.ts:15-17`) — the stream hook
  takes an injectable constructor. Nothing in this story needs the stream; do not acquire a
  polyfill.
- **Node/TS**: TypeScript 5.9.3 strict with `noUnusedLocals`/`noUnusedParameters`; react-router 8.2;
  TanStack Query 5.101. `navigate(to, { state })` history state survives Back/Forward — the reason
  `sessionStorage` is still needed is the *Chat* entry's own state, not a react-router limitation.

### Project Structure Notes

- `frontend/src/features/evidence/` — **new**. `locator.ts`, `origin.ts`, `resolve.ts`,
  `EvidenceTargetPanel.tsx`, plus co-located `*.test.tsx`. AR26 structural seed.
- `frontend/src/hooks/useEvidenceRecord.ts` — **new**, beside `useScenarioProjection.ts`.
- `frontend/src/api/scenarioProjection.ts` — extended with six GET wrappers.
- `frontend/src/lib/errors.ts` — extended with `getErrorCode`.
- `frontend/src/components/primitives/EvidenceLink.tsx` — `id` prop + discriminated activation props.
- `frontend/src/features/chat/ActivityTimeline.tsx` — real `onActivate` + link `id`.
- `frontend/src/features/scenario-data/ScenarioDataView.tsx` — composes the panel, forces the tab.
- `frontend/src/test/accessibility-contract.test.tsx` (or a sibling) — the AC3 jsdom proof.
- `frontend/e2e/` — the keyboard journey and its GET-only stubs.
- Chat code stays in `features/chat/`; it must **never** be imported by `features/scenario-data/`
  (`scenarioDataBoundaries.test.ts` sweeps that directory).

### References

- `_bmad-output/planning-artifacts/epics.md:792-813` — Story 2.8 ACs; `:769-790` (2.7, shipped) and
  `:815-841` (2.9, the fence ahead)
- `epics.md:157` (AR11), `:161` (AR15), `:172` (AR26), `:174` (AR28), `:180` (UX-DR2), `:212`
  (UX-DR18), `:214` (UX-DR19), `:216` (UX-DR20), `:224` (UX-DR24), `:230` (UX-DR27), `:240`
  (UX-DR32), `:244` (UX-DR34), `:1527` (never pad the dataset)
- `sprint-change-proposal-2026-08-09-epics-2-5.md:132` — the simplification this story is scoped to
- `ux-designs/…/EXPERIENCE.md:86` (Evidence link), `:97` (Evidence highlight), `:98` (Return to
  claim), `:99` (Evidence exception panel), `:109-117` (Large-table contract, incl. `:112` exact
  target loading and `:114` field reveal), `:124` (Scenario Data state patterns), `:137` (focus
  contract), `:140` (Back/Forward), `:146-173` (Evidence Navigation and the exception table),
  `:188-196` (Accessibility Floor), `:251-260` (Flow 3 — this story's flow, end to end)
- `prds/prd-ShiftMind-2026-07-21/prd.md:133-134` (FR-7), `requirements-inventory.md:33` (NFR12)
- `1-5-resolve-exact-evidence-targets.md:17,20,87,116` — the resolver this story consumes, and its
  explicit statement that the UI is this story's boundary
- `1-6-establish-shiftmind-design-tokens-and-shared-primitives.md` — `EvidenceHighlight`,
  `EvidenceLink`, the evidence tokens
- `2-7-…md:1039` — the out-of-scope row handing jump/return, origin keys, focus restoration and
  exception panels to this story; `:1054-1095` — the trap list this one extends
- `deferred-work.md:59` (unpinned pagination cursor), `:76`, `:78`, `:81` (the three Story 1.6 items
  naming this story), `:107` (the double-run Gate A trap), `:132-143` (`alembic check` working
  directory), `:194` (breaking a persisted contract `Literal`)
- `docs/EVIDENCE-CONVENTION.md`, `docs/GATE-A-RUNBOOK.md`
- Code: `backend/api/routers/scenario_projection.py:475-609`,
  `backend/application/contracts/{evidence_ref,grounding,scenario_projection}.py`,
  `backend/application/grounding/{calculators,evidence_groups}.py`, `backend/api/schemas.py:122-180`,
  `backend/evals/golden/scheduling_compute/*.json`,
  `frontend/src/features/chat/{ActivityTimeline,ChatView}.tsx`,
  `frontend/src/features/scenario-data/{ScenarioDataView,useGroupControls,useColumnVisibility,columns,filters}.ts{,x}`,
  `frontend/src/components/primitives/{EvidenceLink,EvidenceHighlight,InlineAlert,IdentifierCopyButton}.tsx`,
  `frontend/src/routes/{ScenarioWorkspace,ScenarioData}.tsx`, `frontend/src/lib/errors.ts`,
  `frontend/src/test/{accessibility-contract,scenarioDataBoundaries}.test.*`,
  `frontend/e2e/{keyboard-journey,reduced-motion}.spec.ts`, `frontend/e2e/support/apiStubs.ts`

### Baselines at creation (`6e19ef3`) — re-derive them, do not trust them

Recorded by Story 2.7's completion notes: backend **810 passed / 2 skipped / 7 deselected**;
PostgreSQL **45**; frontend **56 files / 332 tests**; Playwright **46**; `alembic` zero diff;
`gate_a_passed: true`, `blocking: []`. Story 2.7 itself found its inherited baseline stale by 100+
tests; assume the same and measure on a clean tree before you start.

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Implementation Plan

- Implement each numbered task in story order using focused Vitest failures first, minimal production code second, and full frontend regression/type checks before marking the task complete.
- Keep the evidence destination derived from generated contracts, retain the exact cited locator in query identity, and use one read-once origin path for explicit return and browser Back.

### Completion Notes List

- Task 1: Added generated-schema-derived evidence locator parsing/serialization, an exhaustive group-to-tab map, and guarded read-once session origin storage. Added 5 focused tests; full frontend regression is green (58 files / 337 tests) and TypeScript passes.
- Task 2: Made EvidenceLink activation states compile-time complete, added stable DOM IDs, and replaced the inert timeline seam with app-owned origin construction and navigation. Preserved all Story 2.7 claim formatting/states; 11 focused tests and the full 337-test frontend regression pass.
- Task 3: Added six generated-contract GET resolvers, an exhaustive map dispatcher, and a no-retry TanStack Query hook whose identity includes the cited version. Added 9 tests; full frontend regression is green (60 files / 346 tests) and TypeScript passes.
- Task 4: Added the single post-resolution focused EvidenceHighlight region, read-only identifier/window formatting, origin-aware return control, loading skeleton, forced cited tab, and golden-dataset field-key guard. Full frontend regression is green (61 files / 350 tests).
- Task 5: Wired jump activation exclusively from persisted activity/ref data, preserved scenario and selected workspace version, and proved a mismatched citation renders the mismatch panel without retargeting. Full frontend regression is green (61 files / 352 tests).
- Task 6: Added one read-once post-timeline focus restoration path shared by explicit return and browser Back. Proved exact scenario/conversation restoration, exact-link focus, no second focus steal, and zero create/send/execute calls; full frontend regression is green (61 files / 354 tests).
- Task 7: Added four RFC-7807-code-driven InlineAlert states, exact no-retarget assertions, and a non-persisted lost-evidence marker. The marker survives the SPA jump→return trip and intentionally does not survive reload; no persisted activity is mutated. Full frontend regression is green (61 files / 363 tests), TypeScript and lint pass (three pre-existing Fast Refresh warnings remain).

### File List

- frontend/src/features/evidence/locator.test.ts
- frontend/src/features/evidence/locator.ts
- frontend/src/features/evidence/origin.test.ts
- frontend/src/features/evidence/origin.ts
- frontend/src/components/primitives/EvidenceLink.test.tsx
- frontend/src/components/primitives/EvidenceLink.tsx
- frontend/src/components/primitives/fixtures.tsx
- frontend/src/features/chat/ActivityTimeline.test.tsx
- frontend/src/features/chat/ActivityTimeline.tsx
- frontend/src/features/chat/ChatView.tsx
- frontend/src/api/scenarioProjection.test.ts
- frontend/src/api/scenarioProjection.ts
- frontend/src/features/evidence/resolve.test.ts
- frontend/src/features/evidence/resolve.ts
- frontend/src/hooks/useEvidenceRecord.test.tsx
- frontend/src/hooks/useEvidenceRecord.ts
- frontend/src/features/evidence/EvidenceTargetPanel.test.tsx
- frontend/src/features/evidence/EvidenceTargetPanel.tsx
- frontend/src/features/scenario-data/ScenarioDataView.test.tsx
- frontend/src/features/scenario-data/ScenarioDataView.tsx
- frontend/src/lib/errors.ts
- frontend/src/routes/ScenarioData.tsx
- frontend/src/routes/ScenarioWorkspace.tsx
- frontend/src/components/primitives/InlineAlert.tsx
- frontend/src/features/evidence/availability.ts
- frontend/src/lib/errors.test.ts

## Change Log

| Date | Change |
|---|---|
| 2026-08-15 | Story created. Six creation decisions recorded; one honest gap raised (AC1's Results half is unreachable — `producing_run_version` is always `None` and Results is a placeholder route); zero-line `backend/` diff established as a fence rather than an expectation; three `deferred-work.md` items that name this story routed for honest judgement. |
