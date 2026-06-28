---
phase: 2
slug: full-5-tool-set-safe-validation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-29
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (dev dependency, see backend/pyproject.toml) |
| **Config file** | backend/pyproject.toml (test paths); backend/conftest.py (sys.path + fixtures) |
| **Quick run command** | `cd backend && python -m pytest tests/test_api.py -q` |
| **Full suite command** | `cd backend && python -m pytest -q` |
| **Estimated runtime** | ~15-45 seconds (stub engine + stub LLM; no live network) |

---

## Sampling Rate

- **After every task commit:** Run quick run command
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD (planner fills from PLAN.md tasks) | — | — | NLC-02..05 / VAL-01..03 / ENG-05 / TEST-03 | — | unsafe/unknown/degenerate input rejected before solver | unit + api | `python -m pytest -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/` validation cases for unknown IDs, out-of-bounds args, and mixed valid/invalid multi-tool call (TEST-03) — extend the existing `StubEngine` + `app.dependency_overrides` pattern in `backend/tests/test_api.py`
- [ ] Update existing Phase-1 response-shape assertions to the new `applied[]/rejected[]/clarification_needed/no_constraint_found` body

*Existing pytest infrastructure (conftest.py, StubEngine) covers framework needs — no new framework install required.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| (none expected) | — | All five success criteria are automatable via stub LLM + stub/real engine | — |

*All phase behaviors should have automated verification (no live LLM in CI — stub provider drives tests).*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
