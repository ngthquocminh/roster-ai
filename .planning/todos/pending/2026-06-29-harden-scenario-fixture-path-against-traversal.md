---
created: 2026-06-29T16:06:51.278Z
title: Harden scenario fixture path against traversal (WR-04)
area: api
resolves_phase: 4
source: 02-REVIEW.md (WR-04), 02-SECURITY.md (Out-of-Register Findings)
severity: warning (potential high)
files:
  - backend/services/constraint_service.py:152
  - backend/api/routers/scenarios.py
---

## Problem

`scenario["fixture"]` is path-joined and `json.load`'d **unsanitized** in
`backend/services/constraint_service.py:152`. The scenarios router only performs an
`isfile` existence check (not a containment check), so a crafted scenario `fixture`
value such as `"../../../etc/passwd"` (if JSON) or an absolute path enables an
**arbitrary JSON file read**.

Live risk is low today because scenario fixtures are operator-supplied, but this
becomes exploitable the moment any untrusted scenario-creation surface ships
(e.g. the Phase-4 frontend or a public API). Surfaced by the Phase 2 code review
and recorded in `02-SECURITY.md` as an out-of-register finding (outside the Phase 2
NL-constraint threat register — it lives in the scenario-loading path from Phase 1).

## Solution

Add a containment check before loading: resolve the fixture path
(`os.path.realpath` / `Path.resolve()`) and assert it stays within the allowed
scenario/fixture data dir (e.g. `ROSTERAI_DATA_DIR`). Reject absolute paths and any
resolved path that escapes the allowed root with a clear validation error (400/422),
before the `json.load`. Add a test for a `../`-style and absolute-path fixture value.

Carry into the Phase 4 plan as an explicit hardening task.
