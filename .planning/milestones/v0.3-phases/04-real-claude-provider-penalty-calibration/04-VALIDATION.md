---
phase: 4
slug: real-claude-provider-penalty-calibration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-06
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | backend/pyproject.toml |
| **Quick run command** | `cd backend && uv run pytest -m "not live" -q` |
| **Full suite command** | `cd backend && uv run pytest -m "not live"` |
| **Estimated runtime** | ~TBD seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest -m "not live" -q`
- **After every plan wave:** Run `uv run pytest -m "not live"`
- **Before `/gsd-verify-work`:** Full suite must be green (default CI stays stub-only, no API key)
- **Max feedback latency:** TBD seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 4-01-01 | 01 | 1 | REQ-LLM-02 | — | N/A | unit | `uv run pytest -m "not live" -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Register `live` pytest marker + `addopts = "-m \"not live\""` in `backend/pyproject.toml`

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live Gemini parse-path parity | REQ-TEST-04 | Requires real GEMINI_API_KEY; excluded from default CI | Set GEMINI_API_KEY, run `uv run pytest -m live` |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < TBDs
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
