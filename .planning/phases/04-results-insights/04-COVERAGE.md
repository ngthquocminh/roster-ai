# API Coverage — Phase 04 (Results & Insights)

> Full coverage by default. Opt-outs are explicit, reasoned decisions.

The `api-coverage.verify-pre` gate fired on this phase's planning docs (verb+noun
signals: "wire"+"api" — e.g. "wired to `runQuery.data?.status`", files under
`frontend/src/api/`). This is a false positive against the gate's own stated
intent — those phrases describe consuming this project's own first-party FastAPI
backend, not integrating a third-party API/SDK/service. The one endpoint in this
phase that fronts an LLM (`GET /runs/{run_id}/insights`) does not call any
external AI provider from this phase's own code — that integration
(`LLMProvider` Protocol, provider selection, `backend/llm/`) was built and sealed
in a prior milestone; this phase only adds a thin typed frontend wrapper around
the already-existing backend endpoint, identical in kind to every other
`frontend/src/api/*.ts` wrapper in this project. This matrix documents that
explicitly so the gate resolves.

| capability | decision | reason |
|---|---|---|
| results-endpoint (GET /runs/{run_id}/result) | OPT-OUT | First-party backend endpoint (backend/api/routers/runs.py), wrapped by frontend/src/api/results.ts per the existing scenarios.ts/constraints.ts/runs.ts convention |
| insights-endpoint (GET /runs/{run_id}/insights) | OPT-OUT | First-party backend endpoint; LLM-provider integration (backend/llm/) was sealed in a prior milestone. Thin wrapper only (frontend/src/api/insights.ts), no external AI SDK/key here |
| run-status-endpoint (GET /runs/{run_id}) | OPT-OUT | First-party backend endpoint — added `getRun` to the existing frontend/src/api/runs.ts wrapper (D-12's status probe), same first-party convention as above |
