# API Coverage — Phase 03 (Run Execution & History)

> Full coverage by default. Opt-outs are explicit, reasoned decisions.

The `api-coverage.verify-pre` gate fired on this phase's PLAN.md prose (verb+noun
signals: "wrap"+"endpoints", "wiring"+"api", "wrap"+"api"). This is a false
positive against the gate's own stated intent — those phrases describe wrapping
this project's own first-party FastAPI backend, not integrating a third-party
API/SDK/service. This matrix documents that explicitly so the gate resolves.

| capability | decision | reason |
|---|---|---|
| runs-list-endpoint (GET /scenarios/{id}/runs) | OPT-OUT | First-party backend endpoint, not external — built in this project (backend/api/routers/runs.py), wrapped by frontend/src/api/runs.ts per the existing scenarios.ts/constraints.ts convention |
| runs-trigger-endpoint (POST /scenarios/{id}/runs) | OPT-OUT | Same first-party backend as above; no third-party SDK, OAuth, or webhook involved anywhere in this phase |
