---
phase: 2
slug: full-5-tool-set-safe-validation
status: validated
nyquist_compliant: false
wave_0_complete: true
created: 2026-06-29
updated: 2026-06-29
---

# Phase 2 — Validation Strategy

> Per-phase validation contract. Audited post-execution: 8/9 requirements have
> automated coverage; ENG-05's real-engine path is recorded as manual-only.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (dev dependency, see backend/pyproject.toml) |
| **Config file** | backend/pyproject.toml (`testpaths = ["tests"]`); backend/conftest.py (sys.path + fixtures) |
| **Quick run command** | `cd backend && uv run pytest tests/test_constraints_api.py -q` |
| **Full suite command** | `cd backend && uv run pytest -q` |
| **Estimated runtime** | ~5-8 seconds (stub engine + stub LLM; no live network) |

> ⚠️ Run via `uv run pytest`, NOT bare `python -m pytest` — the latter resolves the
> system anaconda interpreter (old `httpx`) and fails at import. The project venv is
> `backend/.venv`. Last full run: **80 passed**.

---

## Sampling Rate

- **After every task commit:** Run quick run command
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Requirement | Plan | Secure Behavior | Test Type | Automated Command | Test File | Status |
|-------------|------|-----------------|-----------|-------------------|-----------|--------|
| NLC-02..05 (five tools parse + echo) | 02-01, 02-02 | All five constraints parsed; readable `parsed_constraint` echo | api + unit | `uv run pytest -q` | `tests/test_constraints_api.py`, `tests/test_engine_overrides.py` | ✅ green |
| VAL-01 (arg bounds) | 02-02 | `factor>0`, `max_hours>0`, day-in-horizon enforced | api | `uv run pytest -q` | `tests/test_constraints_api.py` | ✅ green |
| VAL-02 (unknown-ID reject + non-persist) | 02-01, 02-04 | Unknown task/member → `rejected[]`, never persisted | api | `uv run pytest -q` | `tests/test_constraints_api.py` | ✅ green |
| VAL-03 (parse-UX fields) | 02-01 | `no_constraint_found` / `clarification_needed` signals | api | `uv run pytest -q` | `tests/test_constraints_api.py` | ✅ green |
| ENG-05 (degeneracy — detection logic) | 02-03 | Zero-coverage family flagged; status untouched | unit | `uv run pytest -q` | `tests/test_engine_degenerate.py` | ⚠️ green via mirror only |
| ENG-05 (degeneracy — **real `CpSatEngine.solve()` path**) | 02-03 | Real solve over unservable demand emits warnings + leaves `status` unchanged | — | — | — | 🔶 manual-only (see below) |
| TEST-03 (validation suite) | 02-04 | Unknown IDs / OOB args / mixed multi-tool rejected pre-solver | api | `uv run pytest -q` | `tests/test_constraints_api.py` | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ partial · 🔶 manual-only*

---

## Wave 0 Requirements

- [x] `backend/tests/` validation cases for unknown IDs, out-of-bounds args, and mixed valid/invalid multi-tool call (TEST-03) — delivered in `test_constraints_api.py`
- [x] Phase-1 response-shape assertions updated to the new `applied[]/rejected[]/clarification_needed/no_constraint_found` body

*Existing pytest infrastructure (conftest.py, StubEngine) covered framework needs — no new framework install required.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real-engine degeneracy detection | ENG-05 | `test_engine_degenerate.py` validates a hand-copied `_detect_warnings` mirror (test file lines 20-33), not the real loop in `engine/cpsat/engine.py:116-124`. The production detection + `status=lex.status` invariant therefore have no automated coverage; a drift between the copy and the real loop would pass green. Confirmed by code-review WR-05. Accepted as manual-only on 2026-06-29 (user decision). | Build a `SchedulingProblem` with a task family that has real demand but no qualified/available workers (zero supply), call `create_engine("cpsat").solve(problem, config)`, and assert: (1) `result.warnings` contains an entry naming the starved family + its required hours, and (2) `result.status` equals the solver's own status (detection did not alter it). Recommended to promote to an automated test in a future hardening pass. |

*Tracked for automation in a later pass — not blocking Phase 2.*

---

## Validation Audit 2026-06-29

| Metric | Count |
|--------|-------|
| Requirements audited | 9 |
| Covered (automated) | 8 |
| Manual-only (escalated) | 1 (ENG-05 real-engine path) |
| Missing | 0 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or a documented manual-only entry
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none remain)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [ ] `nyquist_compliant: true` — **not set**; one manual-only gap (ENG-05 real-engine path) remains by user decision

**Approval:** validated (partial) 2026-06-29
