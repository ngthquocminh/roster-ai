---
phase: 260713-stq
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - backend/settings.py
autonomous: true
requirements: [OPENROUTER-PROVIDER]
user_setup:
  - service: openrouter
    why: "The live-gated OpenRouter tests hit the real API. The user has already added OPENROUTER_API_KEY to backend/.env — no code touches .env."
    env_vars:
      - name: OPENROUTER_API_KEY
        source: "OpenRouter Dashboard -> Keys (https://openrouter.ai/keys) — ALREADY SET by user in backend/.env; do not modify"

must_haves:
  truths:
    - "settings._OPENROUTER_DEFAULT_MODEL == 'openai/gpt-oss-20b:free' (the live-verified tool-capable slug), so default_settings().openrouter_model defaults to it when OPENROUTER_MODEL is unset"
    - "The keyless-default-CI invariant is UNCHANGED — default_settings().llm_provider is still 'stub' when LLM_PROVIDER is unset"
    - "The full non-live suite (cd backend && uv run pytest -q) stays green: same passed count as before, 0 failures"
    - "Both @pytest.mark.live OpenRouter tests pass against the user's real key using the new default model (no more upstream 429 from the old meta-llama slug)"
  artifacts:
    - "backend/settings.py (updated _OPENROUTER_DEFAULT_MODEL constant + comment)"
    - ".planning/quick/260713-stq-swap-openrouter-default-model-to-openai-/260713-stq-SUMMARY.md (with live test output)"
  key_links:
    - "settings._OPENROUTER_DEFAULT_MODEL -> Settings.openrouter_model default -> default_settings() (fallback when OPENROUTER_MODEL env unset) -> OpenRouterLLMProvider(model=...) -> real OpenRouter chat.completions call"
---

<objective>
Swap the OpenRouter default model slug from `meta-llama/llama-3.3-70b-instruct:free` to `openai/gpt-oss-20b:free`. The old default is still listed as tool-capable but is CURRENTLY returning 429 rate-limit errors upstream (its backing provider is congested), which fails both live OpenRouter tests. `openai/gpt-oss-20b:free` was probed against the live OpenRouter API and confirmed to answer both a plain chat completion and a tool-calling request with the exact `set_min_workers_per_task` schema shape.

This is a single-line constant change plus verification against the user's real key — the user's direct ask was "test if the key works, make sure all testcases pass."

Purpose: Restore green live OpenRouter tests without touching any provider logic, translation seam, or the stub keyless-CI default.
Output: Updated `_OPENROUTER_DEFAULT_MODEL` constant + comment in `backend/settings.py`, a passing non-live suite, two passing live tests, and a SUMMARY documenting the live results and the new verified slug.
</objective>

<execution_context>
@$HOME/.claude/gsd-core/workflows/execute-plan.md
@$HOME/.claude/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@backend/settings.py
@backend/llm/openrouter.py
@backend/tests/test_openrouter_provider.py

# Prior quick task that introduced OpenRouter support and picked the original default:
@.planning/quick/260713-pn3-add-openroute-as-default-provider-gemini/260713-pn3-SUMMARY.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Swap the OpenRouter default model constant to openai/gpt-oss-20b:free</name>
  <files>backend/settings.py</files>
  <action>
Change the module-level constant `_OPENROUTER_DEFAULT_MODEL` (currently at line 26) from `"meta-llama/llama-3.3-70b-instruct:free"` to `"openai/gpt-oss-20b:free"`.

Add a concise one-line comment directly above the constant explaining the swap: that this slug is live-verified tool-capable as of 2026-07-13, and it replaced the prior `meta-llama/llama-3.3-70b-instruct:free` default which began returning upstream 429 rate-limit errors. Keep it to one line — do not add a paragraph.

Do NOT change anything else in this file. In particular, leave the `Settings.openrouter_model` field wiring, the `default_settings()` `OPENROUTER_MODEL` env fallback (which reads this same constant), and the `LLM_PROVIDER` "stub" default all exactly as they are. The keyless-default-CI invariant must remain intact.

No other files reference the old slug — a repo grep confirmed `meta-llama/llama-3.3-70b-instruct:free` appears only at settings.py:26. The test module (`backend/tests/test_openrouter_provider.py`) and `backend/llm/openrouter.py` use `default_settings()` (which will pick up the new default automatically) or placeholder/fake model strings unrelated to the real default — do NOT edit them.
  </action>
  <verify>
    <automated>cd backend && grep -c 'openai/gpt-oss-20b:free' settings.py</automated>
  </verify>
  <done>settings.py contains `_OPENROUTER_DEFAULT_MODEL = "openai/gpt-oss-20b:free"` with an updated one-line comment; no remaining reference to the old `meta-llama/llama-3.3-70b-instruct:free` slug anywhere in backend/; no other lines changed.</done>
</task>

<task type="auto">
  <name>Task 2: Run non-live suite + live OpenRouter tests and record results in SUMMARY</name>
  <files>.planning/quick/260713-stq-swap-openrouter-default-model-to-openai-/260713-stq-SUMMARY.md</files>
  <action>
Run the two verification commands below from the repo, capturing actual output.

1. Non-live suite (must stay fully green, 0 failures):
   `cd backend && uv run pytest -q`
   Record the exact passed/failed/skipped counts. This is the regression gate — a green run here proves the constant swap did not break the keyless-CI default or any fake-client test.

2. Live-gated OpenRouter tests against the user's real key (both must pass):
   `cd backend && uv run pytest tests/test_openrouter_provider.py -m live -q`
   These two tests (`test_openrouter_parse_constraints_matches_stub_parity` and `test_openrouter_generate_insights_passes_grounding_guard`) call the real OpenRouter API using the new default model. They are the direct answer to the user's "test if the key works" ask. The `-m live` flag overrides the default `-m "not live"` addopts so the gated tests actually run; they skip (rather than fail) if OPENROUTER_API_KEY is absent, so a "2 skipped" result means the key did NOT load from backend/.env — investigate and report that rather than claiming success.

If a live test still fails for a reason unrelated to the model choice (a genuine bug, a schema/grounding-guard mismatch, an auth error), do NOT silently work around it: report the exact failing assertion and traceback in the SUMMARY and stop. Only a rate-limit/model-availability failure is what this change targets.

Then write the SUMMARY.md for this quick task following @$HOME/.claude/gsd-core/templates/summary.md. It MUST include:
- The new verified-live model slug (`openai/gpt-oss-20b:free`) and why the old one was swapped (upstream 429).
- The non-live suite result (actual passed/skipped counts).
- The live test result: both live test names and pass/fail with the actual pytest output line.
- key-files.modified: backend/settings.py.
- requirements-completed: [OPENROUTER-PROVIDER].
  </action>
  <verify>
    <automated>cd backend && uv run pytest -q && uv run pytest tests/test_openrouter_provider.py -m live -q</automated>
  </verify>
  <done>Non-live suite passes with 0 failures; both live OpenRouter tests pass against the real key; SUMMARY.md exists with the new slug, the swap rationale, and the actual non-live + live pytest output recorded.</done>
</task>

</tasks>

<verification>
- `grep -c 'openai/gpt-oss-20b:free' backend/settings.py` returns 1; the old slug returns 0 across backend/.
- `cd backend && uv run pytest -q` → 0 failures (same passed count as before this change; the live tests are excluded by the default `-m "not live"` addopts).
- `cd backend && uv run pytest tests/test_openrouter_provider.py -m live -q` → 2 passed (not 2 skipped — skipped means the key did not load).
- The `LLM_PROVIDER` "stub" default and the `default_settings()` env-fallback wiring are unchanged.
</verification>

<success_criteria>
- `_OPENROUTER_DEFAULT_MODEL == "openai/gpt-oss-20b:free"` with a concise explanatory comment.
- Full non-live pytest suite green (0 failures).
- Both `@pytest.mark.live` OpenRouter tests pass against the user's real OPENROUTER_API_KEY.
- SUMMARY.md records the new verified slug, the swap rationale, and actual non-live + live test output.
- No changes outside `backend/settings.py` (source) and the SUMMARY.
</success_criteria>

<output>
Create `.planning/quick/260713-stq-swap-openrouter-default-model-to-openai-/260713-stq-SUMMARY.md` when done.
</output>
