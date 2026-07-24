# UX Input Reconciliation — ShiftMind Architecture Spine

**Verdict:** NEEDS TARGETED RECONCILIATION

The draft spine is directionally consistent with the UX package and has no foundational paradigm conflict. It lands the strongest authority, durability, versioning, and evidence-safety decisions. Five cross-feature UX contracts remain only partial or absent, however, and could let independently built API, Chat, Scenario Data, Runs, and Results units choose incompatibly. There is also one small state-vocabulary mismatch to resolve.

## Source set

- `ux-designs/ux-ShiftMind-2026-07-22/.memlog.md`
- `ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md`
- `ux-designs/ux-ShiftMind-2026-07-22/DESIGN.md`
- `architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md`

## What landed cleanly

| UX contract | Architecture landing | Assessment |
| --- | --- | --- |
| Model/application/solver authority separation | AD-2, AD-5, AD-9, AD-10 | Strong. The browser and model cannot authorize or construct schedules; application policy and CP-SAT ownership are explicit. |
| Read-only Scenario Data sourced from the same facts used by the agent | AD-4 | Strong. One immutable normalized projection and no mutation route/tool/UI control prevent viewer/agent drift. |
| Durable work, reconnect, and replay without duplicate effects | AD-6, AD-8, AD-13 | Strong. Persist-before-acknowledgement, monotonic event replay, idempotency, and SSE non-authority support the UX reconnect flows. |
| Closed run states and literal terminal distinctions | AD-7 plus the Errors convention | Strong, subject to the vocabulary mismatch below. |
| Immutable proposals/runs/schedules and stale approval failure | AD-9, AD-10 | Strong. Version-bound approval and atomic baseline promotion match the UX's authority cues and stale-request behavior. |
| Evidence grounding, exact-version failure, and no silent retargeting | AD-11 | Strong core, but the locator identity is narrower than the UX contract; see UX-01. |
| One client owner for remote state; cache is not authority | AD-14 | Strong. This prevents approval-by-rendering and browser cache divergence. |
| Peer scenario surfaces and claim-return context | AD-14 | Present at the invariant level. Canonical route and URL-state details remain properly owned by the UX companion unless the spine must stand alone. |
| Accessibility as a release-blocking quality | AD-16 | Present as a gate. Detailed WCAG, focus, table, live-region, motion, and zoom behavior remains in the normative UX companion and does not need duplicating in the architecture spine. |
| Visual authority cues, status text, contrast, responsive layout | `DESIGN.md` / `EXPERIENCE.md` companions | Correctly delegated. These are companion contracts, not additional architecture decisions, except where they require typed states or service isolation as noted below. |

## Findings requiring spine reconciliation

### UX-01 — Evidence locator does not cover every authoritative evidence target

**Severity:** High  
**Sources:** `EXPERIENCE.md:86`, `EXPERIENCE.md:148-173`; architecture AD-11 and AD-14

The UX locator is:

`scenario ID + fixture/schedule/run version + evidence group + record ID + optional field + optional time range + origin claim ID`

AD-11 fixes only `scenario version + evidence group + record ID + optional field/time range`. This is sufficient for Scenario Data but underspecifies links into run/schedule evidence in Results and provenance. Chat, result calculation, evidence storage, and frontend navigation could consequently invent incompatible locator shapes or silently force run evidence into a scenario-only identifier.

**Required reconciliation:** Expand AD-11's target identity to a typed authoritative subject/version — at minimum scenario/fixture version, schedule version, or run ID/version as applicable — plus group, record ID, optional field, and time range. Keep the origin claim outside the evidence identity but require AD-14 to carry it as an application-owned opaque origin key; never accept a model-authored or arbitrary return URL.

**Prevents:** incompatible Chat/Results locators, unsafe return navigation, and evidence links that cannot resolve outside Scenario Data.

### UX-02 — Model-outage fault containment is not an explicit invariant

**Severity:** High  
**Sources:** `.memlog.md` model-unavailable decision; `EXPERIENCE.md:101`, `EXPERIENCE.md:123-128`, `EXPERIENCE.md:167-173`, Flow 4; architecture AD-1, AD-2, AD-5, AD-12

The UX requires a model outage to disable only model-dependent composition/summary work. Scenario Data, existing evidence links, durable conversations/results, provenance, and manual deterministic optimization remain usable. An optional model-summary failure is isolated to that section, and API/solver/model outages must not be conflated.

The hexagonal boundary makes this possible, but no rule requires the application and frontend contracts to preserve it. Separate epics could still implement a single global `agent unavailable` gate that disables the whole workspace.

**Required reconciliation:** Add or amend an invariant so provider/model health cannot gate deterministic queries, saved records/evidence, manual solver commands, approvals that no longer require a model, or provenance. Error contracts must distinguish model, solver, stream, authorization, and general API failures; optional model-generated result sections fail independently.

**Prevents:** adapter failure becoming application-wide unavailability and the browser misrepresenting a partial outage as total system failure.

### UX-03 — Large Scenario Data query/window contract is absent

**Severity:** High  
**Sources:** `.memlog.md` large-table decision; `EXPERIENCE.md:93-95`, `EXPERIENCE.md:109-116`, `EXPERIENCE.md:189`; architecture AD-4, AD-11, AD-13, AD-14

The UX deliberately leaves the rendering mechanism tunable but fixes the observable data contract: bounded pagination or virtualization, deterministic server-defined ordering with a stable-ID tie-break, total and matching counts, serializable sort/filter state, and a way to retrieve the exact page/window containing a deep-linked target before focus. A row outside the currently rendered window must not be reported as missing.

The architecture fixes the projection and transport chain but not those query semantics. The API epic could produce offset pages without stable ordering while the Scenario Data epic assumes cursor navigation or client-only filtering, breaking accessibility, Back/Forward behavior, and evidence targeting.

**Required reconciliation:** Amend AD-4, AD-11, AD-13, or AD-14 with a shared projection-query contract: version-bound filter/sort; deterministic stable-ID tie-break; bounded page/window; total/matching counts and position; and target resolution that locates the containing page/window. Pagination versus virtualization remains deferred to measured fixture scale.

**Prevents:** inconsistent table/query implementations, false missing-evidence results, and non-repeatable navigation under data growth.

### UX-04 — Typed presentation stages are implied but not bound across features

**Severity:** Medium  
**Sources:** `.memlog.md` Chat authority decision; `EXPERIENCE.md:18`, `EXPERIENCE.md:83-91`; `DESIGN.md:73-75`, `DESIGN.md:126-132`, `DESIGN.md:158`; architecture AD-2, AD-6, AD-7, AD-9, AD-10, AD-14

The domain authority partition is strong, but the public/browser contract does not explicitly require analysis, clarification, proposal draft, solver run/progress, comparison, approval request, and promotion outcome to be discriminated typed records/events. The UX depends on that separation so Send, Run optimization, and Approve as baseline cannot collapse into one generic agent action or be inferred from prose.

**Required reconciliation:** Amend AD-6, AD-13, or AD-14 to require discriminated persisted event/resource types for planner messages, grounded claims, clarification/refusal, reversible proposals, run progress/outcomes, comparisons, approval requests/decisions, and promotion outcomes. Consequential controls derive from current server-owned state and policy, never message text or card presence.

**Prevents:** Chat and Results epics parsing prose, visually implying authority the server did not grant, or rendering an enabled promotion control for non-promotable outcomes.

### UX-05 — Non-disclosing authorization failure is incomplete at the browser boundary

**Severity:** Medium  
**Sources:** `EXPERIENCE.md:122-128`, `EXPERIENCE.md:165-170`; architecture AD-3, AD-11, AD-13, AD-15

AD-11 distinguishes unauthorized evidence and AD-3 enforces server scope, but the UX additionally requires denial responses and transitions not to reveal record existence/value through copy, resource identifiers, route titles, or cached flash content. This is not the same as ordinary permission denial and is not guaranteed by RFC 7807 alone.

**Required reconciliation:** Add a response/presentation convention that site/evidence denials use non-enumerating problem details and that protected cached values are cleared or suppressed before denial UI and document/route metadata render. Safe locator fields may be shown only when already authorized for the caller.

**Prevents:** cross-site enumeration and protected-value leakage through UI residue despite correct repository authorization.

## Conflict and ambiguity to resolve

### UX-C1 — `cancellation_requested` is in the architectural run vocabulary but omitted from the UX card list

**Severity:** Low  
**Sources:** architecture AD-7; `EXPERIENCE.md:88`, `EXPERIENCE.md:125`, Flow 5

AD-7 binds all run-status UI to `cancellation_requested`. The UX Run progress card lists queued, running, approval-required, completed, infeasible, timed-out, cancelled, and failed, although Flow 5 describes a pending cancellation transition. This is not a domain conflict, but it can produce a UI that maps `cancellation_requested` back to `running` and hides a meaningful durable state.

**Resolution:** Retain `cancellation_requested` in AD-7 and require the UX presentation label “Cancellation requested.” Treat hyphenated display labels (`approval-required`, `timed-out`) as presentation strings for underscore API enum values, not competing wire values.

## Deliberately left in the UX companions

The following contracts are important but do not warrant duplication as architecture ADs because `EXPERIENCE.md` and `DESIGN.md` are declared companions and AD-14 binds the UX companion:

- Exact route paths, workspace-tab order, Results selected-run behavior, filter URL shape, and Back/Forward focus restoration.
- Loading skeletons, empty-state copy, component placement, sticky headers/columns, contained scroll, and column visibility behavior.
- WCAG 2.2 AA details: semantic tables, `aria-sort`, live regions, focus trapping/restoration, 44px targets, reduced motion, 200% zoom, and text-plus-color status treatment.
- Desktop/tablet/phone layout and the phone read-only-triage assumption. AD-3 already ensures viewport never becomes an authorization boundary.
- Indigo/evidence tokens, typography, card treatments, and visual hierarchy.

If downstream builders are expected to consume `ARCHITECTURE-SPINE.md` without its declared companions, then the spine must instead surface a short **Inherited UX Invariants** block pointing to these normative sections; copying the details into new ADs would create two sources of truth.

## Recommended disposition

1. Amend existing ADs rather than create many new decisions: AD-11 for evidence identity; AD-13/AD-14 for query, typed presentation, and denial contracts; AD-1 or a single new failure-containment AD for model-outage isolation.
2. Keep the UX companions authoritative for interaction, accessibility, responsive, and visual execution.
3. Preserve the architecture's `cancellation_requested` state and align the UX rendering vocabulary.
4. Re-run lint/reviewer checks after these edits; no paradigm, stack, deployment, or domain-boundary redesign is indicated by this reconciliation.
