---
phase: 2
slug: full-5-tool-set-safe-validation
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-06-29
---

# Phase 2 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

Register authored at plan time (all four PLAN.md files carried `<threat_model>` blocks).
Verification performed at ASVS L1 grep-depth; block-on threshold = `high`. All
mitigate-disposition threats have evidence in the implementation; accept-disposition
threats are documented in the Accepted Risks Log. **threats_open: 0.**

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| client → POST /constraints | Untrusted NL text + scenario_id cross into the service | Free-text constraint (≤2000 chars), scenario_id |
| NL text → tool args | Untrusted numeric args (factor, max_hours, day) cross into the solver model | Parsed tool-call arguments |
| service → override store | Resolved tool calls cross into persisted `scenario.overrides` JSON | Validated override records |
| service → CP-SAT builder | Resolved override args cross into variable construction | Numeric penalty/bound parameters |
| solver output → run result JSON | Computed metrics/warnings cross into the persisted run record | Metrics + degeneracy warnings |
| test harness → app | Stub provider + stub engine injected via `dependency_overrides`; no live API crosses | Test fixtures only (no network) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-02-01 | Tampering | NL text → reference resolution | high | mitigate | `_resolve_task`/`_resolve_member` (constraint_service.py:45,84) validate every token against real scenario IDs; unknown → `rejected[]`, never persisted (VAL-02). | closed |
| T-02-02 | Tampering | parse_and_store persistence path | high | mitigate | Read-modify-write persists `applied` only; rejected/clarification are response-only (constraint_service.py:14,156). | closed |
| T-02-03 | Denial of Service | NL text length | low | mitigate | `text: Field(min_length=1, max_length=2000)` (schemas.py:36). | closed |
| T-02-04 | Information Disclosure | rejection error strings | low | accept | Error lists valid task/member options for the user's own scenario only — no multi-tenant model this milestone. | closed (accepted) |
| T-02-05 | Tampering | scale_demand factor | high | mitigate | `factor <= 0` rejected (constraint_service.py:223); scaling in `_aggregate_demand` where unmet slack absorbs shortfall — no factor makes the solve infeasible (D-10). | closed |
| T-02-06 | Tampering | set_max_hours overflow var | high | mitigate | `max_hours > 0` enforced; bounded overflow `NewIntVar` layered under the existing HARD cap (builder.py:385; Pitfall 3). | closed |
| T-02-07 | Tampering | lock_worker_shift day index | medium | mitigate | `day` validated against `0..max_day` (constraint_service.py:257-259); absent-bool keeps model feasible with no candidates (D-07). | closed |
| T-02-08 | Denial of Service | pathological multi-tool input | medium | mitigate | Text capped at 2000 chars; every penalty term is a bounded IntVar/BoolVar — no unbounded variable growth. | closed |
| T-02-09 | Repudiation | degenerate solve narrated as success | medium | mitigate | Zero-coverage families flagged in `warnings` so the run record carries an honest signal (engine.py:116-124; ENG-05). | closed |
| T-02-10 | Tampering | detection altering run status | high | mitigate | Detection is append-only to `warnings`; `status=lex.status` never read/written by it (engine.py:125); asserted by tests. | closed |
| T-02-11 | Tampering | mixed multi-tool persistence | high | mitigate | Tests assert that in a mixed call only the valid constraint persists — no out-of-bounds fragment reaches the store (criterion 5 / VAL-02). | closed |
| T-02-12 | Spoofing | live LLM in CI | medium | mitigate | All tests force `StubLLMProvider` via `app.dependency_overrides[get_llm_provider]`; no API key, no network (TEST-01). | closed |
| T-02-SC | Tampering | dependency supply chain | low | accept | No new packages installed this phase (RESEARCH Package Legitimacy Audit: N/A). | closed (accepted) |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-02-01 | T-02-04 | Rejection errors enumerate only the requester's own scenario IDs; no cross-tenant data exposure (single-tenant milestone). | MinhNTQ | 2026-06-29 |
| AR-02-02 | T-02-SC | Phase added no new dependencies; supply-chain surface unchanged. | MinhNTQ | 2026-06-29 |

*Accepted risks do not resurface in future audit runs.*

---

## Out-of-Register Findings (cross-referenced from code review)

These were surfaced by `02-REVIEW.md` and fall **outside** the Phase-2 threat register
(they live in the scenario-loading / provider-contract surfaces, not the NL-constraint
path this phase added). Recorded here so they are not lost; they do **not** count toward
`threats_open` for Phase 2.

| Ref | Severity | Component | Note | Recommended owner |
|-----|----------|-----------|------|-------------------|
| WR-04 | warning (potential high) | `constraint_service.py:152` `scenario["fixture"]` path-join + `json.load`, unsanitized; scenarios router does an `isfile` check, not containment | Possible arbitrary JSON file read via `../` or absolute path. Scenario fixtures are operator-supplied today (low live risk), but should gain a containment check before any untrusted scenario-creation surface ships. | Phase 4 / scenario-input hardening |
| WR-01 | warning | `constraint_service.py` arg parsing | `KeyError`/`ValueError` on malformed provider output escapes as 500 instead of `rejected[]` — latent with the stub, live once the Phase-4 Claude provider plugs in. | Phase 4 (real provider) |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-06-29 | 13 | 13 | 0 | gsd-secure-phase (L1, ASVS-1) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-06-29
