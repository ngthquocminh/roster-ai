# Story 6.1: Provision AWS Edge, Identity, and Network Boundaries [Technical Enabler]
---
baseline_commit: 11da75a (epic-6/aws-hosting, branched from the v0.5 tag; Gate B passed)
depends_on: 5-13-assess-gate-b (done)
blocks: 6-2-provision-aws-data-and-least-privilege-runtime ("Given the completed private network and identity boundary")
---

Status: in-progress

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

Date: 2026-10-07
Branch: `epic-6/aws-hosting`. Epic 6 is a practice deployment and does not merge to `main` unless
Minh decides otherwise (`epics.md`, Epic 6 "Branch and purpose"). Nothing here touches `main`'s
Gate B claim.

## Story

As a portfolio operator,
I want reviewed infrastructure code for the hosted edge, identity, and network,
so that browser access reaches only the intended private application boundary.

[Source: `_bmad-output/planning-artifacts/epics.md` — Story 6.1]

## Acceptance Criteria

Verbatim from `epics.md`. Tasks cite them by number. D1 scopes which resources AC2 can bind in this story.

1. **Given** the portfolio Terraform environment
   **When** initialization, validation, and reviewed plan run
   **Then** it provisions Route 53/ACM, CloudFront, a private S3 SPA with OAC, ALB, Cognito with public sign-up disabled, and private API/worker/data network boundaries
   **And** no console-only resource is required for a reproducible environment. (NFR21, AR17)

2. **Given** public and service-to-service connections
   **When** transport/storage policy is inspected
   **Then** public hops and CloudFront-to-ALB use HTTPS/TLS 1.2+, RDS requires TLS, and S3/RDS/logs/secrets use encryption at rest with Block Public Access
   **And** API ingress is only through ALB/CloudFront while the worker has no inbound listener. (AR17)

## Facts this story depends on

Every fact below is written down somewhere citable. The developer reads the cited source; nothing
here is re-derived from memory.

| # | Fact | Source |
|---|---|---|
| F1 | Every product API route is under `/api/v1/`. `/health` is unprefixed. The legacy `/fixtures`, `/scenarios`, `/runs`, `/constraints` routers are unprefixed and are not used by the SPA. The fake IdP's `/oidc/*` routes mount only when `OIDC_PROVIDER=fake`. | `backend/api/main.py:418-432` |
| F2 | The BFF callback is `/api/v1/auth/callback`. The Cognito adapter requests scope `openid email`, uses PKCE `S256`, and accepts an optional client secret. | `backend/api/routers/auth.py`, `backend/adapters/cognito/oidc.py:97-115`, `backend/application/ports/identity.py:48-55` |
| F3 | The adapter rejects discovery metadata whose `issuer` differs from the configured `OIDC_ISSUER`, after stripping a trailing slash. | `backend/adapters/cognito/oidc.py:66-67` |
| F4 | Unsafe methods (POST/PUT/PATCH/DELETE) on `/api/v1/*` need an `Origin` (or `Referer`) in `{APP_BASE_URL} ∪ CORS_ORIGINS`, an `x-csrf-token` header, and the session cookie. The edge must forward all three unchanged. | `backend/api/main.py:233-310` |
| F5 | The session cookie is `Secure`, `HttpOnly`, `SameSite=Lax`, `path=/`. Sign-in therefore only works over HTTPS end to end. | `backend/api/routers/auth.py` (`callback`, `set_cookie`) |
| F6 | SSE heartbeat is fixed at 15 s. CloudFront must disable caching for auth/API/SSE; forward query strings, cookies, Origin, CSRF and `Last-Event-ID`; and use an origin response timeout above the heartbeat. The ALB idle timeout must also be above it. | `backend/api/routers/conversations.py:133-141`; AD-21 |
| F7 | The local stack is same-origin: nginx serves the SPA and proxies `/api/` to the API with buffering off. Hosted CloudFront replaces nginx in that role. | `frontend/nginx.conf`, `docker-compose.yml` (`web`) |
| F8 | The API listens on port 8000 and serves `GET /health`. | `Dockerfile` (`CMD`), `docker-compose.yml` (`api.healthcheck`) |
| F9 | Membership is keyed by OIDC `sub`. `SHIFTMIND_SEED_PLANNER_SUBJECT` must equal the subject the IdP issues, or every read returns 403. A Cognito `sub` is a server-generated UUID, so it is known only after the user exists. | `docs/CONFIGURATION.md` (`SHIFTMIND_SEED_PLANNER_SUBJECT`), `backend/scripts/seed_planner.py` |
| F10 | Gate C topology is one API task and one worker task. Multi-AZ, RDS Proxy and multiple tasks are deferred. | AD-24 scope note; ARCHITECTURE-SPINE "Deferred" table |
| F11 | Target topology: CloudFront serves a private-S3 SPA and routes API/SSE through the ALB to the ECS API. RDS sits in private subnets. API ingress is only through ALB/CloudFront, and the worker has no inbound listener. All public hops use TLS 1.2+. S3 is protected by Block Public Access and OAC. | AD-17 |
| F12 | Terraform seed version is 1.15.8, constrained with `required_version` and validated in CI. Infra lives under `infra/terraform/` as environment roots plus reusable AWS modules. | ARCHITECTURE-SPINE "Stack" and "Structural Seed" |

No metric, demand row or assignment is touched, so `docs/DOMAIN-MODEL.md` imposes nothing on this
story.

## Decisions

These were settled at creation. The developer does not reopen them. Each one names the mechanism
and what it does **not** cover.

**D1 — Scope: 6.1 creates the network, edge, identity and state backend only.** It creates the VPC,
subnets, NAT, security groups, the S3 gateway endpoint, Route 53 records, both ACM certificates,
CloudFront, the SPA bucket with OAC, the internal ALB with its HTTPS listener and an empty API target
group, Cognito, and the Terraform state bucket. RDS, the evidence bucket, ECR, Secrets Manager,
CloudWatch log groups, Budgets, IAM task roles and GitHub OIDC belong to Story 6.2. The ECS cluster,
services and task definitions belong to Story 6.3. 6.2's first AC opens with "Given the completed
private network and identity boundary", which places this split in the epic itself.
*Does not cover:* AC2's "RDS requires TLS" clause and the RDS/logs/secrets halves of its
encryption-at-rest clause have no resource to bind until 6.2. 6.1 meets AC2 for every resource it
creates (SPA bucket, state bucket, CloudFront, ALB, security groups), and it builds the private data
subnets and the data security group those resources will use. AC2 is fully met only once 6.2 lands.
Record this in Completion Notes; do not create a placeholder RDS or secret to tick the clause.

**D2 — CloudFront reaches an *internal* ALB through a CloudFront VPC origin.** We do not use a
public ALB guarded by a secret header. The ALB is `internal = true` in the private app subnets.
`aws_cloudfront_vpc_origin` points at it with `origin_protocol_policy = "https-only"` and TLSv1.2.
The ALB security group allows inbound 443 only from the AWS-managed prefix list
`com.amazonaws.global.cloudfront.origin-facing` (VPC-origins docs, "Option 1"). Because CloudFront
validates the origin certificate against the origin domain name, and an `internal-*.elb.amazonaws.com`
name cannot carry an ACM certificate, the origin hostname is `origin.<app_domain>`. That is a Route 53
alias to the internal ALB, with a regional ACM certificate for that name on the ALB listener. VPC
origins also need an internet gateway attached to the VPC, which D5 provides anyway.
*Does not cover:* authentication. Every viewer request on `/api/*` still reaches the ALB, and
authentication and authorization stay the API's job (AD-3). The public `origin.<app_domain>` record
also discloses the ALB's private IPs. Those addresses are unroutable from the internet, and this
story accepts the disclosure.

**D3 — Two ACM certificates, DNS-validated in an existing public hosted zone.** One certificate is
in `us-east-1` for the CloudFront alias `<app_domain>`, as CloudFront requires. The other is in the
ALB region for `origin.<app_domain>`. The env root looks the hosted zone up with
`data "aws_route53_zone"` by name and passes `zone_id` into the modules, so the modules stay testable
without the data source. Registering the domain and the hosted zone that registration creates are
documented prerequisites, not Terraform resources. They are a billing act, not reproducible
infrastructure.
*Does not cover:* buying the domain, or delegating NS records at a third-party registrar. The
runbook (D11) states both as prerequisites.

**D4 — CloudFront behaviors.** This story configures them. Story 6.3 proves streaming through them
end to end, under its own AC.
- *Default behavior → S3 SPA origin.* Methods `GET`/`HEAD`. `viewer_protocol_policy = "redirect-to-https"`.
  Managed `CachingOptimized` cache policy. `compress = true`. A **CloudFront Function (cloudfront-js-2.0) on
  viewer-request** rewrites any URI whose last path segment has no `.` to `/index.html`, so React
  Router deep links work. **No `custom_error_response`.** Error responses are distribution-wide, so a
  403/404 → `/index.html` mapping would also rewrite the API's own RFC 7807 401/403/404 responses,
  including the CSRF 403 from F4, into an HTML 200.
- *Ordered behavior `/api/*` → ALB VPC origin.* All seven methods are allowed (`GET HEAD OPTIONS PUT POST
  PATCH DELETE`). Story 6.4's mutation-denial probes need the API's own denial to answer them, not a
  CloudFront 403. Cached methods are `GET`/`HEAD`. Managed `CachingDisabled` cache policy. Managed
  `AllViewerExceptHostHeader` origin request policy, which forwards every cookie, every query string,
  `Origin`, `x-csrf-token` and `Last-Event-ID` (F4, F6). `viewer_protocol_policy = "https-only"`,
  because a 301 on a POST would lose the body. `compress = false`. On the origin, `origin_read_timeout = 60`,
  above the 15 s heartbeat (F6), and **`response_completion_timeout` left unset**. Setting it would cap
  an SSE stream's total lifetime.
- *ALB.* `idle_timeout = 60`, set explicitly and above the 15 s heartbeat (F6). `drop_invalid_header_fields = true`.
  One HTTPS:443 listener only, with no port-80 listener. Default action forwards to an `ip`-type target
  group on port 8000 with health check `GET /health` → 200 (F8). It has no targets until 6.3.
- `/health` and `/oidc/*` are **not** routed through CloudFront. ALB health checks reach the task
  directly, and the fake IdP never mounts in a hosted environment (F1).
*Does not cover:* proof that SSE streams, heartbeats and reconnect survive the edge. That is Story
6.3's AC2. It also does not cover security response headers (HSTS etc.), WAF, or CloudFront/ALB access
logging. None is in AR17, and each one costs something.

**D5 — Network: one VPC across two AZs and three subnet tiers.** The AZs come from a variable
(`availability_zones`, default the first two AZs of the region), not a data source. That keeps tests
deterministic and lets the operator avoid an AZ that VPC origins do not support.
- *Public subnets ×2.* They hold the internet gateway route and **one** NAT gateway.
  `map_public_ip_on_launch = false`. Nothing else is placed here.
- *Private app subnets ×2.* They hold the internal ALB and, later, the API and worker tasks. Default
  route goes to the NAT gateway. Tasks need egress to ECR, Cognito, LLM providers and Logfire.
- *Private data subnets ×2.* They have **no** `0.0.0.0/0` route and are for RDS in 6.2. RDS subnet
  groups need two AZs.
- An S3 gateway endpoint is attached to the app and data route tables. It is free and keeps S3 traffic
  off the NAT.
- *Security groups,* built from standalone `aws_vpc_security_group_{ingress,egress}_rule` resources
  rather than inline rules:
  - `alb`: in 443 from the CloudFront prefix list; out 8000 to `api`.
  - `api`: in 8000 from `alb` only; out 443 to `0.0.0.0/0`; out 5432 to `data`.
  - `worker`: **no ingress rule at all**; out 443 to `0.0.0.0/0`; out 5432 to `data`.
  - `data`: in 5432 from `api` and `worker`; no egress.
  - `aws_default_security_group` is adopted with no rules, so nothing can fall back to it.
- No custom NACLs. The default NACL's open outbound rule is what the VPC-origin return path needs.
*Does not cover:* egress filtering. API and worker tasks can reach any internet host on 443. The single
NAT gateway is a single-AZ point of failure, and 6.3's environment-limitations AC records it. The
migrator/bootstrap task's security group is 6.2's to add, when the migrator exists.

**D6 — Cognito: admin-only sign-up, a confidential BFF client, and a Terraform-created planner.**
- *User pool.* `admin_create_user_config.allow_admin_create_user_only = true`. Email is the username
  (`username_attributes = ["email"]`, `auto_verified_attributes = ["email"]`). Password minimum
  length 12. `deletion_protection = "INACTIVE"`, so teardown works (AD-17: data persists *until
  explicit teardown*).
- *Domain.* Cognito prefix domain (`<prefix>.auth.<region>.amazoncognito.com`) with
  `managed_login_version = 2` and an `aws_cognito_managed_login_branding` resource for the client using
  `use_cognito_provided_values = true`. Without a branding style, v2 login pages do not render. If
  managed login v2 requires the Essentials tier, set `user_pool_tier = "ESSENTIALS"` explicitly;
  it is free under its MAU allowance. Verify against the provider and AWS docs at implementation.
- *App client.* `generate_secret = true`, because the FastAPI BFF is a confidential client (AD-3).
  `allowed_oauth_flows_user_pool_client = true`, `allowed_oauth_flows = ["code"]`,
  `allowed_oauth_scopes = ["openid", "email"]` (F2), `supported_identity_providers = ["COGNITO"]`,
  `callback_urls = ["https://<app_domain>/api/v1/auth/callback"]` exactly (F2),
  `prevent_user_existence_errors = "ENABLED"`. Token validity stays at defaults: the 60-minute ID token
  matches `SESSION_TTL_S` = 3600.
- *Planner user.* An `aws_cognito_user` for `var.planner_email` with `email_verified = true` and
  `desired_delivery_mediums = ["EMAIL"]`. Cognito emails the temporary password, so no password ever
  exists in code, tfvars or state.
- *Outputs consumed by 6.2/6.3:* `oidc_issuer` (`https://cognito-idp.<region>.amazonaws.com/<pool_id>`,
  no trailing slash, per F3), `oidc_client_id`, `oidc_client_secret` (`sensitive = true`; 6.2 moves it
  into Secrets Manager), `planner_subject` (the user's `sub`, which becomes
  `SHIFTMIND_SEED_PLANNER_SUBJECT` per F9), and `cognito_domain`.
*Does not cover:* the first real sign-in, which needs the deployed API (Story 6.3). It also does not
cover MFA, advanced security features, or a custom auth domain. The client secret does sit in
Terraform state, which D7 protects.

**D7 — Terraform state in S3 with native locking, created by a bootstrap root.** `infra/terraform/bootstrap/`
uses local state (gitignored) and creates one S3 bucket. The bucket has versioning, SSE-S3, all four
Block Public Access flags, `BucketOwnerEnforced`, and a policy that denies `aws:SecureTransport = false`.
The env root uses `backend "s3"` with `use_lockfile = true` and `encrypt = true`, and **no DynamoDB
table** (S3 native locking is the current mechanism). Bucket, key and region come from a partial
`-backend-config=backend.hcl`. That file is gitignored, and `backend.hcl.example` is committed.
*Does not cover:* the bootstrap root's own state is local. If it is lost, the bucket is re-adopted
with `terraform import`, as the runbook documents.

**D8 — Proof has three layers. None of them writes to `evidence/`.**
- *(a) Offline, in CI.* A new workflow, `.github/workflows/infra.yml`, runs on `push` and
  `pull_request` with `paths: ["infra/**", ".github/workflows/infra.yml"]`. It is separate from
  `ci.yml`, whose triggers and floors stay untouched, and it runs on `epic-6/**` pushes, which
  `ci.yml` (push: `main` only) would not. It runs `terraform fmt -check -recursive infra/terraform`.
  For every root and module it runs `init -backend=false` and `validate`. It runs `terraform test` in
  each module and in the env root, using **`mock_provider "aws"`**, with no AWS credentials in the job.
  Pass counts go through `.github/scripts/assert_counts.py`, extended with a `terraform` runner that
  parses `Success! N passed, M failed.`. That keeps the repo's "exit 0 is not enough" rule.
- *(b) Real account, operator-run.* `terraform plan -out=tfplan`, review with `terraform show tfplan`,
  then `terraform apply tfplan`, applying the reviewed plan file exactly. That is AC1's "reviewed plan".
  Then a second `terraform plan -detailed-exitcode` must exit 0 (no changes), which proves no
  console-side fix-up was needed (AC1's "no console-only resource").
- *(c) Edge smoke, operator-run.* `infra/scripts/smoke-edge.sh` uses `curl`, `dig`/`nslookup` and the
  AWS CLI, and asserts each item in Task 8. Results are pasted into Completion Notes.
No evidence file is written, because Gate C reads Stories 6.4 and 6.5 (Release Gate table), not 6.1.
*Does not cover:* sign-in, SSE and invariants through the deployed app, which are Stories 6.3 and
6.4. The offline tests prove configuration intent only. Layers (b) and (c) prove that AWS accepted it.

**D9 — Region, naming, tags.** `var.region` defaults to `ap-southeast-1`. It is closest to the site's
`Asia/Ho_Chi_Minh` timezone and on the VPC-origins supported-Regions list. A second provider,
`aws.us_east_1`, exists only for the CloudFront certificate. Resource names use the prefix
`shiftmind-${var.environment}` (`environment` defaults to `portfolio`). Provider `default_tags` sets
`Project = "shiftmind"`, `Environment = var.environment` and `ManagedBy = "terraform"`.
*Does not cover:* activating those tags as cost-allocation tags, and Budgets. Both belong to 6.2.

**D10 — Versions and dependencies.** `required_version = "~> 1.15.0"` (spine seed 1.15.8; use the
newest 1.15.x and record it). `hashicorp/aws` is pinned `~> 6.<minor>` at the newest 6.x the
developer measures, and recorded. **No other provider and no registry modules**, such as
`terraform-aws-modules/vpc`. The VPC is about 100 reviewable lines, and AR27 forbids adding planned
dependencies early. The `.terraform.lock.hcl` of every root is committed with hashes for
`linux_amd64`, `windows_amd64` and `darwin_arm64`, generated by
`terraform providers lock -platform=…`. Minh develops on Windows and CI runs on Linux.
*Does not cover:* static scanners such as tflint, checkov or tfsec. They are not added, and the policy
assertions live in `terraform test` instead.

**D11 — One runbook, created here and extended by 6.2, 6.3 and 6.5.** `docs/AWS-RUNBOOK.md`
documents: prerequisites (AWS account, a domain with a Route 53 public hosted zone, operator
credentials from IAM Identity Center via `aws configure sso` / `aws sso login`, with **no IAM-user
access keys**, Terraform and AWS CLI v2 installed), bootstrap, plan/review/apply, the smoke script, the
approximate monthly idle cost of what 6.1 creates, and teardown order. A row is added to
`.claude/CLAUDE.md`'s "Where the truth lives" table pointing at it.
*Does not cover:* rollback and backups, which are Story 6.5. 6.5's "deployment runbook" is this file.

## Tasks / Subtasks

- [x] **Task 1 — Tooling and repo hygiene** (AC1; D10)
  - [x] Install Terraform 1.15.x and AWS CLI v2 locally. Neither is installed on this machine at
        creation; use `winget install Hashicorp.Terraform` / `winget install Amazon.AWSCLI`. Record both
        versions in Completion Notes.
  - [x] Extend `.gitignore` with `.terraform/`, `*.tfstate`, `*.tfstate.*`, `*.tfplan`, `tfplan`,
        `*.tfvars` (with `!*.tfvars.example`), `backend.hcl` and `crash.log`. `.terraform.lock.hcl` stays tracked (D10).

- [x] **Task 2 — State bootstrap root** `infra/terraform/bootstrap/` (AC1, AC2; D7)
  - [x] Create the state bucket per D7, outputting its name. Add `terraform.tfvars.example`.

- [x] **Task 3 — `modules/network`** (AC1, AC2; D5, D2)
  - [x] Build the VPC, IGW, three subnet tiers ×2 AZs, the NAT gateway, route tables and the S3 gateway
        endpoint, all per D5.
  - [x] Build the security groups and rules per D5. Look up the CloudFront origin-facing prefix list with
        `data "aws_ec2_managed_prefix_list"` by name.
        The prefix list counts as roughly 55 rules against the SG rule quota, so keep `alb` to that one
        ingress rule.
  - [x] Outputs: VPC ID, subnet ID lists per tier, the four SG IDs, and the route table IDs.
  - [x] `tests/network.tftest.hcl` with `mock_provider "aws"` (supply `override_data` for the prefix list
        `id`). Assert: data route tables contain no `0.0.0.0/0` route; no subnet has
        `map_public_ip_on_launch = true`; `worker` has zero ingress rules; `api` ingress sources only `alb`'s
        SG; `alb` ingress is only 443 from the prefix list; `data` ingress is only 5432 from `api`/`worker`;
        the default SG has no rules. (AC2 second clause)

- [x] **Task 4 — `modules/edge`** (AC1, AC2; D2, D3, D4)
  - [x] Declare `configuration_aliases = [aws.us_east_1]` in `versions.tf`.
  - [x] Build both ACM certificates with DNS validation records and `aws_acm_certificate_validation`.
        CloudFront and the listener must consume the *validated* ARNs. (D3)
  - [x] Build the SPA bucket: all four BPA flags, `BucketOwnerEnforced`, explicit SSE-S3 (`AES256`), and
        an OAC with `signing_behavior = "always"` and `signing_protocol = "sigv4"`. The bucket policy
        grants `s3:GetObject` only to `cloudfront.amazonaws.com` with `AWS:SourceArn` equal to the
        distribution ARN, and denies `aws:SecureTransport = false`.
  - [x] Build the internal ALB, HTTPS listener (`ssl_policy = "ELBSecurityPolicy-TLS13-1-2-2021-06"`) and
        target group per D4. Add the Route 53 alias `origin.<app_domain>` → ALB. (D2)
  - [x] Add `aws_cloudfront_vpc_origin` per D2, and the CloudFront Function per D4 (source in
        `modules/edge/spa-rewrite.js`, loaded with `file()`).
  - [x] Build the distribution per D4: aliases `[app_domain]`, `minimum_protocol_version = "TLSv1.2_2021"`,
        `ssl_support_method = "sni-only"`, `http_version = "http2and3"`, `is_ipv6_enabled = true`,
        `price_class = "PriceClass_200"`, `default_root_object = "index.html"`. Look up managed policies
        with `data "aws_cloudfront_cache_policy"` / `data "aws_cloudfront_origin_request_policy"` by name
        (`Managed-CachingOptimized`, `Managed-CachingDisabled`, `Managed-AllViewerExceptHostHeader`).
        **Verify these names against current AWS docs; do not hardcode policy IDs.**
  - [x] Add Route 53 A and AAAA aliases from `<app_domain>` to the distribution.
  - [x] `tests/edge.tftest.hcl` with `mock_provider "aws"` and `mock_provider "aws" { alias = "us_east_1" }`.
        Pass both through `providers = {…}` in each `run`, and use `override_data` for the policy lookups.
        Assert:
        viewer min protocol `TLSv1.2_2021`; no behavior allows `allow-all`; VPC origin `https-only`
        with `["TLSv1.2"]`; listener protocol `HTTPS` and the TLS policy above; no port-80 listener exists;
        ALB `internal == true` and `idle_timeout >= 16`; the `/api/*` behavior allows all seven methods,
        uses the disabled-cache policy and has `compress == false`; the API origin's `origin_read_timeout > 15`
        and `response_completion_timeout` is null or 0; the distribution has **zero** `custom_error_response`
        blocks; the SPA bucket has all four BPA flags and SSE; OAC is `sigv4`/`always`. (AC2 first clause, D4)

- [x] **Task 5 — `modules/identity`** (AC1; D6)
  - [x] Build the user pool, prefix domain, managed login branding, app client and planner user per D6.
        Expose the outputs D6 lists, with `oidc_client_secret` marked `sensitive`.
  - [x] `tests/identity.tftest.hcl`. Assert: `allow_admin_create_user_only == true`;
        `allowed_oauth_flows == ["code"]`; scopes are exactly `openid` and `email`; the callback list is
        exactly `["https://<app_domain>/api/v1/auth/callback"]` for a test `app_domain`;
        `generate_secret == true`; `supported_identity_providers == ["COGNITO"]`; the issuer output has no
        trailing slash. (AC1 "public sign-up disabled"; F2, F3)

- [x] **Task 6 — Env root `infra/terraform/envs/portfolio/`** (AC1; D3, D7, D9, D10)
  - [x] `versions.tf` (D10), `providers.tf` (default + `us_east_1` alias, `default_tags` per D9),
        `backend.tf` (D7, partial), `variables.tf` (`region`, `environment`, `availability_zones`,
        `app_domain`, `hosted_zone_name`, `cognito_domain_prefix`, `planner_email`, `vpc_cidr`), the
        `data "aws_route53_zone"` lookup (D3), the module wiring, and `outputs.tf`, which re-exports
        D6's outputs plus `app_url`, `alb_arn`, `api_target_group_arn` and the SG/subnet IDs that 6.2/6.3 consume.
  - [x] Commit `terraform.tfvars.example` and `backend.hcl.example`. Real values stay gitignored.
  - [x] `tests/portfolio.tftest.hcl`: a mocked plan of the whole root. Assert the wiring: the CloudFront
        alias equals `app_domain`; the Cognito callback host equals `app_domain`; the ALB subnets are the
        network module's app subnets.
  - [x] Generate multi-platform lock files for `bootstrap/` and `envs/portfolio/` (D10).

- [x] **Task 7 — CI** (AC1; D8a)
  - [x] Add `--runner terraform` to `.github/scripts/assert_counts.py`. It parses the final
        `Success! N passed, M failed.` / `Failure! …` line, and its tests or docstring follow the script's
        existing pattern.
  - [x] Add `.github/workflows/infra.yml` per D8a. Use `hashicorp/setup-terraform` pinned to the D10
        version and `permissions: contents: read`, with no AWS credentials and no `id-token`.
        Set a `--min-passed` floor per test directory equal to the count measured at implementation.

- [ ] **Task 8 — Real plan, apply, and edge smoke** (AC1, AC2; D8b, D8c). The operator runs this
      with Minh's AWS credentials. The developer prepares everything and records the results.
  - [ ] Bootstrap, then `init` with backend config, then `plan -out`, `show`, and `apply tfplan`. Then
        `plan -detailed-exitcode` must exit 0. (D8b)
  - [x] Write `infra/scripts/smoke-edge.sh`. It reads its inputs from `terraform output -json`, uploads a
        throwaway `index.html` placeholder to the SPA bucket (6.3 replaces it), and asserts:
        1. `https://<app_domain>/` → 200 with the placeholder body, and `curl --tls-max 1.1` fails the handshake.
        2. `http://<app_domain>/` → 301 to https.
        3. `https://<app_domain>/scenario-data` → 200 placeholder (SPA rewrite). `https://<app_domain>/assets/missing.js` → 403/404, not the placeholder.
        4. `https://<app_domain>/api/v1/auth/session` → **503 from the ALB** (empty target group). A 502 means
           the origin certificate does not match `origin.<app_domain>` (D2), so the smoke fails.
        5. `POST https://<app_domain>/api/v1/anything` reaches the ALB (503), not a CloudFront 403 (D4 methods).
        6. `origin.<app_domain>` resolves only to RFC 1918 addresses, and a direct `curl` to it from the
           operator machine fails to connect.
        7. The direct S3 object URL for `index.html` → 403.
        8. `GET <oidc_issuer>/.well-known/openid-configuration` has `issuer` equal to the output (F3), and
           its `authorization_endpoint` is on the Cognito domain.
        9. `GET <authorization_endpoint>?response_type=code&client_id=…&redirect_uri=https://<app_domain>/api/v1/auth/callback&scope=openid+email`
           → 200 or a redirect to the login page, **not** a `redirect_mismatch` error.
        10. `aws cognito-idp describe-user-pool` shows `AllowAdminCreateUserOnly: true`.
  - [ ] Paste the smoke output, the measured Terraform and provider versions, and the
        `plan -detailed-exitcode` result into Completion Notes. Do not write an `evidence/` file (D8).
  - [ ] Leave the environment applied for 6.2 unless Minh says to tear it down. Record the date it was
        applied.

- [x] **Task 9 — Documentation** (AC1; D11)
  - [x] Write `docs/AWS-RUNBOOK.md` per D11. Measure the idle cost from the AWS pricing pages at
        implementation rather than copying a figure from this story.
  - [x] Add a `.claude/CLAUDE.md` "Where the truth lives" row for it.
  - [x] Record AC2's 6.2-dependent clauses as open, in Completion Notes (D1).

## Dev Notes

### Files

All new unless marked UPDATE.

```text
infra/terraform/
  bootstrap/{versions.tf, main.tf, variables.tf, outputs.tf, terraform.tfvars.example, .terraform.lock.hcl}
  modules/network/{versions.tf, main.tf, security_groups.tf, variables.tf, outputs.tf, tests/network.tftest.hcl}
  modules/edge/{versions.tf, certificates.tf, spa_bucket.tf, alb.tf, cloudfront.tf, dns.tf, spa-rewrite.js,
                variables.tf, outputs.tf, tests/edge.tftest.hcl}
  modules/identity/{versions.tf, main.tf, variables.tf, outputs.tf, tests/identity.tftest.hcl}
  envs/portfolio/{versions.tf, providers.tf, backend.tf, main.tf, variables.tf, outputs.tf,
                  terraform.tfvars.example, backend.hcl.example, .terraform.lock.hcl, tests/portfolio.tftest.hcl}
infra/scripts/smoke-edge.sh
.github/workflows/infra.yml
docs/AWS-RUNBOOK.md
UPDATE .github/scripts/assert_counts.py  — add the terraform runner; existing runners are unchanged
UPDATE .gitignore                        — Task 1
UPDATE .claude/CLAUDE.md                 — one table row
```

`infra/terraform/` with environment roots plus reusable modules matches the spine's Structural Seed.
Modules do not configure providers. Only the env root has `provider` blocks. Modules declare
`required_providers`, plus `configuration_aliases` where they need them.

### What must not change

- `.github/workflows/ci.yml`: its triggers, jobs and floors stay unchanged (D8a puts infra in its own workflow).
- Backend and frontend code: this story adds no application change. In particular, the Cognito adapter,
  `settings.py`, `nginx.conf` and the Dockerfiles stay as they are. Hosted env wiring (`OIDC_PROVIDER=cognito`,
  `APP_BASE_URL`, `CORS_ORIGINS`, the build-time `VITE_API_BASE_URL`) belongs to Story 6.3.
- `backend/tests/architecture/test_trace_export_boundaries.py` scans tracked files via `git ls-files`.
  No `.tf` file may set `AGENT_TRACE_CONTENT_MODE` (Story 6.3 AC3 extends this to all IaC). 6.1 has no
  reason to mention it.

### Deferred-work items with an Epic 6 trigger that are *not* this story's

Do not pull these in. They are listed so they are not mistaken for omissions:
base-image digest pinning (`deferred-work.md:717`, owned by ECR work in 6.2/6.3), uvicorn error-channel
logging and direct stdout writes (`:685`, `:705`, owned by 6.3 process composition), the cold-volume
postgres healthcheck race (`:715`) and Compose-proof rot (`:697`, owned by 6.3/6.4), and metrics-label
cardinality (`:669`, owned by the first metrics exporter).

### Testing standards

- `terraform test` with `mock_provider` needs **Terraform ≥ 1.7**. Mocked computed attributes get
  generated values only on `command = apply`, and under `command = plan` they are unknown. Mocked `apply`
  never contacts AWS, so prefer `command = apply` in tests that assert on computed values. Data sources
  with list or ID attributes the code indexes into need `override_data` (or `mock_data` defaults), or they
  come back as empty collections or random strings.
- Assertions can reach only the resources of the module under test, or `module.x.<output>` from a
  calling root. That is why each module has its own `tests/` directory (D8a).
- With `mock_provider`, `terraform init` still downloads the real provider plugin, so CI needs network
  access but no credentials.
- Floors follow the repo convention (`.github/scripts/assert_counts.py` docstring): passes are floors and
  failures are zero.
- Docs testing conventions: `docs/TESTING.md`. Infra tests are new there, so add a short section.

### Latest technical notes (researched 2026-10-07)

- **CloudFront VPC origins** (`aws_cloudfront_vpc_origin`, `vpc_origin_config { vpc_origin_id,
  origin_read_timeout, origin_keepalive_timeout }` on the distribution origin). They need an IGW on the VPC
  and at least one free IPv4 address in the private subnet. NLBs with TLS listeners are not supported,
  but ALBs are. ALB SG options are the managed prefix list, or the service-managed
  `CloudFront-VPCOrigins-Service-SG`, which exists only after creation (we use the prefix list, per D2).
  VPC-origin creation and deletion can take about 15 minutes each, so expect a long first apply and
  destroy. `ap-southeast-1` is supported. [AWS: CloudFront Developer Guide, "Restrict access with VPC origins"]
- **Origin certificate match.** For HTTPS to an origin, one name on the origin's certificate must match
  the origin domain name, or CloudFront returns 502. Hence `origin.<app_domain>` (D2).
- **CloudFront timeouts.** `origin_read_timeout` is 1–60 s by default (higher only through a quota
  increase). `response_completion_timeout` must be ≥ `origin_read_timeout` if it is set, and unset means
  no maximum. [hashicorp/terraform-provider-aws v6.33 docs, `cloudfront_distribution`]
- **Cognito managed login v2** needs a branding style (`aws_cognito_managed_login_branding`,
  `use_cognito_provided_values = true`) and `managed_login_version = 2` on `aws_cognito_user_pool_domain`.
- **S3 backend native locking.** `use_lockfile = true` (Terraform ≥ 1.10) replaces DynamoDB locking,
  which is deprecated.
- Prefer standalone `aws_vpc_security_group_ingress_rule` / `_egress_rule` resources over inline rules
  and over the older `aws_security_group_rule`.

### Approximate cost, for the runbook to verify

The idle resources 6.1 creates are one NAT gateway (largest; hourly plus per-GB), one ALB (hourly plus
LCU), one Route 53 hosted zone, and near-zero CloudFront/S3/Cognito at portfolio traffic. That is
roughly US$60–70/month in `ap-southeast-1` before 6.2's RDS and 6.3's Fargate. This is an estimate
for orientation only. Task 9 measures it properly.

### References

- `_bmad-output/planning-artifacts/epics.md` — Epic 6 header, Story 6.1, and Stories 6.2–6.5 for the scope boundary (D1)
- `_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` — AD-3, AD-17, AD-21, AD-23, AD-24 scope note, Stack, Structural Seed, Deferred
- `_bmad-output/planning-artifacts/requirements-inventory.md` — NFR21; `epics.md:163` — AR17
- `backend/api/main.py`, `backend/api/routers/auth.py`, `backend/adapters/cognito/oidc.py`, `backend/application/ports/identity.py`, `backend/api/routers/conversations.py:133-141`
- `frontend/nginx.conf`, `docker-compose.yml`, `Dockerfile`
- `docs/CONFIGURATION.md` — OIDC and seed-planner variables
- `_bmad-output/implementation-artifacts/deferred-work.md` — Epic 6-triggered entries listed above
- `_bmad-output/implementation-artifacts/epic-5-retro-2026-10-05.md` §5 — Epic 6 preparation

## Self-consistency pass (at creation)

- **Task proofs vs Decisions.** Task 8 item 4 expects a 503, which is reachable because D4 leaves the
  target group empty until 6.3. Item 5 expects the POST to reach the ALB, which is reachable because D4
  allows all seven methods. Item 3 expects a missing asset to return 403/404, which is reachable because
  the D4 rewrite skips paths with a `.` and D4 forbids `custom_error_response`. No task proves a state
  that a Decision makes unreachable.
- **Restatement check.** Tasks cite D-numbers for mechanisms and do not restate their reasons. The test
  assertion lists in Tasks 3–5 enumerate *what to assert*. The reasons live only in D2, D4, D5 and D6.
- **AC coverage.** AC1 is covered by Tasks 2–6 and 8, with the reviewed plan per D8b. AC2's first clause
  is covered by Tasks 4 and 8, and its second clause by Tasks 3 and 8. AC2's RDS/secrets/logs halves
  are deferred to 6.2 by D1. That is recorded, not silently dropped.

## Dev Agent Record

### Agent Model Used

Claude Sonnet 5.5 (`claude-sonnet-5-5`), via `bmad-dev-story`, 2026-10-07.

### Implementation Plan

Followed the story's task order. Each module was built from the Decisions (D1–D11), given a
`mock_provider` test suite, then mutation-checked against its own guards before the next one.
Offline proof only: this machine has no AWS credentials, so Task 8's real plan, apply and smoke
are **not done** (see Completion Notes → Open).

### Debug Log References

- `hashicorp/aws` provider download failed three times locally with `releases.hashicorp.com: read`
  (a transient network error, not a configuration problem). `infra.yml`'s `terraform init` step
  retries up to three times; a shared `TF_PLUGIN_CACHE_DIR` avoids repeat downloads.
- A mocked data source's `id` is always null (`override_data` and `mock_data` honour every other
  attribute, verified with a throwaway test). `modules/edge` therefore asserts the managed policy
  *names*, and `smoke-edge.sh` item 11 proves the attached policy IDs on the live distribution.
- `terraform validate` on `modules/edge` alone fails with a misleading "provider configuration
  removed from state" error because of `configuration_aliases`. It is validated through
  `envs/portfolio`, and `infra.yml` skips the standalone validate for that one module.
- `for_each` over `aws_acm_certificate.domain_validation_options` cannot be planned under a mock
  (the whole set is unknown). Each certificate has exactly one name, so the validation records are
  single resources using `one(...)`.
- A literal backspace character got into `assert_counts.py` through a `\b` in a patch script and
  made the new regex never match. Found by running the runner against real `terraform test` logs;
  removed. The `Write`/`Edit` tools and `printf` were used for the later files.

### Completion Notes List

**Measured versions (2026-10-07).** Terraform **1.15.9** (newest 1.15.x; `winget` installs 1.16.5,
so 1.15.9 is in `~/bin`, first on `PATH`). AWS CLI **2.37.10**. `hashicorp/aws` **6.67.0**, the newest
6.x, constrained `~> 6.67`. The lock files carry hashes for `linux_amd64`, `windows_amd64` and
`darwin_arm64`.

**Offline results.**

| Suite | Passed | Floor in `infra.yml` |
|---|---|---|
| `bootstrap` | 3 | 3 |
| `modules/network` | 10 | 10 |
| `modules/edge` | 9 | 9 |
| `modules/identity` | 5 | 5 |
| `envs/portfolio` | 7 | 7 |

`terraform fmt -check -recursive`, `init -backend=false` and `validate` pass for every root and module
except `modules/edge` (validated through `envs/portfolio`). Backend default suite after the change:
**3001 passed, 2 skipped, 10 deselected** (one skip is the evidence-binding check that needs a clean
tree, expected with uncommitted files; the other is the permanent `test_scheduling_inspect.py` skip).
No application code changed.

**Mutation table** (D8 / persistent fact). Every mutation was applied to finished product code with
`scratchpad/mutate.py`, observed failing for the stated reason, and restored; the suite was green again
afterwards and `git status` showed only the intended files. "Before" is the suite result with the real
code, "after" the result with the mutation.

| # | Mutation applied to real code | Guard that should redden | Before | After |
|---|---|---|---|---|
| **bootstrap** | | | | |
| B1 | `restrict_public_buckets` true→false | `state_bucket_is_private_versioned_and_encrypted` | 3/3 | 2 pass, 1 fail |
| B2 | `block_public_acls` true→false | same | 3/3 | 2/1 |
| B3 | ownership `BucketOwnerEnforced`→`ObjectWriter` | same | 3/3 | 2/1 |
| B4 | versioning `Enabled`→`Suspended` | same | 3/3 | 2/1 |
| B5 | SSE `AES256`→`aws:kms` | same | 3/3 | 2/1 |
| B6 | `aws:SecureTransport` condition `false`→`true` | `state_bucket_policy_denies_plaintext_transport` | 3/3 | 2/1 |
| B7 | policy `Deny`→`Allow` | same | 3/3 | 2/1 |
| B8 | bucket-name validation loosened (`\|.*`) | `bucket_name_validation_rejects_uppercase` | 3/3 | 2/1 |
| **modules/network** | | | | |
| N1 | add a `data` entry (route to NAT) to `default_routes` | `data_tier_has_no_internet_route` | 10/10 | 9/1 |
| N2 | app subnet `map_public_ip_on_launch` false→true | `no_subnet_assigns_public_ips` | 10/10 | 9/1 |
| N3 | add a worker ingress rule (port 22 from api) | `worker_has_no_ingress_rule` | 10/10 | 9/1 |
| N4 | `api_from_alb` source SG alb→worker | `api_ingress_comes_only_from_the_alb` | 10/10 | 9/1 |
| N5 | ALB ingress port 443→80 | `alb_ingress_is_only_443_from_the_cloudfront_prefix_list` | 10/10 | 9/1 |
| N6 | ALB ingress source prefix list→api SG | same | 10/10 | 9/1 |
| N7 | `data_from_api` port 5432→3306 | `data_ingress_is_only_5432_from_api_and_worker` | 10/10 | 9/1 |
| N8 | add an egress rule to the data SG | `data_has_no_egress_and_default_sg_has_no_rules` | 10/10 | 9/1 |
| N9 | inline ingress rule on `aws_default_security_group` | same | 10/10 | 9/1 |
| N10 | S3 endpoint `route_table_ids` drops the data table | `s3_gateway_endpoint_is_on_app_and_data_tables` | 10/10 | 9/1 |
| N11 | `worker_https_out` port 443→22 | `workloads_egress_only_443_and_5432` | 10/10 | 9/1 |
| **modules/edge** | | | | |
| E1 | viewer min TLS `TLSv1.2_2021`→`TLSv1` | `viewer_tls_is_1_2_and_no_behavior_allows_plain_http` | 9/9 | 8/1 |
| E2 | SPA behavior `redirect-to-https`→`allow-all` | same | 9/9 | 8/1 |
| E3 | `/api/*` `https-only`→`allow-all` | same + `api_behavior_streams_and_forwards_everything` | 9/9 | 7/2 |
| E4 | VPC origin `https-only`→`http-only` | `vpc_origin_is_https_only_tls_1_2` | 9/9 | 8/1 |
| E5 | VPC origin TLS `TLSv1.2`→`TLSv1.1` | same | 9/9 | 8/1 |
| E6 | ALB `internal` true→false | `alb_is_internal_https_only_with_a_long_idle_timeout` | 9/9 | 8/1 |
| E7 | ALB `idle_timeout` 60→10 | same | 9/9 | 8/1 |
| E8 | add an `http`:80 entry to `local.listeners` | same | 9/9 | 8/1 |
| E9 | listener `ssl_policy`→`ELBSecurityPolicy-2016-08` | same | 9/9 | 8/1 |
| E10 | health-check path `/health`→`/` | same | 9/9 | 8/1 |
| E11 | drop `PATCH` from `/api/*` methods | `api_behavior_streams_and_forwards_everything` | 9/9 | 8/1 |
| E12 | `/api/*` `compress` false→true | same | 9/9 | 8/1 |
| E13 | add a `function_association` to `/api/*` | same | 9/9 | 8/1 |
| E14 | `origin_read_timeout` 60→10 | `api_origin_timeouts_allow_sse_and_are_not_capped` | 9/9 | 8/1 |
| E15 | set `response_completion_timeout = 120` on the API origin | same | 9/9 | 8/1 |
| E16 | API origin domain → `aws_lb.this.dns_name` | same | 9/9 | 8/1 |
| E17 | add a `custom_error_response` | `spa_rewrite_is_on_the_default_behavior_and_errors_are_not_rewritten` | 9/9 | 8/1 |
| E18 | rewrite JS `=== -1`→`!== -1` | same | 9/9 | 8/1 |
| E19 | SPA `block_public_policy` true→false | `spa_bucket_is_private_encrypted_and_oac_signed` | 9/9 | 8/1 |
| E20 | OAC `signing_behavior` `always`→`no-override` | same | 9/9 | 8/1 |
| E21 | SPA SSE `AES256`→`aws:kms` | same | 9/9 | 8/1 |
| E22 | bucket policy `AWS:SourceArn`→`"*"` | `spa_bucket_policy_grants_only_this_distribution_and_denies_plaintext` | 9/9 | 8/1 |
| E23 | `aws:SecureTransport` condition `false`→`true` | same | 9/9 | 8/1 |
| E24 | Allow action `s3:GetObject`→`s3:*` | same | 9/9 | 8/1 |
| E25 | origin certificate validation `DNS`→`EMAIL` | `dns_and_certificates_are_wired_to_the_zone` | 9/9 | 8/1 |
| E26 | `AAAA` alias type→`A` | same | 9/9 | 8/1 |
| **modules/identity** | | | | |
| I1 | `allow_admin_create_user_only` true→false | `sign_up_is_closed_and_passwords_are_long` | 5/5 | 4/1 |
| I2 | password minimum 12→8 | same | 5/5 | 4/1 |
| I3 | `deletion_protection` `INACTIVE`→`ACTIVE` | same | 5/5 | 4/1 |
| I4 | `generate_secret` true→false | `bff_client_is_confidential_code_flow_with_exact_callback` | 5/5 | 4/1 |
| I5 | add the `implicit` OAuth flow | same | 5/5 | 4/1 |
| I6 | add the `profile` scope | same | 5/5 | 4/1 |
| I7 | add a second callback URL | same | 5/5 | 4/1 |
| I8 | callback path `/api/v1/auth/callback`→`/auth/callback` | same | 5/5 | 4/1 |
| I9 | add `Google` to supported IdPs | same | 5/5 | 4/1 |
| I10 | `prevent_user_existence_errors` `ENABLED`→`LEGACY` | same | 5/5 | 4/1 |
| I11 | `managed_login_version` 2→1 | `managed_login_v2_has_a_branding_style` | 5/5 | 4/1 |
| I12 | `use_cognito_provided_values` true→false | same | 5/5 | 4/1 |
| I13 | `user_pool_tier` `ESSENTIALS`→`LITE` | same | 5/5 | 4/1 |
| I14 | add `SMS` to `desired_delivery_mediums` | `planner_is_emailed_a_temporary_password_and_never_has_one_in_code` | 5/5 | 4/1 |
| I15 | set a `temporary_password` | same | 5/5 | 4/1 |
| I16 | planner `email_verified` true→false | same | 5/5 | 4/1 |
| I17 | issuer output gains a trailing slash | `outputs_match_what_the_adapter_expects` | 5/5 | 4/1 |
| **envs/portfolio** | | | | |
| R1 | edge module gets `hosted_zone_name` as `app_domain` | `edge_and_identity_agree_on_the_app_domain` | 7/7 | 6/1 |
| R2 | identity module gets `hosted_zone_name` as `app_domain` | same | 7/7 | 6/1 |
| R3 | ALB subnets → `module.network.public_subnet_ids` | `alb_sits_in_the_network_modules_app_subnets` | 7/7 | 6/1 |
| R4 | default AZ `…b`→`…c` | `default_availability_zones_are_the_first_two_of_the_region` | 7/7 | 6/1 |
| R5 | ignore the `availability_zones` override | `availability_zones_can_be_overridden` | 7/7 | 6/1 |
| R6 | name prefix drops the environment | `resources_are_named_from_the_environment` | 7/7 | 6/1 |
| R7 | drop the `ManagedBy` default tag | same | 7/7 | 6/1 |
| R8 | `app_domain` regex loosened (`\|.*`) | `app_domain_must_be_a_dns_name` | 7/7 | 6/1 |
| R9 | identity `region` → `"us-east-1"` | `oidc_outputs_follow_the_adapter_contract` | 7/7 | 6/1 |
| R10 | `oidc_client_secret` output loses `sensitive = true` | **Terraform itself**: plan fails with "Output refers to sensitive values" (0 pass, 1 fail, 6 skipped). `terraform validate` alone does *not* catch it | 7/7 | error |
| **assert_counts.py `--runner terraform`** | | | | |
| T1 | parser ignores the log and returns `{"passed": 99}` | the `Failure! 4 passed, 1 failed` log must exit 1 | exit 1 | exit 0 (so the scenario detects it); restored |
| **smoke-edge.sh** (stubbed `terraform`, `aws`, `curl`, `dig`) | | | | |
| S1–S13 | one deliberate break per check: no redirect, TLS 1.1 accepted, no SPA rewrite, missing asset rewritten, ALB cert 502, CloudFront 403, origin reachable, bucket readable, trailing-slash issuer, `redirect_mismatch`, sign-up open, wrong managed policy, public origin IP | the matching check, and only that one | 15 PASS / 0 FAIL | 14 PASS / 1 FAIL each |

Two first attempts did not count because they errored in configuration rather than failing an
assertion (removing the ALB prefix list; SSE `AES128`). Each was redone with a valid mutation.

**Guards that cannot be mutated offline (an honest gap, kept):**

- *Which managed policy ID a behavior consumes.* Mock data-source `id` is null, so a swap between two
  policies cannot be observed. `smoke-edge.sh` item 11 covers it on the real distribution.
- *"CloudFront and the listener consume the **validated** certificate ARN".* The mocked
  `aws_acm_certificate_validation` echoes the certificate ARN, so using the unvalidated ARN looks
  identical offline. Real apply would race, not fail deterministically.
- *"No port-80 listener".* The test iterates every entry in `aws_lb_listener.this`; a second listener
  declared as a separate resource would not be seen. The ALB security group (443 only) is a second line.
- *The CloudFront certificate being in us-east-1.* The mock has no region; AWS rejects it at apply.
- *`smoke-edge.sh` against real `curl`/AWS.* The stubs prove the script's logic, not curl's behavior
  (for example `--tls-max` on a Schannel build, handled with an `openssl` fallback but unexercised).

**Deviations from the story text, each small and recorded here.**

1. `aws_lb_listener` is a `for_each` over `local.listeners` (one `https` entry) instead of a single
   named resource, so the "no port-80 listener" assertion has something to iterate.
2. ACM validation records are single resources using `one(domain_validation_options)`, not the usual
   `for_each` (see Debug Log). Equivalent for a single-name certificate.
3. Extra module outputs, so the env-root test can reach what it asserts through `module.x.<output>`:
   `edge.distribution_aliases`, `edge.alb_subnet_ids`, `identity.callback_urls`.
4. `bootstrap/` got its own `tests/bootstrap.tftest.hcl` (3 runs). The story listed tests only for the
   modules and the env root; the state bucket's TLS-only policy is an invariant worth a guard.
5. `smoke-edge.sh` gained item 11 (live managed-policy IDs) to close the mock gap above, and refuses to
   overwrite a non-placeholder `index.html` (`SMOKE_OVERWRITE_INDEX=1` forces it).
6. `infra.yml` also triggers on `.github/scripts/assert_counts.py` changes, and its init step retries.
7. SPA bucket has `force_destroy = true` and the target group `deregistration_delay = 30`, so teardown
   of a practice environment does not stall (AD-17: teardown must work).
8. `.gitignore` also ignores `infra/terraform/modules/**/.terraform.lock.hcl`: only the roots commit a
   lock file (D10), and module-level `init` generates one for testing.
9. The smoke script is invoked as `bash infra/scripts/smoke-edge.sh`, not by path, because a Windows
   checkout does not carry the executable bit.

**AC2: clauses still open until Story 6.2 (D1).** "RDS requires TLS" and the RDS/logs/secrets halves of
"encryption at rest" have no resource to bind in 6.1, and no placeholder RDS or secret was created to
tick them. 6.1 meets AC2 for every resource it creates: the SPA bucket (BPA, SSE-S3, TLS-only policy,
OAC), the state bucket (BPA, SSE-S3, versioning, TLS-only policy), CloudFront (TLS 1.2 floor,
HTTPS-only to the origin), the ALB (HTTPS-only listener, TLS 1.2+ policy) and the security groups (ALB
443 from the CloudFront prefix list only, API 8000 from the ALB only, the worker with no ingress rule at
all). It also builds the private data subnets (no default route) and the `data` security group RDS will
use.

**Open: Task 8 (AC1's "reviewed plan" and "no console-only resource", and the edge smoke).** Not done.
This machine has no AWS credentials, profile or environment variables
(`aws sts get-caller-identity` → `NoCredentials`), and the run needs inputs only Minh holds. To run it
with his credentials:

1. ~~An AWS account profile~~ **Done 2026-10-08.** An IAM Identity Center profile
   (`AdministratorAccess-<account-id>`, region `ap-southeast-1`) is configured and
   `aws sts get-caller-identity` succeeds. The account was empty: only the default VPC, no `shiftmind`
   buckets, no hosted zones, no registered domains.
2. A registered domain with a **public Route 53 hosted zone** already delegated. Terraform needs
   `hosted_zone_name` and `app_domain` (a name inside that zone).
3. `planner_email` (Cognito mails the temporary password there) and a globally unique
   `cognito_domain_prefix`.
4. His go-ahead to apply: roughly US$65.6/month idle (see the runbook) and a 20–30 minute first apply.

**Paused 2026-10-08 on item 2 (the domain).** Minh is preparing a domain and its public hosted zone;
items 3 and 4 and the apply wait on it. Nothing is deployed and nothing is costing money. Everything
else in the story is finished.

Then follow `docs/AWS-RUNBOOK.md` §1–3: bootstrap, `plan -out` / `show` / `apply tfplan`,
`plan -detailed-exitcode` (must exit 0), and `bash infra/scripts/smoke-edge.sh`. Paste the smoke output,
the exit code and the apply date into this section. Risks worth reading in the first plan, none of them
verifiable offline: the CloudFront VPC origin's `http_port = 80` (required by the API, no such listener
exists), `aws_cognito_user.planner.sub` being populated when the username is an email under
`username_attributes`, the `Managed-*` policy names resolving, an AZ that VPC origins do not support, and
`managed_login_version = 2` with `use_cognito_provided_values = true`.

### File List

New:

- `infra/terraform/bootstrap/{versions.tf, main.tf, variables.tf, outputs.tf, terraform.tfvars.example, .terraform.lock.hcl, tests/bootstrap.tftest.hcl}`
- `infra/terraform/modules/network/{versions.tf, main.tf, security_groups.tf, variables.tf, outputs.tf, tests/network.tftest.hcl}`
- `infra/terraform/modules/edge/{versions.tf, certificates.tf, spa_bucket.tf, alb.tf, cloudfront.tf, dns.tf, spa-rewrite.js, variables.tf, outputs.tf, tests/edge.tftest.hcl}`
- `infra/terraform/modules/identity/{versions.tf, main.tf, variables.tf, outputs.tf, tests/identity.tftest.hcl}`
- `infra/terraform/envs/portfolio/{versions.tf, providers.tf, backend.tf, main.tf, variables.tf, outputs.tf, terraform.tfvars.example, backend.hcl.example, .terraform.lock.hcl, tests/portfolio.tftest.hcl}`
- `infra/scripts/smoke-edge.sh`
- `.github/workflows/infra.yml`
- `docs/AWS-RUNBOOK.md`

Modified:

- `.github/scripts/assert_counts.py` (adds the `terraform` runner; existing runners unchanged)
- `.gitignore` (Terraform state, plans, tfvars, backend config, module lock files)
- `.claude/CLAUDE.md` (one table row)
- `docs/TESTING.md` (an "Infrastructure" section)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (story → in-progress)
- `_bmad-output/implementation-artifacts/6-1-provision-aws-edge-identity-and-network-boundaries.md` (this record)

### Change Log

- 2026-10-07: Built the offline half of Story 6.1: state bootstrap, network, edge and identity modules,
  the `envs/portfolio` root, 34 `terraform test` runs (all mutation-checked), the `terraform` runner in
  `assert_counts.py`, `infra.yml`, `smoke-edge.sh`, and `docs/AWS-RUNBOOK.md`. Task 8 (real plan, apply and
  smoke) is open pending AWS access; the story stays `in-progress`.
