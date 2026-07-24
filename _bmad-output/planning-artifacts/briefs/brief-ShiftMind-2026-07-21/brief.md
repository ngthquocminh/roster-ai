---
title: "Product Brief: ShiftMind Agentic Scheduling MVP"
status: ready-for-review
created: 2026-07-21
updated: 2026-07-21
---

# Product Brief: ShiftMind Agentic Scheduling MVP

## Executive Summary

ShiftMind is an agentic workforce-scheduling assistant for distribution centres (DCs). A planner describes an operational goal in natural language; the assistant investigates, proposes a safe course of action, invokes typed tools, runs an OR-Tools CP-SAT optimization model, and explains the resulting coverage and cost trade-offs. The language model interprets and orchestrates. It does not invent the schedule: the deterministic optimizer remains the scheduling authority.

The immediate objective is a robust AI Engineer portfolio MVP that makes its engineering visible: multi-turn tool use, grounded reasoning, human approval, asynchronous execution, deterministic tests, failure isolation, and a clean boundary between probabilistic AI and deterministic optimization. Its honest distinction is not a novel category or proprietary model; it is an inspectable, DC-specific reference architecture showing how to integrate an agent with an optimizer safely. The same ownership and site boundaries can later support a manager registering an organization and its DC sites, inviting users, and operating isolated workspaces.

## Why This Exists

DC scheduling is iterative. Planners interpret demand, qualifications, availability, labour constraints, coverage, and cost, then adjust assumptions and compare results. Conventional interfaces force them to translate operational intent into forms, solver parameters, or manual data edits. Generic chat is unsafe when it can mutate schedules without validation or explain results using ungrounded numbers.

ShiftMind provides one conversational control surface while preserving deterministic scheduling and explicit human authority.

## Primary User and Experience

The MVP serves one authenticated planner working at one DC site through the existing web application. The planner understands operations but should not need to manipulate solver code or raw JSON.

A representative workflow is:

1. The planner asks why outbound coverage is weak on Wednesday.
2. The agent retrieves the relevant run, demand, schedule, and qualification facts.
3. It explains the cause using values grounded in stored results.
4. The planner asks it to keep a worker off a task and reduce overtime.
5. The agent resolves the named entities, previews the proposed actions and expected limitations, and asks for confirmation.
6. After confirmation, it applies the change, starts an asynchronous solve, and continues the conversation when the run finishes.
7. It compares the new run with the baseline and explains what improved, what regressed, and why.

## Product Principles

- **Agentic, not merely conversational.** The assistant investigates, selects tools, observes results, and completes bounded multi-step tasks.
- **Optimization remains authoritative.** The LLM interprets intent and communicates results; CP-SAT constructs the schedule.
- **Trust boundaries are server-enforced.** Model output is untrusted, tool arguments are validated, and user/site identity never comes from model-generated values.
- **Human control matches consequence.** Read-only investigation may execute automatically. [ASSUMPTION] Schedule-affecting changes require a preview and explicit confirmation.
- **Every action is explainable and auditable.** The system records the user request, proposed tool call, approval, execution result, and affected run.
- **Failures remain contained.** An LLM or insight failure cannot corrupt a scenario or invalidate a completed solver run.
- **Portfolio depth over feature breadth.** One polished end-to-end agent workflow is more valuable than superficial SaaS administration.

## Existing Foundation

ShiftMind already ships a React/TypeScript web UI, FastAPI backend, SQLite persistence, asynchronous solve lifecycle, provider-neutral LLM adapters, five validated natural-language scheduling overrides, grounded insight generation, and a CP-SAT engine that optimizes unmet demand before cost. The portfolio MVP extends this working vertical slice rather than rebuilding it.

The principal gap is that the current LLM layer is stateless and task-specific. It can parse a constraint or generate an insight, but it cannot yet retain conversations, choose among a general tool set, handle tool results, pause for approval, or resume after a long-running solve.

## MVP Scope

The portfolio MVP includes:

- one authenticated planner and one site-scoped DC workspace;
- persistent conversations, messages, and agent-turn state;
- an application-owned agent orchestrator and provider-neutral conversational model interface;
- a small typed tool registry covering schedule inspection, workforce lookup, constraint preview/application, run execution, and run comparison;
- automatic read-only investigation and explicit confirmation before schedule mutations;
- asynchronous solve continuation with clear pending, completed, and failed states;
- immutable run input and override snapshots for reproducible comparisons;
- append-only audit events for agent proposals, confirmations, and executions;
- grounded explanations that cite stored schedule metrics rather than model memory;
- deterministic, network-free agent tests plus a small gated live-provider test suite;
- one polished, repeatable demonstration scenario and architecture documentation.

Explicitly out of scope:

- self-service organization registration and invitations;
- multiple active users and full manager/planner/viewer administration;
- billing, subscriptions, quotas, and customer support tooling;
- distributed job infrastructure, autoscaling, and production SRE maturity;
- autonomous schedule publishing or destructive actions without confirmation;
- support for every rule required by a production DC scheduling model.

## Success Criteria

The MVP is successful when:

- a fresh reviewer can complete the representative planner workflow through chat without editing forms or raw data;
- the agent correctly performs a bounded multi-tool task and resumes after an asynchronous solve;
- no schedule mutation occurs without the configured confirmation policy;
- tool calls are permission-checked, validated, site-scoped, and auditable;
- runs are reproducible from immutable snapshots, and explanations contain only values traceable to the relevant run or scenario;
- default automated tests do not require access to a live model API and cover success, clarification, rejection, approval, stale-state, timeout, and provider-failure paths;
- an agent evaluation set measures tool selection, argument extraction, grounding, authorization refusal, and bounded multi-step completion;
- the repository contains a concise architecture narrative and a credible SaaS migration path;
- the demonstration clearly communicates the project's AI-engineering depth within an interview-length walkthrough.

## Future Path

After the portfolio MVP, ShiftMind can add organizations with multiple DC sites, manager-led onboarding, invitations, planner/viewer roles, stronger tenant isolation, durable job workers, PostgreSQL, observability, quotas, and deployment automation. [ASSUMPTION] SQLite and the local worker may remain in the MVP if site scoping, run snapshots, and migration boundaries are implemented cleanly. Commercial validation with real planners and greater scheduling-model fidelity are prerequisites for claiming product-market fit.

## Open Questions for the PRD

- Which five to eight tools create the strongest complete interview demonstration?
- Which mutations require confirmation, and should confirmation expire when scenario state changes?
- What is the minimum authentication mechanism that is robust without becoming an account-management project?
- Should the MVP demonstrate streaming responses, or is durable turn status more valuable?
- Which scenario and measurable before/after result best communicate planner value?
