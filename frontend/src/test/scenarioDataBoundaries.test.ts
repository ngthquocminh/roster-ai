import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { expect, it } from "vitest";

const SCENARIO_DATA_ROOT = join(process.cwd(), "src/features/scenario-data");
// `features/evidence` is composed INTO the Scenario Data surface
// (ScenarioDataView renders EvidenceTargetPanel), so it renders on the surface
// these invariants describe and must be swept with it. It lives outside
// `features/scenario-data` deliberately — Scenario Data composes the evidence
// panel, it does not own it — which is exactly why the sweep has to name it.
const EVIDENCE_ROOT = join(process.cwd(), "src/features/evidence");

function scenarioDataFiles(): string[] {
  return [
    ...sourceFiles(SCENARIO_DATA_ROOT).filter(path => !path.includes(".test.") && !path.endsWith("panelTestContract.tsx")),
    ...sourceFiles(EVIDENCE_ROOT).filter(path => !path.includes(".test.")),
    join(process.cwd(), "src/routes/ScenarioData.tsx"),
  ];
}

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? sourceFiles(path) : entry.name.endsWith(".tsx") || entry.name.endsWith(".ts") ? [path] : [];
  });
}

it("keeps Scenario Data independent from agent and mutation APIs", () => {
  const files = [
    ...scenarioDataFiles(),
    join(process.cwd(), "src/api/scenarioProjection.ts"),
    join(process.cwd(), "src/hooks/useScenarioProjection.ts"),
  ];
  const forbidden = ["@/api/constraints", "@/api/insights", "@/hooks/useApplyConstraint", "@/hooks/useRunInsights"];
  for (const file of files) for (const specifier of forbidden) expect(readFileSync(file, "utf8"), `${file} imports ${specifier}`).not.toContain(specifier);
});

it("keeps Scenario Data free of mutation affordances", () => {
  const MUTATING_VERBS = /\b(create|upload|import|edit|delete)\b/i;
  for (const file of scenarioDataFiles()) {
    const source = readFileSync(file, "utf8");
    expect(source, `${file} renders editable content`).not.toMatch(/contentEditable|draggable|type=["']file["']/i);
    // Code review (story-1.9, 2026-08-06): a button's accessible name falls
    // back to its text content when no aria-label is set — check both, not
    // just aria-label, or an unlabeled `<button>Delete</button>` slips past.
    expect(source, `${file} names a mutating action via aria-label`).not.toMatch(
      new RegExp(`aria-label=["'][^"']*${MUTATING_VERBS.source}`, "i"),
    );
    for (const match of source.matchAll(/<button\b[^>]*>([^<]*)<\/button>/gi)) {
      expect(match[1], `${file} has a button named "${match[1].trim()}"`).not.toMatch(MUTATING_VERBS);
    }
  }
});

it("keeps the governed catalogue and projection clients GET-only", () => {
  for (const relativePath of ["src/api/scenarioProjection.ts", "src/api/scenarioCatalogue.ts"]) {
    const source = readFileSync(join(process.cwd(), relativePath), "utf8");
    expect(source, `${relativePath} calls a mutating client method`).not.toMatch(/client\.(POST|PUT|PATCH|DELETE)\s*\(/);
    expect(source, `${relativePath} has no governed GET calls`).toMatch(/client\.GET\s*\(/);
  }
});
