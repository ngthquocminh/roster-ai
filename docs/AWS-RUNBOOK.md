# AWS runbook

How the hosted ShiftMind environment is built, checked and torn down. This is the
single deployment runbook for Epic 6: Story 6.1 created it for the edge, identity
and network; Stories 6.2, 6.3 and 6.5 extend it for data, releases and rollback.

Epic 6 is a **practice deployment** on its own branch. It does not change `main`'s
Gate B claim. The reproducible part is Terraform under [`infra/terraform/`](../infra/terraform/);
the operator-run proof is the plan, the apply and
[`infra/scripts/smoke-edge.sh`](../infra/scripts/smoke-edge.sh).

## What exists after Story 6.1

```text
Browser ──HTTPS (TLS 1.2+)──► CloudFront  ┬─ default ─► private S3 SPA bucket (OAC, Block Public Access)
                                          └─ /api/*  ─► VPC origin ─HTTPS─► internal ALB ─► [API tasks: Story 6.3]
        Cognito hosted login (admin-only sign-up)        origin.<app_domain> (private A record, ACM cert)

VPC 10.20.0.0/16, two AZs
  public subnets ×2     internet gateway route + ONE NAT gateway, nothing else
  private app subnets×2 internal ALB now; API and worker tasks later
  private data subnets×2  no default route; RDS in Story 6.2
```

| Module | Creates |
|---|---|
| `bootstrap/` | The S3 bucket that holds Terraform state (local state, run once) |
| `modules/network` | VPC, subnets, NAT, route tables, S3 gateway endpoint, security groups |
| `modules/edge` | Both ACM certificates, SPA bucket + OAC, internal ALB + HTTPS listener + empty API target group, CloudFront VPC origin, distribution, SPA-rewrite function, Route 53 records |
| `modules/identity` | Cognito user pool, hosted-login domain, BFF app client, the planner user |
| `envs/portfolio` | Wires the three modules together; the only place with `provider` blocks |

Not here yet: RDS, the evidence bucket, ECR, Secrets Manager, log groups, Budgets,
IAM task roles and GitHub OIDC (Story 6.2); the ECS cluster, services and task
definitions (Story 6.3).

### Open against AC2 until Story 6.2

AC2 asks for "RDS requires TLS" and for RDS, logs and secrets to be encrypted at
rest. Those resources do not exist yet, so those clauses cannot be met or checked
in 6.1. Story 6.1 meets AC2 for every resource it creates (SPA bucket, state
bucket, CloudFront, ALB, security groups) and builds the private data subnets and
the `data` security group that RDS will use. AC2 is fully met only once 6.2 lands.

## Prerequisites

These are not Terraform resources. A domain purchase is a billing act, not
reproducible infrastructure.

1. **An AWS account** and permission to create the resources above. The operator
   identity is broad on purpose in this practice environment; a least-privilege
   deploy role arrives with GitHub OIDC in Story 6.2.
2. **Credentials from IAM Identity Center**, not IAM-user access keys:

   ```bash
   aws configure sso            # once; name the profile, e.g. shiftmind
   aws sso login --profile shiftmind
   export AWS_PROFILE=shiftmind # PowerShell: $env:AWS_PROFILE = "shiftmind"
   aws sts get-caller-identity  # confirm the account before touching anything
   ```

3. **A registered domain and a public Route 53 hosted zone** for it, with the
   registrar's NS records already delegated to that zone. Terraform looks the zone
   up by name (`hosted_zone_name`) and never creates it. If delegation is missing,
   ACM DNS validation waits until it times out.
4. **Terraform 1.15.x** (`required_version = "~> 1.15.0"`) and **AWS CLI v2**.
   Windows: `winget install Hashicorp.Terraform` installs the latest release,
   which may be newer than 1.15; install the newest 1.15.x from
   <https://releases.hashicorp.com/terraform/> instead and put it first on `PATH`.
   CI pins the same version (`TERRAFORM_VERSION` in `.github/workflows/infra.yml`).
5. `python3` and `curl` for the smoke script.

## 1. Bootstrap the state bucket (once)

```bash
cd infra/terraform/bootstrap
cp terraform.tfvars.example terraform.tfvars     # gitignored; set state_bucket_name
terraform init
terraform plan -out=tfplan
terraform show tfplan                            # review it
terraform apply tfplan
terraform output                                 # note state_bucket_name and region
```

The bucket has versioning, SSE-S3, all four Block Public Access flags,
`BucketOwnerEnforced` and a policy that denies `aws:SecureTransport = false`. The
bootstrap root keeps its own state **locally** (gitignored `terraform.tfstate`).
If that file is lost, re-adopt the bucket:

```bash
terraform import aws_s3_bucket.state <bucket-name>
terraform import aws_s3_bucket_public_access_block.state <bucket-name>
terraform import aws_s3_bucket_ownership_controls.state <bucket-name>
terraform import aws_s3_bucket_versioning.state <bucket-name>
terraform import aws_s3_bucket_server_side_encryption_configuration.state <bucket-name>
terraform import aws_s3_bucket_policy.state <bucket-name>
```

## 2. Plan, review, apply the environment

```bash
cd infra/terraform/envs/portfolio
cp terraform.tfvars.example terraform.tfvars     # hosted_zone_name, app_domain, planner_email, ...
cp backend.hcl.example backend.hcl               # bucket + region from step 1
terraform init -backend-config=backend.hcl
terraform plan -out=tfplan
terraform show tfplan                            # the review: read it before applying
terraform apply tfplan                           # apply that exact plan file
```

Apply the **saved plan file**, not a fresh `terraform apply`, so what was reviewed
is exactly what runs. Expect the first apply to take roughly 20–30 minutes: a
CloudFront VPC origin takes about 15 minutes to create (and again to delete), and a
distribution needs several more to deploy.

Then prove that nothing was fixed up in the console. This must exit `0`:

```bash
terraform plan -detailed-exitcode                # 0 = no changes, 2 = drift, 1 = error
```

`availability_zones` defaults to the first two AZs of the region. If the apply
rejects the VPC origin for an AZ, set `availability_zones` in `terraform.tfvars`
to two AZs that CloudFront VPC origins support.

## 3. Edge smoke

```bash
bash infra/scripts/smoke-edge.sh                 # run from the repo root, same credentials
```

It waits for the distribution, uploads a throwaway `index.html` placeholder (and
refuses to overwrite a real SPA unless `SMOKE_OVERWRITE_INDEX=1`), then asserts:

| # | Check |
|---|---|
| 1 | `https://<app>/` returns the placeholder; a TLS 1.1 handshake is refused |
| 2 | `http://<app>/` returns 301 to https |
| 3 | `/scenario-data` returns the placeholder (SPA rewrite); `/assets/missing.js` is **not** rewritten |
| 4 | `GET /api/v1/auth/session` returns **503 from the ALB** (empty target group). **502 means the origin certificate does not match `origin.<app_domain>`** |
| 5 | `POST /api/v1/anything` reaches the ALB (503), not a CloudFront 403 |
| 6 | `origin.<app_domain>` resolves only to RFC 1918 addresses, and a direct request fails |
| 7 | The direct S3 object URL returns 403 |
| 8 | OIDC discovery `issuer` equals the `oidc_issuer` output exactly; `authorization_endpoint` is on the Cognito domain |
| 9 | The authorize URL for the exact BFF callback is not `redirect_mismatch` |
| 10 | `describe-user-pool` shows `AllowAdminCreateUserOnly: true` |
| 11 | The live `/api/*` and default behaviors use the managed cache and origin-request policies |

Item 11 exists because the offline tests cannot prove it: a mocked data source's
`id` is always null, so `terraform test` asserts the policy *names* only.

Sign-in itself cannot be exercised yet. It needs the deployed API (Story 6.3).

### The planner's first sign-in

Terraform creates the planner user with `desired_delivery_mediums = ["EMAIL"]`, so
Cognito emails a temporary password. No password exists in code, tfvars or state.
The `planner_subject` output is that user's `sub`, which Story 6.3 passes as
`SHIFTMIND_SEED_PLANNER_SUBJECT` (`docs/CONFIGURATION.md`). It is a server-generated
UUID known only after the user exists, which is why it is an output and not an input.

## Offline checks (no AWS account)

CI runs them without credentials; run the same locally:

```bash
terraform fmt -check -recursive infra/terraform
cd infra/terraform/modules/network && terraform init -backend=false && terraform validate && terraform test
```

See [`TESTING.md`](TESTING.md#infrastructure-terraform-test) for what they prove and what they cannot.

## Approximate idle cost

Measured on 2026-10-07 from the public AWS price lists for `ap-southeast-1`
(on-demand, 730 hours per month). Re-measure before relying on it; prices change.

| Resource | Price | Per month, idle |
|---|---|---|
| NAT gateway | $0.059 per hour | $43.07 |
| Public IPv4 address on the NAT gateway | $0.005 per hour | $3.65 |
| Application Load Balancer | $0.0252 per hour | $18.40 |
| Route 53 hosted zone | $0.50 per zone | $0.50 |
| **Fixed total** | | **about $65.6** |

Usage-based charges are not included and are near zero for one planner: NAT data
processing is $0.059 per GB, ALB capacity units are $0.008 per LCU-hour, and
Cognito Essentials lists $0.015 per monthly active user. CloudFront, S3 and ACM
add no meaningful idle cost, and the CloudFront price list has no separate
line item for VPC origins. This figure is **before** Story 6.2's RDS and Story
6.3's Fargate tasks, which will raise it.

The NAT gateway is the largest line. If the environment is not in use, destroy it
(below) rather than leaving it running.

## Teardown

Everything is destroyable: Cognito `deletion_protection` is `INACTIVE`, the ALB has
no deletion protection, and the SPA bucket uses `force_destroy`. Teardown order is
the reverse of creation:

```bash
# 1. The environment. Allow ~15 minutes: the VPC origin is slow to delete.
cd infra/terraform/envs/portfolio
terraform plan -destroy -out=tfplan && terraform show tfplan
terraform apply tfplan

# 2. The state bucket, only if you are done with the project entirely.
#    It is versioned, so empty every version and delete marker first
#    (`aws s3 rm --recursive` does not remove versions), then:
cd ../../bootstrap
terraform destroy
```

Leave the state bucket in place if you may redeploy: it costs almost nothing, and
it is the only copy of the environment's state.

## Known limitations of Story 6.1's environment

- **One NAT gateway**, so the app tier's egress is a single-AZ point of failure.
  Story 6.3 records this in its environment-limitations section.
- **Egress is open on 443.** API and worker tasks can reach any internet host over
  HTTPS; there is no egress filtering.
- **TLS ends at the ALB.** CloudFront-to-ALB is HTTPS (TLS 1.2), but ALB-to-task
  traffic on port 8000 is plain HTTP inside the private subnets.
- **No WAF, no HSTS or other response-header policy, no CloudFront or ALB access
  logging.** None is in AR17, and each costs something.
- **`origin.<app_domain>` is a public DNS record** that discloses the ALB's private
  addresses. Those addresses are unroutable from the internet.
- **Authentication is not enforced at the edge.** Every `/api/*` request reaches
  the ALB; authentication and authorization stay the API's job (AD-3).
- **The Cognito client secret is in Terraform state**, which is why the state
  bucket is private, encrypted, versioned and TLS-only.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `https://<app>/api/...` returns **502** | The ALB certificate does not match `origin.<app_domain>` (CloudFront validates the origin certificate against the origin hostname) |
| `/api/...` returns **503** | Expected until Story 6.3 registers tasks in the target group |
| `init` fails with `releases.hashicorp.com: read` | A transient provider download failure; rerun `terraform init` |
| ACM validation never finishes | The hosted zone's NS records are not delegated at the registrar |
| `terraform validate` in `modules/edge` reports a provider configuration "removed from state" | A standalone `validate` rejects `configuration_aliases`; validate through `envs/portfolio`, which instantiates the module with both providers |
