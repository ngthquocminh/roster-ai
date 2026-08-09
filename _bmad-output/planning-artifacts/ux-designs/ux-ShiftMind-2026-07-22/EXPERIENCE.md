---
name: ShiftMind
status: final
sources:
  - ../../prds/prd-ShiftMind-2026-07-21/prd.md
  - ../../prds/prd-ShiftMind-2026-07-21/addendum.md
updated: 2026-07-23
---

# ShiftMind — Experience Spine

## Foundation

Responsive desktop web built on the existing React/Vite application with shadcn/ui, Tailwind, Radix, React Router, and TanStack Query. `DESIGN.md` owns visual identity; this spine owns information architecture, behavior, states, interactions, accessibility, and journeys. The UI system is inherited unless a ShiftMind-specific delta is named.

These two spines win on conflict with any future mock, wireframe, or import.

Experience posture: evidence before confidence; analysis, draft, deterministic computation, comparison, approval, and baseline promotion are visibly separate. Scenario Data is inspect-only. The model interprets and orchestrates but never appears to construct or authorize a schedule.

### Assumptions carried from `.memlog.md`

- **[ASSUMPTION — memlog]** Maya is the fictional planner named by the PRD, not a research-validated persona.
- **[ASSUMPTION — memlog]** Desktop/laptop is primary; tablet uses stacked panels and contained table scrolling; phone is for read-only triage, not the full planning workflow.
- **[ASSUMPTION — memlog]** The current indigo accent, neutral shadcn palette, and inherited dark theme remain; dark mode is not an MVP requirement.
- **[ASSUMPTION — memlog]** Dataset scale requires bounded virtualization or pagination. Exact thresholds remain implementation-tunable, but deterministic sorting, filtering, focus, row position, and evidence targeting are not tunable.
- **[ASSUMPTION — memlog]** No offline write queue, notification system, new brand promise, regulated claim, or scenario-data mutation is introduced.

## Information Architecture

### Route and surface map

| Surface | Canonical location | Reached from | Purpose |
|---|---|---|---|
| Fixture catalogue | `/` | Sign-in/app open | Choose one predefined scenario fixture; no create, upload, import, or edit path. |
| Chat | `/scenarios/:scenarioId` with app-owned conversation selection | Fixture row, Workspace tabs | Revisit/create a durable conversation; investigate, clarify, draft, run, compare, and request approval. |
| Scenario Data | `/scenarios/:scenarioId/data` | Workspace tabs, Evidence link | Inspect the exact normalized fixture facts and stable identifiers available to agent investigation. |
| Runs | `/scenarios/:scenarioId/runs` | Workspace tabs, Chat run card | Inspect durable run state, start the existing manual deterministic solver workflow, cancel when permitted, or reopen a result. |
| Results | `/scenarios/:scenarioId/runs/:runId` | Runs row, Chat result card, Workspace Results tab when a run is selected | Inspect feasibility, deltas, schedule, immutable evidence, and decision provenance for one run. |

The scenario workspace has four peer views in this order: **Chat, Scenario Data, Runs, Results**. A persistent **Scenario/version context** names scenario, stable scenario ID, immutable fixture version, and operational-baseline version across all four. Changing scenario returns through the Fixture catalogue; it never happens implicitly from a claim link.

The Results tab points to the currently selected run. With no selected run it is disabled with the accessible explanation “Results unavailable: select a run,” while Results remains directly deep-linkable. Chat opens the last durable conversation for that scenario; a conversation selector exposes prior conversations and a clearly labelled New conversation action.

### Scenario Data groups

The group order is fixed so direct inspection and agent evidence use the same vocabulary:

1. **Overview** — fixture name, scenario ID, immutable fixture version, baseline schedule version, time horizon, counts, and last verified timestamp.
2. **Work areas and tasks** — stable work-area/task identifiers and normalized attributes.
3. **Workers** — stable worker identifiers, qualifications, and availability.
4. **Demand** — work area/task, interval, required capacity, and normalized units.
5. **Baseline assignments** — worker, shift/time interval, task/role, assignment and schedule-version identifiers.
6. **Locks** — locked assignment or rule target, scope, source, and stable identifier.
7. **Constraints and objectives** — active hard/soft type, parameters, priority/weight where applicable, and stable identifier.

No group exposes upload, create, edit, delete, import, row selection for bulk action, editable cells, or mutation-looking overflow menus. Copying an identifier, filtering, sorting, changing visible columns, and opening evidence are inspection actions.

## Voice and Tone

Microcopy is operational, bounded, and explicit about state. Brand posture lives in `DESIGN.md`.

| Do | Don't |
|---|---|
| “Draft — no baseline change.” | “I’ve updated the schedule.” |
| “Run `R-1842` is queued.” | “I’m fixing it now.” |
| “Agent unavailable. Scenario Data, saved results, and manual optimization are still available.” | “ShiftMind is offline.” |
| “This claim cites fixture `v7`, Demand `DEM-204`, 13:00–17:00.” | “Based on our data…” |
| “Approval is stale because baseline `b12` changed to `b13`.” | “Something changed. Try again.” |
| “No demand intervals match these filters.” | “No data.” |
| “Evidence is not available to this session.” | Reveal whether an unauthorized record exists. |
| Use literal outcomes: completed, infeasible, timed out, cancelled, failed, rejected, expired. | Collapse distinct outcomes into “Done” or “Error.” |

Avoid confidence scores, anthropomorphic waiting copy, hidden reasoning, celebration, urgency, and unsupported benefit claims. A refusal names the unsupported action and a safe next step when one exists.

## Component Patterns

Visual specifications live in `DESIGN.md` Components.

| Component | Use | Behavioral contract |
|---|---|---|
| Workspace tabs | Scenario workspace | Preserve selected scenario and version across Chat, Scenario Data, Runs, and Results. Results requires a selected run. Each tab has a real route; browser Back/Forward works. |
| Scenario/version context | All scenario views | Always shows scenario name/ID and immutable fixture version; shows baseline version where relevant. A mismatch is labelled before any recovery action. |
| Conversation timeline | Chat | Reconstructs persisted messages, structured cards, tool summaries, and terminal outcomes in durable order. Reconnect appends/replays by persisted event identity; it never duplicates a visible event. |
| Chat composer | Chat | Multiline input. Sending text creates a planner message only; it never implies run authorization or baseline approval. Disabled during model outage with fallback routes left active. |
| Message block | Chat | Distinguishes planner message, grounded agent response, clarification, and refusal by author/type label. Numerical or schedule-specific claims render adjacent Evidence links. |
| Evidence link | Agent claim, result metric, provenance event | Carries scenario ID, exact fixture/schedule/run version, evidence group, record ID, and optional field/time range. Opens the exact target without discarding claim position. |
| Draft card | Chat | Shows resolved entities, proposed constraints/objectives, preserved locks, expected versions, and consequence summary. Parameters may be revised or rejected; no baseline changes. Run optimization is a separate explicit control. |
| Run progress card | Chat, Runs, Results | Shows run ID and persisted state: queued, running, approval-required, completed, infeasible, timed-out, cancelled, or failed. No invented percentage/ETA. Recovery uses the same run ID. |
| Comparison summary | Chat, Results | Names candidate and baseline versions, then affected worker/shift/task, interval coverage, overtime, cost/objective components, constraint status, and unresolved infeasibility. Missing metrics say “Not computed.” |
| Approval request | Chat, Results | Binds exact candidate, current baseline, material parameters, consequence summary, and versions. Approve as baseline requires a separate explicit action; rejection/expiry/stale never resubmits. |
| Terminal outcome | Chat, Runs, Results | Presents literal final state and next valid actions. A non-promotable result never exposes an enabled Approve as baseline control. |
| Scenario group navigation | Scenario Data | Changes only the visible normalized group; selection is reflected in the URL. On tablet it may collapse to a Select without changing group names/order. |
| Scenario Data grid | Scenario Data, evidence targets | Native semantic table with caption and column headers. Read-only. Stable server-defined tie-break order; visible sort/filter state; bounded viewport; contained horizontal scroll. |
| Filter bar | Scenario Data | Field-aware search/filter; Apply and Clear are explicit. Shows active filter count and total/matching rows. Filters serialize to the URL without mutating data. |
| Column chooser | Scenario Data | Shows/hides non-required columns for this session. Stable ID, evidence target field, and key context columns cannot all be hidden. |
| Identifier copy control | Scenario Data, Runs, Results, provenance | Copies the full stable identifier and announces “Copied {identifier type}.” It does not select a row or imply editability. |
| Evidence highlight | Scenario Data, Results | Programmatic target for an Evidence link. Focuses and highlights exactly one row/cell/record after data resolves; persists until navigation, filter change, or dismissal. |
| Return to claim | Evidence target | Restores the originating Chat message/claim or Results element, scroll position, and keyboard focus. Uses an app-owned origin key, never an arbitrary redirect URL. |
| Evidence exception panel | Scenario Data, Results | Distinct titles/paths for version mismatch, missing evidence, and unauthorized evidence. Never silently substitutes another version or record. |
| Runs table | Runs | Stable newest-first list unless the user chooses another explicit sort. Row activation opens Results; retry/cancel controls are separately labelled and idempotent. |
| Results evidence panel | Results | Keeps deterministic result, warnings, schedule, comparison, and evidence accessible independent of model availability. Optional model-generated summary failure is isolated to that summary. |
| Provenance timeline | Results | Ordered request, evidence consulted, concise decision summary, proposals/results, policy outcomes, solver run, approval, execution, and before/after versions. Does not expose hidden chain-of-thought. |
| Status badge | All views | Always includes literal status text and accessible name; color/icon are secondary. |
| Inline alert | All views | Persistent within the affected surface. Gives one concise cause and recovery action when safe. Does not erase valid saved content. |
| Skeleton | Cold-loading surfaces | Matches expected headings/cards/table regions. No fake values. Replaced atomically by loaded, empty, or error state. |
| Empty state | Fixture catalogue, Chat, Scenario Data group, Runs, Results | Explains what is absent and offers at most one valid route/action. A legitimate zero-row group is not an error. |
| Reconnect banner | Chat, Runs | Shows Disconnected → Reconnecting → Reconnected; durable data remains visible. Reconnected announcement is brief and event replay deduplicates by ID. |

### Large-table contract

- Never use unbounded infinite scroll. The implementation may choose bounded virtualization or pagination by measured fixture scale **[ASSUMPTION — memlog]**, but the visible contract is stable: total and matching row counts, current position/range, deterministic order with stable-ID tie-break, and an explicit route to the first/previous/next/last segment where pagination is used.
- Sorting is explicit from header controls; multi-column sort order is announced. Filtering never changes the underlying fixture and can always be cleared. Deep links retrieve the target page/window before focus; they never report “missing” merely because the row was not currently rendered.
- Sticky headers remain visible during vertical scroll. A primary identifier column may be sticky where useful. Header/column overlap uses opaque surfaces and boundaries.
- Column visibility is a viewing preference, not data configuration. If a link targets a hidden field, that field becomes temporarily visible and the chooser states why.
- Empty filtered result keeps headers/filter context and says “No records in this group match these filters.” An intrinsically empty group says “This fixture has no records in this group.”
- Export is not implied. Copying individual identifiers/values may be available; bulk download is out of this UX contract unless separately authorized by product scope.

## State Patterns

| Surface | Cold/loading | Empty | Error/unavailable | Stale/reconnect |
|---|---|---|---|---|
| Fixture catalogue | Skeleton rows plus “Loading predefined scenarios…” | “No predefined scenarios are available.” No creation CTA. | Inline alert; retry. Authentication failure routes to sign-in without exposing fixture names. | If cached, label “Saved catalogue — refresh unavailable”; selecting requires current authorization. |
| Chat | Restore timeline skeleton, then replay durable state | New conversation prompt with example scope, not fabricated history | Model outage disables only composer/agent actions and links to Scenario Data, Runs/manual optimization, and saved Results. Message-send failure retains draft text and offers retry. | Reconnect banner; replay by event ID. Scenario/baseline drift marks affected Draft/Approval request stale and disables consequential actions. |
| Scenario Data | Context and group skeleton first; grid skeleton matches expected columns | Group-specific legitimate empty copy; fixture-level absence is an error because a selected fixture must resolve | Query error keeps context and offers retry. Unauthorized resource uses non-disclosing Evidence exception panel. No fallback to another fixture/version. | Cached rows may remain visible with “Stale — last verified at [timestamp]”; claim links requiring unverified current context do not silently resolve against cache. |
| Runs | Heading and table skeleton; accepted trigger immediately yields a run ID/state | “No runs for this scenario.” Manual Run optimization is the only CTA when permitted | List error offers retry. Run states remain distinct. Model outage does not disable manual deterministic run. | Reconnect resumes persisted events. If event stream is down, polling/status refresh preserves the same run and labels delayed updates. |
| Results | Load run status before result. Completed result sections resolve independently only where isolation is safe | No selected run: route to Runs. Completed run with no schedule says so without inventing zero metrics | Run fetch failure vs failed/infeasible/timed-out result are distinct. Model summary outage leaves deterministic result/evidence intact. | Comparison shows candidate/baseline versions. A newer baseline marks comparison stale and blocks approval until refresh/revise/rerun. |

Global permission denial preserves no protected values in copy, URL titles, or cached flash content. A full application API outage is not described as a model outage. Saved browser-visible content may remain read-only with a stale label; no offline writes or approvals are queued.

## Interaction Primitives

### Keyboard and focus

- `Tab` / `Shift+Tab` follow visual reading order. `Enter` or `Space` activates buttons, tabs, table-row links, sort controls, and Evidence links according to native semantics.
- Chat composer: `Enter` inserts a new line; `Ctrl+Enter` / `Command+Enter` sends. The visible Send button is always available when sending is valid. Sending never triggers Run optimization or approval.
- Scenario Data tables remain semantic tables, not spreadsheet editors. Data cells are not placed in the tab order merely for viewing. Header sort buttons, filters, column controls, links, and copy controls are tabbable.
- An evidence target receives programmatic focus with `tabindex=-1` after its row/window loads. Assistive text announces group, record, field/range, and cited version. Return to claim restores focus to the originating link.
- `Escape` closes the topmost popover/dialog without committing a change and returns focus to its trigger. Closing an Approval request performs no approval decision.
- Runs rows open with `Enter`/`Space`; row-level Cancel/Retry controls stop propagation and state the affected run ID.
- Browser Back/Forward restores surface, filters, evidence target, and origin when still authorized. Native browser find remains available; ShiftMind does not replace system shortcuts with undocumented globals.

### Pointer and motion

Click/tap follows the same controls as keyboard. Hover may supplement but never reveal the only evidence, run, or approval action. Dragging is not used for scheduling, row reordering, or column meaning in this scope. Loading spinners and skeletons respect reduced motion; evidence targeting never flashes or pulses.

## Evidence Navigation

### Claim-to-record contract

Every numerical or schedule-specific agent claim is rendered from structured claim content with one or more adjacent Evidence links. Each link resolves an application-owned locator:

`scenario ID + fixture/schedule/run version + evidence group + record ID + optional field + optional time range + origin claim ID`

The visible label is specific, for example “Evidence: Demand `DEM-204`, 13:00–17:00, fixture `v7`.” A generic message-level Sources link is insufficient. Future agent responses use this same locator contract; prose-only URLs and model-generated routes are not trusted navigation.

### Jump and return

1. Activating Evidence link records conversation ID, message ID, claim ID, scroll offset, and focused element in app-owned navigation state.
2. ShiftMind opens Scenario Data or the Results evidence region for the cited scenario/version, selects the named group, applies only the locator needed to reveal the record, and loads the correct page/window.
3. Evidence highlight focuses the row/cell/record and announces the resolved target. Normal user filters are preserved separately and restored on return.
4. Return to claim returns to the exact claim, restores scroll/focus, and does not resend or regenerate the message.

### Exception behavior

| Exception | Required behavior |
|---|---|
| Version mismatch | Do not switch the workspace or substitute current data. State cited and selected versions. If authorized, offer **Open cited version** as an explicit read-only action; otherwise offer Return to claim. |
| Missing evidence | Confirm the locator could not resolve in the exact cited version, show safe locator fields, offer Retry and Return to claim, and flag the originating claim as “Evidence unavailable.” Do not choose a similar row. |
| Unauthorized evidence | Say “Evidence is not available to this session,” reveal no record existence/value, and offer Return to claim. Reauthorization follows the application sign-in path. |
| Stale cached evidence | Label last-verified time. Do not present it as current or use it to satisfy a version-bound approval. Offer Retry/refresh when online. |
| Model outage | Existing structured links in saved messages continue to resolve because evidence navigation is application-owned. No new agent claims are generated. |

Unsupported numerical content must fail the grounding gate rather than render an unlinked confident claim. If a stored historical message has lost resolvable evidence, preserve the message as history but visibly mark the claim and use the missing-evidence path.

## Responsive & Platform

| Viewport | Behavior |
|---|---|
| Desktop/laptop (`≥1024px`, primary) | Full four-view workspace. Chat/Runs/Results use the centered reading column; Scenario Data expands within 24px gutters. Group navigation may sit beside the grid when space permits. |
| Tablet (`768–1023px`) | Panels stack. Workspace tabs remain horizontally scrollable without truncating labels. Scenario group navigation becomes a Select or horizontal list; tables keep contained two-axis scroll and sticky headers. Draft, run, and approval controls remain explicit and full-width where needed. |
| Phone (`<768px`) | **[ASSUMPTION — memlog]** Read-only triage: view Chat history, Scenario Data, Runs, Results, evidence, and provenance. Composer, draft revision, Run optimization, cancellation, and approval direct Maya to desktop with clear copy; server authorization does not depend on viewport. Tables use contained horizontal scroll and a compact essential-column default. |

ShiftMind is a responsive web application, not a native mobile product. Touch targets remain at least 44 by 44 CSS px. No hover-only controls.

## Accessibility Floor

- WCAG 2.2 AA for the full desktop journey and read-only responsive views. Visual contrast responsibilities live in `DESIGN.md`.
- Landmarks and headings identify Fixture catalogue and each workspace view. On route change, focus moves to the view heading except evidence jumps, which move to the exact evidence target.
- Tables use a caption, `<th scope>` associations, sort state via `aria-sort`, and text alternatives for abbreviated identifiers. Virtualized implementations must preserve announced row position/total; an accessible paginated mode is required if the chosen virtualization cannot.
- Status badge, run progress, reconnect, approval, and terminal state use text rather than color alone. Durable state transitions announce through a polite live region; destructive/blocked transitions may use assertive announcement without repeated chatter.
- Dialogs trap focus, name their purpose, and return focus. Approval's primary action includes the consequence in its accessible name, for example “Approve candidate `c14` as baseline replacing `b12`.”
- Evidence link names target group, identifier, and version. Evidence highlight has visible focus; Return to claim restores the invoking element.
- Reduced motion disables non-essential transitions and spinner rotation where the platform requests it; status text remains.
- Zoom to 200% and text spacing changes must not hide controls or force page-level horizontal scrolling. Scenario Data may scroll within its labelled table region.
- Errors are associated with affected controls, drafts are retained after recoverable failures, and copy-to-clipboard feedback is announced.
- Supported test matrix (portfolio minimum): latest Chrome and Edge on Windows, keyboard-only operation, and 100%/200% zoom with increased text spacing and reduced motion — verified through automated tooling (axe-core, ARIA/semantic assertions, Playwright browser checks). Manual assistive-technology (screen-reader) verification is explicitly out of scope for this portfolio MVP: no real users exist yet (see product brief), and automated accessibility coverage is the recorded bar. WCAG 2.2 AA conformance claims are scoped to this matrix until it is deliberately widened.

## Source Requirement Coverage

This map points to UX contracts without restating the PRD's product logic.

| Source requirement (verbatim) | UX coverage |
|---|---|
| FR-1–FR-3 — Authentication and site-scoped authorization | Authenticated workspace shell and fixture catalogue gating; non-disclosing error states; every route assumes a valid session and viewport never substitutes for authorization. |
| FR-4 — Durable conversations | Conversation timeline; Chat states; Flows 1 and 5. |
| FR-5 — Grounded schedule investigation | Scenario Data IA; Evidence Navigation; Flows 1–3. |
| FR-6 — Clarification and refusal | Message block; Voice and Tone; Flow 1 failure path. |
| FR-7 — Evidence-linked explanations | Evidence link/highlight/return; Evidence Navigation; Flow 3. |
| FR-8 — Model-outage fallback | Chat/Runs/Results states; Flow 4. |
| FR-9 — Typed proposal creation | Draft card; Flow 1. |
| FR-10 — Reversible draft boundary | Draft card and separate interaction primitives; Flow 1. |
| FR-11 — Deterministic schedule generation | Run progress card, Results evidence panel, Voice and Tone; Flows 1 and 4. |
| FR-12 — Bounded asynchronous run | Run progress card; Runs state; Flow 1. |
| FR-13 — Progress and recovery | Run progress card, Reconnect banner; Flow 5. |
| FR-14 — Immutable run evidence | Scenario/version context, Results evidence panel, Provenance timeline; Flows 3 and 5. |
| FR-15 — Before/after comparison | Comparison summary; Results IA; Flows 1 and 6. |
| FR-16 — Retry and cancellation safety | Runs table and Run progress card behavior; Flow 5 failure path. |
| FR-17 — Baseline-promotion proposal | Approval request separated from completed candidate; Flow 1. |
| FR-18 — Exact-action approval | Approval request, stale state; Flow 6. |
| FR-19 — Atomic baseline promotion and recovery | Terminal outcome and Provenance timeline; Flows 1, 5, and 6. |
| FR-20 — Complete decision provenance | Provenance timeline; Results IA; Flows 1 and 3. |
| FR-21 — Complete authoritative audit | Provenance timeline; audit-independent Results behavior; saved evidence remains available during model/telemetry outage (Flow 4). |
| FR-22 — Predefined scenario selection | Fixture catalogue and Scenario Data read-only boundary; Flow 2. |
| FR-24 — Read-only Scenario Data viewer | Scenario Data groups, component/large-table/state contracts; Flows 2 and 3. |

## Key Flows

### Flow 1 — Repair Wednesday outbound coverage (Maya, DC planner)

1. Maya signs in, chooses the predefined Wednesday outbound fixture, and sees its ID, fixture version, and baseline version in Scenario/version context.
2. She opens Scenario Data, checks Demand, Workers, Baseline assignments, Locks, and Constraints and objectives, then returns to Chat.
3. Maya asks why outbound coverage is weak Wednesday afternoon. The agent replies with adjacent Evidence links and requests clarification rather than guessing if worker/task identity is ambiguous.
4. She asks to keep a named worker off a task, preserve locks, and reduce overtime. Draft card shows resolved entities, intended constraints/objectives, preserved locks, expected versions, and “Draft — no baseline change.”
5. Maya revises or accepts draft parameters, then separately chooses Run optimization. Run progress card immediately shows a durable run ID and queued/running state.
6. Results presents feasibility, hard constraints, affected worker/shift/task diff, coverage/overtime/cost deltas, objective trade-offs, and unresolved gaps with evidence.
7. Maya opens Approval request for the exact feasible candidate and current baseline, reviews the consequence summary, and chooses Approve as baseline.
8. **Climax:** Terminal outcome confirms candidate and new operational-baseline versions, while Provenance timeline links the request, cited evidence, draft, run, approval, and before/after versions.

Failure paths: ambiguous identity → clarification with draft uncreated; infeasible/timed-out/failed/cancelled run → literal non-promotable outcome and revise/retry/abandon choices; stale baseline → Flow 6. No failure silently changes the baseline.

### Flow 2 — Inspect Scenario Data directly (Maya, before trusting Chat)

1. Maya selects a predefined fixture from Fixture catalogue.
2. She opens Scenario Data and confirms scenario ID, immutable fixture version, and baseline version.
3. She moves through the seven fixed groups, uses Filter bar to find Wednesday outbound demand, and sorts by interval while the stable-ID tie-break remains deterministic.
4. She copies the demand and task identifiers, opens Workers and Locks, and clears the filters.
5. **Climax:** Maya can reconcile the exact normalized demand, eligibility, assignments, and locks without asking the agent and without seeing any mutation control.

Failure paths: a group has no records → legitimate group-specific Empty state; query fails → context remains, Inline alert offers Retry; unauthorized fixture → non-disclosing denial and no cached protected values.

### Flow 3 — Jump from an agent claim to evidence and return (Maya, verifying a number)

1. In Chat, Maya reaches the claim “Outbound is short by 4 worker-hours from 13:00–17:00,” with an adjacent Evidence link naming Demand record, range, and fixture version.
2. She activates the link. ShiftMind records the exact claim origin and opens Scenario Data at the cited Demand group/version.
3. The grid loads the correct page/window, temporarily reveals the target field if needed, focuses Evidence highlight, and announces record, field/range, and version.
4. Maya inspects neighboring demand and assignment rows without changing the fixture.
5. She activates Return to claim.
6. **Climax:** Chat returns to the same message, scroll position, and focused Evidence link; the conversation is neither regenerated nor lost.

Failure paths: selected/cited versions differ → explicit Version mismatch with optional Open cited version; locator missing → no similar-row substitution and claim marked Evidence unavailable; unauthorized → no record disclosure and Return to claim.

### Flow 4 — Continue during a model outage (Maya, coverage repair still needed)

1. Maya opens Chat and sees an Inline alert: agent assistance is unavailable; her durable conversation remains visible and composer is disabled.
2. She opens Scenario Data and verifies the saved fixture facts and locks.
3. She opens Runs and chooses the existing manual Run optimization control, which does not depend on the model.
4. Run progress card shows the durable solver run; Maya opens Results when complete.
5. **Climax:** Deterministic feasibility, schedule, metrics, evidence, and prior provenance remain usable while only model-generated assistance is unavailable.

Failure paths: manual solver is also unavailable → separate solver/service error, no conflation with model outage, no lost saved result; an optional model summary fails → only that summary section shows retry.

### Flow 5 — Reconnect and recover durable work (Maya, browser connection interrupted)

1. Maya starts Run optimization and receives run ID `R-1842` in queued/running state.
2. The browser disconnects. Reconnect banner appears while the existing timeline and run ID remain visible.
3. Maya reloads or returns later. Chat reconstructs persisted messages/cards; Runs retrieves `R-1842` and replays unseen events by persisted event ID.
4. Completed state links to the same Results and immutable evidence; duplicate replay is suppressed.
5. **Climax:** Maya resumes from the accepted run and result with one run, one semantic effect, and the same provenance—not a restarted conversation or duplicate solver job.

Failure paths: stream replay remains unavailable → labelled delayed-update polling/manual refresh; repeated Run optimization request → existing semantic response/run returned; cancellation request → pending/running state transitions once and remains inspectable.

### Flow 6 — Resolve stale approval and version mismatch (Maya, baseline changed before approval)

1. Maya reviews candidate `c14` compared with baseline `b12` and opens its Approval request.
2. Before she approves, the operational baseline becomes `b13` through a valid prior/recovered action.
3. ShiftMind marks the Comparison summary and Approval request stale, disables Approve as baseline, and names expected `b12` versus current `b13`.
4. Maya opens current Results/provenance, then chooses the offered refresh path: revise the draft or rerun against `b13`; ShiftMind never silently rebases `c14`.
5. A new candidate/comparison produces a new version-bound Approval request.
6. **Climax:** Maya approves only after the UI names the refreshed candidate, current baseline, consequence summary, and versions; the stale request remains recorded as rejected/invalid with no baseline effect.

Failure paths: expired/reused/mismatched approval → literal rejection, no resubmission; evidence for the old comparison is missing/unauthorized → Evidence exception panel and approval remains blocked.
