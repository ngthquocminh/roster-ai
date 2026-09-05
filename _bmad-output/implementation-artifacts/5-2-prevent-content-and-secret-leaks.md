---
baseline_commit: c0ef358
---

# Story 5.2: Prevent Content and Secret Leaks

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a security reviewer,
I want logs and any exported traces limited to explicitly safe metadata,
So that diagnosis cannot leak credentials, workforce data, prompts, schedules, tool payloads, or
approval evidence.

**This is the second story of Epic 5's portfolio sequence.** Story 5.1 built the telemetry channel
this story constrains, and its Decision 12 hands 5.2 "a typed record with a closed field set to
assert against, instead of free-form log lines". Story 5.1 deliberately stopped one step short of
minimization: *"it is **not** a content-minimization proof — no allow-list is enforced at an export
boundary, no adversarial or secret fixture is run, and no scrubber exists."* This story is that step.

**The leak is not hypothetical and it is not in the telemetry contract.** `TelemetryRecordV1` is
clean by construction. The leak is in the *other* branch of the same formatter and in the process
that shares its stream — proven empirically at story creation, not inferred:

* `JsonLogFormatter.format` has a fallback branch for ordinary stdlib records that writes
  `record.getMessage()` and `self.formatException(record.exc_info)` verbatim
  (`backend/adapters/telemetry/json_logs.py:29-41`).
* `configure_json_logging` installs that formatter on the **process root logger**
  (`json_logs.py:60-71`), and root's default level is `WARNING` — so every `logger.exception(...)`
  in the repository reaches it. There are five, all on the agent-run path
  (`api/routers/approvals.py:229,278,294`; `api/routers/conversations.py:353,464`).
* No `create_engine` call in the repository passes `hide_parameters=True`, so a SQLAlchemy
  `StatementError`'s own `str()` carries `[SQL: …]` **and `[parameters: (…)]`** — the bound values,
  i.e. workforce rows, conversation text, schedule payloads.
* `backend/worker/main.py::_report_error` (`:59`) prints `{error}` plus a full
  `traceback.print_exception(...)` to stderr, under a docstring (`:62`) that says "This repo
  configures no logger" — which stopped being true at `:143`, where Story 5.1 landed
  `configure_json_logging()` as the first statement of `main()`.

Measured end to end at creation (canary bound from a variable, not a source literal):

```
[SQL: select ? from nonexistent_table]\n[parameters: ('WORKER-SECRET-123456',)]   → LEAKED
same engine with hide_parameters=True:
[SQL parameters hidden due to hide_parameters=True]                              → not leaked
```

**Scope summary:** a sanitizing rewrite of the non-telemetry branch of `JsonLogFormatter`, one
architecture guard that log call sites pass literal message templates, `hide_parameters=True` at
four engine construction sites plus a guard, `include_binary_content=False` on the agent's
`InstrumentationSettings`, `repr=False` on the two credential-bearing `Settings` fields that lack it,
a sanitized worker error path, runtime and AST bounding of telemetry label keys/values, a new
minimization suite driven by three fixture classes, and one generated evidence file registered as a
Gate A check. **No migration, no new table, no new route, no new API response field, no new runtime
dependency, no new golden case, and zero frontend diff.**

**Depends on, and consumes:** Story 5.1's `TelemetryRecordV1`, `TelemetrySink`,
`JsonLogTelemetrySink`, `JsonLogFormatter`, `configure_json_logging`, `TELEMETRY_LABEL_KEYS`, and
`tests/architecture/test_telemetry_boundaries.py`; Story 2.1's `InstrumentationSettings(include_content=False)`
and the in-memory-span-exporter test pattern; Story 2.9's four pinned prompt-injection golden cases;
Story 1.11's `gate_a_checks.py` registry and `evidence_binding.py`; Story 3.11's
`artifact_versions` generator pattern; Story 4.5/4.6's precedent for a registered stored measurement
paired with a live machinery check.

**Unblocks:** Story 5.3 (a one-command run whose logs are safe to show), Story 5.4 (the walkthrough
can point at a proof rather than a promise), and Epic 6's hosted CloudWatch/Logfire surface, which
inherits this story's minimization posture rather than inventing one.

---

## Facts this story depends on — each one written down and citable

Retro action **A3** (`epic-1-2-retro-2026-08-16.md` §6.1) requires this pass before decisions. Every
rule below is recorded somewhere citable; none may be re-derived from code.

| Fact | Where it is written |
|---|---|
| **NFR3, verbatim:** "Workforce, prompt, schedule, approval, and credential content must be excluded from external telemetry **by default**; only explicitly allow-listed sanitized metadata may leave the application boundary." The operative noun is **boundary** — not "must never be written down". | `epics.md:79` (NFR3) |
| **NFR30, verbatim:** "Product data and authoritative audit must remain in **ShiftMind-controlled persistence**; external model and telemetry providers receive only the minimum explicitly configured content." This is the sentence that makes PostgreSQL persistence of prompts, tool payloads and approval evidence **correct rather than a leak**. | `epics.md:133` (NFR30) |
| **NFR4, verbatim:** "Secrets must never appear in prompts, browser payloads, audit summaries, logs, traces, or evaluation fixtures." Six named surfaces — three of which (browser payloads, audit summaries, evaluation fixtures) are **not** in this story's AC1 *Given*. | `epics.md:81` (NFR4) |
| **AD-15's telemetry clause:** "Secrets stay server-side; external telemetry excludes prompt/tool/workforce/schedule content **by default**." Same default-off posture, stated architecturally. | `ARCHITECTURE-SPINE.md` (2026-07-22) — AD-15 |
| **AD-12: no telemetry system authorizes or blocks product work.** CloudWatch owns AWS diagnosis; **sanitized** OpenTelemetry/Logfire owns optional AI traces; PostgreSQL owns product state and append-only business audit. | `ARCHITECTURE-SPINE.md` — AD-12; `epics.md:158` (AR12) |
| **AD-1 / AR1: domain and application code must not import** FastAPI, PydanticAI, SQLAlchemy, Cognito, S3, Logfire, or concrete model providers. Story 5.1 extended the same rule to `adapters/telemetry/` itself via `FORBIDDEN_ADAPTER_ROOT_MODULES`. | `ARCHITECTURE-SPINE.md` — AD-1; `epics.md:147` (AR1); `backend/tests/architecture/test_telemetry_boundaries.py:153-155` |
| **AR27: add and lock each planned dependency only at its implementation gate.** The Stack table's `Logfire SDK 4.38.0` is a **planned optional telemetry seed**. Story 5.1's Decision 10 moved ownership of that row to **this story** and left it `planned`. | `ARCHITECTURE-SPINE.md` — *Stack*; `epics.md:173` (AR27); `5-1-…​.md` Decision 10; `backend/pyproject.toml:26-28` |
| **Epic 5's ACs are subject-neutral, verified at the Epic 4 retrospective:** 5.1 says "structured JSON logs and metrics", 5.2 says "**any configured** trace export". "Epic 5 does NOT inherit the 4.5 AC3/AC4 subject vacuity. CloudWatch stays legitimate in Epic 6." A story that manufactures a Logfire or CloudWatch subject to have something to minimize is doing the wrong thing. | `sprint-status.yaml:2662-2666` |
| **NFR5 coverage is organised by untrusted SOURCE, not by transport, and this MVP has exactly two sources:** the planner's own chat text, and scenario/fixture data. Rendered tool output is a *transport* for scenario data, not a third source. The four pinned injection case ids are `scheduling-baseline-injection-chat-text`, `scheduling-inspect-injection-chat-text`, `scheduling-inspect-injection-fixture-field`, `scheduling-inspect-injection-tool-output`. | `backend/evals/README.md:94-117`; `backend/tests/test_evaluation_harness.py:656-671` |
| **NFR26: normal CI is deterministic-first and keyless.** `create_provider` resolves the `stub` provider by default; `GEMINI_API_KEY`/`OPENROUTER_API_KEY` **must not** be configured as repository secrets. Any secret fixture this story adds is a **synthetic canary**, never a real credential. | `epics.md:125` (NFR26); `docs/CI-SECRETS-CHECKLIST.md` — *Secrets that must NOT be added* |
| **NFR27: every evaluation report must bind dataset, evaluator, model, prompt, tool, policy, application, scenario, solver, code, and image versions** — eleven bindings plus `schema_version`, emitted by `resolve_bindings()`, never hand-typed. | `epics.md:127` (NFR27); `docs/EVIDENCE-CONVENTION.md` — *What `resolve_bindings()` enforces* |
| **Commit the code, then measure on a clean tree, then generate, then commit the evidence separately.** Hand-typing an evidence file is the defect the whole convention exists to prevent. | `docs/EVIDENCE-CONVENTION.md` — *The rule*; `.claude/CLAUDE.md` — *Evidence files* |
| **An evidence file that claims to block release MUST expose a top-level `passed` boolean AND be registered in `backend/scripts/gate_a_checks.py`.** An unregistered blocking artifact makes the gate pass *because* the proof is unbound — the exact failure Stories 3.10 and 3.11 shipped. It must additionally be **paired with a live check on its generator**, because a stored flag is a past-tense answer to a present-tense question. | `docs/EVIDENCE-CONVENTION.md` — *A verdict key Gate A can read*, and the two rules that follow it |
| **Adding a Gate A check or an `NFR29_GATES` invariant obliges regenerating `evidence/story-1.11/gate-a-readiness-report.json`** through the three-runner procedure, on a clean tree, with Docker PostgreSQL up. Two committed tests compare the report to the live registry by identity, not by count. | `docs/GATE-A-RUNBOOK.md` §3; `backend/tests/test_gate_a_readiness.py:335,362` |
| **NFR29's enumerated list does not name content minimization.** It names authorization, approval, isolation, hard constraints, grounding, idempotency, authoritative audit, viewer parity, recovery, accessibility, backup/restore, and rollback. AC2's citation of NFR29 is the *only* authority for treating a leak as release-blocking — see Decision 9, which makes that extension explicitly rather than smuggling it in. | `epics.md:131` (NFR29); AC2 at `epics.md:1420-1423` |
| **Measured fields carry unit suffixes** (`_ms`, `_s`, `_h`, `_bytes`, `_usd`); correlation identifiers are propagated as properties and **never used as metric labels**. | `ARCHITECTURE-SPINE.md` — *Consistency Conventions*, **Time and measures** and **Correlation** rows; `epics.md:117` (NFR22) |
| `outbound`/`inbound` demand is measured in **volume**, `indirect` in **headcount**; assignments carry worker identity but **no `family`**; a metric reading assignments must not accept a `family` argument. **This story computes no demand metric and adds no metric.** It constrains what leaves the application and must not introduce a field derived from, or shaped like, a demand or coverage figure. Workforce rows appear here only as *canary content that must not leak*. | `docs/DOMAIN-MODEL.md` §1, §2, §3 |
| **Manual assistive-technology verification is descoped**; accessibility is proven by automated coverage alone. Not exercised here — this story has a zero-line frontend diff. | `EXPERIENCE.md` — Accessibility Floor; `.claude/CLAUDE.md` |
| **A demonstrated red must come from mutating code that is already green**, and the Dev Agent Record must carry a mutation table (mutation, guard, before, after) before the story reaches review; the reviewer independently re-runs at least one row. Landed as a loaded fact at `c4f5de1`. | `epic-4-retro-2026-09-02.md` §4, §6 A1; `_bmad/custom/bmad-dev-story.toml`; `_bmad/custom/bmad-code-review.toml` |

---

## Acceptance Criteria

Verbatim from `epics.md:1415-1423`.

**AC1.**
**Given** structured application logging and any configured trace export
**When** logs and traces emit
**Then** content and binary capture are disabled by default, only allow-listed sanitized attributes
may leave the application, and credentials, workforce data, prompts/completions, schedule payloads,
tool arguments/results, and approval evidence are scrubbed
**And** external model and telemetry providers receive only the minimum explicitly configured
content. (NFR3, NFR4, NFR30)

**AC2.**
**Given** secret, prompt-injection, and adversarial telemetry fixtures
**When** the minimization suite executes
**Then** any prohibited content in a log or exported trace fails the story
**And** `evidence/story-5.2/content-minimization-report.json` records the tested channels, fixtures,
and artifact versions. (NFR5, NFR27, NFR29)

---

## Measured at creation — `c0ef358`, clean tree

Do not re-derive these from code; re-verify them at Task 1 and record any drift.

| Fact | Measurement |
|---|---|
| Backend default suite | **1558 passed, 1 skipped, 7 deselected** (`uv run --frozen pytest -q`, 173.6 s, Docker PostgreSQL **up** — `postgres`-marked tests run in the default suite) |
| Backend `-m postgres` | **158 passed, 1408 deselected** (58.5 s) |
| `tests/test_evidence_convention.py` | **87 passed** |
| `tests/architecture/` | **69 passed** across 11 files |
| `tests/test_gate_a_readiness.py` | **44 passed** |
| Logging call sites in the whole repository (non-test, non-`.venv`) | **five**: `api/routers/approvals.py:229,278,294` (`logger.exception`), `api/routers/conversations.py:353,464` (`logger.exception`), plus one `logger.info` at `conversations.py:412`. Two `logging.getLogger(__name__)` calls, at `approvals.py:62` and `conversations.py:100` |
| Effective level of those loggers | inherited from **root = `WARNING`**. `configure_json_logging` deliberately raises only `shiftmind.telemetry` to `INFO` (`json_logs.py:78-80`). So every `logger.exception` (ERROR) **does** emit; the single `logger.info` **does not** |
| Handler placement | `configure_json_logging()` adds one `StreamHandler(JsonLogFormatter())` to the **root** logger (`json_logs.py:60-71`). Called from `api/main.py:58` (lifespan) and `worker/main.py:143` (`main()`) |
| The fallback branch | `JsonLogFormatter.format` emits `occurred_at`, `level`, `logger`, **`message` = `record.getMessage()`**, and — when `record.exc_info` is set — **`exception` = `self.formatException(...)`** (`json_logs.py:29-41`) |
| `create_engine` calls passing `hide_parameters` | **zero.** Four non-test SQLAlchemy construction sites: `adapters/postgres/fixture_history.py:54`, `adapters/postgres/identity.py:35`, `scripts/seed_planner.py:134`, and `api/deps.py:238` — the last spelled **`create_postgres_engine`** via the alias at `api/deps.py:17`. Test sites: `conftest.py:55,87`, `tests/fixtures/worker_process.py:42`. Separately, `create_engine` is ALSO the CP-SAT solver factory (`engine/base.py:33`), called at `api/deps.py:68`, `scripts/calibrate_penalties.py:46`, `run.py:25` — same name, different function |
| SQLAlchemy leak, **measured both ways** | default engine → `[SQL: select ? from nonexistent_table]\n[parameters: ('WORKER-SECRET-123456',)]`, canary **present** in the emitted JSON line. `hide_parameters=True` → `[SQL parameters hidden due to hide_parameters=True]`, canary **absent** |
| `InstrumentationSettings` in pydantic-ai 2.27.0 | `include_binary_content: bool = **True**`, `include_content: bool = True`, `include_model_request_parameters: bool = True` (`.venv/…/pydantic_ai/models/instrumented.py:71-74,82-86`). `agent/runtime.py:138-144` sets **only** `include_content=False` — so binary capture is at its permissive default today |
| Span attribute keys actually emitted with `include_content=False` (measured through an in-memory exporter, one tool-calling run) | `agent_name`, `gen_ai.agent.call.id`, `gen_ai.agent.name`, `gen_ai.aggregated_usage.input_tokens`, `gen_ai.aggregated_usage.output_tokens`, `gen_ai.conversation.id`, `gen_ai.input.messages`, `gen_ai.operation.name`, `gen_ai.output.messages`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.system`, `gen_ai.tool.call.id`, `gen_ai.tool.definitions`, `gen_ai.tool.name`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `logfire.json_schema`, `logfire.msg`, `model_name`, `model_request_parameters`, `pydantic_ai.all_messages`. Span names: `invoke_agent agent`, `chat …`, `execute_tool <name>` |
| What the message-shaped attributes actually contain with content off | **structure only.** `gen_ai.input.messages` = `[{"role":"user","parts":[{"type":"text"}]}]`; `gen_ai.output.messages` = `[{"role":"assistant","parts":[{"type":"tool_call","id":"look-1","name":"lookup"}]}]`; `pydantic_ai.all_messages` likewise; `logfire.msg` = `"running tool: lookup"` / `"agent run"`. Prompt and tool-argument canaries **absent** |
| `model_request_parameters` / `gen_ai.tool.definitions` | present, and carry the **full tool JSON schema** (`function_tools[].parameters_json_schema`, `tool_visibility`, `output_mode`, …). Application-authored from `CapabilityManifestV1`; contains no planner or workforce content |
| `Settings` fields carrying a credential | seven. **Five already have `repr=False`** (`llm_api_key:61`, `openrouter_api_key:63`, `oidc_client_secret:74`, `csrf_secret:82`, `agent_runtime_api_key:100`, all tagged T-04-01). **Two do not**: `database_url:54` and `provisioning_database_url:55`, both of which embed `rosterai:rosterai@` by default |
| Existing repr guards | exactly two, and both enumerate one field: `test_oidc_client_secret_is_redacted_from_settings_repr` and `test_csrf_secret_is_redacted_from_settings_repr` (`tests/test_identity_provider.py:66,80`) |
| Existing no-leak assertion | one, and it is scoped to serialized **telemetry records** only: `tests/test_telemetry_correlation.py:219-220` asserts four canaries (`PLANNER_SECRET_5_1`, `MODEL_SECRET_5_1`, `TOOL_ARGUMENT_SECRET_5_1`, `TOOL_RESULT_SECRET_5_1`) are absent. Nothing asserts anything about the *log stream* or about *spans* |
| Worker error path | `worker/main.py::_report_error` (`:59`) prints `f"…{type(error).__name__}: {error}"` to stderr **and** `traceback.print_exception(...)`. Its docstring's premise at `:62` ("This repo configures no logger") is false as of Story 5.1, which added `configure_json_logging()` at `main():143` |
| RFC 7807 surface | already non-disclosing. `versioned_unhandled_problem` returns fixed copy and says so in its own docstring; validation, 401/403/404 and the fallback all use fixed strings (`api/main.py:112-181`). **No change owed here** |
| `AgentRunOutcomeV1.summary` | set to `str(exc)[:200]` at five sites in `agent/runtime.py:282,292,330,355,395`, and **read by nothing** outside tests (`grep '\.summary'` over non-test backend roots returns zero hits). Not a live channel today |
| Registered Gate A evidence paths | **seven**, pinned by identity in `test_registered_evidence_files_are_deliberate` (`tests/test_gate_a_readiness.py:265-286`). Its docstring: *"Adding a fourth is a decision, not a detail."* |
| Ledger entries whose revisit trigger names this story | **two**, both verbatim "Story 5.2's export-boundary minimization work": `deferred-work.md:663` (label *values* have no cardinality guard) and `:667` (the AST walker only catches literal label keys) |

**Frontend was deliberately not measured.** This story has a zero-line frontend diff (Decision 11);
the last recorded figures are Story 5.0's Vitest **647 tests / 85 files** and Playwright **80 tests /
10 files**, which supersede the stale 575/66 carried in the 4.4/4.6 notes. CI floors in
`.github/workflows/ci.yml:9-13` are floors and ceilings — do not edit them.

---

## Twelve decisions were made at story creation — do not re-litigate them

Each decision states its mechanism **and what that mechanism does not cover**. The second half is
load-bearing: Story 4.2's Decision 10 named a goal and a mechanism that blocked only one of two
directions, and the gap shipped.

### Decision 1 — The channel inventory is closed, and persistence is not one of the channels

AC1's *Given* is "structured application logging and **any configured** trace export". That, plus
NFR3's word "boundary" and NFR30's "product data … must remain in ShiftMind-controlled persistence",
fixes exactly four channels:

| # | Channel | Where |
|---|---|---|
| C1 | JSON log stream — **telemetry** branch | `JsonLogFormatter.format` when `shiftmind_telemetry` is set; fed by `JsonLogTelemetrySink.emit` |
| C2 | JSON log stream — **free-text fallback** branch | `JsonLogFormatter.format` when it is not; fed by every stdlib logger at ≥ root's level |
| C3 | Worker process stderr | `worker/main.py::_report_error` |
| C4 | OpenTelemetry spans | emitted by `Instrumentation(settings=…)` in `agent/runtime.py:161`, exported only when a caller injects a `tracer_provider` |

C1 is already minimal by Story 5.1's Decision 12 and gets only the label bounding in Decision 8.
C2, C3 and C4 are this story's work.

**What this does not cover.** PostgreSQL is **not** a channel: `persisted_event`, `audit_event`,
proposal payloads and approval evidence legitimately hold prompts, tool payloads and schedule rows,
and NFR30 says so in as many words. Do not scrub them; a dev agent that "fixes" persistence has
broken FR20/FR21 provenance to satisfy a requirement that never asked for it. Browser payloads
(NFR4) are also outside AC1's *Given*, and the RFC 7807 handlers already emit fixed copy — verified,
no change owed. Evaluation fixtures (NFR4) are covered only to the extent of Decision 10's
synthetic-canary rule; no existing golden case is edited.

### Decision 2 — C2 is sanitized by rewriting the branch, not by deleting the logger calls

The fallback branch keeps existing, because deleting the five `logger.exception` call sites would
make the agent-run path undiagnosable and each one exists for a documented reason (a revoked
membership race, a run left non-terminal for recovery, a promotion already on the wire). What
changes is **what the branch is allowed to emit**. New closed field set, and nothing else:

| Field | Source | Why it is safe |
|---|---|---|
| `occurred_at` | `record.created` | a timestamp |
| `level` | `record.levelname` | closed stdlib vocabulary |
| `logger` | `record.name` | module path, source-derived |
| `event` | **`record.msg`**, the un-interpolated template | a source literal, guaranteed by Decision 3 |
| `exception_type` | `type(exc).__qualname__` for each exception in the `__cause__`/`__context__` chain | a class name |
| `call_site` | `f"{record.module}:{record.lineno}"` | source coordinates |

**`record.args` is dropped and `record.exc_info` is never formatted.** Those two are the entire leak:
the args are the interpolated values, and `formatException` is what carries
`[parameters: (…)]`, a psycopg `invalid input syntax for type uuid: "…"`, or a pydantic
`ValidationError` echoing its offending input.

**What this does not cover.** The exception *type chain* is retained deliberately, and a type name is
not content — but a future codebase that encodes data into an exception class name would defeat this,
and nothing guards that. Diagnosis loses the interpolated values: an operator reading `event:
"finalizing run %s failed; it remains claimed"` and `call_site` knows *which* arm fired and *where*,
and must join to the telemetry stream's `correlation` block (C1, already carrying `agent_run_id`) for
*which run*. That join is the intended workflow and is why C1 was built first; it is not a gap. This
decision also says nothing about third-party loggers, which Decision 4 owns.

### Decision 3 — Every log call site must pass a literal message template, enforced by AST

Decision 2's `event` field is only safe if `record.msg` is a source literal. A future
`logger.exception(f"failed for {worker.name}")` would put content straight into the field the
sanitizer trusts.

Guard, in `tests/architecture/test_telemetry_boundaries.py`: across the non-test backend roots,
assert the message argument of every logger call is an `ast.Constant` string — rejecting f-strings
(`JoinedStr`), `%`/`+` (`BinOp`), and `.format(...)` / `.join(...)` calls.

**Identify the receiver, never the method name alone.** `debug|info|warning|error|exception|critical|log`
are not unique to `logging.Logger`, and this repository already has three colliding call sites:
`argparse.ArgumentParser.error` at `worker/main.py:161`, `:175` and
`scripts/generate_repair_journey_evidence.py:316` — and `worker/main.py:175`'s argument **is** an
f-string. A name-only walker flags all three on day one, and after Task 6 puts a real module logger
into `worker/main.py` the collision is live in a single file. So the walker must first collect the
names bound by `<name> = logging.getLogger(...)` in the module, and flag only calls whose receiver is
one of those names (plus a direct `logging.getLogger(...).<method>(...)` chain).

Those three `parser.error` calls are **not** a leak and are deliberately out of scope: their
arguments are an operator-supplied CLI value and an import-time `ImportError`/`AttributeError`/
`TypeError`/`ValueError`, neither of which carries planner, workforce or schedule content. Say that
in the guard's docstring so the next reader does not "fix" argparse to satisfy a logging rule.

**What this does not cover.** It is an AST guard over *this repository's* roots: a logger call inside
a third-party package, or one built by a helper that receives the string as a parameter, passes it.
A logger obtained in a way the walker does not model — passed in as an argument, pulled off `self`,
or fetched inline through a wrapper — is also invisible to it; no such pattern exists today, and the
walker's receiver rule is what makes that assumption checkable rather than assumed. It does not bound
`record.args` — it does not need to, because Decision 2 drops them entirely; the two mechanisms are
deliberately independent so that neither alone is load-bearing.

### Decision 4 — Third-party loggers reach C2 too, and the same sanitizer covers them

Story 5.1's code review already scoped the *level* bump to `shiftmind.telemetry` so SQLAlchemy/httpx
`INFO` records stop flowing. But root's own level is `WARNING`, so any library's `WARNING` or
`ERROR` still reaches the root handler and is formatted by the same fallback branch — and a library's
message is emphatically not a source literal of ours.

Decision 2's field set handles this correctly **because it does not trust `record.msg` blindly** in
one respect: it emits the template, and for a third-party record whose `msg` is already an
interpolated string the template *is* that string. So one extra rule: the fallback branch emits
`event` only for records whose `record.name` is under an application-owned prefix
(`api`, `worker`, `application`, `adapters`, `agent`, `engine`, `services`, `store`, `scripts`,
`shiftmind`); for every other logger it emits the fixed literal `"third_party"` and keeps `logger`,
`level`, `exception_type` and `call_site`.

**What this does not cover.** It means a genuinely useful third-party diagnostic — a connection-pool
warning naming a host — is reduced to its logger name and exception type. That is the accepted cost
of a default-deny boundary and is why `logger` and `call_site` are retained. It also does not stop a
library writing to stdout/stderr directly, outside `logging` entirely; nothing in this repository
can, and no guard is added for it.

### Decision 5 — `hide_parameters=True` at every engine construction site, plus an AST guard

The formatter no longer emits exception text, so this is defence in depth rather than the primary
fix — and it is worth having because it removes the values at the **source**, before any future
consumer (a debugger, a `print`, a test's `--showlocals`, Epic 6's CloudWatch) can pick them up.
Applied at the four non-test sites; guarded by an AST test asserting every **SQLAlchemy** engine
construction under the non-test backend roots passes `hide_parameters=True`.

**Resolve the import binding, never the call name.** `create_engine` is bound to *two different
functions* in this repository, and a name-based walker is wrong in both directions:

| Call site | Bound to | Guard must |
|---|---|---|
| `adapters/postgres/fixture_history.py:54`, `adapters/postgres/identity.py:35`, `scripts/seed_planner.py:134` | `sqlalchemy.create_engine` | **flag** |
| `api/deps.py:238` — spelled **`create_postgres_engine`**, an alias set at `api/deps.py:17` | `sqlalchemy.create_engine` | **flag** |
| `api/deps.py:68`, `scripts/calibrate_penalties.py:46`, `run.py:25` | `engine.base.create_engine` — the **CP-SAT solver factory** | **ignore** |

A name-only walker therefore *misses* `api/deps.py:238` — the engine serving every API request, the
single most important site — while *flagging* three solver-factory calls. It would go green with the
main runtime engine unprotected: the "guard that cannot go red" pattern the Epic 1-2 retrospective
names as this project's most expensive. So the walker must build a per-module map of local binding
name → origin from each `Import`/`ImportFrom` (honouring `asname`) and flag only bindings that
resolve to `sqlalchemy.create_engine`.

**What this does not cover.** It hides bound *parameters*, not the SQL statement text — which is
application-authored and safe. It does not touch the three test-fixture engines
(`conftest.py:55,87`, `tests/fixtures/worker_process.py:42`), deliberately: a red test that cannot
show its bound parameters is materially harder to fix, and those engines never run in a deployment.
And it cannot reach an engine built by a factory supplied through
`SHIFTMIND_WORKER_RUNTIME_FACTORY` from outside this repository — **Story 5.3 owns the first
production worker factory and inherits this obligation**; say so in its story rather than assuming
the guard travels.

### Decision 6 — C4: `include_binary_content=False` is added; `include_model_request_parameters` stays `True`

AC1 says "content **and binary** capture are disabled by default". Measured:
`InstrumentationSettings.include_binary_content` defaults to `True` and `agent/runtime.py:138-144`
never sets it. One keyword, both call arms.

`include_model_request_parameters` stays at its default, deliberately. Measured, it serializes the
**tool definitions** — `function_tools[].parameters_json_schema`, `tool_visibility`, `output_mode` —
which are authored by `CapabilityManifestV1`, contain no planner, workforce or schedule content, and
are the single most useful attribute for diagnosing a mis-routed capability. Recorded here so the
next reader does not re-open it.

**What this does not cover.** Measured on pydantic-ai **2.27.0** with a text-only prompt: no
`BinaryContent` reaches the agent today, so this flag is closing a latent path, not an exploited one
— which is exactly why it must be set rather than argued away. The flag also does not bound the tool
*schema* size; `model_request_parameters` can be large, and the ledger's low-severity efficiency row
is the place for that, not this story.

### Decision 7 — C4's proof asserts on OBSERVED spans, never on the settings object

Story 2.1's spike states the rule in its own docstring: *"Reading `settings.include_content is False`
would prove nothing about what is emitted."* The minimization suite therefore drives a real agent run
through an `InMemorySpanExporter` (the `opentelemetry-sdk` dev dependency Story 2.1 added for exactly
this) and asserts over the serialized span blob: every canary absent, and every emitted attribute key
present in a declared allow-list constant.

The allow-list is seeded from the 23 keys measured at creation and lives beside the guard, so a
pydantic-ai upgrade that starts emitting a new attribute turns the suite **red and names the key**
rather than silently exporting it.

**What this does not cover.** The allow-list bounds attribute *keys*. Values are bounded by the
canary assertions and by `include_content=False`, not by a schema — a future framework version that
starts putting content into an *already-allowed* key (say `logfire.msg`) is caught only if a canary
happens to reach it. The canary set in Decision 10 is chosen to make that likely, not certain. Nor
does this story add an exporter: see Decision 12.

### Decision 8 — Label keys and values are bounded at the sink and at the AST, closing two ledger rows

`deferred-work.md:663` and `:667` both name "Story 5.2's export-boundary minimization work" as their
owner. Both close here:

* **Runtime (`:663`):** `JsonLogTelemetrySink.emit` drops any label whose key is not in
  `TELEMETRY_LABEL_KEYS`, and truncates any label value over a declared maximum
  (`_MAX_LABEL_VALUE_CHARS`). A dropped key is not an error — AD-12 forbids telemetry raising — it
  simply does not leave.
* **AST (`:667`):** the existing walker is extended from *enumerating literal keys* to **rejecting
  non-literal ones**: a `labels` dict with a computed key, a `labels[...] = …` subscript
  whose key is not an `ast.Constant`, or a `labels.update(...)` call, all fail.

  > **CORRECTED at code review (2026-09-05): "or value" is struck as unimplementable.** A walker that
  > rejects a computed label *value* flags 8 legitimate producer sites and 0 key violations —
  > `api/main.py` (`route_template`, `request.method`, `status_class`), `agent/runtime.py`
  > (`self._config.model`, `budget_outcome`), `decide_approval.py` (`outcome`),
  > `execute_schedule_run.py` (`outcome.solver_status`), `lease_and_execute_schedule_run.py`
  > (`lease.job_type`). A label value **must** vary at runtime or the label records nothing, so
  > requiring it to be a literal contradicts what a label is for. The key half is the whole
  > implementable surface. Do not re-open this as unfinished work.

**What this does not cover.** Truncation bounds a value's *length*, not its *contents* and not its
*cardinality*: a 20-character secret in `failure_reason` still leaves, and a 36-character UUID
survives the 128-character bound intact. That is bounded instead by the closed vocabularies those
keys already draw from (`agent/runtime.py:316-320` refuses any failure code no granted manifest
declares) — i.e. by the type system, not by anything this story builds. Named so a later story
adding a label from a free field knows the residual shape. **Because of this, `deferred-work.md:663`
is re-pointed rather than closed at code review: its subject was cardinality, and cardinality is
the metrics-exporter question, owned by Epic 6.**

### Decision 9 — The evidence file is release-blocking, therefore registered — and NFR29's list is extended on purpose

AC2 cites **NFR29** and says a leak "fails the story". NFR29's enumerated list does **not** name
content minimization (it names authorization, approval, isolation, hard constraints, grounding,
idempotency, authoritative audit, viewer parity, recovery, accessibility, backup/restore, rollback).
Two readings were available and one is wrong:

* Emit `passed` without registering. This is **exactly** the Story 3.10/3.11 defect the evidence
  convention was written to stop: an unregistered artifact cannot block anything, so the gate goes
  green *because* the proof is unbound.
* Register it, and say plainly that AC2's citation is what puts content minimization into
  `NFR29_GATES`. **This is the decision.**

So: a new `Invariant("content_minimization", …, "NFR29")` in `NFR29_GATES`; a `GateACheck` binding
`evidence/story-5.2/content-minimization-report.json`; and — per the convention's second rule — a
**paired live pytest check on the generator's own machinery**, so the invariant never rests on a
stored flag alone. The registered-evidence set in `test_gate_a_readiness.py:265` grows from seven to
eight, which its own docstring says must be a decision; this is that decision, recorded.

**What this does not cover.** Gate A is the **AR28 entry boundary for Epic 2**, long since passed. A
red here therefore blocks the release-gate report and Story 5.4's claim, not any epic boundary — do
not describe it as "blocking Epic 2". The invariant covers only Decision 1's four channels; a leak
through persistence or the browser is out of its scope by construction, not by oversight.

### Decision 10 — Three fixture classes, mapped onto the taxonomy that is already written down

AC2 names "secret, prompt-injection, and adversarial telemetry fixtures". Each maps to something that
already exists rather than a new invention:

1. **Secret fixtures** — synthetic canaries injected into every credential-bearing environment
   variable (`GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `OIDC_CLIENT_SECRET`, `CSRF_SECRET`,
   `AGENT_RUNTIME_API_KEY`, `DATABASE_URL`, `PROVISIONING_DATABASE_URL`). **Never a real key** —
   `docs/CI-SECRETS-CHECKLIST.md` forbids configuring one, and NFR26 keeps CI keyless.
2. **Prompt-injection fixtures** — the **four pinned golden case ids**, reused, not re-authored.
   They already cover both untrusted sources named in `evals/README.md:94-117` (planner chat text;
   scenario data, via both the fixture-field and rendered-tool-output transports). The new assertion
   is orthogonal to the existing one: 2.9 proves the injection cannot widen authority; 5.2 proves its
   *text* does not reach a log or a span.
3. **Adversarial telemetry fixtures** — values engineered against the sanitizer itself: a control
   character and a newline (would break JSON-lines framing), a value far over
   `_MAX_LABEL_VALUE_CHARS`, a `%`-format directive inside a log argument, a label key ending `_id`,
   and a computed label key.

**What this does not cover.** Class 1 proves a canary placed in configuration does not reach a
channel; it does not prove the *real* deployment secret is unreachable, which no test can. Class 2
reuses cases pinned by `test_injection_corpus_attempts_compliance_but_cannot_widen_authority` — if
that set ever changes, this suite must follow, and the coupling is deliberate so it cannot drift
silently. No new golden case is added, and `MVP_PRODUCT_CAPABILITIES`'s four-case floor is untouched.

### Decision 11 — No exporter, no Logfire SDK, no new dependency, no migration, zero frontend diff

AC1 says "**any configured** trace export", and the Epic 4 retrospective verified at
`sprint-status.yaml:2662-2666` that Epic 5's ACs are subject-neutral. AR27 forbids locking a planned
dependency before its gate, and `backend/pyproject.toml:26-28` records the deliberate work already
done to keep the Logfire SDK out of the tree. The only export path that exists is a caller-injected
`tracer_provider`; Decision 7 makes that path provably minimal, which satisfies the conditional.

**The Stack table's `Logfire SDK 4.38.0` row stays `planned` after this story**, and ownership passes
to **Epic 6**, which is where AD-12 puts hosted diagnosis. Say so in Completion Notes rather than
leaving a reader to infer that "the leak story" satisfied it.

**What this does not cover.** Nothing here proves anything about a *future* exporter's own
configuration — an OTLP endpoint, its headers, or its sampling. Epic 6 inherits that. Frontend: zero
lines; `docs/API.md` is untouched because no published contract changes; the only documentation owed
is `docs/CONFIGURATION.md` and `docs/CI-SECRETS-CHECKLIST.md` (Task 12).

### Decision 12 — Ledger disposition: two close, one stays open, and three new entries are owed

* `deferred-work.md:663` (label values unguarded) and `:667` (AST walker's literal-only blind spot) —
  **CLOSE**, per Decision 8. Both name this story's export-boundary work as their trigger and both
  are discharged by mechanism, not by argument.
* `deferred-work.md:669` (`tool_call_id` is a model-controlled unbounded string) — **LEAVE OPEN,
  UNTOUCHED.** Its trigger is "the first real (non-stub) provider wired in, or the first capability
  module that lets the model influence this ID". Neither fires here. Decision 8's truncation applies
  to *labels*, and `tool_call_id` is a `correlation` property, not a label — do not conflate them and
  do not claim this story bounded it.
* `deferred-work.md:508`, `:639` (`diagnosis:cloudwatch_owned_by_epic_6`) — **LEAVE OPEN.** Decision
  11 keeps CloudWatch in Epic 6.
* New entries owed by this story: the exception-class-name residual (Decision 2), the third-party
  stdout/stderr path (Decision 4), and the factory-supplied engine outside the AST guard's reach
  (Decision 5), each with an owner and a revisit trigger.

**What this does not cover.** Task 13 edits `deferred-work.md` for the two closes and this story's
own new entries, and touches `sprint-status.yaml` only for this story's own row. It reconciles
nothing else and re-points nothing.

---

## Tasks / Subtasks

- [x] **Task 1 — Re-verify the creation measurements before changing anything (AC: 1, 2)**
  - [x] Confirm `git rev-parse HEAD` is `c0ef358` or record the drift.
  - [x] Re-run the four suites in *Measured at creation* and record any difference in the Dev Agent
        Record. Docker PostgreSQL must be up, or the default-suite figure is not comparable.
  - [x] Re-confirm the five logging call sites, the four `create_engine` sites, and that
        `agent/runtime.py` still sets only `include_content=False`. If any moved, use the new
        location and note it — do not assume the line numbers.

- [x] **Task 2 — Reproduce the leak before fixing it (AC: 1)**
  - [x] Add `backend/tests/test_content_minimization.py`. First case: a canary bound from a
        variable flows through a real `StatementError` into a `logger.exception` on a logger whose
        handler is `JsonLogFormatter`; assert the canary is **absent** from the emitted line. Confirm
        by hand that it fails on the pre-Task-3 formatter, and record that observation in the Debug
        Log.
  - [x] Second case: the same for `worker/main.py::_report_error`, captured on a redirected stderr.
  - [x] This is a leak reproduction, **not** the demonstrated red. Per retro A1 a red from
        incomplete code does not count; the demonstrated reds all come from Task 14's mutations of
        already-green code.

- [x] **Task 3 — Sanitize the non-telemetry branch of `JsonLogFormatter` (AC: 1) — per Decision 2 and Decision 4**
  - [x] Replace the fallback branch's payload with the closed field set in Decision 2's table.
        `record.args` are dropped; `record.exc_info` is walked for `type(exc).__qualname__` across
        the `__cause__`/`__context__` chain and never formatted.
  - [x] Apply Decision 4's application-owned logger-prefix rule to the `event` field.
  - [x] Do not touch the telemetry branch. Do not change `configure_json_logging`'s level scoping —
        Story 5.1's review deliberately narrowed it to `shiftmind.telemetry`.

- [x] **Task 4 — Guard that log call sites pass literal templates (AC: 1) — per Decision 3**
  - [x] Extend `backend/tests/architecture/test_telemetry_boundaries.py` with an AST walker over the
        non-test backend roots rejecting a non-`ast.Constant` message argument to a logger call.
  - [x] **Resolve the receiver — do not match on method name alone.** Collect the names bound by
        `<name> = logging.getLogger(...)` per module and flag only those receivers. Three existing
        `argparse.ArgumentParser.error` call sites collide by name (`worker/main.py:161,175`,
        `scripts/generate_repair_journey_evidence.py:316`) and one of them passes an f-string; a
        name-only walker is red on arrival, and Task 6 makes the collision live inside a single file.
        Record in the guard's docstring why those three are out of scope (per Decision 3).
  - [x] Add the paired `test_each_guard_detects_synthetic_violating_source`-style case, following the
        file's existing convention at `:308`.

- [x] **Task 5 — `hide_parameters=True` at the four non-test engine sites, plus its guard (AC: 1) — per Decision 5**
  - [x] `adapters/postgres/fixture_history.py:54`, `adapters/postgres/identity.py:35`,
        `api/deps.py:238`, `scripts/seed_planner.py:134`.
  - [x] AST guard asserting every **SQLAlchemy** engine construction under the non-test roots passes
        it. **Resolve the import binding, not the call name** — per Decision 5's table, `create_engine`
        names two different functions here, so a name-only walker misses the aliased
        `create_postgres_engine` at `api/deps.py:238` and flags three CP-SAT solver-factory calls.
        Build a per-module binding→origin map from `Import`/`ImportFrom` (honouring `asname`).
  - [x] Add the negative case too: a synthetic module importing `engine.base.create_engine` must
        **not** be flagged, and one importing `sqlalchemy.create_engine as anything` must be. Without
        both directions the guard proves only one of the two failure modes.
  - [x] Scope the walker so the three test-fixture engines are excluded by path, and state that
        exclusion in the test's docstring per Decision 5.

- [x] **Task 6 — Sanitize the worker's error path (AC: 1) — per Decision 1 (channel C3) and Decision 2**
  - [x] Replace `_report_error`'s `print` + `traceback.print_exception` with a module-logger call
        carrying a **literal** template. `logger.exception` is fine and is the natural choice: after
        Task 3 the formatter is what drops the args and the traceback, so the worker needs no
        scrubbing of its own — it needs to stop bypassing the formatter via `print`/stderr.
  - [x] Correct the docstring's false premise ("This repo configures no logger") — `main()` calls
        `configure_json_logging()` at `:143`.
  - [x] Keep the backoff behaviour byte-for-byte: `MAX_ERROR_BACKOFF_SECONDS`, the reset on success,
        and `run_worker_loop`'s `on_error` injection point are Story 3.x recovery guarantees and are
        not this story's to change.

- [x] **Task 7 — `include_binary_content=False` (AC: 1) — per Decision 6**
  - [x] Add the keyword to **both** arms of the `InstrumentationSettings` construction at
        `agent/runtime.py:138-144` — the `tracer_provider is not None` arm and the bare one.
  - [x] Extend the comment above it to name the flag and its default, so the next reader does not
        have to open the vendor source to learn that `True` was the default.

- [x] **Task 8 — `repr=False` on the two credential-bearing settings fields, guarded by derivation (AC: 1) — per Decision 10, fixture class 1**
  - [x] `database_url` and `provisioning_database_url` gain `field(repr=False)`, tagged like the
        existing five (T-04-01).
  - [x] Replace the enumeration pattern: add one test that sets a distinct canary into **every**
        credential-bearing environment variable in Decision 10's class-1 list and asserts none appears
        in `repr(default_settings())`. The env-var list is the closed input, so a new credential
        setting added without `repr=False` turns it red. Leave the two existing single-field tests in
        place — they are cheap and they name their own regression.

- [x] **Task 9 — Bound telemetry label keys and values (AC: 1) — per Decision 8**
  - [x] Runtime: `JsonLogTelemetrySink.emit` drops keys outside `TELEMETRY_LABEL_KEYS` and truncates
        values over `_MAX_LABEL_VALUE_CHARS`. Never raise — AD-12.
  - [x] AST: extend the existing walker in `test_telemetry_boundaries.py` from enumerating literal
        keys to **rejecting** computed keys and values, and `labels.update(...)`.

- [x] **Task 10 — The minimization suite (AC: 2) — per Decisions 7 and 10**
  - [x] Three fixture classes exactly as Decision 10 defines them, in
        `backend/tests/test_content_minimization.py`.
  - [x] Channel coverage: C2 (log stream, both application and third-party records), C3 (worker
        stderr), C4 (observed spans through an `InMemorySpanExporter`), and a C1 regression case
        asserting Story 5.1's four existing canaries still do not appear.
  - [x] Declare the span-attribute allow-list as a module constant seeded from the 23 keys measured
        at creation, and assert emitted keys are a subset of it.
  - [x] Import `opentelemetry.sdk` **hard, never `importorskip`** — it is a declared dev dependency
        and a skipped privacy proof is a false green (`tests/test_agent_runtime_adapter.py:682` sets
        the precedent and says why).
  - [x] Reuse the four pinned injection case ids; do not author a new golden case.

- [x] **Task 11 — Generate the evidence file (AC: 2) — per Decision 9 and `docs/EVIDENCE-CONVENTION.md`**
  - [x] Write `backend/evals/content_minimization_report.py`, following
        `recovery_idempotency_report.py`'s shape: named `PROOF_NODES` (one per channel × fixture
        class, so a regression is attributable to a channel rather than to "the suite"), JUnit
        ingestion via `_junit_outcome` requiring `tests > 0, skipped == 0, failures == 0, errors == 0`,
        `ARTIFACT_CONTRACT_MODULES`/`ARTIFACT_DECLARED_VERSIONS` for AC2's "artifact versions", and
        `resolve_bindings()` for all eleven NFR27 bindings plus `schema_version`.
  - [x] Emit a top-level **`passed`** boolean. Also record `channels` (Decision 1's four) and
        `fixtures` (Decision 10's three classes with their case ids) — AC2 names both explicitly.
  - [x] Exempt the generator's **own output** from the dirty-tree check, using the
        `own_output` / `ValueError` pattern at `recovery_idempotency_report.py:390-396` verbatim —
        writing the report is what dirties the tree, and without the exemption the generator dies on
        `DirtyTreeError` before doing any work. An uncommitted *source* change still refuses, which is
        the point.
  - [x] **Order is the requirement, not a nicety:** commit the code first; confirm
        `git status --porcelain` is empty; run the measurement; generate; run
        `pytest tests/test_evidence_convention.py`; commit the evidence on its own. Never hand-type
        the file. Do not use `--allow-dirty`.
  - [x] The full three-commit sequence for Tasks 11-12 is in *Dev Notes → The commit plan*. Follow it
        literally; the ordering is load-bearing, not stylistic.

- [x] **Task 12 — Register the Gate A check and regenerate the readiness report (AC: 2) — per Decision 9**
  - [x] Add `Invariant("content_minimization", …, "NFR29")` to `NFR29_GATES` and the paired
        `GateACheck` entries in `backend/scripts/gate_a_checks.py`: one binding the evidence path, one
        live pytest check on the generator's machinery.
  - [x] **Three committed assertions must be updated in the same commit as the registry edit, or
        they go red for the wrong reason:**
        (a) `test_accessibility_is_tracked_as_nfr29_not_as_an_ar28_invariant` (`:94-108`) pins
        `NFR29_GATES` as an **exact ordered tuple** of five keys — append `"content_minimization"`.
        (b) `test_registered_evidence_files_are_deliberate` (`:265`) pins seven evidence
        paths — make it eight, with a comment recording that it is a decision (its docstring demands
        one).
        (c) `test_registry_covers_more_than_the_four_evidence_files` (`:171`) fails any invariant
        resting on evidence files alone — this is the mechanical enforcement of Decision 9's paired
        live check, so `content_minimization` must carry the generator-machinery check or it is red.
  - [x] **Exactly two tests are then unavoidably red at that commit** — the two report-drift
        assertions at `:335` and `:362`. They cannot be fixed by editing a test; only the pass-2
        report fixes them. That one-commit red window is structural (`resolve_bindings()` refuses a
        dirty tree, so the registry must be committed before the report can bind to it) and is the
        minimum achievable. Story 4.6's ordering produced a **four**-commit window instead.
  - [x] **Sequencing trap A — the registry must not name a file that does not exist yet.**
        `test_every_registered_evidence_file_exists_on_disk` requires the file present when the
        registry names it, while the evidence convention requires the code commit to precede the
        evidence commit. Resolve it by putting the *registry edit* in the **evidence commit**,
        alongside the report — the registry is a statement about the evidence, so it belongs with it.
        Story 4.6 did the opposite (`b7ec2eb` put the registry edit in its `feat` commit) and left
        the backend suite red for four commits; **do not copy that.**
  - [x] **Sequencing trap B — the readiness report must be regenerated TWICE, and the runbook does
        not say so.** `backend/tests/test_gate_a_readiness.py` is itself a registered contributing
        check under `measurement_integrity` (`gate_a_checks.py:457-468`). So on pass 1 the pytest run
        still sees the *stale committed* report, `test_committed_readiness_report_covers_exactly_the_live_registry`
        and its `_nfr29_gates` sibling are red, and the report generated from that XML records
        `measurement_integrity` as **failed**. Pass 2 re-runs pytest against the now-correct report on
        disk and regenerates from the green XML. `gate_a_readiness.py` exempts its own output (and its
        `.tmp` sibling) from the dirty-tree check for exactly this reason — its comment at `:605-608`
        says "run 2 of 2" — so **both passes run on an otherwise clean tree and `--allow-dirty` is
        never needed.** Commit only the pass-2 report.
  - [x] Run both passes through the three-runner procedure in `docs/GATE-A-RUNBOOK.md` §3, with
        Docker up. Record the two-pass sequence and both verdicts in the Dev Agent Record.
  - [x] **Fix the runbook.** §3 documents a single pass and is silent on trap B; the knowledge lives
        only in a code comment. Add the second pass and its reason to `docs/GATE-A-RUNBOOK.md` §3 —
        this story is the first to hit it since the exemption was written, and leaving it in a
        comment is how the next story rediscovers it at review.
  - [x] Update `docs/CONFIGURATION.md` if any setting is added (none is expected — this story adds no
        env var), and add a line to `docs/CI-SECRETS-CHECKLIST.md`'s review checklist noting that the
        minimization suite's canaries are synthetic and must never be replaced with real keys.

- [x] **Task 13 — Ledger and status (AC: 2) — per Decision 12**
  - [x] Close `deferred-work.md:663` and `:667`, each naming the mechanism that discharged it.
  - [x] Leave `:669`, `:508` and `:639` untouched; do not re-point them.
  - [x] Add the three new entries Decision 12 names, each with an owner and a revisit trigger.
  - [x] Update this story's row in `sprint-status.yaml` and nothing else.

- [x] **Task 14 — Demonstrated-red mutation table (AC: 1, 2)**
  - [x] Before review, fill the table in the Dev Agent Record. Every red must come from **mutating
        already-green code**, not from incomplete code. Minimum rows: the formatter's `record.args`
        drop, the exception-text drop, the literal-template AST guard, the `hide_parameters` guard,
        `include_binary_content`, the settings-repr canary sweep, the label-key drop, the span
        allow-list, and the generator's `skipped == 0` requirement.

### Review Findings

_Code review 2026-09-05 (`dc22bd4..21cdaf8`). Three parallel layers plus reviewer-run
mutations. Every finding below was reproduced by executing code, not inferred from the diff.
Cleared at review, recorded so they are not re-raised: the `hide_parameters` alias path
(mutating `api/deps.py:238` reddens the guard naming that site), the `_tree_is_clean`
exemption (a dirty real source file still raises `DirtyTreeError` naming it), the skip-count
drift (`test_evidence_binding.py:469`'s dirty-tree `skipif`, not test pollution), and the span
allow-list (all 24 keys are observed by the driven run — nothing padded)._

- [x] [Review][Patch] **RESOLVED 2026-09-05 (option 2): drive the real fixtures through the channels** — implement Decision 10 classes 2 and 3 as specified: load the injection text from the four pinned golden files and drive it through C1-C4 (do not re-author), and add the three missing class-3 values (control character, newline, `%`-format directive in a log argument). Sequencing is load-bearing: the C4 span-events patch must land FIRST, or the injection assertion inspects `span.attributes` only and passes vacuously while `exception.message` carries the text. The `%`-directive fixture also reddens mutation-table row 1, closing that finding too. Original finding: **Evidence file records prompt-injection and adversarial fixtures that no proof node exercises** — `fixtures.prompt_injection` names the four pinned `scheduling-*-injection-*` golden cases, but they appear only as `dataset_files` hashed for binding in `content_minimization_report.py:44-49`; no proof node reads them. `fixtures.adversarial` lists "control characters", "newline" and "% directive", none of which any node exercises. Decision 10.2 requires the injection corpus be "reused, not re-authored", and AC2 requires the report record the *tested* fixtures. Two ways out, and the choice is yours: drive the four golden cases through the C1–C4 channels (real work), or narrow the report's declared fixtures to what is actually tested (honest, smaller claim).
- [x] [Review][Patch] **RESOLVED 2026-09-05 (option 2): re-point the entry, and delete the unimplementable half of Decision 8** — close only what shipped (key allow-list + `_MAX_LABEL_VALUE_CHARS` length bound); open a fresh ledger entry for label-value *cardinality* triggered on the first metrics exporter (Epic 6), not on this story. Also record in Decision 8 that "reject a computed label **value**" cannot be built as written: measured, it flags 8 legitimate producer sites (`api/main.py` route_template/method/status_class, `agent/runtime.py` model/budget_outcome, `decide_approval.py` outcome, `execute_schedule_run.py` solver_status, `lease_and_execute_schedule_run.py` job_type) and 0 key violations — a label value must vary at runtime or the label is useless. Strike it so no future story tries to build it. Original finding: **`deferred-work.md:663` was closed on length, not on cardinality** — the entry was NFR22 cardinality ("a future producer could put an unbounded value into an allowed key such as `failure_reason` or `model`"). It is closed by `value[:128]`, which bounds length; a 36-char UUID survives intact. Latent today — both named keys are currently bounded by `Literal` unions, not by the truncation. The tension is in the spec, not the dev's work: Decision 8's own "what this does not cover" sentence says truncation bounds length not contents, while Decision 12 says CLOSE. Choose: reword the closure as partial, re-point the entry, or implement the value guard Decision 8 specified ("a computed key **or value** … all fail" — the AST half rejects keys only, as its own docstring at `test_telemetry_boundaries.py:99` concedes).
- [x] [Review][Note] **ACCEPTED AS DESIGNED 2026-09-05 (option 1): template-only log messages are a deliberate trade-off, no code change** — the formatter emits `record.msg`, never `getMessage()`, so `%s` arguments are dropped. Verified at review that this loses nothing diagnostically material: `api/routers/approvals.py:278` emits a `TelemetryRecordV1` on the same path carrying `correlation.agent_run_id`/`conversation_id`/`request_id` plus `failure_reason` and `agent_run_status` labels, and the log line still carries the full `exception_type` cause chain, `call_site`, `logger` and `occurred_at`. Correlation lives on the telemetry channel by design; logs signal, telemetry diagnoses. The only real loss is the backoff number in the worker's outer-loop handler. Adding allow-listed structured fields to the log payload was considered and rejected: it duplicates what telemetry already carries and adds a second allow-list surface to maintain, i.e. a second place to leak. Original finding: **Sanitized logs are now diagnostically empty** — the formatter emits `record.msg`, never `getMessage()`, so `%s` arguments are dropped with no structured field replacing them: `worker/main.py:62` logs "retrying in %s seconds" with no backoff, `api/routers/approvals.py:278` logs "for agent run %s" with no run id. This is the correct *security* behaviour, and naively "fixing" it is exactly the leak in the finding below. The design call — add safe structured fields to the payload, or accept template-only logs — is yours.
- [x] [Review][Patch] **Mutation-table row 1 is false; Decision 2's `record.args` vector has no test at all** — I applied the row's exact mutation (`"event": record.getMessage() if owned else "third_party"`) and the minimization suite plus both new architecture guards stayed green (21 passed); the Acceptance Auditor saw the full suite stay green too. The mutation reintroduces a real leak: `logger.error('db failed for %s', secret)` then emits `"event":"db failed for WORKFORCE-ROW-SECRET-42"`. The only helper, `_formatted_exception_line`, passes `"safe-id"` as its sole arg, so no test can ever carry a canary through `record.args`. [backend/adapters/telemetry/json_logs.py:47]
- [x] [Review][Patch] **C3's worker-stderr proof is a false green** — passes only because pytest installs root handlers. Run with `-p no:logging` it FAILS: the canary is present in redirected stderr, because with no root handler `logging.lastResort` writes the full traceback and message there. The test never asserts the sanitized boundary was used, and three of the twelve evidence cells rest on it. [backend/tests/test_content_minimization.py:61-71]
- [x] [Review][Patch] **C4 spans leak exception content through span EVENTS, which the suite never inspects** — on the provider-error path OpenTelemetry records an `exception` event carrying `exception.message` and `exception.stacktrace` verbatim. Reproduced: a canary raised from the model appears in the span events of both `chat` and `invoke_agent` spans, while `keys <= SPAN_ATTRIBUTE_ALLOW_LIST` passes and the canary is absent from `attributes`. The test builds its blob from `span.attributes` only. Latent while no exporter is wired, live the moment Epic 6 lands Logfire — which this story names as planned. [backend/tests/test_content_minimization.py:172-180]
- [x] [Review][Patch] **The literal-template guard's blind spots are live leak paths** — the formatter emits an owned logger's message verbatim, so this guard is the only thing standing between an f-string and a leak. It resolves only module-level `name = logging.getLogger(...)`. Measured green (i.e. bypassed) for: `from logging import getLogger`, `self.logger`, `import logging as lg`, and alias reassignment. Proven end-to-end — a canary via `from logging import getLogger` on logger `api.routers.probe` emitted `"event":"failed for WORKFORCE-ROW-CANARY-XYZ"`. The fix pattern already exists in the same file: the engine guard's import-binding resolution. [backend/tests/architecture/test_telemetry_boundaries.py:121-133]
- [x] [Review][Patch] **A fifth, privileged engine site was never fixed and is invisible to the guard** — `engine_from_config(...)` on `default_settings().provisioning_database_url` (the superuser DSN) with no `hide_parameters`. `migrations/` is not in `NON_TEST_BACKEND_ROOTS`, so the guard can never see it. The story fixed four sites; there are five. [backend/migrations/env.py:81]
- [x] [Review][Patch] **The engine guard misses spellings it claims to cover** — measured green for `import sqlalchemy; sqlalchemy.create_engine(url)`, `import sqlalchemy as sa; sa.create_engine(url)`, and — a name-form call the guard's own shape claims to handle — `from sqlalchemy.engine import create_engine`, whose binding resolves to `sqlalchemy.engine.create_engine` and misses the `sqlalchemy.create_engine` equality check. `engine_from_config` and `create_async_engine` are not in the matched set at all. Not ledgered. [backend/tests/architecture/test_telemetry_boundaries.py:164-172]
- [x] [Review][Patch] **The guard that locks the "attributable proof matrix" cannot go red** — it asserts only that 12 keys exist and each value starts with the file prefix. I collapsed all twelve cells onto a single node and it stayed green. The matrix is in fact 6 distinct tests behind 12 names (all three `c1_telemetry_*` and all three `c3_worker_stderr_*` share one node each), so a regression is not attributable to a channel — the thing Task 11 exists to guarantee. Missing from the mutation table, which the team review rule requires for every new guard. [backend/tests/test_content_minimization_report.py:26-31]
- [x] [Review][Patch] **Fixture class 1 is bound to no proof node** — `test_every_credential_environment_value_is_absent_from_settings_repr` is the only test implementing Decision 10's seven-canary sweep, and it is absent from `PROOF_NODES`. `passed: true` does not depend on it, while the report asserts `"secrets": "seven synthetic configuration canaries"`. [backend/evals/content_minimization_report.py:24-37]
- [x] [Review][Patch] **Stored evidence predates a change to its own proof machinery** — the report records `git_commit: a8e0449` (written at `79bb374`), but `4be2534` subsequently changed `test_content_minimization_report.py`, the registered `content_minimization_report_machinery` check for the same invariant. The final refresh at `3750134` touched only the readiness report. `docs/EVIDENCE-CONVENTION.md` exists to prevent exactly this; regenerate. [evidence/story-5.2/content-minimization-report.json]
- [x] [Review][Patch] **A non-str label silently destroys the whole telemetry record; a list defeats the bound** — `value[:128]` sits inside the `try` whose `except Exception: return None` drops the record, so `labels={"failure_reason": 5}` emits zero records where `json.dumps` previously coped. A list value slices by element count, emitting a 5000-char label. Type says `Mapping[str, str]`, so both are latent. Coerce with `str(value)[:N]`. Also unbounded here: the `exception_type` chain has a cycle guard but no depth cap. [backend/adapters/telemetry/json_logs.py:69-72]
- [x] [Review][Patch] **`extra={"shiftmind_telemetry": ...}` bypasses the allow-list and truncation entirely** — the formatter dumps the payload verbatim; only the sink applies the key filter and the 128-char bound. Any other caller setting that attribute ships an arbitrary dict. Only the sink sets it today. [backend/adapters/telemetry/json_logs.py:35]
- [x] [Review][Patch] **Run the worker as a process and its own error channel goes blank** — `logger = logging.getLogger(__name__)` becomes `__main__` under both `python worker/main.py` and `python -m worker.main`, and `__main__` is not in `_APPLICATION_LOGGER_PREFIXES`, so the sanitized event renders as `"third_party"` and the failure message is discarded. Verified; the file carries `if __name__ == "__main__"`. The test imports the module, so it never sees this. Name the logger literally. The same prefix list omits `evals`, `ingest`, `llm`, `domain` and `config`. [backend/worker/main.py:34]
- [x] [Review][Patch] **Both new guards walk 9 of 16 first-party package directories** — `NON_TEST_BACKEND_ROOTS` omits `config`, `domain`, `evals`, `fixtures`, `ingest`, `llm`, `migrations` and the three backend-root modules; Tasks 4 and 5 both say "across the non-test backend roots". 41 first-party files are unscanned, including `evals/`, which this story added to. One live violation today (the migrations engine above). [backend/tests/architecture/test_telemetry_boundaries.py:23-26]
- [x] [Review][Patch] **On failure the generator writes the canaries into the committed evidence** — `failures[name]` embeds the child pytest run's full stdout/stderr, so a red proof node would persist into `content-minimization-report.json` exactly the secrets and injection payloads the report exists to prove absent. Also `measure()` has no `except subprocess.TimeoutExpired`, so a node exceeding `timeout=180` crashes the generator and leaves the previous `passed: true` file in place. [backend/evals/content_minimization_report.py:96-127]
- [x] [Review][Patch] **Mutation table is missing rows for delivered guards** — no row for `unsafe_label_operations`, the `_MAX_LABEL_VALUE_CHARS` truncation (the key-drop row covers key filtering only), Decision 4's `_APPLICATION_LOGGER_PREFIXES` third-party rule, `write_report`'s proof-node-completeness `ValueError`, the attributability guard, or the `_tree_is_clean` exemption. Row 1 is false (above); the engine row mutates a literally-named site and so does not prove the alias resolution that the spec was nearly shipped without — I re-ran it at `api/deps.py:238` and it does hold. [story Dev Agent Record]
- [x] [Review][Patch] **Stale counts in Gate A machinery names and comments** — `test_registered_evidence_files_are_deliberate` now guards eight paths under a docstring narrating "three to five"; `gate_a_readiness.py:121` still says "Seventeen of the twenty registry checks" against a registry of 33. A reviewer using either to judge whether growth was deliberate reads a false number. [backend/tests/test_gate_a_readiness.py:255]
- [x] [Review][Patch] **Decision 3's required docstring rationale is not recorded** — the decision asks the guard to say *why* argparse is exempt (an operator-supplied CLI value at import time, carrying no planner, workforce or schedule content) "so the next reader does not 'fix' argparse to satisfy a logging rule". The docstring says only "argparse parser.error is not a log channel". [backend/tests/architecture/test_telemetry_boundaries.py:283]
- [x] [Review][Defer] **Uvicorn's error channel bypasses the sanitizer** [backend/api/main.py:58] — deferred, pre-existing. `LOGGING_CONFIG` gives `uvicorn` `propagate: false` and its own plain-text handler, which `uvicorn.error` inherits, so an unhandled ASGI exception prints message and traceback to stderr without touching `JsonLogFormatter`. Production process composition is explicitly Epic 6's. The new ledger entry names "direct stream writes", which is the wrong mechanism for this one.
- [x] [Review][Defer] **`artifact_versions` digests are never re-verified** [backend/scripts/evidence_binding.py:815] — deferred, pre-existing. `audit_evidence_drift` reads only `contract_digests`; Story 3.11 and Story 5.2 are the two reports using `artifact_versions`, so editing `json_logs.py` leaves the recorded sha256 stale with no drift reported. Inherited convention gap, not introduced here.
- [x] [Review][Defer] **Story 5.1's telemetry guards have their own blind spots** [backend/tests/architecture/test_telemetry_boundaries.py:22] — deferred, pre-existing. `PRODUCER_ROOTS` omits `adapters`, `services`, `store`, `engine` and `scripts`; a non-literal `event=` makes `telemetry_calls` skip the call entirely so run-attribution never sees it; `labels=dict(...)` and `labels=build_labels(...)` are `ast.Call` not `ast.Dict` and pass unflagged; `emit` reached through a bound alias is not counted. All predate this diff.


---

## Dev Notes

### Traps — the quietest first

1. **The telemetry branch is already correct. Do not "improve" it.** `TelemetryRecordV1` has no
   free-text field and `test_telemetry_contract_has_no_free_text_field` enforces that. The leak is
   the *other* branch of the same function. A dev agent that rewrites `JsonLogTelemetrySink.emit`'s
   payload construction has changed the one thing that was fine.

2. **Do not scrub PostgreSQL.** NFR30 says product data *belongs* in ShiftMind-controlled
   persistence. `persisted_event` payloads, `audit_event.safe_summary`, proposal bodies and approval
   evidence are FR20/FR21 provenance. Touching them fails Epic 4's invariants to satisfy a
   requirement that never asked.

3. **`configure_json_logging` attaches to the *root* logger.** That is why a library's `WARNING`
   reaches your formatter and why Decision 4 exists. It is also why you must not raise root's level
   to `INFO` "to see more" — Story 5.1's review explicitly narrowed the bump to
   `shiftmind.telemetry` for this exact reason, and the comment at `json_logs.py:72-77` says so.

4. **`logger.exception` is ERROR and root's default level is WARNING.** So all five call sites emit
   today; the single `logger.info` at `conversations.py:412` does not. Do not "fix" the info call —
   it is silent, and making it loud would add a channel.

5. **`hide_parameters` hides parameters, not the statement.** After Task 5 a `StatementError` still
   prints `[SQL: select ? from …]`. That is application-authored SQL and is safe. A test asserting
   the SQL text is absent will fail for the wrong reason.

6. **Assert on emitted spans, never on the settings object.** `settings.include_binary_content is
   False` proves nothing about what leaves. Story 2.1's spike says so in its own docstring
   (`spikes/agent_runtime/tests/test_capabilities.py:542-547`) and Story 5.1's
   `test_authoritative_audit_survives_a_failing_span_exporter` follows the same discipline.

7. **`importorskip` on `opentelemetry.sdk` would make the privacy proof a false green.** It is a
   declared dev dependency. Import it hard — the precedent and the reasoning are at
   `tests/test_agent_runtime_adapter.py:682-687`.

8. **The generator must require the proof to have RUN.** A pytest process that skips everything
   exits 0. Read the JUnit XML and require `tests > 0, skipped == 0, failures == 0, errors == 0` —
   `_junit_outcome` in `backend/evals/recovery_idempotency_report.py` is the shape to copy, and
   `docs/EVIDENCE-CONVENTION.md` names this as a learned rule.

9. **Registering a Gate A check costs a three-runner regeneration.** pytest **plus** Vitest **plus**
   Playwright, on a clean tree, Docker up, per `docs/GATE-A-RUNBOOK.md` §3 — including the Windows
   streaming-reporter workaround documented there. Budget for it; Story 4.6 paid the same cost.

10. **Two Gate A sequencing traps, not one.** (a) The registry edit belongs in the *evidence*
    commit — `test_every_registered_evidence_file_exists_on_disk` and the convention's commit
    ordering pull in opposite directions. (b) The readiness report must be regenerated **twice**,
    because `test_gate_a_readiness.py` is itself a contributing check, so pass 1's XML necessarily
    contains its own drift failures. Task 12 spells both out. Neither is resolved by
    `--allow-dirty`, and the generator's own output exemption is what makes pass 2 legal on a clean
    tree.

11. **Never put a real API key anywhere near this suite.** `docs/CI-SECRETS-CHECKLIST.md` forbids
    configuring `GEMINI_API_KEY`/`OPENROUTER_API_KEY` as repository secrets, and NFR26 keeps CI
    keyless. Every fixture is a synthetic canary.

12. **`AgentRunOutcomeV1.summary` is not a channel today** — it is `str(exc)[:200]` and is read by
    nothing outside tests. Do not spend the story on it; if you want it recorded, it is a ledger
    entry, not a task.

### Files being modified — read these before editing

| File | What it does today | What this story changes | What must be preserved |
|---|---|---|---|
| `backend/adapters/telemetry/json_logs.py` | Two-branch formatter (telemetry payload; free-text fallback) + `configure_json_logging` installing one root handler and raising only `shiftmind.telemetry` to INFO | Rewrites the fallback branch's field set (Task 3); adds label key-drop and value truncation to `emit` (Task 9) | The telemetry branch verbatim; `emit`'s blanket `except Exception: return None` (AD-12 — two emission sites run inside transactions whose exception rolls back a baseline promotion); the handler-idempotency marker `_shiftmind_json_handler`; the narrowed level scoping and its comment |
| `backend/agent/runtime.py` | Builds `InstrumentationSettings(include_content=False[, tracer_provider])` in two arms at `:138-144` | Adds `include_binary_content=False` to both arms (Task 7) | Both arms — the `tracer_provider is not None` split exists so a test can observe spans without changing what is emitted; the AD-12/AD-15 comment above it; the typed `RunCancelled`/`UsageLimitExceeded` mapping below it |
| `backend/worker/main.py` | `_report_error` prints message + full traceback to stderr; `main()` calls `configure_json_logging()` at `:143` | Sanitized error emission and a corrected docstring (Task 6) | `run_worker_loop`'s backoff (`MAX_ERROR_BACKOFF_SECONDS`, reset on success), the `on_error` injection seam, `install_shutdown_handlers` ordering before the factory runs, and the `dispose()` in `finally` |
| `backend/settings.py` | Five credential fields carry `repr=False`; `database_url`/`provisioning_database_url` do not | Adds `repr=False` to those two (Task 8) | Every default value and every parser; `AC2_CEILING_FIELDS` validation at process start; no new env var is added |
| `backend/adapters/postgres/fixture_history.py`, `…/identity.py`, `backend/api/deps.py`, `backend/scripts/seed_planner.py` | Four `create_engine(...)` construction sites | Adds `hide_parameters=True` (Task 5) | The `engine or create_engine(...)` injection pattern at each site — tests pass their own engine and must keep doing so |
| `backend/tests/architecture/test_telemetry_boundaries.py` | 9 guards incl. the literal-label-key walker and the paired synthetic-violation test at `:308` | Adds the literal-template guard (Task 4), the `hide_parameters` guard (Task 5), the computed-label rejection (Task 9), each with a synthetic-violation pair | Every existing guard; `FORBIDDEN_TEXT_FIELDS`; `FORBIDDEN_ADAPTER_ROOT_MODULES`; `RUN_SCOPED_EVENTS` |
| `backend/scripts/gate_a_checks.py` | `AR28_INVARIANTS` + `NFR29_GATES` + `AC2_GATES`; 31 `GateACheck` entries | One new `NFR29_GATES` invariant and two new checks (Task 12) | `ALL_INVARIANTS`'s composition order; every existing invariant key (the committed report is compared by identity) |
| `backend/tests/test_gate_a_readiness.py` | 44 tests, incl. the seven-path pinned set at `:265` and the two report-vs-registry identity tests at `:335,:362` | Grows the pinned set to eight with a recorded reason (Task 12) | Both identity tests; `test_registry_covers_more_than_the_four_evidence_files` |
| `_bmad-output/implementation-artifacts/deferred-work.md` | The ledger | Closes `:663`, `:667`; adds three entries (Task 13) | `:669`, `:508`, `:639` and every other row |

New files: `backend/tests/test_content_minimization.py`,
`backend/evals/content_minimization_report.py`, `evidence/story-5.2/content-minimization-report.json`.

### The commit plan — Tasks 11 and 12, in order

The ordering is forced by four rules pulling against each other: `resolve_bindings()` refuses a dirty
tree; a registered `evidence_path` must exist on disk; the committed readiness report must match the
live registry by identity; and `test_gate_a_readiness.py` is itself a contributing check, so its own
reds poison any report generated from that run.

| # | Commit | Contents | State after |
|---|---|---|---|
| 1 | `feat(story-5.2): …` | All source and test changes, the generator script, and the `docs/GATE-A-RUNBOOK.md` §3 two-pass fix. **No registry edit, no evidence file.** | Tree clean, suite **green** |
| — | *(measure)* | On the clean tree at commit 1: run the minimization suite to JUnit XML, then generate `evidence/story-5.2/content-minimization-report.json`. `git_commit` binds to commit 1 — the tree that was actually measured | Tree dirty by the report only |
| 2 | `evidence(story-5.2): …` | The story evidence file **plus** the `gate_a_checks.py` registry edit **plus** the three assertion updates (a)(b)(c) above | Tree clean, suite **red on exactly two tests** (`:335`, `:362`) |
| — | *(pass 1)* | Three-runner run at commit 2 → pytest XML carries those two failures → generate. The report on disk now matches the registry, but records `measurement_integrity` **failed**. **Do not commit it** | Report on disk correct, verdict dishonest |
| — | *(pass 2)* | Re-run all three runners — the two tests now read the corrected report on disk and pass — then generate again from the green XML | Report honest and green |
| 3 | `evidence(gate-a): include content minimization` | The pass-2 readiness report only | Tree clean, suite **green** |

Both passes are clean-tree legal because `gate_a_readiness.py:605-612` exempts its own output and its
`.tmp` sibling; `--allow-dirty` is never used and any uncommitted *source* change still refuses.
Commit 2 binds `git_commit` to a commit that touches `gate_a_checks.py`, satisfying the convention's
"the recorded commit touches at least one code file" rule.

**If commits 1 and 2 are merged into one, the story evidence's `git_commit` names a tree that was
never measured** — the exact defect `docs/EVIDENCE-CONVENTION.md` was written to stop. **If the
registry edit is moved into commit 1**, `test_every_registered_evidence_file_exists_on_disk` joins the
red set and the window grows from one commit to three — Story 4.6's mistake, verified in its git
history at `b7ec2eb`.

### Testing requirements

* Backend tests live in `backend/tests/`; architecture guards in `backend/tests/architecture/`.
  Absolute imports from the backend root (`conftest.py` puts it on `sys.path`).
* Run with `uv run --frozen pytest -q` from `backend/`. `addopts = -m "not live"` is in force and
  must stay — `docs/CI-SECRETS-CHECKLIST.md` depends on it.
* Docker PostgreSQL 18 must be up for the default suite to be comparable to the creation figure.
* Every new guard needs a **synthetic violating source** case, matching
  `test_each_guard_detects_synthetic_violating_source`'s existing convention — a guard that has never
  been shown to go red is the pattern the Epic 1-2 retrospective names as this project's most
  expensive.
* No new golden case, no change to `MVP_PRODUCT_CAPABILITIES`, no change to the four pinned injection
  case ids.
* Zero frontend tests are added or changed.

### Project structure notes

`adapters/` is the declared home for telemetry adapters (`ARCHITECTURE-SPINE.md` — *Structural Seed*;
AR26), and `adapters/telemetry/` must import no framework — Story 5.1's
`FORBIDDEN_ADAPTER_ROOT_MODULES` guard covers `fastapi`, `sqlalchemy`, `pydantic_ai`,
`pydantic_graph`, `logfire`, `opentelemetry`. **Task 3's sanitizer therefore may not import
SQLAlchemy to recognise a `StatementError`** — it must work by walking the exception chain
generically and emitting class names, which is what Decision 2 already specifies. `backend/evals/` is
the declared home for report generators (`approval_audit_report.py`,
`recovery_idempotency_report.py`, `repair_correctness_report.py` are the neighbours).
`domain/` and `application/` gain nothing here.

### Open questions — neither blocks this story

1. **Should `event` carry the message template at all?** Decision 2 keeps it because the template is
   a source literal and Decision 3 guards that. A stricter reading of "only allow-listed sanitized
   attributes" would replace it with a closed enum of log-event names, as `TelemetryEventV1` does for
   C1. That is a bigger change (it would touch all five call sites and every future one) and it buys
   little while Decision 3's guard holds. **Revisit trigger:** the first log call site whose template
   cannot be made a literal.

2. **Does `model_request_parameters` belong in a hosted export?** Decision 6 keeps it: it is
   application-authored and diagnostically valuable. Its size is a cost, not a privacy problem.
   **Revisit trigger:** Epic 6 wiring a real OTLP exporter with a per-span size budget.

### References

* AC text, NFR3/4/5/26/27/29/30, AR1/AR12/AR26/AR27 — `_bmad-output/planning-artifacts/epics.md:79,81,83,117,125,127,131,133,147,158,172,173,1415-1423`
* AD-1, AD-12, AD-15, Stack table, Structural Seed, Consistency Conventions — `_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md:52,156,174,254,261,278,302`
* Epic 5 subject-neutrality verification — `_bmad-output/implementation-artifacts/sprint-status.yaml:2592-2597`
* Story 5.1's Decisions 1-4, 10, 12, 13 — `_bmad-output/implementation-artifacts/5-1-instrument-agent-runs-for-latency-budget-and-cost.md:131,190,332,363,384`
* Evidence rules, the `passed` contract, the live-check pairing, the run-must-have-happened rule — `docs/EVIDENCE-CONVENTION.md`
* Three-runner regeneration and the Windows reporter workaround — `docs/GATE-A-RUNBOOK.md` §3
* NFR5's source taxonomy and the four pinned case ids — `backend/evals/README.md:94-117`; `backend/tests/test_evaluation_harness.py:656-671`
* Keyless-CI rule and the forbidden repository secrets — `docs/CI-SECRETS-CHECKLIST.md`
* Demand family/unit dimensional model (no metric is computed here; cited per the standing rule) — `docs/DOMAIN-MODEL.md` §1, §2, §3
* Demonstrated-red definition and the mutation-table requirement — `_bmad-output/implementation-artifacts/epic-4-retro-2026-09-02.md` §4, §6 A1

---

## Dev Agent Record

### Agent Model Used

GPT-5 Codex

### Implementation Plan

Red-green-refactor in story order: reproduce C2/C3 leaks; close and guard log, engine,
worker, settings, label, and span boundaries; generate NFR27 evidence; register the
NFR29 gate; run the required two-pass three-runner Gate A sequence.

### Debug Log References

- Pre-change HEAD drifted from baseline `c0ef358` to `dc22bd45`; creation inventories remained structurally unchanged.
- Baseline: default `1557 passed, 2 skipped, 7 deselected`; PostgreSQL `158 passed`; evidence `87`; architecture `69`; Gate A `44`.
- Leak reproduction: `2 failed` before the formatter and worker fixes, with both synthetic canaries present.
- Span inventory drift: current pydantic-ai also emits allow-listed key `pydantic_ai.tool.deferral.name`.
- Gate A pass 1: AR28 and NFR29 passed; measurement integrity failed only on the two expected stale-report identity tests.
- The documented pass-2 own-output exemption initially skipped/failed the clean-binding realism test; fixed both collection and binding-call scopes without `--allow-dirty`.
- Final clean-tree suite: `1576 passed, 1 skipped, 7 deselected`; Vitest passed; Playwright passed; `gate_a_passed: true`.

### Demonstrated-red mutation table (retro A1 — required before review)

Re-measured in full at code review (2026-09-05). **23 of 23 mutations redden.** Each row was applied
to real, already-green code, the named guard was run, and the mutation reverted — not asserted from
reading. The pre-review table's first row was **false**: `record.getMessage()` left the whole suite
green, because no test carried a canary on `record.args`. It reddens now only because Decision 10's
class-3 `%`-directive fixture, which had never been written, exists.

| Mutation applied to real code | Guard that should redden | Before | After |
|---|---|---|---|
| Interpolate `record.args` via `record.getMessage()` | C2 injection + adversarial cells | green | RED — 2 cells; `%`-directive canary emitted |
| Emit `str(exc)` into the fallback JSON payload | C2/C3 exception canaries | green | RED |
| Treat third-party loggers as owned | C2 adversarial cell | green | RED |
| Accept every telemetry label key at runtime | C1 runtime key allow-list | green | RED |
| Remove the label value truncation | C1 adversarial cell | green | RED |
| Revert label coercion to `value[:n]` | C1 label type-safety node | green | RED — record silently dropped |
| Reject computed label keys no longer | `unsafe_label_operations` synthetic case | green | RED |
| Remove `hide_parameters=True` from `api/deps.py` | SQLAlchemy engine AST guard | green | RED — **alias path**, not a literal name |
| Remove `hide_parameters=True` from `migrations/env.py` | SQLAlchemy engine AST guard | green | RED — `engine_from_config`, 5th site |
| Return no violations from the literal-template walker | synthetic nonliteral logger case | green | RED |
| Match logger receivers by name only | five logger-spelling evasions | green | RED |
| Restrict the engine guard to bare-name calls | five engine-spelling evasions | green | RED |
| Remove `include_binary_content=False` | two-constructor binary-capture guard | green | RED |
| Remove `repr=False` from `database_url` | seven-credential repr sweep | green | RED |
| Remove `pydantic_ai.tool.deferral.name` from the allow-list | observed-span key allow-list | green | RED |
| Drop span EVENTS from the C4 blob | C4 provider-error cell | green | RED |
| Collapse all 12 matrix cells onto one node | proof-matrix distinctness | green | RED |
| Point a matrix cell at a nonexistent test | proof-matrix existence check | green | RED |
| Ignore the JUnit `skipped` count | generator fail-closed machinery | green | RED |
| Accept an incomplete proof-node set | `write_report` completeness | green | RED |
| Write child pytest output into report failures | failure-detail containment | green | RED |
| Restore alembic `fileConfig`'s `disable_existing_loggers` default | logging-config AST guard | green | RED |
| Drop `__main__` from the owned-logger prefixes | worker-as-process ownership node | green | RED |

### Completion Notes List

- Sanitized application and third-party JSON logs to a closed metadata field set; worker failures now use that boundary.
- Hid SQLAlchemy parameters at all four production construction sites and redacted every credential-bearing settings field.
- Disabled binary trace capture, bounded observed span keys, and bounded telemetry label keys/values.
- Added a 12-node, four-channel × three-fixture-class minimization report and registered its stored and live proofs under NFR29.
- Closed the two Story 5.1 ledger triggers, added three residual-risk entries, and documented the corrected two-pass Gate A procedure.
- Logfire remains planned for Epic 6; no exporter, dependency, migration, API contract, or frontend source change was introduced.

### File List

- `_bmad-output/implementation-artifacts/5-2-prevent-content-and-secret-leaks.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `backend/adapters/postgres/fixture_history.py`
- `backend/adapters/postgres/identity.py`
- `backend/adapters/telemetry/json_logs.py`
- `backend/agent/runtime.py`
- `backend/api/deps.py`
- `backend/evals/content_minimization_report.py`
- `backend/migrations/env.py`  *(added at code review)*
- `backend/scripts/gate_a_checks.py`
- `backend/scripts/gate_a_readiness.py`  *(added at code review)*
- `backend/scripts/seed_planner.py`
- `backend/settings.py`
- `backend/tests/architecture/test_telemetry_boundaries.py`
- `backend/tests/test_content_minimization.py`
- `backend/tests/test_content_minimization_report.py`
- `backend/tests/test_evidence_binding.py`
- `backend/tests/test_gate_a_readiness.py`
- `backend/worker/main.py`
- `docs/CI-SECRETS-CHECKLIST.md`
- `docs/GATE-A-RUNBOOK.md`
- `evidence/story-1.11/gate-a-readiness-report.json`
- `evidence/story-5.2/content-minimization-report.json`

---

## Change Log

| Date | Change |
|---|---|
| 2026-09-04 | Story created at `c0ef358`. Twelve decisions recorded; the log-stream leak and its `hide_parameters` remedy measured empirically at creation rather than inferred. |
| 2026-09-05 | Decision 9 confirmed (register, not emit-and-orphan). Four defects found in the story itself and fixed before dev: the Gate A sequencing resolution covered only trap A and missed the two-pass regeneration forced by `test_gate_a_readiness.py` being its own contributing check; `NFR29_GATES`' exact-ordered-tuple assertion and the paired-live-check enforcement at `test_gate_a_readiness.py:171` were unlisted; and Decision 3's guard, specified by method name, would have been red on arrival against three `argparse.ArgumentParser.error` collisions; and Decision 5's guard, specified by call name, would have gone green while missing `api/deps.py:238` — the API's own engine — because `create_engine` names both SQLAlchemy's factory and the CP-SAT one. Added *Dev Notes → The commit plan*. |
| 2026-09-05 | Implemented content and secret minimization across all four channels, generated and registered evidence, closed ledger triggers, demonstrated nine real-code mutations, and passed the final three-runner Gate A report. |
