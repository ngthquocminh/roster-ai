# Brownfield Reconciliation — Architecture Spine vs Current Code

**Reviewed:** 2026-07-22  
**Target:** `ARCHITECTURE-SPINE.md`  
**Verdict:** **CONVERGENT TARGET, HIGH-MIGRATION GAP**

The spine is credible as a target architecture and preserves the strongest existing seams: pure scheduling domain objects, a `SchedulerEngine` protocol with a CP-SAT implementation, provider-neutral LLM output, thin FastAPI routers over services/repositories, one generated frontend contract/client, and TanStack Query ownership of remote state. It is not a description of the current runtime. The live system is an unauthenticated SQLite application whose mutable scenarios, in-process worker, four-state uppercase run lifecycle, default FastAPI errors, and partly hand-authored result contract violate several target invariants. Those gaps are mostly acknowledged in the memlog and planned inputs, so they are migration work rather than reasons to reject the spine. The dangerous path is incremental feature work that assumes the new invariants exist before the persistence, identity, versioning, and worker foundations land.

## Existing conventions the spine should ratify

| Existing seam | Code evidence | Reconciliation |
| --- | --- | --- |
| Pure scheduling domain | `backend/domain/types.py`, `problem.py`, and `result.py` use stdlib dataclasses and do not import web, persistence, solver, or provider packages. | Ratifies AD-1's inward dependency direction. Keep these types framework-free during the migration. |
| Solver port and adapter | `backend/engine/base.py` defines `SchedulerEngine`; `engine/cpsat/engine.py` implements it and consumes/returns domain-owned values. | Ratifies CP-SAT as the deterministic construction boundary in AD-2. The current factory can become composition-root wiring without changing the domain contract. |
| Provider-neutral LLM seam | `backend/llm/base.py` defines `LLMProvider`; Gemini and OpenRouter translate vendor tool calls into `domain.overrides.OverrideCall`. | Ratifies the adapter principle. Preserve this translation boundary when introducing `AgentRuntime`/PydanticAI; do not expose PydanticAI messages or deferred-call types to application/domain modules. |
| Services orchestrate repositories | Routers call functions in `backend/services/*`; repositories are thin and do not commit independently. | This is the nearest brownfield analogue of application use cases. Evolve `services` behind compatibility imports instead of a disruptive all-at-once rename. |
| Repository transaction participation | `backend/store/repositories.py` executes statements but leaves commits to callers. | Ratifies the intended non-committing repository rule, although transaction ownership must move out of individual service helpers into explicit command/UoW boundaries. |
| Opaque server IDs and UTC timestamps | Scenario/run IDs use `uuid.uuid4().hex`; timestamps use timezone-aware UTC ISO output. | Compatible with the identifier/time conventions. The database migration must convert timestamp text into `timestamptz` and retain IDs as opaque strings. |
| Generated frontend contract and one client | `backend/scripts/export_openapi.py`, `frontend/src/api/schema.d.ts`, and `frontend/src/api/client.ts` establish one `openapi-fetch` client. | Directly ratifies AD-13. Close the result-response hole rather than replacing the pattern. |
| One remote-cache owner | Frontend hooks use TanStack Query; the `QueryClientProvider` is mounted above the router. | Ratifies AD-14. Keep route/local state limited to presentation/navigation. |
| Route composition | `frontend/src/App.tsx` keeps top-level composition in routes and delegates data work to hooks/components. | Compatible with the structural seed's `routes` intent. The peer surfaces need expansion, not a new routing paradigm. |
| Deterministic tests by default | `backend/pyproject.toml` excludes `live` tests by default; engine/API tests use stubs and small deterministic problems. | Ratifies the core of AD-16. Extend this convention to agent, authorization, recovery, and architecture proofs. |
| Validated solver pin | `ortools==9.11.4210` is explicit in `pyproject.toml` and resolved in `uv.lock`, with a documented 9.15 dev-machine failure. | The spine's OR-Tools pin is grounded and should remain until deliberately recalibrated. |

## Contradictions and migration hazards

### Critical foundations

1. **Current persistence cannot satisfy AD-3, AD-6, AD-8–AD-12, AD-17, or AD-18.** `backend/store/db.py` has only mutable `scenarios` and `runs` SQLite tables. There are no organizations, sites, memberships, scenario versions, conversations, messages, jobs, approvals, events, schedule versions, baselines, audit events, or evidence references. No row carries trusted site scope or a monotonic aggregate version. This is an expected planned replacement, but all agent/governance work must wait on the PostgreSQL/Alembic ownership spine or it will create a second disposable persistence model.

2. **The current worker has an unrecoverable commit/submit gap.** `run_service.create_run()` commits `PENDING`, then the router separately calls `submit_run()` into a process-local `ThreadPoolExecutor`. A process crash after commit but before/during submission leaves a permanent pending row; shutdown can cancel futures without reconciling rows; no lease, heartbeat, attempt count, compare-and-set transition, or recovery scan exists. Do not try to preserve this execution lifecycle behind a superficial status rename. Introduce the job table and separately runnable lease worker as one vertical migration.

3. **No identity, site authority, or isolation exists.** All scenario/run/override/result resources are globally addressable by opaque ID. `api/deps.py` supplies database, solver, model, and settings only; CORS is the only web security middleware. Repository methods accept no trusted context, and SQLite has no RLS equivalent. Adding Cognito at the edge without membership-derived repository scope would create authentication without tenant isolation. The safe order is schema/backfill and scoped repositories, then BFF session/Cognito, then RLS defense in depth.

4. **Scenario and run evidence is mutable and not reproducible.** `scenarios.fixture` is a filesystem path; `/fixtures` lists current files; `ingest.load_problem()` reads the file at solve time. Replacing a JSON file silently changes the meaning of an existing scenario. Constraints update the scenario's `overrides` JSON in place. Runs store no scenario/override/policy input snapshot, and `insight_service` explicitly reads the scenario's *current* overrides when describing an old run. This directly violates AD-4, AD-9, and AD-11 and can produce historically false explanations. Seed immutable `scenario_version` content/evidence and versioned proposal inputs before relying on any provenance claim.

5. **Consequential mutations have no command idempotency or optimistic version checks.** `POST /scenarios`, `POST /constraints`, and `POST /scenarios/{id}/runs` accept neither idempotency keys nor expected versions. Repeating trigger-run creates another run. `override_id()` deduplicates only a truncated content hash of `(tool,args)` inside a scenario JSON object; it is not actor/site/operation/body-scoped command idempotency and must not be reused as the job/tool-effect key promised by AD-8. Add database uniqueness and replay semantics at the application command boundary.

### Lifecycle and contract divergence

6. **Run vocabulary conflicts with AD-7.** The database and SPA use uppercase `PENDING`, `RUNNING`, `COMPLETED`, and `FAILED`; the spine fixes lowercase `queued`, `running`, `approval_required`, `completed`, `infeasible`, `timed_out`, `cancellation_requested`, `cancelled`, and `failed`. The solver's `INFEASIBLE`, `UNKNOWN`, or time-limit result is stored as `solver_status` while the workflow row becomes `COMPLETED`, so current semantics cannot be mapped by lowercasing alone. Define an explicit compatibility mapping and migrate API/frontend atomically; otherwise the current frontend's `isTerminalStatus()` treats every unknown future status as terminal, causing polling to stop for `queued`, `approval_required`, or `cancellation_requested`.

7. **State transitions are unconditional, not closed or immutable.** `RunRepo.set_running/set_completed/set_failed` update by ID with no expected prior state/version. There are no cancellation commands or terminal-state protections. The PostgreSQL migration needs compare-and-set predicates and affected-row checks; carrying these repository methods forward would undermine AD-7 even after the schema expands.

8. **SSE is absent and polling is authoritative for UX freshness.** `useRuns` polls every two seconds while it recognizes an active uppercase state. This is a valid brownfield fallback but not AD-6/AD-13's persisted event replay. Keep polling during migration as a compatibility path, but generate SSE only from committed event rows; do not stream directly from solver/thread callbacks.

9. **The public error contract is FastAPI default detail JSON, not RFC 7807.** Routers raise `HTTPException(detail=...)`, and validation produces `HTTPValidationError`. Frontend wrappers attach HTTP status by spreading the generated error body. AD-13 requires stable application codes, correlation IDs, resource IDs, and current versions. Introduce one application-error taxonomy and global HTTP mapper before independently built epics add more endpoint-specific branches.

10. **OpenAPI generation has a known escape hatch.** `/runs/{run_id}/result` has no `response_model`; `frontend/src/api/results.ts` hand-maintains `RunResult` and casts `unknown`. This contradicts the otherwise real generated-contract convention and AD-13. Add backend response models for schedule/result/evidence shapes and regenerate the client before versioned results proliferate.

11. **Frontend navigation does not yet match AD-14.** Current scenario tabs are Editor, Runs, and Results; Results is a disabled button except while on a deep link. There is no Chat or Scenario Data peer route, and no evidence-return context. This is planned feature work, but route names/URLs and query keys should be fixed early so later epics do not build incompatible scenario shells.

### Boundary and transaction hazards

12. **Services are only partially application-layer clean.** `run_service` imports concrete SQLite, filesystem ingest, store connection creation, and the executor; `constraint_service` imports concrete settings, fixture paths, repository classes, and provider protocol; `insight_service` reads persistence rows directly. The domain/engine core is clean, but merely renaming `services` to `application` would make AD-1 false. Extract ports/use cases around existing behavior and keep concrete compatibility adapters outside the new application package.

13. **Transaction ownership is inconsistent with the stated convention.** Repositories do not commit, which is good, but `scenario_service.create_scenario`, `constraint_service.parse_and_store`, and `run_service.create_run/_execute` call `conn.commit()` themselves while `get_db()` also commits after a request. The future command handler/UoW should own exactly one transaction, especially where mutation and audit must commit atomically. Avoid preserving service-local commits through the SQLAlchemy migration.

14. **Existing `OverrideCall` is intentionally loose, while AD-5 requires typed capability contracts.** It stores a tool name plus `dict[str, Any]`; five provider schemas are duplicated across Gemini/OpenRouter/stub implementations, and application validation branches by string. Preserve the provider-neutral concept, but move schemas, risk, permission, version, audit mapping, and evaluation cases into one application-owned registry. Provider adapters should render that registry rather than remain separate schema authorities.

15. **Existing LLM paths perform direct model calls inside synchronous request work.** Constraint parsing and insight generation execute within request threadpools; only solving uses the local executor. For the target durable agent, accepted messages/tool plans must be persisted before model or tool work and resumed by workflow state. Reusing these request-scoped flows as the agent loop would violate AD-6 even if PydanticAI is wrapped.

16. **Current numeric grounding is useful but weaker than AD-11.** `_grounding_guard` allows a number when it approximately matches any allowed metric value, not when a claim cites an exact version-bound record/field. It also uses the current overrides instead of a run snapshot. Keep it as a defense-in-depth text check, not as evidence provenance or calculator verification.

## Technology and version grounding

### Grounded in current manifests/locks

- FastAPI `0.138.1`, Pydantic `2.13.4`, and OR-Tools `9.11.4210` are resolved in `backend/uv.lock`.
- React `19.2.7`, React Router `8.2.0`, TanStack Query `5.101.2`, `openapi-fetch` `0.17.0`, TypeScript `5.9.3`, and Vite `8.1.5` are resolved in `frontend/package-lock.json`.
- Python `3.12` is a selected target, not the only current runtime: `backend/pyproject.toml` currently permits `>=3.10,<3.13`. The container/tooling must explicitly pin 3.12 for the spine table to become executable truth.
- Node.js `22.22.0` is not pinned by a repository runtime file. It is the minimum required by the resolved React Router package, but there is no `.nvmrc`, `.node-version`, container, or toolchain declaration. Add an explicit runtime pin.

### Explicitly planned, but not present in code/locks

PydanticAI, PostgreSQL/RDS, SQLAlchemy, Psycopg, Alembic, Logfire/OpenTelemetry, Cognito, S3, CloudFront, ALB, ECS Fargate, ECR, Secrets Manager, CloudWatch, Terraform, and GitHub Actions OIDC are explicitly selected by the PRD addendum and technical research. Their inclusion is grounded as target architecture, not brownfield implementation.

The exact future pins in the spine—PydanticAI `2.14.1`, PostgreSQL `18.4`, SQLAlchemy `2.0.51`, Psycopg `3.3.4`, Alembic `1.18.5`, Logfire SDK `4.38.0`, and Terraform `1.15.5`—are recorded as externally verified in the architecture memlog, but they do not appear in project manifests or the authoritative PRD/research at exact patch level. Treat them as dated seed selections. Add them to lockfiles/toolchain files when each technology enters code and revalidate compatibility together; the statement that lockfiles own later patch movement is appropriate only after those locks exist.

No Dockerfile, Compose file, Alembic configuration, Terraform file, CI workflow, PostgreSQL driver, identity adapter, evidence adapter, telemetry adapter, or worker entry point currently exists. Diagrams showing these components must continue to be read as target seed, not deployed topology.

## Recommended migration constraints

1. Make the first slice PostgreSQL/Alembic plus organization/site/membership, immutable scenario versions, scoped repositories, versioned runs, and transactional audit. Backfill existing scenarios/runs under the one seeded site before enabling RLS.
2. Preserve the pure domain, `SchedulerEngine`, provider-neutral translation, generated-client, and TanStack Query seams. Wrap them; do not rewrite them merely to match folder names.
3. Replace the thread executor with the job table and lease worker before introducing durable agent/approval behavior. Keep old polling as a temporary read compatibility path.
4. Introduce the new run state machine with an explicit legacy mapping and update backend schema, OpenAPI, frontend status registry, terminal predicates, and tests in one coordinated change.
5. Snapshot scenario version, proposal/tool inputs, solver configuration, policy/tool/model versions, and evidence references at acceptance time. Never generate a historical explanation from mutable current scenario state.
6. Establish application error/problem details, idempotency, expected-version handling, and UoW ownership before multiple epics add mutating commands.
7. Add typed response models for every public endpoint and make generated types the only wire-contract source before expanding Chat, approvals, evidence, and Scenario Data.

## Final assessment

No load-bearing spine decision is disproved by the current code. The core architecture direction is compatible with the brownfield's best seams and with the superseding PRD addendum. The spine should pass reconciliation as a **target contract**, with implementation-readiness conditioned on treating persistence/tenancy/versioning/worker migration as the foundation and on documenting status and contract compatibility. It should not be presented as already adopted by the runtime: today only the pure-domain, solver/provider seam, generated-client, React Query, and deterministic-test portions are materially present.
