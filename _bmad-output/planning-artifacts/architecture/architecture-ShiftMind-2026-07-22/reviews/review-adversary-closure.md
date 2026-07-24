# Adversarial Closure Check

**Verdict:** **FAIL — one concrete blocker remains.**

- **The session and lease bootstrap functions are not explicitly declared `SECURITY DEFINER`.** AD-23 now gives `shiftmind_owner` the tables/functions, denies runtime roles inheritance, bypass-RLS, ownership, and direct access to `auth.session_index`/`workflow.job_queue`, then permits those roles only to execute owner-held hardened functions. PostgreSQL functions are `SECURITY INVOKER` by default: merely being owner-held does not make them run with the owner's privileges. As written, `auth.resolve_session` and `workflow.lease_next_job` execute as callers that have no table access and therefore cannot resolve or lease anything. State explicitly that both are `SECURITY DEFINER` functions owned by NOLOGIN `shiftmind_owner` (retaining the fixed `search_path`, PUBLIC revoke, no dynamic SQL, and execute-only grants already specified). With that wording, the last four-hole set converges.
