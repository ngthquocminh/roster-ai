# ShiftMind Architecture

ShiftMind is a hexagonal modular monolith: dependencies point inward, and the
domain and application layers do not import web frameworks, persistence
libraries, identity providers, telemetry exporters, or concrete model
providers. Adapters implement the outer boundary; application code owns the
workflow and its policy.

The rule is enforced mechanically rather than by convention: the suites in
`backend/tests/architecture/` sweep the domain and application packages for
forbidden imports, and any exception must be named in `ALLOWED_LEAKS`, which a
companion test asserts still exists and still leaks — so a suppression cannot
outlive the violation it covers. Three ports under `backend/application/ports/`
currently import SQLAlchemy's `Connection` and are recorded there; closing them
is tracked in the deferred-work ledger.

Authority is deliberately divided three ways:

- The model proposes typed intent only.
- Application code owns identity, authorization, policy, versions, approvals,
  state, and audit.
- CP-SAT alone constructs or validates an accepted schedule.

For the reviewer journey and proof links, see [the walkthrough](WALKTHROUGH.md).

The numbered architecture decisions and their invariants are **not restated
here**. They live, normatively, in the
[architecture spine](../_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md),
which carries each decision's adopted or deferred status and is maintained by
the workflows that change the system. It sits under `_bmad-output/` because that
is where it is written and updated, but unlike the planning records around it,
it is normative rather than historical — read it as the source of truth for
architectural intent. A second, hand-maintained copy in `docs/` would only drift
away from it.

The former v0.3/v0.4 design, including the derivation of the CP-SAT model, is
preserved unchanged in [the archive](archive/architecture-v0.4.md).
