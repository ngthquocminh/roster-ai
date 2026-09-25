# Testing

## Required live conversation acceptance — Story 5.7

**AI conversational readiness requires live evidence.** Deterministic tests cannot establish that natural conversations work. Story 5.7's suite is the acceptance evidence; its verdict feeds Gate B as `live_conversation_journeys`.

### Run it

```bash
cd backend
uv run python -m evals.live_conversations.suite \
  --agent-model 'openrouter:openai/gpt-5.6-luna' \
  --judge-model 'openrouter:google/gemini-2.5-flash' \
  --reasoning-effort low --repetitions 3 \
  --spend-limit-usd <approved ceiling> --prior-spend-usd <real OpenRouter usage> \
  --output ../_bmad-output/test-artifacts/live-matrix.json

uv run python -m evals.live_conversations.evidence \
  ../_bmad-output/test-artifacts/live-matrix.json --accept-finding B:5
```

The suite is opt-in and paid: it is never selected by `pytest`. It builds the API and web images once, then each execution brings up and tears down its own Compose stack (Postgres, API, worker, web) and drives the authenticated HTTP conversation path — no doubles, no stubs. Scenario B runs the real CP-SAT solver and a real approval. Keys come from `backend/.env`; nothing is printed.

`--accept-finding SCENARIO:TURN` is given once per turn the owner has accepted (below); the example is the turn the recorded matrix accepted. Give none when nothing was accepted.

The measured configuration -- reasoning effort, the per-token prices that drive the spend limiter, and the request, tool-call, token and deadline limits -- is the tracked `backend/evals/live_conversations/compose.override.yml`, which `--override-file` defaults to. Every run report records the models, their endpoint identity (no credential), the reasoning effort and that file's sha256, plus the content id of the API and web images it ran; the evidence binds them as `measured_configuration` and `version_bindings.image`. Update the price rates in that file whenever `--agent-model` changes, or every cost figure is wrong.

### Gate the result against the committed baseline

The suite above answers *how good is it right now*. `backend/evals/baselines/live-conversations.json` records what known-good looked like -- the per-turn `{executed, passed}` counts of the Story 5.7 measurement (87/90), its models, effort and behavioural configuration digest. It is a projection of that one measurement, derived by `backend/scripts/derive_live_conversation_baseline.py` and never hand-typed, and it is deliberately tracked config rather than evidence, so it does not live under `evidence/`.

After a paid run, compare the evidence document it produced against that baseline:

```bash
cd backend
uv run --frozen python scripts/live_conversation_drop_check.py   --report ../evidence/story-5.7/live-conversation-journeys.json
```

Pass the *evidence* document (what `evals.live_conversations.evidence` writes), not the raw `live-matrix.json` run report -- only the former carries `turn_pass_rates`.

The path above is illustrative, not a working example to copy-paste as-is: the committed Story 5.7 evidence predates `behavioral_digest` and can never gain one, so running the command verbatim against it always exits 1 with a `configuration_match` refusal. Point `--report` at the evidence document *your own* paid run just produced.

The check exits non-zero on any of:

- **Tier 1** -- a turn the baseline recorded at full marks now passes zero executions, named. Turns the baseline never scored full (`B:5`, `B:8`, `C:3` at 2/3) are exempt from this tier and watched by Tier 3 instead.
- **Tier 2** -- any never-accept occurrence, on a single instance: a wrong value, unit, entity or version, a missing or unauthorized effect, or a false success claim.
- **Tier 3** -- fewer than 83 of 90 turns passed.
- **Structural** -- `clean_scenarios` no longer contains `A`, `B` and `C`.
- **Refusal** -- the run's `behavioral_digest` differs from the baseline's, or either side was truncated (`blocking_reasons`, `complete_repetitions`, `runs[].complete`). A refusal is reported as a distinct outcome from a failure and never yields a tier verdict.

Each verdict is reported separately in the Gate A readiness status vocabulary (`passed` / `failed` / `skipped` / `missing`), so a future Gate B assessment consumes them as rows. It is operator-invoked on the machine that ran the paid suite: the live suite may never run in `ci.yml` (NFR26/AD-16), so no workflow job, secret or cron entry exists for it. The half that needs no credential -- that the committed baseline still matches the committed Story 5.7 evidence -- runs in the default `pytest` suite on every CI run (`backend/tests/test_live_conversation_drop_check.py`). Re-derive the baseline whenever that evidence is regenerated.

`--resume <report.json>` continues an interrupted report (refused unless it names the same commit, configuration and image ids; pair it with `--skip-image-build`), `--execution-retries` retries one execution that ends on an infrastructure fault, and `--skip-image-build` reuses images already built from the same code (recorded in the report). Evidence generation refuses a set of reports of which none built its images, so a first run must build; only a resume of a report that did may skip the build.

### What it covers

- Three authored conversations: **A** introduction, typo and memory (6 turns); **B** draft → real solver run → approval → baseline (12); **C** tool tour (12). 30 user turns per repetition, generated live from fresh state, with a verdict on every turn.
- The inventory is 135 operations, derived from the installed capabilities. 37 are live-required: every one is exercised live, or carries a named reason a planner turn cannot reach it plus the test that proves it instead (10 do, e.g. draft groups the resolver rejects). The other 98 — query keys, paging, invalid-query paths, manifest error codes and the compute-risk run tool the registry withholds from chat — are deterministic-only. Neither set may vanish from the denominator, and a known product gap (the demonstration approval branch, Story 5.7 Decision 1) is stated as one.
- Two independent layers per turn: fact/effect checks read the application and fixture directly, and a separately configured LLM judge scores relevance, continuity, completeness and clarification/refusal. A judge pass can never override a fact or effect failure.

### Measured results

Recorded matrix (the one the committed evidence file describes; refreshed with it), `openai/gpt-5.6-luna` + `google/gemini-2.5-flash`, images rebuilt, 9 executions:

| | Result |
|---|---|
| Turns passed | **87 / 90** |
| Clean executions | **6 / 9** (three complete repetitions; every scenario clean at least once) |
| Clean run per scenario | A ✅ B ✅ C ✅ |
| False claims, wrong facts, missing effects | **none** |
| Tracked spend | USD 0.58 |

Run `64ca2862-a81c-45f7-adcb-56586f62d57f`, measured on a clean tree at `437b63a`, the code commit the evidence binds (the run started at `db0a5dd`, a docs-only commit; no code file differs between the two, which `evidence.generate` checks and records as `measured_at_commit`).

Accepted findings (recorded, not hidden), each passed 2 of 3 and none involved a false claim: **B:5** and **C:3** were an agent turn that ended without an answer (`unsuccessful_agent_turn`: an invalid output and a run-budget exhaustion), and **B:8** was a completed answer (feasible candidate, 76 assignments) that the judge scored 1 for completeness. Roughly 1 turn in 30 fails in this matrix, spread across different turns rather than a fixed set of broken ones. `evidence/story-5.7/live-conversation-journeys.json` carries the per-turn pass rates, the accepted findings' per-execution failure reasons, the verdict, and the sha256 of the source report.

Earlier attempts of the same measurement session, not counted in the evidence (a report's images must match, and each rebuild produced new image ids): two stopped at the image build because Docker was not running (no execution, no spend), and run `33821ef3-03c9-4bf4-9fc9-ec5ca8355c4a` crashed on a Windows `PermissionError` while saving its ninth execution, after 8 executions and 2 turns of the ninth (USD 0.53). Its turn failures were B:5, C:8, C:9 (`unsuccessful_agent_turn`, C:8 and C:9 also `required_persisted_draft_missing`) and A:4 in repetition 2, an `unsupported_claim`: the reply was cut to "This scenario has " because its `worker_count` claim carried no evidence (`missing_evidence`, no value), so no wrong figure was shown. The owner accepted evidence from the complete run only, with this disclosure.

A stricter cross-check with `google/gemini-2.5-pro` as judge (~5x the judging cost) found real defects the cheaper judge passed, including a per-task figure presented as a scenario-wide total (since fixed, with a regression test). Use it when hunting defects; the cheaper judge runs the recorded matrix.

### What blocks

A wrong value, unit, entity or version, a missing or unauthorized effect, or a false success claim blocks regardless of pass rates and can never be accepted. A turn that fails without one of those may be recorded as a finding **only when the owner accepts that exact turn**, and its pass rate is published either way. Missing, skipped, partial or stale evidence blocks; no release exception can mark this obligation passed.

ShiftMind has two independent test suites: `pytest` for the Python backend
(`backend/`) and `vitest` for the React/TypeScript frontend (`frontend/`).
Neither suite makes live network calls by default — the backend drives all
LLM-dependent tests through a stub `LLMProvider`, and the frontend mocks the
API client at the module boundary. A small number of backend tests are tagged
`@pytest.mark.live` and exercise a real LLM provider; they are excluded from
the default run and require a real API key.


### Trace export during a live run (Story 5.9)

With `LOGFIRE_TOKEN` (and `LOGFIRE_BASE_URL` for an EU project) in `backend/.env`, `suite.py` passes both into the disposable stack and its API and worker export traces to Logfire. The stack's override sets the one diagnostic content mode, so those traces carry prompts, completions and tool arguments/results, tagged `deployment.environment=live-eval`; credentials and exception text are still withheld. The token never enters a run report or `measured_configuration`, and the content-mode key is excluded from `behavioral_digest`, so the drop check still compares with the committed baseline.

### Publish a finished live run to Logfire (Story 5.10)

```bash
cd backend
uv run python -m evals.live_conversations.logfire_publish ../_bmad-output/test-artifacts/<run>.json
```

The input is the **raw run report** `suite.py --output` wrote, never the `evidence/story-5.7/…` document (it has no conversation IDs). It needs `LOGFIRE_TOKEN` (and `LOGFIRE_BASE_URL` for an EU project) in `backend/.env`. It writes:

- one `live_eval.verdict` span per turn of every attempt, **inside that conversation's trace** (trace ID = the conversation UUID). The span is stamped at publication time; the turn's own time is the `shiftmind.live_eval.occurred_at` attribute. (Logfire answered 200 but silently dropped spans backdated six days, measured 2026-09-25.) It carries the turn index, verdict, agent model, `configuration_digest`, the report's `run_id` and sha256, and join keys (`shiftmind.agent_run.id`, scenario, repetition, attempt, `final_attempt`, run status, failure codes). No text;
- one **experiment** under dataset `live-conversations`, named `{model} {run_id}`, one case per final-attempt turn (`A:1:rep1`, …). The case shows the user message and obligation (`inputs`), the visible reply (`output.reply`), the recorded verdict, the judge's score **and reason** per dimension, and token/cost metrics. Nothing is re-executed: the task returns the recording.

Exit codes: **0** published; **1** `logfire_export_failed` (unreachable, slow or rejecting Logfire — decided by what the export really delivered, never by `force_flush()`); **2** a refusal: `configuration_invalid`, `logfire_token_absent`, `report_unreadable`, `report_schema_unsupported`, `report_unfinished`, `report_malformed`, `report_contains_credential`, `report_nothing_to_publish` (every execution ended without a conversation — nothing to export), `publisher_internal_error` (an unexpected exception while writing spans or running the experiment). One JSON line on stdout says which.

`--verdicts-only` writes the verdict spans without the experiment, for a report whose experiment is already published.

**Publish each report once.** There is no idempotency key and the publisher never reads Logfire back, so a second publication duplicates the verdict spans and adds a second experiment of the same name; a failed publication may have left a partial one.

What leaves (addendum §6, channel 2): only those four text fields plus identifiers, closed-vocabulary values and numbers, through the same export-boundary sanitizer as the API and worker, with every resource tagged `deployment.environment=live-eval`. What never leaves: `verified` facts, tool and command observations, fixture setup, usage correlation (`actor_id`), judge usage, failure-reason strings, the raw activity, the host/OS/paths the Logfire SDK's own exporter would send (it is off), and any configured credential (an exact-value match refuses the whole report). The report, the baseline, the drop check and `evidence/**` are never written.

Tests: `tests/test_live_eval_publication.py` (publisher subprocess against a local OTLP server), the `live_eval`/`evals` policy units in `tests/test_trace_export_boundary.py`, and the one-file/dev-pin guards in `tests/architecture/test_trace_export_boundaries.py`.

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

### Trace export proof suites (Story 5.9)

The default suite is keyless for trace export (`conftest.py` pops `LOGFIRE_TOKEN`). The proofs capture what the real `OTLPSpanExporter` posts through a test `requests.Session` (`tests/trace_capture.py`) and decode the OTLP payload:

- `tests/test_trace_export_boundary.py`: the allow-list policy, sanitizer, sampler and propagator.
- `tests/test_content_minimization.py`: channels C4-C8, exported agent, HTTP server, HTTP client, database and worker spans, against Story 5.2's fixtures.
- `tests/test_trace_request_path.py` (`postgres`): one conversation is one trace; runs join by ID.
- `tests/test_trace_export_failure_independence.py`: an unreachable, slow or rejecting Logfire changes no outcome and blocks nothing.
- `tests/architecture/test_trace_export_boundaries.py`: one export boundary, no `logfire`, the content-mode config guard, placeholder-only SQL; since Story 5.10, `logfire`/`pydantic_evals` in the publisher only and pinned exactly in the dev group.
- `tests/test_live_eval_publication.py`: the Story 5.10 publisher (see *Publish a finished live run to Logfire*).

`addopts` disables Logfire's two pytest plugins (`-p no:logfire -p no:pytest_logfire`): one would configure Logfire itself, unsanitized, if `CI` and a token were ever both set.

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

This corpus is a **scripted conformance suite**, not a regression dataset over
model quality: its model output is authored per case, so it proves what the
application does with a given model turn — tool contracts, refusals, grounding,
evidence and visible state — and it cannot prove model routing quality, because
a case never disagrees with its own authored output. That question belongs to
the live counterpart above, gated against `backend/evals/baselines/
live-conversations.json`.

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
