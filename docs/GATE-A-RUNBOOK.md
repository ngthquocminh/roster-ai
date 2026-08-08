# Gate A Runbook

Operational procedures for the Gate A foundation: the one-way brownfield
cutover, the legacy-route live flag, the manual screen-reader pass, and
regenerating the readiness report.

Gate A is the AR28 boundary. Epic 2 (AgentRuntime and agent tools) may not
begin until `evidence/story-1.11/gate-a-readiness-report.json` records
`gate_a_passed: true`.

See also [`EVIDENCE-CONVENTION.md`](EVIDENCE-CONVENTION.md) for how every
evidence file must be produced.

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

## 3. The manual NVDA screen-reader pass

Automated tooling covers roughly a third of WCAG issues. The manual pass is the
one check the automated suite cannot substitute for.

> **Never infer this pass from axe output or from reading the source.** If
> speech output cannot be genuinely observed, record `not executed` with the
> reason and the date.

### Setup

1. Install [NVDA](https://www.nvaccess.org) (free). The support matrix names
   NVDA on Windows; Narrator or JAWS is a spec change, not a substitution.
2. Start NVDA, then open **Speech Viewer**: `Insert+N` → Tools → Speech Viewer.
   Every utterance renders as readable text, which is what makes the result
   observable and recordable rather than a claim.
3. Optionally start NVDA with `--log-level=DEBUG` for a secondary record at
   `%TEMP%\nvda.log`.

### Opening the Gate A surface

A plain `npm run preview` cannot be signed in by hand: the OIDC issuer is a
non-routable fake (`http://shiftmind.test/oidc`) and sessions live in the API
process rather than in PostgreSQL. Use the manual harness, which serves the
production build and supplies the same deterministic API stubs the automated
accessibility layer uses:

**Run this from a native Windows shell — PowerShell, cmd, or Git Bash for
Windows. Not WSL.** NVDA is a Windows application and can only read a Windows
browser process; a browser launched from WSL is a Linux process that NVDA
cannot see at all.

PowerShell (the env assignment persists for the session, so set it once and run
both browsers):

```powershell
cd frontend
$env:NVDA_MANUAL = "1"

npx playwright test e2e/manual-nvda.spec.ts --project=chromium --headed
npx playwright test e2e/manual-nvda.spec.ts --project=msedge --headed
```

Git Bash:

```bash
cd frontend

NVDA_MANUAL=1 npx playwright test e2e/manual-nvda.spec.ts \
  --project=chromium --headed
NVDA_MANUAL=1 npx playwright test e2e/manual-nvda.spec.ts \
  --project=msedge --headed
```

cmd: `set NVDA_MANUAL=1 && npx playwright test e2e/manual-nvda.spec.ts --project=chromium --headed`

It builds, serves at `http://localhost:4173`, opens a real browser window and
parks. Drive it by keyboard; press **Resume** in the Playwright Inspector to
close. Without `NVDA_MANUAL` the file registers no test at all, so it never
appears in `npm run test:e2e` — not even as a skip.

### Recording the result

Fill in the observed-utterance column for **every** row of
[`ACCESSIBILITY-NVDA-CHECKLIST.md`](ACCESSIBILITY-NVDA-CHECKLIST.md), in both
Chrome and Edge:

| Row | What to do |
|---|---|
| Heading announcement on route change | Open a catalogue scenario, then activate Scenario Data |
| Table caption + column-header association | Enter each tabular group; navigate caption → data cells |
| Sort-state change | Focus a sortable header, activate twice |
| Row position after page change | Activate Next on a multi-page group |
| Identifier copy | Activate a Copy control |
| Evidence-reveal explanation | Follow an evidence link targeting a hidden field |
| Disabled Results explanation | Tab through the workspace tabs to Results |

Scope is Gate A only: the fixture catalogue, the workspace shell and Scenario
Data. Chat, Runs and Results are route placeholders owned by Stories 4.6–4.9.

**Expect real findings.** `ScenarioWorkspace.tsx:22-30` documents a prior bug
where two focus calls interrupted a screen reader mid-announcement — exactly
the class of defect only this pass detects. A finding is an honest result, not
a failure; fix it if it is in Gate A scope and record it.

---

## 4. Regenerating the readiness report

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

The JUnit XML is written to `_bmad-output/test-artifacts/gate-a/` and is
gitignored: it is regenerable, noisy, and the report already carries the
summarised result. It must never be written into `evidence/`.

Because it is gitignored, the report pins it by **sha256** rather than by
existence — an existence check on an uncommitted artifact would unbind the
report on every machine but the one that generated it. The report also records
each run's own start timestamp and blocks if it predates the commit being bound,
so a stale XML left lying in the directory cannot be read as a fresh result.

## 5. Regenerating the Story 1.4/1.5/1.9/1.10 evidence

Separate script, same ordering rule. Use it whenever those files need rebinding
— after the NVDA pass lands, for instance, which changes Story 1.10's recorded
result.

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
