# Handover — G′ grounding plan, phases 1–3

Written 2026-09-27 at the end of the planning session. Read this first, then each spec as you
reach it. Everything below that is not in the specs or the research doc is listed here on purpose.

## Where things are

- Branch: `feat/grounding-g-prime`, branched from `main` at `a9e1c20`. Nothing is pushed.
- Research + decisions D1–D3: `_bmad-output/planning-artifacts/research/technical-grounded-answers-claim-evidence-attribution-research-2026-09-26.md`
  (section "Decisions Recorded During Research").
- Approved specs (`status: ready-for-dev`, intent frozen), in this order:
  1. `spec-grounding-1-evidence-registry-short-handles.md`
  2. `spec-grounding-2a-value-placeholders.md`
  3. `spec-grounding-2b-fact-claim-tags.md`
  4. `spec-grounding-3-tier1-checker-shadow.md`
- Phase 4 (`spec-grounding-4-untagged-prose-scan.md`) is **deferred and NOT approved** — do not
  implement it (logged in `deferred-work.md`).

## How to run each phase

- Run `bmad-quick-dev` with the spec path. The specs are approved, so it resumes at step 3
  (implement), then step 4 (review), then step 5 (present).
- One commit per phase on the branch, after its review passes. Conventional-commit style as in
  `git log`; end the message with the Co-Authored-By line from the session instructions.
- **Reviewer subagents are permitted** (Blind Hunter + Edge Case Hunter) for every phase review.
- Each phase must leave `cd backend && uv run pytest -q` green; phases touching the frontend also
  `cd frontend && npm run typecheck && npm test`.

## Stop and ask Minh when

- An earlier phase forces a change inside a later spec's `<frozen-after-approval>` block.
- Phase 3 reaches **any `live_conversations` run** — stop and wait for Minh's explicit permission
  (and the key; Jev through OpenRouter probably reuses the existing OpenRouter key — confirm).
- Anything would enable an enforcing tier-1 mode (flag/strip).
- A spec's "Ask First" item triggers.

## Gotchas found this session

- `backend/tests/architecture/test_trace_export_boundaries.py` allows `AGENT_TRACE_CONTENT_MODE`
  only in `settings.py`, `conftest.py`, `evals/live_conversations/configuration.py` and
  `evals/live_conversations/compose.override.yml`. A commit adding it to `docker-compose.yml` was
  removed for breaking this guard.
- D2 changes **FR7/NFR12** in `epics.md` (phase 2a task), not AR11 — AR11 (locators + calculators)
  still holds.
- Python `write_text` on Windows produces CRLF; when scripting edits, read/write bytes and keep the
  file's existing line endings.
- Ad-hoc scripts importing `settings` can export to the real Logfire project (see memory).
- The full backend suite takes ~7 minutes; run targeted tests while iterating.
- `docs/DOMAIN-MODEL.md` is normative for demand family/unit — cite it, never re-derive it.
