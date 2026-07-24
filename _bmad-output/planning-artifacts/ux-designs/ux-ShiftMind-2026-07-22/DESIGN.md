---
name: ShiftMind
description: Visual identity for an evidence-first governed scheduling workspace; shadcn/ui and Tailwind supply the base system.
status: final
sources:
  - ../../prds/prd-ShiftMind-2026-07-21/prd.md
  - ../../prds/prd-ShiftMind-2026-07-21/addendum.md
updated: 2026-07-23
colors:
  primary: '#4F46E5'
  primary-foreground: '#FFFFFF'
  evidence-link: '#4338CA'
  evidence-surface: '#EEF2FF'
  evidence-border: '#C7D2FE'
  evidence-foreground: '#1E1B4B'
  focus-ring: '#4F46E5'
typography:
  page-title:
    fontFamily: 'ui-sans-serif, system-ui, sans-serif'
    fontSize: 20px
    fontWeight: '600'
    lineHeight: '1.2'
  metric:
    fontFamily: 'ui-sans-serif, system-ui, sans-serif'
    fontSize: 28px
    fontWeight: '600'
    lineHeight: '1.2'
  identifier:
    fontFamily: 'ui-monospace, SFMono-Regular, Consolas, monospace'
    fontSize: 12px
    fontWeight: '400'
    lineHeight: '1.5'
rounded:
  evidence: 6px
  data-region: 6px
spacing:
  evidence-inset: 12px
  data-cell-x: 8px
  workspace-gutter: 24px
components:
  workspace-tabs:
    active-foreground: '{colors.primary}'
    active-underline: '{colors.primary}'
    inactive-foreground: 'inherits shadcn muted-foreground'
  scenario-version-context:
    border: 'inherits shadcn border'
    identifier-type: '{typography.identifier.fontFamily}'
    gutter: '{spacing.workspace-gutter}'
  evidence-link:
    foreground: '{colors.evidence-link}'
    focus-ring: '{colors.focus-ring}'
    radius: '{rounded.evidence}'
  evidence-highlight:
    background: '{colors.evidence-surface}'
    border: '{colors.evidence-border}'
    foreground: '{colors.evidence-foreground}'
    inset: '{spacing.evidence-inset}'
    radius: '{rounded.evidence}'
  scenario-data-grid:
    border: 'inherits shadcn border'
    header-background: 'inherits shadcn muted'
    cell-x: '{spacing.data-cell-x}'
    radius: '{rounded.data-region}'
  return-to-claim:
    foreground: '{colors.evidence-link}'
    focus-ring: '{colors.focus-ring}'
---

# ShiftMind — Design Spine

## Brand & Style

ShiftMind is a sober operational tool: evidence is prominent, authority boundaries are visible, and status is never decorative. It inherits the existing shadcn/ui, Tailwind, Radix, and system-font vocabulary. This spine defines only ShiftMind deltas: the retained indigo navigation accent, a quiet evidence-target treatment, identifier typography, and dense read-only data regions.

The visual hierarchy must make four layers legible without theatrics: selected scenario and immutable version, planner/agent conversation, deterministic solver state, and evidence/provenance. Cards separate bounded objects; they do not imply that every paragraph is an action. Motion is functional and restrained. No confidence gauges, AI glows, gradients, animated avatars, or celebratory approval effects.

## Colors

- **Primary indigo (`#4F46E5`)** retains the implemented scenario-tab accent. Use it for the active workspace view and primary focus affordances, not to claim success or feasibility.
- **Evidence link (`#4338CA`)** is the accessible text/link tone for claim citations and return links on light surfaces. Evidence links remain underlined or otherwise link-identifiable; color alone is insufficient.
- **Evidence surface (`#EEF2FF`), border (`#C7D2FE`), and foreground (`#1E1B4B`)** identify the exact evidence target reached from a claim. The treatment is temporary and localized to the resolved row/cell or record card.
- **All neutral, destructive, card, popover, input, muted, border, chart, and dark-mode tokens inherit unchanged from the existing shadcn theme.** Run states use text, icon, and structure in addition to inherited color. ShiftMind introduces no new success or warning palette.

The evidence foreground/surface combination and white/evidence-link combination target WCAG 2.2 AA for normal text. The primary/white pair is reserved for large text or controls whose shipped contrast is verified before use; ordinary inline links use `{colors.evidence-link}`.

## Typography

The system sans stack remains the default for body, controls, table values, labels, and messages. `{typography.page-title}` and `{typography.metric}` preserve the existing visual ramp for route headings and KPI cards. Stable identifiers, fixture versions, run IDs, schedule versions, and compact field names use `{typography.identifier}` when monospace improves scanning; ordinary names and explanations stay sans-serif.

Do not use display fonts, brand typefaces, or all-caps AI labels. Long identifiers wrap or truncate with an adjacent copy control and accessible full value; they never force the whole workspace wider.

## Layout & Spacing

Tailwind's spacing scale remains authoritative. Existing centered `max-w-5xl` content with 24px horizontal gutters continues for Chat, Runs, and Results. Scenario Data may use the available viewport width after `{spacing.workspace-gutter}` gutters so large grids do not compress into the reading column. Horizontal overflow stays inside the grid region, never on the page.

The scenario/version context and four peer workspace tabs remain visible above each view. Chat uses a readable single column. Results stack warning, metric, comparison, schedule, and provenance regions in evidence order. Tables use `{spacing.data-cell-x}` horizontal cell padding, sticky headers, and a sticky primary identifier column only when it materially preserves orientation.

## Elevation & Depth

Inherit shadcn Card, Alert, Dialog, Popover, Sheet, Tooltip, and dropdown elevation unchanged. Hierarchy comes from borders, background tone, headings, and placement. Evidence targeting uses `{components.evidence-highlight.background}` plus its border, not a shadow or pulse. Sticky table headers and columns use an opaque inherited surface with a hairline boundary so text never layers visually over scrolled content.

## Shapes

Inherit the current shadcn radius scale. `{rounded.evidence}` and `{rounded.data-region}` record only the ShiftMind-specific target and grid-region corners. Pills are reserved for compact statuses or immutable-version labels; full cards, message blocks, and table containers are not pill-shaped.

## Components

### ShiftMind visual deltas

| Component | Visual contract |
|---|---|
| Workspace tabs | Four peer labels: Chat, Scenario Data, Runs, Results. Active text and 2px underline use `{components.workspace-tabs.active-foreground}`; inactive and disabled states inherit shadcn muted treatment. Active state is also conveyed by `aria-current`, not color alone. |
| Scenario/version context | Quiet full-width context row above tabs or view content. Scenario name is primary; stable scenario ID, fixture version, and operational-baseline version use `{typography.identifier}` or compact badges. Border and surface inherit shadcn. |
| Evidence link | Compact inline control beside the supported claim, using `{components.evidence-link.foreground}` and a conventional link affordance. Optional record/field label may use an icon, but the accessible text names the target and version. |
| Evidence highlight | Exact resolved row, cell, or record card receives `{components.evidence-highlight.background}`, foreground, and border. No animation is required; reduced-motion and default behavior are visually identical. |
| Scenario Data grid | Dense shadcn Table delta with sticky opaque header, optional sticky identifier column, contained two-axis overflow, visible sort state, and no selection/edit styling. Header surface uses inherited muted tone. |
| Return to claim | Low-emphasis link/button near the evidence target, visually paired with Evidence link and never presented as a primary action. |

### Inherited visual coverage

Every component named by the experience spine is covered below. “Inherited” means no ShiftMind visual override; behavioral rules remain in `EXPERIENCE.md`.

| Component | Visual source or concrete treatment |
|---|---|
| Conversation timeline | Inherits normal document flow, shadcn Separator, and system typography; no chat bubbles required for agent prose. Planner and agent authorship use labels and alignment, not color alone. |
| Chat composer | Inherits shadcn Textarea, Button, Tooltip, and focus ring. Send and Run optimization cannot share the same primary control treatment. |
| Message block | Inherits body typography and card/border tokens. Clarification and refusal variants use shadcn Alert structure with explicit headings. |
| Draft card | Inherits shadcn Card, Input, Select, Button, and Separator. “Draft — no baseline change” is a text label above parameters. |
| Run progress card | Inherits shadcn Alert/Card and indeterminate Loader styling. State label and run ID remain visible; no fabricated percentage or ETA. |
| Comparison summary | Inherits shadcn Card/Table and existing metric typography. Deltas use signed text and labels, not green/red alone. |
| Approval request | Inherits shadcn Card, Alert, Button, and Dialog. Consequence summary precedes the destructive-consequence action; Approve as baseline is visually distinct from Run optimization. |
| Terminal outcome | Inherits shadcn Alert and Status badge. Completed, infeasible, timed-out, cancelled, failed, rejected, expired, and stale each show literal text. |
| Scenario group navigation | Inherits shadcn Tabs or Select. Active group uses the same active affordance as Workspace tabs without introducing another accent. |
| Filter bar | Inherits shadcn Input, Button, Popover, Select, and Badge. Active filters are text-labelled and removable; no edit iconography. |
| Column chooser | Inherits shadcn DropdownMenu/Popover with Checkbox items. It controls visibility only. |
| Identifier copy control | Inherits shadcn ghost Button and Tooltip. Copied feedback is text/assistive announcement, not only an icon swap. |
| Evidence exception panel | Inherits shadcn Alert. Missing, unauthorized, and version mismatch variants use different titles and recovery copy, not custom colors. |
| Runs table | Inherits shadcn Table and existing scroll container. Row focus and navigation retain the shipped table treatment. |
| Results evidence panel | Inherits shadcn Card, Table, Alert, and existing metric components; saved results never visually depend on the model status. |
| Provenance timeline | Inherits shadcn Card, Separator, Collapsible, and system typography. Stable IDs use `{typography.identifier}`. |
| Status badge | Inherits shadcn Badge. Text and icon carry meaning; color is secondary. |
| Inline alert | Inherits shadcn Alert default/destructive variants with a concise title and action when recovery is possible. |
| Skeleton | Inherits shadcn Skeleton. Shapes match the expected final regions and never impersonate real values. |
| Empty state | Inherits system typography and shadcn Button/Link. One explanation and at most one recovery action. |
| Reconnect banner | Inherits shadcn Alert. Persistent but non-modal; reconnecting state does not cover saved content. |

## Do's and Don'ts

| Do | Don't |
|---|---|
| Keep scenario and immutable version visible across Chat, Scenario Data, Runs, and Results | Let a view appear unbound from the evidence version it displays |
| Place Evidence links adjacent to the exact numerical or schedule-specific claim | Add one generic “Sources” link at the end of an agent message |
| Use text, icon, and structure for every run and approval state | Encode feasible/failed/stale with color alone |
| Make read-only tables look inspectable but not editable | Show checkboxes, selection fills, add-row controls, editable-cell cursors, upload, import, or delete affordances |
| Keep large-table scrolling inside a bordered region with sticky orientation cues | Allow the page itself to acquire horizontal scroll |
| Preserve saved data and results visually during a model outage | Gray out the whole workspace because Chat is unavailable |
| Use a stable, temporary evidence highlight | Pulse, flash, or animate the target |
| Separate Send, Run optimization, and Approve as baseline | Use one visually continuous “AI action” button for all authority levels |
