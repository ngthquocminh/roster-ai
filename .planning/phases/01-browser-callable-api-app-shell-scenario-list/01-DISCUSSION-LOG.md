# Phase 1: Browser-Callable API + App Shell + Scenario List - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-15
**Phase:** 1-Browser-Callable API + App Shell + Scenario List
**Areas discussed:** none — user declined discussion and routed straight to planning

---

## Outcome

Four gray areas were surfaced and presented. The user declined all of them:
**"nothing move on to plan for the phase."**

No implementation decisions were made in discussion. Everything in CONTEXT.md's
`<decisions>` is either locked upstream at milestone scoping (D-01..D-07) or
delegated to Claude's discretion. The four areas below were **presented but not
selected** — they are recorded here so a retrospective can ask whether skipping
them cost anything.

---

## Areas presented (none selected)

| Area | Why it was raised | Disposition |
|---|---|---|
| **API client typing — generated vs hand-written** | SHELL-02 says types mirror `docs/API.md`, but FastAPI auto-serves `/openapi.json`, so codegen is viable. Generated types cannot drift; hand-written ones silently can — and this repo has documented history of exactly that drift (commit `93ca4e0` existed to fix it). | Claude's discretion |
| **Server state & polling strategy** | Raw `fetch` + `useState` vs TanStack Query. Decided in Phase 1 (the client is built here) but the cost lands in Phase 3, which polls run status across ~2min waits. Optimising for Phase 1 alone under-serves Phase 3. | Claude's discretion |
| **CORS shape + Vite dev proxy** | A Vite dev proxy sidesteps CORS in development but hides misconfiguration until first deploy — while Phase 1 criterion 1 requires "no CORS error in the console". Also settles the fresh-per-call vs register-once asymmetry found in `settings.py`. | Claude's discretion |
| **Styling approach** | Tailwind / CSS Modules / plain CSS. Nothing to inherit (repo is 100% Python). Propagates through every view in Phases 2-4 and hosts Phase 4's chart. | Claude's discretion |

---

## Claude's Discretion

All four areas above. The planner owns these choices. CONTEXT.md carries the full
analysis for each so the reasoning is not lost.

---

## Deferred Ideas

None raised — no discussion occurred.

**Todo cross-reference:** `todo.match-phase 1` returned all 8 pending todos (4 at
score 0.9). All were keyword false positives (`scenario`, `api`, `fixtures`,
`backend`); the matcher does not distinguish frontend from backend scope. None
were folded. Rationale per todo is recorded in CONTEXT.md's `<deferred>` section.
Notably, WR-04, input upload, and run cancellation are Out of Scope by explicit
user decisions made earlier the same day — folding them would have re-litigated
locked decisions.
