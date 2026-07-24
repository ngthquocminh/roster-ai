---
title: ShiftMind Canonical Requirements Inventory
date: 2026-07-23
status: normative
source: sprint-change-proposal-2026-07-23.md (MQ-4 remediation)
---

# ShiftMind Canonical Requirements Inventory

This is the single canonical requirement register for ShiftMind. All artifacts — PRD, UX design, architecture, epics, stories, and tests — must reference requirements by the IDs below. IDs are frozen: new requirements append (FR25+, NFR36+); no requirement is ever renumbered.

- **Functional requirements (FR1–FR24):** normative text lives in the PRD (`prds/prd-ShiftMind-2026-07-21/prd.md`). The epics document restates them in condensed form; on any divergence the PRD wording governs.
- **Non-functional requirements (NFR1–NFR35):** the numbering below is canonical (it matches `epics.md`). The PRD's unnumbered NFR section defers to this catalogue. Provenance identifies where each requirement originated.
- **UX design requirements (UX-DR1–UX-DR35)** and **architecture requirements (AR1–AR28):** defined normatively in `epics.md` (Requirements Inventory section), sourced from `ux-designs/ux-ShiftMind-2026-07-22/` and `architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` respectively. They are referenced here by pointer and are not duplicated.

Provenance tags: `PRD#n` = nth item of the PRD's NFR section by sequence · `PRD-AR` = PRD Additional Requirements / addendum · `UX` = UX-derived (adopted as normative per the PRD addendum) · `ARCH` = architecture-derived · `SPEC` = canonical spec.

## Non-Functional Requirements

| ID | Requirement (canonical short form) | Provenance |
|---|---|---|
| NFR1 | Tenant-isolation tests permit zero cross-site reads or writes. | PRD#1 |
| NFR2 | Every mutating tool call uses current authorization, expected resource version, idempotency protection, deterministic invariants, and authoritative audit evidence. | PRD#2 |
| NFR3 | Workforce, prompt, schedule, approval, and credential content excluded from external telemetry by default; only allow-listed sanitized metadata leaves the boundary. | PRD#3 |
| NFR4 | Secrets never appear in prompts, browser payloads, audit summaries, logs, traces, or evaluation fixtures. | PRD#4 |
| NFR5 | Prompt-injection tests cover chat and every untrusted data channel introduced by the MVP. | PRD#5 |
| NFR6 | Worker termination, lease expiry, replay, and recovery create zero duplicate effects. | PRD#6 |
| NFR7 | Accepted work remains discoverable after browser, API, stream, or worker interruption. | PRD#7 |
| NFR8 | 100% of operational-baseline promotions require valid parameter- and version-bound approval. | PRD#8 |
| NFR9 | Baseline promotion, schedule versioning, successful authoritative audit, and the resulting persisted event share one consistency boundary. | PRD#9 |
| NFR10 | Model-provider or Logfire failure causes zero product-state corruption and zero authoritative-audit loss; manual and deterministic workflows remain available. | PRD#10 |
| NFR11 | 100% of completed feasible schedules satisfy deterministic hard constraints. | PRD#11 |
| NFR12 | 100% of numerical agent claims pass the grounding evaluator before release. | PRD#12 |
| NFR13 | Infeasible, timed-out, cancelled, failed, and successful outcomes are never represented as equivalent. | PRD#13 |
| NFR14 | Planner locks remain satisfied or the run returns a clear infeasibility diagnosis. | PRD#14 |
| NFR15 | The product records API acknowledgement latency, first-persisted-event latency, end-to-end agent duration, model/tool latency, solver duration, queue age, approval age, token use, and cost per completed task. | PRD#15 |
| NFR16 | Agent and solver budgets are explicit positive application configuration with safe defaults, never chosen by the model. | PRD#16 |
| NFR17 | Public-launch service objectives are set from measured portfolio traffic before accepting a customer; no unsupported enterprise service-level claim. | PRD#17 |
| NFR18 | The primary desktop journey and read-only responsive views meet WCAG 2.2 AA, remain keyboard-operable, use meaningful status text, and announce durable progress/approval state. | PRD#18 + UX |
| NFR19 | Review, Run optimization, and Approve as baseline remain distinct in language, control, consequence, and visual treatment. | PRD#19 |
| NFR20 | 200% zoom, text-spacing changes, and reduced-motion preferences must not hide controls, create page-level horizontal scrolling, or remove status meaning. | UX |
| NFR21 | Every environment is reproducible from reviewed infrastructure code and immutable application images. | PRD#20 |
| NFR22 | Every agent run is searchable by one stable run identifier across product records, audit, operational logs, and traces, without high-cardinality IDs as metric labels. | PRD#21 + ARCH |
| NFR23 | An unhealthy AWS release is recoverable to the prior schema-compatible image through a tested rollback procedure. | PRD#22 |
| NFR24 | Automated RDS backups, a demonstrated restore drill, and documented recovery limitations are required for the portfolio environment. | ARCH |
| NFR25 | AWS cost, queue health, lease expiry, budget cutoffs, tool/guardrail denials, approval age/outcomes, solver duration/failure, evaluation regressions, audit-write failure, model failure, and telemetry-export health are observable and alertable. | PRD#23 |
| NFR26 | Normal CI is deterministic-first; live-provider tests are explicit, gated, budgeted, and never the sole release evidence. | ARCH/SPEC |
| NFR27 | Every evaluation report binds dataset, evaluator, model, prompt, tool, policy, application, scenario, solver, code, and image versions. | PRD-AR/SPEC |
| NFR28 | Initial golden dataset: ≥50 versioned cases, ≥4 per allowed capability, ≥10 consequential/prohibited cases; ≥90% overall tool routing and 100% consequential/prohibited routing. | PRD-AR |
| NFR29 | Any regression in authorization, approval, isolation, hard constraints, grounding, idempotency, authoritative audit, viewer parity, recovery, accessibility, backup/restore, or rollback blocks release regardless of aggregate helpfulness. | PRD-AR |
| NFR30 | Product data and authoritative audit remain in ShiftMind-controlled persistence; external providers receive only the minimum explicitly configured content. | PRD-AR/ARCH |
| NFR31 | Successful mutations write audit evidence in the business transaction where possible; denied and failed consequential attempts are recorded reliably and separately. | PRD-AR/ARCH |
| NFR32 | Audit captures actor/site, request/run/tool/approval/job identifiers, action and policy outcome, safe summaries or hashes, before/after versions, software/model/prompt/tool/policy versions, and immutable evidence references. | PRD-AR |
| NFR33 | Audit access is site-scoped; the normal application path cannot update or delete audit events. | PRD-AR |
| NFR34 | The portfolio documents current retention settings and limitations without implying a customer deletion, residency, compliance, or regulatory-WORM policy. | PRD-AR |
| NFR35 | Internal demonstration thresholds (non-SLO, per NFR17), **final as of 2026-07-23**: initial Scenario Data group-window load ≤ 2 s; exact evidence-target resolution ≤ 2 s; first persisted run event after acknowledgement ≤ 5 s; SSE reconnect replay to current state ≤ 5 s. Measured under the protocol below. These are internal acceptance thresholds, never customer service-level objectives. | NEW (readiness report 2026-07-23) |

### NFR35 measurement protocol (normative)

The thresholds above are meaningless without a fixed measurement method, so this protocol is part of the requirement. A story claiming NFR35 acceptance must record its measured values as release evidence; a miss blocks acceptance of that story.

| Parameter | Value |
|---|---|
| Fixture scale | The largest Gate A predefined fixture, at its full committed size. Thresholds are not measured against a reduced fixture. |
| Environment | The CI reference runner or an equivalent local developer machine, single API task and single worker, documented in the evidence record. Not the AWS hosted environment — hosted latency is out of scope until measured traffic exists (NFR17). |
| Warm/cold | Warm process and warm database connection pool. One discarded warm-up request precedes measurement. |
| Runs and rule | Three consecutive runs; **every** run must meet the threshold. This is a deterministic all-runs rule, not a percentile, because three samples cannot support a percentile claim. |
| Clock boundaries | Server-side measures (Scenario Data load, evidence resolution) run from request receipt to response completion, excluding network transit and browser render. Client-observed measures (first persisted run event, SSE replay) run from API acknowledgement or reconnect request receipt to client receipt of the relevant event. |
| Evidence format | A dated record naming the fixture version, environment, per-run measured values in milliseconds, threshold, pass/fail, and the code/image versions under test, bound like any other evaluation report (NFR27). |

Allocation to stories and architecture: Story 1.4 (group-window load), Story 1.5 (evidence-target resolution), Story 3.5 (first persisted run event), Story 2.4 (SSE reconnect replay); architecture contract AD-26 in `ARCHITECTURE-SPINE.md`.

## Functional Requirements (pointer)

FR1–FR24 as defined in `prds/prd-ShiftMind-2026-07-21/prd.md` (Product Requirements). Epic-level coverage: see the FR Coverage Map in `epics.md` (FR13 has two independently acceptable ownership boundaries: Story 3.5 owns optimization progress/recovery behavior, while Story 4.1 owns approval-required state, presentation, and replay; FR23 is delivered by Epic 2, Story 2.6, beside the capability registry it governs).
