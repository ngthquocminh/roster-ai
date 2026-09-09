# ShiftMind API

The running application is the API contract. With the composed stack running,
use its OpenAPI interfaces: `/docs` for Swagger UI, `/redoc` for Redoc, and
`/openapi.json` for the machine-readable schema. Do not maintain a second,
hand-written route contract here.

## Approval and provenance semantics

An approval request binds one feasible candidate schedule to its scenario,
policy, and expected resource version. Creating a request requires an
`Idempotency-Key`; a replay returns the existing binding. A decision also
requires an idempotency key and expected resource version. A successful
approval consumes the binding, promotes the candidate schedule version exactly
once, and appends the corresponding audit records. Rejection, expiry, and
staleness are distinct terminal outcomes.

The provenance reader is the authoritative, site-scoped timeline for a
schedule run. It joins committed run, conversation, approval, and audit facts
without recomputing figures. Before/after baseline versions come from the
immutable audit pair, not from the current baseline pointer. A protected or
unknown run returns the same not-found response.

If a frozen baseline cannot be authoritatively read, is for another scenario
version, or has no persisted metrics, the candidate remains readable but its
comparison is unavailable with a literal reason. An unavailable baseline is
never represented as an empty baseline.

## Route inventory

Generated from the running composed application on 2026-09-09 with:

```bash
docker compose exec -T api python -c "from api.main import app; print('\\n'.join(sorted(app.openapi()['paths'])))"
```

| Area | Routes |
|---|---:|
| Versioned planner surface | 40 operations under `/api/v1` |
| Authentication | login, callback, logout, session |
| Planner workflow | scenario catalogue and projections; conversations; proposals; schedule runs; approvals and provenance |
| Local-only/support surface | health, fixtures, fake OIDC, and the compatibility routes still mounted for the local composition |

The generated schema is deliberately the complete route inventory. This page
preserves only semantics that a schema cannot express reliably.
