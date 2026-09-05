# CI Secrets Checklist

## Required secrets: none

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs end to end on a
fresh fork with **no repository secrets configured**. Nothing needs to be set
before the first run.

This is a property of the design, not an accident:

| Dependency | How CI satisfies it without a secret |
|---|---|
| LLM provider | `backend/llm/base.py::create_provider` resolves the keyless `stub` provider by default (NFR26, AD-16) |
| OIDC / sign-in | `backend/adapters/oidc/fake.py` — a local double that signs its own tokens and serves its own discovery/JWKS in-process |
| PostgreSQL | An ephemeral `postgres:18` service container using the same `rosterai:rosterai` credentials as `docker-compose.yml`, which is what `backend/settings.py` already defaults to |

## Secrets that must NOT be added

`GEMINI_API_KEY` and `OPENROUTER_API_KEY` must not be configured as repository
secrets or exposed to any job in this workflow.

**NFR26** keeps live-provider calls out of normal CI. The seven
`@pytest.mark.live` tests are excluded by `addopts = "-m \"not live\""` in
`backend/pyproject.toml`, and the `backend` job asserts that exclusion is still
in force before running anything. Adding the keys would not by itself run those
tests, but it would remove the last barrier if the marker default were ever
dropped, and it puts a live credential on every pull-request build — including
builds from forks.

If a live-provider suite is ever needed in CI, it belongs in a **separate,
explicitly gated and budgeted workflow** — per NFR26 its result is
non-authoritative and can never satisfy a release gate on its own.

## Permissions

The workflow declares `permissions: contents: read` at the top level. It does
not write to the repository, publish packages, comment on pull requests, or use
the `GITHUB_TOKEN` for anything beyond checkout. If a future job needs more,
grant it at the **job** level rather than widening the top-level block.

## Review checklist

Before merging a change to `.github/workflows/ci.yml`:

- [ ] No credential, token, connection string, or key is hard-coded
- [ ] No new `secrets.*` reference was introduced
- [ ] `permissions:` was not widened at the top level
- [ ] No `${{ inputs.* }}` or `${{ github.event.* }}` value is interpolated
      directly into a `run:` block — route it through `env:` and reference it
      as `"$VAR"` (these are user-controllable and are a script-injection vector)
- [ ] Uploaded artifacts contain only test logs and Playwright traces, no
      environment dumps
- [ ] Story 5.2 minimization canaries remain synthetic placeholders and have
      not been replaced with real provider, database, OIDC, or runtime secrets
- [ ] Artifact `retention-days` is set (30) rather than left to the default
