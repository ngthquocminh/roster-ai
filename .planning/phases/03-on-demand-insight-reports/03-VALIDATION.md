---
phase: 3
slug: on-demand-insight-reports
status: draft
nyquist_compliant: false
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
| _to be filled by planner_ | | | INS-01..04 | T-3-xx | | unit/api | `uv run pytest ...` | | ⬜ pending |

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

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
