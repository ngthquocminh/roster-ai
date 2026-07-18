---
phase: 03
slug: run-execution-history
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-07-18
---

# Phase 03 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| browser → backend (fetch) | `listRuns`/`triggerRun` — scenario_id path param crosses into a read-only GET / a POST; same-origin-configured first-party calls to the project's own FastAPI backend (no third-party API) | scenario_id (path param), RunOut payloads |
| polling loop → browser resources | `useRuns`'s `refetchInterval` schedules repeated background fetches while any run is non-terminal | none (client-side resource usage only) |
| backend `RunOut.error` string → DOM | a server-recorded error message (potentially long, multi-line, or containing HTML/unicode) is rendered into the run history table | RunOut.error (free text) |
| hand-typed / bookmarked URL → Runs view | a user can deep-link to `/scenarios/:anyId/runs` with an arbitrary (possibly nonexistent) scenarioId | scenarioId (route param) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-3-01 | Tampering | `listRuns`/`triggerRun` path param | low | mitigate | `scenario_id` passed as a typed openapi-fetch path param (URL-encoded), never string-concatenated — verified: `frontend/src/api/runs.ts:16,27` use `params: { path: { scenario_id: scenarioId } }` | closed |
| T-3-02 | Information disclosure | thrown `{ status, ...error }` | low | accept | Attached error may carry backend detail but is thrown for status-branching only; downstream components render fixed copy, not the error body. Internal demo app, no auth (out of scope per REQUIREMENTS.md). | closed |
| T-3-SC | Tampering (supply chain) | npm/pip/cargo installs | n/a | n/a | No package installs this phase — verified: `git diff` on `frontend/package.json` across the phase's commit range is empty | closed |
| T-3-03 | Denial of service | `useRuns` `refetchInterval` | medium | mitigate | Interval predicate returns `false` the instant `hasActiveRun` is false; React Query clears the interval on unmount; no hand-rolled `setInterval` — verified: `frontend/src/hooks/useRuns.ts:30-31` | closed |
| T-3-04 | Tampering | `["runs", scenarioId]` key drift | low | mitigate | `useTriggerRun`'s invalidation key and `useRuns`'s query key asserted byte-identical — verified: both hooks use `["runs", scenarioId]` literally (`useRuns.ts:28`, `useTriggerRun.ts:29`) | closed |
| T-3-05 | Tampering (XSS) | `RunHistoryTable` error/timestamp/status cells | high | mitigate | `run.error` and every cell value render as plain JSX text children only — no `dangerouslySetInnerHTML` anywhere in the file (self-documented at `RunHistoryTable.tsx:24`); proven by a negative test asserting no element is created from an HTML-looking error string | closed |
| T-3-06 | Information disclosure | inline FAILED error text | low | accept | RUN-05 deliberately surfaces the recorded error to the user; this is required behavior, not a leak. Internal unauthenticated demo app; residual risk accepted. | closed |
| T-3-07 | Information disclosure | `TriggerRunButton` error line | low | mitigate | Renders one of two fixed copy strings selected by `getErrorStatus(error)`; backend error body never rendered — verified: `TriggerRunButton.tsx:17,35` | closed |
| T-3-08 | Repudiation / honesty | `RunInFlightPanel` + `TriggerRunButton` affordances | medium | mitigate | Negative tests assert no cancel control and no progressbar/determinate-progress element in any state — self-documented at `RunInFlightPanel.tsx:13`, `TriggerRunButton.tsx:9` | closed |
| T-3-09 | Tampering / injection | deep-link scenarioId → `useRuns` → `listRuns` | low | mitigate | scenarioId flows only into a read-only GET as a typed, URL-encoded path param; a nonexistent scenarioId returns an empty list (endpoint does not 404), so the view renders the ordinary empty state rather than a gate | closed |
| T-3-10 | Elevation / scope | Results tab + `runs/:runId` route | low | mitigate | Phase does not enable the disabled Results tab or build ResultsView content — verified: `git diff` on `ScenarioLayout.tsx` across the phase's commit range is empty; `ScenarioLayout.tsx:59-60` still renders `disabled` / `aria-disabled="true"` | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on (high) count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-3-01 | T-3-02 | Thrown `{status, ...error}` may carry backend detail, but it is used for status-branching only — no component renders the raw error body. Internal, unauthenticated demo app (auth out of scope per REQUIREMENTS.md). | plan author (03-01-PLAN.md) | 2026-07-18 |
| AR-3-02 | T-3-06 | RUN-05 requires the FAILED run's error text to be shown inline — this is the feature's required behavior, not an unintended leak. Internal, unauthenticated demo app. | plan author (03-03-PLAN.md) | 2026-07-18 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-07-18 | 10 (+1 n/a) | 10 | 0 | /gsd-secure-phase orchestrator (L1 grep-depth, register authored at plan time — short-circuit per ASVS L1 rule, no auditor spawn required) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-18
