# Final Version, Edge, RLS, S3, and PydanticAI Re-review

**Target:** `ARCHITECTURE-SPINE.md`  
**Lens:** resolution of the prior version/provenance, CloudFront/ALB edge, PostgreSQL RLS, S3 create-only, and PydanticAI findings; check for unsupported claims introduced by the fixes  
**Reviewed:** 2026-07-22  
**Verdict:** **NEEDS MINOR CHANGES — the architecture direction is supportable and three of the five prior findings are fully resolved, but the edge policy omits query-string forwarding and describes a CloudFront buffering control that AWS does not document; the RLS runtime-role restriction should also be made explicit.**

No newly introduced technology family is nonexistent or incompatible with the proposed modular-monolith deployment. The revised stack provenance, PydanticAI compatibility gate, S3 create-only controls, retention settings, and most of the edge/RLS controls are materially stronger and implementation-oriented. The remaining items are narrow wording/configuration corrections, not reasons to revisit the selected architecture.

## Prior-finding disposition

| Prior finding | Status | Final assessment |
| --- | --- | --- |
| Brownfield locks versus planned seeds | **RESOLVED** | The stack table now has an explicit status/basis column. Python 3.12 is correctly described as a planned target within the repository constraint, Node 22.22.0 as an unpinned local seed, repository-resolved packages as locks, and new backend/infrastructure packages as planned seeds. |
| CloudFront/ALB SSE and BFF behavior | **PARTIALLY RESOLVED** | AD-21 now binds cache disablement, cookies and relevant headers, allowed methods, a 15-second heartbeat, and timeouts above that heartbeat. It still omits query strings from the origin-request policy and uses unsupported “disables buffering” wording. |
| PostgreSQL RLS role and owner constraints | **PARTIALLY RESOLVED** | AD-23 now separates the migration owner, enables and forces RLS, and binds transaction-local tenant context. “Restricted” runtime roles should explicitly mean `NOSUPERUSER NOBYPASSRLS`; `FORCE ROW LEVEL SECURITY` does not constrain those bypass-capable roles. |
| S3 create-only evidence semantics | **RESOLVED** | AD-23 binds content/version-addressed keys, bucket versioning, an `If-None-Match: *` bucket-policy requirement, and no `DeleteObject` permission for application roles. It also correctly distinguishes product-level create-only behavior from regulatory WORM. |
| PydanticAI freshness and compatibility | **RESOLVED, WITH ONE EDITORIAL TIGHTENING** | AD-19 now requires an exact compatibility spike covering Python/Pydantic/provider fit, deferred calls, deterministic doubles, owned durable-message translation, and content-disabled instrumentation before adoption. Version 2.14.1 is a real, supportable seed. The phrase “different V2 patch” is unnecessarily narrow; “different V2 release” is the semantically correct gate. |

## Remaining findings

### HIGH — AD-21 must forward API query strings independently of cache disablement

AD-21 explicitly forwards cookies, `Origin`, CSRF, and `Last-Event-ID`, but it does not say that query strings are forwarded. CloudFront does not send viewer query strings, arbitrary headers, or cookies to the origin by default. A cache-disabled behavior does not itself establish an origin-request policy that forwards query strings. AWS treats query strings as a separate origin-request-policy dimension. [CloudFront origin-request policies](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/controlling-origin-requests.html), [origin-request policy settings](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/origin-request-understand-origin-request-policy.html)

This matters because the spine includes cursor-, filter-, and bounded-window APIs. Those requests can silently reach FastAPI without their cursor/filter parameters while the Terraform still appears to satisfy the current prose.

**Required correction:** amend AD-21 to require forwarding all API query strings, or an explicit allow-list maintained with the OpenAPI contract. Keep them out of the cache key because the API/SSE behavior is cache-disabled; forward them through the origin-request policy.

### MEDIUM — “CloudFront disables buffering” is not an implementable CloudFront setting

AWS documents CloudFront cache policies, origin-request policies, allowed methods, and origin response/read timeout behavior. It does not document a cache-behavior or Terraform switch that disables response buffering. The revised sentence therefore risks sending an implementer looking for a control that does not exist.

The useful parts of the intended contract are already present: a cache-disabled API/SSE behavior, heartbeat traffic before the smallest edge/origin idle timeout, and forwarding of `Last-Event-ID`. CloudFront's origin response timeout applies while waiting for the response and between response packets, while ALB has its own idle timeout. [CloudFront origin timeout](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DownloadDistValuesOrigin.html), [ALB idle timeout](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/edit-load-balancer-attributes.html)

**Required correction:** remove “and buffering” from the asserted CloudFront configuration. Replace it with a deploy-time streaming proof: the first SSE bytes and periodic heartbeat must traverse CloudFront and ALB without aggregation or timeout, and reconnect with `Last-Event-ID` must replay correctly.

### MEDIUM — The runtime RLS role attributes remain implicit

AD-23 fixes the owner-bypass problem by separating migrations from API/worker roles and by applying `ENABLE` plus `FORCE ROW LEVEL SECURITY`. That is a strong correction. However, PostgreSQL states that superusers and roles with `BYPASSRLS` always bypass row security. Calling the runtime roles “restricted” does not make the prohibited role attributes testable. [PostgreSQL 18 row security](https://www.postgresql.org/docs/18/ddl-rowsecurity.html)

**Required correction:** state that API and worker roles are non-owner, `NOSUPERUSER NOBYPASSRLS` roles and require a migration/integration assertion against the actual deployed runtime roles. Preserve scoped repositories because referential-integrity operations and privileged maintenance are not tenant-isolation substitutes.

### LOW — Use “V2 release,” not “V2 patch,” in the PydanticAI gate

The selected PydanticAI 2.14.1 seed is valid, and the compatibility spike is the right control for a fast-moving dependency absent from the brownfield repository. Restricting substitution to another “patch” is needlessly narrower than the stated intent: a later compatible V2 minor may be the release that passes the spike.

**Required correction:** replace “a different V2 patch may replace the seed” with “a different V2 release may replace the seed.” Any selected version should then be exact-pinned in the implementation lockfile. [PydanticAI release page](https://pypi.org/project/pydantic-ai/)

## New-claim reality check

The fixes did not otherwise introduce unsupported service or library claims:

- **RDS retention:** a seven-day automated-backup retention period is supported and is an explicit configuration rather than a universal service default. A final snapshot at teardown is also supported, provided Terraform/deletion workflow binds it rather than relying on an operator convention. [RDS backup retention](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithAutomatedBackups.BackupRetention.html), [RDS deletion and final snapshots](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DeleteInstance.html)
- **CloudWatch retention:** thirty-day log-group retention is a supported configurable period. It must be set on each application log group because indefinite retention is otherwise possible. [CloudWatch log groups and retention](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Working-with-log-groups-and-streams.html)
- **PydanticAI instrumentation:** content-disabled instrumentation is supported; official instrumentation exposes `include_content=False` so prompts, completions, and tool content can be excluded while retaining structural telemetry. [PydanticAI instrumented models](https://pydantic.dev/docs/ai/api/models/instrumented/)
- **S3 create-only behavior:** conditional writes and policies requiring `If-None-Match` are supported. The new “not regulatory WORM” qualification is accurate and avoids overstating IAM/versioning controls. [S3 conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html), [enforcing conditional writes](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes-enforce.html)
- **Cognito enrollment:** disabling public self-service sign-up and using administrator-created users is supported. The architecture correctly leaves application membership enforcement outside Cognito. [Cognito user creation](https://docs.aws.amazon.com/cognito/latest/developerguide/how-to-create-user-accounts.html)

## Final gate

The architecture can proceed after four localized edits:

1. Add query-string forwarding to AD-21.
2. Replace the unsupported CloudFront “buffering” setting with an end-to-end SSE streaming/replay verification requirement.
3. Make `NOSUPERUSER NOBYPASSRLS` explicit for deployed API/worker roles.
4. Change PydanticAI “V2 patch” to “V2 release.”

With those edits, all five prior findings are closed and the revised claims are supported by current official documentation.
