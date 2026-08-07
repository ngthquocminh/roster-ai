# Scenario Data NVDA Checklist

Story 1.10 manual screen-reader matrix for the Gate A catalogue, scenario workspace, and Scenario Data viewer.

- Measurement date: 2026-08-06
- Preview command: `npm run preview`
- Chrome result: Not executed — NVDA is unavailable in the execution environment.
- Edge result: Not executed — NVDA is unavailable in the execution environment.
- Availability checks: `Get-Command nvda` and the standard system/user NVDA executable paths returned no installation.

Automated axe and semantic tests complement this checklist but do not substitute for the manual screen-reader observations below.

| Obligation | Test action | Expected utterance | Chrome observed utterance | Chrome result | Edge observed utterance | Edge result |
|---|---|---|---|---|---|---|
| Heading announcement on route change | Open a catalogue scenario, then activate Scenario Data. | The focused scenario heading is announced once after catalogue navigation; Scenario Data is announced as the section heading after the workspace route change. | Not observed — NVDA unavailable. | Not executed | Not observed — NVDA unavailable. | Not executed |
| Table caption and column-header association | Enter each of the six tabular groups and navigate from its caption into several data cells. | The group caption is announced and each data cell is associated with its column header. | Not observed — NVDA unavailable. | Not executed | Not observed — NVDA unavailable. | Not executed |
| Sort-state change | Focus a sortable column header, activate it twice, and inspect the announced state. | The column name and ascending state are announced after the first activation; descending is announced after the second. | Not observed — NVDA unavailable. | Not executed | Not observed — NVDA unavailable. | Not executed |
| Row position after page change | Activate Next on a group with more than one page. | The live status announces the new visible row range and total or matching count. | Not observed — NVDA unavailable. | Not executed | Not observed — NVDA unavailable. | Not executed |
| Identifier copy | Activate a Copy control for an identifier. | `Copied {identifier type}` is announced by the polite status region. | Not observed — NVDA unavailable. | Not executed | Not observed — NVDA unavailable. | Not executed |
| Evidence-reveal explanation | Follow an evidence link targeting a currently hidden field and inspect the viewer explanation and chooser item. | `{Field} is shown because an evidence link targets it` is announced; the chooser identifies the field as shown for the linked evidence target. | Not observed — NVDA unavailable. | Not executed | Not observed — NVDA unavailable. | Not executed |
| Disabled Results explanation | Navigate through the scenario workspace tabs to Results. | `Results` is presented as unavailable together with `Results unavailable: select a run`; it is not exposed as an actionable link or button. | Not observed — NVDA unavailable. | Not executed | Not observed — NVDA unavailable. | Not executed |

The matrix must be rerun on a Windows workstation with NVDA, Chrome, and Edge before the manual screen-reader gate can be reported as passed.
