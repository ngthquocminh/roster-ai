# ShiftMind (repo `rosterai`)

AI-assisted workforce scheduling: a planner describes a change in plain English,
a PydanticAI agent proposes typed intent, application code validates and governs
it, and OR-Tools CP-SAT alone builds the schedule. What it is and how it works:
[`README.md`](../README.md). Don't restate the docs below here; link to them.

## Where the truth lives

| Topic | Source |
|---|---|
| Architecture decisions and invariants (normative) | `_bmad-output/planning-artifacts/architecture/architecture-ShiftMind-2026-07-22/ARCHITECTURE-SPINE.md` |
| Trust boundaries and hexagonal layering | `docs/ARCHITECTURE.md` (enforced by `backend/tests/architecture/`) |
| Setup, commands, codegen, Protocol seams | `docs/DEVELOPMENT.md`, `docs/GETTING-STARTED.md` |
| Env vars and settings | `docs/CONFIGURATION.md` |
| Test suites, live eval, mocking convention | `docs/TESTING.md` |
| Demand family/unit rules | `docs/DOMAIN-MODEL.md` |
| Stack and versions | `backend/pyproject.toml`, `frontend/package.json` |
| Superseded v0.3/v0.4 design (SQLite, `LLMProvider`) | `docs/archive/` (historical only, do not follow) |

**Legacy code:** `backend/llm/`, `backend/services/` and `backend/store/` are v0.3/v0.4
compatibility adapters. Chat and LLM work goes through `backend/agent/` (PydanticAI
`AgentRuntime`) and `backend/application/`. Don't extend the legacy paths.

## Read before touching these

### Metrics and demand

`docs/DOMAIN-MODEL.md` is normative: `outbound`/`inbound` demand is **volume**,
`indirect` is **headcount**, and assignments carry worker identity but **no family**.
Cite it; never re-derive the rule from adapter code. Re-deriving it caused five of
Story 2.7's nine decision-grade review findings. A headcount question about
outbound/inbound work is **valid** and is answered from assignments, not demand,
so don't guard by family. (Auto-loaded into create-story, dev-story and code-review via
`_bmad/custom/*.toml`.)

### Evidence files (`evidence/**/*.json`)

Follow `docs/EVIDENCE-CONVENTION.md`: **commit the code, then measure, then
generate with `backend/scripts/evidence_binding.py`, then commit the evidence
separately.** Never hand-type an evidence file. Gate A operations are in
`docs/GATE-A-RUNBOOK.md`. Manual assistive-technology verification is descoped;
accessibility is proven by automated coverage alone (see the Accessibility Floor in
`_bmad-output/planning-artifacts/ux-designs/ux-ShiftMind-2026-07-22/EXPERIENCE.md`).

### Docker compose in a Claude Code cloud sandbox

Plain `docker compose up -d --build` fails there because of sandbox networking,
not app bugs. Run `.claude/sandbox/docker-dev.sh` instead, and see
`.claude/sandbox/README.md` for why. Don't re-diagnose it from scratch.

## Conventions

These are the conventions not covered by `docs/DEVELOPMENT.md`'s Code style section.

**Backend (Python 3.10–3.12, uv)**
- Absolute imports from the `backend/` root (`from domain.types import Member`), never relative.
- Type hints on every parameter and return; `X | None` and built-in generics, not `Optional`/`Union`.
- Domain value types are `@dataclass(frozen=True)`. Interfaces are `typing.Protocol` + a factory.
- Domain and application layers import no framework, persistence, provider or telemetry
  code. The architecture tests enforce this, and any exception must be listed in `ALLOWED_LEAKS`.
- Comments explain *why*. Module docstrings state purpose and design decisions.

**Frontend (React 19, strict TS)**
- `@/` alias for all imports. Named exports only. Components `PascalCase.tsx`, hooks `useX.ts`,
  and tests co-located (`X.test.tsx`).
- Request/response types derive from generated `src/api/schema.d.ts`, never hand-authored.
  Run `npm run codegen` after any backend route/schema change.
- Hooks are thin TanStack Query wrappers, and business logic stays in components. Query keys are
  shared contracts.
- API wrappers throw `{ status, ...error }`. Read the status with `getErrorStatus()` from
  `src/lib/errors.ts`, not ad-hoc casts.
