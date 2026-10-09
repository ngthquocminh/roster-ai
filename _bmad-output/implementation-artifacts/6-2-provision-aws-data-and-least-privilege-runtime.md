# Story 6.2: Provision AWS Data and Least-Privilege Runtime [Technical Enabler]
---
baseline_commit: 0cd124e (epic-6/aws-hosting, after PR #52 merged Story 6.1)
depends_on: 6-1-provision-aws-edge-identity-and-network-boundaries (done; environment applied and live)
blocks: 6-3-deploy-immutable-api-worker-and-web-releases
---

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

Date: 2026-10-09
Branch: create `epic-6/story-6.2-aws-data-runtime` from `epic-6/aws-hosting` (the 6.1 pattern). Epic 6 is a
practice deployment and does not merge to `main` unless Minh decides otherwise (`epics.md`, Epic 6
"Branch and purpose").

## Before you start (fresh context)

These are operator and machine facts that the code does not show. Account IDs, profile names, the
domain and emails are deliberately absent: this repository is public (F19).

1. **Commit the story first.** This file and the `sprint-status.yaml` change are uncommitted on
   `epic-6/aws-hosting`. Make them the first commit on the story branch,
   `docs(story-6.2): create the AWS data and least-privilege runtime story` (the 6.1 pattern).
2. **Docker Desktop must be running.** Task 1's `-m postgres` baseline needs compose's `postgres`,
   Task 3 needs a throwaway `postgres:18.4`, and Task 4 builds both images. When the daemon is down,
   the postgres tests *skip* rather than fail, so a green run without Docker proves nothing.
3. **Terraform must be 1.15.9.** Check with `terraform version`. `winget` installs 1.16.x; 6.1 put
   1.15.9 first on `PATH` (6.1 Completion Notes).
4. **AWS access is Minh's SSO session.** Task 1's read-only checks and all of Phase B need it.
   - Ask Minh to run `! aws sso login --sso-session <session>`, then set `AWS_PROFILE` to the profile
     `aws configure list-profiles` shows. Never commit either name.
   - `terraform apply` is blocked for the agent, so Minh approves each apply himself.
   - The live environment's `envs/portfolio/terraform.tfvars` and `backend.hcl` already exist locally
     (gitignored).
5. **New tfvars values come from Minh,** and only into the gitignored `terraform.tfvars`:
   - `budget_alert_email`;
   - confirm `monthly_budget_usd`.

   `github_repository` is this repository's `owner/name` from `git remote -v`.
6. **GitHub CLI.** `gh` is signed in as the repository owner with `repo` scope. Task 11's environment
   and secret setup uses it.
7. **Commits and pushes.**
   - Batch commits per task cluster, not per micro-fix.
   - Do not push or open a PR without Minh's go-ahead, and scan before every push (F19).
   - The environment bills about US$2.2/day while up. Phase A makes no AWS write.

## Story

As a portfolio operator,
I want reviewed infrastructure for persistent data and runtime identities,
so that schedules, evidence, secrets, images, logs, and cost controls remain private and least-privileged.

[Source: `_bmad-output/planning-artifacts/epics.md` — Story 6.2]

## Acceptance Criteria

Verbatim from `epics.md`. Tasks cite them by number.

1. **Given** the completed private network and identity boundary
   **When** the data/runtime Terraform plan is applied
   **Then** it provisions non-public RDS PostgreSQL, create-only versioned S3 evidence, ECR, Secrets Manager, CloudWatch, AWS Budgets/cost tags, and separate API/worker task roles
   **And** database/evidence endpoints are reachable only from their intended runtime boundary. (NFR21, AR17)

2. **Given** deployment, API, worker, lease, and owner roles
   **When** privilege tests run
   **Then** long-lived deploy keys are absent, GitHub Actions uses OIDC, runtime roles own no tables and cannot bypass RLS, and API/worker task roles receive only their required AWS actions
   **And** S3 application roles cannot delete or overwrite evidence objects. (AR23)

3. **Given** the architecture's planned infrastructure dependencies
   **When** infrastructure manifests are finalized for this gate
   **Then** immutable image digests own deployed patch movement, building on the dependency pinning Story 5.3 established locally
   **And** unused planned dependencies are not added prematurely. (AR27)

AC2's "deployment, API, worker, lease, and owner roles" is AD-23's role list: the deployment migrator,
the API and worker database logins, `shiftmind_lease`, and `shiftmind_owner`. The AWS halves of AC2
(deploy keys, OIDC, task roles, S3) are IAM. Both halves are proven here.

## Facts this story depends on

Every row is written down somewhere citable. Read the source; do not re-derive.

| # | Fact | Source |
|---|---|---|
| F1 | The RDS master user is `LOGIN NOSUPERUSER INHERIT CREATEDB CREATEROLE`, a member of `rds_superuser`, and **not** a PostgreSQL superuser. | AWS RDS User Guide, "Understanding the rds_superuser role" |
| F2 | In PostgreSQL 18, "`CREATEROLE` does not confer the ability to grant or revoke the `BYPASSRLS` privilege"; only a superuser or a role that has `BYPASSRLS` can specify it. So the RDS master cannot run `CREATE ROLE … BYPASSRLS`. | PostgreSQL 18 docs, `role-attributes.html` and `sql-createrole.html` |
| F3 | A non-superuser `CREATEROLE` creator is granted the new role `WITH ADMIN TRUE, SET FALSE, INHERIT FALSE`, and may grant it back to itself with `SET`/`INHERIT`. `createrole_self_grant` defaults to empty. | PostgreSQL 18 docs, `role-attributes.html`; `runtime-config-client.html` (`createrole_self_grant`) |
| F4 | A non-superuser `ALTER … OWNER TO r` needs to be able to `SET ROLE r`, and `r` needs `CREATE` on the object's schema. `ALTER SCHEMA … OWNER TO r` needs `r` to have `CREATE` on the database. | PostgreSQL 18 docs, `sql-altertable.html`, `sql-alterschema.html` |
| F5 | The migration chain assumes a superuser migrator. `5e2a4c9d1f70` creates `shiftmind_owner … BYPASSRLS` (lines 84-97) and runs `ALTER SCHEMA auth OWNER TO shiftmind_owner` (line 98). Its auth `SECURITY DEFINER` functions read the FORCE-RLS `membership` table before any `app.site_id` exists, and they rely on that `BYPASSRLS` to do it (comment at lines 76-83). `workflow.lease_next_job` relies on it for the FORCE-RLS `workflow.job_queue` (`a2b3c4d5e6f7`, comment at lines 207-211). | the two migrations |
| F6 | Seeding inserts into FORCE-RLS tables with no `app.site_id`: `site`, `scenario`, `scenario_version`, `fixture_lineage` and `membership`. It works today only because the provisioning role is the container superuser. | `backend/adapters/postgres/fixture_history.py` (`ensure_seed_site`, `import_fixture`); `backend/scripts/seed_planner.py` (`provision_seed_planner`); `docker-compose.yml` (`POSTGRES_USER`) |
| F7 | `bootstrap_local()` runs `alembic upgrade head`, imports the fixtures and provisions the seed planner, all through `ROSTERAI_PROVISIONING_DATABASE_URL`. | `backend/scripts/bootstrap_local.py` |
| F8 | The API and the worker both connect as `shiftmind_login`, through `ROSTERAI_DATABASE_URL`. The worker then uses `SET ROLE shiftmind_lease` / `SET LOCAL ROLE shiftmind_runtime`. The migration creates `shiftmind_login` with the literal password `'shiftmind_login'`. | `backend/settings.py:380-394`; `backend/worker/composition.py:22`; `backend/worker/lease_worker.py:30,51`; `5e2a4c9d1f70` lines 193-208 |
| F9 | No backend code calls any AWS API (there is no `boto3`/`botocore` anywhere in `backend/`). AD-12's "large evidence is written to S3" has no producer. | grep, verified at creation |
| F10 | Hosted secrets the app reads from env: `ROSTERAI_DATABASE_URL`, `ROSTERAI_PROVISIONING_DATABASE_URL`, `OIDC_CLIENT_SECRET` and `CSRF_SECRET`. The seed inputs are `SHIFTMIND_SEED_PLANNER_SUBJECT` and `SHIFTMIND_SEED_PLANNER_EMAIL`. | `backend/settings.py:373-432`; `docs/CONFIGURATION.md` |
| F11 | Container bases are tag-pinned, not digest-pinned (`Dockerfile:1-2`, `frontend/Dockerfile:1,10`). The ledger names "Epic 6's ECR work under AD-17" as the owner. | `deferred-work.md:717` |
| F12 | A bucket policy can require `If-None-Match` on `PutObject`/`CompleteMultipartUpload` with the `s3:if-none-match` condition key. Multipart needs `s3:ObjectCreationOperation` so that `CreateMultipartUpload`/`UploadPart` still work. Once a bucket enforces it, `CopyObject` into the bucket fails. | AWS S3 User Guide, "Enforce conditional writes on Amazon S3 buckets" (Example 2 is the Deny shape) |
| F13 | `hashicorp/aws` has an ephemeral `aws_secretsmanager_random_password` and the write-only arguments `aws_db_instance.password_wo`/`password_wo_version` and `aws_secretsmanager_secret_version.secret_string_wo`/`secret_string_wo_version`. Neither ephemeral values nor write-only values are stored in state or in plan files. Requires Terraform ≥ 1.11. | provider docs (v6.33); Terraform docs, "Write-only arguments" |
| F14 | Terraform 1.10's `mock_provider` could **not** mock ephemeral resource types. Whether 1.15 can is unverified. | HashiCorp Discuss thread "Terraform 1.10 Test No ephemeral resource types in mock providers" |
| F15 | GitHub OIDC: AWS ignores the `thumbprint_list`. For a job with `environment: X`, the token's `sub` is `repo:<owner>/<repo>:environment:X`. `aws-actions/configure-aws-credentials` is at v6, and it does **not** mask the account ID unless `mask-aws-account-id: true` is set. | provider docs (`iam_openid_connect_provider`); configure-aws-credentials README |
| F16 | RDS for PostgreSQL supports 18.4, which matches the spine seed. | AWS What's New, May 2026; ARCHITECTURE-SPINE "Stack" |
| F17 | CI caps skips and checks that the default run deselects exactly the `live`-marked tests (NFR26). A new pytest marker excluded by `addopts` breaks that check. | `.github/workflows/ci.yml` (NFR26 step, `--max-skipped`) |
| F18 | 6.1's outputs that 6.2 consumes: `data_subnet_ids`, `app_subnet_ids`, the `api`/`worker`/`data` security-group IDs, `oidc_client_secret` (sensitive) and `planner_subject`. Modules have no `provider` blocks. | `infra/terraform/envs/portfolio/outputs.tf`; Story 6.1 Dev Notes |
| F19 | The repository is public. Account IDs, the hosted domain and email addresses stay out of committed files and out of public Actions logs. | memory `feedback-public-repo-scan-before-push` |

No metric, demand row or assignment is touched, so `docs/DOMAIN-MODEL.md` imposes nothing on this
story.

## Decisions

These were settled at creation. The developer does not reopen them. Each one states its mechanism and
what it does **not** cover.

**D1 — Scope. 6.2 provisions the data tier and every runtime identity, and runs the first database
bootstrap on RDS. 6.3 deploys the application.** 6.2 creates:
- RDS, its parameter and subnet groups, the evidence bucket, ECR, Secrets Manager secrets, CloudWatch
  log groups, a Budget with cost allocation tags, the task and execution roles, and the GitHub OIDC
  deploy role;
- the ECS cluster and one one-off `migrate` task definition, with its security group.

It also runs that task once on RDS (D3). This moves the ECS cluster from 6.3 to here. Story 6.1's D1
gave it to 6.3, but that was a forward guess, and 6.1's D5 already reserved "the migrator/bootstrap
task's security group" for 6.2. Running the bootstrap is the only way to prove AC2's database-role
clause and AC1's reachability clause on the hosted database itself.
*Does not cover:* the API and worker task definitions and services, the LLM/Logfire/TypeSafe secrets,
the SPA build and publish, the deploy pipeline and its environment-reviewed Terraform plans, the first
sign-in, and SSE through the edge. All of those are 6.3. Backup *proof* and rollback are 6.5 (D5 only
sets the backup values on the instance it creates).

**D2 — The migration chain must run under RDS's non-superuser master. BYPASSRLS is replaced 1:1 by
an owner-exempt policy on every RLS table.** F1-F6 make the chain fail on RDS as written. The
mechanism:
1. Edit `5e2a4c9d1f70` so it runs as a `CREATEROLE` non-superuser:
   - create `shiftmind_owner` as `NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`;
   - immediately `GRANT shiftmind_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE` (F3, F4). This is
     AD-23's "only the deployment migrator may `SET ROLE` to it", made explicit. `INHERIT` is needed
     because later migrations alter and grant on owner-held `workflow.job_queue`;
   - create the schema as `CREATE SCHEMA auth AUTHORIZATION shiftmind_owner`, after the role exists,
     instead of `CREATE SCHEMA auth` + `ALTER SCHEMA … OWNER` (F4). This is the pattern `a2b3c4d5e6f7`
     already uses for `workflow`.

   No other historical migration changes except comments. Fix any further failure that D13's
   non-superuser run surfaces with the narrowest grant or reordering, and record each one.
2. A new head migration (down revision `a8b9c0d1e2f3`):
   - if `shiftmind_owner` still has `BYPASSRLS` (any existing superuser-created cluster), run
     `ALTER ROLE shiftmind_owner NOBYPASSRLS`;
   - make sure the migrator holds the membership above;
   - create one policy `<table>_owner_exempt`, `AS PERMISSIVE FOR ALL TO shiftmind_owner USING (true)
     WITH CHECK (true)`, on **every** table that has `relrowsecurity`. Enumerate them from `pg_class`
     in Python and quote the identifiers; do not use `EXECUTE format(`.

   The downgrade drops those policies and restores `BYPASSRLS` only when the current user is a
   superuser.

   Who can see what does not change. `shiftmind_owner` and the migrator, which inherits it, keep exactly
   the RLS exemption the attribute used to give, and `shiftmind_owner` stays unreachable from any
   runtime credential. Only the mechanism changes, so local, CI and RDS now share one model.
3. Update the comments that say the owner "carries BYPASSRLS". They are in `5e2a4c9d1f70`,
   `a2b3c4d5e6f7` (`renew_job_lease`), `test_identity_role_boundaries.py:91-93` and
   `test_job_leasing_postgres.py:1064`.

The API and the worker keep sharing the `shiftmind_login` database login (F8). AC2's "separate"
applies to the IAM task roles (D8). The database grants of API and worker are not split.
*Does not cover:* separate API and worker database logins (`deferred-work` entry, Task 13). It also does
not cover separation of duties, which the spine defers. An account administrator can still change the
role model; this is least privilege for runtime credentials, not tamper-proofing. Because roles are
cluster-global, running the new migration on any local database flips `shiftmind_owner` for every
database in that cluster. A local database still at the old head then loses login until
`bootstrap_local` upgrades it, which `docker compose up` does.

**D3 — One hosted bootstrap entry point: `python -m scripts.bootstrap_hosted [--require-tls]`.** It
runs, in order:
1. `bootstrap_local(settings=…)` unchanged: migrate, import fixtures, provision the seed planner (F7).
2. Rotates the `shiftmind_login` password to the one in `ROSTERAI_DATABASE_URL`, with one
   `ALTER ROLE shiftmind_login PASSWORD …` built with `psycopg.sql.Literal`. It refuses to run when that
   URL's user is not `shiftmind_login` or its password is the literal `shiftmind_login`.
3. Runs D4's checks.
4. Prints exactly one JSON line to stdout. The line holds fixture counts, `planner_created`, `tls`
   (`"required"` or `"not_requested"`) and `privileges: {passed, checks: [{name, passed, detail}]}`.
   It never contains a URL, password, host or account ID.
5. Exits non-zero on any failure.

It is idempotent: a second run replays the fixtures, reports `planner_created: false`, re-asserts the
same password and passes the same checks. Engines use `hide_parameters=True`. The migrate task
definition (D10) runs it with `--require-tls`.
*Does not cover:* proof that sign-in works. Sign-in uses the owner-exempt `membership` policy, and the
existing identity-lifecycle test proves that path; the first hosted sign-in is 6.3's. It also does not
cover a functional lease on RDS. Leasing a real job from a check would be a side effect, so the hosted
check stays read-only apart from the password rotation. Rotation is not scheduled; it happens when
D6's credentials version changes.

**D4 — The privilege checks (`backend/scripts/check_db_privileges.py`).** These are pure catalog
queries plus connection probes, run as the migrator. Each check is a named result, and "could not
determine" counts as a failure. Two-sided where possible.

| Check | Asserts |
|---|---|
| `runtime_roles_are_not_privileged` | `shiftmind_login`, `shiftmind_runtime` and `shiftmind_lease` have `rolsuper = false`, `rolbypassrls = false` and `rolinherit = false` (AD-23) |
| `runtime_roles_own_nothing` | No relation, function, schema or type is owned by a runtime role |
| `runtime_roles_cannot_reach_privileged_roles` | `pg_has_role(r, x, 'MEMBER')` is false for each runtime role `r` and each `x` in {`shiftmind_owner`, the migrator, `rds_superuser` if it exists} |
| `owner_is_unprivileged_and_unreachable` | `shiftmind_owner` has `rolcanlogin = false`, `rolsuper = false` and `rolbypassrls = false`. The non-superuser roles that can `SET ROLE shiftmind_owner` are a subset of {`current_user`} |
| `owner_holds_the_definer_objects` | `shiftmind_owner` owns the `auth` tables and functions (the exact sets in `test_identity_role_boundaries.py:105-146`), `workflow.job_queue`, and `workflow.lease_next_job` and `workflow.renew_job_lease` (`a2b3c4d5e6f7`) |
| `rls_is_forced_on_every_tenant_table` | Every table in `public` or `workflow` with a `site_id` column has `relrowsecurity` and `relforcerowsecurity`. `auth.session_index` is the AD-23 control table and is excluded by name |
| `every_rls_table_has_an_owner_exempt_policy` | For every `relrowsecurity` table, a `<table>_owner_exempt` policy exists whose roles are exactly {`shiftmind_owner`} |
| `runtime_roles_have_no_auth_table_privileges` | `has_table_privilege` is false for every runtime role on `auth.session_index` and `auth.login_handshake` |
| `login_uses_the_rotated_password` | Connecting as `shiftmind_login` with the URL's password succeeds and `current_user` is `shiftmind_login`. Connecting with the password `shiftmind_login` fails with an authentication error |
| `tls_is_required` (only with `--require-tls`) | The migrator's session reports `ssl = true` in `pg_stat_ssl`. A `sslmode=disable` connection with the same valid credentials is refused, and the error names `pg_hba`/"no encryption" |

The module exposes `run_checks(...) -> list[CheckResult]` so a postgres test can drive it against the
governed test database and against a synthetic violation.
*Does not cover:* row-level behaviour (that RLS policies filter correctly). The existing postgres suites
own that. The checks prove the role model, not every policy predicate.

**D5 — RDS.**
- Engine `postgres` `18.4` (F16), with `auto_minor_version_upgrade = false` and
  `allow_major_version_upgrade = false`. A version moves only through a reviewed plan.
- Class `db.t4g.micro` if `describe-orderable-db-instance-options` lists it for 18.4 in the region,
  else `db.t3.micro`. Record which. `gp3`, 20 GB, no storage autoscaling. `multi_az = false` (spine
  "Deferred").
- `publicly_accessible = false`. A `aws_db_subnet_group` over 6.1's data subnets.
  `vpc_security_group_ids` is only 6.1's `data` security group.
- `storage_encrypted = true`, with the AWS-managed key.
- A custom `postgres18` parameter group with `rds.force_ssl = 1`. Use the `apply_method` the engine
  defaults report for that parameter. No statement logging (`log_statement` stays at its default),
  because D3 sends a password in a DDL statement.
- `db_name = "rosterai"`. The master username is `shiftmind_migrator`, and the password comes from D6.
- `backup_retention_period = 7`, `skip_final_snapshot = false` with
  `final_snapshot_identifier = "<prefix>-db-final"`, `deletion_protection = false`,
  `copy_tags_to_snapshot = true`, `apply_immediately = true`. These are AD-17's values on the resource
  this story creates. Leaving them for 6.5 would mean creating the instance wrong, and a destroy without
  `final_snapshot_identifier` errors.
- `iam_database_authentication_enabled = false`, `performance_insights_enabled = false`,
  `monitoring_interval = 0`, and no CloudWatch log exports (D10's not-added list).

Client URLs use `sslmode=require`.
*Does not cover:*
- server-certificate verification by the client. `verify-full` needs the RDS CA bundle in the image
  (ledger entry, Task 13);
- 6.5's proof of backups and the final snapshot, and the restore drill (NFR24, deferred);
- Multi-AZ;
- the final snapshot that a teardown leaves behind. It must be deleted by hand before a second teardown
  of a re-created environment (runbook).

**D6 — Credentials are generated ephemerally and reach AWS only through write-only arguments.**
Terraform generates two passwords with the provider's ephemeral `aws_secretsmanager_random_password`
(40 characters, `exclude_punctuation = true`, so they are URL-safe and avoid RDS's forbidden
characters), plus a third one for `CSRF_SECRET`. They reach AWS only through `password_wo` and
`secret_string_wo` (F13). One local, `db_credentials_version`, drives both `*_wo_version`s. The URL
secrets also carry `replace_triggered_by = [aws_db_instance.this.id]`, so a replaced instance rewrites
the host. Nothing generated is in state or in a plan file.

| Secret (`shiftmind/<env>/…`) | Value | Env var (6.3 maps it) | Readable by (execution role) |
|---|---|---|---|
| `database-url` | `postgresql+psycopg://shiftmind_login:<generated>@<rds>:5432/rosterai?sslmode=require` (write-only) | `ROSTERAI_DATABASE_URL` | api, worker, migrate |
| `provisioning-database-url` | `postgresql+psycopg://shiftmind_migrator:<generated>@…?sslmode=require` (write-only; the same value as `password_wo`) | `ROSTERAI_PROVISIONING_DATABASE_URL` | migrate only |
| `oidc-client-secret` | `module.identity.oidc_client_secret`, as a plain `secret_string` (already in state per 6.1 D6; a plain value tracks client replacement automatically) | `OIDC_CLIENT_SECRET` | api only |
| `csrf-secret` | generated (write-only) | `CSRF_SECRET` | api only |

Every secret uses the default `aws/secretsmanager` key, has `recovery_window_in_days = 0` so a teardown
followed by a re-apply does not collide, and has no resource policy.
**Measured fallback (F14).** Task 1 first runs a throwaway `terraform test` with an ephemeral resource
under `mock_provider "aws"`.
- If mocking works, the ephemeral resources live in `modules/data`/`modules/runtime` beside their
  consumers.
- If it does not, the three ephemeral resources move into a module of their own, `modules/credentials`,
  whose only outputs are the three passwords (`ephemeral = true`). The consuming modules take
  `ephemeral = true` input variables, which tests set to literals. Every test that instantiates
  `modules/credentials` uses `override_module`.
- If `override_module` cannot supply ephemeral outputs either, **stop and report**. Do not move a
  password into state to make tests pass.

*Does not cover:* scheduled rotation; operator-supplied provider keys (`AGENT_RUNTIME_API_KEY`,
`LOGFIRE_TOKEN`, `TYPESAFE_API_KEY`), which are 6.3's and are added with the task definitions that
read them; and the Cognito client secret being in state, which 6.1 accepted.

**D7 — The evidence bucket is create-only for every principal.** `<prefix>-evidence-<account_id>`,
mirroring `modules/edge/spa_bucket.tf`'s style:
- all four Block Public Access flags, `BucketOwnerEnforced`, SSE-S3 (`AES256`), versioning `Enabled`,
  `force_destroy = true`. Destroy removes the bucket policy first, then the versions, so teardown still
  works;
- no lifecycle rule. Evidence persists until teardown (AD-17).

The policy has three `Deny` statements with `Principal = "*"`:
1. `DenyInsecureTransport` on `s3:*` over the bucket and `/*`.
2. `DenyOverwrite`: `s3:PutObject` on `/*` when `Null {"s3:if-none-match": "true"}` and
   `Bool {"s3:ObjectCreationOperation": "true"}` (F12, Example 2's shape).
3. `DenyDelete`: `s3:DeleteObject` and `s3:DeleteObjectVersion` on `/*`.

No application role is granted any S3 action (D8, F9). Because the Deny applies to everyone, it holds
whenever a writer is later granted access, and the operator can prove it live with their own
credentials.
*Does not cover:* regulatory WORM. An account admin can remove the policy (AD-23). It also does not
cover a network-path condition (`aws:SourceVpce`) for application writers. No runtime principal can
reach the bucket at all today; the first story that writes evidence to S3 grants the writer
`s3:PutObject`/`s3:GetObject` and adds that condition (ledger, Task 13). `CopyObject` into the bucket is
impossible by design (F12).

**D8 — IAM runtime roles.** Each one trusts `ecs-tasks.amazonaws.com` with an
`aws:SourceAccount = <account>` condition.

| Role | Policy |
|---|---|
| `<prefix>-api-task`, `<prefix>-worker-task` | **None**. No backend code calls AWS (F9) |
| `<prefix>-api-exec` | `ecr:GetAuthorizationToken` on `*`; `ecr:BatchGetImage` and `ecr:GetDownloadUrlForLayer` on the backend repository; `logs:CreateLogStream` and `logs:PutLogEvents` on the api log group; `secretsmanager:GetSecretValue` on `database-url`, `oidc-client-secret` and `csrf-secret` |
| `<prefix>-worker-exec` | the same ECR actions; logs on the worker group; `database-url` only |
| `<prefix>-migrate-exec` | the same ECR actions; logs on the migrate group; `database-url` and `provisioning-database-url` |

Policies are inline and resource-scoped. Do not attach `AmazonECSTaskExecutionRolePolicy`; it grants
`*` on ECR and Logs. The migrate task has no task role.
*Does not cover:* ECS Exec, and the permissions 6.3's task definitions will need for secrets 6.3 adds.
6.3 extends `api-exec`/`worker-exec`.

**D9 — GitHub OIDC deploy identity, proven by doing its one job.**
- An `aws_iam_openid_connect_provider` for `https://token.actions.githubusercontent.com`, with
  `client_id_list = ["sts.amazonaws.com"]` and no `thumbprint_list` (F15). If Task 1 finds that the
  account already has this provider, set `var.github_oidc_provider_arn`. The module then looks it up and
  does **not** manage it, so a teardown cannot delete a provider another project uses.
- The role `<prefix>-github-deploy` trusts it with `StringEquals` on
  `token.actions.githubusercontent.com:aud = sts.amazonaws.com` **and**
  `…:sub = repo:${var.github_repository}:environment:${var.github_environment}` (default `portfolio`).
  Use `StringEquals`, never `StringLike`. `max_session_duration = 3600`.
- Its only permissions: `ecr:GetAuthorizationToken` on `*`, plus `BatchCheckLayerAvailability`,
  `InitiateLayerUpload`, `UploadLayerPart`, `CompleteLayerUpload`, `PutImage`, `BatchGetImage` and
  `DescribeImages` on the backend repository.
- GitHub side, documented and run by Minh: environment `portfolio` with a deployment-branch policy of
  `epic-6/*`, and a **repository** secret `AWS_DEPLOY_ROLE_ARN`. It is repository-level so the negative
  job below can read it too.
- `.github/workflows/backend-image.yml`, on `push` to `epic-6/**` with `paths` over `Dockerfile`,
  `.dockerignore`, `backend/**`, `data/**`, `alembic.ini` and itself:
  - job `oidc-denied-without-environment` (no `environment`, `id-token: write`) first asserts the secret
    is non-empty without printing it. Its `configure-aws-credentials@v6` step must then **fail**;
  - job `publish-backend-image` (`environment: portfolio`) assumes the role with
    `mask-aws-account-id: true`. It asserts that the caller ARN contains
    `:assumed-role/<prefix>-github-deploy/` (and prints only ok/fail). It asserts that
    `aws secretsmanager list-secrets` and `aws s3api list-buckets` are both **denied**. It skips the
    build when the tag `${GITHUB_SHA}` already exists. Otherwise it builds `Dockerfile` and pushes
    `<repo>:${GITHUB_SHA}`, then writes **only** the `sha256:` digest to `$GITHUB_STEP_SUMMARY`.

*Does not cover:* required reviewers on the environment. 6.3's "environment-reviewed" deploys add them
when the role gains deploy powers; until then the role can only push one repository. Frontend assets
and deployment are 6.3's. The OIDC `sub` customization API is not used.

**D10 — ECR, digests and the not-added list (AC3).**
- One repository, `<prefix>-backend`: `image_tag_mutability = "IMMUTABLE"`, `scan_on_push = true`,
  `AES256`, `force_delete = true`, and a lifecycle that keeps the 10 most recent images (6.5 needs
  prior digests for rollback).
- The `migrate` task definition references `<repo_url>@<digest>` only. `var.backend_image_digest` is
  validated against `^sha256:[0-9a-f]{64}$` and defaults to `null`. While it is `null` the task
  definition has `count = 0`, so the first apply can create the repository before any image exists.
  The definition is Fargate, `awsvpc`, `X86_64`, 0.5 vCPU / 1 GB, logging to the migrate group, and
  runs `["python", "-m", "scripts.bootstrap_hosted", "--require-tls"]`. Its environment is
  `SHIFTMIND_SEED_PLANNER_SUBJECT` (6.1's `planner_subject`) and `SHIFTMIND_SEED_PLANNER_EMAIL`
  (`planner_email`). Its secrets are the two DB URLs.
- Pin every `FROM` in `Dockerfile` and `frontend/Dockerfile` to `<tag>@sha256:<index digest>`. Resolve
  the digests with `docker buildx imagetools inspect`. This closes `deferred-work.md:717`. The CI build
  in D9 is what verifies the pins resolve.

**Not added (AR27)**, so nobody "completes" this story by adding them:
- `boto3` or any AWS SDK in `backend/`;
- RDS Proxy, Multi-AZ, a read replica;
- KMS customer-managed keys;
- Secrets Manager rotation Lambdas;
- Performance Insights, Enhanced Monitoring, RDS log exports, Container Insights;
- a second ECR repository for the web image (the SPA is S3 assets);
- SQS, WAF;
- a NAT gateway per AZ;
- the `random` provider, registry modules, and any provider other than `hashicorp/aws`;
- API/worker task definitions and services (6.3).

*Does not cover:* re-pointing the local image-digest manifest (`deferred-work.md:693`). It is
re-pointed to Story 6.4, whose report binds image versions.

**D11 — Logs, Budget, cost tags.**
- Log groups `/shiftmind/<env>/api`, `/worker` and `/migrate`, each with `retention_in_days = 30`
  (AD-17). CloudWatch Logs encrypts at rest by default; no CMK is added.
- `aws_budgets_budget`: monthly `COST`, `var.monthly_budget_usd`, account-wide rather than
  tag-filtered. A tag-filtered budget is blind to untagged spend and reads $0 until the tags are
  activated: a guard that cannot go red. Notifications go to `var.budget_alert_email` at 80% `ACTUAL`
  and 100% `FORECASTED`.
- `aws_ce_cost_allocation_tag` sets `Project` and `Environment` to `Active`. If the API rejects a tag
  because billing has not discovered it yet (about 24 h after first use), record it and re-apply later.
  If the provider needs the Cost Explorer region, use the existing `aws.us_east_1` alias.
- Put these in the env root's `cost.tf`.

*Does not cover:* other workloads in the same account count against the budget. That is accepted for a
practice account; the runbook says so.

**D12 — Network: one `migrator` security group.** It is added to `modules/network`:
- no ingress rule at all;
- egress 443 to `0.0.0.0/0` (ECR via the NAT and the S3 gateway endpoint, Secrets Manager, Logs);
- egress 5432 to `data`;
- a new `data_from_migrator` ingress, 5432.

`data`'s ingress sources become exactly {`api`, `worker`, `migrator`}. Standalone rule resources only
(6.1 D5).
*Does not cover:* VPC interface endpoints for ECR, Secrets Manager or Logs. Egress goes through the
single NAT, and that is why the egress is 443-anywhere.

**D13 — Proof layers. None writes to `evidence/`, because Gate C reads 6.4 and 6.5 (6.1 D8 precedent).**
- *(a) Offline.*
  - `terraform test` with `mock_provider` per new module, in each changed module, and in the env root.
  - `infra.yml` gains the new module directories and a step that **fails if any directory containing
    `tests/*.tftest.hcl` is missing from the matrix**. That closes `deferred-work.md:1537-1539`.
  - New pytest guards in the default suite:
    - every `FROM` carries `@sha256:<64 hex>`;
    - no `.tf` file declares `aws_iam_user`/`aws_iam_access_key`, and no workflow references
      `aws-access-key-id`, `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY`;
    - the `bootstrap_hosted` refusal logic;
    - `check_db_privileges` against the governed test DB, plus a synthetic violation;
    - an owner-exempt-policy coverage test.

    Each guard has a synthetic violating-source case, per repository convention.
- *(b) Non-superuser bootstrap in CI.* `infra/scripts/bootstrap-nonsuperuser.sh <superuser-url>`:
  - creates `rds_master_sim LOGIN NOSUPERUSER CREATEROLE CREATEDB NOBYPASSRLS INHERIT` and a database
    it owns, on a **fresh** cluster, because roles are cluster-global (F17 rules out a pytest marker);
  - runs `bootstrap_hosted` twice as `rds_master_sim`, with a generated login password;
  - asserts both verdicts (`passed`, a check-count floor, the second run `planner_created: false`).

  A new `infra.yml` job runs it against a `postgres:18.4` service. Its `paths` gain
  `backend/migrations/**`, the two new scripts, `bootstrap_local.py`, `seed_planner.py` and
  `fixture_history.py`. It is a lower bound on RDS's master, which additionally holds
  `rds_superuser`.
- *(c) Live, operator-run with Minh's go-ahead.*
  - a two-phase reviewed apply, each followed by `plan -detailed-exitcode` = 0;
  - the `backend-image.yml` run (both jobs);
  - `infra/scripts/run-migrate.sh`;
  - `infra/scripts/smoke-data.sh` (Task 11).

*Does not cover:* a hosted functional lease or sign-in (D3), or a stub harness for the new smoke
scripts. Their checks are two-sided and fail closed instead.

**D14 — Documentation.** Extend `docs/AWS-RUNBOOK.md`:
- what exists after 6.2, and the secret/role tables;
- GitHub environment and secret setup (`gh api`/`gh secret set` commands);
- the two-phase apply;
- run-migrate, and the data smoke;
- the evidence bucket's create-only rule, and how an admin deliberately removes an object (remove the
  policy, then re-apply);
- the measured idle cost of 6.2's additions;
- the teardown additions (final snapshot left behind; secrets deleted immediately);
- its "Open against AC2" paragraph, replaced by a statement that 6.2 closed it.

Add hosted notes to `docs/CONFIGURATION.md` (URL shape with `sslmode=require`; Secrets Manager as the
hosted source). Extend `docs/TESTING.md`'s Infrastructure section with the new suites and the local
non-superuser run (`docker run -d -p 5433:5432 -e POSTGRES_PASSWORD=… postgres:18.4`).
*Does not cover:* 6.3's environment-limitations section.

## Tasks / Subtasks

### Phase A: offline (no AWS writes)

- [ ] **Task 1 — Baseline and measurements** (all ACs)
  - [ ] Branch per the header. Re-derive the test baselines before changing anything. Record each
        suite's **total and split**, because 3.12's review showed the pass/skip split moves with the
        environment while the total stays stable. The suites:
        - backend default `pytest -q`;
        - `-m postgres`;
        - frontend `vitest`;
        - every `terraform test` directory;
        - `alembic check` from the repo root.
  - [ ] Run the F14 measurement and pick D6's branch. Record the Terraform version and the exact error,
        if any.
  - [ ] Read-only AWS checks, with Minh's SSO session. Record each result:
        - `aws iam list-open-id-connect-providers` (D9's branch);
        - `aws rds describe-orderable-db-instance-options --engine postgres --engine-version 18.4`
          (D5's class);
        - `aws rds describe-engine-default-parameters --db-parameter-group-family postgres18` for
          `rds.force_ssl` (its default, and whether it applies immediately or only after a reboot);
        - `aws ce list-cost-allocation-tags --tag-keys Project Environment`.
  - [ ] Check whether `hashicorp/aws` has a newer 6.x than 6.67. If one is adopted, re-lock every root
        for all three platforms (6.1 D10). Otherwise keep `~> 6.67`.

- [ ] **Task 2 — RDS-compatible role model** (AC2; D2)
  - [ ] Make the `5e2a4c9d1f70` edits and the comment edits (D2.1, D2.3). Write the new head
        migration (D2.2).
  - [ ] Update `test_identity_role_boundaries.py`. The owner test now also asserts
        `rolbypassrls = false`, and the docstrings change.
  - [ ] Add a postgres test that every `relrowsecurity` table has its owner-exempt policy. Inject a
        synthetic violation (a throwaway RLS table with no policy) and observe it red.
  - [ ] Run the full default and `-m postgres` suites. `test_identity_store_completes_full_lifecycle_under_the_restricted_role`
        and the leasing tests must stay green; they are the functional proof of the owner-exempt
        policies. Record any test that enumerates `pg_policies` or pins the alembic head, and update it.
  - [ ] `alembic check` from the repo root: zero operations, exactly one new migration file.

- [ ] **Task 3 — Hosted bootstrap and privilege checks** (AC2; D3, D4)
  - [ ] `backend/scripts/check_db_privileges.py` per D4, and `backend/scripts/bootstrap_hosted.py` per
        D3. Absolute imports, full type hints, `hide_parameters=True`.
  - [ ] Unit tests (default suite, no DB) for the refusal rules and for the JSON line never containing
        the URL, password or host.
  - [ ] A postgres test that runs `run_checks` against the governed test DB, where every check
        passes; the TLS check is not requested. Then inject one synthetic violation per check family
        and observe it fail. Inject each one either inside a transaction the test rolls back
        (`run_checks` must then run on that connection) or on throwaway objects the test drops. For
        example: `GRANT shiftmind_owner TO shiftmind_lease`, or an RLS table without its policy.
        Roles are cluster-global, so nothing may outlive the test.
  - [ ] Write `infra/scripts/bootstrap-nonsuperuser.sh` per D13(b). Run it locally against a throwaway
        `postgres:18.4` container. Record the failures it surfaces before D2 is complete; that is the
        RDS-compatibility evidence, and each one goes in the Debug Log.

- [ ] **Task 4 — Image pins and credential guards** (AC2, AC3; D9, D10, D13a)
  - [ ] Pin the four `FROM` lines (D10). Build both images locally to prove the pins resolve, and
        record the digests.
  - [ ] Add the two guards to `backend/tests/architecture/` with synthetic violations: the `FROM`
        digest guard, extending `test_local_composition.py`, and a new `test_deploy_credentials.py`.

- [ ] **Task 5 — `modules/network`: the migrator security group** (AC1; D12)
  - [ ] Add the security group and its rules. Add `migrator_security_group_id` to the outputs.
  - [ ] Update `tests/network.tftest.hcl`:
        - `migrator` has zero ingress rules and no inline `ingress`;
        - its egress is only 443 and 5432-to-`data`;
        - `data` ingress sources are exactly {`api`, `worker`, `migrator`} on 5432.

- [ ] **Task 6 — `modules/data`** (AC1, AC2; D5, D6, D7)
  - [ ] Build RDS, its parameter and subnet groups, the two DB URL secrets, and the evidence bucket
        with its policy.
  - [ ] Write `tests/data.tftest.hcl`. Assert:
        - `publicly_accessible == false`, `storage_encrypted == true`, `multi_az == false`, engine
          `18.4`;
        - `auto_minor_version_upgrade == false`;
        - backup retention `7`, `skip_final_snapshot == false` with a final identifier,
          `deletion_protection == false`;
        - the subnet group is exactly the input data subnets, and the instance has exactly the input
          `data` security group;
        - the parameter group sets `rds.force_ssl = 1`;
        - `password` is null and `password_wo_version` is set, and no secret version has a plain
          `secret_string` except where D6 says so;
        - the URL secrets carry `replace_triggered_by`;
        - the evidence bucket has all four BPA flags, `BucketOwnerEnforced`, `AES256`, versioning
          `Enabled`, and **no** lifecycle;
        - the policy's three Deny statements have exactly D7's principals, actions, resources and
          conditions. Assert the full set, so that narrowing an action or a resource reddens (the 6.1
          review finding).

- [ ] **Task 7 — `modules/runtime`** (AC1, AC2, AC3; D1, D6, D8, D10, D11)
  - [ ] Build:
        - the ECR repository and its lifecycle;
        - the three log groups;
        - the ECS cluster (no Container Insights);
        - the two task roles and three execution roles, with their inline policies;
        - the `oidc-client-secret` and `csrf-secret` secrets;
        - the `migrate` task definition (`count` follows the digest).
  - [ ] Write `tests/runtime.tftest.hcl`. Assert:
        - the repository is `IMMUTABLE` with scan on push;
        - every log group has retention 30;
        - the task roles have no policies of any kind;
        - each execution role's `GetSecretValue` resources are exactly D6's column. Assert the exact
          set; a superset fails;
        - no policy statement has `Action = "*"`, or `Resource = "*"` outside
          `ecr:GetAuthorizationToken`;
        - every trust policy has the `aws:SourceAccount` condition;
        - the task definition image matches `@sha256:`, its command contains `--require-tls`, and it
          has no task role;
        - with `backend_image_digest = null` there is no task definition, and a malformed digest fails
          validation (`expect_failures`).

- [ ] **Task 8 — `modules/github_oidc`** (AC2; D9)
  - [ ] Build the provider (or the lookup) and the deploy role.
  - [ ] Write `tests/github_oidc.tftest.hcl`. Assert:
        - the trust uses `StringEquals` on both `aud` and `sub`, and `sub` is exactly
          `repo:<repo>:environment:<env>` for test inputs;
        - no `StringLike` appears;
        - the permissions are exactly D9's ECR actions on the repository ARN, plus
          `GetAuthorizationToken` on `*`;
        - with `github_oidc_provider_arn` set, no provider resource exists.

- [ ] **Task 9 — Env root** (AC1; D1, D11)
  - [ ] Wire the four modules. New variables:
        - `db_instance_class`, `db_credentials_version` (default `1`);
        - `backend_image_digest` (default `null`);
        - `github_repository`, `github_environment`, `github_oidc_provider_arn` (default `null`);
        - `monthly_budget_usd`, `budget_alert_email`.

        Add `cost.tf` (D11). Add outputs for everything 6.3 and the scripts consume (the RDS address,
        evidence bucket, repository URL, cluster name, task definition ARN, role ARNs, secret ARNs,
        log group names, `migrator_security_group_id`, `github_deploy_role_arn`). Mark nothing
        sensitive that is not.
  - [ ] Update `terraform.tfvars.example` with placeholders only (F19).
  - [ ] Extend `tests/portfolio.tftest.hcl`:
        - RDS receives `module.network.data_subnet_ids` and `data_security_group_id`;
        - the migrate task definition's environment carries `module.identity.planner_subject`;
        - the `oidc-client-secret` value comes from `module.identity`;
        - the budget is account-wide (no `cost_filter`);
        - both cost tags are `Active`.
  - [ ] Re-lock if Task 1 changed the provider.

- [ ] **Task 10 — CI** (AC2; D9, D13)
  - [ ] Extend `infra.yml`:
        - add the new module directories with `--min-passed` floors equal to the measured counts;
        - add the matrix-coverage step;
        - add the non-superuser bootstrap job, with its own floor on the verdict's check count;
        - extend the `paths` (D13b).
  - [ ] Add `.github/workflows/backend-image.yml` per D9. Use `permissions: contents: read` at the top,
        and `id-token: write` only on the two jobs. Do not echo the role ARN, the registry host or the
        account ID.
  - [ ] **Checkpoint (report, not a pause).** Report the Phase A results. The report must contain:
        - every terraform suite's count;
        - the backend totals and split;
        - the bootstrap-nonsuperuser result, plus the list of failures it surfaced before D2;
        - the mutation table so far.

### Phase B: live (Minh's AWS credentials, with his go-ahead at each step)

- [ ] **Task 11 — Apply, publish, bootstrap, smoke** (AC1-AC3; D13c)
  - [ ] **Apply 1** with `backend_image_digest = null`: `plan -out`, `show`, `apply tfplan`, then
        `plan -detailed-exitcode` = 0. Record the resource count and the slowest resources.
  - [ ] GitHub setup per the runbook: the environment, its branch policy, and the repository secret
        from `terraform output -raw github_deploy_role_arn`.
  - [ ] Run the public-repo scan, then push the story branch, with Minh's go-ahead. The scan covers
        patches and messages for emails, account IDs, secrets and the hosted domain. Both
        `backend-image.yml` jobs must reach their expected outcome. Record the run URL and the digest.
  - [ ] **Apply 2** with that digest: reviewed plan, then `plan -detailed-exitcode` = 0.
  - [ ] Write and run `infra/scripts/run-migrate.sh`:
        - read the terraform outputs, then `aws ecs run-task` with FARGATE, the app subnets, the
          migrator security group and `assignPublicIp=DISABLED`;
        - `wait tasks-stopped`, then require container exit code 0;
        - fetch the log stream and parse the JSON line. Require `privileges.passed`, `tls == "required"`
          and a check-count floor.

        Run it **twice**. The second run must show `planner_created: false`.
  - [ ] Write and run `infra/scripts/smoke-data.sh`. It follows the `smoke-edge.sh` conventions:
        - inputs from `terraform output -json`;
        - fatal on a missing output;
        - `tr -d '\r'` on the Python helpers' output;
        - "could not determine" is a FAIL.

        It asserts:
        1. RDS: not public, encrypted, engine 18.4, Multi-AZ off, backups 7, deletion protection off,
           the subnet group is exactly the data subnets, and the only security group is `data`.
        2. Its parameter group has `rds.force_ssl = 1`.
        3. The endpoint resolves only to addresses inside the data subnets' CIDRs, and a TCP connect to
           5432 from this machine fails.
        4. `data` ingress is exactly 5432 from {`api`, `worker`, `migrator`}, and `migrator` has no
           ingress rule.
        5. The evidence bucket: four BPA flags, versioning `Enabled`, `AES256`, `BucketOwnerEnforced`.
        6. Evidence create-only, live with the operator's own credentials, on a unique key under
           `smoke/`:
           - put with `--if-none-match '*'` → 200;
           - the same put again → 412;
           - a put without the header → 403;
           - `delete-object` → 403;
           - `delete-object --version-id` → 403;
           - `get-object` → 200.

           The probe objects stay, by design (D7).
        7. ECR: `IMMUTABLE`, scan on push. The migrate task definition's image is `@sha256:`, and that
           digest exists in the repository.
        8. The three log groups exist with retention 30.
        9. The four secrets exist, have an `AWSCURRENT` version, and have no resource policy.
        10. `simulate-principal-policy` against D6/D8/D9, **two-sided**:
            - each execution role is allowed its own secrets and denied every other secret;
            - both task roles are denied the same action list that some execution role is allowed (this
              proves the harness can see an allow);
            - the deploy role is allowed `ecr:PutImage` on the backend repository and denied it on any
              other repository ARN. It is also denied `secretsmanager:GetSecretValue`,
              `s3:DeleteObject` on evidence, and `iam:CreateAccessKey`.
        11. Both task roles have zero attached and zero inline policies.
        12. The deploy role's trust is the GitHub provider, with `StringEquals` on `aud` and the exact
            `sub`.
        13. No IAM user in the account has an active access key. `gh secret list` (repository and
            environment) holds no `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`.
        14. The budget exists with D11's notifications, and both cost tags are `Active`.
  - [ ] Paste the run-migrate and smoke outputs, the versions, and both `-detailed-exitcode` results
        into Completion Notes, with the account ID and domain redacted (F19). Write no `evidence/` file
        (D13).
  - [ ] Leave the environment applied for 6.3 unless Minh says otherwise. Record the apply date and the
        new daily cost.

- [ ] **Task 12 — Mutation table** (all ACs; retro action A2)
  - [ ] Observe every new guard failing for its stated reason, then restore it. At minimum:
        - Rows M1-M7:
          - M1: restore `BYPASSRLS` in `5e2a4c9d1f70` → the non-superuser bootstrap fails at
            `CREATE ROLE`;
          - M2: drop the membership grant → it fails at `CREATE SCHEMA … AUTHORIZATION`;
          - M3: drop `membership`'s owner-exempt policy → the identity-lifecycle test goes red, and
            the non-superuser seeding fails;
          - M4: drop `job_queue`'s owner-exempt policy → the leasing tests go red;
          - M5: grant `shiftmind_owner` to `shiftmind_login` → D4 goes red;
          - M6: add an RLS table without the policy → the coverage test goes red;
          - M7: skip the password rotation → `login_uses_the_rotated_password` goes red.
        - One row per Terraform assertion family, in the 6.1 style (before/after counts).
        - The two architecture guards.
        - The two-sided simulation, by pointing one execution role at the wrong secret ARN.

        Record a first attempt that errored in configuration rather than in an assertion as not
        counting, as 6.1 did.

- [ ] **Task 13 — Documentation and ledger** (D14)
  - [ ] Update the runbook, `CONFIGURATION.md` and `TESTING.md` per D14. Measure the idle cost from
        the AWS price lists for `ap-southeast-1`; do not copy a figure from this story.
  - [ ] In `deferred-work.md`:
        - **close** `:717` (D10) and `:1537-1539` (D13a);
        - **re-point** `:693` to Story 6.4 (D10);
        - **add** entries for:
          - separate API and worker DB logins (D2);
          - client-side `verify-full` (D5);
          - an `aws:SourceVpce` condition for the first evidence writer (D7);
          - required reviewers on `portfolio` (D9);
          - the GitHub OIDC provider ownership if it was pre-existing (D9).

          Each entry gets an owner or a trigger.

## Dev Notes

### Files

All files are new unless marked UPDATE.

```text
backend/migrations/versions/<rev>_replace_owner_bypassrls_with_policies.py
backend/scripts/{bootstrap_hosted.py, check_db_privileges.py}
backend/tests/{test_bootstrap_hosted.py, test_db_privileges_postgres.py}
backend/tests/architecture/test_deploy_credentials.py
infra/terraform/modules/data/{versions.tf, main.tf, evidence_bucket.tf, secrets.tf, variables.tf, outputs.tf, tests/data.tftest.hcl}
infra/terraform/modules/runtime/{versions.tf, ecr.tf, logs.tf, ecs.tf, iam.tf, secrets.tf, variables.tf, outputs.tf, tests/runtime.tftest.hcl}
infra/terraform/modules/github_oidc/{versions.tf, main.tf, variables.tf, outputs.tf, tests/github_oidc.tftest.hcl}
[infra/terraform/modules/credentials/…  only if D6's fallback is taken]
infra/terraform/envs/portfolio/cost.tf
infra/scripts/{bootstrap-nonsuperuser.sh, run-migrate.sh, smoke-data.sh}
.github/workflows/backend-image.yml
UPDATE backend/migrations/versions/5e2a4c9d1f70_add_seeded_site_identity.py   (D2.1, comments)
UPDATE backend/migrations/versions/a2b3c4d5e6f7_add_job_queue_and_lease_functions.py  (comments only)
UPDATE backend/tests/test_identity_role_boundaries.py, backend/tests/test_job_leasing_postgres.py (D2.3)
UPDATE backend/tests/architecture/test_local_composition.py  (FROM digest guard)
UPDATE Dockerfile, frontend/Dockerfile  (D10 pins)
UPDATE infra/terraform/modules/network/{security_groups.tf, outputs.tf, tests/network.tftest.hcl}  (D12)
UPDATE infra/terraform/envs/portfolio/{main.tf, variables.tf, outputs.tf, terraform.tfvars.example, tests/portfolio.tftest.hcl}
UPDATE .github/workflows/infra.yml
UPDATE docs/AWS-RUNBOOK.md, docs/CONFIGURATION.md, docs/TESTING.md
UPDATE _bmad-output/implementation-artifacts/deferred-work.md
```

### Current state of the files being modified

| File | Today | This story changes | Must be preserved |
|---|---|---|---|
| `5e2a4c9d1f70` | Creates `auth`, then the owner with `BYPASSRLS`, then `ALTER SCHEMA auth OWNER`. Creates `shiftmind_login` with password `'shiftmind_login'` and grants it `shiftmind_runtime`. Defines five `SECURITY DEFINER` auth functions owned by the owner | Role attribute, the self-grant, schema-by-`AUTHORIZATION` ordering, comments (D2.1) | Every function body, every grant and revoke, the downgrade order, and the `IF NOT EXISTS` idempotence of each role |
| `a2b3c4d5e6f7` | Already uses `CREATE SCHEMA workflow AUTHORIZATION shiftmind_owner`; owns `job_queue` and the lease functions | Comments only | Every string `test_lease_role_boundaries.py` asserts (lines 61-87) |
| `bootstrap_local.py` | Migrate, fixtures and planner through the provisioning URL | **Nothing.** `bootstrap_hosted` calls it | Its local behaviour and the compose `bootstrap` service |
| `test_identity_role_boundaries.py` | Proves the login/runtime/owner boundaries locally; its lifecycle test runs the real store as `shiftmind_login` | Add an owner `rolbypassrls = false` assertion and update the docstring | Every existing assertion |
| `modules/network` | 4 SGs, standalone rules; 10 tests | +1 SG, +3 rules, +1 output, test updates | Every 6.1 assertion and the `smoke-edge.sh` check 12 semantics |
| `envs/portfolio` | Wires network/edge/identity; 7 tests | +3 modules, `cost.tf`, variables and outputs | Every 6.1 output, which `smoke-edge.sh` reads |
| `infra.yml` | 5-entry matrix, offline only | New entries, a coverage step, the non-superuser job, extended paths | No AWS credentials and no `id-token` in this workflow |
| `Dockerfile`s | Tag-pinned bases | `@sha256:` digests | Every other line (the `test_local_composition.py` assertions) |

### What must not change

- `.github/workflows/ci.yml`: triggers, jobs and floors (D13 puts new CI in `infra.yml`).
- No new runtime Python dependency (`backend/pyproject.toml` and `uv.lock` stay unchanged). psycopg's
  `sql` module and SQLAlchemy's `make_url` are already available.
- `backend/settings.py`: no new setting. The hosted bootstrap reads the existing env vars (F10).
- `AGENT_TRACE_CONTENT_MODE` must not appear in any `.tf` file or workflow
  (`test_trace_export_boundaries.py`; 6.3 AC3).
- `docker-compose.yml`, `frontend/nginx.conf`, the application routes, and the frontend source.
- Story 6.1's resources. The two applies must show **no** change to 6.1's edge or identity resources.
  Network gains only additions.

### What Story 6.3 inherits (record it in the runbook; do not build it)

- The cluster, `api-exec`/`worker-exec`, `api-task`/`worker-task`, the log groups, and D6's secret to
  env-var mapping.
- Re-running `migrate` with each new digest as a deploy step.
- Extending the deploy role and adding required reviewers.
- The LLM, Logfire and TypeSafe secrets.
- The 6.1 deferrals (`index.html` caching, `explicit_auth_flows`, `logout_urls`).

### Testing standards

- **Mock providers.** The `mock_provider` notes in 6.1's Dev Notes still hold:
  - use `command = apply` for computed values;
  - `override_data` for indexed data sources;
  - a mocked data source's `id` is null;
  - assertions reach `module.x.<output>` only from a calling root.
- **Write-only arguments.** Their values are never visible to assertions. Assert the
  `*_wo_version` attributes and the absence of the plain attributes.
- **Floors and mutations.** Pass counts are floors, skips are zero, and every guard needs an observed
  red (Task 12).
- **Postgres tests.** They use `governed_postgres_engine` (`backend/conftest.py:129-141`), a throwaway
  database migrated by the local superuser. The **non-superuser** proof needs a fresh cluster and lives
  in D13(b), not in pytest (F17).
- **Smoke conventions.** New smoke checks follow `smoke-edge.sh`'s Windows lessons: `tr -d '\r'`;
  `/c/...` paths in `PATH`; invoke the script with `bash`.

### Latest technical notes (researched 2026-10-09)

- RDS's master has no `BYPASSRLS`, and `CREATEROLE` cannot grant it (F1, F2). This is the load-bearing
  finding of this story. D2 is the response; the alternative was finding out at 6.3's first deploy.
- S3 conditional-write enforcement mirrors AWS's Example 2, with `s3:if-none-match` in place of
  `s3:if-match`. AWS CLI v2 supports `aws s3api put-object --if-none-match '*'`.
- `configure-aws-credentials@v6`. Thumbprints are ignored for GitHub. The account ID is unmasked by
  default (F15).
- Ephemeral and write-only arguments need Terraform ≥ 1.11. The repository uses 1.15.9. Whether
  `mock_provider` can mock an ephemeral resource is unverified (F14), which is why D6 has a measured
  fallback.
- Possible first-time account effects: the ECS and RDS service-linked roles are created on first use.
  An `aws_ce_cost_allocation_tag` fails until billing has discovered the tag (D11).

### Approximate cost, for Task 13 to verify

6.2 adds:
- the RDS instance-hours plus 20 GB of gp3 (the largest addition);
- four secrets at about $0.40 each per month;
- ECR storage at about $0.10 per GB-month for at most 10 images;
- negligible log ingestion, and Budgets within the free allowance.

Expect roughly $15-30 per month on top of 6.1's ~$65.6. This is for orientation only; Task 13 measures
it.

### References

- `_bmad-output/planning-artifacts/epics.md`: the Epic 6 header and Stories 6.1-6.5.
- `_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md`:
  AD-12, AD-17, AD-23, the AD-24 scope note, "Stack", "Deferred".
- `_bmad-output/implementation-artifacts/6-1-provision-aws-edge-identity-and-network-boundaries.md`:
  D1, D5, D6, D8, D10, the Testing standards, and the Review Findings.
- `_bmad-output/implementation-artifacts/deferred-work.md`: `:693`, `:717`, `:1506-1539`.
- The code in F5-F10. `docs/AWS-RUNBOOK.md`, `docs/CONFIGURATION.md`, `docs/TESTING.md`.

## Self-consistency pass (at creation)

- **Task proofs vs Decisions.**
  - Smoke item 6 expects 403 for a put without the header and for deletes *by the admin operator*.
    This is reachable because D7's Denies use `Principal "*"`, and an explicit Deny beats the admin's
    Allow.
  - run-migrate's `tls == "required"` is reachable because D10's command carries `--require-tls`.
  - `login_uses_the_rotated_password` is reachable because D3 step 2 runs before D4.
  - The owner check "SET-capable roles ⊆ {current_user}" holds on RDS because D2.1 grants the master
    the membership, and locally because the superuser is excluded by `rolsuper`.
  - The negative OIDC job fails because its token's `sub` is not `environment:portfolio` (D9).
  - The positive job's denied calls are denied because D9 grants only ECR.
  - Apply 1 with no digest is valid because D10 sets `count = 0`.
  - The CI non-superuser run seeds successfully only because D2.2's policies cover `site`,
    `scenario*`, `fixture_lineage` and `membership` (F6).

  No task proves a state that a Decision makes unreachable.
- **Restatement check.** Tasks cite D- and F-numbers. Test assertion lists enumerate *what* to assert;
  the reasons live only in the Decisions. D2 is the only place that explains why the owner loses
  `BYPASSRLS`.
- **AC coverage.**
  - AC1: Tasks 5-9 and 11 (smoke 1-9, 14; run-migrate is the positive reachability proof).
  - AC2: Tasks 2-4, 6-8, 10 and 11 (smoke 6, 10-13; run-migrate's verdict; the OIDC jobs).
  - AC3: Tasks 4, 7 and 11 (smoke 7) and D10's not-added list.
  - 6.1's AC2 clauses left open until 6.2 close here: RDS requires TLS (D5 and `tls_is_required`),
    and RDS, logs and secrets are encrypted at rest (D5, D11, D6).

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

### Change Log

- 2026-10-09: Story created (bmad-create-story). Ultimate context engine analysis completed: comprehensive developer guide created.
