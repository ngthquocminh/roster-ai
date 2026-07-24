# Adversarial Closure Verification

**Verdict:** **PASS**

AD-23 now explicitly declares both `auth.resolve_session` and `workflow.lease_next_job` as owner-held `SECURITY DEFINER` functions. It also revokes PUBLIC, grants `EXECUTE` only to the corresponding caller role, fixes `search_path`, prohibits dynamic SQL, keeps runtime roles `NOINHERIT NOSUPERUSER NOBYPASSRLS`, and starts domain work in a new tenant-scoped transaction. The final identified RLS bootstrap/leasing blocker is closed.
