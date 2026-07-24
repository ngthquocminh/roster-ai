# Architecture-Spine Closure Check

**Target:** `ARCHITECTURE-SPINE.md`  
**Reviewed:** 2026-07-22  
**Verdict:** **PASS**

Both previously open conditions are closed.

- AD-7 now permits both `AgentRun` and `ScheduleRun` to leave `queued` as `timed_out` or `failed`, in addition to running or planner cancellation (`ARCHITECTURE-SPINE.md:92-121`). This makes accepted queue-time wall-clock exhaustion and unrecoverable pre-lease failure representable without reopening the separated workflow state machines.
- Stack now uses Node.js `24.18.0 LTS` and Terraform `1.15.8`, matching the current official stable/LTS choices verified on 2026-07-22. Each remains explicitly a planned seed with an enforceable adoption gate: commit the Node toolchain pin and pass install/test/typecheck/build; constrain Terraform with `required_version` and validate providers/plan in CI (`ARCHITECTURE-SPINE.md:255-278`).

No remaining blocker was found within this closure scope.
