---
title: "ShiftMind Product Brief Addendum"
status: ready-for-review
created: 2026-07-21
updated: 2026-07-21
---

# ShiftMind Product Brief Addendum

This addendum preserves technical context for the PRD and architecture workflows. It does not add MVP scope.

## Current System and Architecture Gaps

| Area | Existing capability | Unresolved implication |
|---|---|---|
| Scheduling | OR-Tools CP-SAT with qualification, availability, shift-to-task linkage, hourly coverage, caps on hours and gaps, and lexicographic optimization that minimizes unmet demand before cost | The model is intentionally distilled and must not be presented as having the fidelity of a production scheduling model. |
| Extensibility | `SchedulerEngine` isolates the pure domain from the solver | Preserve this boundary when agent tools invoke scheduling use cases. |
| LLM integration | Deterministic stub, Gemini, and OpenRouter behind `LLMProvider`, with translation between provider-neutral calls and vendor-specific payloads | The interface is stateless and task-specific; it is not a conversational agent contract. |
| Model safety | Worker/task references and argument ranges are resolved and validated on the server | Current valid constraints persist immediately, without preview or confirmation. |
| Execution | FastAPI, SQLite WAL, and a single-worker executor persist `PENDING -> RUNNING -> COMPLETED/FAILED` | The worker lacks cancellation, progress reporting, restart durability, and multi-process coordination. |
| Reproducibility | Runs persist results and insights | Overrides are mutable scenario JSON, and runs do not fully snapshot the active override set used to produce them. |
| Access control | None | Repository reads are global; authentication, ownership, site scoping, and authorization must be added together. |
| User experience | React/TypeScript UI supports scenarios, constraints, run polling, results, charts, and insights | Conversations, tool results, confirmation state, audit history, input upload, and what-if comparison are absent. |
| Quality | Deterministic offline tests and numeric grounding for insights | The agent needs evaluation coverage for tool choice, arguments, authorization, grounding, and multi-step completion. |

## Agent Runtime Contract

[ASSUMPTION] Preserve the existing task-specific `LLMProvider` methods for compatibility and introduce a separate conversational `AgentModel`. An application-owned `AgentService` controls the loop:

```text
Chat API
  -> AgentService
       -> context loader
       -> AgentModel
       -> typed tool registry
       -> authorization and risk policy
       -> confirmation state
       -> application-service tool executor
       -> append-only audit recorder
  -> scheduling and query services
  -> CP-SAT worker
```

The model never receives a general repository or SQL tool. Each agent tool exposes a narrow application use case with JSON-schema input, required permission, risk class, validation, and a structured result. Actor and site identity come from the authenticated server context, never from model-generated arguments.

Candidate tools include scenario summary, coverage-gap inspection, qualified-worker lookup, active-constraint listing, constraint preview and application, run start/status, and run comparison. The PRD should select the final set around one demonstrable job rather than a target tool count.

Execution invariants:

- Persist conversations, messages, turns, proposed calls, confirmations, results, and audit events.
- Treat confirmation as authorization over an exact proposal and scenario version; stale proposals must be regenerated.
- Bound each turn by tool-call count, elapsed time, and token or cost limits.
- Return durable job identifiers for long-running tools and resume from persisted state instead of holding an HTTP request open.
- Snapshot scenario data, active overrides, solver configuration, and relevant tool versions for every run.
- Keep the deterministic model for CI and gate live-provider tests explicitly.

## Identity and Tenancy Boundary

The portfolio MVP needs real access control even with one user:

```text
Organization (future-ready)
  -> DC Site
       -> Membership (one seeded planner in MVP)
       -> Scenario -> immutable Runs
       -> Conversations and Audit Events
```

All repository operations must be scoped using server-derived site context. Adding `site_id` columns or a site selector alone is not isolation. The MVP can disable registration and invitations and enforce one membership while preserving future manager, planner, and viewer roles.

## Architecture-Shaping Open Decisions

- Whether a customer maps to one DC or an organization containing several DC sites.
- Whether to offer shared multi-tenant deployments, dedicated customer deployments, or both.
- Which roles may publish schedules rather than prepare drafts.
- Data-retention, privacy, residency, and model-provider requirements for workforce data.
- Whether MVP authentication is local or integrates with an external identity provider.
- Integration boundaries for workforce-management, HR, demand, and identity systems.
