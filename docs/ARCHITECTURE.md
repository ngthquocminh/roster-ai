# ShiftMind Architecture

ShiftMind is a hexagonal modular monolith: dependencies point inward, and the
domain and application layers do not import web frameworks, persistence
libraries, identity providers, telemetry exporters, or concrete model
providers. Adapters implement the outer boundary; application code owns the
workflow and its policy.

Authority is deliberately divided three ways:

- The model proposes typed intent only.
- Application code owns identity, authorization, policy, versions, approvals,
  state, and audit.
- CP-SAT alone constructs or validates an accepted schedule.

For the reviewer journey and proof links, see [the walkthrough](WALKTHROUGH.md).
For the adopted architecture decisions and invariants, see the
[architecture spine](../_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md).

The former v0.3/v0.4 design, including the derivation of the CP-SAT model, is
preserved unchanged in [the archive](archive/architecture-v0.4.md).
