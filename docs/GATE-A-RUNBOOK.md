# Gate A Runbook

Operational procedures for the Gate A foundation: the one-way brownfield
cutover, the legacy-route live flag, and regenerating the readiness report.

Gate A is the AR28 boundary. Epic 2 (AgentRuntime and agent tools) may not
begin until `evidence/story-1.11/gate-a-readiness-report.json` records
`gate_a_passed: true`.

See also [`EVIDENCE-CONVENTION.md`](EVIDENCE-CONVENTION.md) for how every
evidence file must be produced.

**Manual assistive-technology (screen-reader) verification is out of scope**
for this portfolio MVP — a deliberate, recorded descope decision (no real
users exist yet; see the product brief and `EXPERIENCE.md`'s Accessibility
Floor). Accessibility is proven by the automated `accessibility_component_layer`
and `accessibility_browser_layer` checks below; there is no manual pass in
this runbook.

### What "read-only" means once drafts are writable (stated 2026-08-18)

Gate A's read-only invariant has always been about **what may change**, never
about the count of HTTP verbs on the app. Stated positively:

> **No write path mutates governed scenario data or the operational baseline
> pointer.** The `scenario`, `scenario_version` and fixture-history rows a
> Gate A viewer reads are immutable after import; the baseline pointer and
> schedule version move only through an explicit, out-of-band operation that
> does not exist yet.

A proposal is **new state, not a mutation of the scenario it cites**. Story 3.1
persists `ProposalV1` into its own SCHEDULING-aggregate tables and writes
nothing to `scenario` or `scenario_version`; the draft cites a
`scenario_version_id` and goes stale when a newer one appears, which is the
opposite of mutating it. So "the API grew a POST" is not, on its own, a Gate A
regression — and a guard phrased as "no POST anywhere" would report one.

Approved write paths, each with the reason it does not touch governed data:

| Path | Why it is allowed |
|------|-------------------|
| `POST /api/v1/auth/logout` | Session lifecycle. Touches identity storage only. |
| `POST /api/v1/conversations` | Story 2.3 conversation aggregate. |
| `POST /api/v1/conversations/{id}/messages` | Appends a turn. The turn *reads* the pinned projection and never writes it. |
| `POST /api/v1/conversations/{id}/agent-runs/{id}/execute` | Advances an agent run; writes run state and, through `finalize_agent_run`, the proposal aggregate. |
| `POST /api/v1/proposals/{id}/revisions` | Appends a new proposal version. Governed scenario rows untouched; the cited `scenario_version_id` is a foreign key, not a target. |
| `POST /api/v1/proposals/{id}/rejection` | Terminal transition on the proposal aggregate only. |
| `POST /api/v1/schedule-runs` | Creates an immutable run snapshot, queued schedule-run aggregate, workflow job, and run event; governed scenario rows and the baseline pointer remain untouched. |
| `POST /api/v1/schedule-runs/{id}/cancellation` | Transitions the schedule-run aggregate and its workflow cancellation carrier; governed scenario data and the baseline pointer remain untouched. |

Before deploying the first release that exposes `POST /api/v1/schedule-runs`,
drain every pre-existing non-terminal schedule run (`solver_queued`,
`solver_running`, or `cancellation_requested`) before applying the job-queue
upgrade. A pre-upgrade run has no `workflow.job_queue` row and cannot be safely
backfilled because no real lease epoch or attempt exists to assign it. Resume
run creation only after the upgrade completes and the drain query returns zero.

That table is enforced, in two independent steps. A new write route turns
`test_gate_a_write_surface_is_exactly_the_approved_paths` red, because it
derives the live list from the OpenAPI document and compares it against its own
literal. Appending a tuple to that literal is **not** enough to get back to
green: `test_runbook_records_every_versioned_write_path` then reads this file
and fails until the route is recorded here too.

It matches on path shape, not parameter names, and scans the whole document
rather than parsing the table — so `{id}` versus `{proposal_id}` is fine, and
reformatting this table into a list will not break it. What it cannot check is
whether the reason you write beside a path is a good one. That is a reviewer's
job; the test only guarantees you had to come here and write something.

Every route in that table is authenticated and CSRF-guarded — that part is
enforced centrally by `enforce_versioned_session_and_csrf` for the whole
`/api/v1` surface, and asserted per-route by the parametrized denial tests.
**Site scoping is not uniform**, and the differences are deliberate:

- `auth/logout` resolves no session dependency and no site context. It acts on
  the session cookie itself; there is no site-scoped row to protect.
- `agent-runs/{id}/execute` uses `get_site_context_opener`, not
  `get_site_context`, because it opens the RLS-scoped connection inside the
  background run rather than per-request.
- The two proposal write routes use `get_site_context` directly, which is what
  `test_proposal_write_routes_resolve_site_context_and_session` asserts.

### Legacy SQLite write routes are NOT part of that surface

`POST /scenarios`, `POST /scenarios/{id}/runs` and `POST /constraints` still
exist outside `/api/v1`. They are unauthenticated and site-unaware, and are held
offline by `refuse_legacy_routes_during_gate_a` — a **filesystem-flag** check, not
an authorization check. It fails closed on error, but an environment where the
flag path is simply absent serves them. That is an operational fact about a
deployment, not a property of the code, which is why it is section 2's live-flag
procedure and not a test. Do not read the `/api/v1` write-surface test as a
statement about these three.

Proposals are **created** inside the conversation turn (`finalize_agent_run`),
not by an HTTP create route — there is deliberately no `POST /api/v1/proposals`.

Authentication and CSRF are the property to re-assert when a future story adds a
write path — not the absence of writes.

Note there is **no application-level "viewer" role**. Authorization is session +
site membership + row-level security; `role` in this codebase means a PostgreSQL
role (see `backend/tests/test_identity_role_boundaries.py`).

---

## 1. The one-way cutover

> **Do not run the real cutover against a development checkout.** It writes a
> persistent maintenance flag that takes the legacy `/scenarios`, `/runs` and
> `/constraints` routes offline, which breaks the 61 tests that depend on those
> routes being reachable. Story 1.9 recorded this explicitly: proving the
> *mechanism* (done, with isolated settings) and performing the *operation*
> against a real environment are two different things. If you are ever tempted
> to "just run the cutover so a test passes", the test is targeting the wrong
> environment.

AR25/AD-25 make this a one-way brownfield cutover, performed in an offline
maintenance window.

1. **Disable supervisor auto-restart**, or scale the API service to zero.
2. **Stop the running `uvicorn api.main:app` process and wait for it to fully
   exit.** Process termination is the authoritative worker-drain boundary.
   `_drain_worker_pool()` in the script only observes `run_service._pool`
   *within the script's own process* — it is a defensive check for
   same-process/test invocation, never a substitute for this step. There is no
   in-process admin trigger, because no authenticated admin model exists yet.
3. **Run the cutover:**
   ```bash
   cd backend
   uv run --frozen python scripts/gate_a_cutover.py
   ```
   In order it: writes the persistent maintenance flag, drains the in-process
   pool, snapshots the legacy SQLite database next to the original as
   `rosterai.pre-gate-a-<timestamp>.db`, ensures the `ShiftMind / Seeded Site`
   site exists, and imports both governed fixtures with RFC 8785 checksums.
4. **Validate the import**, then restart the application.

Old SQLite scenarios and runs stay offline afterwards — readable only through
the snapshot file. They are deliberately not migrated; fabricating governed
history for them would defeat the point of the fixture lineage.

### Seeding a local environment without cutting over

For local work you usually want the governed fixtures and a planner user
*without* the maintenance flag. Import through the adapter directly:

```bash
cd backend
uv run --frozen python -c "
import sys; sys.path.insert(0, '.')
import json
from adapters.postgres.fixture_history import PostgresFixtureHistoryAdapter
from scripts.gate_a_cutover import default_fixtures
from settings import default_settings

settings = default_settings()
adapter = PostgresFixtureHistoryAdapter(settings.provisioning_database_url)
site_id = adapter.ensure_seed_site('ShiftMind', 'Seeded Site')
for spec in default_fixtures():
    payload = json.loads(spec.path.read_text(encoding='utf-8'))
    adapter.import_fixture(
        site_id=site_id, fixture_id=spec.fixture_id, version=spec.version,
        payload=payload, source_package='predefined-fixtures',
        source_path=spec.path.name,
    )
"
```

Then provision a planner identity:

```bash
SHIFTMIND_SEED_PLANNER_SUBJECT=local-planner \
SHIFTMIND_SEED_PLANNER_EMAIL=you@example.com \
  uv run --frozen python scripts/seed_planner.py
```

Prerequisites: Docker PostgreSQL 18 up (`docker compose up -d postgres`) and
`uv run --frozen alembic upgrade head` applied.

---

## 2. The legacy-route live flag

Story 1.9 proved the *mechanism* and explicitly left the *live state* to this
runbook (`evidence/story-1.9/…json` records
`"legacy_route_live_flag_state": "not verified by this story — operational
fact, owned by Story 1.11 / release runbook"`).

**Mechanism.** `refuse_legacy_routes_during_gate_a` in `backend/api/main.py`
refuses every method on the `/scenarios`, `/runs` and `/constraints` prefixes
once the flag path exists. `/health` and `/fixtures` stay available — they are
not SQLite-backed. `_gate_a_flag_is_set()` uses `.exists()` and fails *closed*
on any `OSError`, so a permission problem is treated as "maintenance active"
rather than silently permitting mutations.

**How to check the live state** of a given environment:

```bash
# 1. What path is the flag configured at?
cd backend
uv run --frozen python -c "
import sys; sys.path.insert(0, '.')
from settings import default_settings
print(default_settings().maintenance_flag_path)
"

# 2. Does it exist in the target environment?
#    (local)
test -e "$(...)" && echo "cutover ACTIVE" || echo "cutover NOT active"

# 3. Confirm behaviourally against the running API:
curl -s -o /dev/null -w '%{http_code}\n' "$API_ORIGIN/scenarios"
#   503 (or refusal) -> flag is set, legacy routes are offline
#   200              -> flag is NOT set, legacy routes are still live
```

The environment variable is `ROSTERAI_MAINTENANCE_FLAG`; it defaults to
`var/gate-a-maintenance` relative to `backend/`.

**Current recorded state (2026-08-07): not applicable — no deployed
environment exists.** There is no `.github/`, no image pipeline and no hosted
API; deployment is Epic 5 (Stories 5.5–5.7). On a local development checkout
the flag is deliberately absent, which is why the 61 legacy-route tests still
pass. This is an honest "not yet applicable", not a pass.

---

## 3. Regenerating the readiness report

The ordering is the whole point — see
[`EVIDENCE-CONVENTION.md`](EVIDENCE-CONVENTION.md).

```bash
# 0. Commit the code. The tree must be clean.
git status --porcelain      # must be empty

# 1. Run the three suites, writing JUnit XML.
cd backend
uv run --frozen pytest --junitxml=../_bmad-output/test-artifacts/gate-a/pytest.xml

cd ../frontend
npx vitest run --reporter=junit \
  --outputFile=../_bmad-output/test-artifacts/gate-a/vitest.xml
PLAYWRIGHT_JUNIT_OUTPUT_NAME=../_bmad-output/test-artifacts/gate-a/playwright.xml \
  npx playwright test --reporter=junit
# PowerShell equivalent of that last one (the VAR=value prefix is POSIX-only):
#   $env:PLAYWRIGHT_JUNIT_OUTPUT_NAME = "../_bmad-output/test-artifacts/gate-a/playwright.xml"
#   npx playwright test --reporter=junit

# 2. Generate.
cd ../backend
uv run --frozen python scripts/gate_a_readiness.py \
  --pytest-xml     ../_bmad-output/test-artifacts/gate-a/pytest.xml \
  --vitest-xml     ../_bmad-output/test-artifacts/gate-a/vitest.xml \
  --playwright-xml ../_bmad-output/test-artifacts/gate-a/playwright.xml

# 3. Commit the report on its own.
```

**Docker PostgreSQL 18 must be up.** `postgres`-marked tests skip *cleanly*
without it, and a skip is treated as not proven — so running the gate without
the database blocks it rather than producing a false green. That is deliberate.

`--reporter=junit` must be passed on the Playwright **command line only**;
`playwright.config.ts` pins `reporter: "list"` and that committed default must
not change.

### If Playwright's JUnit reporter will not exit (Windows)

Playwright's own aggregating JUnit reporter completes every browser case on
this Windows host but does not exit, so step 1's Playwright command hangs after
the last test. Use the committed streaming reporter instead — it writes the XML
after each finished case rather than once at teardown:

```bash
cd frontend
PLAYWRIGHT_JUNIT_OUTPUT_FILE=../_bmad-output/test-artifacts/gate-a/playwright.xml \
  npx playwright test --reporter=./e2e/support/streaming-junit-reporter.mjs
# PowerShell:
#   $env:PLAYWRIGHT_JUNIT_OUTPUT_FILE = "../_bmad-output/test-artifacts/gate-a/playwright.xml"
#   npx playwright test --reporter=./e2e/support/streaming-junit-reporter.mjs
```

Note the different variable: the built-in reporter reads
`PLAYWRIGHT_JUNIT_OUTPUT_NAME`, the streaming one reads
`PLAYWRIGHT_JUNIT_OUTPUT_FILE`. It lives in the repository (not in the
gitignored artifacts directory) precisely so a `playwright.xml` bound into
`evidence/` can be re-derived by anyone.

**Known limitation** — tracked in `deferred-work.md`: it has no `onEnd`
finalisation and hard-codes `errors="0"`, so a run that dies midway produces a
file that is accurate about the cases that finished and silent about the ones
that never started. Cross-check the case count against a plain `list` run before
binding the result.

The JUnit XML is written to `_bmad-output/test-artifacts/gate-a/` and is
gitignored: it is regenerable, noisy, and the report already carries the
summarised result. It must never be written into `evidence/`.

Because it is gitignored, the report pins it by **sha256** rather than by
existence — an existence check on an uncommitted artifact would unbind the
report on every machine but the one that generated it. The report also records
each run's own start timestamp and blocks if it predates the commit being bound,
so a stale XML left lying in the directory cannot be read as a fresh result.

## 4. Regenerating the Story 1.4/1.5/1.9/1.10 evidence

Separate script, same ordering rule. Use it whenever those files need
rebinding — after a re-measurement changes one of their recorded results, for
instance.

```bash
# 0. Commit the code. The tree must be clean.
git status --porcelain      # must be empty

# 1. Capture a postgres run; 1.4 and 1.5 read their NFR35 measurements from it.
cd backend
uv run --frozen pytest -m postgres -s -q | tee ../_bmad-output/test-artifacts/gate-a/postgres.log

# 2. Rebind all four, in one pass.
uv run --frozen python scripts/regenerate_evidence.py \
  --measurements ../_bmad-output/test-artifacts/gate-a/postgres.log

# 3. Commit the evidence on its own.
```

Omitting `--measurements` rewrites the bindings only and leaves every recorded
measurement untouched, which is what you want when nothing was re-measured.

The script resolves all four binding sets **before** writing any file: writing
the first one dirties the tree, and `resolve_bindings()` refuses a dirty tree.
It exits non-zero if any file comes out unbound, and it preserves every semantic
field — the story-specific guards (`test_scenario_projection.py`,
`test_gate_a_mutation_audit.py`) assert those and must stay green.

### Reading the exit code

The script exits **non-zero** on any check that is missing, unbound, skipped or
failing. `gate_a_passed: false` with a populated `blocking[]` naming each
offending check is a valid, honest outcome — it blocks Epic 2, not the story
that produced it.

Do not tune the registry, relax a check or soften a recorded result to reach
`true`. The entire value of a gate is that it can say no.

### Adding a check

Add an entry to `GATE_A_CHECKS` in `backend/scripts/gate_a_checks.py` naming
its story, its invariant, and its proving artifact (an evidence path or a set
of test files). Ingestion fails loudly if a declared test file produces no
cases, so a renamed or deleted test surfaces immediately instead of quietly
decaying into a check that no longer runs.
