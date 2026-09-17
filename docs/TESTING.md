<!-- generated-by: gsd-doc-writer -->
# Testing

## Required live conversation acceptance — Story 5.7

**AI conversational readiness requires live evidence.** Passing deterministic tests or Story 5.6's six two-user-turn cases does not establish that natural conversations work. Story 5.7 is in progress, not passed; the commands below for existing suites do not run its required suite.

The [Story 5.7 contract](../_bmad-output/implementation-artifacts/5-7-prove-live-conversations-through-baseline-promotion.md) and [scenario catalogue](../_bmad-output/implementation-artifacts/live-conversation-scenarios-5-7.md) require:

- Reproduce `HI my name is Minh` → `how can you help me?` → `how many work are therre?` using the configured real provider through the actual chat path.
- Three authored conversations (right-sized 2026-09-17): A introduction/clarification (6 user turns), B draft → real solver → approval → baseline (12), and C tool tour (12). That is 30 user turns per full run. Each runs from fresh state with a verdict on every turn, and scheduling turns need at most two tool calls. Generate all replies and history live.
- Inventory every installed tool and supported operation, including `shiftmind_demonstration`; show attempted calls, successful results, and verified effects separately. Disabled or unreachable required coverage is a gap, not a pass. Application commands do not count as LLM tool calls.
- Prove persisted draft creation/revision, explicit optimization, actual worker/solver candidate, comparison, agent-proposed approval, authenticated approval, and the exact baseline change. Use isolated test state.
- Run against real application persistence and services. Score useful answers, exact grounded facts, and durable effects, not just a valid response envelope.
- Require one clean run of each scenario on the same code/configuration/dataset, then three repetitions reporting per-turn pass rates. A false claim or wrong fact/effect in any counted run fails. A model-reliability failure with no false claim may be recorded as a finding only with explicit owner acceptance. Preserve every first-attempt failure and retry. Missing, skipped, partial, failed, or stale required evidence blocks completion and Gate B; no exception can mark this obligation passed.
- Enforce explicit finite budgets and version-bound evidence. Retain only sanitized authored-test planner-visible transcripts and safe outcomes in dedicated test artifacts; no credentials, hidden reasoning, raw provider payloads, unrelated conversations, or production telemetry content.

Implementation must add the runnable command and wire the required `live_conversation_journeys` Gate B verdict. Until then this requirement is **unproven**. Existing live `authoritative: false` fields distinguish provider observations from deterministic invariant proof; they do not make live conversation failures optional. Deterministic tests remain regression safeguards and cannot substitute for this acceptance evidence.

**Answer scoring:** Story 5.7 requires independent checks of actual data, units, tool results and saved effects, plus a separately configured LLM-as-judge for relevance, continuity, completeness and clarification/refusal. The judge receives prior conversation and verified facts, not future messages. Its 0–2 rubric requires 2 on every applicable dimension for automatic pass; uncertain grades require recorded human review. Wrong facts/effects always fail, regardless of judge scores. Record every judge/fact disagreement and false pass, and review every failing or uncertain turn before counting a run. See the story's “How answers are judged” section for the complete protocol.

ShiftMind has two independent test suites: `pytest` for the Python backend
(`backend/`) and `vitest` for the React/TypeScript frontend (`frontend/`).
Neither suite makes live network calls by default — the backend drives all
LLM-dependent tests through a stub `LLMProvider`, and the frontend mocks the
API client at the module boundary. A small number of backend tests are tagged
`@pytest.mark.live` and exercise a real LLM provider; they are excluded from
the default run and require a real API key.

For a deeper walkthrough of test structure, fixtures, and mocking
conventions with more code examples, see
[`.planning/codebase/TESTING.md`](../.planning/codebase/TESTING.md).

## Backend (pytest)

**Runner:** `pytest`, configured in `backend/pyproject.toml`.

Run from the `backend/` directory (or prefix with `uv run` from anywhere):

```bash
cd backend
uv run pytest                 # default suite — stub LLM provider, no network calls
uv run pytest -v              # verbose output
uv run pytest tests/test_api.py            # single file
uv run pytest tests/test_api.py -k health  # single test by name
```

### Live provider tests

Tests marked `@pytest.mark.live` exercise a real LLM provider (Gemini or
OpenRouter) over the network and are excluded by default via
`addopts = "-m \"not live\""` in `backend/pyproject.toml`. Files such as
`tests/test_gemini_provider.py` and `tests/test_openrouter_provider.py` carry
this marker. To run them:

```bash
cd backend
uv run pytest -m live          # requires GEMINI_API_KEY and/or OPENROUTER_API_KEY
```

`backend/conftest.py` surfaces only `GEMINI_API_KEY` / `OPENROUTER_API_KEY`
from a local `backend/.env` so the `live` marker can detect a developer's key.
It deliberately does **not** load `LLM_PROVIDER` / `LLM_MODEL` from `.env`, so
the default (non-`live`) suite always runs against the keyless `stub`
provider regardless of a developer's local configuration.

### Agent evaluation harness (golden datasets, `backend/evals/`)

The chat/agent surface (`backend/agent/`, `backend/application/use_cases/
execute_turn.py`) is evaluated by a SEPARATE, versioned golden-case harness in
`backend/evals/` — distinct from the `LLMProvider`/Gemini/OpenRouter tests
above, which cover the older constraint-parsing seam. Every golden case has a
deterministic execution (a case-driven PydanticAI `FunctionModel` double,
`backend/evals/doubles.py`) that is the **authoritative** safety/correctness
evidence, run in the default suite with no network access:

```bash
cd backend
uv run pytest tests/test_evaluation_harness.py tests/test_execute_turn_use_case.py
```

**Single-turn golden cases** (`backend/evals/golden/**/*.json`, schema in
`evals/cases.py::GoldenCase`) exercise one prompt/response pair per case —
tool routing, grounding, clarification, refusal, and drafts.

**Multi-turn golden cases** (`backend/evals/golden_multi_turn/**/*.json`,
schema in `evals/cases.py::MultiTurnGoldenCase`/`GoldenTurn`, added in Story
5.6) exercise history and tool continuity ACROSS turns through the real
product seam (`execute_turn` / `rehydrate_history`), never a single-turn
shortcut:

- A later turn's `history_mode: "raw_turn"` replays a prior turn's exact owned
  transcript (the same "owned resume transcript" mechanism
  `api/routers/approvals.py` already uses to resume after an approval), so a
  dependent tool call can be proven to use a REAL trusted antecedent — the
  double reads the value out of prior history (`evals/doubles.py`'s
  `HistoryLookupV1` mechanism) rather than replaying a hardcoded literal.
- A later turn's `history_mode: "rehydrated_activities"` exercises the
  ordinary conversational path every other multi-turn request takes, proving
  the `HISTORY_MESSAGE_BOUND` (100-message) window: old activities stay
  durable in the caller's own record but never reach the provider once a
  conversation exceeds the bound.
- Four cases prove the antecedent fails closed on its own: a missing,
  stale (an explicit consistency-check mismatch), unauthorized
  (installed-but-ungranted capability), or truncated (pushed outside the
  100-message window) antecedent must never be guessed, silently retargeted,
  or granted new authority — see `evals/golden_multi_turn/history_and_tools/`.
  Each names WHICH fault fired via `GoldenTurn.expected_failure_reason`
  (`"antecedent_absent"`/`"antecedent_stale"`/…, deterministic-only —
  `evals/doubles.py::AntecedentFaultError.code`), so a case cannot pass
  vacuously on an unrelated harness crash landing on the same generic
  `failed` outcome (code review 2026-09-14).
- The long-history case additionally asserts `expected_history_absent`: a
  substring that must NOT appear in the text this turn actually observes
  after `execute_turn`'s own `HISTORY_MESSAGE_BOUND` truncation. This is
  computed identically for a double OR a real live model (before either is
  ever called), so the 100-message bound is proven through the harness on
  BOTH run sources, not only by a separate unit test.

Both dataset shapes generate an NFR27-bound demonstration report the same way:

```bash
uv run python -c "from pathlib import Path; from evals.report import generate_demonstration_report; generate_demonstration_report(Path('/tmp/report.json'))"
uv run python -c "from pathlib import Path; from evals.report import generate_multi_turn_demonstration_report; generate_multi_turn_demonstration_report(Path('/tmp/multi-turn-report.json'))"
```

**Live counterpart (opt-in, non-authoritative, explicitly budgeted).** Both
single- and multi-turn datasets have a live counterpart that scores the same
cases against the real configured provider (`AGENT_RUNTIME_MODEL` /
`AGENT_RUNTIME_API_KEY`). Neither is selected by the default suite, neither
can ever become authoritative (`run_source="live"` always yields
`EvalVerdict.authoritative is False`), and neither reads a credential or
allows a network call outside its own explicit, scoped
`models.override_allow_model_requests(True)` block:

```bash
uv run pytest -m live tests/test_evaluation_harness.py::test_golden_cases_against_live_agent_are_non_authoritative
uv run pytest -m live tests/test_evaluation_harness.py::test_live_multi_turn_suite_is_bounded_and_non_authoritative
```

A multi-turn live turn is scored under the SAME gate as deterministic
(state must match — via `GoldenTurn.live_expected_visible_state` when a real
provider legitimately diverges — tool routing and results must match; only
free TEXT stays ungated, since a real model's prose never reproduces a
scripted double's exact wording). Code review 2026-09-14: the state gate
used to be skipped entirely on the live path, so a dead or do-nothing
provider could "pass" a turn expecting zero tool calls regardless of
behaviour — live evidence is what runs against the real, shipped provider,
so a live-side gap is treated as more serious than an equivalent
deterministic-only one, not less.

The multi-turn live suite additionally requires an explicit
`evals.report.LiveSuiteBudgetV1` — every one of its six ceilings (case count,
total requests, total tool calls, total tokens, elapsed seconds, spend USD)
is a **required, positive, finite** number; there is no default that lets an
ordinary test call a provider. Cumulative usage/cost is accounted, and every
ceiling re-checked, **after every turn** (not only at a case boundary), so a
ceiling crossed mid-case stops the run before its next turn and a case cut
short is marked `partial` and never counts as passed. `spend_usd_limit` is
enforced only when the caller supplies real per-token pricing
(`input_usd_per_mtok`/`output_usd_per_mtok`); the report's own
`spend_measured` field says whether it actually was, so a `spend_usd_limit`
declared but never measured is visible rather than silently vacuous.
`evals.report.generate_bounded_live_multi_turn_report` is the documented
explicit command that runs this suite and persists a safe, NFR27-bound
report (carrying its own `release_gate_eligible: False`/`release_gate_status`
pair, same as the deterministic report) — its `readiness` field is
`blocked`, `eligible`, or `excepted` (an explicit, validated, time-bounded
`LiveReadinessExceptionV1`, itself rejected at CONSTRUCTION for an
incomplete field or a timezone-naive `expires_at` rather than only lazily at
use time — an incomplete or expired one blocks exactly like having none).
**A live pass is necessary, but never sufficient, to ship**: it cannot
satisfy, weaken, or replace the deterministic report above, and it never
decides the separate Gate B release-gate question.

Diagnostics persisted from a live run (`generate_live_diagnostics`,
`evals.report._safe_diagnostic_record`) carry only ordered tool-call/
tool-result NAMES and COUNTS plus a closed-vocabulary outcome classification
— never a raw prompt, tool argument, tool-result body, or credential. A
write/serialization failure for one case never erases diagnostics already
flushed for earlier cases.

### Where tests live

All backend tests are in `backend/tests/`, named `test_*.py`, separate from
the implementation they exercise (no co-location). Existing files include
`test_api.py`, `test_scenarios_api.py`, `test_constraints_api.py`,
`test_engine_small.py`, `test_llm_provider.py`, `test_gemini_provider.py`,
and `test_openrouter_provider.py`.

### Writing a new backend test

1. Add a new `test_*.py` file in `backend/tests/`, or a new `def test_*()`
   function in an existing file. Open with a module docstring describing
   what the file exercises.
2. For API-level tests, reuse the `client` fixture pattern (see
   `tests/test_scenarios_api.py`): it spins up a `TestClient` with a temp
   SQLite database (`ROSTERAI_DB` pointed at `tmp_path`) and stubs both the
   solver engine and the LLM provider via FastAPI's
   `app.dependency_overrides`:

   ```python
   app.dependency_overrides[get_engine] = lambda: StubEngine()
   app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider()
   ```

3. Only stub what's expensive or non-deterministic — the real CP-SAT solver
   (`StubEngine`) and real LLM calls (`StubLLMProvider`). Let everything else
   run for real: the actual SQLite database (in a temp dir), real fixture
   JSON from `data/`, and real Pydantic validation.
4. If a test needs a real LLM provider (Gemini/OpenRouter), mark it
   `@pytest.mark.live` so it's excluded from the default CI run.
5. Assert the HTTP status code first, then the response body shape.

No coverage tool is configured for the backend.

## Frontend (vitest)

**Runner:** `vitest` (configured via `test` block in `frontend/vite.config.ts`),
with `jsdom` as the DOM environment and `@testing-library/jest-dom` for DOM
matchers.

Run from the `frontend/` directory:

```bash
cd frontend
npm run test              # runs `vitest run` — full suite, single pass
npm run test -- --watch   # watch mode
npm run typecheck         # tsc --noEmit
npm run lint              # oxlint
```

### Where tests live

Frontend tests are co-located with the source file they cover:
`Component.test.tsx` next to `Component.tsx`, `lib.test.ts` next to `lib.ts`.
For example, `src/api/scenarios.test.ts` sits beside `src/api/scenarios.ts`,
and `src/components/editor/ScenarioHeader.test.tsx` sits beside
`ScenarioHeader.tsx`.

### Mocking convention: `vi.mock` boundary mocks, not MSW

This repo's convention is to mock at the module boundary with vitest's
`vi.mock()` — **not** MSW (network-level interception). Mock the `./client`
module (the generated `openapi-fetch` client) at the top of the test file,
before importing it:

```typescript
vi.mock("./client", () => ({
  client: {
    GET: vi.fn(),
    POST: vi.fn(),
  },
}));

import { client } from "./client";
const mockGET = client.GET as unknown as ReturnType<typeof vi.fn>;
const mockPOST = client.POST as unknown as ReturnType<typeof vi.fn>;
```

Reset mocks in a `beforeEach()`:

```typescript
beforeEach(() => {
  mockGET.mockReset();
  mockPOST.mockReset();
});
```

Use `.mockResolvedValueOnce(...)` for a single expected call, or
`.mockImplementation((path) => ...)` when a test drives multiple distinct
endpoints in one case.

### Writing a new frontend test

1. Create `Component.test.tsx` (or `lib.test.ts`) next to the file under
   test. Open with a doc comment describing what's covered and why it's
   mocked the way it is.
2. Mock the API client module boundary (`vi.mock("./client", ...)`), not the
   network layer — do not introduce MSW.
3. For components that route or link, use `createMemoryRouter` from
   `react-router` instead of mocking navigation:

   ```typescript
   const router = createMemoryRouter(
     [{ path: "/scenarios/:scenarioId", Component: () => <ScenarioHeader scenarioQuery={scenarioQuery} /> }],
     { initialEntries: ["/scenarios/abc"] },
   );
   return render(<RouterProvider router={router} />);
   ```

4. Query the DOM with `@testing-library/react`'s `screen.getByRole()` /
   `screen.getByText()` — don't reach into component internals.
5. Group related cases in `describe()` blocks; name `it()` cases after the
   expected behavior (e.g. `"resolves to [] (not null/undefined/throw) when..."`).
6. Do not mock React Query itself, `@testing-library/react`, or plain utility
   functions — only external boundaries (API client, router where relevant).

`src/test/setup.ts` runs before every test file: it imports
`@testing-library/jest-dom` and polyfills a few DOM APIs jsdom lacks
(`hasPointerCapture`, `releasePointerCapture`, `scrollIntoView`) that Radix UI
components need.

No coverage tool is configured for the frontend.

## Cross-cutting principles

- **Isolation:** every test is independent — no shared state between tests.
  Backend tests get a fresh temp SQLite database per test (`tmp_path`);
  frontend mocks are reset in `beforeEach()`.
- **No live network calls by default:** the backend stub LLM provider and
  frontend `vi.mock()` boundary mean the default suites never touch the
  network. Only `pytest -m live` breaks this rule, intentionally, on request.
- **Determinism:** no time-dependent assertions; async completion is polled
  with a timeout rather than relying on fixed sleeps.
