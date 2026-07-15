---
phase: 3
slug: on-demand-insight-reports
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-30
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (dev dependency) |
| **Config file** | `backend/pyproject.toml` (test paths) + `backend/tests/conftest.py` |
| **Quick run command** | `cd backend && uv run pytest tests/test_api.py -q` |
| **Full suite command** | `cd backend && uv run pytest -q` |
| **Estimated runtime** | ~30–60 seconds (no live LLM/network; stub-driven) |

---

## Sampling Rate

- **After every task commit:** Run quick command
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01 T1 | 03-01 | 1 | INS-01, INS-04 | — | RED: happy-path/not-ready/cache tests fail before impl | api | `uv run --directory backend pytest tests/test_insights_api.py -x` | ❌ creates it | ⬜ pending |
| 03-01 T2 | 03-01 | 1 | INS-03, INS-04 | T-3-01 | set_insight parameterized SQL; deterministic stub; insight_json column/migration | unit | `uv run --directory backend pytest tests/test_llm_provider.py -x` | ✅ extends | ⬜ pending |
| 03-01 T3 | 03-01 | 1 | INS-01, INS-03 (criterion 1, 4) | T-3-02, T-3-04 | grounding guard before persist; sync def off event loop; cache short-circuit | api | `uv run --directory backend pytest tests/test_insights_api.py -x` | ✅ | ⬜ pending |
| 03-02 T1 | 03-02 | 2 | INS-02, INS-03 (criterion 2, 3) | T-3-02, T-3-03, T-3-05 | provider-failure isolation (run stays COMPLETED, nothing cached); fabrication rejected 502; honest warning narration | api | `uv run --directory backend pytest tests/test_insights_api.py -x` | ✅ extends | ⬜ pending |
| 03-02 T2 | 03-02 | 2 | INS-03 (LLM-01/TEST-01) | — | deterministic, I/O-free generate_insights | unit | `uv run --directory backend pytest tests/test_llm_provider.py -x` | ✅ extends | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> Planner: derive one row per task covering the 4 success criteria — (1) generate-on-COMPLETED + not-ready body, (2) every report number grounded in metrics JSON (D-06 guard), (3) provider-failure leaves run COMPLETED + result untouched + nothing cached, (4) second fetch returns cache without re-calling provider. All stub-driven, no network.

---

## Wave 0 Requirements

- [ ] `backend/tests/` — insight endpoint tests (generate→cache→provider-failure→not-ready) using `app.dependency_overrides` on `get_llm_provider`
- [ ] Reuse `backend/tests/conftest.py` shared fixtures + temp DB
- [ ] pytest already present — no framework install needed

*Existing infrastructure (pytest + `StubEngine`/`dependency_overrides`) covers all phase requirements; planner extends it with a stub `generate_insights`.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| _none expected_ | | | |

*All phase behaviors have automated verification (stub-driven, deterministic per TEST-01).*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (03-01 Task 1 creates test_insights_api.py as the RED test)
- [x] No watch-mode flags
- [x] Feedback latency < 60s (stub-driven, no network)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planner-approved 2026-06-30
