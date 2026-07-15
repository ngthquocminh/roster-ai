# v0.3 research — archived

Domain research produced at the start of milestone **v0.3 (LLM Layer)**,
researched 2026-06-28 by four parallel researchers plus a synthesizer. Archived
here at the v0.3/v0.4 boundary so v0.4's research could not overwrite it in
place — the researchers write to these exact filenames.

**Not maintained.** This is a record of what was believed before v0.3 was built,
not a description of what shipped. For what actually shipped see
`.planning/MILESTONES.md`, `.planning/milestones/v0.3-ROADMAP.md`, and
`docs/design.md` §4 (the durable LLM-layer design).

## Read this before trusting any of it

`STACK.md` researched the `anthropic-sdk-python` and recommended Claude as the
LLM provider. **That is not what shipped.** There is no free Claude API tier, so
v0.3 shipped `stub` (default, keeps CI keyless) + Gemini (`google-genai`) +
OpenRouter (openai SDK) instead — see PROJECT.md's Key Decisions table.

That gap is the useful thing about this archive: it's a concrete record of
confident up-front research that didn't survive contact with a constraint nobody
had checked yet (pricing). Worth remembering next time a research doc reads as
settled.

| File | Scope |
|------|-------|
| `STACK.md` | Proposed stack additions for the LLM layer — see caveat above |
| `FEATURES.md` | Feature landscape for NL constraint editing + insights |
| `ARCHITECTURE.md` | How the LLM layer was expected to integrate |
| `PITFALLS.md` | Anticipated failure modes |
| `SUMMARY.md` | Synthesis of the four |
