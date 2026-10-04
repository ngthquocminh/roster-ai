---
title: 'Chat as a collapsible side panel in the scenario workspace'
type: 'feature'
created: '2026-10-04'
status: 'done'
baseline_commit: '9a4e3f1'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Chat is its own workspace tab, so the planner cannot read Scenario Data, Runs or Results while talking to the agent. Following an Evidence link also takes them out of the conversation.

**Approach:** Mount `ChatView` once in a right-side panel inside the loaded `ScenarioWorkspace`, so it stays mounted across all workspace tabs. The panel toggles between expanded and a slim collapsed rail, and the Chat tab is removed.

## Boundaries & Constraints

**Always:**
- Right side. On desktop (`lg`, ≥1024px) the expanded panel **pushes** the page: content shrinks and nothing is covered. Collapsed is a ~48px rail with a chat icon and an expand button that stays visible.
- Expanded/collapsed state is saved in `localStorage` under one key and defaults to expanded. Every storage read and write is wrapped in try/catch, so a broken or blocked store falls back to the default.
- Below `lg` the panel is a full-height drawer **overlaying** the page, closed on first render whatever is stored, and opened from a visible toggle.
- `ChatView` stays mounted while collapsed (hidden, not unmounted), so the live stream and unsaved Draft card edits survive collapsing and tab switches.
- The toggle is a real `<button>` with `aria-expanded`, `aria-controls` and an accessible name ("Expand chat" / "Collapse chat"). Hit targets are at least 44px (`min-h-11`).
- `/scenarios/:scenarioId` (the old Chat URL) redirects to `/scenarios/:scenarioId/data`, keeping the search string and history `state`. When `?conversation=` is present, the panel opens.
- Conversation selection survives navigating between tabs and following Evidence links, even when the destination URL has no `?conversation=`.

**Ask First:** Any backend or API change. Any change to `EvidenceTargetPanel`'s Return-to-claim contract.

**Never:** No new dependencies. No change to the internals of chat behaviour (stream, composer, drafts, archive). No drag-to-resize. No full-page Chat route kept alongside the panel.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First visit, desktop | no stored state | panel expanded beside the workspace | N/A |
| Collapse then reload | stored collapsed | rail shown, chat hidden but mounted | storage throws → expanded |
| Pick conversation, then click a Scenario Data tab or Evidence link | URL loses `?conversation=` | same conversation stays selected | N/A |
| Return to claim | `/scenarios/:id?conversation=X` + state | redirect to `/data?conversation=X`, panel opens, origin claim focused | N/A |
| Narrow viewport | width < 1024 | drawer closed; toggle opens it over the content | N/A |
| Workspace loading or error | context query pending/failed | no panel rendered (unchanged screens) | N/A |

</frozen-after-approval>

## Code Map

- `frontend/src/routes/ScenarioWorkspace.tsx` -- loaded-state shell; becomes a flex row of content + panel.
- `frontend/src/features/chat/ChatView.tsx` -- reads the selection from `?conversation=` (line ~105); `select()` writes it back.
- `frontend/src/features/scenario-workspace/WorkspaceTabs.tsx` -- holds the Chat NavLink to remove.
- `frontend/src/App.tsx` -- route tree; index child is `ScenarioChat`.
- `frontend/src/routes/ScenarioChat.tsx` -- becomes the index redirect.
- `frontend/src/features/evidence/EvidenceTargetPanel.tsx:140` -- Return to claim navigates to `/scenarios/:id?conversation=X` with `state.evidenceOrigin`. Unchanged; relies on the redirect.
- `frontend/src/features/chat/ActivityTimeline.tsx:95` -- the Evidence link navigates to `/data?…`, dropping `conversation`.
- `frontend/src/components/layout/AppBar.tsx` -- `h-16` header; the panel sits below it.

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/features/chat/ChatView.tsx` -- keep a `useState` of the last selected id. Derive `requestedId` = URL param if present, else the remembered id. `select()` updates both. -- the selection survives URLs without the param, and existing URL-driven tests still hold.
- [x] `frontend/src/features/chat/ChatPanel.tsx` (new) -- `<aside>` panel: header with title and toggle; collapsed rail; localStorage persistence; narrow-viewport drawer (`matchMedia("(min-width: 1024px)")` for the initial state); opens when `?conversation=` appears; renders `ChatView` always, hidden when collapsed. -- the single owner of panel behaviour.
- [x] `frontend/src/routes/ScenarioWorkspace.tsx` -- loaded state: content column (`min-w-0 flex-1`, keeps `max-w-6xl` centring) plus `<ChatPanel scenarioId>`. Desktop panel is sticky under the AppBar at `h-[calc(100vh-4rem)]` and about 420px wide when expanded. -- the push layout.
- [x] `frontend/src/features/scenario-workspace/WorkspaceTabs.tsx` -- remove the Chat tab. -- the chat now lives in the panel.
- [x] `frontend/src/routes/ScenarioChat.tsx` + `frontend/src/App.tsx` -- replace with a `ScenarioIndexRedirect` (`<Navigate replace to={{ pathname: "data", search }} state={location.state} />`) and wire it as the index route. -- keeps old links and Return to claim working.
- [x] Tests -- new `ChatPanel.test.tsx` (toggle and aria-expanded, persistence including a throwing storage, stays mounted when collapsed, opens on `?conversation=`). Rewrite `ScenarioChat.test.tsx` for the redirect (search and state preserved). Update `ScenarioWorkspace.test.tsx` and `router.test.tsx` for no Chat tab and a mounted panel. Add a `ChatView.test.tsx` case: select, navigate to a URL without the param, selection kept.

**Acceptance Criteria:**
- Given a loaded workspace on desktop, when the planner collapses the panel, then the content widens, the rail with "Expand chat" remains, and the chat's DOM (including Draft edits) is still present.
- Given an open conversation, when the planner switches between Scenario Data, Runs and Results, then the panel keeps showing the same conversation without remounting.
- Given the Chat tab is gone, when the workspace tabs render, then they read Scenario Data, Runs, Results.

## Design Notes

Selection precedence in `ChatView`:
```ts
const [remembered, setRemembered] = useState("");
const requestedId = searchParams.get("conversation") ?? remembered;
// select(id): setRemembered(id); also write ?conversation=id (replace)
```
URL first, so Return to claim and deep links win. Memory second, so tab and Evidence navigation don't drop the thread.

## Verification

**Commands:**
- `cd frontend && npx tsc -b` -- expected: no errors
- `cd frontend && npm run lint` -- expected: no new findings
- `cd frontend && npx vitest run` -- expected: all pass

**Manual checks:**
- `npm run dev`: toggle the panel, reload, switch tabs, follow an Evidence link and use Return to claim, then narrow the window below 1024px.

## Suggested Review Order

**Panel behaviour (entry point)**

- One owner for expanded/collapsed, persistence, drawer mode; ChatView always mounted, only hidden.
  [`ChatPanel.tsx:51`](../../frontend/src/features/chat/ChatPanel.tsx#L51)

- URL-named conversation opens the panel on first render, before ChatView's focus restoration.
  [`ChatPanel.tsx:65`](../../frontend/src/features/chat/ChatPanel.tsx#L65)

- Breakpoint changes re-derive state; URL conversation still wins over stored collapse.
  [`ChatPanel.tsx:71`](../../frontend/src/features/chat/ChatPanel.tsx#L71)

- Narrow drawer closes on real page changes (not the chat's own `?conversation=` writes) and Escape.
  [`ChatPanel.tsx:89`](../../frontend/src/features/chat/ChatPanel.tsx#L89)

- Only the desktop choice is persisted; storage failures fall back to expanded.
  [`ChatPanel.tsx:97`](../../frontend/src/features/chat/ChatPanel.tsx#L97)

**Conversation selection across tabs**

- URL wins; remembered id covers tab and Evidence links that drop `?conversation=`.
  [`ChatView.tsx:107`](../../frontend/src/features/chat/ChatView.tsx#L107)

- Restoration never spends the origin token on a target inside a hidden panel.
  [`ChatView.tsx:148`](../../frontend/src/features/chat/ChatView.tsx#L148)

**Layout and routing**

- Push layout: content and panel scroll independently below the h-16 app bar.
  [`ScenarioWorkspace.tsx:125`](../../frontend/src/routes/ScenarioWorkspace.tsx#L125)

- Keyed by scenario so chat state never leaks between scenarios.
  [`ScenarioWorkspace.tsx:157`](../../frontend/src/routes/ScenarioWorkspace.tsx#L157)

- Old Chat URL → Scenario Data, carrying search, hash and Return-to-claim state.
  [`ScenarioIndexRedirect.tsx:12`](../../frontend/src/routes/ScenarioIndexRedirect.tsx#L12)

- Index route wiring and the removed Chat tab.
  [`App.tsx:63`](../../frontend/src/App.tsx#L63)
  [`WorkspaceTabs.tsx:26`](../../frontend/src/features/scenario-workspace/WorkspaceTabs.tsx#L26)

**Tests**

- Panel toggle, persistence, first-render open, drawer close paths.
  [`ChatPanel.test.tsx:52`](../../frontend/src/features/chat/ChatPanel.test.tsx#L52)

- Selection survives param-less navigation; unlisted URL ids don't overwrite it.
  [`ChatView.test.tsx:439`](../../frontend/src/features/chat/ChatView.test.tsx#L439)

- Real route tree: old Chat URL lands on Data with the panel mounted.
  [`router.test.tsx:168`](../../frontend/src/routes/router.test.tsx#L168)
