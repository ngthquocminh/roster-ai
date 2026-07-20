# Phase 1: Browser-Callable API + App Shell + Scenario List - Context

**Gathered:** 2026-07-15
**Status:** Ready for planning

<domain>
## Phase Boundary

A browser can reach the ShiftMind API, the React app shell exists, and a user can
see and create scenarios against the live backend.

Delivers: CORS on the FastAPI app (the milestone's only backend change), a
Vite + React + TypeScript app under `frontend/`, a typed API client, routing/nav
for the four views, readable error surfacing, and a Home view that lists and
creates scenarios from committed fixtures.

Requirements: BE-01, SHELL-01, SHELL-02, SHELL-03, SHELL-04, SCEN-01, SCEN-02.

Not this phase: scenario detail + NL constraints (Phase 2), run trigger/polling
(Phase 3), results/charts/insights (Phase 4).

</domain>

<decisions>
## Implementation Decisions

The user reviewed the gray areas below and elected not to discuss them —
**"nothing, move on to plan for the phase."** Nothing was decided in discussion;
everything in this section is either (a) already locked upstream at milestone
scoping, or (b) explicitly delegated to Claude. Both are marked as such.

### Locked upstream (milestone scoping, 2026-07-15 — do NOT re-litigate)

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

Four gray areas were surfaced and explicitly delegated. The planner decides;
none were pre-answered by the user. Each carries real analysis worth preserving:

- **API client typing — generated vs hand-written.** SHELL-02 says types mirror
  `docs/API.md`. But FastAPI already auto-serves `/openapi.json`, so types could
  be code-generated from the live schema instead. Weigh: generated types cannot
  drift from the backend; hand-written ones silently can — and this repo has a
  documented history of exactly that drift (the v0.3/v0.4 doc sync, commit
  `93ca4e0`, existed because docs diverged from code). Cost is a codegen step and
  tooling. Note `docs/API.md` is accurate as of `93ca4e0`, so hand-writing from
  it is currently safe; the risk is future drift, not present error.
- **Server state & polling strategy.** Raw `fetch` + `useState`, or TanStack
  Query? Decided here because the client is built in this phase, but the
  consequence lands in **Phase 3**, which must poll run status to terminal across
  waits of up to ~2 minutes. TanStack Query provides `refetchInterval`, caching,
  and loading/error states; raw fetch means hand-rolling all of it later.
  Choosing for Phase 1's needs alone will under-serve Phase 3.
- **CORS shape + Vite dev proxy.** Vite can proxy `/api` → backend in dev, which
  sidesteps CORS entirely during development — but BE-01 still requires real CORS
  for the built origin. Decide: proxy in dev + CORS for prod, or CORS everywhere.
  A dev proxy has a specific hazard here: it hides CORS misconfiguration until
  first deploy, and Phase 1's criterion 1 explicitly requires "no CORS error in
  the console" — verify that against a real cross-origin request, not a proxied
  one.
- **Styling approach.** Tailwind, CSS Modules, or plain CSS. Nothing exists to
  inherit (the repo is entirely Python). This choice propagates through every
  view in Phases 2-4, and Phase 4's chart will sit inside whatever system is
  chosen.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### The API contract (authoritative — read first)
- `docs/API.md` — the complete, accurate HTTP contract. Brought current at commit
  `93ca4e0`; **trust it over any other prose about the API.** Covers every
  endpoint, request/response shape, status codes, and the Configuration section
  (`LLM_PROVIDER`, `ROSTERAI_DB`, `ROSTERAI_DATA_DIR`).
- `docs/API.md` "Endpoints" → `GET /fixtures`, `POST /scenarios`, `GET /scenarios`,
  `GET /scenarios/{scenario_id}` — the four endpoints this phase consumes.
- `docs/API.md` "Status code summary" — note `400` for unknown fixture on
  `POST /scenarios`; that is SHELL-04's error path for this phase.

### Design rationale (the "why")
- `docs/design.md` §2 — whole-system architecture; the two Protocol seams.
- `docs/design.md` §6 — open decisions, incl. "Solve-time vs. optimality" (bears
  on Phase 3, not this one).
- `docs/README.md` — the docs ownership boundary. `docs/` = reference + rationale
  + origin; `.planning/` = planning lifecycle. Do not add phase status to `docs/`.

### Milestone scope
- `.planning/PROJECT.md` "## Current Milestone: v0.4" — target features and the
  **"v0.4 key context — noted for later handling"** table (5 items). That table is
  load-bearing; read it.
- `.planning/REQUIREMENTS.md` — the 24 v1 requirements; this phase owns 7.
- `.planning/ROADMAP.md` "Phase 1" — goal, 5 success criteria, and Notes.

### Origin (context only — NOT a spec)
- `docs/vision.md` — the original idea snapshot. **Frozen and unmaintained.**
  It sketched the four views, but it is not a commitment and is wrong in places
  (it assumed a localStorage session UUID and a Render deploy, neither of which
  happened). Treat as input, never as contract.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`backend/settings.py`** — `Settings` frozen dataclass + `default_settings()`
  reading env fresh per call, with `load_dotenv(backend/.env, override=False)`.
  **BE-01's configurable origins should follow this exact pattern** (add a field +
  an env var, e.g. `CORS_ORIGINS`), not invent a second config mechanism.
- **`backend/.env` / `.env.example`** — established env-config convention from
  quick task 260708-e7z. A new origins var belongs in `.env.example`.

### Established Patterns
- **Config via env with sane defaults**, resolved in `settings.py` and injected
  through the `get_settings` FastAPI dependency (`api/deps.py`).
- **Secrets never in `__repr__`** — `Settings` marks both API keys `repr=False`
  (T-04-01). CORS origins are not secret, but do not weaken this pattern.
- **Python/backend conventions do not transfer** — the repo is 100% Python. There
  is no existing JS/TS lint, format, or naming convention to inherit. `frontend/`
  is genuinely greenfield; the only `package.json` in the repo is `.claude/`'s
  GSD tooling and is unrelated.

### Integration Points
- **`backend/api/main.py`** — small and clean: `app = FastAPI(...)` then five
  `include_router` calls. CORS middleware inserts directly after app creation,
  before the routers. This is the entire footprint of BE-01.
- **⚠️ Tension worth resolving in the plan:** `settings.py`'s docstring says
  settings are *"read fresh each call so env overrides apply at request time."*
  Middleware, however, registers **once** at app creation — so CORS origins are
  read once at startup and will NOT pick up per-request env changes, unlike every
  other setting. This is a real asymmetry. It is fine, but it should be a
  conscious choice with a comment, not an accident, and tests that override env
  per-request (the established test pattern) will not affect CORS.
- **`backend/api/deps.py`** — `get_settings` dependency; where a request-scoped
  read would normally happen.

</code_context>

<specifics>
## Specific Ideas

No specific requirements from discussion — the user declined the gray areas and
delegated them. Standard approaches are acceptable within the locked decisions
above.

One inherited specific worth noting: `docs/vision.md` sketched the Home view as
"scenario list/create". That is the shape SCEN-01/SCEN-02 encode, but vision.md
is a frozen snapshot and not binding on layout.

</specifics>

<deferred>
## Deferred Ideas

None raised in discussion — no discussion occurred.

### Reviewed Todos (not folded)

`todo.match-phase 1` returned **all 8** pending todos, 4 scoring 0.9. Every match
is a **false positive from keyword overlap** (`scenario`, `api`, `fixtures`,
`backend`) — the matcher has no notion of frontend-vs-backend scope. Phase 1 is a
frontend scaffold plus one CORS line; none of these belong to it. Reviewed and
explicitly not folded:

| Todo | Why not folded |
|---|---|
| Harden scenario fixture path against traversal (WR-04) | Out of scope for v0.4 by explicit user decision. v2 `WR-04`. Hard prerequisite for upload (v0.5), not for this phase. |
| Add input upload endpoint | Out of scope by explicit user decision — v0.4 uses the fixture dropdown. v2 `UP-01`. |
| Add per-scenario engine selection | Backend/engine work; unrelated to the app shell. |
| Add run cancellation and concurrency limits | Out of scope by explicit user decision. v2 `OPS-01`. Bears on **Phase 3** (RUN-03 ships an honest "cannot be cancelled" wait), not Phase 1. |
| Extract solver engine into a separate service | Post-POC architecture; unrelated. |
| Add round-2 relative-gap stop | v2 `OPS-02`. Bears on **Phase 3**'s wait, not Phase 1. |
| Tune DEMAND_LOAD and task mix | Engine fixture tuning; cosmetic. Unrelated. |
| Demand deadline-fill scheduling | Engine semantics. Unrelated. |

</deferred>

---

*Phase: 1-Browser-Callable API + App Shell + Scenario List*
*Context gathered: 2026-07-15*
