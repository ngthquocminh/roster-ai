# Version and Edge Convergence Verification

**Target:** `ARCHITECTURE-SPINE.md`  
**Scope:** final verification of query forwarding, SSE edge proof, PostgreSQL runtime-role restrictions, and PydanticAI V2 substitution wording  
**Reviewed:** 2026-07-22  
**Verdict:** **PASS**

All four previously open findings are resolved. No remaining concrete hole was found in this focused scope.

| Check | Result | Evidence in the spine |
| --- | --- | --- |
| CloudFront query forwarding | **PASS** | AD-21 explicitly requires CloudFront to forward query strings in addition to cookies, `Origin`, CSRF, `Last-Event-ID`, and required methods. This closes the cursor/filter loss path independently of cache disablement. |
| Unsupported buffering claim and SSE proof | **PASS** | AD-21 no longer asserts a generic CloudFront buffering switch. It instead requires an end-to-end test through CloudFront and ALB proving streamed heartbeats, reconnect, and replay, while retaining the heartbeat-versus-timeout contract. |
| PostgreSQL runtime-role RLS guarantees | **PASS** | AD-23 explicitly makes API, worker, and lease roles non-owner `NOSUPERUSER NOBYPASSRLS` roles, retains `ENABLE` plus `FORCE ROW LEVEL SECURITY`, and limits bootstrap/lease access through hardened functions before tenant-scoped work. |
| PydanticAI substitution wording | **PASS** | AD-19 now says a different **V2 release** may replace the seed only after the same compatibility evidence, avoiding the earlier patch-only restriction while preserving the proof gate. |

**Final conclusion:** the prior version/edge/RLS/PydanticAI convergence findings are closed. The spine is implementation-ready under this review lens.
