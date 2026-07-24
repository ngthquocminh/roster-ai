# Version, Service-Reality, and Brownfield-Lock Review

**Target:** `ARCHITECTURE-SPINE.md`  
**Lens:** current technology versions, continued existence and fit, live service defaults/constraints, and brownfield-lock accuracy  
**Reviewed:** 2026-07-22  
**Verdict:** **NEEDS CHANGES — the technology families are viable, but the stack table overstates repository locks and three service invariants depend on non-default configuration that the spine does not bind.**

No named technology was found to be nonexistent or fundamentally incompatible with the proposed modular-monolith design. PostgreSQL 18.4 is available on Amazon RDS, the SQLAlchemy/Psycopg pairing supports it, Cognito supports authorization-code + PKCE, and the frontend lock is coherent with Vite 8 and Node 22. The review does not endorse the current wording as implementation-ready, however, because a lower-level builder could currently treat planned seeds as existing locks and could deploy CloudFront/ALB, PostgreSQL RLS, or S3 evidence with unsafe defaults while still claiming compliance.

## Findings

### HIGH — The stack table does not distinguish actual brownfield locks from planned seeds

The sentence at spine line 177 says that “existing rows are repository locks” and planned rows must later be added, but no row is marked `existing` or `planned`. Repository inspection produces a materially different classification:

| Stack row | Reality on 2026-07-22 | Required classification |
| --- | --- | --- |
| Python 3.12 | `pyproject.toml` and `uv.lock` allow `>=3.10,<3.13`; the checked local `.venv` is Python 3.10.9. There is no `.python-version` or exact interpreter lock. | **Planned runtime baseline**, not an existing lock |
| FastAPI 0.138.1 | Resolved in `uv.lock` and installed in `.venv`; the direct manifest says only `fastapi`. | **Existing resolved lock**, not a direct manifest pin |
| Pydantic 2.13.4 | Resolved transitively in `uv.lock` and installed. | **Existing transitive lock** |
| OR-Tools 9.11.4210 | Direct exact pin with a repository comment that 9.15 crashes on the developer machine; installed in `.venv`. | **Existing intentional compatibility lock** |
| React 19.2.7, React Router 8.2.0, TanStack Query 5.101.2, openapi-fetch 0.17.0, TypeScript 5.9.3, Vite 8.1.5 | Exact resolved versions in `package-lock.json`; direct declarations are compatible ranges. | **Existing resolved locks** |
| Node.js 22.22.0 | The host currently runs this version, but the repository has no `.nvmrc`, `.node-version`, Volta declaration, or root `engines` constraint. | **Undeclared local toolchain**, not a repository lock |
| PydanticAI, PostgreSQL/RDS, SQLAlchemy, Psycopg, Alembic, Logfire, Terraform | Absent from current manifests/infrastructure. | **Planned seeds** |

This is not editorial trivia: it controls whether implementation agents preserve a brownfield constraint or introduce a new dependency. Add an explicit `Status`/`Basis` column (for example `existing direct pin`, `existing resolved lock`, `planned seed`) and name the authoritative lockfile. Do not call Python 3.12 or Node 22.22.0 repository locks until the repository declares them.

The version selections themselves mostly exist and are coherent. FastAPI 0.138.1 is a valid brownfield resolution but is no longer the newest release; PyPI lists 0.139.2. That is acceptable only when labeled as an existing tested lock, not as the current 2026-07-22 seed. [FastAPI release history](https://pypi.org/project/fastapi/)

**Disposition:** autofix in the spine before handoff.

### HIGH — The CloudFront → ALB SSE/BFF path relies on non-default cache, forwarding, and timeout behavior

AD-6 requires replayable SSE using `Last-Event-ID`; AD-3 requires an opaque session cookie and CSRF handling; AD-17 routes API and SSE through CloudFront and ALB. The service defaults do not satisfy that contract by themselves:

- CloudFront does not forward viewer cookies, arbitrary headers, or query strings to a custom origin by default; those values require a cache policy and/or origin-request policy. `Last-Event-ID`, the application session cookie, CSRF header, and all API query strings therefore need an explicit allow-list. [CloudFront origin-request policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/controlling-origin-requests.html)
- Dynamic API and SSE behaviors need caching disabled. CloudFront documents that all minimum/default/maximum TTLs must be zero to disable caching; a positive minimum TTL can cache even responses marked `private`, `no-store`, or `no-cache`. [CloudFront cache policy semantics](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cache-key-understand-cache-policy.html)
- CloudFront's origin response timeout applies both before the first packet and between response packets. ALB's connection idle timeout defaults to 60 seconds and HTTP/2 PING frames do not reset it. A quiet SSE stream can therefore be dropped despite correct application replay logic. [CloudFront origin timeouts](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DownloadDistValuesOrigin.html), [ALB idle timeout](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/edit-load-balancer-attributes.html)

Bind a distinct `/api/*`/SSE behavior with caching disabled, exact cookie/header/query forwarding, and a server heartbeat interval below the smallest configured idle/read timeout. Bind a timeout value in Terraform or make the heartbeat contract authoritative; leaving both to defaults permits incompatible implementations. Also require the ALB origin to be inaccessible except from CloudFront (for example, the CloudFront origin-facing managed prefix list plus an origin-verification control), otherwise “API ingress is only through ALB/CloudFront” is not demonstrated merely by drawing the route.

**Disposition:** discuss exact heartbeat/timeout values, then fix AD-6/AD-17 or the conventions table.

### HIGH — “RLS supplies defense in depth” is incomplete without the database-role rule

PostgreSQL RLS is a good fit, but it is disabled by default, and table owners normally bypass it unless `FORCE ROW LEVEL SECURITY` is applied. PostgreSQL also notes that referential-integrity checks bypass row security. [PostgreSQL 18 row-security documentation](https://www.postgresql.org/docs/18/ddl-rowsecurity.html)

The spine requires trusted site context and RLS but never says which role owns tables/migrations or which role the API/worker uses. A builder can run SQLAlchemy under the migration/table-owner role, enable policies, and still bypass them while satisfying the current prose.

Bind all of the following: migrations run as a distinct owner role; API and worker connect as non-owner, `NOBYPASSRLS` runtime roles; tenant tables use `ENABLE ROW LEVEL SECURITY` plus either a non-owner runtime arrangement or `FORCE ROW LEVEL SECURITY`; connection checkout/transaction setup establishes trusted site context; negative integration tests run under the real runtime role. Treat RLS as defense in depth, not as a substitute for scoped repositories, exactly as AD-3 intends.

**Disposition:** autofix as an enforceable sub-rule of AD-3.

### MEDIUM — “Checksummed create-only S3 objects” is not an S3 default and currently overstates immutability

Without a conditional request, writing the same key overwrites an object in an unversioned or version-suspended bucket. S3 supports `If-None-Match: *`, and a bucket policy can require conditional writes. [S3 conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html), [enforcing conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html)

AD-12 should bind deterministic content/version keys, `If-None-Match: *`, a bucket policy requiring that precondition, and denial of delete/version-delete to API and worker roles. This provides application-level create-only evidence. It does **not** provide regulatory WORM; S3 Object Lock is the relevant WORM mechanism and requires versioning. The Deferred section correctly postpones regulatory WORM, so the spine should explicitly distinguish “create-only under application/IAM controls” from WORM. [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)

**Disposition:** fix terminology and implementation invariant; keep regulatory Object Lock deferred.

### MEDIUM — Several valid seed versions need a freshness/compatibility gate, not an implication of prior repository validation

- **PydanticAI 2.14.1** exists and is the current PyPI release, published 2026-07-21. It is a newly released v2 line and absent from the repository. The official project supports typed tools, approval, durable-execution integrations, testing, provider abstraction, and OpenTelemetry, so it fits the adapter role, but it needs an exact-pin spike against the selected provider extras and the owned serialization/checkpoint contracts before becoming a lock. [PydanticAI on PyPI](https://pypi.org/project/pydantic-ai/), [official project overview](https://github.com/pydantic/pydantic-ai)
- **Node.js 22.22.0** is a real LTS release and satisfies Vite 8's Node `20.19+` or `22.12+` requirement. Node 24 is now the latest LTS, so a new deployment baseline should either choose Node 24 for longer runway or record why Node 22 is deliberately retained and declare it in the repository/CI/container. [Node 22.22.0 release](https://nodejs.org/en/blog/release/v22.22.0), [Node release status](https://nodejs.org/en/about/previous-releases), [Vite 8 Node requirements](https://vite.dev/blog/announcing-vite8)
- **OR-Tools 9.11.4210** is intentionally old relative to PyPI's 9.15.6755, but it is the strongest actual brownfield lock: exact-pinned, installed, and accompanied by a repository-specific incompatibility note. Preserve it until a controlled upgrade reproduces or clears the 9.15 crash. [OR-Tools release history](https://pypi.org/project/ortools/)
- **Psycopg 3.3.4** supports Python 3.10–3.14 and PostgreSQL 10–18, and SQLAlchemy 2.0.51 has a dedicated `psycopg` dialect. The future container manifest must choose `psycopg[binary]`, `psycopg[c]`, or a pure-Python install with `libpq`; plain `psycopg` is not operationally self-contained. [Psycopg installation/support matrix](https://www.psycopg.org/psycopg3/docs/basic/install.html), [SQLAlchemy PostgreSQL dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html)

**Disposition:** retain as planned seeds, add named implementation proof gates.

## Version and Fit Check

| Technology | Spine version | Check | Result |
| --- | ---: | --- | --- |
| Python | 3.12 | Supported by the planned Python packages and within the existing `>=3.10,<3.13` range | Fit, but not locked; existing `.venv` is 3.10.9 |
| FastAPI | 0.138.1 | Present in `uv.lock`/`.venv`; PyPI current is 0.139.2 | Valid existing lock, not newest seed |
| Pydantic | 2.13.4 | Present in `uv.lock`/`.venv`; stable release exists | Valid existing transitive lock ([PyPI](https://pypi.org/project/pydantic/)) |
| PydanticAI | 2.14.1 | Official current release; Python >=3.10 | Valid planned seed; fresh major requires spike |
| OR-Tools CP-SAT | 9.11.4210 | Exact direct pin; CP-SAT exists; newer 9.15 available | Valid intentional brownfield pin |
| PostgreSQL / RDS | 18.4 | AWS added RDS support 2026-05-14; standard support listed through Sep 2027 | Valid planned seed; verify availability/default in the chosen region at plan time ([AWS release](https://aws.amazon.com/about-aws/whats-new/2026/05/amazon-rds-postgresql/), [AWS calendar](https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-release-calendar.html)) |
| SQLAlchemy | 2.0.51 | Current 2.0 docs support PostgreSQL 9.6+ and Psycopg 3 | Valid planned seed |
| Psycopg | 3.3.4 | Supports PostgreSQL through 18 and Python through 3.14 | Valid planned seed; choose installation extra |
| Alembic | 1.18.5 | Current released migration tool for SQLAlchemy | Valid planned seed ([official changelog](https://alembic.sqlalchemy.org/en/latest/changelog.html)) |
| Logfire SDK | 4.38.0 | Official current release; FastAPI/SQLAlchemy/Psycopg integrations exist | Valid planned optional telemetry seed ([PyPI](https://pypi.org/project/logfire/)) |
| Node.js | 22.22.0 | Real LTS, compatible with Vite 8 | Fit but undeclared; Node 24 is latest LTS |
| React | 19.2.7 | Exact npm lock; current stable package | Valid existing lock ([npm](https://www.npmjs.com/package/react)) |
| React Router | 8.2.0 | Exact npm lock; current package exists | Valid existing lock ([npm](https://www.npmjs.com/package/react-router)) |
| TanStack Query | 5.101.2 | Exact npm lock; 5.101.3 released after the lock | Valid existing lock, one patch behind ([npm](https://www.npmjs.com/package/%40tanstack/react-query)) |
| openapi-fetch | 0.17.0 | Exact npm lock; official package supports generated OpenAPI TypeScript types | Valid existing lock ([npm](https://www.npmjs.com/package/openapi-fetch)) |
| TypeScript | 5.9.3 | Exact npm lock | Valid existing lock; preserve until deliberate TS-major migration |
| Vite | 8.1.5 | Exact npm lock; current stable release | Valid existing lock ([npm](https://www.npmjs.com/package/vite)) |
| Terraform | 1.15.5 | Official binaries exist; no `infra/terraform` or CLI constraint exists yet | Valid planned seed ([HashiCorp release](https://releases.hashicorp.com/terraform/1.15.5/)) |

## Reality-Checked Technology Decisions That Can Stand

- A separate ECS Fargate API and worker using the same image is a supported and appropriate process boundary; it avoids relying on FastAPI in-process background work for durable CPU-heavy jobs.
- PostgreSQL 18.4 on RDS, SQLAlchemy 2.0.51, Psycopg 3.3.4, and Alembic 1.18.5 form a compatible persistence/migration set.
- Cognito User Pools supports authorization-code grants with PKCE and HTTPS token exchange. Disabling self-service sign-up and administrator-seeding one user is supported. The application/database must still enforce membership and the one-active-user product rule. [Cognito PKCE](https://docs.aws.amazon.com/cognito/latest/developerguide/using-pkce-in-authorization-code.html), [administrator-created users](https://docs.aws.amazon.com/cognito/latest/developerguide/how-to-create-user-accounts.html)
- A private S3 SPA behind CloudFront is supported, but the infrastructure should explicitly use Origin Access Control; “private S3” is not achieved by naming both services alone.
- Terraform plus GitHub Actions OIDC, immutable ECR digests, separate task roles, Secrets Manager, CloudWatch, and RDS automated backups are all live AWS mechanisms and fit the portfolio deployment.
- TanStack Query as the sole remote-cache owner and openapi-fetch over generated FastAPI OpenAPI types match the existing frontend and installed lockfile.

## Required Changes Before Final Status

1. Add per-row stack provenance (`existing direct`, `existing resolved/transitive`, `planned`) and correct Python/Node classifications.
2. Bind the CloudFront API/SSE behavior: caching disabled, precise forwarding, heartbeat, and timeout contract.
3. Bind migration-owner versus runtime database roles and the RLS enforcement/test rule.
4. Define S3 create-only enforcement and distinguish it from deferred WORM.
5. Keep fresh planned dependencies behind their stated manifest/lockfile gate, with an explicit PydanticAI provider/serialization spike and a declared Python/Node toolchain.

With those corrections, the committed technology direction is supportable by current official documentation and consistent with the brownfield repository.
