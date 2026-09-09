# ShiftMind portfolio walkthrough

ShiftMind demonstrates a governed workforce-planning workflow: the model proposes typed intent, application code owns identity, authorization, policy, versions, approvals, state, and audit, and CP-SAT alone constructs or validates an accepted schedule.

## Run it

From a clean clone, run `docker compose up -d --build`, open `http://localhost:8080`, and sign in through the local fake identity provider. The default deterministic agent is keyless. The complete reproducible proof is `backend/tests/compose_proof.py`.

## Architecture boundary

ShiftMind is a hexagonal modular monolith: dependencies point inward, so domain and application code remain free of framework and concrete-provider types. The adopted invariants are in the [architecture spine](../_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md).

## Wednesday coverage journey — captured 2026-09-09

Captured at commit `bb5b8ef5f744bc3785b3cc731df3392108d150ec` on a host with 16 logical CPUs, using the composed local stack and deterministic runtime.

1. Sign in and select `sample_tiny_input`.
2. Create conversation `83b846e8-eba8-4968-86c9-44da1f97dd16`.
3. Send the request and execute agent run `03e0d1bc-8346-48a2-a1f6-c37300c57745`.
4. Create proposal `73047261-8bd2-417a-b30c-5a179bfb4e93`.
5. Start schedule run `bf53e121-f410-4d6e-a232-9b94f43ba138`.
6. The solver completed and produced candidate version `d7b7273c-3105-4085-a05e-d3542b5f6284` with 76 assignments.
7. Request approval `6bd6d275-d5bf-407c-9ab4-6bf13db86616` and approve it; the binding became `consumed` and promoted that candidate as the baseline.
8. Open the Provenance timeline for the run to connect the request, scenario evidence, draft, run, approval, and promoted version.

The candidate recorded 0 unmet minutes, 1,993 overtime minutes, and total cost 11,549.69. Coverage required/served minutes were Despatch 4,162.45/7,088; Pick 15,929.71/17,314; Putaways 4,104.88/6,592; and Receiving 988.98/656. These are solver metrics, not a conversion of demand volume into time; see the [domain model](DOMAIN-MODEL.md) for the unit boundary.

<!-- behavioral-claims:start -->
The composed journey reaches `solver_completed`, creates and consumes an approval, promotes the candidate baseline, and returns a populated provenance timeline. Anchor: `backend/tests/compose_proof.py::test_one_command_stack_serves_real_oidc_and_worker`.
The evaluation harness is demonstrated by `evidence/story-2.2/evaluation-harness-demonstration.json`. Anchor: `evidence/story-2.2/evaluation-harness-demonstration.json`.
Automated accessibility coverage is recorded in `evidence/story-4.6/state-semantics-and-accessibility.json`. Anchor: `evidence/story-4.6/state-semantics-and-accessibility.json`.
<!-- behavioral-claims:end -->

## Evidence and gates

The [evaluation demonstration](../evidence/story-2.2/evaluation-harness-demonstration.json), [Gate A readiness report](../evidence/story-1.11/gate-a-readiness-report.json), and [automated accessibility evidence](../evidence/story-4.6/state-semantics-and-accessibility.json) are bound artifacts. Gate B's checklist is in [`epics.md`](../_bmad-output/planning-artifacts/epics.md). The aggregate release report is specified as `evidence/epic-5/release-gate-report.json`, but it is an Evaluation/QA-owner step after this story: the dataset currently has 30 cases against its 50-case floor, which requires recorded owner rationale rather than a fabricated report.

## Limitations

### Single-planner scope and self-approval

The planner who requests an approval can decide it. No separation-of-duties rule exists and none is planned at this milestone. Revisit this when activating a second user or during a customer security review.

### Fixture-only source data

The journey uses immutable fixtures. There is no scenario-source mutation command, route, tool, or UI control in this portfolio scope.

### Retention

There is no data-retention or purge policy. Conversations, audit records, snapshots, and local database records have no configured expiry; container logs are bounded only by Docker defaults. Session and approval expiries are workflow lifetimes, not retention settings.

### No hosted deployment

There is no hosted deployment at this milestone; the documented path is the local composed stack.

### Non-customer status

This is a portfolio artifact, not a customer service.

### No enterprise promise

No claim here is a customer promise for latency, availability, recovery, concurrency, or cost. The recorded measurements are local acceptance evidence.
