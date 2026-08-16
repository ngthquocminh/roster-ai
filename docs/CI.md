# Continuous Integration

The pipeline lives in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml).
It runs the suites this repo already had; it configures no test framework of its
own. For how to write and run tests, see [`TESTING.md`](TESTING.md).

Everything below exists because of one property of this codebase: **several of
its suites degrade to skips rather than failures when the environment is
wrong.** A naive runner would go green having proved nothing. Read the
[Assertion contract](#assertion-contract) before changing any job.

## Gates

| Job | Command | Baseline enforced |
|---|---|---|
| `backend` | `uv run --frozen pytest` (in `backend/`) | ≥864 passed, ≤1 skipped, ≥7 deselected |
| `backend` | `uv run --frozen pytest tests/test_evidence_convention.py` | ≥48 passed, **0 skipped** |
| `backend-postgres` | `uv run --frozen pytest -m postgres` | ≥45 passed, **0 skipped** |
| `migrations` | `uv run --project backend alembic check` (**from repo root**) | no new upgrade operations |
| `frontend` | `npm run lint` / `typecheck` / `build` / `test` | ≥400 passed, 0 skipped (63 files) |
| `e2e` | `npm run test:e2e` | ≥48 passed, 0 skipped, **0 flaky** |
| `burn-in` | `npx playwright test --retries=0` ×10 | schedule / manual only |

`summary` rolls the five required gates into one status, so branch protection
needs a single required check.

Baselines were measured on `faf22eb` (2026-08-16) with PostgreSQL running.

### Deliberately not run

`pytest -m live` — the seven `@pytest.mark.live` tests call a real LLM
provider. **NFR26** keeps them out of normal CI, and no `GEMINI_API_KEY` or
`OPENROUTER_API_KEY` is set on any job, so the keyless `stub` provider is what
gets exercised.

This is enforced, not assumed. The `backend` job compares the number of
live-marked tests against the number the default run deselects; if someone
removes `addopts = "-m \"not live\""` from `backend/pyproject.toml`, the two
stop matching and the job fails before any test runs.

## Assertion contract

Every suite pipes its output through
[`.github/scripts/assert_counts.py`](../.github/scripts/assert_counts.py),
which parses the runner's own summary line and enforces:

- **a floor on passes** — so adding tests never reddens CI, but a suite that
  silently stopped collecting does;
- **a ceiling on skips** — because in this repo an unexpected skip is the
  failure mode, not a neutral outcome;
- **zero failed / errored / flaky** — `flaky` matters because
  `playwright.config.ts` sets `retries: 2` under CI, which would otherwise let
  an intermittent test report success.

Raise a floor when a suite grows and you want the new tests protected. Never
raise a skip ceiling to make a red build green — that is the exact move these
assertions exist to prevent.

## Environment traps

Five things about this repo are load-bearing for CI and non-obvious. Each is
commented at its use site in `ci.yml`; they are collected here because four of
the five produce a *misleading* symptom.

### 1. `alembic` must be invoked from the repository root

`alembic.ini` sits at the repo root and sets
`script_location = %(here)s/backend/migrations`. Run from `backend/` — pytest's
working directory, and the obvious place to stand — alembic finds no config and
dies with:

```
FAILED: No 'script_location' key found in configuration.
```

That reads like a missing or broken config file. It is not; it is a
working-directory mistake. This misreading previously cost a story, which
synthesized a temporary `alembic.ini` to work around a problem that did not
exist (see the `CORRECTED 2026-08-10` entry in
`_bmad-output/implementation-artifacts/deferred-work.md`).

The `migrations` job therefore has **no** `working-directory: backend`. Do not
add one.

It also runs `alembic upgrade head` before `alembic check`: `check` compares the
models against a live database, and against an empty one it would report the
entire schema as pending.

### 2. The runner must have git

`backend/tests/test_evidence_convention.py`'s `requires_git` guard skips
`test_every_recorded_commit_is_a_real_ancestor_that_touched_code` and
`test_evidence_file_is_fully_bound` when git is unavailable — so a git-less
image sweeps the whole evidence tree green having proved nothing about any
commit binding.

Two defences: an explicit `git --version` / `git rev-parse` step that fails
loudly, and the `0 skipped` ceiling on the standalone evidence-convention run.

### 3. The checkout must have full history

`actions/checkout` clones with `fetch-depth: 1` by default. The evidence audit
resolves each recorded commit with
`git merge-base --is-ancestor <commit> HEAD`
(`backend/scripts/evidence_binding.py:640`). Under a shallow clone those objects
are simply absent and the ancestry assertions **fail on a healthy tree**.

The `backend` job pins `fetch-depth: 0`.

### 4. PostgreSQL absence is a skip, not a failure

`backend/conftest.py::_temporary_postgres_database` bounds its admin connection
to three seconds and then calls
`pytest.skip("PostgreSQL integration service is not available")`.

Two consequences:

- The **default** suite contains 45 `@pytest.mark.postgres` tests. Without the
  service they become 45 skips and the run still exits 0 — hence the
  `postgres:18` service on the `backend` job, not just on `backend-postgres`.
- `backend-postgres` asserts `0 skipped`. Nothing else distinguishes "45 tests
  passed" from "the database was never there".

The service credentials mirror `docker-compose.yml` exactly, which is what
`backend/settings.py` defaults to, so no `ROSTERAI_*_DATABASE_URL` override is
needed.

### 5. Playwright needs the Edge channel installed

`playwright.config.ts` declares two projects: `chromium` and `msedge`
(`channel: "msedge"`). The 48-test baseline is 24 specs across both. GitHub's
`ubuntu-latest` image ships no Edge, so `playwright install --with-deps
chromium` alone fails 24 tests with `Executable doesn't exist`.

The `e2e` job installs `chromium msedge`. Note the browser cache only covers
Playwright's downloaded Chromium — Edge is installed to a system location by
apt on every run.

## Secrets

**None.** See [`CI-SECRETS-CHECKLIST.md`](CI-SECRETS-CHECKLIST.md).

## Reproducing CI locally

There is no `ci-local.sh`; a second copy of these commands would drift from the
workflow. Run them directly, with `docker compose up -d postgres` first:

```bash
# backend gates
cd backend
uv run --frozen pytest tests/test_evidence_convention.py -q   # expect 48 passed, 0 skipped
uv run --frozen pytest -q                                     # expect 864 passed, 1 skipped, 7 deselected
uv run --frozen pytest -m postgres -q                         # expect 45 passed, 0 skipped

# migration gate — from the REPOSITORY ROOT, see trap 1
cd ..
uv run --project backend alembic check

# frontend gates
cd frontend
npm run lint && npm run typecheck && npm run build
npm test                                                      # expect 63 files, 400 passed
npm run test:e2e                                              # expect 48 passed
```

Three CI conditions cannot be reproduced locally: a shallow checkout, a git-less
image, and an absent PostgreSQL service. Those are exactly the ones the
assertions in `assert_counts.py` cover.

## Deliberate omissions

- **No test sharding.** The template default is a four-way matrix. The backend
  suite takes ~53s and would need `pytest-xdist`, which is not a dependency and
  adding one is outside "wire CI around the real suites". The E2E suite takes
  ~2 minutes, less than the per-shard build-and-install overhead, and sharding
  would break the single `48 passed` assertion. Parallelism comes from the six
  jobs running concurrently instead. Revisit when a suite passes ~10 minutes.
- **No external notifications.** Results surface through the GitHub job summary
  and failure artifacts. Wiring Slack or email would mean inventing a secret
  this repo does not have.
- **Burn-in is not on pull requests.** Ten build-and-run cycles is too heavy for
  a PR gate; it runs weekly on Sunday 02:00 UTC and on manual dispatch.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `No 'script_location' key found in configuration` | alembic run from `backend/` instead of the repo root — trap 1 |
| Evidence tests fail on `is not an ancestor of HEAD` | shallow checkout — trap 3 |
| `backend` job reports ~46 skipped | PostgreSQL service did not come up — trap 4 |
| `backend-postgres` reports `45 skipped` and the assert fails | same as above, made attributable |
| `Executable doesn't exist ... msedge` | Edge channel not installed — trap 5 |
| Assert fails with `only N passed, expected at least M` | tests were removed (lower the floor deliberately) or the runner crashed mid-run |
