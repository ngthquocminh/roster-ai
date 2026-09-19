# Documentation ownership

One owner per audience prevents drift.

- **The reviewer entry point is the repository [README](../README.md)**: what the
  system is, how authority is partitioned, what the evidence shows, and what is
  still open. Everything else supports it.
- **Reviewer-facing system documentation** lives in `docs/`: the
  [walkthrough](WALKTHROUGH.md), [architecture](ARCHITECTURE.md), setup,
  configuration, and the API pointer. Diagrams referenced by the README live in
  `docs/assets/`.
- **Planning lifecycle and implementation records** live in `_bmad-output/`.
  They record what was decided, built, and still deferred; they are not the
  reviewer entry point.
- **Historical material** lives in `docs/archive/`. It is retained for context
  but is neither current nor maintained.

The original product vision is preserved as
[archived vision](archive/vision.md). The superseded v0.3/v0.4 design is
[archived architecture](archive/architecture-v0.4.md).
