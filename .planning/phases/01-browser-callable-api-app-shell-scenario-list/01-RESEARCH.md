# Phase 1: Browser-Callable API + App Shell + Scenario List - Research

**Researched:** 2026-07-16
**Domain:** Vite + React + TypeScript SPA against a FastAPI backend (CORS enablement, routing shell, typed client, scenario list/create)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

Locked upstream (milestone scoping, 2026-07-15 — do NOT re-litigate):

- **D-01:** Stack is **Vite + React + TypeScript**. TypeScript specifically so
  the client can be typed against the API contract — the user rejected plain JS
  on the grounds that hand-typed response shapes drift silently.
- **D-02:** **No auth.** No login, no session, no localStorage session UUID.
  Every scenario is globally visible. Out of scope, not an oversight.
- **D-03:** **No file upload.** Scenarios are created by picking from fixtures
  the backend already has (`GET /fixtures`). Upload is v0.5 (v2 `UP-01`) and is
  blocked on WR-04 landing first.
- **D-04:** **CORS origins configurable, not hardcoded** (BE-01's requirement text).
- **D-05:** Default `LLM_PROVIDER=stub` — keyless and deterministic. Nothing in
  this phase may require a live API key; default CI stays keyless.
- **D-06:** Desktop-first. Mobile/responsive polish is explicitly out of scope
  for v0.4.
- **D-07:** All four views ship this milestone, plus a demand-vs-served chart in
  Phase 4 — so the shell built here must accommodate four routes.

### Claude's Discretion

Four gray areas were surfaced and explicitly delegated (user declined to
discuss them — "nothing, move on to plan for the phase"). This research
resolves three of them (client typing, server state/polling, CORS shape); the
fourth (styling) was independently locked by `01-UI-SPEC.md` (shadcn + Tailwind
v4) before this research began:

- **API client typing — generated vs hand-written.** Resolved by this research:
  generated (`openapi-typescript` + `openapi-fetch`) — see Pattern 1.
- **Server state & polling strategy.** Resolved by this research: TanStack
  Query v5 from Phase 1 on — see Pattern 3.
- **CORS shape + Vite dev proxy.** Resolved by this research: real
  `CORSMiddleware` everywhere, no dev proxy — see Alternatives Considered.
- **Styling approach.** Already resolved upstream by `01-UI-SPEC.md`: shadcn
  (Radix primitives) + Tailwind CSS v4. This research treats that as locked
  and builds the Tailwind v4 setup guidance on top of it (see Common Pitfalls
  #4).

### Deferred Ideas (OUT OF SCOPE)

None raised in discussion — no discussion occurred. All 8 `todo.match-phase 1`
matches were reviewed and explicitly not folded (keyword false positives —
`scenario`/`api`/`fixtures`/`backend` overlap with backend-only or v2-scoped
todos: fixture path traversal hardening (WR-04), input upload (UP-01), run
cancellation (OPS-01), round-2 relative-gap stop (OPS-02), per-scenario engine
selection, engine-as-a-service extraction, demand scheduling tuning — none are
frontend-shell concerns).

</user_constraints>

## Project Constraints (from CLAUDE.md)

Directives extracted from `.claude/CLAUDE.md` that this phase must respect:

- **Tech stack is locked** — Python backend, OR-Tools CP-SAT, FastAPI, SQLite
  (WAL), uv-managed deps are "established in Phases 1–2, not up for change in
  this milestone." This phase's only backend touch (BE-01/CORS) must fit
  inside the existing `settings.py`/`api/main.py` pattern, not introduce a new
  config mechanism.
- **Testing: no live LLM API in CI** — irrelevant to this phase's own new code
  (no LLM calls), but the new `backend/tests/test_cors.py` must not
  incidentally require `LLM_PROVIDER` to be anything but the default `stub`.
- **Naming conventions (Python side):** snake_case modules/functions/variables,
  PascalCase classes, UPPERCASE constants — applies to the `cors_origins`
  `Settings` field addition (see Code Examples).
- **Secrets never in `__repr__`** — CORS origins are not secret, so this does
  not require `repr=False`, but do not weaken the existing pattern on the
  adjacent `llm_api_key`/`openrouter_api_key` fields while editing `settings.py`.
- **No existing frontend conventions to inherit** — CLAUDE.md's naming/style
  sections are Python-only; `frontend/` is genuinely greenfield. This research
  proposes idiomatic React/TS conventions (PascalCase components, camelCase
  `use*` hooks, shadcn's own kebab-case file naming inside `components/ui/`)
  since CLAUDE.md is silent on JS/TS.
- **GSD workflow enforcement** — file-changing work for this phase must go
  through `/gsd-execute-phase` per CLAUDE.md's workflow-enforcement section;
  noted here for the planner's awareness, not a technical constraint on the
  research itself.

## Summary

This phase is a well-trodden shape: a greenfield Vite + React + TypeScript SPA
that calls a documented REST API, plus one backend line (CORS). Nothing here
requires novel architecture — the four discretion areas left open by
`01-CONTEXT.md` (client typing, polling/server-state, CORS shape, styling) all
have a single clearly-dominant, low-risk answer for 2026, and `01-UI-SPEC.md`
has already locked styling (shadcn + Tailwind v4). This research resolves the
remaining three.

`docs/API.md` is confirmed accurate against the live backend source
(`backend/api/schemas.py`, `backend/api/routers/scenarios.py`,
`backend/api/routers/fixtures.py` were read directly). React Router's install
target changed since most training-data tutorials: as of the current major
version the recommended package is **`react-router`** itself (not
`react-router-dom`), with `RouterProvider` imported from `react-router/dom`.
Tailwind v4 (already pinned by UI-SPEC via the shadcn Vite installer) drops the
`tailwind.config.js` + PostCSS setup entirely in favor of a `@tailwindcss/vite`
plugin and one `@import "tailwindcss";` line — planners and executors coming
from Tailwind v3 muscle memory will over-build this step if not warned.

**Primary recommendation:** Scaffold with `npm create vite@latest frontend --
--template react-ts`, add `react-router` (data router API) for SHELL-03,
`@tanstack/react-query` v5 for all server state (list/create now, it directly
serves Phase 3's polling need), and generate the typed client from the
backend's own OpenAPI schema via `openapi-typescript` + `openapi-fetch` rather
than hand-typing `docs/API.md` — this makes SHELL-02 immune to the exact
docs/code drift class that forced the `93ca4e0` doc-sync commit. Wire CORS with
real `CORSMiddleware` (allow-list, no dev proxy) so Phase 1's "no CORS error"
criterion is verified against the actual cross-origin path, not a proxy that
would hide a misconfiguration until first deploy.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Cross-origin access control (BE-01) | API / Backend | — | `CORSMiddleware` is server-side; the browser only reacts to headers it emits |
| App shell / client-side routing (SHELL-01, SHELL-03) | Browser / Client | — | This is a pure SPA (no SSR framework chosen or needed) — Vite builds static assets, routing happens entirely client-side via React Router's browser router |
| Typed API client (SHELL-02) | Browser / Client | API / Backend (schema source) | Client owns the fetch call and type-checking; the backend's OpenAPI schema is the source of truth the client is generated from |
| Error surfacing (SHELL-04) | Browser / Client | — | All error states (network, 4xx/5xx, render crash) are rendered client-side; the backend just returns standard FastAPI error shapes it already produces |
| Scenario list (SCEN-01) | Browser / Client | API / Backend | Backend owns persistence and ordering (`GET /scenarios`, newest-first); client only renders and caches |
| Scenario create (SCEN-02) | Browser / Client | API / Backend | Backend owns validation (unknown-fixture 400, empty-name 422) and persistence; client mirrors validation for UX only, never as the source of truth |
| Build to static assets | CDN / Static | — | `vite build` output (`frontend/dist/`) is a static-asset bundle with no server-rendering step; deployable to any static host |
| Data persistence | Database / Storage | — | Untouched this phase — existing SQLite (WAL) via `store/db.py`; no schema changes |

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BE-01 | CORS accepts frontend origins, configurable not hardcoded | `Standard Stack` (CORSMiddleware), `Code Examples` (Settings pattern + CORS test), `Common Pitfalls` (settings-read-once tension, wildcard+credentials) |
| SHELL-01 | Vite + React + TS app under `frontend/`, dev + build | `Standard Stack` (scaffold command, versions), `Recommended Project Structure` |
| SHELL-02 | Typed API client mirroring `docs/API.md` | `Standard Stack` (openapi-typescript + openapi-fetch), `Code Examples` (codegen pipeline), `Don't Hand-Roll` |
| SHELL-03 | Navigate four views, deep-linkable | `Standard Stack` (react-router), `Code Examples` (nested route config), `Architecture Patterns` |
| SHELL-04 | Readable errors, never blank/silent | `Common Pitfalls` (CORS-vs-network ambiguity), UI-SPEC Copywriting Contract (already locked, cross-referenced) |
| SCEN-01 | See list of scenarios | `Code Examples` (TanStack Query useQuery), `Validation Architecture` |
| SCEN-02 | Create scenario from fixture picklist | `Code Examples` (TanStack Query useMutation), `Validation Architecture`, `Common Pitfalls` (client-side validation must mirror, not replace, server 400/422) |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `vite` | ^8.1 (verified 8.1.4 on npm, 2026-07-16) | Build tool / dev server | Already locked by UI-SPEC's shadcn init params (`--template vite`); fastest HMR dev loop for React SPAs |
| `react` | ^19 (verified 19.x current, 2026-06-01 latest publish) | UI library | Locked upstream (D-01) |
| `react-dom` | ^19 (matches `react`) | DOM renderer | Locked upstream (D-01) |
| `typescript` | ^5 (verify exact minor at scaffold time — `npm create vite` pins its own compatible range) | Type checking | Locked upstream (D-01) — "types can't drift silently" was the explicit rationale |
| `react-router` | ^7 (verified 8.2.0 is current major; `react-router` — not `react-router-dom` — is now the recommended install target) [CITED: context7 /remix-run/react-router] | Client-side routing (SHELL-03) | Only mainstream React router; supports `createBrowserRouter` nested layouts + deep-linkable paths out of the box |
| `@tanstack/react-query` | ^5 (verified 5.101.2 on npm) [CITED: context7 /tanstack/query] | Server state, caching, polling | Chosen at Claude's discretion (CONTEXT.md) — `refetchInterval` is exactly what Phase 3's run-status polling needs; using it from Phase 1 avoids a later fetch→Query migration |
| `openapi-typescript` | ^7 (verified 7.13.0) [CITED: context7 /openapi-ts/openapi-typescript] | Generate TS types from the backend's OpenAPI schema | Removes the SHELL-02 drift risk named explicitly in CONTEXT.md (the `93ca4e0` doc-sync precedent) |
| `openapi-fetch` | ^0.17 (verified 0.17.0) [CITED: context7 /openapi-ts/openapi-typescript] | Thin typed fetch wrapper consuming the generated schema | Zero-runtime-cost, pairs directly with `openapi-typescript`'s output; no need to hand-write a fetch wrapper |
| `tailwindcss` + `@tailwindcss/vite` | ^4.3 (verified 4.3.2) [CITED: context7 /shadcn-ui/ui] | Styling | Locked by UI-SPEC (shadcn requires Tailwind) |
| `@vitejs/plugin-react` | ^6 (verified 6.0.3) | Vite's React plugin (Babel-based, Vite scaffold default) | Ships with `npm create vite -- --template react-ts`; no reason to swap to the SWC variant for this project's scale |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `lucide-react` | ^1 (verified 1.24.0) | Icon set | Already pinned by UI-SPEC as shadcn's default icon library |
| `class-variance-authority`, `clsx`, `tailwind-merge`, `@radix-ui/react-slot` | latest (all `[VERIFIED: npm registry]`, OK verdict — see audit) | shadcn component internals (`cn()` utility, variant props) | Auto-added by `npx shadcn add <component>` — do not hand-install; let the CLI manage these |
| `@types/node` | current major (verified 26.x) | Needed for `path.resolve` in `vite.config.ts`'s `@` alias | Required the moment the shadcn `@/*` path alias is wired (see Code Examples) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `openapi-typescript` + `openapi-fetch` codegen | Hand-written types mirroring `docs/API.md` | Zero tooling, but reintroduces exactly the drift class CONTEXT.md flags as a documented recurring problem in this repo. Only defensible if the codegen step is judged not worth the setup cost for 4 endpoints — it isn't; the pipeline is 2 npm packages and one script. |
| `@tanstack/react-query` | Raw `fetch` + `useState`/`useEffect` | Less to install now, but CONTEXT.md is explicit that Phase 3 needs `refetchInterval`-grade polling across ~2min waits; deferring Query to Phase 3 means re-deriving loading/error/caching semantics for every hook built in Phase 1 first, then throwing them away. |
| `react-router` (data router: `createBrowserRouter`) | `react-router-dom` v6-style `<BrowserRouter><Routes>` (declarative mode) | Declarative mode still works and is still exported, but the library's own README now names `react-router` as the install target and the data-router API (loaders, nested layouts) is the actively-developed surface. Use the data router. |
| Real `CORSMiddleware` everywhere (dev + prod) | Vite dev proxy (`server.proxy`) in dev + CORS only in prod | A proxy sidesteps CORS in dev entirely, which would let a CORS misconfiguration go undetected until the first real deploy — directly contradicted by Phase 1's criterion 1 ("no CORS error in the console", verified against a real cross-origin request). |
| MSW (`msw`) for API mocking in frontend tests | Direct `vi.fn()`/`vi.spyOn` mocks of the typed client module | See Package Legitimacy Audit — `msw` triggered a `SLOP` verdict (likely a heuristic false positive given its 18M/week downloads and known `mockServiceWorker.js` postinstall script) and this phase's test surface (4 endpoints, ~7 requirements) does not need MSW's network-level interception. Mock the generated client functions directly; revisit MSW only if a later phase's test surface grows complex enough to justify it, with human verification first. |

**Installation:**
```bash
# Scaffold (creates frontend/ with package.json, tsconfig, default ESLint config)
npm create vite@latest frontend -- --template react-ts
cd frontend

# Routing + server state
npm install react-router @tanstack/react-query

# Typed client (openapi-typescript is dev-only; it only runs codegen)
npm install openapi-fetch
npm install -D openapi-typescript

# shadcn init (mechanical step per UI-SPEC — pinned params, no judgment needed)
npx shadcn@latest init -t vite -b radix -y --css-variables
# Tailwind + @tailwindcss/vite are installed by the shadcn Vite installer as part of init;
# do not separately hand-roll a tailwind.config.js — v4 does not use one by default.

# Component primitives this phase needs (per UI-SPEC Registry Safety)
npx shadcn@latest add button input select dialog table alert tabs
```

**Version verification:** All versions above were checked against the live npm
registry on 2026-07-16 (`npm view <pkg> version`) and cross-referenced against
Context7 documentation for API surface (not just existence). Package names
themselves originate from training knowledge / this research session's
reasoning, not from an authoritative catalog lookup — per the provenance rule,
treat package **names** as `[ASSUMED]` even though their registry existence and
current version are `[CITED: npm registry]`/`[VERIFIED]` where noted below.

## Package Legitimacy Audit

All packages checked via `gsd-tools query package-legitimacy check --ecosystem npm`.

| Package | Registry | Age (latest publish) | Downloads/wk | Source Repo | Verdict | Disposition |
|---------|----------|----------------------|--------------|--------------|---------|-------------|
| `react` | npm | 2026-06-01 | 144.9M | github.com/facebook/react | OK | Approved `[VERIFIED: npm registry]` |
| `react-dom` | npm | 2026-06-01 | 112.9M | github.com/facebook/react | OK | Approved `[VERIFIED: npm registry]` |
| `openapi-typescript` | npm | 2026-02-11 | 4.0M | github.com/openapi-ts/openapi-typescript | OK | Approved `[VERIFIED: npm registry]` |
| `openapi-fetch` | npm | 2026-02-11 | 5.8M | github.com/openapi-ts/openapi-typescript | OK | Approved `[VERIFIED: npm registry]` |
| `class-variance-authority` | npm | 2024-11-26 | 45.5M | github.com/joe-bell/cva | OK | Approved `[VERIFIED: npm registry]` |
| `clsx` | npm | 2024-04-23 | 85.6M | github.com/lukeed/clsx | OK | Approved `[VERIFIED: npm registry]` |
| `tailwind-merge` | npm | 2026-05-10 | 57.9M | github.com/dcastil/tailwind-merge | OK | Approved `[VERIFIED: npm registry]` |
| `@radix-ui/react-slot` | npm | 2026-06-15 | 157.3M | github.com/radix-ui/primitives | OK | Approved `[VERIFIED: npm registry]` |
| `@testing-library/react` | npm | 2026-01-19 | 44.3M | github.com/testing-library/react-testing-library | OK | Approved `[VERIFIED: npm registry]` |
| `jsdom` | npm | 2026-04-30 | 62.0M | github.com/jsdom/jsdom | OK | Approved `[VERIFIED: npm registry]` |
| `@vitejs/plugin-react-swc` | npm | 2026-05-14 | 12.4M | github.com/vitejs/vite-plugin-react | OK | Approved (alternative, not recommended default) `[VERIFIED: npm registry]` |
| `@types/react`, `@types/react-dom` | npm | 2026-06 / 2025-11 | 106M / 86.6M | github.com/DefinitelyTyped/DefinitelyTyped | OK | Approved `[VERIFIED: npm registry]` |
| `vite` | npm | 2026-07-09 | 117.2M | github.com/vitejs/vite | SUS ("too-new") | **Flagged, human-verify** — see note below |
| `react-router` | npm | 2026-07-08 | 38.8M | github.com/remix-run/react-router | SUS ("too-new") | **Flagged, human-verify** — see note below |
| `react-router-dom` | npm | 2026-06-29 | 41.7M | github.com/remix-run/react-router | SUS ("too-new") | Not recommended (superseded by `react-router` — see State of the Art) |
| `@tanstack/react-query` | npm | 2026-06-27 | 56.2M | github.com/TanStack/query | SUS ("too-new") | **Flagged, human-verify** — see note below |
| `tailwindcss` | npm | 2026-06-29 | 97.8M | github.com/tailwindlabs/tailwindcss | SUS ("too-new") | **Flagged, human-verify** — see note below (already locked by UI-SPEC regardless) |
| `shadcn` | npm | 2026-07-03 | 5.0M | github.com/shadcn-ui/ui | SUS ("too-new") | **Flagged, human-verify** — see note below (already locked by UI-SPEC) |
| `@vitejs/plugin-react` | npm | 2026-06-23 | 55.3M | github.com/vitejs/vite-plugin-react | SUS ("too-new") | **Flagged, human-verify** — see note below |
| `@tailwindcss/vite` | npm | 2026-06-29 | 38.2M | github.com/tailwindlabs/tailwindcss | SUS ("too-new") | **Flagged, human-verify** — see note below |
| `lucide-react` | npm | 2026-07-09 | 69.7M | github.com/lucide-icons/lucide | SUS ("too-new") | **Flagged, human-verify** — see note below |
| `vitest` | npm | 2026-07-06 | 72.7M | github.com/vitest-dev/vitest | SUS ("too-new") | **Flagged, human-verify** — see note below |
| `msw` | npm | 2026-07-08 | 18.1M | github.com/mswjs/msw | **SLOP** ("too-new" + "suspicious-postinstall") | **REMOVED** — see note below |

**Note on the "too-new" SUS cluster:** every package above flagged `SUS` solely
for `too-new` is a top-tier, multi-million-download-per-week package from a
well-known maintainer org (Vite core team, Remix/React Router team, TanStack,
Tailwind Labs, shadcn, vitest-dev), each with weekly download counts between
12M and 157M. The heuristic is keying off *latest version publish date*, not
package registration age — these are all fast-releasing, actively-maintained
projects, not new/hallucinated packages. This reads as a heuristic false
positive against high-velocity release cadence, not a legitimacy concern. Per
protocol these are still tagged `SUS` and the planner must add a
`checkpoint:human-verify` task before the corresponding install step — treat
that checkpoint as a quick sanity glance (confirm the package name and repo
URL match what's written here), not a deep audit.

**Packages removed due to `[SLOP]` verdict:** `msw`. Flagged for both
"too-new" (same false-positive pattern as above — 18.1M weekly downloads,
official `mswjs` org) and "suspicious-postinstall" (its postinstall script
registers the `mockServiceWorker.js` service worker file, which is MSW's
well-documented normal setup step, not obfuscated network/filesystem access).
Removed from all recommendations per protocol regardless; if a later phase
wants MSW, it must re-run this legitimacy check and get explicit human
sign-off given the postinstall flag.

**Packages flagged as suspicious `[SUS]`:** `vite`, `react-router`,
`react-router-dom`, `@tanstack/react-query`, `tailwindcss`, `shadcn`,
`@vitejs/plugin-react`, `@tailwindcss/vite`, `lucide-react`, `vitest` — the
planner must insert a `checkpoint:human-verify` task before each corresponding
install step (can be one combined checkpoint before the `npm install`/`npx
shadcn init` task, since they install together).

## Architecture Patterns

### System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│ Browser (Vite-built SPA, no SSR)                                       │
│                                                                          │
│  URL entry / deep link                                                 │
│        │                                                                │
│        ▼                                                                │
│  ┌───────────────────┐   nested under   ┌─────────────────────────┐    │
│  │ createBrowserRouter│ ───────────────▶ │ Root layout (app bar)    │    │
│  │ route table        │                  │  └─ Outlet               │    │
│  └───────────────────┘                  └────────────┬────────────┘    │
│                                                         │                │
│                     ┌───────────────────────┬──────────┴─────────┐      │
│                     ▼                       ▼                    ▼      │
│              Home ( / )          ScenarioLayout (/scenarios/:id/*)      │
│           (scenario list          ┌─ Editor tab (placeholder)           │
│            + create dialog)       ├─ Runs tab   (placeholder)           │
│                     │              └─ Results tab (placeholder)         │
│                     ▼                                                    │
│        TanStack Query hooks (useScenarios, useFixtures,                 │
│        useCreateScenario) — own loading/error/cache state                │
│                     │                                                    │
│                     ▼                                                    │
│        Typed client (openapi-fetch + generated schema)                  │
│                     │                                                    │
│                     ▼                                                    │
│        On query/mutation error → ErrorBanner (SHELL-04),                │
│        never a blank screen; render crash → error boundary backstop     │
└──────────────────────────────┼───────────────────────────────────────────┘
                                 │ fetch() — real cross-origin request
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│ FastAPI backend (unchanged except CORSMiddleware, added first in app.py) │
│                                                                          │
│   GET  /fixtures         → list *.json in ROSTERAI_DATA_DIR              │
│   POST /scenarios        → 400 unknown fixture | 422 validation | 201    │
│   GET  /scenarios        → list, newest-first                            │
│   GET  /scenarios/{id}   → 404 | 200  (not called by Phase 1 UI, but      │
│                              still behind the same CORS gate)             │
└──────────────────────────────┬───────────────────────────────────────────┘
                                 ▼
                        SQLite (WAL) — `scenarios` table
```

### Recommended Project Structure
```
frontend/
├── src/
│   ├── api/
│   │   ├── schema.d.ts        # generated by openapi-typescript — regenerate via npm script, do not hand-edit
│   │   ├── client.ts          # openapi-fetch instance; baseUrl from VITE_API_BASE_URL
│   │   └── scenarios.ts       # thin typed wrapper fns consumed by hooks (listScenarios, createScenario, listFixtures)
│   ├── hooks/
│   │   ├── useScenarios.ts    # useQuery(['scenarios'], ...)
│   │   ├── useFixtures.ts     # useQuery(['fixtures'], ...)
│   │   └── useCreateScenario.ts  # useMutation + query invalidation
│   ├── components/
│   │   ├── ui/                # shadcn-generated primitives (button.tsx, input.tsx, select.tsx, dialog.tsx, table.tsx, alert.tsx, tabs.tsx)
│   │   ├── layout/             # AppBar.tsx, ScenarioTabs.tsx, ErrorBanner.tsx, PlaceholderView.tsx
│   │   └── scenarios/           # ScenarioTable.tsx, CreateScenarioDialog.tsx
│   ├── routes/                   # Home.tsx, ScenarioLayout.tsx, EditorPlaceholder.tsx, RunsPlaceholder.tsx, ResultsPlaceholder.tsx
│   ├── lib/
│   │   ├── utils.ts             # cn() — shadcn's clsx+tailwind-merge helper
│   │   └── env.ts               # typed accessor for import.meta.env.VITE_API_BASE_URL
│   ├── App.tsx                   # router table (createBrowserRouter)
│   ├── main.tsx                  # QueryClientProvider + RouterProvider mount
│   └── index.css                  # `@import "tailwindcss";` — no separate config file
├── vite.config.ts                  # react() + tailwindcss() plugins, `@` alias
├── tsconfig.json / tsconfig.app.json / tsconfig.node.json
├── components.json                  # shadcn config (style: new-york, base: neutral)
├── .env.example                      # VITE_API_BASE_URL=http://127.0.0.1:8000
└── package.json
```

### Pattern 1: Codegen'd typed client, thin hand-written wrappers
**What:** Run `openapi-typescript` against the backend's own OpenAPI schema to
produce `paths`/`components` types, then use `openapi-fetch`'s `createClient`
for the actual HTTP calls. Hand-write only thin per-resource functions
(`listScenarios()`, `createScenario(body)`) that call the typed client — never
hand-write the request/response *shapes* themselves.
**When to use:** Every endpoint this phase (or any later phase) consumes.
**Example:**
```bash
# Generate schema without needing a running server — export FastAPI's own schema:
cd backend
uv run python -c "import json; from api.main import app; print(json.dumps(app.openapi()))" > ../frontend/openapi.json
cd ../frontend
npx openapi-typescript ./openapi.json -o ./src/api/schema.d.ts
```
```typescript
// Source: Context7 /openapi-ts/openapi-typescript — openapi-fetch/index.md
import createClient from "openapi-fetch";
import type { paths } from "./schema";

export const client = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_BASE_URL,
});
```
```typescript
// src/api/scenarios.ts — thin wrapper, no hand-written shapes
import { client } from "./client";

export async function listScenarios() {
  const { data, error } = await client.GET("/scenarios");
  if (error) throw error;
  return data;
}

export async function createScenario(body: { name: string; fixture: string }) {
  const { data, error, response } = await client.POST("/scenarios", { body });
  if (error) throw { status: response.status, ...error };
  return data;
}
```
**Why this satisfies SHELL-02's letter, not just its spirit:** `docs/API.md`
and the generated schema both derive from the same FastAPI route/Pydantic
definitions — as long as the backend and its OpenAPI schema stay in sync (which
FastAPI guarantees automatically), the generated types can never silently
diverge from what `docs/API.md` documents. If `docs/API.md` and the generated
schema ever *do* disagree, that is itself a signal the doc has gone stale
again — the codegen path structurally can't be the one that's wrong.

### Pattern 2: Data router with a scenario-scoped layout route
**What:** `createBrowserRouter` with a root layout (persistent app bar) and a
nested `ScenarioLayout` route under `/scenarios/:scenarioId` that renders the
persistent tab nav (Editor/Runs/Results) and an `<Outlet />` for whichever tab
is active.
**When to use:** SHELL-03's four-route shell, exactly as specified in
`01-UI-SPEC.md`'s Application Structure section.
**Example:**
```tsx
// Source: Context7 /remix-run/react-router — docs/start/data/routing.md, adapted to this phase's route map
import { createBrowserRouter } from "react-router";
import { RouterProvider } from "react-router/dom";

const router = createBrowserRouter([
  {
    path: "/",
    Component: RootLayout,          // persistent app bar
    children: [
      { index: true, Component: Home },
      {
        path: "scenarios/:scenarioId",
        Component: ScenarioLayout,   // persistent Editor/Runs/Results tab nav
        children: [
          { index: true, Component: EditorPlaceholder },
          { path: "runs", Component: RunsPlaceholder },
          { path: "runs/:runId", Component: ResultsPlaceholder },
        ],
      },
    ],
  },
]);
```
Note the route map above nests `ScenarioEditor` at the index (`/scenarios/:id`)
rather than `/scenarios/:id/editor` — this matches `01-UI-SPEC.md`'s exact
route table (`/`, `/scenarios/:scenarioId`, `/scenarios/:scenarioId/runs`,
`/scenarios/:scenarioId/runs/:runId`); do not introduce an `/editor` segment
that UI-SPEC didn't specify.

### Pattern 3: TanStack Query for every server read/write, from Phase 1 on
**What:** Every `GET`/`POST` call this phase makes goes through `useQuery` /
`useMutation`, never raw `fetch` + `useState`.
**When to use:** `useScenarios()`, `useFixtures()` (queries); `useCreateScenario()`
(mutation, invalidates the `['scenarios']` query key on success so the new row
appears without a manual refetch).
**Example:**
```tsx
// Source: Context7 /tanstack/query — docs/framework/react/overview.md, adapted
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listScenarios, createScenario } from "../api/scenarios";

export function useScenarios() {
  return useQuery({ queryKey: ["scenarios"], queryFn: listScenarios });
}

export function useCreateScenario() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createScenario,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scenarios"] }),
  });
}
```

### Anti-Patterns to Avoid
- **Hand-typing request/response shapes from `docs/API.md`:** works today,
  silently drifts tomorrow — this is the exact failure class that produced the
  `93ca4e0` doc-sync commit. Generate types instead (Pattern 1).
- **A Vite dev proxy for `/api`:** hides CORS misconfiguration until the first
  real deploy; Phase 1's own success criterion requires the CORS path to be
  verified for real. Configure `VITE_API_BASE_URL` to the backend's real origin
  in dev too.
- **Flat global nav links to all four views:** `Editor`/`Runs`/`Results` are
  meaningless without a `:scenarioId` — UI-SPEC deliberately scopes them under
  the scenario layout route, not the root nav. Don't "simplify" this into four
  flat top-level links.
- **`react-router-dom` from muscle memory:** still installable and not
  deprecated on the registry, but the library's own current docs name
  `react-router` as the install target with `RouterProvider` from
  `react-router/dom`. Installing `react-router-dom` out of habit works but
  pulls an extra, now-secondary package.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| API request/response typing | Hand-authored `interface`s mirroring `docs/API.md` | `openapi-typescript` + `openapi-fetch` | Removes an entire documented drift class (see Pattern 1) |
| Client-side routing + deep linking | A hand-rolled `switch (location.pathname)` router | `react-router`'s `createBrowserRouter` | Handles nested layouts, `:param` extraction, and browser history correctly; a hand-rolled router will eventually re-derive all of this |
| Server state (loading/error/cache/refetch) | `useState` + `useEffect` + manual `AbortController` | `@tanstack/react-query` | Directly serves Phase 3's polling need too — see CONTEXT.md's discretion analysis |
| Tailwind class merging / conditional variants | String-concatenation `className` logic | shadcn's `cn()` (`clsx` + `tailwind-merge`) | Auto-installed with the first `shadcn add`; hand-rolling variant logic reintroduces exactly what CVA + `cn()` solve |
| CORS header logic | Custom Starlette middleware checking `Origin` against an allowlist | `fastapi.middleware.cors.CORSMiddleware` | Battle-tested, handles preflight `OPTIONS` correctly; a hand-rolled version is a well-known way to accidentally reflect `*` with credentials enabled |

**Key insight:** every "don't hand-roll" in this table maps to a genuinely
easy-to-get-subtly-wrong problem (CORS preflight edge cases, route param
extraction, cache invalidation timing) where the standard library's test
coverage vastly exceeds anything worth writing for a phase this size.

## Common Pitfalls

### Pitfall 1: CORS origins are read once at process startup, not per-request
**What goes wrong:** `backend/settings.py`'s `default_settings()` docstring
promises "read fresh each call so env overrides apply at runtime" — true for
every other setting, but `app.add_middleware(CORSMiddleware, ...)` runs once
at module import time (`api/main.py`). Changing `CORS_ORIGINS` in the
environment after the app has started (or in a test that imports `api.main`
before setting the env var) has no effect until the process restarts / module
re-imports.
**Why it happens:** Middleware registration is a one-time app-construction
step; `Settings` re-reads env on every *call* to `default_settings()`, but
`add_middleware` only calls it once, at import time.
**How to avoid:** Treat this as a conscious, commented tradeoff (not a bug) —
add a one-line comment at the `add_middleware` call site noting CORS origins
are fixed at process start. For tests, follow the existing pattern already
used in `backend/tests/test_api.py`: set the env var via `monkeypatch.setenv`
*before* importing `from api.main import app`, inside the test fixture — this
already works correctly for exactly this reason.
**Warning signs:** A test that sets `CORS_ORIGINS` mid-test (after `app` is
already imported at module scope) and expects the new origin to be allowed
will fail silently-confusingly (CORS headers just won't appear, no exception).

### Pitfall 2: Wildcard origins + credentials is a footgun this app can sidestep entirely
**What goes wrong:** `CORSMiddleware(allow_origins=["*"], allow_credentials=True)`
is rejected by browsers at runtime (a wildcard-with-credentials combination is
invalid per the Fetch spec) — a classic source of "CORS works in Postman/curl
but fails in the browser" confusion.
**Why it happens:** Copy-pasting a generic CORS tutorial snippet without
noticing `allow_credentials` defaults to `False` and this app has no reason to
set it `True`.
**How to avoid:** D-02 (no auth) means this app never sends cookies or
`Authorization` headers that require `allow_credentials=True`. Leave it at its
default `False`, and use a real, explicit, env-configurable allow-list for
`allow_origins` (never `"*"`) per D-04's "configurable, not hardcoded"
requirement. An explicit list is also just better practice regardless of the
credentials question.
**Warning signs:** A `TypeError`-free but browser-console CORS error that
doesn't reproduce via `curl -H "Origin: ..."`.

### Pitfall 3: React Router v6-era tutorials name the wrong install package
**What goes wrong:** Following a `react-router-dom` v6 tutorial (still the
majority of search results by volume) when the current recommended install
target and import path have changed.
**Why it happens:** `react-router-dom` is not deprecated and still works —
there's no hard error to catch this at compile time, just a stale-but-valid
package choice.
**How to avoid:** `npm install react-router` (not `-dom`); `RouterProvider`
comes from `react-router/dom`, everything else (`createBrowserRouter`,
`useLoaderData`, `Outlet`, etc.) comes from `react-router` directly. [CITED:
context7 /remix-run/react-router]
**Warning signs:** `package.json` listing both `react-router` and
`react-router-dom` — a sign of confusion mid-migration.

### Pitfall 4: Tailwind v4 setup instructions from v3-era memory
**What goes wrong:** Manually creating a `tailwind.config.js` with a `content:
[...]` glob and wiring PostCSS by hand — the standard v3 setup, no longer how
v4 works.
**Why it happens:** Tailwind v3 muscle memory; most existing StackOverflow/blog
content still documents the v3 flow.
**How to avoid:** v4 (already locked by UI-SPEC via the shadcn Vite installer)
uses the `@tailwindcss/vite` plugin in `vite.config.ts` plus a single
`@import "tailwindcss";` line in `index.css` — no `tailwind.config.js`, no
`content` glob, no PostCSS config file needed by default. [CITED: context7
/shadcn-ui/ui — apps/v4/content/docs/installation/vite.mdx]
**Warning signs:** A `postcss.config.js` and `tailwind.config.js` appearing in
`git status` after `shadcn init` — they shouldn't, for the default v4 Vite path.

### Pitfall 5: CORS errors and "backend is down" are indistinguishable to `fetch`
**What goes wrong:** Building a "CORS blocked" error message distinct from a
"network unreachable" message — `fetch()` cannot tell these apart; both throw
a generic `TypeError: Failed to fetch` with no further detail.
**Why it happens:** Browsers deliberately withhold CORS-failure specifics from
JS for security reasons (an attacker page shouldn't learn *why* a
cross-origin request failed).
**How to avoid:** Already resolved in `01-UI-SPEC.md`'s Copywriting Contract —
the "Can't reach the ShiftMind API..." banner text is deliberately
non-diagnostic. Do not try to build origin-detection logic to differentiate
these cases; it cannot work reliably and the UI-SPEC explicitly calls out that
over-claiming here would itself be dishonest.
**Warning signs:** A PR that adds `try { ... } catch (e) { if (e.message.includes('CORS')) ... }`
— `fetch` errors don't reliably carry a distinguishable `'CORS'` substring across browsers.

## Code Examples

### CORS wiring following the existing `settings.py` pattern
```python
# Source: backend/settings.py pattern (read directly), extended per BE-01 / D-04
# settings.py — add a field + env var, same shape as every other Settings field
cors_origins: tuple[str, ...] = field(default=())

# default_settings() — same fresh-per-call read as every other field
cors_origins_raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
cors_origins = tuple(o.strip() for o in cors_origins_raw.split(",") if o.strip())
```
```python
# api/main.py — insert directly after app creation, before include_router calls
# NOTE: CORS origins are resolved once here, at process/import time — unlike
# every other Settings field, they do NOT change without a process restart.
# This mirrors CORSMiddleware's own one-time registration; see RESEARCH.md
# "Common Pitfalls" #1.
from fastapi.middleware.cors import CORSMiddleware
from api.deps import get_settings

app = FastAPI(title="ShiftMind API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().cors_origins),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    # allow_credentials intentionally left at its default False — D-02 (no
    # auth) means no cookie/Authorization-header requests ever need it, and
    # combining a real origin allow-list with credentials=True is unnecessary
    # surface area to reason about.
)
```
```python
# Test — follows the exact env-before-import pattern already used in test_api.py
def test_cors_reflects_configured_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("ROSTERAI_DB", str(tmp_path / "test.db"))
    from api.main import app
    with TestClient(app) as client:
        resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
        assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"

        resp2 = client.get("/health", headers={"Origin": "http://evil.example"})
        assert "access-control-allow-origin" not in resp2.headers
```
[ASSUMED — the exact CORSMiddleware response-header behavior on a disallowed
origin (silently omitting the header rather than erroring) follows Starlette's
documented reflect-only-if-matched behavior; not independently re-verified
against the installed Starlette version this session.]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `npm install react-router-dom`, `<BrowserRouter><Routes><Route>` | `npm install react-router`, `createBrowserRouter` + `RouterProvider` (from `react-router/dom`) | React Router's v7 unification (react-router-dom absorbed into react-router as the primary package); current major verified 8.2.0 on npm 2026-07-16 | Tutorials/StackOverflow answers referencing `react-router-dom` v6 are still functionally valid but no longer the maintainers' recommended install path |
| Tailwind v3: `tailwind.config.js` + `content: [...]` glob + PostCSS | Tailwind v4: `@tailwindcss/vite` plugin + `@import "tailwindcss";`, zero-config content detection | Tailwind v4 GA | No config file to keep in sync with new source paths; fewer moving parts for this phase's greenfield setup |
| `shadcn-ui` npm package (`npx shadcn-ui@latest init`) | `shadcn` npm package (`npx shadcn@latest init`) | Package renamed; `shadcn-ui` is frozen at 0.9.5 on the registry while `shadcn` is actively released (verified 4.13.0) | Already correctly reflected in `01-UI-SPEC.md`; flagging here so the planner doesn't "correct" it back to the old name from stale training data |

**Deprecated/outdated:**
- `react-router-dom` as the primary install: not deprecated, still works, but
  superseded as the recommended entry point.
- Tailwind v3 `content` glob configuration: not applicable under the v4 Vite
  plugin path this project uses.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Vite's `import.meta.env.VITE_*` convention applies as expected for `VITE_API_BASE_URL` (standard Vite behavior, not independently re-confirmed via Context7 this session) | Recommended Project Structure, Code Examples | Low — this is extremely well-established Vite behavior; if wrong, the env var simply wouldn't be exposed to client code and would fail loudly at first `import.meta.env` access, not silently |
| A2 | `CORSMiddleware`'s behavior on a disallowed `Origin` is to omit `access-control-allow-origin` from the response rather than return an error status | Code Examples (CORS test) | Low-Medium — if the actual behavior differs (e.g. it still allows the request through without CORS headers, which the browser then blocks client-side), the exact test assertion may need adjusting, but the CORS *behavior itself* (browser blocks unlisted origins) is unaffected |
| A3 | `npm create vite@latest frontend -- --template react-ts` scaffolds a default ESLint config sufficient for this project (no additional lint tooling recommended) | Standard Stack | Low — worst case, planner/executor adds a lint step later; no functional risk to this phase's requirements |

## Open Questions

1. **Should the generated `schema.d.ts` be committed to git or regenerated on install?**
   - What we know: `openapi-typescript` output is deterministic given the same backend schema; committing it makes the repo self-contained (no need to run the backend to typecheck the frontend) but means it can go stale if someone changes a backend route without regenerating.
   - What's unclear: whether this project wants a CI check that regeneration matches the committed file (drift guard) or just trusts developer discipline.
   - Recommendation: commit it (keeps `npm install && npm run build` working without a running backend — important for the "builds to static assets with one command" criterion), and add an `npm run codegen` script the planner should wire as a documented manual step after any backend schema change. A CI drift-check is a reasonable Phase 2+ follow-up, not required for Phase 1's criteria.

2. **Exact CORS_ORIGINS default value for local dev.**
   - What we know: Vite's default dev server port is `5173`; `vite preview` (serving the built `dist/`) defaults to `4173`.
   - What's unclear: whether the planner wants both ports in the default `CORS_ORIGINS`, or just the dev-server port, with `preview` left to be added explicitly when needed.
   - Recommendation: default `CORS_ORIGINS=http://localhost:5173,http://localhost:4173` in `.env.example` so both `npm run dev` and `npm run preview` work against the backend without extra config — cheap to include both, and criterion 5 ("app builds to static assets with one command") implies `preview` should also work.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|--------------|-----------|---------|----------|
| Node.js | Frontend scaffold, build, dev server | Yes | v22.22.0 | — |
| npm | Package install, `npm create vite` | Yes | 10.9.0 | — |
| uv | Backend dev server (`uv run uvicorn ...`), OpenAPI export script | Yes | 0.10.8 | — |
| Python | Backend | Yes | 3.10.9 / 3.12.10 both present | — |
| git | Version control | Yes | 2.45.1 | — |
| `frontend/` directory | This phase's entire deliverable | No (does not exist yet) | — | Created by this phase's scaffold task — expected, not a gap |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None — `frontend/` not existing yet is
the expected greenfield starting state for this phase, not an environment gap.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Backend framework | pytest (existing) — `backend/pyproject.toml` `[tool.pytest.ini_options]`, `testpaths = ["tests"]` |
| Backend quick run | `cd backend && uv run pytest tests/test_cors.py -x` (new file this phase adds) |
| Backend full suite | `cd backend && uv run pytest` (excludes `-m live` by default per existing `addopts`) |
| Frontend framework | none yet — recommend Vitest (verified 4.1.10) + `@testing-library/react` (16.3.2) + `jsdom` (29.1.1), all `[VERIFIED: npm registry]` OK-verdict, paired with Vite by convention |
| Frontend config file | none yet — add a `test` block to `vite.config.ts` (Vitest reads Vite config natively) |
| Frontend quick run | `cd frontend && npx vitest run <file>` |
| Frontend full suite | `cd frontend && npx vitest run` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|--------------------|-------------|
| BE-01 | Configured origin gets CORS headers; other origins don't | unit (pytest) | `uv run pytest tests/test_cors.py -x` | ❌ Wave 0 |
| SHELL-01 | `npm run build` produces static assets without error | smoke (manual-only) | `npm run build` (exit code 0) | N/A — build success is not a unit-testable behavior; verified by command exit code at execution/verify time |
| SHELL-02 | Generated client types compile; wrapper fns call correct paths | typecheck + unit | `npx tsc --noEmit` + `npx vitest run src/api/scenarios.test.ts` | ❌ Wave 0 |
| SHELL-03 | Deep link to each of the 4 routes mounts the correct component | component (Vitest + Testing Library) | `npx vitest run src/routes/router.test.tsx` | ❌ Wave 0 |
| SHELL-04 | Fetch failure renders the exact backend-unreachable banner copy, not a blank screen | component | `npx vitest run src/components/layout/ErrorBanner.test.tsx` | ❌ Wave 0 |
| SCEN-01 | Populated / empty / loading / error list states render per UI-SPEC | component | `npx vitest run src/components/scenarios/ScenarioTable.test.tsx` | ❌ Wave 0 |
| SCEN-02 | Create dialog: disabled-until-valid, submit success appends row, 400/422 render inline errors | component | `npx vitest run src/components/scenarios/CreateScenarioDialog.test.tsx` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** the single relevant test file's quick command (backend
  `pytest tests/test_cors.py -x`, or frontend `vitest run <file>`).
- **Per wave merge:** full backend suite (`uv run pytest`) + full frontend
  suite (`vitest run`).
- **Phase gate:** both full suites green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `backend/tests/test_cors.py` — covers BE-01, following the existing
  env-before-import fixture pattern from `test_api.py`.
- [ ] `frontend/vitest.config.ts` (or a `test` block merged into
  `vite.config.ts`) + `frontend/src/test/setup.ts` (jest-dom matchers,
  `@testing-library/jest-dom`) — framework install: `npm install -D vitest
  @testing-library/react @testing-library/jest-dom jsdom` (all `[VERIFIED: npm
  registry]`, OK verdict).
- [ ] A test-only mock helper for the typed client (`vi.mock('../api/client')`
  or per-function `vi.fn()` stubs) — replaces the MSW path this research
  explicitly avoided (see Package Legitimacy Audit).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|-------------------|
| V2 Authentication | No | D-02 — explicitly out of scope for v0.4 |
| V3 Session Management | No | No sessions exist |
| V4 Access Control | No | D-02 — every scenario is globally visible by design; not a gap this phase introduces or must close |
| V5 Input Validation | Yes | Client mirrors server validation for UX (name non-empty, fixture from the `GET /fixtures` list only — never free text) but the server (`ScenarioCreate` Pydantic model, `Field(min_length=1)`) remains the actual source of truth; client-side checks are never trusted as the security boundary |
| V6 Cryptography | No | Not applicable — no secrets handled client-side |
| V7 Error Handling & Logging | Yes | Never render raw exception text, stack traces, or raw backend `detail` strings for unexpected (5xx/network) failures to the user — use the fixed, non-diagnostic copy from `01-UI-SPEC.md`'s Copywriting Contract. Known 4xx `detail` strings (400 unknown fixture, 422 validation) are already safe, structured, non-sensitive text and may be reflected inline per UI-SPEC. |
| V9 Communications | Yes | `CORSMiddleware` allow-list (never `"*"`), no unnecessary `allow_credentials=True` (see Common Pitfalls #2) |
| V14 Configuration | Yes | `CORS_ORIGINS` configurable via env var (BE-01/D-04), not hardcoded; matches the existing `settings.py` fresh-per-call pattern for every other config field (with the one documented exception — see Common Pitfalls #1) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| CORS misconfiguration (wildcard origin, or wildcard + credentials) | Tampering / Information Disclosure | Explicit env-configured origin allow-list; `allow_credentials` left at default `False` (see Code Examples) |
| Reflected/leaked backend internals in an error surface | Information Disclosure | Fixed, non-diagnostic copy for unexpected failures (UI-SPEC Copywriting Contract); never render `error.stack` or a raw caught exception's `.message` for unhandled cases |
| XSS via unescaped user-supplied scenario name | Tampering | React's default JSX text-node escaping is sufficient — the scenario `name` field is only ever rendered as JSX children, never via `dangerouslySetInnerHTML`. No sanitization library needed; just don't introduce `dangerouslySetInnerHTML` for user data anywhere in this phase's components. |
| Overly broad CORS allow-list masking the "no auth" risk already documented in `PROJECT.md` | Information Disclosure / Elevation of Privilege | Already an accepted, explicitly-documented risk (PROJECT.md "v0.4 key context" #1 — "handle later"); this phase's obligation is only to keep the CORS allow-list to the actual dev/build origins, not `"*"`, so the exposure doesn't silently widen beyond what's already accepted |

## Sources

### Primary (HIGH confidence)
- Live codebase reads: `backend/settings.py`, `backend/api/main.py`,
  `backend/api/deps.py`, `backend/api/schemas.py`,
  `backend/api/routers/{fixtures,scenarios}.py`, `backend/tests/test_api.py`,
  `backend/pyproject.toml` — read directly this session.
- `docs/API.md` — read directly; confirmed as the authoritative contract per
  `01-CONTEXT.md`'s canonical-refs instruction.
- npm registry (`npm view <pkg> version`) — live query, 2026-07-16, for every
  version cited above.
- `gsd-tools query package-legitimacy check` — live query, 2026-07-16, full
  results in Package Legitimacy Audit.

### Secondary (MEDIUM confidence)
- Context7 `/remix-run/react-router` — install-package guidance,
  `createBrowserRouter`/`RouterProvider` API, nested route config.
- Context7 `/tanstack/query` (`/tanstack/query`) — `useQuery`/`useMutation`,
  `refetchInterval` polling patterns, `QueryClientProvider` setup.
- Context7 `/openapi-ts/openapi-typescript` — codegen CLI usage,
  `openapi-fetch` client creation and typed request/response pattern.
- Context7 `/fastapi/fastapi` — `CORSMiddleware` configuration, default
  `allow_credentials`/`allow_methods` values, wildcard+credentials constraint.
- Context7 `/vitejs/vite` — scaffold command, `server.proxy` (evaluated and
  rejected — see Alternatives Considered), build output structure.
- Context7 `/shadcn-ui/ui` — init CLI flags (cross-checked against
  `01-UI-SPEC.md`'s already-pinned params), Tailwind v4 Vite setup
  (`@tailwindcss/vite`, `@import "tailwindcss"`, `@` path alias wiring).

### Tertiary (LOW confidence)
- None used as the basis for a recommendation — all package-existence claims
  were cross-checked against the live npm registry rather than left as
  training-data assertions.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every package version was live-queried against npm on
  2026-07-16 and its API surface cross-checked against Context7 docs, not
  relied on from training data alone.
- Architecture: HIGH — the route map, layout nesting, and data-flow diagram
  are derived directly from `01-UI-SPEC.md`'s already-locked Application
  Structure section plus `docs/API.md`'s confirmed endpoint contract.
- Pitfalls: HIGH for the CORS-timing and CORS-credentials pitfalls (grounded
  in reading the actual `settings.py`/`api/main.py` source); MEDIUM for the
  React Router / Tailwind v4 naming pitfalls (grounded in Context7 docs, which
  can shift again before this codebase is next touched).

**Research date:** 2026-07-16
**Valid until:** ~30 days for the architecture/pattern guidance (stable);
~7-14 days for exact package versions given this ecosystem's release cadence —
re-verify versions with `npm view <pkg> version` at plan/execute time rather
than trusting the numbers above if this research is more than two weeks old.
