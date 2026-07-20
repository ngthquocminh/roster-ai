# Phase 2: Scenario Detail + Plain-English Constraints - Pattern Map

**Mapped:** 2026-07-17
**Files analyzed:** 17
**Analogs found:** 17 / 17

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/api/schemas.py` (+ `OverrideOut`) | model | request-response | `backend/api/schemas.py` (`AppliedConstraint`) | exact (same file, sibling model) |
| `backend/api/routers/scenarios.py` (+ `GET /{scenario_id}/overrides`) | route | CRUD (read) | `backend/api/routers/scenarios.py` (`get_scenario`) | exact (same file, sibling route) |
| `backend/services/constraint_service.py` (persist `parsed_constraint`) | service | CRUD (read-modify-write) | same file, lines 367-372 (existing persist block) | exact (in-place edit) |
| `frontend/src/api/scenarios.ts` (+ `getScenario`, `getScenarioOverrides`) | utility (typed endpoint wrapper) | request-response | `frontend/src/api/scenarios.ts` (`listScenarios`, `createScenario`) | exact (same file, sibling wrappers) |
| `frontend/src/api/constraints.ts` (new) | utility (typed endpoint wrapper) | request-response | `frontend/src/api/scenarios.ts` (`createScenario`) | exact (POST wrapper w/ status-attach) |
| `frontend/src/hooks/useScenario.ts` (new) | hook | CRUD (read) | `frontend/src/hooks/useScenarios.ts` | exact (single-record variant) |
| `frontend/src/hooks/useOverrides.ts` (new) | hook | CRUD (read, dependent query) | `frontend/src/hooks/useScenarios.ts` | role-match (adds `enabled` gating) |
| `frontend/src/hooks/useApplyConstraint.ts` (new) | hook | request-response (mutation) | `frontend/src/hooks/useCreateScenario.ts` | exact |
| `frontend/src/routes/Editor.tsx` (replaces `EditorPlaceholder.tsx`) | component (route) | request-response | `frontend/src/routes/EditorPlaceholder.tsx` (route slot) + `frontend/src/components/scenarios/ScenarioTable.tsx` (state handling shape) | role-match |
| `frontend/src/components/editor/ScenarioHeader.tsx` (new) | component | request-response (single fetch) | `frontend/src/components/scenarios/ScenarioTable.tsx` (loading/error/populated state triad) | role-match |
| `frontend/src/components/editor/OverridesList.tsx` (new) | component | CRUD (read, list) | `frontend/src/components/scenarios/ScenarioTable.tsx` | exact (list states: loading/empty/error/populated/overflow) |
| `frontend/src/components/editor/ConstraintTranscript.tsx` (new) | component | event-driven (session log) | `frontend/src/components/scenarios/ScenarioTable.tsx` (list rendering) + no direct transcript precedent (see Architecture Pattern 4 in RESEARCH.md) | partial-match |
| `frontend/src/components/editor/TranscriptEntry.tsx` (new) | component | transform (render one response) | `frontend/src/components/layout/ErrorBanner.tsx` (fixed-copy render over a passed-in value) | partial-match |
| `frontend/src/components/editor/ConstraintInput.tsx` (new) | component (form) | request-response (mutation) | `frontend/src/components/scenarios/CreateScenarioDialog.tsx` | exact (form + mutation + status-branch pattern), with the important divergence noted below |
| `frontend/src/components/editor/ProviderDownBanner` (or reused `Alert`) | component | request-response (transient banner) | `frontend/src/components/layout/ErrorBanner.tsx` | role-match (same banner-not-toast philosophy, different variant) |
| `backend/tests/test_scenarios_api.py` (new) | test | request-response | `backend/tests/test_constraints_api.py` (structure/style) | role-match |
| `frontend/src/api/constraints.test.ts` (new) | test | request-response | `frontend/src/api/scenarios.test.ts` | exact |

## Pattern Assignments

### `backend/api/schemas.py` — add `OverrideOut` (model)

**Analog:** `backend/api/schemas.py` lines 55-65 (`AppliedConstraint`, `RejectedConstraint`)

```python
# Existing sibling models (lines 55-65) — the shape to imitate:
class AppliedConstraint(BaseModel):
    id: str
    tool: str
    args: dict
    parsed_constraint: str

class RejectedConstraint(BaseModel):
    tool: str
    error: str
```

**New model to add** (per RESEARCH.md Pitfall 2 — do NOT reuse `AppliedConstraint`, its `parsed_constraint: str` is non-optional and will 500 on legacy data):
```python
class OverrideOut(BaseModel):
    id: str
    tool: str
    args: dict
    parsed_constraint: str | None = None  # None for pre-D-02 legacy entries
```
Place directly after `RejectedConstraint`/`ConstraintParseResponse` (bottom of file), matching the existing grouping of constraint-related models together.

---

### `backend/api/routers/scenarios.py` — add `GET /{scenario_id}/overrides`

**Analog:** same file, `get_scenario` (lines 35-41) — identical 404 pattern, identical `Depends(get_db)` DI shape.

**Imports pattern** (lines 1-12, extend with `json`):
```python
"""Scenario CRUD."""
from __future__ import annotations

import os
import sqlite3
import json  # NEW — needed to parse the stored `overrides` JSON column

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_db, get_settings
from api.schemas import ScenarioCreate, ScenarioOut, OverrideOut  # extend import
from services import scenario_service
from settings import Settings
```

**Core pattern — 404-then-shape, copied verbatim in structure** (existing `get_scenario`, lines 35-41):
```python
@router.get("/{scenario_id}", response_model=ScenarioOut,
            responses={404: {"description": "Scenario not found"}})
def get_scenario(scenario_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    s = scenario_service.get_scenario(conn, scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return s
```

**New route to add**, same file, same router instance, following the identical 404-guard shape:
```python
@router.get("/{scenario_id}/overrides", response_model=list[OverrideOut],
            responses={404: {"description": "Scenario not found"}})
def get_scenario_overrides(scenario_id: str, conn: sqlite3.Connection = Depends(get_db)) -> list[dict]:
    s = scenario_service.get_scenario(conn, scenario_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    raw = json.loads(s["overrides"] or "{}")
    return [{"id": k, **v} for k, v in raw.items()]
```
Note: reuses `scenario_service.get_scenario` (same lookup already used by the existing route) rather than a new query — the 404 semantics stay identical between the two routes on this resource.

---

### `backend/services/constraint_service.py` — persist `parsed_constraint` (D-02)

**Analog:** same file, existing persist block (lines 367-372) — in-place, additive edit only.

**Current code** (lines 367-372):
```python
# Persist ONLY applied entries; rejected/clarification are response-only (T-02-02)
if applied:
    existing = json.loads(scenario["overrides"] or "{}")
    for entry in applied:
        existing[entry["id"]] = {"tool": entry["tool"], "args": entry["args"]}
    repo.update_overrides(scenario_id, json.dumps(existing))
    conn.commit()
```

**Change (one line, additive only)** — `entry` already carries `parsed_constraint` (built inline per-tool, e.g. line ~201: `parsed_constraint = f"At least {n} workers on {task_label}..."`, appended into `applied.append({..., "parsed_constraint": parsed_constraint})` at lines 202, 237, 275, 315, 350):
```python
if applied:
    existing = json.loads(scenario["overrides"] or "{}")
    for entry in applied:
        existing[entry["id"]] = {
            "tool": entry["tool"],
            "args": entry["args"],
            "parsed_constraint": entry["parsed_constraint"],  # NEW (D-02)
        }
    repo.update_overrides(scenario_id, json.dumps(existing))
    conn.commit()
```
**Verified safe downstream** (RESEARCH.md Pitfall 5): `run_service.py:90` (`OverrideCall(id=k, tool=v["tool"], args=v["args"])`) and `insight_service.py:161` (`{"tool": v["tool"], "args": v["args"]}`) both use explicit key access, not `**v` spread or dict-equality — the added key is ignored safely by both readers. Do not refactor either reader as part of this change.

---

### `frontend/src/api/scenarios.ts` — add `getScenario`, `getScenarioOverrides`

**Analog:** same file — `listScenarios` (lines 26-30) for the GET-no-body shape, `createScenario` (lines 38-51) for the status-attach-on-error shape.

**Imports pattern** (lines 1-13, unchanged, no new imports needed):
```typescript
import { client } from "./client";
import type { paths } from "./schema";
```

**Core pattern — bare GET, no error status needed for list reads** (existing `listScenarios`):
```typescript
export async function listScenarios() {
  const { data, error } = await client.GET("/scenarios");
  if (error) throw error;
  return data;
}
```

**New wrappers to add**, following the identical shape — a path-param GET (`getScenario`) mirrors `listScenarios`' plain-throw (404 is a legitimate, expected outcome the caller's `useQuery` surfaces as `isError`, not something requiring status-branching client-side beyond what `ScenarioLayout`/`Editor` already needs for the 404 view):
```typescript
export async function getScenario(scenarioId: string) {
  const { data, error, response } = await client.GET("/scenarios/{scenario_id}", {
    params: { path: { scenario_id: scenarioId } },
  });
  if (error) {
    // Editor needs response.status to distinguish 404 (terminal "not found"
    // view, E7) from other failures (ErrorBanner) — same T-1-02 convention.
    throw { status: response.status, ...error };
  }
  return data;
}

export async function getScenarioOverrides(scenarioId: string) {
  const { data, error, response } = await client.GET("/scenarios/{scenario_id}/overrides", {
    params: { path: { scenario_id: scenarioId } },
  });
  if (error) {
    throw { status: response.status, ...error };
  }
  return data;
}
```
Regenerate `schema.d.ts` (`npm run codegen`) after the backend D-01 change lands — `paths["/scenarios/{scenario_id}/overrides"]` will not exist until then.

---

### `frontend/src/api/constraints.ts` (new file) — `applyConstraint`

**Analog:** `frontend/src/api/scenarios.ts`, `createScenario` (lines 38-51) — the exact POST + status-attach shape CONS-05's 503-vs-422 branching depends on.

```typescript
// frontend/src/api/constraints.ts (new file, same pattern as scenarios.ts)
import { client } from "./client";
import type { paths } from "./schema";

type ConstraintParseRequest =
  paths["/constraints"]["post"]["requestBody"]["content"]["application/json"];

export async function applyConstraint(body: ConstraintParseRequest) {
  const { data, error, response } = await client.POST("/constraints", { body });
  if (error) {
    // CONS-05 needs response.status to distinguish 503 (provider down) from
    // 422 (validation) — same T-1-02 convention as createScenario.
    throw { status: response.status, ...error };
  }
  return data; // ConstraintParseResponse: applied[], rejected[], clarification_needed, no_constraint_found
}
```

---

### `frontend/src/hooks/useScenario.ts` (new)

**Analog:** `frontend/src/hooks/useScenarios.ts` (entire file, lines 1-25) — single-record variant of the identical `useQuery` wrapper shape.

```typescript
// frontend/src/hooks/useScenarios.ts (existing, full file)
import { useQuery } from "@tanstack/react-query";
import { listScenarios } from "@/api/scenarios";

export function useScenarios() {
  return useQuery({
    queryKey: ["scenarios"],
    queryFn: listScenarios,
  });
}
```

**New hook**, following identically:
```typescript
// frontend/src/hooks/useScenario.ts
import { useQuery } from "@tanstack/react-query";
import { getScenario } from "@/api/scenarios";

export function useScenario(scenarioId: string) {
  return useQuery({
    queryKey: ["scenario", scenarioId],
    queryFn: () => getScenario(scenarioId),
  });
}
```

---

### `frontend/src/hooks/useOverrides.ts` (new) — dependent query

**Analog:** `frontend/src/hooks/useScenarios.ts` + RESEARCH.md Pattern 3 (dependent query via `enabled`).

```typescript
// frontend/src/hooks/useOverrides.ts
import { useQuery } from "@tanstack/react-query";
import { getScenarioOverrides } from "@/api/scenarios";

export function useOverrides(scenarioId: string, options: { enabled: boolean }) {
  return useQuery({
    queryKey: ["scenario", scenarioId, "overrides"],
    queryFn: () => getScenarioOverrides(scenarioId),
    enabled: options.enabled, // caller passes: scenarioQuery.isSuccess
  });
}
```
**Cross-plan contract (same hazard `useScenarios.ts`'s own header comment documents for `["scenarios"]`):** this exact query key (`["scenario", scenarioId, "overrides"]`) must byte-match the key `useApplyConstraint.ts` invalidates.

---

### `frontend/src/hooks/useApplyConstraint.ts` (new) — mutation + invalidation

**Analog:** `frontend/src/hooks/useCreateScenario.ts` (entire file, lines 1-34) — exact `useMutation` + `invalidateQueries` shape.

```typescript
// frontend/src/hooks/useCreateScenario.ts (existing, full file)
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createScenario } from "@/api/scenarios";

export function useCreateScenario() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createScenario,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scenarios"] });
    },
  });
}
```

**New hook**, same shape, invalidates the overrides key (NOT the scenario-detail key — RESEARCH.md Open Question 2 confirms `ScenarioOut` fields never change from `POST /constraints`):
```typescript
// frontend/src/hooks/useApplyConstraint.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { applyConstraint } from "@/api/constraints";

export function useApplyConstraint(scenarioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (text: string) => applyConstraint({ scenario_id: scenarioId, text }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scenario", scenarioId, "overrides"] });
    },
  });
}
```
**Divergence from the analog:** transcript-append and textarea-clear logic do NOT belong in this hook — they belong in the calling component's own `.mutate(text, { onSuccess: (data) => {...} })` callback (mirrors `CreateScenarioDialog`'s two-level `createScenario.mutate(body, { onSuccess: ... })` pattern), because the transcript is session `useState`, not query cache, and the clear condition depends on the *response body* (see `ConstraintInput.tsx` below), not "the request succeeded."

---

### `frontend/src/components/editor/OverridesList.tsx` (new)

**Analog:** `frontend/src/components/scenarios/ScenarioTable.tsx` (entire file, lines 1-135) — closest existing list component; copy its loading/error/empty/populated/overflow state machine directly.

**Imports pattern** (lines 34-47, adapted):
```typescript
import { LoaderCircle } from "lucide-react";
import { useOverrides } from "@/hooks/useOverrides";
import { ErrorBanner } from "@/components/layout/ErrorBanner";
```

**Core state-machine pattern** (lines 57-91, this is the template to replicate almost verbatim):
```typescript
if (isLoading) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16">
      <LoaderCircle className="size-6 animate-spin text-muted-foreground" aria-hidden="true" />
      <p className="text-sm leading-[1.5] text-muted-foreground">Loading overrides…</p>
    </div>
  );
}
if (isError) {
  return <ErrorBanner error={error} />;
}
const overrides = data ?? [];
if (overrides.length === 0) {
  return (
    <div className="flex flex-col items-center gap-4 py-16 text-center">
      <h2 className="text-[20px] leading-[1.2] font-semibold">No constraints applied yet</h2>
      <p className="text-sm leading-[1.5] text-muted-foreground">
        Type a plain-English constraint below to add one.
      </p>
    </div>
  );
}
```

**Overflow container pattern** (line 94, exact class to reuse):
```typescript
<div className="max-h-[420px] overflow-y-auto rounded-md border border-border">
  {/* one row per override, keyed by override.id (never index), server order preserved */}
</div>
```
**Row rendering:** render `override.parsed_constraint` verbatim (D-02) if present; else render the legacy fallback (`{Tool Label}: {comma-separated key=value args}` per UI-SPEC's Tool Label Map, italic + "(legacy entry)" caption) — this is new UI logic with no direct precedent, but the *container/state-machine* pattern is a direct copy of `ScenarioTable`.
**Never client-side re-sort** — same principle as `ScenarioTable`'s comment (lines 15-18): render `data` in exactly the order the backend returns.

---

### `frontend/src/components/editor/ScenarioHeader.tsx` (new)

**Analog:** `frontend/src/components/scenarios/ScenarioTable.tsx` loading/error triad (lines 57-73), adapted for a single-record fetch (`useScenario`) instead of a list.

```typescript
if (isLoading) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16">
      <LoaderCircle className="size-6 animate-spin text-muted-foreground" aria-hidden="true" />
      <p className="text-sm leading-[1.5] text-muted-foreground">Loading scenario…</p>
    </div>
  );
}
if (isError && error.status === 404) {
  // E7: terminal "Scenario not found" view + "Back to Scenarios" button (routes to "/")
}
if (isError) {
  return <ErrorBanner error={error} />;
}
```
Populated: name → Heading (`text-[20px] leading-[1.2] font-semibold`, matching `CreateScenarioDialog`'s `DialogTitle` styling, line 131); fixture → `font-mono truncate` (exact class from `ScenarioTable` line 123); `time_limit_s`/`created_at` → Label-role captions (`text-xs text-muted-foreground`, matching `CreateScenarioDialog`'s field-label class, line 145-146).

---

### `frontend/src/components/editor/ConstraintInput.tsx` (new) — form + mutation

**Analog:** `frontend/src/components/scenarios/CreateScenarioDialog.tsx` (entire file) — closest existing form-with-mutation component. Copy its structural shape (controlled state, `isSubmitting`/`canSubmit` derivation, status-branching on `error.status`, whole-form-disables-during-submit) but NOT its unconditional-clear-on-success behavior.

**Controlled state + submit-gating pattern** (lines 77-102):
```typescript
const [name, setName] = React.useState("");
// ...
const isSubmitting = createScenario.isPending;
const canSubmit = name.trim().length > 0 && fixture.length > 0 && !isSubmitting;
```
Applied to `ConstraintInput`:
```typescript
const [text, setText] = React.useState("");
const applyConstraint = useApplyConstraint(scenarioId);
const isSubmitting = applyConstraint.isPending;
const canSubmit = text.trim().length > 0 && text.length <= 2000 && !isSubmitting;
```

**Status-branch error pattern** (lines 104-110, exact shape to reuse for 503-vs-422):
```typescript
const submitError = createScenario.error as { status?: number } | null;
const fixtureErrorMessage =
  submitError?.status === 400 ? "..." : undefined;
```
Applied:
```typescript
const applyError = applyConstraint.error as { status?: number } | null;
const isProviderDown = applyError?.status === 503; // D-04 distinct banner, NOT destructive
// 422 branch must still exist (structural backstop, RESEARCH.md Pitfall/E4-422)
```

**CRITICAL DIVERGENCE — do NOT copy this part of the analog** (lines 112-125, `handleSubmit`'s `onSuccess: () => onOpenChange(false)` unconditional-clear):
```typescript
// CreateScenarioDialog's pattern (line 120-122) — DO NOT replicate as-is:
createScenario.mutate(
  { name, fixture },
  { onSuccess: () => { onOpenChange(false); } }, // always closes/clears
);
```
`ConstraintInput` must instead gate the clear on the **response body**, not "request succeeded" (UI-SPEC Input-preservation rule / RESEARCH.md Pitfall 4):
```typescript
applyConstraint.mutate(text, {
  onSuccess: (data) => {
    appendTranscriptEntry(data); // parent/local session state, D-03
    if (data.applied.length > 0 && data.clarification_needed === null) {
      setText("");
    }
    // else: rejected-only / clarification / no-match / preserved text stays
  },
});
```

**Whole-form-disables-during-submit** (mirrors `Input`/`Select` both disabling, lines 153/173): the `Textarea` and submit `Button` both disable while `isSubmitting`.

---

### `frontend/src/components/editor/TranscriptEntry.tsx` / provider-down banner (new)

**Analog:** `frontend/src/components/layout/ErrorBanner.tsx` (entire file) — fixed-copy-over-passed-prop banner philosophy; and `frontend/src/components/ui/alert.tsx` for the `default` (NOT `destructive`) variant CONS-05 requires.

```typescript
// ErrorBanner.tsx (existing) — persistent inline Alert, not a toast:
<Alert className="mx-6 my-4 max-w-3xl border-destructive/40">
  <AlertTitle>Can't reach the ShiftMind API.</AlertTitle>
  <AlertDescription className="whitespace-normal break-words">...</AlertDescription>
</Alert>
```
Applied to the 503 provider-down banner (D-04) — same `Alert`/`AlertTitle`/`AlertDescription` composition, but **`variant="default"` not the destructive border class**, per UI-SPEC's explicit distinction:
```typescript
<Alert variant="default" className="mx-6 my-4 max-w-3xl">
  <AlertTitle>The constraint parser is unavailable right now.</AlertTitle>
  <AlertDescription>
    The LLM provider couldn't be reached. Your constraint wasn't lost — edit it if needed and try again in a moment.
  </AlertDescription>
</Alert>
```
Rejected-entry styling (in `TranscriptEntry`) instead uses `text-destructive` (the `alert.tsx` `destructive` variant's own token, `alert.tsx` lines 12-13) — this is the token's first real render surface per UI-SPEC.

---

### `backend/tests/test_scenarios_api.py` (new)

**Analog:** `backend/tests/test_constraints_api.py` — read for `TestClient` setup/fixture conventions (DB override, scenario-creation helper) rather than duplicated verbatim here (file not read in full this pass; same `pytest` + `fastapi.testclient.TestClient` pattern applies per RESEARCH.md's Validation Architecture section). New file needed for: `GET /scenarios/{id}/overrides` shape, 404, and legacy-fallback (no `parsed_constraint` key) non-500 assertions.

---

### `frontend/src/api/constraints.test.ts` (new)

**Analog:** `frontend/src/api/scenarios.test.ts` (entire file) — exact `vi.mock("./client")` boundary-mock pattern (NOT `msw` — repo convention, see file's own header comment lines 1-8).

```typescript
vi.mock("./client", () => ({
  client: { GET: vi.fn(), POST: vi.fn() },
}));
import { client } from "./client";
const mockPOST = client.POST as unknown as ReturnType<typeof vi.fn>;
```
Apply the same `describe("applyConstraint")` shape as `describe("createScenario")` (lines 90-127): success resolves to data; error resolves→rejects with `{status: 503}` and `{status: 422}` attached (CONS-05's exact discriminator).

## Shared Patterns

### Status-attach error convention (T-1-02)
**Source:** `frontend/src/api/scenarios.ts` `createScenario` (lines 44-49)
**Apply to:** `getScenario`, `getScenarioOverrides`, `applyConstraint` — every new/modified wrapper this phase.
```typescript
if (error) {
  throw { status: response.status, ...error };
}
```
Callers branch on `error.status` (403/404/422/503), never on error message text.

### TanStack Query invalidation-on-mutation-success
**Source:** `frontend/src/hooks/useCreateScenario.ts`
**Apply to:** `useApplyConstraint` — invalidates `["scenario", scenarioId, "overrides"]` (not the scenario-detail key).
Cross-file query-key contract: `useOverrides.ts`'s `queryKey` and `useApplyConstraint.ts`'s `invalidateQueries` key must byte-match.

### List state machine (loading/error/empty/populated/overflow)
**Source:** `frontend/src/components/scenarios/ScenarioTable.tsx` (lines 57-134)
**Apply to:** `OverridesList.tsx`, and (single-record variant) `ScenarioHeader.tsx`.
Centered spinner + literal loading text; `ErrorBanner` on error (no partial/stale rows); dedicated empty-state block; `max-h-[420px] overflow-y-auto rounded-md border border-border` container for overflow; server order preserved, never client re-sorted; keyed by `id`.

### Banner-not-toast for persistent server-state failures
**Source:** `frontend/src/components/layout/ErrorBanner.tsx`
**Apply to:** the 503 provider-down banner — persistent inline `Alert`, fixed copy, `variant="default"` (not `destructive`) to stay visually distinct from validation/rejection styling (CONS-05's load-bearing requirement).

### Form + mutation with status-branch, whole-form-disable-on-submit
**Source:** `frontend/src/components/scenarios/CreateScenarioDialog.tsx`
**Apply to:** `ConstraintInput.tsx` — controlled state, `canSubmit` derivation, textarea+button both disable while `isPending`, error status-branch drives inline messaging. **Do not** copy the unconditional-clear-on-success; gate on response body per UI-SPEC's Input-preservation rule instead.

### React default JSX escaping — no `dangerouslySetInnerHTML`
**Source:** `frontend/src/components/scenarios/ScenarioTable.tsx` (comment, lines 25-27, T-1-03)
**Apply to:** every render of `parsed_constraint`, `error`, `clarification_needed` text (all server-influenced, task/member-name-derived strings) — plain JSX text-node interpolation only.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `frontend/src/components/editor/ConstraintTranscript.tsx` | component | event-driven (session log) | No chat-transcript/session-log UI exists anywhere in the current codebase; nearest precedent is `ScenarioTable`'s list-rendering shape (container/keying only), and the auto-scroll behavior (RESEARCH.md Architecture Pattern 4) has no repo precedent — implement per RESEARCH.md's `scrollIntoView` example directly. |

## Metadata

**Analog search scope:** `frontend/src/api/`, `frontend/src/hooks/`, `frontend/src/components/scenarios/`, `frontend/src/components/layout/`, `frontend/src/components/ui/`, `frontend/src/routes/`, `backend/api/`, `backend/services/`
**Files scanned:** 12 read directly (scenarios.ts, useScenarios.ts, useCreateScenario.ts, CreateScenarioDialog.tsx, ScenarioTable.tsx, ErrorBanner.tsx, EditorPlaceholder.tsx, alert.tsx, schemas.py, routers/scenarios.py, constraint_service.py excerpt, scenarios.test.ts)
**Pattern extraction date:** 2026-07-17
