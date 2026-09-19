# ShiftMind

## A governed AI agent for workforce schedule repair

**In brief.** A planner describes a scheduling change in plain English; an LLM agent turns it into a typed proposal; an OR-Tools CP-SAT solver re-plans the week; the planner approves promotion of the result. The language model has no authority over any step — identity, policy, numbers, approvals, and state all belong to application code. Solo build, roughly four months part-time (first commit 2026-05-30). A portfolio artifact, not a hosted service.

ShiftMind is an AI-assisted workforce-planning workflow for a distribution centre. A planner investigates a weekly scenario in natural language, proposes constraint changes, runs a new optimization, compares it against the current baseline, requests approval, and promotes an approved candidate.

The interesting problem is not adding chat to an optimizer. It is keeping a probabilistic model useful without letting it become a source of record — so the workflow stays inspectable and recoverable when the model is wrong, manipulated, or unavailable.

## Run it

```bash
docker compose up -d --build
```

Open `http://localhost:8080` and sign in through the local fake identity provider. The composed stack uses a keyless deterministic agent model by default, so this journey needs no provider credential, and the fake provider is exposed only when `OIDC_PROVIDER=fake`. Setup, recovery, and configuration details are in [Getting Started](docs/GETTING-STARTED.md); the reviewer journey with real captured output is in [the walkthrough](docs/WALKTHROUGH.md).

## The risks this design targets

- The model invents a number, or cites the wrong scenario version.
- A stale approval promotes the wrong candidate.
- A worker loses its lease mid-solve, then commits anyway.
- Retries duplicate effects; reconnecting clients miss events.
- Prompt injection or untrusted scenario data tries to widen what the model may do.
- A test suite looks green because important tests were quietly skipped.

## The solver

Scheduling is done by **OR-Tools CP-SAT**, and it is the only component that may construct or validate an accepted schedule. CP-SAT has no native lexicographic objective, so the engine uses solve-and-lock: round 1 minimizes unmet labour-hours; that optimum is then locked as a constraint; round 2 minimizes cost, warm-started from the round-1 solution. If round 2 finds nothing in time, the round-1 schedule is returned instead of failing.

Natural-language changes enter the model only as **soft penalty terms in round 2** — minimum-workers shortfall, locked shift, excluded worker, maximum hours. Because coverage is locked first, a request can trade cost but never coverage, and a bad or over-broad request cannot make the solve infeasible.

## How the system is designed

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/authority-boundary-dark.svg">
  <img alt="ShiftMind authority boundary: untrusted planner text, scenario data and conversation history reach the model, which emits only a typed proposal across a trust boundary; on the application side a gate re-derives actor, capability, policy and versions, rejects with a named outcome, and otherwise forwards to a read path (application calculator to grounded answer) or a write path (CP-SAT to immutable candidate to exact-action approval to atomic baseline commit), all over PostgreSQL row-level security." src="docs/assets/authority-boundary-light.svg">
</picture>

*Figure 1 — The authority boundary: how an untrusted model request becomes a governed effect.*

### Authority is partitioned

Three components, three jobs. The **model** interprets language and proposes typed tool calls. The **application** enforces identity, site scope, authorization, policy, versions, budgets, approvals, idempotency, persistence, audit, and workflow state. **CP-SAT** builds the schedule.

Six capability modules are installed through a literal, reviewable registry across five closed risk classes (`inspect`, `draft`, `compute`, `consequential`, `prohibited`). Each declares its contracts, permission, scope, approval policy, timeout, budget, idempotency semantics, and audit and evidence mapping. The model cannot grant itself a tool.

The backend is a hexagonal modular monolith with separate API and worker processes; architecture tests scan for forbidden framework and persistence imports.

### Identity is server-derived

Sign-in is OIDC authorization code with PKCE through a FastAPI backend-for-frontend. Provider tokens stay on the server; the browser holds only a `Secure`/`HttpOnly`/`SameSite` cookie for an opaque session, and unsafe methods also require same-origin plus a CSRF token.

Every request, tool call, job lease, and approval decision **re-resolves actor and site** from the current session. A cross-site lookup returns the same "not found" as a genuinely absent record. Beneath that, PostgreSQL row-level security is `ENABLE` **and** `FORCE` on every tenant table, with least-privilege roles that can neither own a table nor bypass RLS — so an application authorization bug is not a cross-tenant breach.

### Numerical answers fail closed

The model never supplies a trusted number. It proposes a *value-free* claim that references a result produced by an application calculator. The grounding gate then checks that the cited result exists, its metric and arguments match, its scenario version is current, its evidence still resolves and is authorized, and the calculator consumed as many rows as it cited. A zero is accepted only when the calculator proves it consumed zero rows.

Failures are classified across the trust boundary: missing citations and argument mismatches are model failures, inconsistent calculator output is `calculation_failed`, and stale or unauthorized evidence has its own outcome.

### Workflow state is durable and recoverable

Conversations, agent runs, tool calls, schedule runs, approvals, audit records, and events are persisted, and work commits before acknowledgement. The solver runs in a separate worker that leases jobs from PostgreSQL with expiry, heartbeat, and a monotonically increasing **fencing epoch**, so a worker that lost its lease cannot commit an obsolete result.

Schedule inputs and outputs are immutable versions, with a separate baseline pointer naming the accepted one. Commands use scoped idempotency. The event stream carries persisted sequence numbers and supports `Last-Event-ID` replay.

### Approval binds one exact action

Promotion is not a reusable flag. An approval is bound to the actor and site, action type, normalized parameter hash, candidate version, baseline version, consequence-summary hash, policy version, and expiry. On approval the application revalidates those facts and, in one transaction, consumes the approval, moves the baseline pointer, writes audit, and persists the event. If the transaction fails the approval stays pending — there is no "approved but not yet applied" state.

### Untrusted content cannot widen authority

Scenario data, conversation history, and model output are inputs, not instructions, because none of the enforcement points above read them. A successful prompt injection can change what the model *says* or which typed proposal it emits. It cannot grant a permission, forge a citation past the grounding gate, or promote a baseline.

The tool surface is the six installed contracts — no arbitrary SQL, shell, filesystem, credential, or network reach. Budgets for iterations, calls, tokens, retries, wall time, concurrency, and solver duration come from application config, so a manipulated run ends in a stable `budget_exhausted` or `timed_out`. Telemetry excludes prompt, tool, workforce, and schedule content by default, and the adapter discards the provider's hidden reasoning.

### Audit is separate from observability

Business audit is authoritative and unsampled: an append-only `audit_event` written *inside* the business transaction, separating initiating from deciding actor and carrying before-and-after versions, parameter, consequence, and policy hashes, and worker fencing facts. It does not depend on a logger, span exporter, or external service being up. Structured JSON telemetry and OpenTelemetry `gen_ai.*` spans answer different questions and are explicitly not business authority.

### Decisions are traceable within the governed workflow

A site-scoped query joins committed records into a deterministic nine-stage timeline from solver execution through baseline promotion, without recomputing anything, and the React UI renders it. A challenged number can be walked back to the scenario version, the proposed metric, the application-produced result, and its evidence.

The limit is stated plainly: `agent_run` does not yet pin the model identifier or composed-instruction hash, and hidden reasoning is discarded by design. A failure can be *localized* to the model proposal, calculator, evidence, policy, solver, or committed effect, but the exact wording a provider produced cannot be reproduced. This is decision traceability, not full traceability.

## Evaluation

**Deterministic evidence.** The default test path is keyless and network-free, using a PydanticAI `FunctionModel` double while still exercising the real turn-execution and history-rehydration seams. The dataset holds 30 single-turn golden cases and 6 multi-turn cases; multi-turn failure cases record the *expected failure reason*, so an unrelated crash cannot satisfy them. CI fails on minimum pass counts, any skip beyond a fixed budget, any failed or flaky test, and a mismatch between live-marked tests and tests excluded from the default run.

**Live conversation acceptance.** A paid, opt-in suite runs disposable Docker Compose stacks (PostgreSQL, API, worker, web) and drives the authenticated HTTP path with no model doubles. The schedule-repair scenario invokes the real CP-SAT worker and the real approval workflow. Each turn gets two independent checks: application and fixture assertions on facts and effects, and a separately configured LLM judge on relevance, continuity, completeness, and appropriate refusal. **A judge pass can never override a failed fact or effect check.**

The committed evidence records 3 repetitions and 90 evaluated turns, **88 passed**. Both failures are the same disclosed finding — turn B:5 completed *without an answer* in 2 of 3 repetitions — so no false claim, wrong fact, or missing effect was recorded; the failure mode was declining to finish, not asserting something untrue. Coverage is measured against a 135-operation inventory derived from the six capability contracts: 37 live-required (27 observed live; 10 carry a named reason a planner turn cannot reach them, plus the test that covers them instead) and 98 deterministic-only.

## Product surface and stack

The React app covers fixture selection, conversation, scenario data, schedule runs, results, approvals, and the provenance timeline. The API schema is generated from OpenAPI rather than hand-maintained.

- **Backend:** Python, FastAPI, PydanticAI, OR-Tools CP-SAT, PostgreSQL, SQLAlchemy Core, Alembic, pytest
- **Frontend:** React 19, strict TypeScript, Vite, TanStack Query, Tailwind, Radix/shadcn, Vitest, Playwright
- **Runtime:** Docker Compose (PostgreSQL, API, bootstrap, worker, web)

## Limitations and what comes next

Not production-complete. Gate A has recorded readiness evidence; **Gate B has not passed** — the deterministic dataset holds 30 golden cases against a 50-case floor, and the repository deliberately leaves the gate open rather than emitting a report without the required owner rationale.

| Limitation | Next step |
|---|---|
| Single-planner scope: the initiating planner may decide their own approval | Separation of duties; test reassignment, membership revocation, and concurrent decisions |
| Traceability stops at the model boundary | Agent-execution manifest with model and instruction hashes, canonical tool argument/result hashes, human decision rationale |
| Traces are instrumented but not exported; OTel exception events can retain messages | Sanitizing tracer provider, then an OTLP backend — with audit proven to survive exporter failure |
| Local Docker Compose only; latency, reliability, and cost figures are local observations | AWS design exists but stays design work until deployed and measured; no service-level claim until then |

Also open, and listed in the [walkthrough](docs/WALKTHROUGH.md): fixture-only inputs, no retention or audit-search policy, unaggregated logs, three allow-listed persistence imports in application ports, and automated-only accessibility evidence.

## Verification references

- Docs: [walkthrough](docs/WALKTHROUGH.md) · [architecture boundary](docs/ARCHITECTURE.md) · [testing and live acceptance](docs/TESTING.md) · [domain model](docs/DOMAIN-MODEL.md)
- Decisions: the 26 numbered architecture decisions, with adopted/deferred status, live in the [architecture spine](_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md)
- Code: [capability registry](backend/application/capabilities/installed.py) · [grounding gate](backend/application/grounding/gate.py) · [approval decision](backend/application/use_cases/decide_approval.py) · [provenance query](backend/application/queries/decision_provenance.py) · [CP-SAT objective](backend/engine/cpsat/objective.py) · [agent tracing](backend/agent/runtime.py)
- Evidence: [approval and audit invariants](evidence/story-4.5/approval-audit-invariants.json) · [live conversations](evidence/story-5.7/live-conversation-journeys.json) · [CI workflow](.github/workflows/ci.yml)
