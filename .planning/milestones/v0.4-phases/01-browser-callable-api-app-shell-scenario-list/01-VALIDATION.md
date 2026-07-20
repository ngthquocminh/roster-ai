---
phase: 1
slug: browser-callable-api-app-shell-scenario-list
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-16
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

This phase spans two test stacks: the existing backend pytest suite (BE-01) and a
frontend suite that does not exist yet (SHELL-*/SCEN-*). Both are represented below.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Backend: pytest (existing) · Frontend: Vitest 4.1.10 + @testing-library/react 16.3.2 + jsdom 29.1.1 — Wave 0 installs |
| **Config file** | Backend: `backend/pyproject.toml` `[tool.pytest.ini_options]` (`testpaths = ["tests"]`) · Frontend: none — Wave 0 adds a `test` block to `frontend/vite.config.ts` (Vitest reads Vite config natively) |
| **Quick run command** | Backend: `cd backend && uv run pytest tests/test_cors.py -x` · Frontend: `cd frontend && npx vitest run <file>` |
| **Full suite command** | Backend: `cd backend && uv run pytest` (excludes `-m live` per existing `addopts`) · Frontend: `cd frontend && npx vitest run` |
| **Estimated runtime** | ~30 seconds (backend ~15s existing suite, frontend ~10s cold) |

---

## Sampling Rate

- **After every task commit:** Run the single relevant test file's quick command — backend `uv run pytest tests/test_cors.py -x`, or frontend `npx vitest run <file>`
- **After every plan wave:** Run `cd backend && uv run pytest` **and** `cd frontend && npx vitest run`
- **Before `/gsd-verify-work`:** Both full suites must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

Task IDs bind at plan time — plans did not exist when this file was seeded. Rows are
keyed by requirement; `/gsd-validate-phase` fills the Task ID column once plans land.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | BE-01 | T-1-01 | Only env-configured origins receive CORS headers; allow-list is never `*` and `allow_credentials` stays default `False` | unit | `cd backend && uv run pytest tests/test_cors.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SHELL-01 | — | N/A | smoke (manual-only) | `cd frontend && npm run build` (exit 0) | N/A | ⬜ pending |
| TBD | TBD | TBD | SHELL-02 | — | N/A | typecheck + unit | `cd frontend && npx tsc --noEmit` + `npx vitest run src/api/scenarios.test.ts` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SHELL-03 | — | N/A | component | `cd frontend && npx vitest run src/routes/router.test.tsx` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SHELL-04 | T-1-02 | Unexpected (5xx/network) failures render fixed non-diagnostic copy — never raw `detail`, `error.stack`, or a caught exception's `.message` | component | `cd frontend && npx vitest run src/components/layout/ErrorBanner.test.tsx` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCEN-01 | T-1-03 | User-supplied scenario `name` renders only as JSX children — no `dangerouslySetInnerHTML` anywhere in this phase | component | `cd frontend && npx vitest run src/components/scenarios/ScenarioTable.test.tsx` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | SCEN-02 | T-1-03 | Fixture choice constrained to the `GET /fixtures` list (never free text); server `ScenarioCreate` validation remains the source of truth | component | `cd frontend && npx vitest run src/components/scenarios/CreateScenarioDialog.test.tsx` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Threat Ref legend** (seeded from RESEARCH.md `## Security Domain`, ASVS L1 — the
planner should reuse these IDs in its PLAN.md `<threat_model>` blocks rather than mint new ones):

| ID | Threat | STRIDE | Mitigation |
|----|--------|--------|------------|
| T-1-01 | CORS misconfiguration (wildcard origin, or wildcard + credentials) | Tampering / Information Disclosure | Explicit env-configured origin allow-list; `allow_credentials` left at default `False` |
| T-1-02 | Reflected/leaked backend internals in an error surface | Information Disclosure | Fixed, non-diagnostic copy per UI-SPEC Copywriting Contract for unexpected failures |
| T-1-03 | XSS via unescaped user-supplied scenario name | Tampering | React default JSX text-node escaping; no `dangerouslySetInnerHTML` for user data |

---

## Wave 0 Requirements

- [ ] `backend/tests/test_cors.py` — stubs for BE-01, following the existing env-before-import fixture pattern from `backend/tests/test_api.py`
- [ ] `frontend/vite.config.ts` `test` block (or `frontend/vitest.config.ts`) + `frontend/src/test/setup.ts` (jest-dom matchers) — shared fixtures
- [ ] `npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom` — framework install (no frontend framework detected)
- [ ] Test-only mock helper for the typed client (`vi.mock('../api/client')` or per-function `vi.fn()` stubs) — replaces the MSW path the research explicitly avoided (see RESEARCH.md `## Package Legitimacy Audit`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `npm run build` produces static assets | SHELL-01 | Build success is not a unit-testable behavior — verified by command exit code at execution/verify time | `cd frontend && npm run build`; assert exit 0 and `dist/` contains `index.html` + hashed assets |
| Real browser loads the app against the live backend with no CORS error in the console | BE-01, SCEN-01 | Cross-origin preflight behavior in a real browser is the criterion; pytest covers header emission but not the browser's enforcement | Start backend, `npm run dev`, open `http://localhost:5173`, confirm the scenario list renders and DevTools console shows no CORS error |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags (`vitest run`, never bare `vitest`)
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
