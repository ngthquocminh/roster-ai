# ShiftMind

ShiftMind is a portfolio implementation of a governed workforce-planning
workflow: a planner proposes a change, the application enforces identity,
authorization, policy, versions, approvals, state, and audit, and CP-SAT alone
constructs the accepted schedule.

Start the complete local system from a clean clone:

```bash
docker compose up -d --build
```

Open `http://localhost:8080` and sign in through the local fake identity
provider. The composed stack uses a keyless deterministic agent model by
default, so this journey needs no provider credential.

For the complete reviewer journey, real-run output, architecture boundary,
evidence, and current limitations, read [the portfolio walkthrough](docs/WALKTHROUGH.md).
For setup, recovery, and configuration details, read [Getting Started](docs/GETTING-STARTED.md).

## Notes

- OIDC sign-in, server-side sessions, CSRF enforcement, site membership, and
  PostgreSQL row-level security protect the versioned planner surface. The local
  fake identity provider is exposed only when `OIDC_PROVIDER=fake`.
- The repository is a portfolio artifact, not a hosted customer service.
