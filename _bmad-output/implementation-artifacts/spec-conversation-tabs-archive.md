---
title: 'Conversation list: single-row overflow tabs with archive'
type: 'feature'
created: '2026-09-25'
status: 'done'
review_loop_iteration: 1
context: []
baseline_commit: 'b00d1cbb99c84d35f79ac689bb36173d92b4f14d'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `ConversationList` renders conversations as a `flex-wrap` button
group, which grows tall as conversations accumulate, and there is no way to
remove a conversation from the list.

**Approach:** Restyle the list as a single-row, horizontally-scrolling tab
strip (no wrap, overflow-x scroll). Add an "Archive" affix button per tab that
soft-hides the conversation (new `archived_at` column) via a new backend
endpoint; archived conversations disappear from the list.

## Boundaries & Constraints

**Always:**
- Archive is soft (`archived_at` timestamp), never a hard delete. No row, message, agent_run, or persisted_event is ever removed.
- `list_for_scenario` excludes `archived_at IS NOT NULL` by default; no query param to include archived (no "view archived" UI in this pass).
- Archiving is idempotent: archiving an already-archived conversation is a no-op success, not an error.
- An unknown/cross-site/foreign conversation on archive returns 404, same non-disclosure shape as the other conversation endpoints (AD-3).
- The tab button (select) and the archive button are **sibling** controls, never nested (no `<button>` inside `<button>`) — keeps `getByRole("button", { name: "Conversation <id8>" })` accessible-name stable for existing/future tests.
- DB grants stay column-scoped: `shiftmind_runtime` gets `GRANT UPDATE (archived_at) ON conversation`, mirroring the existing `c7d6e5f4a3b2` pattern — never a blanket `UPDATE`/`DELETE` grant.
- Follow existing conventions: action-style route (`POST /{conversation_id}/archive`, not generic PATCH), `openapi-fetch` client wrapper, TanStack Query invalidation on success.

**Ask First:** none — open design points were already resolved with the human (archive-only semantics, × affix per tab, archived conversations disappear entirely, keep as one combined spec).

**Never:**
- No hard-delete endpoint or UI.
- No "unarchive" / "view archived" UI in this pass (deferred; not tracked separately since it's a natural, obvious follow-up rather than a distinct shippable goal).
- No full ARIA `tablist`/roving-tabindex pattern — keep existing `nav > ul > li` list semantics, just restyle for single-row overflow. Scope is visual, not a new interaction model.
- No `expected_resource_version` / optimistic-concurrency check on archive — it's an idempotent state flag, not an event-stream mutation.
- Archive is **list-visibility only, not an access-control change**: `timeline`, `send_message`, `execute_agent_turn`, and the SSE `/events` route are unchanged and still resolve an archived conversation by id. Anyone with the conversation id (an open tab, a bookmarked link) can keep reading and writing to it; an in-flight agent run keeps running. Confirmed explicitly with the human after code review flagged it (2026-09-26) — making archive also revoke read/write access is out of scope for this pass, not an oversight.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Archive visible conversation | Valid `conversation_id`, own site | `archived_at` set, 204 | N/A |
| Archive already-archived conversation | Same id, archived again | 204, `archived_at` unchanged (no double-stamp) | N/A |
| Archive unknown/foreign-site conversation | Unknown or other-site id | 404, same shape as other conversation 404s | AD-3 non-disclosure |
| List conversations after archive | Scenario with 1 active + 1 archived | `items` contains only the active one | N/A |
| Archive the currently-selected conversation | `selectedId` = archived id, list refetched | Selection auto-clears (existing `items.some(...)` derivation in `ChatView`) — no new code needed | N/A |
| Many conversations | > fits one row | Tab strip scrolls horizontally; no wrap, no vertical growth | N/A |

</frozen-after-approval>

## Code Map

- `backend/adapters/postgres/schema.py:275` -- add `Column("archived_at", DateTime(timezone=True), nullable=True)` to `conversation` table
- `backend/migrations/versions/` (new, `down_revision="e5f6a7b8c9d0"`) -- add column + `GRANT UPDATE (archived_at) ON conversation TO shiftmind_runtime` (pattern: `c7d6e5f4a3b2_grant_agent_run_status_update.py`)
- `backend/application/ports/conversation.py` -- add `archive(connection, *, conversation_id) -> bool` to `ConversationRepository` Protocol (no explicit `site_id` — the `get_site_context`-scoped connection's RLS policy already confines the `UPDATE` to the caller's site, same as `timeline()`)
- `backend/adapters/postgres/conversation.py:220` (`list_for_scenario`) -- filter `conversation.c.archived_at.is_(None)`; add `archive()` impl (`UPDATE ... SET archived_at = COALESCE(archived_at, now()) WHERE id = :id RETURNING id`; no row (unknown or RLS-hidden foreign-site id) → repo returns `False`)
- `backend/api/routers/conversations.py:176` -- add `POST /{conversation_id}/archive`, 204 on success, 404 via same `HTTPException(status_code=404)` idiom as `create_conversation`
- `backend/tests/test_conversations_postgres.py`, `backend/tests/test_conversations_api.py` -- cover the I/O matrix above
- `frontend/openapi.json`, `frontend/src/api/schema.d.ts` -- regenerate (`export_openapi.py` then `codegen:types`)
- `frontend/src/api/conversations.ts` -- add `archiveConversation(conversationId)`
- `frontend/src/hooks/useConversations.ts` -- add `useArchiveConversation(scenarioId)` (invalidates `conversationsKey`)
- `frontend/src/features/chat/ConversationList.tsx` -- rewrite to single-row overflow strip; add per-tab archive affix + confirm dialog (pattern: `ApprovalDecisionDialog.tsx`/`ApprovalDecisionPanel.tsx` — trigger ref, `onRestoreFocus`)
- `frontend/src/features/chat/ChatView.tsx:227` -- wire `useArchiveConversation`, pass down to `ConversationList`
- `backend/tests/test_evidence_binding.py:332` -- discovered during implementation: hardcodes the alembic head revision; must track the new migration's revision id
- `backend/tests/test_gate_a_mutation_audit.py:262`, `docs/GATE-A-RUNBOOK.md:45` -- discovered during implementation: Gate A's write-surface allowlist and runbook both enumerate every versioned write route explicitly; the new archive route must be added to both

## Tasks & Acceptance

**Execution:**
- [x] `backend/adapters/postgres/schema.py` -- add `archived_at` column to `conversation` table -- storage for soft-archive
- [x] `backend/migrations/versions/f7a8b9c0d1e2_add_conversation_archive.py` -- nullable column + column-scoped GRANT -- schema change + minimal runtime privilege, per existing pattern
- [x] `backend/application/ports/conversation.py` -- add `archive()` to the Protocol -- keeps port/adapter in sync
- [x] `backend/adapters/postgres/conversation.py` -- implement `archive()`; filter `list_for_scenario` -- soft-hide behavior
- [x] `backend/api/routers/conversations.py` -- add archive route -- HTTP surface
- [x] `backend/tests/test_conversations_postgres.py` -- repo-level: archive, idempotent re-archive, list excludes archived, unknown/foreign-site → `False`, plus a column-grant boundary test
- [x] `backend/tests/test_conversations_api.py` -- route-level: 204 happy path, idempotent re-archive, 404 unknown/foreign
- [x] `backend/scripts/export_openapi.py` run, then `frontend` `npm run codegen:types` -- refresh generated types
- [x] `frontend/src/api/conversations.ts` -- `archiveConversation()` -- typed client call
- [x] `frontend/src/hooks/useConversations.ts` -- `useArchiveConversation()` -- mutation + cache invalidation
- [x] `frontend/src/features/chat/ConversationList.tsx` -- single-row overflow layout; per-tab × affix opens a confirm dialog before archiving -- UI ask
- [x] `frontend/src/features/chat/ChatView.tsx` -- wire the mutation through -- owns mutations per existing convention
- [x] `frontend/src/features/chat/ConversationList.test.tsx` (new) -- renders as single row/overflow; × is a sibling control with its own accessible name; confirm dialog gates the archive call
- [x] `frontend/src/features/chat/ChatView.test.tsx` -- extend: archiving the selected conversation clears selection; archived item drops out of the rendered list
- [x] `backend/tests/test_evidence_binding.py` -- update the hardcoded alembic head literal to the new migration's revision id
- [x] `backend/tests/test_gate_a_mutation_audit.py`, `docs/GATE-A-RUNBOOK.md` -- add the new archive route to Gate A's approved-write-surface list and record why it does not touch governed scenario data or the baseline pointer
- [x] `frontend/src/features/chat/ChatView.tsx` -- review round 1 patches: per-id `archivingIds` tracked via `mutateAsync` + `try/finally` (not `.mutate(id, {onSettled})`, which shares one observer's callback options across concurrent calls); surface `archive.isError` with a retry action; add a focus fallback for when archiving the last conversation unmounts the list
- [x] `frontend/src/features/chat/ConversationList.tsx` -- review round 1 patches: `archivingIds: ReadonlySet<string>` prop (was a single `archivingId`); `onFocusFallback` prop as a third focus-restore fallback after the trigger and the list
- [x] `frontend/src/features/chat/ChatView.test.tsx`, `frontend/src/features/chat/ConversationList.test.tsx` -- extend for the round-1 patches: failed archive shows a retry action; two concurrent archives don't cross-contaminate each other's disabled state

**Acceptance Criteria:**
- Given a scenario with more conversations than fit one row, when the list renders, then it stays a single row and scrolls horizontally (no vertical wrap).
- Given a conversation tab, when its archive affix is activated and confirmed, then the conversation disappears from the list and, if it was selected, the chat view returns to its unselected state.
- Given an archive request for a conversation belonging to another site, when the endpoint is called, then it returns 404 with the same shape as other conversation 404s.
- Given an already-archived conversation, when archive is called again, then it still returns 204 and `archived_at` is unchanged.

## Design Notes

**Archive affix as sibling, not nested button:** `<li>` holds two elements —
the existing select `<Button>` and a new small icon `<Button>` (e.g.
`aria-label={`Archive conversation ${id8}`}`) — never one inside the other.

**Confirm dialog:** reuse the `Dialog`/`DialogContent`/`DialogFooter` primitives
and the trigger-ref + `onRestoreFocus` shape from
`ApprovalDecisionPanel.tsx`/`ApprovalDecisionDialog.tsx`, since there's no
"unarchive" UI in this pass and the action should not be one accidental click.

**Row layout:** swap the `<ul>`'s `flex flex-wrap gap-2` for
`flex flex-nowrap gap-2 overflow-x-auto` with `whitespace-nowrap` on items;
keep the existing `nav > ul > li` semantics as-is.

## Spec Change Log

- **2026-09-26, review loop 1 (intent_gap → resolved, no code change):** Blind Hunter + Edge Case Hunter both flagged that archive only affects `list_for_scenario`; `timeline`/`send_message`/`execute_agent_turn`/the SSE route still resolve an archived conversation by id, and an in-flight agent run isn't guarded. The frozen spec was silent on whether archive should also revoke read/write access. Asked the human directly: confirmed list-only is the intended scope. Amended the frozen `Never` section to state this explicitly rather than leave it unstated. **KEEP:** the `archived_at`-only, list-scoped design is correct as shipped — do not add read/write guards on archived conversations without a fresh human decision to expand scope.
- **2026-09-26, review loop 1 (patch, applied):** Both reviewers found `ChatView` never read `archive.isError`, so a failed archive (network error, or a race where someone else already archived it) failed silently with no retry affordance. Added an `InlineAlert` keyed to the failing conversation id with a "Try again" action.
- **2026-09-26, review loop 1 (patch, applied):** Edge Case Hunter found `archivingId` derived from `archive.isPending`/`archive.variables` on one shared `useMutation` reflects only the LATEST call — archiving conversation B while A was still in flight re-enabled A's control mid-request, allowing a duplicate archive POST. Fixed by tracking a `Set<string>` of in-flight ids in `ChatView`, updated via `archive.mutateAsync` in a per-call `try/finally` (not `.mutate(id, { onSettled })` — that stores callback options on ONE shared observer, so a second concurrent `.mutate()` call overwrites which callback fires when either promise settles, which would have left the first id stuck disabled after resolving).
- **2026-09-26, review loop 1 (patch, applied):** Edge Case Hunter found that archiving the sole remaining conversation could unmount the whole `ConversationList` (which returns `null` when `conversations` is empty) before the confirm dialog's focus-restore `setTimeout` fires, leaving both `triggerRef` and `listRef` disconnected and dropping focus to `<body>`. Added an `onFocusFallback` prop, wired by `ChatView` to the "New conversation" button, as a third fallback after the trigger and the list itself.
- **2026-09-26, review loop 1 (defer):** Edge Case Hunter's race between sending a message and archiving the same conversation (no mutual guard) is real but low-impact (no data loss, just a UI-ordering quirk) and needs a product decision on desired behavior, not a mechanical fix. Logged to `deferred-work.md` rather than blocking this pass.
- **2026-09-26, review loop 1 (reject):** No audit row/`archived_by` for the archive mutation, no `resource_version` bump, no DB CHECK constraint against un-setting `archived_at`, the Protocol docstring not being type-enforced, and the in-memory test double manually mirroring the filter — all either explicitly out of scope per the frozen `Never` list, or consistent with existing conventions elsewhere in this codebase (audit rows are scoped to approval/baseline mutations only; other mutations here also rely on application-level invariants, not DB constraints).

## Verification

**Commands:**
- `cd backend && uv run pytest tests/test_conversations_postgres.py tests/test_conversations_api.py` -- expected: all pass, including new archive cases
- `cd backend && uv run alembic upgrade head` -- expected: new migration applies cleanly
- `cd frontend && npm run codegen:types` -- expected: `schema.d.ts` reflects the new archive route with no manual edits needed
- `cd frontend && npx vitest run src/features/chat` -- expected: `ConversationList` and `ChatView` tests pass
- `cd frontend && npx tsc --noEmit` -- expected: no type errors

## Suggested Review Order

**Data model & repository (the archive semantics)**

- New nullable column backing soft-archive; never a hard delete.
  [`schema.py:282`](../../backend/adapters/postgres/schema.py#L282)

- Column-scoped `GRANT`, mirroring the existing `agent_run.status` precedent — never a blanket grant.
  [`f7a8b9c0d1e2_add_conversation_archive.py:20`](../../backend/migrations/versions/f7a8b9c0d1e2_add_conversation_archive.py#L20)

- `COALESCE` makes re-archiving idempotent; RLS alone denies a foreign-site id.
  [`conversation.py:246`](../../backend/adapters/postgres/conversation.py#L246)

- `list_for_scenario` now excludes archived rows — the one place archive actually takes effect.
  [`conversation.py:229`](../../backend/adapters/postgres/conversation.py#L229)

- Protocol addition; documents the AD-3 non-disclosure and idempotency contract the adapter fulfills.
  [`conversation.py:124`](../../backend/application/ports/conversation.py#L124)

**HTTP surface**

- `POST .../archive`, 204 on success, 404 (non-disclosing) otherwise.
  [`conversations.py:183`](../../backend/api/routers/conversations.py#L183)

**Gate A bookkeeping (why this write route is safe)**

- New route added to the approved-write-surface allowlist.
  [`test_gate_a_mutation_audit.py`](../../backend/tests/test_gate_a_mutation_audit.py)

- Runbook entry stating what the route does NOT touch.
  [`GATE-A-RUNBOOK.md`](../../docs/GATE-A-RUNBOOK.md)

- Alembic head literal updated to the new migration's revision.
  [`test_evidence_binding.py`](../../backend/tests/test_evidence_binding.py)

**Frontend: tab-strip layout + archive UI**

- Single-row overflow layout; archive affix as a sibling control (never nested) with its own confirm dialog.
  [`ConversationList.tsx:31`](../../frontend/src/features/chat/ConversationList.tsx#L31)

- Third focus-restore fallback, for when archiving the last conversation unmounts the whole list.
  [`ConversationList.tsx:61`](../../frontend/src/features/chat/ConversationList.tsx#L61)

- Typed client call for the new endpoint.
  [`conversations.ts:31`](../../frontend/src/api/conversations.ts#L31)

- Mutation wrapper; invalidates the conversations query on success.
  [`useConversations.ts:5`](../../frontend/src/hooks/useConversations.ts#L5)

**Frontend: ChatView wiring and concurrency-safety**

- Per-id tracking via `mutateAsync` + `try/finally` — NOT `.mutate(id, {onSettled})`, which shares one observer's callback options across concurrent calls.
  [`ChatView.tsx:171`](../../frontend/src/features/chat/ChatView.tsx#L171)

- Failed archive now surfaces a retry action instead of failing silently.
  [`ChatView.tsx:223`](../../frontend/src/features/chat/ChatView.tsx#L223)

- Wiring: per-id archiving set, focus fallback target, archive callback passed down.
  [`ChatView.tsx:281`](../../frontend/src/features/chat/ChatView.tsx#L281)

**Tests**

- Repo-level: archive, idempotent re-archive, foreign-site denial, column-grant boundary.
  [`test_conversations_postgres.py`](../../backend/tests/test_conversations_postgres.py)

- Route-level: 204/404/idempotent-204.
  [`test_conversations_api.py`](../../backend/tests/test_conversations_api.py)

- Presentational: layout, sibling controls, confirm-dialog gating, per-id disabled state.
  [`ConversationList.test.tsx`](../../frontend/src/features/chat/ConversationList.test.tsx)

- Integration: selection-clearing derivation, retry-on-failure, concurrent-archive independence.
  [`ChatView.test.tsx`](../../frontend/src/features/chat/ChatView.test.tsx)

**Peripheral**

- Deferred: the unguarded send/archive race on the same conversation.
  [`deferred-work.md`](../../_bmad-output/implementation-artifacts/deferred-work.md)
