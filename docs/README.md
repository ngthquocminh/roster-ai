# Documentation ownership

One owner per audience prevents drift.

- **Reviewer-facing system documentation** lives in `docs/`: the
  [walkthrough](WALKTHROUGH.md), [architecture](ARCHITECTURE.md), setup,
  configuration, and the API pointer.
- **Planning lifecycle and implementation records** live in `_bmad-output/`.
  They record what was decided, built, and still deferred; they are not the
  reviewer entry point.
- **Historical material** lives in `docs/archive/`. It is retained for context
  but is neither current nor maintained.

The original product vision is preserved as
[archived vision](archive/vision.md). The superseded v0.3/v0.4 design is
[archived architecture](archive/architecture-v0.4.md).
