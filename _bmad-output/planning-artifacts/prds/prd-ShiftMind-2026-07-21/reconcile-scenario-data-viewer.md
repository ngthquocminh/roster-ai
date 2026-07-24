# Reconciliation — Scenario Data Viewer Update

## Input

Update the existing ShiftMind PRD with a read-only Scenario Data viewer that uses predefined fixtures only, exposes agent-relevant normalized data, is part of Gate A, and is implemented before agent orchestration. Scenario upload and editing remain excluded.

## Reconciliation result

- **Predefined fixtures only:** Captured in FR-22 and reinforced in FR-24, the primary journey, the release suite, and the implementation sequence.
- **Read-only viewer:** Captured in FR-24 with no upload, create, edit, delete, or import action and with a negative mutation-path acceptance test.
- **Agent-relevant normalized data:** FR-24 names the required data groups and requires value/identifier parity with the agent's allow-listed scenario inspection capability for the same fixture version.
- **Gate A:** FR-24 is explicitly included in Gate A, and Scenario Data integrity is a Gate A-blocking metric.
- **Before orchestration:** Gate A and addendum stage 2 require the viewer and its tests to pass before `AgentRuntime` or tool orchestration begins.

## Prior-source fit

The update is consistent with the product brief's requirements for inspectable, traceable scenario facts, fixture-based demonstration data, and no raw-data editing. It is also consistent with the technical research's application-owned data and agent boundaries. The new viewer is a product-scope addition that operationalizes those principles without adding custom scenario management.

## Gaps and conflicts

- No conflict with a recorded decision.
- No unresolved product or scope question.
- Implementation-specific contract placement and sequencing are retained in `addendum.md`; the user-visible capability and acceptance boundary remain in `prd.md`.
