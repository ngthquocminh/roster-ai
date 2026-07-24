---
title: "ShiftMind Governed Scheduling Agent MVP — Technical Addendum"
status: final
created: 2026-07-21
updated: 2026-07-23
parent_prd: "prd.md"
review_gate: passed
---

# ShiftMind Governed Scheduling Agent MVP — Technical Addendum

This addendum records architecture-shaping mechanisms and implementation guidance. The PRD remains the product contract; substitutions are allowed only when they preserve its observable requirements and invariants.

## 1. Architecture thesis

Use a production-shaped modular monolith with separately runnable API and worker processes. One bounded agent sits at the interpretation/orchestration edge; application code owns identity, site scope, authorization, policy, risk, approval, versioning, budgets, idempotency, persistence, and audit. CP-SAT owns schedule construction and feasibility.

Before the agent runtime is introduced, the web application exposes a read-only Scenario Data viewer over the same application-owned normalized scenario read contract later consumed by agent inspection tools. This makes fixture contents and identifiers independently inspectable, prevents the agent adapter from becoming a second interpretation of source data, and provides a deterministic parity seam for Gate A.

```text
React web / BFF session
          |
     FastAPI API  ---- persisted SSE ----> browser
          |
     AgentRuntime (PydanticAI adapter)
          |
 trusted AgentDeps + typed allow-listed tool gateway
          |
 application services + policy + approval + audit
          |
 PostgreSQL state/jobs  <---- worker ----> CP-SAT
          |
       S3 evidence

JSON stdout -> CloudWatch       sanitized OpenTelemetry -> hosted Logfire
versioned datasets/tests -> Pydantic Evals and CI release gates
```

The recovery boundary is persisted product state, not an HTTP stream, an ECS task, a model SDK, or a Logfire trace.

## 2. Technology decisions

| Concern | Portfolio decision | Boundary or caveat |
|---|---|---|
| Agent runtime | PydanticAI behind ShiftMind-owned `AgentRuntime` | Pin a tested version; framework approval helpers do not authorize actions |
| API/domain | FastAPI, Pydantic, existing Python application services | Tools call use cases, never repositories directly |
| Optimizer | Existing OR-Tools CP-SAT through `SchedulerEngine` | The model cannot create accepted assignments |
| Persistence | PostgreSQL, SQLAlchemy 2, Psycopg 3, Alembic | Replace SQLite before public AWS hosting |
| Async work | PostgreSQL job table and separate application worker | Add SQS/outbox only after measured queue or integration need |
| Browser updates | REST/JSON commands plus persisted SSE replay | Commands remain durable without the stream; use `Last-Event-ID` replay |
| Authentication | Cognito User Pool with application BFF/session boundary | Public sign-up off; map Cognito subject to current membership |
| Evidence | PostgreSQL business records plus checksummed S3 snapshots | Business audit is authoritative and unsampled |
| Agent observability | Hosted Logfire Personal through OpenTelemetry | Optional for correctness; disable prompt/tool content capture by default |
| AWS operations | Structured JSON stdout and CloudWatch logs/alarms | Keep diagnosis available when external telemetry fails |
| Evaluation | Pydantic Evals, pytest, deterministic model doubles, Playwright | Version-controlled datasets and CI gates remain application-owned |
| Infrastructure | Terraform and GitHub Actions OIDC | Immutable images, reviewed plans, no long-lived AWS deploy keys |

### 2.1 Why Logfire is used

Hosted Logfire Personal is appropriate for the portfolio as a convenience observability and evaluation control plane: PydanticAI/FastAPI/database instrumentation, agent/tool traces, token and cost visibility, dashboards, alerts, and Pydantic Evals comparison. It is not self-hosted, not the domain audit trail, and not required for product operation. Its finite quota/retention and external hosting are acceptable only because authoritative evidence remains in PostgreSQL/S3, JSON logs remain in CloudWatch, telemetry content is minimized, and export failure never blocks the workflow. A paid Logfire tier, a different OTLP backend, or Phoenix can be evaluated when collaboration, retention, compliance, or self-hosting requirements become real.

## 3. Agent runtime and tool contract

`AgentRuntime` isolates PydanticAI models, messages, deferred calls, instrumentation, and model-provider configuration. Application-owned state machines and records remain stable across framework changes.

Trusted `AgentDeps` should carry actor ID, site ID, membership/permissions, request and run correlation IDs, database/application-service handles, current resource versions, policy version, clock, and budget—not values supplied by the model.

Each tool declaration includes:

- typed input and output schema;
- read/draft/compute/consequential risk class;
- required permission and site-scoped resource loader;
- expected resource version and idempotency semantics;
- deterministic preconditions and domain invariants;
- budget cost and timeout;
- safe audit/telemetry summaries;
- possible errors and whether clarification, retry, approval, or termination follows.

The runtime persists model messages and structured outcomes as needed for resumption, but provenance exposes concise application-owned decision summaries and evidence rather than hidden chain-of-thought.

### 3.1 Capability-module extension contract

Do not encode the current six-capability catalogue as branches in the agent loop. Compose the available toolset from an application-owned registry using authenticated role, site, deployment feature flags, and conversation context. Each module owns its schemas, handler adapter, policy declaration, safe evidence mapping, and evaluation fixtures. The registry rejects incomplete modules and exposes only the capabilities granted for the current run.

The fixture-only MVP ships a `scheduling` module with coarse business capabilities rather than a large set of solver primitives. A later `dc_management` module may add separately permissioned capabilities such as:

- inspect and manage team members, skills, qualifications, and availability;
- inspect and update site scheduling configuration;
- import, validate, create, and version custom scenarios;
- inspect data-import validation and lineage.

Future read and write operations remain distinct. Administrative mutations require their own roles, resource versions, consequence previews, approval policy, idempotency, and audit records. Loading a module never grants authority by itself, and model-generated capability names cannot bypass the registry.

The Scenario Data viewer is not an agent capability and does not depend on `AgentRuntime`. Its authenticated query endpoint calls the application scenario-read service directly and returns a versioned normalized projection covering work areas/tasks, workers/qualifications/availability, demand intervals, baseline assignments, locks, constraints, and objectives. The later agent inspection adapter uses that same service and schema. The MVP exposes no scenario mutation route, command handler, or UI control; future `dc_management` writes remain a separate post-MVP boundary.

## 4. Durable workflow and approval binding

Recommended turn flow:

1. Authenticate the BFF session and resolve the active membership/site.
2. Persist the planner message and accepted agent run.
3. Load only authorized, versioned context.
4. Execute the agent within model/tool/token/time budgets.
5. Validate each proposed tool call against trusted context, ownership, versions, policy, risk, invariants, and budget.
6. Execute read/draft/compute work idempotently or persist an exact approval request and pause.
7. Lease long-running solver work from PostgreSQL; checkpoint state and publish persisted progress events.
8. Resume the same run after job result or approval.
9. Commit business mutation and successful audit evidence atomically; record denial/failure reliably.
10. Stream or replay persisted events to the browser.

An approval record binds at least actor, site, action type, normalized parameter hash, candidate schedule/version, baseline/version, consequence-summary hash, policy version, creation/expiry, and one-time decision state. A client boolean such as `approved=true` is never sufficient. If any bound resource changes, the approval becomes invalid.

Mutating HTTP commands require a caller-provided idempotency key scoped to actor, site, operation, and body hash plus an expected resource version. Internal worker/tool effects use stable keys such as `(agent_run_id, tool_call_id)`.

## 5. Core logical data model

```text
organization
  -> site
     -> membership -> app_user / external identity
     -> scenario -> scenario_version
        -> schedule_run -> schedule_version -> evidence_snapshot
     -> conversation -> message -> agent_run -> tool_call
                                      -> approval_request
                                      -> job / persisted_event
     -> audit_event
```

In the MVP, `scenario_version` records are seeded fixtures and are read-only to the planner and agent. The future DC-management boundary may create new versions through validated imports or edits; historical run inputs remain immutable.

Every user-owned table carries or derives a site boundary. Repository methods require trusted site context, and PostgreSQL row-level security provides defense in depth. The portfolio provisioning service and database invariant reject a second authenticatable application user or active membership; disabling the UI alone is insufficient. Database roles used by the application should not update/delete/truncate audit events. A hash chain may provide tamper evidence but must not be described as absolute immutability; later signed export to S3 Object Lock can create an additional WORM boundary.

S3 evidence objects use content-addressed or immutable version-addressed keys, checksums, and create-only application semantics. A run points to the exact object version and never overwrites evidence in place. This is write-once product behavior, not a claim of regulatory WORM storage unless S3 Object Lock is separately configured and governed.

## 6. Audit, logs, traces, and evaluations are different systems

| Need | Record of truth |
|---|---|
| User identity | Cognito issuer/subject mapped to application user |
| Current authorization | Active PostgreSQL site membership and policy |
| Schedule/workflow state | Versioned PostgreSQL records |
| Business decision evidence | Append-only PostgreSQL audit plus S3 snapshot references |
| AWS/container diagnosis | CloudWatch logs, metrics, events, and alarms |
| Agent behavior exploration | Sanitized OpenTelemetry traces in hosted Logfire |
| Release quality | Version-controlled Pydantic Evals/pytest/Playwright datasets and reports |

Use stable identifiers across these systems: request, conversation, agent run, tool call, approval, job, solver run, audit event, site, actor, and schedule version. Do not use high-cardinality identifiers as metric labels.

Logfire must use PydanticAI instrumentation with content and binary capture disabled by default. Export only allow-listed attributes and scrub as defense in depth. Never export credentials, raw workforce data, full prompts/completions, schedule payloads, tool arguments/results, or approval evidence unless a specific safe diagnostic mode is authorized.

## 7. AWS target deployment

```text
Route 53 / ACM
       |
   CloudFront
    /      \
private S3  ALB -> ECS Fargate API
   SPA                 |
                 RDS PostgreSQL
                       |
                  ECS Fargate worker -> S3 evidence

Cognito -> BFF session/membership
ECR -> immutable images
Secrets Manager -> runtime secrets
CloudWatch <- awslogs/alarms
hosted Logfire <- sanitized OTLP
```

Use the same backend image with separate API and worker commands and least-privilege task roles. The ECS execution role handles image pulls, referenced secrets, and logging; application task roles grant only API- or worker-specific actions. Use CloudFront Origin Access Control for the private frontend bucket. Configure AWS Budgets and cost-allocation tags from the portfolio deployment.

**[ASSUMPTION]** For the low-cost portfolio environment, one API task, one worker task, small RDS capacity, and a portfolio network mode are acceptable with disclosed limitations. The portfolio still enables automated RDS backups and demonstrates a restore drill. Before accepting customers, validate private networking/egress, multiple API tasks, RDS Multi-AZ, formal recovery objectives, worker scaling, security review, and cost model.

## 8. Evaluation and executable architecture proofs

Use deterministic model doubles for normal CI. Golden datasets should contain expected tool, typed arguments, allowed/refused status, evidence IDs, and schedule oracle outputs. Live-provider tests are explicit, gated, and never the only evidence.

Portfolio proofs:

1. Attempt a cross-site request and show deterministic denial.
2. Kill the solver worker mid-run, restart it, and show recovery without duplicate effects.
3. Retry a mutation and show the original semantic response.
4. Change the baseline after an approval request and show stale approval rejection.
5. Inject an unsupported numerical claim and show the grounding evaluator fail it.
6. Insert prompt injection through supported untrusted content and show authority remains unchanged.
7. Disable Logfire export and show the workflow and authoritative audit continue.
8. Deploy an unhealthy image and demonstrate AWS rollback.

## 9. Implementation sequence

1. **Tenant and fixture spine:** PostgreSQL/Alembic, organization/site/membership, one-user enforcement, immutable predefined fixture versions, normalized scenario-read service, versioned run records, and audit foundation.
2. **Scenario Data foundation:** authenticated read-only viewer UI/API, fixture catalogue navigation, version metadata, normalized workforce/demand/baseline/lock/constraint/objective projections, viewer-to-service contract tests, and negative mutation-path tests.
3. **Bounded agent slice:** only after stage 2 passes, introduce `AgentRuntime`, typed read tools over the existing scenario-read service and schema, durable conversations, deterministic doubles, grounded investigation, and viewer-to-agent parity tests.
4. **Durable workflow:** worker leases, persisted events/SSE replay, solver deferral, budgets, cancellation, idempotency, versioned snapshots.
5. **Governed action:** draft/change tools, exact approval, atomic operational-baseline promotion, provenance UI/API, stale/replay tests.
6. **Trust and quality surface:** Logfire/CloudWatch, Pydantic Evals, injection/grounding/tenant/recovery exercises, privacy controls.
7. **AWS portfolio release:** Cognito, containers, Terraform, GitHub OIDC, CloudFront/S3, ALB/ECS, RDS/S3, Secrets, budgets, deploy/rollback proof.

Each stage ends with executable evidence; later stages do not replace missing invariants from earlier ones.

## 10. Deferred architecture triggers

- Add transactional outbox/SQS when measured backlog, independent consumers, or database polling impact justifies a broker.
- Reassess Temporal or another durable workflow engine only for genuinely branching, multi-day, or cross-system workflows.
- Add multiple workers when queue age and solver CPU data justify them; preserve explicit concurrency and idempotency.
- Offer dedicated site/customer infrastructure only for measured noisy-neighbor risk or contractual isolation.
- Replace or upgrade hosted Logfire when retention, team collaboration, compliance, quota, or self-hosting becomes a real requirement.
- Defer WebSockets, GraphQL, gRPC, public MCP, Celery/Redis, Kafka, Kubernetes, service mesh, CQRS, event sourcing, generalized RAG, and multi-agent orchestration until a product requirement demands them.

## 11. Normative requirements inventory

The canonical numbered requirement register is `_bmad-output/planning-artifacts/requirements-inventory.md`. The PRD's unnumbered non-functional requirements section defers to that catalogue's NFR1–NFR35 numbering, which all artifacts (UX, architecture, epics, stories, tests) must use. The UX-derived accessibility and responsive constraints — WCAG 2.2 AA, 200% zoom, text-spacing, reduced motion, 44×44 CSS-pixel touch targets, and phone read-only triage — are adopted as normative MVP requirements (NFR18, NFR20, and the UX-DR set), scoped to the supported browser/assistive-technology matrix declared in `EXPERIENCE.md`.

NFR35's four internal demonstration thresholds are **final as of 2026-07-23** and are no longer placeholders deferred to sprint planning: initial Scenario Data group-window load ≤ 2 s, exact evidence-target resolution ≤ 2 s, first persisted run event after acknowledgement ≤ 5 s, and SSE reconnect replay to current state ≤ 5 s. They are binding on implementation acceptance under the measurement protocol recorded with them in the canonical register, are allocated to architecture components by AD-26, and are cited by the acceptance criteria of Stories 1.4, 1.5, 2.4, and 3.5. Consistent with NFR17 they remain internal portfolio acceptance thresholds measured on the CI reference environment, and must never be presented as customer latency, availability, or recovery objectives.
