---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments:
  - '_bmad-output/planning-artifacts/briefs/brief-ShiftMind-2026-07-21/brief.md'
  - '_bmad-output/planning-artifacts/briefs/brief-ShiftMind-2026-07-21/addendum.md'
workflowType: 'research'
lastStep: 6
research_type: 'technical'
research_topic: 'Production-shaped agent architecture for the ShiftMind portfolio MVP'
research_goals: 'Define every essential agentic-product component and the simplest credible implementation of each, including guardrails, monitoring, structured logging, distributed tracing, full audit and decision provenance, evaluation, security, resilience, and operations.'
user_name: 'Minh'
date: '2026-07-21'
web_research_enabled: true
source_verification: true
---

# ShiftMind: From Scheduling Optimizer to Governed Agentic SaaS

**Date:** 2026-07-21
**Author:** Minh
**Research Type:** technical

---

## Research Overview

This report evaluates how to evolve ShiftMind's working CP-SAT workforce scheduler and natural-language constraint layer into a production-shaped agentic product for an AI-engineering portfolio, while preserving a credible path to a real multi-tenant SaaS. Research covered the agent runtime, typed tools, guardrails, human approval, durable execution, identity and tenant isolation, authoritative audit, decision provenance, evaluation, observability, AWS deployment, operational resilience, cost controls, and implementation sequencing.

The central finding is that ShiftMind should be built as one bounded scheduling agent around a deterministic core. The model interprets planner intent and proposes typed actions; application-owned policy, current site membership, resource versions, approvals, domain invariants, and idempotent commands decide what executes. PostgreSQL is the durable workflow and audit boundary; S3 holds immutable evidence; CloudWatch diagnoses AWS operations; hosted Logfire provides sanitized agent observability and evaluation visualization without becoming a correctness dependency.

The recommended portfolio MVP uses one seeded Cognito planner and one site but adopts the same site/membership data shape required by the future SaaS. It demonstrates conversation, tool use, solver execution, approval-gated publication, crash recovery, complete provenance, evaluation gates, and reproducible AWS deployment while deferring onboarding, billing, multiple active users, multi-agent orchestration, generalized RAG, and premature distributed infrastructure. The consolidated conclusions and decision framework appear in **Research Synthesis and Strategic Conclusions** near the end of this report.

## Technical Research Scope Confirmation

**Research Topic:** Production-shaped agent architecture for the ShiftMind portfolio MVP

**Research Goals:** Define every essential agentic-product component and the simplest credible implementation of each, including guardrails, monitoring, structured logging, distributed tracing, full audit and decision provenance, evaluation, security, resilience, and operations.

**Technical Research Scope:**

- Architecture Analysis - design patterns, frameworks, system architecture
- Implementation Approaches - development methodologies, coding patterns
- Technology Stack - languages, frameworks, tools, platforms
- Integration Patterns - APIs, protocols, interoperability
- Performance Considerations - scalability, optimization, patterns
- Agent Completeness - orchestration, state, memory, tools, guardrails, observability, audit, evaluation, security, and resilience
- Proportional Implementation - a simple portfolio-MVP version and credible SaaS evolution for every component

**Research Methodology:**

- Current web data with rigorous source verification
- Multi-source validation for critical technical claims
- Confidence level framework for uncertain information
- Comprehensive technical coverage with architecture-specific insights
- Preference for primary sources, official specifications, and original research

**Scope Confirmed:** 2026-07-21

---

<!-- Content will be appended sequentially through research workflow steps -->

## Technology Stack Analysis

### Stack Decision Summary

The recommended portfolio stack is a **production-shaped modular monolith**: one React application, one FastAPI API process, one Python solver worker, PostgreSQL, and separately deployable observability containers. Every component has a visible responsibility, but the MVP avoids distributed systems whose complexity would not improve the agent demonstration.

| Concern | MVP choice | Why it earns its place | Later evolution |
|---|---|---|---|
| Agent runtime | PydanticAI behind a ShiftMind-owned `AgentRuntime` interface | Typed tools, provider flexibility, deferred tools, approval support, OpenTelemetry, and eval support align with the existing Python/Pydantic stack | Reassess LangGraph or a durable workflow engine only for genuinely branching, multi-day, or multi-agent work |
| API and domain | Existing FastAPI, Pydantic, and pure Python domain | Preserves working code and clean inward dependencies | Scale API and worker independently |
| Product database | PostgreSQL with SQLAlchemy 2.x and Alembic | Durable jobs, concurrent API/worker writes, migrations, RLS, transactional audit, and queue-style locking | Managed RDS PostgreSQL |
| Observability/evals | Pydantic Logfire Cloud through OpenTelemetry, with Pydantic Evals | Native PydanticAI/FastAPI/database instrumentation plus traces, logs, metrics, dashboards, alerts, datasets, and experiment comparison in one service | Phoenix is the open-source/local alternative; any OTLP backend remains possible |
| Application logs | Structured JSON stdout correlated with Logfire traces | Preserves a local/CloudWatch fallback while Logfire provides search and trace context | Central log archive with explicit retention |
| Service metrics | Logfire metrics, dashboards, and alerts | Removes Prometheus/Grafana containers from the default MVP while retaining visible operational health | Add Prometheus/Grafana or managed cloud monitoring when independent operations requirements justify it |
| Audit | Append-only PostgreSQL audit events written with business transactions | Authoritative, complete decision provenance independent of sampled telemetry | Signed batch export to WORM storage such as S3 Object Lock |
| Async work | PostgreSQL job table plus a separate worker | Durable and restart-aware without Redis/Celery infrastructure | SQS or durable workflow runtime when operational evidence justifies it |
| Authentication | Seeded local user with an opaque secure cookie behind an `IdentityProvider` boundary | Enforces one real planner without building an identity platform | Managed OIDC such as Cognito using Authorization Code with PKCE |
| Local/hosted runtime | Docker Compose locally; ECS Fargate and RDS on AWS | Same containers locally and in the hosted portfolio environment | Multi-AZ and autoscaling only when service objectives require them |

### Programming Languages

**Python remains the agent, API, domain, evaluation, and solver language.** ShiftMind already uses Python for FastAPI, provider adapters, and OR-Tools. PydanticAI adds typed dependency injection, tool schemas, validation, deferred tools, approval workflows, OpenTelemetry integration, and evaluation support without adding a second backend language. Its approval feature is a workflow mechanism, not an authorization boundary; ShiftMind must continue to enforce identity, site scope, permissions, and audit in application code. [PydanticAI overview](https://pydantic.dev/docs/ai/overview/) and [deferred tools and approvals](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/).

**TypeScript remains the browser language.** The existing React application, generated OpenAPI types, TanStack Query, and test stack already provide a suitable agent UI surface. No additional frontend framework is required. The browser should display conversations, approvals, job progress, traces/audit links, and evaluation summaries through typed API contracts.

No emerging language adds portfolio value here. The important evolution is stronger type and schema discipline across boundaries, not polyglot services.

_Popular languages:_ Python for agent/backend/solver; TypeScript for the web client.  
_Emerging languages:_ None recommended for this scope.  
_Performance characteristics:_ Keep CPU-heavy CP-SAT solving outside the API process; agent orchestration is I/O-bound and fits async Python.  
_Confidence:_ High.

### Development Frameworks and Libraries

#### Agent runtime comparison

- **PydanticAI — recommended, medium-high confidence.** It fits FastAPI and a provider-neutral design and supports typed tools, durable/deferred execution patterns, OpenTelemetry, and code-first evals. Pin an exact tested version and wrap it behind `AgentRuntime`, because the agent-framework ecosystem is evolving. [PydanticAI durable execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/) and [Pydantic Evals](https://pydantic.dev/docs/ai/evals/evals/).
- **Application-owned loop — viable fallback.** It gives maximum control, but ShiftMind would need to implement malformed-call handling, pause/resume, retries, turn limits, parallel calls, and streaming semantics. Those mechanics consume effort without differentiating the scheduling product.
- **OpenAI Agents SDK — strong second choice if OpenAI becomes primary.** It provides an agent loop, Pydantic-generated tools, guardrails, sessions, approval pause/resume, and rich traces. It is more OpenAI-centred than ShiftMind's existing Gemini/OpenRouter seam. [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) and [human-in-the-loop](https://openai.github.io/openai-agents-python/human_in_the_loop/).
- **LangGraph — defer.** Its checkpoints and interrupts are strong for explicit graph workflows and indefinite pauses, but graph/checkpointer concepts add ceremony for one bounded agent. An interrupted node restarts from its beginning, so pre-interrupt side effects require idempotency. [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts).
- **Temporal, Restate, DBOS, or similar — SaaS option, not MVP default.** They become valuable when agent work spans multiple services, days, retries, and persistent branches.

The application—not the selected framework—owns the tool registry, read/write/risk classes, authorization, approval records, idempotency, job lifecycle, audit events, prompt/policy/tool versions, evidence references, and decision summaries.

#### Supporting Python libraries

- **SQLAlchemy 2.x and Alembic:** make the expanded schema and migrations explicit and testable. [SQLAlchemy asyncio](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) and [Alembic](https://alembic.sqlalchemy.org/en/latest/api/overview.html).
- **structlog:** emits JSON and binds correlation context through `contextvars`. [structlog documentation](https://www.structlog.org/en/stable/).
- **OpenTelemetry Python and FastAPI instrumentation:** provide vendor-neutral request, model, agent, and tool spans. [Python instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/) and [FastAPI instrumentation](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html).
- **prometheus-client:** exposes low-cardinality operational metrics through `/metrics`. [Prometheus Python client](https://prometheus.github.io/client_python/).
- **pytest:** remains the deterministic CI foundation; agent datasets and graders should be callable from tests rather than requiring a hosted service.

_Ecosystem maturity:_ FastAPI, PostgreSQL, SQLAlchemy, OpenTelemetry, Prometheus, and pytest are mature. Agent runtimes and GenAI semantic conventions are less stable, so adapters and pinned versions are required.  
_Confidence:_ High for supporting libraries; medium-high for PydanticAI.

### Database and Storage Technologies

**PostgreSQL is recommended for the implemented MVP.** SQLite WAL remains valid for a local single-process demonstration, but SQLite permits only one simultaneous write transaction. ShiftMind's target MVP now includes API/worker concurrency, durable job claiming, site isolation, approval records, and transactional audit events; PostgreSQL fits those requirements directly. PostgreSQL row-level security can default-deny access when no policy matches, while `FOR UPDATE SKIP LOCKED` supports multiple consumers of a queue-like table. [SQLite transactions](https://www.sqlite.org/lang_transaction.html), [SQLite WAL](https://www.sqlite.org/wal.html), [PostgreSQL row security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html), and [PostgreSQL `SELECT`](https://www.postgresql.org/docs/current/sql-select.html).

Recommended storage roles:

- relational product state: organizations, sites, memberships, scenarios, conversations, turns, approvals, runs, and run snapshots;
- durable job rows with status, lease, heartbeat, attempt count, cancellation request, result/error reference, and idempotency key;
- append-only audit events with actor/site, correlation identifiers, versions, evidence references, guardrail/authorization outcomes, approvals, tool inputs/outputs or hashes, and result versions;
- Phoenix's own local persistence for traces/evaluation experiments, kept separate from authoritative business audit.

Audit rows should be transactionally coupled to successful mutations where possible. The runtime role should not have update/delete/truncate permissions on audit events, and a trigger can reject those operations. A per-run hash chain provides tamper evidence, but it must not be described as absolute immutability. A later signed export to S3 Object Lock creates a separate WORM trust boundary. [PostgreSQL privileges](https://www.postgresql.org/docs/current/sql-grant.html), [trigger functions](https://www.postgresql.org/docs/current/plpgsql-trigger.html), and [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html).

Redis, a vector database, a graph database, and a warehouse are not required for the MVP. Add them only for measured caching, retrieval, relationship, or analytics requirements.

_Relational database:_ PostgreSQL.  
_NoSQL/in-memory:_ None required.  
_Analytics/evaluation store:_ Version-controlled datasets plus Phoenix experiments.  
_Confidence:_ High.

### Development Tools and Platforms

**Observability and governance use four separate planes:**

1. deterministic guardrail enforcement in application code;
2. OpenTelemetry agent traces, logs, metrics, and evaluations in Logfire;
3. structured JSON stdout for local and platform logging fallback;
4. authoritative append-only business/security audit events in PostgreSQL.

These are complementary, not interchangeable. Traces can be sampled or expire; logs diagnose operations; metrics aggregate health; audit records must be complete and governed.

**Logfire is the recommended default observability backend after focused comparison.** It is built on OpenTelemetry and has first-party instrumentation for PydanticAI, FastAPI, Pydantic validation, HTTP clients, PostgreSQL drivers, SQLAlchemy, system metrics, pytest, and structured logging. It provides AI conversation/tool panels, token and cost tracking, logs, traces, metrics, SQL-queryable dashboards, query-based alerts, and Pydantic Evals experiment comparison. [Logfire AI observability](https://logfire.pydantic.dev/docs/ai-observability/), [integrations](https://logfire.pydantic.dev/docs/integrations/), [dashboards](https://logfire.pydantic.dev/docs/guides/web-ui/dashboards/), [alerts](https://logfire.pydantic.dev/docs/guides/web-ui/alerts/), and [evaluations](https://logfire.pydantic.dev/docs/guides/web-ui/evals/).

Logfire can replace the default Phoenix, Prometheus, and Grafana services for this MVP. It can also receive structured logs, although retaining JSON stdout provides a platform fallback and makes local failures diagnosable when the telemetry backend is unavailable.

**Phoenix remains the preferred open-source/local alternative.** It offers OTLP/OpenInference traces, datasets, experiments, and code/LLM/human evaluations in a lightweight self-hosted deployment. Choose Phoenix instead when local ownership or open-source self-hosting matters more than Logfire's full-stack Pydantic integration. [Phoenix overview](https://arize.com/docs/phoenix) and [Phoenix Docker deployment](https://arize.com/docs/phoenix/self-hosting/deployment-options/docker).

Logfire self-hosting is not an MVP option: official self-hosting is an Enterprise offering requiring Kubernetes, PostgreSQL 16+, object storage, an identity provider, and substantial local SSD capacity. The simple Logfire path is its hosted service. [Logfire self-hosting](https://logfire.pydantic.dev/docs/reference/self-hosted/overview/).

**Structured logs:** bind stable identifiers such as `request_id`, `trace_id`, `agent_run_id`, `conversation_id`, `actor_id`, `site_id`, `tool_call_id`, and `audit_event_id`. Exclude raw workforce data, credentials, unrestricted prompts, and tool-result bodies. OWASP distinguishes operational/security logging from process, transaction, and audit trails and recommends deliberate exclusion or masking of secrets and sensitive data. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).

**Metrics:** expose agent runs, LLM calls/tokens, tool calls/duration, guardrail outcomes, approval outcomes, solver jobs/duration, audit write failures, and evaluation pass/fail counts. Do not place request, user, conversation, or trace identifiers in metric labels because they create high cardinality. One Logfire dashboard and two or three alerts are enough for the MVP. Prometheus/Grafana remain a portable alternative if independent or self-hosted operations monitoring becomes a requirement. [Prometheus instrumentation practices](https://prometheus.io/docs/practices/instrumentation/).

**Evaluation:** keep 30–50 curated scenarios in version control. Prefer deterministic graders for tool choice, schema validity, authorization, confirmation, idempotency, grounding, stale-state behaviour, solver invariants, and bounded termination. Use an LLM judge only for qualities such as explanation usefulness, with a written rubric and periodic human calibration. Phoenix can attach code, model, and human evaluations to traces and compare experiments. [Phoenix agent evaluation example](https://arize.com/docs/phoenix/cookbook/evaluation/evaluate-an-agent) and [NIST AI Resource Center](https://airc.nist.gov/).

_Version control/build:_ existing Git, `uv`, npm, generated OpenAPI types.  
_Testing:_ pytest, Vitest, version-controlled eval datasets, a scripted model, and a small gated live-provider suite.  
_Confidence:_ High.

### Focused Assessment: What Logfire Covers

| Agent-product capability | Logfire coverage | What ShiftMind must still own |
|---|---|---|
| PydanticAI/model/tool tracing | **Strong** | Stable internal IDs and domain event semantics |
| FastAPI, HTTP, database, validation tracing | **Strong** | Correct instrumentation boundaries and redaction |
| Multi-turn conversation/tool inspection | **Strong** | Authoritative conversation and turn persistence |
| Token, cost, latency, exception monitoring | **Strong** | Budgets and runtime enforcement |
| Structured logs and correlation | **Strong** | Log policy, safe fields, JSON stdout fallback |
| Metrics and dashboards | **Strong for MVP** | Metric definitions and low-cardinality labels |
| Alerts | **Adequate for MVP** | Operational thresholds and response ownership |
| Offline evaluation visualization | **Strong with Pydantic Evals** | Version-controlled datasets, graders, CI gates, and human calibration |
| Sensitive-data scrubbing | **Useful defense in depth** | Data minimization and explicit `include_content` policy |
| Guardrail enforcement | **No** | Deterministic input, tool, authorization, invariant, and output checks |
| Human approval workflow | **No; supplied by PydanticAI/application state** | Approval scope, expiry, actor verification, and persistence |
| Durable solver jobs | **No** | PostgreSQL job state, leases, retries, and idempotency |
| Authorization and tenant isolation | **No** | Principal context, repository scoping, permissions, and RLS |
| Authoritative business audit | **No** | Append-only transactional events, access controls, retention, and tamper evidence |
| Exact decision replay | **Partial evidence only** | Versioned prompts/tools/policies, input/run snapshots, evidence references, and controlled re-execution |

Logfire's own audit-log API concerns changes to Logfire resources and administration; it is not ShiftMind's domain audit trail. Telemetry may be sampled and hosted Logfire's standard retention is finite—official documentation currently states that data older than 30 days is pruned outside extended-retention arrangements—so it cannot be the only record of schedule-affecting decisions. [Logfire usage and retention](https://logfire.pydantic.dev/docs/logfire-costs/) and [sampling](https://logfire.pydantic.dev/docs/how-to-guides/sampling/).

PydanticAI telemetry can include prompts, completions, tool arguments, and tool responses. That content capture is enabled by default in current instrumentation. ShiftMind should set `include_content=False` by default, attach only sanitized decision metadata, and use Logfire scrubbing as a second layer rather than relying on pattern matching as the privacy boundary. [Logfire PydanticAI instrumentation API](https://logfire.pydantic.dev/docs/reference/api/logfire/) and [scrubbing](https://logfire.pydantic.dev/docs/how-to-guides/scrubbing/).

**Revised MVP recommendation:** use hosted Logfire as the single observability and evaluation control plane; keep OpenTelemetry-compatible attributes and JSON stdout for portability; retain PostgreSQL as the authoritative audit and job store. Provide an optional Phoenix Docker profile only if a fully local demonstration is important.

### Cloud Infrastructure and Deployment

**Local portfolio environment:** Docker Compose with `frontend`, `api`, `worker`, and `postgres`, exporting OpenTelemetry to hosted Logfire. An optional local-observability profile may add Phoenix when the demo must run without a hosted telemetry service.

**AWS is the target deployment, not an unspecified future option.** The local component boundaries must map directly to AWS services:

```text
Route 53 + ACM
      |
CloudFront
  |-- private S3 origin: React application
  `-- /api/* -> public ALB
                    |
             ECS Fargate API service
                    |
        +-----------+------------+
        |                        |
  RDS PostgreSQL          S3 scenario/run snapshots
        |
  ECS Fargate worker service -> CP-SAT

API and worker
  |-- JSON stdout -> CloudWatch Logs
  |-- OpenTelemetry -> hosted Logfire
  |-- secrets -> Secrets Manager
  `-- AWS access -> separate least-privilege task roles

Cognito User Pool -> authenticated principal -> ShiftMind membership/site policy
```

Use the same application image with separate API and worker commands. The API and worker become separate ECS Fargate services or task definitions so CPU allocation, failure domains, and scaling remain independent. RDS PostgreSQL stores domain state, jobs, approvals, and audit events. S3 stores larger immutable scenario/run artifacts behind an `ObjectStore` interface. ECR stores immutable application images.

CloudFront should serve the React SPA from a private S3 bucket using Origin Access Control and route API traffic to an Application Load Balancer. AWS recommends OAC for restricting S3 origins to CloudFront. [Secure static website with CloudFront](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/getting-started-secure-static-website-cloudformation-template.html) and [CloudFront origin access](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DownloadDistValuesOrigin.html).

For the hosted portfolio, Cognito User Pools are the target identity provider. Use Authorization Code with PKCE, disable public sign-up for the single-user MVP, seed one planner, validate tokens server-side, and map Cognito `sub` to a ShiftMind membership and site. Cognito supports PKCE specifically to bind authorization-code redemption to the initiating client. [Cognito PKCE](https://docs.aws.amazon.com/cognito/latest/developerguide/using-pkce-in-authorization-code.html) and [app-client guidance](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-client-apps.html).

Logfire remains the AI/application observability plane on AWS. ECS containers export OpenTelemetry directly to hosted Logfire in the MVP. Structured stdout simultaneously goes through the ECS `awslogs` driver to CloudWatch, so startup failures and export outages remain diagnosable. An AWS Distro for OpenTelemetry sidecar is a later option if routing, batching, or dual export to CloudWatch becomes necessary; it is not required for the first deployment. [ECS CloudWatch logs](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_awslogs.html) and [ADOT application metrics on ECS](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/application-metrics-cloudwatch.html).

Use separate ECS task execution and task roles. The execution role permits ECR image pulls, CloudWatch logging, and referenced secrets; application task roles grant only the API or worker's required AWS actions. Store model keys, database credentials, Cognito configuration secrets, and the Logfire write token in Secrets Manager. AWS documents these as distinct ECS security roles. [ECS IAM role practices](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html) and [Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html).

Provision the AWS environment as code from the beginning. The precise choice between Terraform and AWS CDK can be finalized in architecture research; the requirement is reproducible environments, no console-only resources, tagged cost ownership, and separate development/portfolio configuration.

**Do not use Kubernetes for this phase.** Two application processes and one managed database do not justify control-plane and cluster operational complexity. This is an inference from ShiftMind's component count, not a claim that Kubernetes is technically incapable. [Kubernetes cluster architecture](https://kubernetes.io/docs/concepts/architecture/).

**Do not run CP-SAT as a normal FastAPI background task or primary Lambda function.** FastAPI warns that heavy background computation may require separate processes or servers. Lambda functions also have a 15-minute maximum duration, while the existing solver is CPU-heavy and variably long-running. [FastAPI background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/) and [Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html).

_Container technology:_ Docker/Compose locally, ECS Fargate hosted.  
_Serverless:_ useful later for small adapters or scheduled exports, not the solver or primary API.  
_Confidence:_ High for the MVP; medium for long-term hosting because real usage is unknown.

### Technology Adoption Trends

Agent frameworks increasingly bundle loops, tools, sessions, approvals, guardrails, and traces. That reduces boilerplate but makes framework lock-in and hidden control flow a risk. ShiftMind should isolate framework mechanics behind an application contract and keep safety, authorization, audit, and scheduling semantics outside it.

OpenTelemetry is the strongest interoperability choice for traces and metrics. Its GenAI conventions now cover agents and tools, but they remain under active development; ShiftMind should pin instrumentation and map stable internal event names to external semantic conventions rather than coupling audit schemas to them. [OpenTelemetry GenAI conventions repository](https://github.com/open-telemetry/semantic-conventions-genai) and [semantic conventions](https://opentelemetry.io/docs/specs/semconv/).

Evaluation practice is moving from spot-checking outputs toward versioned datasets, trace/path grading, deterministic safety assertions, experiments, and sampled online signals. For ShiftMind, the schedule engine supplies unusually strong deterministic oracles: constraint validity, objective terms, run snapshots, and before/after metrics can ground evaluation beyond subjective LLM judging.

The recommended adoption rule is therefore: **use mature infrastructure directly, wrap fast-moving agent technology, and never outsource the authoritative policy or audit boundary to a framework or telemetry vendor.**

### Quality Assessment

- **High confidence:** Python/FastAPI/React continuity; PostgreSQL; separate solver worker; Docker/ECS; OpenTelemetry; JSON logging; hosted Logfire with CloudWatch fallback; separate transactional audit; deterministic evaluation-first design.
- **Medium-high confidence:** PydanticAI as the best current framework fit. Its capability match is strong, but it should be pinned and isolated behind contract tests.
- **Medium confidence:** exact OpenTelemetry GenAI attribute mapping and the eventual hosted observability platform, because standards and product economics are still changing.
- **Research gap to revisit:** hosted deployment cost, traffic scale, data residency, and customer identity requirements cannot be selected responsibly before real usage or customer constraints exist.

## Integration Patterns Analysis

### Integration Research Synthesis

Parallel research covered PydanticAI's model, tool, deferred-execution, approval, and message-history contracts; HTTP/SSE standards; AWS CloudFront, ALB, ECS, RDS, S3, SQS, IAM, and logging behavior; Cognito/OIDC security; transactional outbox and idempotency; OpenTelemetry correlation; and OWASP guidance for agent authorization and prompt injection.

The cross-integration conclusion is a durable, application-owned run protocol:

```text
Browser command
  -> FastAPI validates session, site membership, request, and idempotency
  -> PostgreSQL commits agent_run + run.queued + audit evidence
  -> ECS worker leases run and executes PydanticAI
       -> read-only tool: authorize, execute, record result
       -> risky tool: persist exact approval request and pause
       -> CP-SAT tool: persist solver job and pause
  -> worker persists sequenced run events
  -> FastAPI replays/tails events to browser over SSE
  -> approval or tool result queues the exact run for resumption
```

The browser connection, ECS task, model SDK, and Logfire trace are all replaceable. PostgreSQL state is the recovery boundary. This is the key difference between a streamed chat demo and a production-shaped agent.

### API Design Patterns

Use same-origin, versioned **REST/JSON commands and resources** behind CloudFront. The public contract should expose ShiftMind concepts, not PydanticAI message or provider payloads:

```http
POST /api/v1/conversations/{conversation_id}/turns
Idempotency-Key: <client-generated UUID>
-> 202 { "run_id": "...", "status": "queued" }

GET /api/v1/agent-runs/{run_id}
-> durable status, result, and pending action

GET /api/v1/agent-runs/{run_id}/events
Last-Event-ID: <persisted event sequence>
-> text/event-stream

GET /api/v1/approval-requests/{approval_id}
-> sanitized action, consequence, evidence, and expiry

POST /api/v1/approval-requests/{approval_id}/decision
Idempotency-Key: <client-generated UUID>
If-Match: "approval-<version>"
-> approved or denied result
```

Return `202 Accepted` for queued work. The durable run resource, not the original POST connection, represents progress. Publish an OpenAPI contract from FastAPI and generate TypeScript client types where practical. Use UUID identifiers, ISO 8601 UTC timestamps, explicit enums, and a `schema_version` on persisted event and snapshot envelopes.

Every mutating request requires an idempotency key scoped by actor, site, operation, and request-body hash. Claim the key and create the mutation atomically; repeat requests return the same semantic result, while reuse with different arguments fails. Internal effects use stable keys such as `(agent_run_id, tool_call_id)` because HTTP idempotency alone cannot protect worker retries. AWS recommends caller-provided request identifiers and semantically equivalent retry responses for idempotent APIs. [Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/).

Use independent optimistic versions for workflow state and schedule state. Risky schedule changes carry a strong ETag and `If-Match`; stale versions return `412 Precondition Failed`. Database commands use conditional updates rather than a read-then-write check. HTTP defines `If-Match` specifically to prevent lost updates from concurrent changes. [RFC 9110 HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110).

GraphQL does not improve the command-heavy MVP, gRPC is unnecessary inside one Python deployment, and public webhooks introduce authentication, retry, and delivery products that ShiftMind does not yet need. Keep these out of the initial public surface.

### Communication Protocols

Use HTTPS for all browser traffic and **SSE plus ordinary POST commands** for live agent progress. User messages and approval decisions are discrete client-to-server commands; tokens, statuses, tool activity, and job completion are predominantly server-to-client. The WHATWG EventSource protocol supplies typed events, event IDs, automatic reconnect, retry hints, and `Last-Event-ID`. [WHATWG Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html).

Persist events before publishing them, with a monotonically increasing sequence per run:

```text
run.queued
run.started
text.delta
tool.requested
approval.required
solver.queued
tool.completed
run.completed
run.failed
```

The SSE event `id` is the database sequence, not an in-memory counter. On reconnect, the endpoint replays later persisted events and then tails new ones. Send a comment heartbeat approximately every 15 seconds, disable CloudFront caching for `/events`, and test the full CloudFront -> ALB -> ECS path. ALB's idle timeout is configurable and defaults to 60 seconds, so the heartbeat must stay comfortably below the configured intermediary timeouts. [ALB attributes](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/edit-load-balancer-attributes.html).

Do not execute the agent inside the SSE response generator. A browser disconnect must not cancel persistence or lose a completed tool effect. An ECS worker owns execution; the SSE endpoint only observes durable events. WebSockets remain a later option for genuinely continuous bidirectional collaboration, not a default requirement.

Use W3C Trace Context at synchronous boundaries and persist trace correlation at asynchronous ones. API logs include `trace_id` and `span_id`; job rows include the originating trace and run IDs; worker spans use a trace link or explicit correlation attributes when continuing later. `traceparent` is diagnostic context, never identity or authorization evidence, and must not contain PII or site data. [W3C Trace Context](https://www.w3.org/TR/trace-context/).

### Data Formats and Standards

Use four deliberately separate data representations:

| Contract | Format | Purpose |
|---|---|---|
| Public API | Versioned JSON described by OpenAPI | Stable browser/application interoperability |
| Agent tools | Pydantic input/output models rendered as JSON Schema | Typed model proposals and validation |
| Runtime checkpoint | PydanticAI message serialization plus ShiftMind metadata | Exact pause/resume compatibility |
| Evidence snapshot | Canonical, versioned JSON, optionally gzip-compressed in S3 | Solver input/output and reproducible audit evidence |

PydanticAI function tools derive schemas from typed Python definitions and validate model-generated arguments before calling application code. That is a data-validity boundary, not an authorization boundary. Security context must be injected from trusted runtime dependencies rather than appearing in tool arguments. [PydanticAI function tools](https://pydantic.dev/docs/ai/tools-toolsets/tools/).

Every agent run pins `model_provider`, `model_id`, prompt-template version, tool-contract version, policy version, and application version. Large solver inputs and outputs use unique S3 keys such as `sites/{site_id}/runs/{run_id}/input-{sha256}.json.gz`; PostgreSQL stores the bucket, key, version ID, SHA-256 digest, schema version, size, and content type. Upload first, verify the checksum, then commit the database pointer and audit event. Orphan cleanup handles the unavoidable lack of an RDS/S3 distributed transaction. S3 Versioning provides recovery from accidental overwrite or deletion; Object Lock is deferred until a real WORM retention requirement exists. [S3 Versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html).

Do not store or claim to reconstruct hidden chain-of-thought. Traceable decisions instead store the user-visible request/response, concise decision summary, evidence references, constraint and guardrail results, safe tool arguments, authorization rule IDs, approval decision, actual outcome, schedule versions, and model/prompt/tool/policy versions.

### System Interoperability Approaches

Keep a ShiftMind-owned `AgentRuntime` interface between application services and PydanticAI. PydanticAI supplies the model/tool loop, provider abstraction, typed dependencies, and deferred-tool mechanism; ShiftMind owns authentication, site context, policy, approval records, jobs, audit, and domain invariants.

Use narrow tools such as:

```text
get_schedule_context
evaluate_candidate_change
request_solver_run
request_publish_schedule
```

Never expose unrestricted SQL, shell execution, arbitrary URL fetching, credentials, wildcard tool access, or a generic cross-site service account. Tool wrappers inject an application-created `AuthContext` containing actor, site, membership, role, and permissions. The model cannot supply or override it.

PydanticAI's deferred-tool protocol is the adapter for long work and human approval. `ApprovalRequired` pauses a proposed risky action; `CallDeferred` pauses a CP-SAT request that executes elsewhere. Persist the validated call, unique tool-call ID, exact message checkpoint, and runtime versions; resume with the original history and `DeferredToolResults` keyed to that call. [PydanticAI deferred tools](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/).

Conversation persistence should therefore separate:

- `conversation`: product thread and ownership;
- `agent_run`: one submitted turn or resumption and durable state;
- `agent_message_checkpoint`: framework-specific recovery payload;
- `run_event`: stable frontend event DTO;
- `pending_tool_call` and `approval_request`: application workflow state;
- domain state and `audit_event`: authoritative business record.

This dual representation prevents PydanticAI upgrades from becoming public API or audit migrations. PydanticAI documents message-history serialization and resumption, but the application must load authoritative history from PostgreSQL rather than trusting history submitted by a browser. [PydanticAI message history](https://pydantic.dev/docs/ai/core-concepts/message-history/).

### Microservices Integration Patterns

ShiftMind should remain a **modular monolith with process separation**, not a collection of network microservices:

- CloudFront routes `/*` to the private S3 SPA and `/api/*` to the ALB; API caching is disabled.
- `shiftmind-api` is an ECS Fargate service behind the ALB.
- `shiftmind-worker` is an independent ECS Fargate service with no public endpoint.
- Both may use the same immutable ECR image with different entrypoints, task definitions, task roles, health checks, and CPU/memory profiles.
- RDS PostgreSQL is the shared durable coordination boundary; S3 holds bulky immutable evidence.

Prefer a CloudFront VPC origin with an internal ALB where regional and IaC support is suitable. Otherwise restrict a public ALB to CloudFront and verify a secret origin header. CloudFront now documents private VPC origins for ALBs. [CloudFront VPC origins](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-vpc-origins.html).

For the MVP, the worker claims PostgreSQL jobs with `FOR UPDATE SKIP LOCKED`, writes a lease owner and expiry, commits, and performs CP-SAT outside the claim transaction. Heartbeats extend the lease; expired leases recover abandoned work; completion commits result state and audit evidence atomically. PostgreSQL explicitly notes `SKIP LOCKED` can be used to avoid lock contention with multiple consumers of a queue-like table. [PostgreSQL `SELECT` locking clause](https://www.postgresql.org/docs/current/sql-select.html).

Do not add service discovery, a service mesh, distributed sagas, or circuit-breaker libraries yet. There is no synchronous service graph to justify them. Use explicit HTTP/model timeouts, bounded retries with jitter for transient external failures, and ECS health/deployment rollback controls.

### Event-Driven Integration

The MVP is event-informed but not event-sourced. Product state remains normalized PostgreSQL state. `run_event` supports UI replay; `audit_event` supplies immutable business evidence; neither is used to rebuild every domain aggregate.

For every state-changing command, commit together where applicable:

```text
domain mutation
+ append-only audit event
+ job or outbox row
```

When one PostgreSQL-backed API and worker are sufficient, the job table avoids a database/message-broker dual write. Introduce SQS only when measured backlog, burst scaling, multiple consumers, or cross-service separation warrants it. At that point use the transactional outbox pattern: commit domain state, audit, and outbox row atomically; then an idempotent relay publishes to SQS. AWS's guidance identifies the outbox as the solution to database/message dual-write inconsistency and warns that consumers must still be idempotent. [AWS transactional outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html).

Use SQS Standard unless strict per-site ordering is proven necessary. Standard queues provide at-least-once delivery, so the worker must deduplicate by stable job ID and commit results before deleting a message. [SQS at-least-once delivery](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/standard-queues-at-least-once-delivery.html). FIFO with `site_id` as the message group is a later ordering option; optimistic schedule-version checks remain mandatory.

### Integration Security Patterns

Prefer a same-origin **Backend-for-Frontend** pattern for the AWS-hosted first-party UI. FastAPI acts as a Cognito confidential client using Authorization Code with PKCE; Cognito tokens stay server-side and the browser receives an opaque `Secure`, `HttpOnly`, `SameSite` session cookie. Store only a hash of the session ID and add explicit CSRF protection to state-changing endpoints. Cognito documents PKCE for binding authorization-code redemption to the initiating client. [Cognito PKCE](https://docs.aws.amazon.com/cognito/latest/developerguide/using-pkce-in-authorization-code.html). The BFF choice is medium-high confidence because the current IETF browser-app BCP remains a draft; it is still preferable here to exposing long-lived tokens to JavaScript. [OAuth for Browser-Based Applications draft](https://datatracker.ietf.org/doc/draft-ietf-oauth-browser-based-apps/26/).

Cognito authenticates; ShiftMind authorizes. Map `(issuer, sub)` to an active `app_user` and `site_membership` on every request. A URL or token site claim is only a selector/hint: PostgreSQL membership is authoritative. The trusted context is constructed once at the API boundary, persisted on runs/jobs/approvals/audit events, and loaded by workers from durable state. Reauthorize immediately before every asynchronous state change.

The non-negotiable tool pipeline is:

```text
validated arguments
  -> authenticated AuthContext
  -> deterministic role/action policy
  -> site and resource ownership check
  -> current schedule-version and invariant check
  -> risk classification and approval gate
  -> idempotent execution
  -> transactional audit
```

Treat user messages, uploads, retrieved text, database notes, and tool results as untrusted data. Separate data from instructions; allow-list tools; schema-validate calls; cap model requests, tokens, retries, tool depth, and runtime; filter tool outputs; and verify each action against the original intent. OWASP recommends least privilege, complete mediation, and human approval for excessive-agency risks. [OWASP Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/) and [AI Agent Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html).

An approval is an application record, not a boolean returned by the client or model. Bind it to actor, site, tool name, canonical argument hash, resource, expected schedule version, risk reason, expiry, one-time status, approver, and decision timestamp. On execution, verify it is approved, unexpired, unused, argument-identical, version-current, and still authorized. Consume approval and apply the mutation atomically or with an idempotent operation. PydanticAI explicitly warns that its approval flow is not itself an authorization boundary against untrusted clients. [PydanticAI UI integration security](https://pydantic.dev/docs/ai/integrations/ui/overview/).

Keep three records with different purposes:

| Record | System | Contract |
|---|---|---|
| Business audit | PostgreSQL, with referenced S3 evidence | Authoritative, append-only, unsampled, access-controlled |
| Operational logs | Structured stdout to CloudWatch | Diagnostics, alarms, bounded retention |
| Agent/application telemetry | OpenTelemetry to hosted Logfire | Traces, metrics, dashboards, alerts, evaluation; may be sampled |

Write a successful mutation and its audit event in the same transaction. Record denied and failed attempts in a separate reliable audit transaction because their business transaction is rolled back. Give the runtime audit role `INSERT` and required `SELECT`, but no `UPDATE` or `DELETE`; optionally add a trigger and hash-chain fields for tamper evidence. `pgAudit` may supplement SQL-level security auditing but cannot explain the application decision.

Correlate, but never conflate, these stores with `request_id`, `trace_id`, `agent_run_id`, `tool_call_id`, `approval_id`, `job_id`, `audit_event_id`, `actor_id`, `site_id`, and `schedule_version_id`. An audit row may contain a trace ID as a navigation aid; a trace can never prove authorization or substitute for the audit event.

Configure Logfire/PydanticAI with `include_content=False` and `include_binary_content=False` and export allow-listed, sanitized attributes. Prompts, completions, tool arguments, and responses may otherwise be captured. [Logfire PydanticAI instrumentation](https://logfire.pydantic.dev/docs/reference/api/logfire/). ECS stdout/stderr still goes through `awslogs` to CloudWatch so startup and exporter failures remain visible. [ECS CloudWatch logging](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_awslogs.html).

Use distinct ECS task roles for API and worker and a separate task execution role. Store database credentials, model keys, Logfire token, and any CloudFront-origin secret in Secrets Manager. Private Fargate tasks require controlled outbound connectivity for the model provider and hosted Logfire; the network design must account for that rather than assuming all traffic stays within AWS.

The governing security invariant is:

> No model output, model memory, browser-supplied site value, or client-submitted approval can authorize an action. Only authenticated application context, current PostgreSQL membership, deterministic policy, current resource state, and a valid parameter-bound approval can do so.

### Integration Quality Assessment

- **High confidence:** REST resources, SSE replay, application-owned authorization, typed narrow tools, deferred pause/resume, PostgreSQL durability, transactional audit, idempotency, optimistic versions, CloudWatch/Logfire separation, and the AWS API/worker topology.
- **Medium-high confidence:** PostgreSQL queue before SQS and BFF before direct SPA tokens. Both are intentional MVP architecture judgments and have explicit evolution paths.
- **Validation required in deployment:** SSE heartbeat behavior across the actual CloudFront/ALB configuration; worker lease recovery during forced ECS replacement; model/Logfire outbound networking; Cognito logout/session invalidation; and concurrent approval/version conflicts.
- **Deferred by design:** GraphQL, gRPC, WebSockets, MCP as a public protocol, Kafka/RabbitMQ, SQS, service mesh, event sourcing, CQRS, sagas, Temporal/DBOS, and Kubernetes. Each solves a scale or integration problem not yet demonstrated by the portfolio MVP.

## Architectural Patterns and Design

### System Architecture Patterns

ShiftMind should use a **production-shaped modular monolith with process separation**. It has one application and domain model, but deploys the synchronous API and asynchronous work as independently replaceable processes. The agent is a bounded orchestration component around the deterministic scheduling engine, not a second source of business rules.

```text
CloudFront
  |-- React SPA in private S3
  `-- /api/* -> ALB -> FastAPI BFF
                           |
                    PostgreSQL / RDS
         +-----------------+------------------+
         |                 |                  |
    conversations      durable runs      authoritative audit
    approvals/jobs     run events         memberships/policy
         |
    ECS Agent Worker
         |
    Context Builder
         v
    PydanticAI Agent
         v
    Deterministic Tool Gateway
         |-- authorization and site isolation
         |-- schema validation and guardrails
         |-- schedule-version and invariant checks
         |-- risk classification and approval
         `-- idempotency and transactional audit
                    |
          +---------+---------+
          |                   |
     read/domain tools    CP-SAT solver jobs
                              |
                      immutable S3 evidence

CloudWatch <- JSON operational logs
Logfire   <- sanitized OpenTelemetry
Pydantic Evals <- version-controlled evaluation datasets
```

This is an evolutionary change to the existing code. Preserve the pure scheduling domain and `SchedulerEngine` protocol. Evolve the current `LLMProvider` seam into a broader ShiftMind-owned `AgentRuntime`, replace the in-process solve pool with a durable worker, and migrate SQLite to PostgreSQL before public AWS deployment. The deterministic stub and numeric-grounding guard remain valuable controls and test doubles.

Use **one scheduling agent with narrow tools**. A multi-agent topology would add delegation, trust, evaluation, and cost surfaces without solving a demonstrated problem. AWS's Agentic AI Lens recommends bounded responsibilities, observable actions, versioned agent behavior, proportionate human oversight, and explicit contracts. [AWS Agentic AI design principles](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/design-principles.html).

Model the agent workflow as an application-owned state machine:

```text
QUEUED
  -> RUNNING
      |-- COMPLETED
      |-- AWAITING_APPROVAL
      |-- AWAITING_TOOL_RESULT
      |-- RETRY_SCHEDULED
      `-- FAILED

AWAITING_APPROVAL
  |-- APPROVED -> QUEUED_FOR_RESUME
  |-- DENIED
  `-- EXPIRED

AWAITING_TOOL_RESULT
  |-- TOOL_COMPLETED -> QUEUED_FOR_RESUME
  |-- TOOL_FAILED
  `-- TIMED_OUT
```

Each transition uses optimistic compare-and-set versioning and emits an audit event. No browser connection or ECS process must remain alive while waiting. PydanticAI supplies deferred calls and resumption using unique tool-call IDs and stored message history. Its integrations with Temporal, DBOS, Prefect, and Restate remain future options if exact mid-run durable execution becomes necessary. [PydanticAI deferred tools](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/) and [durable execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/).

### Design Principles and Best Practices

The core principle is **deterministic core, stochastic edge**. The LLM interprets intent, selects from an approved capability set, and explains results. Application code controls identity, authorization, tenant context, validation, state transitions, solver invariants, execution, approval, and audit.

Apply these architectural rules:

- **The model proposes; application code disposes.** A generated tool call is an untrusted proposal until the entire deterministic gateway accepts it.
- **Ports and adapters.** Domain and application services depend on `SchedulerEngine`, `AgentRuntime`, `ModelGateway`, `ObjectStore`, `AuditSink`, and `Telemetry` interfaces rather than vendor SDKs.
- **Version behavior like code.** Persist model/provider ID, prompt, tool-contract, policy, evaluator, and application versions for each run. Review, test, stage, and roll back those artifacts.
- **Explicit capability registry.** Each tool declares its schema, required permission, risk tier, timeout, idempotency behavior, and whether it can be deferred.
- **Make state explicit.** Conversation, agent run, message checkpoint, tool call, approval, solver job, schedule version, run event, and audit event are separate concepts.
- **Fail closed for authority; degrade gracefully for availability.** An unavailable model must not bypass controls, while manual scheduling and existing solver functions remain available.
- **No hidden-reasoning dependency.** Store concise decision summaries, evidence references, policy outcomes, and actions—not chain-of-thought.
- **Quality gates before architectural expansion.** Add a framework or AWS service only after a measurable reliability, scale, collaboration, or compliance need appears.

AWS recommends treating agent behavior as code and grounding autonomy in schemas, registries, success criteria, and observable contracts. [AWS Agentic AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentic-ai-lens.html).

### Scalability and Performance Patterns

Scale API, agent/solver work, model use, and storage independently:

- API tasks are horizontally scalable and contain no authoritative in-memory state.
- Worker concurrency is explicitly bounded because CP-SAT is CPU-heavy; a worker leases one or a configured small number of jobs.
- PostgreSQL jobs begin as the queue; job age and lease recovery are the primary workload signals.
- Per-site quotas bound concurrent agent runs, concurrent solver jobs, tokens, model cost, uploaded data, stored snapshots, and API requests.
- Pure read tools and parsed scenario artifacts may be cached by `(site_id, resource_id, version)`; mutations and approval decisions are never served from a cache.
- Agent limits include maximum model requests, tool calls, tool depth, tokens, wall-clock duration, solver time, and retry attempts.

Unbounded reasoning loops and tool use are specific agentic cost and reliability risks. AWS recommends enforcement outside the model loop with per-cycle, per-task, and daily limits. [AWS automated agent cost controls](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentcost07-bp01.html).

Use a measured evolution path:

| Trigger | Architectural response |
|---|---|
| More API traffic | Increase stateless ECS API tasks behind ALB |
| Solver backlog or long queue age | Increase worker capacity within CPU/database limits |
| RDS polling pressure | Add `LISTEN/NOTIFY` as a wake-up hint, then outbox + SQS if necessary |
| Connection churn | Add RDS Proxy only after pool evidence supports it |
| Large tenant becomes noisy neighbor | Enforce stricter quotas or isolate its workers |
| Strong customer isolation contract | Offer a siloed deployment tier |
| Complex cross-service durable workflow | Evaluate Temporal, DBOS, Restate, or Step Functions |

The initial portfolio deployment can run one API and one worker task. A customer-facing availability target should use at least two API tasks across Availability Zones, RDS Multi-AZ where budget permits, tested backup restore, and explicit recovery objectives.

### Integration and Communication Patterns

The public architecture uses REST commands, durable resources, and SSE replay as defined in the integration analysis. Internally, modules call application interfaces directly; a network protocol is not introduced between modules simply to imitate microservices.

The most important integration boundary is the tool gateway:

```text
agent proposal
  -> tool registry lookup
  -> typed argument validation
  -> trusted AuthContext injection
  -> authorization and site check
  -> schedule-version and domain invariants
  -> risk/approval policy
  -> idempotent application command
  -> audit + result
```

Provider-specific model requests and PydanticAI message objects stay behind `AgentRuntime`. Frontend events are stable ShiftMind DTOs. Solver inputs/outputs are domain schemas. This prevents framework upgrades from propagating across the product.

Define graceful degradation explicitly:

| Dependency failure | System behaviour |
|---|---|
| Model provider unavailable | Manual constraint editing and solver functions remain usable |
| Agent worker unavailable | Runs remain queued and recover through leases |
| Solver failure | Failure is visible; no schedule is published |
| Browser disconnect | Work continues; SSE later replays persisted events |
| Logfire unavailable or capped | Product/audit continue; CloudWatch remains available |
| Approval expires | Action fails closed and must be proposed again |
| Worker retries after an effect | Stable idempotency key prevents duplication |
| Schedule changes during a run | Stale mutation is rejected and re-planned |

### Security Architecture Patterns

Guardrails are a layered architecture, not a single system prompt:

1. Session authentication, CSRF protection, request-size limits, and rate limits.
2. Trusted site and membership resolution.
3. Input and attachment validation.
4. Separation of untrusted content from instructions and prompt-injection handling.
5. Allow-listed, versioned tool registry.
6. Pydantic argument and result validation.
7. Deterministic role/action policy.
8. Tenant and resource ownership check.
9. Current schedule version and domain-invariant validation.
10. Risk classification and human approval.
11. Tool timeout, retry, iteration, token, concurrency, and cost budgets.
12. Output grounding, sensitive-data filtering, and safe error mapping.
13. Transactional audit and sanitized telemetry.

Suggested autonomy tiers:

- **Tier 0 — explain:** inspect schedules, constraints, and metrics automatically.
- **Tier 1 — propose:** create draft changes and comparisons automatically.
- **Tier 2 — compute:** launch bounded solver runs automatically within site quotas.
- **Tier 3 — consequential:** publishing or replacing an operational schedule requires parameter-bound approval.
- **Tier 4 — forbidden:** role management, arbitrary SQL, shell access, credentials, and unrestricted external requests are never tools.

AWS's current agent security guidance calls for tool authorization, validated tool input/output, least privilege, human oversight, decision-artifact storage, distributed tracing, prompt-injection defence, and output filtering. [AWS Agentic AI security architecture](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/security.html).

Cognito authenticates the user; PostgreSQL membership authorizes the action; repository scoping and row-level security isolate the tenant. AWS explicitly notes that a user can be authenticated and authorized yet still access another tenant if isolation is not separately enforced. [AWS SaaS authorization and isolation guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-api-access-authorization/introduction.html).

For the current single-user phase, public registration is disabled and deployment bootstrapping creates one site, one user, and one planner membership. Application configuration and a database constraint prevent creation of an additional active user. This deliberately temporary rule exercises the future identity/membership model without pretending the local no-auth state is safe for public hosting.

### Data Architecture Patterns

Use PostgreSQL as the source of truth with `site_id` present from the first production-shaped schema. The core aggregate groups are:

```text
Identity:       app_user, site, site_membership, session
Scheduling:     scenario, scenario_version, constraint_override,
                solver_job, schedule_version
Agent:          conversation, message, agent_run,
                message_checkpoint, pending_tool_call, approval_request
Evidence:       run_event, audit_event, artifact_reference
Control:        idempotency_record, policy_version, tool_contract_version
Evaluation:     eval_dataset_version, eval_run_summary, reviewed_case_reference
```

Use foreign keys, unique constraints, optimistic version columns, and explicit state-transition commands. Every tenant-owned row includes `site_id`; repositories require it; PostgreSQL row-level security provides defense in depth. PostgreSQL policies can restrict which rows are visible and which rows may be created or changed. [PostgreSQL row-security policies](https://www.postgresql.org/docs/current/catalog-pg-policy.html).

The portfolio begins with one seeded planner and one site but uses the full membership shape. Future onboarding activates more users and roles rather than migrating every domain table from global ownership to tenant ownership.

The authoritative audit ledger is append-only and unsampled. A state-changing transaction writes the mutation and its success event together. Denied or failed attempts use a separate reliable audit transaction. Evidence fields include actor/site, request and run IDs, action, policy result, approval, resource versions before/after, safe argument/result summaries, model/prompt/tool/policy versions, trace correlation, and S3 snapshot references. Optional hash chaining and a mutation-rejecting trigger add tamper evidence.

Conversation memory is deliberately scoped and simple: persisted user-visible messages plus compact, evidence-linked summaries. Do not add a vector database or generalized long-term memory until a retrieval use case and data-retention policy exist.

S3 stores immutable, content-addressed solver input/output and evidence bundles. PostgreSQL remains the index and source of current job/audit state. Separate retention policies apply to business state, conversations, audit, S3 evidence, CloudWatch logs, and Logfire telemetry.

### Evaluation and Decision-Provenance Architecture

Evaluation is a first-class delivery pipeline rather than a dashboard added after implementation:

```text
version-controlled dataset
        -> candidate agent configuration
        -> deterministic evaluators
             |-- correct tool and arguments
             |-- forbidden tool not called
             |-- site scope preserved
             |-- approval requested when required
             |-- schema and schedule invariants hold
             |-- numbers grounded in solver evidence
             `-- budgets respected
        -> selective subjective evaluators
             |-- helpfulness
             |-- explanation quality
             `-- appropriate clarification
        -> release quality gate
```

Pydantic Evals is code-first and can write results to disk or the terminal without Logfire. It supports deterministic, custom, LLM-judge, and span-based evaluators; Logfire adds experiment comparison and trace visualization. [Pydantic Evals](https://pydantic.dev/docs/ai/evals/evals/).

Keep curated golden, safety/red-team, tenant-isolation, approval-bypass, tool-selection, stale-version, provider-failure, and solver-edge datasets in version control. Promote reviewed failures from production into regression cases. Deterministic assertions gate every release; subjective evaluator thresholds use repeated runs or confidence intervals to avoid treating stochastic scores as exact.

Online evaluation is sampled and advisory. Guardrail outcomes, authorization denials, approval decisions, mutations, and audit evidence are unsampled. Pydantic's online evaluation emits OpenTelemetry evaluation events and can use sinks in addition to a telemetry backend, which keeps Logfire optional. [Pydantic online evaluation](https://pydantic.dev/docs/ai/evals/online-evaluation/).

Decision traceability does not mean hidden chain-of-thought. A reviewer should be able to reconstruct the request, trusted context, evidence, tool proposal, policy checks, approval, actual effects, before/after schedule versions, and exact software/model configuration from structured records.

### Deployment and Operations Architecture

Deploy the React SPA through CloudFront and private S3, the BFF/API as an ECS Fargate service behind ALB, and agent/solver work as an independent ECS Fargate worker service. Use RDS PostgreSQL, S3 evidence storage, ECR images, Cognito identity, Secrets Manager, CloudWatch, and hosted Logfire. Provision every environment through infrastructure as code.

API and worker use separate task definitions and least-privilege task roles. CloudWatch captures stdout/stderr and AWS health; Logfire receives sanitized OpenTelemetry directly in the MVP. An OpenTelemetry Collector is added only when centralized sampling, scrubbing, buffering, or dual export is required. Logfire is not on the correctness path.

Operational requirements include:

- readiness and liveness checks for API and worker;
- ECS deployment circuit breaker with automatic rollback;
- database migrations as a controlled deployment step;
- PostgreSQL automated backups and tested restore;
- explicit CloudWatch log retention and alarms;
- queue age, lease expiry, agent failure, solver duration, model latency/error, approval age, guardrail denial, token/cost, and evaluation-regression dashboards;
- environment and application version tags on all telemetry;
- CI gates for unit, integration, authorization, migration, solver regression, agent evaluation, dependency, container, and IaC checks.

ECS can stop and roll back a deployment that fails to reach steady state or passes insufficient health checks. [ECS deployment circuit breaker](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/deployment-circuit-breaker.html).

### Architectural Decision Summary

| Decision | Selected pattern | Rejected for MVP |
|---|---|---|
| Agent topology | One bounded scheduling agent | Multi-agent swarm |
| Application shape | Modular monolith, API/worker separation | Network microservices |
| Durable orchestration | PostgreSQL state machine and leases | In-memory waits; Temporal initially |
| Tenant deployment | Pooled SaaS with strict site context | Stack per DC by default |
| Safety | Deterministic tool gateway plus risk-tiered approval | Prompt-only guardrails |
| Agent memory | Scoped conversation and evidence summaries | Vector database/general memory |
| Audit | Transactional PostgreSQL ledger plus S3 evidence | Telemetry as audit |
| Observability | CloudWatch plus hosted Logfire Personal | Self-hosted Logfire/Kubernetes |
| Evaluation | Pydantic Evals in code/CI, Logfire visualization | Manual spot checks only |
| Async messaging | PostgreSQL jobs first | SQS/Kafka before measured need |

The explicit exclusions—multi-agent orchestration, generalized RAG, Kubernetes, service mesh, event sourcing, CQRS, sagas, generic MCP, and automatic schedule publication—make the design stronger. Each included component has a demonstrable responsibility, failure model, and evolution trigger.

## Implementation Approaches and Technology Adoption

### Technology Adoption Strategies

Adopt the target architecture through independently demonstrable vertical slices, not a rewrite. Preserve the working CP-SAT engine, pure domain objects, provider seams, frontend, numeric-grounding guard, and deterministic stub. Replace infrastructure one boundary at a time and require the existing behavior to pass before adding new agent capabilities.

The order matters:

1. PostgreSQL and tenant foundation.
2. Bounded PydanticAI agent kernel.
3. Durable agent/solver runs, approvals, and SSE.
4. Guardrails, audit, Logfire, CloudWatch, and evaluation.
5. Containerization, Terraform, Cognito, and AWS deployment.
6. SaaS onboarding and role expansion only after the portfolio release.

This sequence keeps every migration reversible. SQLite can remain available for a short local transition while repository contract tests prove PostgreSQL parity; the current constraint endpoints can coexist with the new conversation API; and Logfire remains optional throughout.

Upgrade the runtime baseline to Python 3.12 while retaining the validated OR-Tools pin. PydanticAI requires Python 3.10 or later, and stable V2 was released in June 2026. Pin resolved framework versions in `uv.lock`, use compatible upper bounds, and wrap message/tool serialization with contract tests because the project version policy allows some evolution in minor releases. [PydanticAI installation](https://pydantic.dev/docs/ai/overview/install/) and [version policy](https://pydantic.dev/docs/ai/project/version-policy/).

Prefer the slim PydanticAI distribution with only the Google, OpenRouter/OpenAI-compatible, Logfire, and retry integrations required by ShiftMind. Do not install MCP, Temporal, DBOS, Prefect, or additional provider SDKs without an implemented use case.

### Development Workflows and Tooling

Use one monorepo and one immutable backend image with distinct API and worker entrypoints. Continue `uv` and the checked-in lockfile for Python; use `npm ci` and the existing lockfile for the frontend. Add:

- Ruff for Python formatting and linting;
- mypy for application and agent-boundary type checking;
- pytest and AnyIO for backend tests;
- PostgreSQL service containers for integration tests;
- PydanticAI `TestModel` and `FunctionModel` for deterministic agent behavior;
- Pydantic Evals for versioned evaluation datasets;
- existing oxlint, TypeScript strict checking, Vitest, and Testing Library;
- Playwright for critical end-to-end flows;
- Terraform format, validate, plan, checks, and selected tests;
- dependency, secret, and container-image scanning.

The repository currently has no GitHub Actions workflow. Introduce a required pull-request pipeline:

```text
Pull request
  |-- backend lint, type check, unit and solver tests
  |-- PostgreSQL repository and migration tests
  |-- deterministic agent tests and eval smoke suite
  |-- frontend lint, type check, Vitest, codegen drift, build
  |-- Playwright critical-flow smoke tests
  |-- container build and scan
  `-- Terraform format, validation, security checks, and plan
```

PydanticAI recommends pytest, `TestModel`/`FunctionModel`, dependency/model overrides, and `ALLOW_MODEL_REQUESTS=False` to prevent accidental paid or nondeterministic calls in tests. [PydanticAI testing](https://pydantic.dev/docs/ai/guides/testing/).

Use short-lived branches and ADRs for decisions that alter security, data, agent autonomy, or AWS cost. Generated OpenAPI types remain the frontend contract; CI fails if the checked-in client no longer matches the backend schema.

Select Terraform for AWS IaC. It adds a visible, reviewable plan to the portfolio and supports formatting, validation, state locking, speculative plans, and native tests. Store remote state in a locked backend once more than one environment or operator exists. [Terraform plan](https://developer.hashicorp.com/terraform/cli/commands/plan), [state locking](https://developer.hashicorp.com/terraform/language/state/locking), and [Terraform tests](https://developer.hashicorp.com/terraform/cli/commands/test).

### Testing and Quality Assurance

Use a layered quality strategy:

**Deterministic unit/domain tests** cover CP-SAT constraints, numeric grounding, schemas, policies, state transitions, idempotency, hashes, and version checks.

**Repository/integration tests** run against real PostgreSQL and cover migrations, transactions, leases, row-level security, audit atomicity, concurrent approvals, expired leases, and cross-site denial.

**Agent component tests** use `TestModel` for broad tool-contract execution and `FunctionModel` for exact model/tool trajectories. They assert which tools were presented, selected, denied, deferred, approved, and resumed without real model traffic.

**Evaluation datasets** include:

- golden tool selection and arguments;
- forbidden-tool and excessive-agency cases;
- cross-site and role-denial attempts;
- approval required, mismatch, expiry, replay, and stale-version cases;
- grounded and fabricated numeric explanations;
- prompt injection in user text, imported data, notes, and tool results;
- malformed provider responses, timeouts, and retry budgets;
- solver infeasibility, timeout, and constraint edge cases;
- worker crash, lease recovery, and idempotent resumption.

Pydantic Evals is code-first, can persist or print reports without Logfire, and supports deterministic, custom, LLM-judge, argument-correctness, trajectory, and span-based evaluators. Prefer deterministic evaluators; use LLM judges only for helpfulness, explanation clarity, and appropriate clarification. [Pydantic Evals](https://pydantic.dev/docs/ai/evals/evals/) and [span-based evaluation](https://pydantic.dev/docs/ai/evals/evaluators/span-based/).

**End-to-end tests** exercise login, conversation, SSE reconnect, safe constraint proposal, solver launch, approval, publication, audit inspection, and logout. Playwright recommends user-visible assertions and isolated tests, with conservative CI worker settings for reproducibility. [Playwright best practices](https://playwright.dev/docs/best-practices) and [CI guidance](https://playwright.dev/docs/ci).

**Live-provider evals** run manually or on a budgeted schedule, never on every pull request. Record provider/model/version and repeat stochastic cases when comparing quality.

### Deployment and Operations Practices

Build one backend image, tag it with the Git SHA, push it to ECR, and deploy the same digest with API and worker commands. Use GitHub Actions OIDC to assume narrow AWS roles rather than storing long-lived access keys. Constrain the trust policy to the repository, protected branch, or deployment environment. [GitHub Actions OIDC for AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).

The protected deployment sequence is:

```text
approved commit
  -> assume AWS role through OIDC
  -> build, scan, attest, and push immutable image
  -> apply reviewed Terraform plan
  -> run one-off Alembic migration task
  -> deploy API and worker services
  -> execute auth/API/worker/SSE smoke tests
  -> accept deployment or invoke ECS rollback
```

Never run migrations automatically in every application replica. Use a single controlled migration task, backward-compatible expand/contract migrations, and a rollback plan that accounts for schema compatibility.

Operational runbooks cover model-provider outage, worker backlog, stuck leases, RDS saturation, failed migrations, Cognito outage, Logfire export failure, audit-integrity alerts, and cost spikes. Backups are not considered complete until a restore is tested. Define recovery point and recovery time objectives before accepting customers.

Dashboards and alarms cover:

- API error/latency and ECS health;
- agent success, failure, retry, and cutoff rate;
- tool usage, denial, approval, and timeout rate;
- job queue age, lease expiry, and solver duration;
- tokens, model latency, cost per run, and cost per completed task;
- cross-tenant denials and suspicious guardrail events;
- evaluation pass rate and regression by model/prompt/tool version;
- Logfire export health and CloudWatch logging continuity.

### Team Organization and Skills

This is a solo portfolio project, so organize work by explicit ownership artifacts rather than pretending to have multiple teams:

| Discipline | Required artifact or practice |
|---|---|
| Product/domain | Agent purpose, user stories, autonomy tiers, schedule terminology |
| Agent engineering | Prompt/tool specifications, runtime limits, eval datasets, provider contracts |
| Backend/data | Application services, PostgreSQL schema, migrations, transaction boundaries |
| Optimization | Solver invariants, deterministic fixtures, objective and performance baselines |
| Security | Threat model, tool policy, tenant-isolation matrix, approval and audit controls |
| Platform | Docker, Terraform, CI/CD, AWS networking/IAM, backup and runbooks |
| UX | Approval consequence display, progress/recovery states, audit/provenance view |

For interview presentation, prepare short architecture and failure demonstrations rather than only slides: deny a cross-site request, interrupt/recover a worker, reject a stale approval, trace a run, show an evaluation regression, and deploy/roll back an image.

The most valuable skills to demonstrate are typed agent tool design, deterministic guardrails, evaluation methodology, durable workflow design, multi-tenant authorization, distributed tracing, CP-SAT/domain integration, and practical AWS delivery.

### Cost Optimization and Resource Management

For the portfolio environment:

- use hosted Logfire Personal;
- run one API and one worker task;
- choose a small single-AZ RDS instance with automated backups;
- use CloudFront/S3 for the frontend;
- use a public ALB;
- allow ECS tasks public egress with public IPs but no direct inbound security-group access to avoid a permanent NAT Gateway charge;
- keep the worker at one instance and stop nonessential environments when inactive;
- cap model calls, tokens, agent iterations, solver time, and concurrent work;
- configure AWS Budgets and mandatory cost-allocation tags.

For a customer-facing SaaS, move ECS tasks into private subnets with controlled egress, deploy at least two API tasks, use RDS Multi-AZ, scale workers from queue age, and upgrade Logfire when uninterrupted ingestion, collaboration, retention, or compliance requires it. Consider Fargate Spot for recoverable worker capacity only after interruption and lease-recovery tests pass.

Do not cache authorization decisions or schedule mutations. Cache only immutable/versioned reads and parsed scenario artifacts. Attribute model tokens, inference expense, solver CPU time, S3 storage, and run counts to `site_id` from the beginning.

### Risk Assessment and Mitigation

| Risk | Mitigation |
|---|---|
| Scope becomes unfinishable | Deliver vertical increments with explicit exit demonstrations and maintain the exclusion list |
| Framework API changes | Pin dependencies, wrap PydanticAI, serialize through adapters, and run contract tests |
| Agent performs unauthorized work | Trusted context, narrow tools, deterministic policy, approval, and transactional audit |
| Tenant data leakage | `site_id` everywhere, repository scoping, RLS, and adversarial cross-site tests |
| Duplicate effects after retry | Stable idempotency keys, leases, compare-and-set versions, and atomic finalization |
| Missing audit evidence | Write mutations and audit together; separately record denied/failed attempts |
| Sensitive content reaches telemetry | Content capture disabled, allow-listed metadata, local redaction, and scrubbing |
| Logfire free limit or outage | Product continues; PostgreSQL audit and CloudWatch remain independent |
| Evaluation becomes subjective | Deterministic evaluators first; judges only for qualitative dimensions |
| AWS costs surprise the developer | Budget alarms, small capacity, portfolio network mode, cost-per-run telemetry |
| Architecture remains theoretical | Every milestone ends with a reproducible user or failure/recovery demonstration |

## Technical Research Recommendations

### Implementation Roadmap

**Milestone 1 — PostgreSQL and tenant spine**

- Add Docker Compose PostgreSQL, SQLAlchemy 2, Psycopg 3, and Alembic.
- Port repositories behind existing service interfaces.
- Add site/user/membership/session, audit, idempotency, and version columns.
- Seed and enforce one active planner.
- Prove existing engine/API/frontend behavior and isolation tests.

**Milestone 2 — Agent kernel**

- Add ShiftMind `AgentRuntime` and `AgentDeps`.
- Introduce versioned prompts and approved tool registry.
- Expose read tools, safe draft constraint tools, and bounded solver request.
- Add deterministic agent tests and initial golden/safety eval datasets.

**Milestone 3 — Durable execution and approvals**

- Build worker command, job leasing, heartbeats, retries, and recovery.
- Add agent-run/checkpoint/tool/approval state.
- Implement deferred solver calls and parameter-bound approvals.
- Add persisted run events, SSE replay, cancellation, and optimistic versions.

**Milestone 4 — Production trust surface**

- Complete layered guardrails and autonomy tiers.
- Add transactional audit, provenance UI/API, JSON logging, Logfire, and CloudWatch attributes.
- Build offline eval gates, sampled online evaluators, and failure-to-regression workflow.
- Run worker-kill, stale-approval, injection, tenant, and telemetry-outage exercises.

**Milestone 5 — AWS portfolio deployment**

- Add Dockerfiles and local Compose parity.
- Build Terraform for S3/CloudFront, ALB/ECS, RDS, S3 evidence, Cognito, ECR, IAM, Secrets, CloudWatch, and budgets.
- Add GitHub Actions CI/CD with OIDC and protected deployment.
- Test migrations, backup/restore, SSE, worker recovery, and ECS rollback.

**Milestone 6 — SaaS activation**

- Add invitation onboarding, roles, DC/site administration, quotas, and cost reporting.
- Introduce SQS, private/dedicated customer infrastructure, or advanced orchestration only in response to measured requirements.

### Technology Stack Recommendations

| Area | Recommendation |
|---|---|
| Runtime | Python 3.12 and existing validated OR-Tools pin |
| API | FastAPI, Pydantic v2, Uvicorn |
| Agent | PydanticAI stable V2 behind `AgentRuntime` |
| Model providers | Existing Gemini and OpenRouter support through a model factory |
| Database | PostgreSQL, SQLAlchemy 2, Psycopg 3, Alembic |
| Worker | Application-owned PostgreSQL lease loop |
| Authentication | Cognito and Authlib-based FastAPI BFF |
| Evaluation | Pydantic Evals, pytest, deterministic model doubles |
| Observability | Hosted Logfire Personal, OpenTelemetry, JSON stdout, CloudWatch |
| Object storage | Local filesystem adapter; S3 on AWS |
| Frontend | Existing React/Vite/TanStack Query/OpenAPI client |
| E2E testing | Playwright |
| Infrastructure | Terraform |
| CI/CD | GitHub Actions and AWS OIDC |
| Packaging/quality | `uv`, npm lockfile, Ruff, mypy, oxlint, strict TypeScript |

### Skill Development Requirements

Prioritize learning and demonstrating:

1. PydanticAI tools, typed dependencies, deferred calls, message checkpoints, and deterministic testing.
2. Evaluation design: datasets, deterministic oracles, trajectory/argument checks, judge calibration, and release thresholds.
3. PostgreSQL transactions, locking, RLS, optimistic concurrency, and Alembic migrations.
4. OAuth/OIDC BFF security, Cognito, CSRF, session management, and tenant isolation.
5. OpenTelemetry traces/metrics/log correlation and safe AI telemetry.
6. ECS Fargate, task roles, networking, RDS, S3, CloudFront, Secrets Manager, and rollback.
7. Terraform state, plans, modules, security checks, and environment promotion.
8. Threat modeling and incident/failure exercises for agent tools and approvals.

### Success Metrics and KPIs

- 100% of mutating tool calls have authorization, version, idempotency, and audit evidence.
- 100% of schedule publications require valid parameter-bound approval.
- Zero cross-site accesses across the tenant-isolation suite.
- 100% of completed schedules satisfy deterministic hard constraints.
- 100% of numerical agent claims pass the grounding evaluator.
- At least 90% tool-selection accuracy on the curated golden dataset before release.
- Worker crash recovery produces zero duplicate effects.
- Every agent run is searchable by `agent_run_id` across database, logs, and traces.
- Logfire failure or quota exhaustion does not fail product operations.
- Every deployment is reproducible from Terraform and an immutable image digest.
- Model tokens, solver duration, queue age, approval age, and cost per completed task are measurable.

## Research Synthesis and Strategic Conclusions

### Executive Summary

ShiftMind's strongest technical asset is not the language model. It is the combination of a real workforce-scheduling domain, a deterministic CP-SAT optimizer, and objective schedule evidence. The recommended product architecture places one bounded LLM agent at the interpretation and orchestration edge of that system while keeping identity, tenant isolation, authorization, approval, business state, solver invariants, execution, and audit under deterministic application control.

This is a timely architecture problem. AWS's June 2026 Agentic AI Lens identifies iterative reasoning, autonomous tool use, stochastic behavior, memory, and multi-agent coordination as failure and cost dimensions that ordinary request/response architecture does not address. It recommends bounded scope, observable actions, versioned behavior, explicit contracts, proportionate human oversight, evaluation, graceful degradation, and cost controls. [AWS Agentic AI Lens](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentic-ai-lens.html). OWASP's Top 10 for Agentic Applications 2026 separately highlights goal hijacking, tool misuse, and identity/privilege risks. [OWASP Top 10 for Agentic Applications](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/).

The portfolio MVP should therefore demonstrate a governed decision-and-action system, not a chat wrapper. It uses one seeded Cognito planner and one site, but implements the site/membership model, durable run state, approvals, audit ledger, evidence snapshots, evaluation datasets, and AWS process boundaries required by the later SaaS. Hosted Logfire Personal is the recommended AI observability plane; PostgreSQL and S3 remain the authoritative decision record. This is robust enough to impress technically, while invitation onboarding, multiple active users, billing, customer administration, and dedicated deployments remain later product work.

**Key technical findings:**

- One bounded scheduling agent is safer, cheaper, and easier to evaluate than a multi-agent design for the present use case.
- The model proposes tool calls; an application-owned gateway validates, authorizes, risk-classifies, approves, executes, and audits them.
- PostgreSQL must replace SQLite before public hosting because it is simultaneously the transactional domain store, durable run/job store, approval store, and audit boundary.
- Long-running solver and agent work belongs in a separate ECS worker, never a FastAPI background task or an open browser stream.
- Observability, audit, and evaluation are distinct: Logfire explains behavior, CloudWatch diagnoses AWS operations, PostgreSQL/S3 prove business actions, and Pydantic Evals measures quality.
- Tenant context must propagate from Cognito identity through membership, repository, worker, tool, audit, telemetry, and cost attribution; the model never supplies it.
- The migration should be incremental and demonstrable, preserving the working domain, solver, provider seams, frontend, deterministic stub, and grounding checks.

**Top recommendations:**

1. Migrate to PostgreSQL and establish the site/membership/audit spine before adding the agent loop.
2. Implement PydanticAI behind a ShiftMind-owned `AgentRuntime` with typed dependencies and a narrow tool registry.
3. Make every consequential action durable, idempotent, version-checked, approval-aware, and transactionally audited.
4. Build deterministic evaluations and failure exercises alongside each capability, not after feature completion.
5. Deploy with Terraform to CloudFront/S3, ALB/ECS, RDS, S3, Cognito, CloudWatch, Secrets Manager, and hosted Logfire.

### Table of Contents

1. Technical Research Introduction and Methodology
2. Technical Landscape and Architecture Analysis
3. Implementation Approaches and Best Practices
4. Technology Stack Evolution and Current Trends
5. Integration and Interoperability Patterns
6. Performance and Scalability Analysis
7. Security, Audit, and Governance
8. Strategic Technical Recommendations
9. Implementation Roadmap and Risk Assessment
10. Future Technical Outlook and Innovation Opportunities
11. Research Methodology and Source Verification
12. Technical Appendices and Reference Materials

### 1. Technical Research Introduction and Methodology

The research question was not merely how to call an LLM from FastAPI. It was how to make a scheduling assistant safe and operationally credible when it can interpret requests, choose tools, launch expensive optimization, propose mutations, and eventually affect an operational schedule.

The analysis started from the working repository rather than a greenfield diagram: a pure domain layer, CP-SAT engine, real-schema fixtures, SQLite repositories, FastAPI services, provider abstraction, deterministic stub, numeric-grounding guard, React UI, and in-process solve pool. It then evaluated the smallest architecture that adds agent autonomy without invalidating those assets.

Research used current primary documentation from Pydantic, AWS, PostgreSQL, FastAPI, SQLAlchemy, OpenTelemetry, Terraform, GitHub, NIST, OWASP, WHATWG, W3C, and Playwright. Claims about current product capabilities, plan limits, and cloud behavior were checked against official sources available on 2026-07-21. Architecture recommendations were separated from vendor facts and assigned confidence levels where usage evidence is not yet available.

The original goals—guardrails, monitoring, logging, full audit, traceable decisions, evaluation, security, resilience, and AWS deployment—were achieved as explicit components and contracts rather than a list of tools. A further insight was that the future SaaS tenant model must influence the MVP schema immediately, even though the first release deliberately permits only one active user.

### 2. Technical Landscape and Architecture Analysis

The selected pattern is a **production-shaped modular monolith with process separation**:

```text
Experience: React + FastAPI BFF + Cognito session
Control:    AuthContext + policy + guardrails + approval + state machine
Cognition:  AgentRuntime + PydanticAI + model provider
Execution:  domain services + PostgreSQL worker + CP-SAT
Evidence:   PostgreSQL audit + S3 snapshots + CloudWatch + Logfire + evals
```

The experience plane accepts intent; cognition proposes; control decides; execution changes state; evidence proves and measures. These authority boundaries are more important than the number of services.

The agent is a single-purpose scheduling assistant with explicit autonomy tiers. It can explain and inspect automatically, create reversible drafts, and launch bounded solver work. Publishing or replacing an operational schedule requires a parameter- and version-bound human approval. Administrative identity operations, unrestricted SQL, shell access, credentials, and arbitrary network access are never agent capabilities.

PydanticAI is the best fit because its typed tools, dependency injection, provider abstraction, message history, deferred calls, test models, evaluation integration, and OpenTelemetry support match the problem. It remains behind `AgentRuntime`; ShiftMind owns policy, audit, tenancy, and state. Deferred tools support the exact stop/resume boundary required by approval and external solver jobs. [PydanticAI deferred tools](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/).

### 3. Implementation Approaches and Best Practices

Implementation follows vertical migration slices:

- PostgreSQL/Alembic/site membership and audit first.
- PydanticAI agent kernel with read-only tools next.
- Durable run state, worker leases, solver deferral, approvals, and SSE next.
- Guardrails, provenance, Logfire, CloudWatch, and evaluation next.
- Cognito, Docker, Terraform, GitHub Actions, and AWS deployment last within the portfolio milestone.

Every slice ends with an executable proof. Examples include denying cross-site access, killing/recovering a worker, deduplicating a retried mutation, rejecting a stale approval, rejecting a fabricated number, continuing while Logfire is unavailable, and rolling back a failed ECS deployment.

The quality workflow uses deterministic test models by default. PydanticAI recommends `TestModel`, `FunctionModel`, overrides, and disabling real model requests during tests. [PydanticAI testing](https://pydantic.dev/docs/ai/guides/testing/). Live provider evaluations are budgeted and scheduled separately from pull-request tests.

Infrastructure changes use reviewed Terraform plans and GitHub Actions assumes AWS deployment roles using OIDC, avoiding long-lived AWS keys. [Terraform plan](https://developer.hashicorp.com/terraform/cli/commands/plan) and [GitHub OIDC for AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).

### 4. Technology Stack Evolution and Current Trends

The recommended stack is intentionally conservative around the fast-moving agent layer:

| Layer | Selection |
|---|---|
| Runtime | Python 3.12, `uv`, validated OR-Tools pin |
| API | FastAPI, Pydantic v2, Uvicorn |
| Agent | PydanticAI stable V2 behind `AgentRuntime` |
| Model access | Existing Gemini/OpenRouter choices behind a model factory |
| Persistence | PostgreSQL, SQLAlchemy 2, Psycopg 3, Alembic |
| Worker | Application-owned PostgreSQL lease loop |
| Evaluation | Pydantic Evals, pytest, deterministic model doubles |
| Observability | OpenTelemetry, hosted Logfire, JSON/CloudWatch |
| AWS | CloudFront, S3, ALB, ECS Fargate, RDS, Cognito, ECR, Secrets Manager |
| Infrastructure | Terraform and GitHub Actions OIDC |
| Frontend | Existing React/Vite/TanStack Query/OpenAPI client; Playwright E2E |

PydanticAI stable V2 was released in June 2026 and supports Python 3.10+. The project should lock exact resolved versions and isolate framework-specific history and event types because agent APIs and GenAI telemetry conventions continue to evolve. [PydanticAI version policy](https://pydantic.dev/docs/ai/project/version-policy/).

OpenTelemetry is the portability anchor. Its semantic conventions provide shared naming across platforms, but evolving GenAI attributes should never become the business audit schema. [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/).

### 5. Integration and Interoperability Patterns

The public interface uses versioned REST/JSON resources, generated OpenAPI client types, and SSE for one-way progress. Commands such as submit-turn and decide-approval require idempotency keys; state-changing commands require expected versions. SSE events carry persisted database sequences so a replacement ECS task can replay them after `Last-Event-ID`. The WHATWG specification defines reconnection and event-ID behavior. [WHATWG server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html).

Internal modules use direct typed interfaces. PydanticAI provider messages, tool objects, and message checkpoints are internal adapters; browser events and domain DTOs remain ShiftMind-owned. Agent, tool, worker, audit, log, and trace records share correlation IDs without treating those IDs as authorization evidence.

PostgreSQL is the initial durable queue. If scale later requires SQS, the database mutation, audit event, and outbox record commit together; an idempotent relay publishes. AWS recommends transactional outbox to avoid database/message dual-write inconsistency and still requires idempotent consumers. [AWS transactional outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html).

### 6. Performance and Scalability Analysis

API and worker capacity scale independently. The API is stateless; the worker has explicit solver concurrency because CP-SAT is CPU-heavy. Primary performance signals include API command latency, time to first persisted event, end-to-end agent duration, model latency, tool duration, queue age, solver duration, approval age, token usage, and cost per completed task.

Agent limits are enforced outside the model: maximum model calls, tool calls, iterations, tokens, retries, wall-clock time, concurrent runs, and solver time. Per-site quotas prevent a future tenant from consuming shared inference, database, or solver capacity. AWS recommends measurable performance targets and CI quality gates rather than optimizing averages without a user outcome. [AWS agent performance criteria](https://docs.aws.amazon.com/wellarchitected/latest/agentic-ai-lens/agentperf01-bp01.html).

PostgreSQL jobs, one API task, and one worker task are sufficient for the portfolio. Scale responses are evidence-driven: more API tasks for HTTP load; more workers for queue age; RDS Proxy for demonstrated connection churn; SQS for broker-worthy backlog or independent consumers; dedicated tenant capacity for measured noisy-neighbor or contractual isolation.

### 7. Security, Audit, and Governance

Security is layered across session, input, model, tool, application, data, infrastructure, and evidence boundaries. The deterministic tool gateway performs schema validation, trusted-context injection, authorization, tenant/resource checks, schedule-version checks, domain invariants, risk classification, approval, budget enforcement, idempotent execution, output filtering, and audit.

Cognito authenticates; current PostgreSQL membership authorizes; repository scoping and row-level security isolate. AWS explicitly distinguishes tenant isolation from authentication and general authorization. [AWS multi-tenant authorization guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-api-access-authorization/introduction.html).

The audit ledger is append-only, unsampled, access-controlled, and written transactionally with successful mutations. Failed and denied attempts are recorded through a separate reliable transaction. Evidence includes actor/site, request/run/tool/approval/job IDs, policy outcomes, safe arguments/results, resource versions, prompt/model/tool/policy/application versions, and immutable S3 references. It stores no hidden chain-of-thought.

Observability is separate. Logfire traces agent/model/tool behavior; CloudWatch retains container and AWS operational evidence. Configure PydanticAI instrumentation with content and binary capture disabled, then export allow-listed attributes. Hosted Logfire Personal is suitable for the portfolio but has finite retention and a usage cap, so its loss cannot affect correctness. [Logfire pricing](https://pydantic.dev/pricing).

### 8. Strategic Technical Recommendations

The differentiator is **deterministic optimization governed through an evaluable agent interface**. Many portfolio agents demonstrate prompting and tool calls; fewer demonstrate transactional safety, approval integrity, tenant isolation, crash recovery, decision provenance, deterministic domain oracles, and cloud operations.

The strategic decisions are:

- Build the agent around the existing scheduler, not a competing AI scheduler.
- Use one agent until independently valuable specialized agents exist.
- Implement SaaS-shaped data isolation now, SaaS onboarding later.
- Make high-risk autonomy explicit and approval-bound.
- Treat prompts, tools, models, policies, and evaluators as versioned release artifacts.
- Use Logfire for leverage, not dependence.
- Use failure demonstrations and evaluation results as portfolio proof.

The CV narrative is: *evolved a deterministic workforce optimizer into a secure, durable, evaluable agentic system deployed on AWS; integrated LLM planning and typed tools with application-owned policy, approval, tenant isolation, CP-SAT invariants, audit, observability, and evaluation.*

### 9. Implementation Roadmap and Risk Assessment

| Milestone | Outcome | Principal proof |
|---|---|---|
| PostgreSQL and tenant spine | Durable schema, one-user enforcement, audit | Cross-site request denied |
| Agent kernel | Typed PydanticAI tools behind `AgentRuntime` | Deterministic model selects and executes safe tools |
| Durable workflow | Worker, deferral, approvals, SSE | Worker kill/recovery without duplication |
| Trust surface | Guardrails, provenance, Logfire, evals | Stale approval and fabricated evidence rejected |
| AWS deployment | Terraform, Cognito, ECS/RDS/S3, CI/CD | Reproducible deploy and automatic rollback |
| SaaS activation | Invitations, roles, onboarding, quotas | Multiple isolated DC sites |

The largest risk is scope, followed by tenant leakage, duplicate side effects, framework churn, incomplete evidence, sensitive telemetry, subjective evaluation, and AWS cost. The roadmap mitigates these through vertical gates, site context everywhere, idempotency and versioning, framework adapters, transactional audit, content-minimized telemetry, deterministic evaluation-first design, and budget alarms.

### 10. Future Technical Outlook and Innovation Opportunities

Near-term evolution should improve the single agent rather than multiply agents: richer comparison tools, explainable schedule deltas, reviewed production cases feeding eval datasets, provider/model routing, calibrated uncertainty, and better cost/quality dashboards.

Medium-term SaaS work includes invitation onboarding, planner/viewer/approver/manager roles, multiple sites, tenant quotas, cost attribution, customer data-retention controls, and optional SQS-backed scaling. Dedicated infrastructure may become an enterprise deployment tier.

Advanced orchestration—Temporal/DBOS/Restate, multi-agent delegation, MCP exposure, retrieval systems, or specialized memory—should be adopted only after a workflow requires it and its security/evaluation surface is specified. This preserves architectural optionality while avoiding agent-framework fashion as a design driver.

The strongest research opportunities are schedule-specific evaluators, causal explanations of objective changes, uncertainty calibration for tool selection, adversarial tests against untrusted operational data, and human-approval UX that reduces automation bias.

### 11. Research Methodology and Source Verification

Primary sources were preferred for current technical claims. Major source groups were:

- PydanticAI, Pydantic Evals, and Logfire documentation for runtime, testing, deferred calls, observability, plans, and version policy.
- AWS Well-Architected and Prescriptive Guidance for agent architecture, ECS, Cognito, tenant isolation, messaging, IAM, CloudWatch, RDS, S3, and cost/reliability patterns.
- PostgreSQL and SQLAlchemy documentation for transactions, locking, RLS, Psycopg, and versioning.
- WHATWG, W3C, RFC, and OpenTelemetry specifications for SSE, trace propagation, HTTP preconditions, and telemetry semantics.
- OWASP and NIST for agent security, human oversight, risk management, and evaluation framing.
- Terraform, GitHub, FastAPI, and Playwright documentation for delivery and testing practices.

Web searches were executed throughout the research steps rather than only during synthesis. Unstable product facts such as Logfire pricing, retention, PydanticAI version status, and AWS capabilities were rechecked against current official pages. Architecture judgments were cross-checked against repository constraints and labeled separately from vendor guarantees.

**Confidence:** high for the MVP architecture, security invariants, PostgreSQL/worker model, evaluation approach, and AWS service mapping; medium-high for BFF and PostgreSQL-queue-first adoption choices; medium for future scale and compliance needs because no real customer workload or contract exists.

**Limitations:** no load benchmark of the target agent workflow, AWS cost model for a selected region, customer data-residency requirement, formal legal assessment, or real multi-tenant traffic exists yet. These are implementation validation tasks, not reasons to broaden the MVP now.

### 12. Technical Appendices and Reference Materials

#### Final Agent Invariant

> No model output, model memory, browser-supplied site value, or client-submitted approval can authorize an action. Only authenticated application context, current PostgreSQL membership, deterministic policy, current resource state, and a valid parameter-bound approval can do so.

#### Final Record-of-Truth Matrix

| Concern | Record of truth |
|---|---|
| User identity | Cognito issuer and subject mapped to `app_user` |
| Site authorization | Active PostgreSQL `site_membership` |
| Schedule state | Versioned PostgreSQL domain records |
| Workflow state | PostgreSQL agent run, approval, and job records |
| Business audit | Append-only PostgreSQL audit ledger |
| Large evidence | Immutable, checksummed S3 snapshots referenced by audit |
| AWS diagnosis | CloudWatch logs, metrics, events, and alarms |
| Agent observability | OpenTelemetry traces in hosted Logfire |
| Release quality | Version-controlled Pydantic Evals datasets and reports |

#### Final MVP Acceptance Gate

The portfolio MVP is complete when one authenticated planner can ask the agent to inspect and change a schedule safely; solver work survives process failure; consequential publication requires a valid approval; every action is attributable and evidence-linked; deterministic and agent evaluations pass; Logfire provides sanitized traces without becoming mandatory; and the entire system deploys reproducibly to AWS with tested rollback.

## Technical Research Conclusion

ShiftMind should not imitate a fully mature enterprise platform in its first agent release. It should implement the hard architectural truths of such a platform in compact form: bounded autonomy, explicit authority, durable state, deterministic execution, complete evidence, measurable quality, graceful failure, tenant-aware design, and reproducible operations.

That produces both an impressive portfolio and a credible product foundation. The portfolio demonstrates the difficult parts of AI engineering rather than maximizing component count. The future SaaS can activate onboarding, roles, quotas, and dedicated tiers without replacing the agent, audit, tenant, or deployment foundations established here.

**Technical Research Completion Date:** 2026-07-21  
**Research Period:** Current-state comprehensive technical analysis  
**Source Verification:** Current primary technical sources cited throughout  
**Technical Confidence Level:** High for the portfolio MVP architecture; conditional for later scale and compliance decisions
