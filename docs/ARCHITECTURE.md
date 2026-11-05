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
outlive the violation it covers. `ALLOWED_LEAKS` is currently empty: the ports
under `backend/application/ports/` type the driver handle as `connection: Any`
rather than importing SQLAlchemy's `Connection`.

Authority is deliberately divided three ways:

- The model proposes typed intent only.
- Application code owns identity, authorization, policy, versions, approvals,
  state, and audit.
- CP-SAT alone constructs or validates an accepted schedule.

For the reviewer journey and proof links, see [the walkthrough](WALKTHROUGH.md).

The numbered architecture decisions (`AD-n`) cited in code comments are kept in
the project's private planning record, not in this repository. This document
and the architecture tests are the public statement of the boundaries those
decisions produced.

The CP-SAT model itself (data pipeline, domain types, variables, constraints and
the lexicographic objective) is described in [SOLVER-MODEL.md](SOLVER-MODEL.md).
