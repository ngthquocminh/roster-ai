# docs/ — what belongs here

One owner per audience. That's the whole rule. `docs/` rotted before because
`PLAN.md` quietly duplicated `.planning/`'s job with no rule saying which one
wins when they disagreed — so they drifted, and nobody could tell which was
current. The fix isn't a better tracker; it's not having two.

- **Planning lifecycle** (what's next / what shipped / what was decided) →
  `.planning/` (`STATE.md`, `ROADMAP.md`, `MILESTONES.md`). This is GSD's job.
  Nothing in `docs/` tracks phase status any more.
- **Reference + rationale** → `docs/`. [`API.md`](API.md) is the live HTTP
  contract. [`design.md`](design.md) is *why* the system is shaped the way it
  is and what was deliberately not built. Neither has a GSD equivalent —
  `.planning/` tracks progress, not durable design.
- **Origin** → `docs/`. [`vision.md`](vision.md) is the initial idea the
  project started from: a frozen snapshot, kept for reference, not maintained.

The hand-written phase-by-phase tracker that used to live here was retired at
the v0.3/v0.4 boundary in favor of `.planning/` doing that job exclusively.
For current status, see `.planning/`.

`docs/archive/` holds the superseded Phase 1–2 plan docs — historical record
of how those phases were built, not maintained, not current.
