# Phase 4: Real LLM Provider (free-tier first) + Penalty Calibration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-06
**Phase:** 4-real-claude-provider-penalty-calibration
**Areas discussed:** Provider transport, "Free API" production strategy, Phase-4 scoping

---

## Provider transport

| Option | Description | Selected |
|--------|-------------|----------|
| Anthropic API (direct) | Claude via `anthropic` SDK, `ANTHROPIC_API_KEY`. Shortest path, but no free tier. | |
| AWS Bedrock | Claude via `AnthropicBedrock` client, IAM auth. Same wire format, but pulls Phase-5 AWS infra forward. | |
| Free-tier vendor (Gemini) | A vendor with a genuine free tier, behind the same seam. | ✓ |

**User's choice:** "I want to use free API first." → Google Gemini free tier as the first real provider.
**Notes:** No free Claude API tier exists, so "free first" necessarily means a different vendor. The provider-neutral seam makes Claude a trivial future swap; design.md's "Gemini later" simply becomes "Gemini first."

---

## "Free API" production strategy (what free-first is really for)

| Option | Description | Selected |
|--------|-------------|----------|
| A — Lean | One free provider (Gemini) now; fallback gateway as the next phase. | ✓ |
| B — PoC gateway now | Phase 4 lands a minimal `FallbackProvider` over two free providers (Gemini→Groq on 429) + calibration + live test. | |

**User's choice:** A. Plus stated production vision: a gateway that routes across free APIs and switches when one is rate-limited, with a customer **free trial** running on limited free access.
**Notes:** Separated into two scopes — (1) provider routing/failover = engineering, fits the seam as a composite provider, next phase; (2) per-customer free-trial quota = multi-tenant product layer (customers/auth/metering) that does not exist in the codebase yet → future milestone. Neither is throwaway relative to Phase 4 because both compose behind the same `LLMProvider` seam.

---

## Phase-4 scoping (todos)

| Item | Description | Selected |
|------|-------------|----------|
| Fold WR-05 | Real-engine test for ENG-05 degeneracy — same fixture/engine surface as calibration. | ✓ Folded |
| Fold WR-04 | Harden fixture path traversal (security) — unrelated to provider/calibration. | Reviewed, not folded |

**Notes:** WR-04 recommended as a standalone `/gsd-quick` fix.

---

## Claude's Discretion

- Exact calibration weight values + sweep strategy (D-08).
- Env var names / `Settings` field shapes (D-04/D-05), within "default stub, keyless CI."
- D-07 stub wire-shape decision (Gemini-shaped stub vs separate adapter).

## Deferred Ideas

- Provider fallback gateway (composite `FallbackProvider`, 429 rotation) — next phase; evaluate hand-rolled vs LiteLLM vs OpenRouter.
- Per-customer free-trial + quota management — future milestone.
- AWS Bedrock transport / Anthropic-direct Claude — later (Phase 5 / when a paid key is in play).
