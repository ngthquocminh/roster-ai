# Phase 4: Real LLM Provider (free-tier first) + Penalty Calibration - Context

**Gathered:** 2026-07-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Drop the **first real, network-backed LLM provider** into the existing
`LLMProvider` seam (the `create_provider()` factory currently registers only
`"stub"`), driven by config; **empirically calibrate** the four soft-override
penalty weights against the committed full-week fixture (ENG-04); and add **one
live integration test** that stays out of the default CI run (TEST-04). Default
CI remains stub-only and needs no API key.

**Pivot from the roadmap title (locked this discussion):** the phase was scoped
as "Real *Claude* Provider," but there is **no free Claude API tier**. Per the
user's direction ("use a free API first"), the first real provider is **Google
Gemini (free tier)**. Because the seam is provider-neutral, Claude remains a
trivial future swap — design.md's "Claude now; Gemini later" simply becomes
"Gemini first, Claude/others later." Requirements LLM-02 / TEST-04 and the
ROADMAP phase title reference Claude specifically and will need light,
provider-generic re-wording (flagged for the planner; see canonical_refs).

**One real provider only.** A multi-provider **fallback gateway** (rotate to
another free API on rate-limit) and **per-customer free-trial quota** are the
user's stated production vision but are explicitly **deferred** (see Deferred
Ideas) — they compose behind this same seam, so nothing built here is throwaway.

</domain>

<decisions>
## Implementation Decisions

### Provider transport (the user's headline question)
- **D-01:** First real provider = **Google Gemini via the Google AI Studio
  free-tier API key**. Registered in `create_provider()` under a new name
  (e.g. `"gemini"`) alongside `"stub"`. Chosen over Anthropic-direct (no free
  tier) and AWS Bedrock (pulls Phase-5 deploy/IAM concerns forward; deferred).
- **D-02:** Gemini's **native function calling** drives `parse_constraints`;
  its text generation drives `generate_insights`. The vendor's function-call
  payload is translated to provider-neutral `list[OverrideCall]` **at the seam**
  — no vendor payload crosses `LLMProvider` (upholds Phase 1 D-08/D-09).
- **D-03:** SDK = the current Google GenAI Python SDK (**`google-genai`**).
  Researcher must confirm the exact current SDK package + function-calling API
  and the current model id via **Context7** before the planner commits syntax.

### Selection, auth, config
- **D-04:** `get_llm_provider` (currently hardcodes `"stub"`) becomes
  **env-driven** — e.g. `LLM_PROVIDER` with default `"stub"` so CI stays
  keyless. Extend the `Settings` dataclass (currently filesystem-only) with the
  provider name, model id, and API key (read fresh per call, matching the
  existing env-override pattern).
- **D-05:** **Replace the stale default model** `claude-sonnet-4-6` (matches no
  current model) with a **current Gemini model** as the default (a fast/cheap
  Flash-tier model is fine for tool-use parsing + short insights). Exact id →
  researcher confirms. The setting name should read provider-generically rather
  than `ANTHROPIC_MODEL` (e.g. `LLM_MODEL` or `GEMINI_MODEL`).

### "Wire-format parity" — reframed (criterion 3 / TEST-04)
- **D-06:** Parity no longer means "byte-parity with Claude `tool_use`." It means
  **the live Gemini provider's parse path yields the same `OverrideCall` results
  as the stub for the same input text.** The neutral `OverrideCall` output is the
  contract, not the vendor payload shape.
- **D-07 (open for planner/researcher):** The Phase-1 `StubLLMProvider` currently
  emits a **Claude-shaped** `tool_use` payload. Decide whether to (a) re-point the
  stub to Gemini's function-call shape so the *same* translation function is
  exercised by both stub and live provider (strongest parity signal), or (b) keep
  the stub Claude-shaped and give Gemini its own adapter. Preference: whatever
  makes stub and live share one parse/translation path. Not locked here — it is an
  implementation-path call for the planner.

### Penalty calibration (ENG-04)
- **D-08:** Calibrate the four weights (`MIN_WORKERS_PENALTY`,
  `LOCK_SHIFT_PENALTY`, `EXCLUDE_WORKER_PENALTY`, `MAX_HOURS_PENALTY`, all
  currently `100_000`/`50_000` placeholders) against the **committed full-week
  fixture** via a small **calibration harness/script** that sweeps weights, plus
  **a couple of regression-test assertions** encoding the pass/fail signal:
  a **satisfiable** override is honored; an **unsatisfiable** one degrades
  gracefully to baseline coverage (respected, not dominating the round-2 cost
  objective). Calibration uses the **real engine + stub LLM** → no API key → stays
  in CI.

### Live integration test (TEST-04)
- **D-09:** Mark the single live test `@pytest.mark.live`, **excluded from the
  default run** (`-m "not live"`), and **env-gated** to skip when the Gemini API
  key is absent. It exercises the same parse path as the stub and asserts the
  D-06 reframed parity. Only a developer with a key set runs it.

### Folded Todos
- **WR-05 — Add real-engine test for ENG-05 degeneracy detection** (testing):
  folded. It exercises the **real engine against the full-week fixture** — the
  same surface the calibration harness (D-08) sets up — so it is a natural fit
  here rather than a separate effort.

### Claude's Discretion
- Exact calibration weight values and the sweep/search strategy (D-08).
- The precise env var names (`LLM_PROVIDER` / `LLM_MODEL` vs `GEMINI_*`) and
  `Settings` field shapes (D-04/D-05), within the "default stub, keyless CI" rule.
- D-07 stub-shape decision (Gemini-shaped stub vs separate adapter).
- Insight prose wording (already bounded by Phase-3 D-03/D-04 + the D-06 guard).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements / roadmap (this phase)
- `.planning/REQUIREMENTS.md` — **LLM-02, ENG-04, TEST-04** (Phase-4 IDs).
  ⚠ LLM-02 text says "A *Claude* implementation … `ANTHROPIC_MODEL`" and TEST-04
  says "live-*Claude*" — both need provider-generic re-wording per D-01. Planner
  should reconcile (or flag a `/gsd-phase` edit) so docs match the Gemini-first
  decision.
- `.planning/ROADMAP.md` §"Phase 4" — goal + 3 success criteria. Phase **title**
  and criteria 1/3 name Claude/`ANTHROPIC_MODEL`/`tool_use`; read alongside D-01,
  D-05, D-06 which supersede the vendor-specific wording.

### Project design source-of-truth
- `docs/design.md` — engineering design of record; the `LLMProvider` Protocol
  seam and "Claude now; Gemini later" (now Gemini-first). §"LLM providers".
- `docs/PLAN.md` — hand-written phase tracker this milestone formalizes.

### Prior-phase decisions this phase builds on
- `.planning/phases/01-first-nl-constraint-end-to-end/01-CONTEXT.md` — provider
  seam design **D-08/D-09** (provider-neutral Protocol; no vendor payload crosses
  the boundary) — the rule D-02 upholds.
- `.planning/phases/03-on-demand-insight-reports/03-CONTEXT.md` — **D-06 numeric
  grounding guard** (provider-agnostic; now also guards Gemini insights) and the
  `generate_insights(summary: dict) -> str` contract.

### Live code seams this phase touches
- `backend/llm/base.py` — `LLMProvider` Protocol + `create_provider()` factory;
  **add the `"gemini"` branch** here.
- `backend/llm/stub.py` — `StubLLMProvider`; subject of the D-07 wire-shape call.
- `backend/api/deps.py` — `get_llm_provider` (hardcodes `"stub"`); make env-driven.
- `backend/settings.py` — `Settings` dataclass (filesystem-only today); extend
  with provider/model/key per D-04/D-05.
- `backend/config/constants.py` — the four penalty constants to calibrate (D-08);
  each already carries a "calibration deferred to Phase 4 (ENG-04)" note.
- `backend/engine/cpsat/builder.py` (`round2_cost` assembly, ~L406) and
  `backend/engine/cpsat/objective.py` (lexicographic round-1→round-2 solve) — the
  mechanism calibration tunes.
- `backend/tests/test_api.py` — `app.dependency_overrides` + stub pattern; template
  for the calibration regression tests and the gated live test.
- committed full-week fixture (calibration + WR-05 target) — under `data/`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `create_provider(name)` factory + `get_llm_provider` dependency
  (`llm/base.py`, `api/deps.py`): the exact swap point — add `"gemini"`, flip
  the default selection to env-driven. Service/route code is untouched
  (criterion 1: "the seam holds").
- `StubLLMProvider` (`llm/stub.py`): the deterministic parse/insight contract the
  Gemini provider must match; also the parity reference for D-06.
- D-06 grounding guard (Phase 3, in the insight service): provider-agnostic —
  protects Gemini-generated insights with no change.
- `Settings` dataclass (`settings.py`): frozen, read fresh per call from env —
  extend with provider/model/key following the existing pattern.
- Committed full-week fixture: the calibration target and the real-engine test
  input for folded WR-05.

### Established Patterns
- **Provider-neutral Protocol seam** — nothing vendor-specific crosses
  `LLMProvider`; the Gemini adapter translates function-call payload →
  `list[OverrideCall]` internally.
- **Soft round-2 penalties only** — overrides are additive terms in `round2_cost`
  (never round-1, never hard); calibration tunes magnitudes, not the mechanism.
- **Per-request fresh settings + DI** for swappable seams (`get_llm_provider`).
- **Stub-only CI** — default test run must stay green with no API key.

### Integration Points
- New `"gemini"` branch in `create_provider()`; env-driven default in
  `get_llm_provider`.
- New `Settings` fields consumed at provider construction.
- Calibration harness/regression tests wire the real CP-SAT engine + stub LLM
  against the full-week fixture.
- Live test gated by `@pytest.mark.live` + key-presence skip.

</code_context>

<specifics>
## Specific Ideas

- "Use a free API first" — no free Claude tier exists, so Gemini free tier is the
  concrete first real provider; Claude stays a drop-in for later.
- The long-term production vision is a **gateway that rotates across free APIs on
  rate-limit**, with a **customer free-trial** on limited free access. Captured as
  deferred (below) — not built in Phase 4.
- Researcher must use **Context7** to confirm the current `google-genai` SDK
  function-calling API and current Gemini model id (per the user's standing rule
  to fetch live docs for libraries/APIs).

</specifics>

<deferred>
## Deferred Ideas

- **Provider fallback gateway** — a composite `FallbackProvider([...])` behind the
  same `LLMProvider` seam that rotates to another free provider on rate-limit
  (HTTP 429). Bounded engineering, **next phase**. Build options to evaluate then:
  a hand-rolled `FallbackProvider` (no new dep), **LiteLLM** (open-source gateway,
  fallback chains + unified interface, self-hostable), or **OpenRouter** (hosted).
- **Per-customer free-trial + quota management** — customers/tenants, auth,
  per-customer key or usage metering. None of this exists in the codebase; the
  milestone is scoped "API + engine only." **Future milestone.**
- **AWS Bedrock transport** for Claude — same Anthropic Messages/`tool_use` format
  via the `anthropic` SDK's Bedrock client; add when AWS deploy lands (Phase 5).
- **Anthropic-direct Claude provider** — trivial future `create_provider("claude")`
  branch once a paid key is in play.

### Reviewed Todos (not folded)
- **WR-04 — Harden scenario fixture path against traversal** (api/security):
  reviewed; **not folded**. High keyword match but unrelated to provider/
  calibration work — better as a standalone quick fix (e.g. `/gsd-quick`).

</deferred>

---

*Phase: 4-Real LLM Provider (free-tier first) + Penalty Calibration*
*Context gathered: 2026-07-06*
