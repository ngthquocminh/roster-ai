# Scenario Data NVDA Checklist

Story 1.10 manual screen-reader matrix for the Gate A catalogue, scenario workspace, and Scenario Data viewer. Re-attempted under Story 1.11 Task 6.

- Measurement date: 2026-08-08
- Harness: `NVDA_MANUAL=1 npx playwright test e2e/manual-nvda.spec.ts --project=<chromium|msedge> --headed` (see `docs/GATE-A-RUNBOOK.md`)
- Chrome result: **Not executed** — run started with NVDA installed and Speech Viewer active, then cancelled by the user on 2026-08-08 before the checklist rows were exercised.
- Edge result: **Not executed** — not started; cancelled with the Chrome run.
- 2026-08-06 note (superseded): the earlier attempt recorded `not executed` for a different reason — NVDA was not installed in the execution environment at all.

Automated axe and semantic tests complement this checklist but do not substitute for the manual screen-reader observations below. **No row below may be marked passed on the strength of axe output or source reading.**

| Obligation | Test action | Expected utterance | Chrome observed utterance | Chrome result | Edge observed utterance | Edge result |
|---|---|---|---|---|---|---|
| Heading announcement on route change | Open a catalogue scenario, then activate Scenario Data. | The focused scenario heading is announced once after catalogue navigation; Scenario Data is announced as the section heading after the workspace route change. | Not observed — run cancelled. | Not executed | Not observed — run cancelled. | Not executed |
| Table caption and column-header association | Enter each of the six tabular groups and navigate from its caption into several data cells. | The group caption is announced and each data cell is associated with its column header. | Not observed for the six Scenario Data groups — run cancelled. See partial observation below, which covers the catalogue table only. | Not executed | Not observed — run cancelled. | Not executed |
| Sort-state change | Focus a sortable column header, activate it twice, and inspect the announced state. | The column name and ascending state are announced after the first activation; descending is announced after the second. | Not observed — run cancelled. | Not executed | Not observed — run cancelled. | Not executed |
| Row position after page change | Activate Next on a group with more than one page. | The live status announces the new visible row range and total or matching count. | Not observed — run cancelled. | Not executed | Not observed — run cancelled. | Not executed |
| Identifier copy | Activate a Copy control for an identifier. | `Copied {identifier type}` is announced by the polite status region. | Not observed — run cancelled. | Not executed | Not observed — run cancelled. | Not executed |
| Evidence-reveal explanation | Follow an evidence link targeting a currently hidden field and inspect the viewer explanation and chooser item. | `{Field} is shown because an evidence link targets it` is announced; the chooser identifies the field as shown for the linked evidence target. | Not observed — run cancelled. | Not executed | Not observed — run cancelled. | Not executed |
| Disabled Results explanation | Navigate through the scenario workspace tabs to Results. | `Results` is presented as unavailable together with `Results unavailable: select a run`; it is not exposed as an actionable link or button. | Not observed — run cancelled. | Not executed | Not observed — run cancelled. | Not executed |

## Partial observation (2026-08-08, Chrome)

One genuine capture was taken before the run was cancelled. It is recorded here because it was really observed, but it **does not satisfy any row above** — the catalogue table is not one of the six Scenario Data tabular groups that row 2 names.

Speech Viewer, fixture catalogue route, verbatim:

```
ShiftMind
table  with 2 rows and 4 columns  caption    Predefined scenario fixture versions
out of caption  row 1  column 1  Scenario name
column 2  Scenario ID
column 3  Fixture version
column 4  Imported at
row 2  Scenario name  column 1  link    sample_tiny_input
Scenario ID  column 2  11111111-1111-4111-8111-111111111111
Fixture version  column 3  v1
Imported at  column 4  2026-08-06 00:00
```

What it shows, for the **catalogue table only**:

- the table caption is announced (`Predefined scenario fixture versions`)
- all four column headers are announced in the header row
- each data cell is announced with its column header prefix
- the scenario name is correctly exposed as a `link`

Unresolved from this capture: the `h1` "Fixture catalogue" does not appear in the pasted range, so it is **unknown** whether the heading is announced on load. This is the same class of defect as the focus bug documented at `frontend/src/routes/ScenarioWorkspace.tsx:22-30` and is worth targeting first whenever the pass is resumed.

## To resume

The matrix must be rerun on a Windows workstation with NVDA, Chrome, and Edge before the manual screen-reader gate can be reported as passed. Until then `evidence/story-1.10/…json` keeps `nvda_manual_pass: not executed` and `passed: false`, and `evidence/story-1.11/gate-a-readiness-report.json` reports `gate_a_passed: false` — which is what blocks Epic 2, per AR28.

Procedure and NVDA setup: `docs/GATE-A-RUNBOOK.md` § 3.
