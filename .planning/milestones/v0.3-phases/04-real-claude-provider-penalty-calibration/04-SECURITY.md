---
phase: 04
slug: real-claude-provider-penalty-calibration
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: 2026-07-15
---

# Phase 04 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|----------------|
| env → process | LLM provider/model/key read from the OS environment into the frozen `Settings` object | `LLM_PROVIDER`, `LLM_MODEL`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` |
| config → provider factory | `settings.llm_provider` string selects which backend `create_provider` instantiates | provider name string |
| process → Gemini API | Outbound network call to `generativelanguage.googleapis.com` carrying the bearer API key | API key, prompt/tool-call payload |
| NL text → model → tool args | Untrusted user constraint text influences the model's function-call arguments | free-text constraint → structured `OverrideCall` args |
| uv add google-genai | Third-party package pulled into the runtime | supply-chain trust |
| (04-03, none new) | Real CP-SAT engine + committed fixture + directly-built `OverrideCall`s; entirely offline | — |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-04-01 (plan 01) | Information Disclosure | `Settings.llm_api_key` (env-read key) | high | mitigate | `repr=False` field; key only ever passed as a kwarg into `create_provider`/`GeminiLLMProvider.__init__`/`OpenRouterLLMProvider.__init__` — never logged, persisted, returned, or interpolated into any string in `settings.py`/`api/deps.py`/`llm/base.py` (verified by inspection) | closed |
| T-04-02 (plan 01) | Elevation of Privilege | `create_provider` unknown-name path | low | mitigate | Fixed `"stub"`/`"gemini"`/`"openrouter"` branches only; unknown names raise `ValueError` (fail closed), no dynamic import of attacker-supplied module names (`backend/llm/base.py:53`) | closed |
| T-04-03 (plan 01) | Tampering | env-driven provider selection defaulting keyless | medium | mitigate | Default `LLM_PROVIDER="stub"` — zero network calls on the no-config path; automated test `test_default_settings_llm_defaults_keyless` (D2/04-01) confirms | closed |
| T-04-SC (plan 02) | Tampering | `uv add google-genai` (supply-chain legitimacy) | high | mitigate | Blocking human-verify checkpoint confirmed package identity on pypi.org + `github.com/googleapis/python-genai` before install; verdict recorded in `04-RESEARCH.md` Package Legitimacy Audit (never auto-approved) | closed |
| T-04-01 (plan 02) | Information Disclosure | Gemini API key at client construction + error paths | high | mitigate | Key flows only as `GeminiLLMProvider.__init__(api_key=...)` into `genai.Client`; automated grep verification (D5/04-02) confirms no occurrence in any log/exception/response string in `backend/llm/gemini.py` | closed |
| T-04-02 (plan 02) | Tampering | Prompt injection via NL text → out-of-schema/out-of-bounds tool args | medium | mitigate | Provider-agnostic `constraint_service` VAL-01 (bounds) + VAL-02 (real-id resolution) scrutinizes every `OverrideCall` regardless of producer (confirmed present, unchanged from Phase 2); AUTO mode + declaration-only tools prevent SDK auto-execution | closed |
| T-04-03 (plan 02) | Denial of Service | Denial-of-wallet via repeated live Gemini calls in CI | medium | mitigate | `live` pytest marker + `addopts = -m "not live"` exclude the live test by default; self-skips when key absent; automated test (D4/04-02) confirms default run makes zero Gemini calls | closed |
| T-04-05 (plan 02) | Denial of Service | LLM/network failure invalidating a computed schedule | high | mitigate | Insight generation is a separate post-run step; provider exceptions wrapped into `InsightGenerationError` (router → 502), run status/`result_json` never mutated (confirmed in `services/insight_service.py`) | closed |
| T-04-04 (plan 02) | Tampering | Fabricated numeric content in Gemini-authored insight text | low | accept | Existing Phase-3 `_grounding_guard` (D-06, provider-agnostic, unchanged) rejects any numeric token not traceable to the run's metrics; confirmed present in `services/insight_service.py`; prompt additionally instructs the model to cite only supplied figures | closed |
| T-04-06 (plan 03) | Tampering | Penalty weight miscalibrated so an override dominates round-2 cost | low | mitigate | `test_unsatisfiable_override_degrades_gracefully` bounded-cost assertion is the CI-enforced guard (D3/04-03, passing); sweep script sizes weights relative to baseline wage-cost magnitude | closed |
| T-04-07 (plan 03) | Tampering | Calibration script leaves `config.constants` mutated as a side effect | low | mitigate | `run_case` in `scripts/calibrate_penalties.py` saves and restores each swept constant in a `finally` block (confirmed at line 48); script not imported by production code or tests | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on (high) count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|--------------|------|
| AR-04-01 | T-04-04 (plan 02) | Fabricated numeric content in LLM-authored insight text is structurally impossible to fully rule out for any generative provider; the existing provider-agnostic grounding guard (D-06) already rejects ungrounded numeric tokens before they reach the user, so residual risk is limited to non-numeric mischaracterization, judged low-severity and acceptable without further mitigation this phase | /gsd-verify-work UAT session | 2026-07-15 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|----------------|--------|------|--------|
| 2026-07-15 | 11 | 11 | 0 | /gsd-secure-phase orchestrator (L1 grep-depth, short-circuit per ASVS-1 + plan-time register) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-15
