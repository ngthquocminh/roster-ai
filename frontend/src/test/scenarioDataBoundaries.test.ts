import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { expect, it } from "vitest";

const SCENARIO_DATA_ROOT = join(process.cwd(), "src/features/scenario-data");

function scenarioDataFiles(): string[] {
  return [
    ...sourceFiles(SCENARIO_DATA_ROOT).filter(path => !path.includes(".test.") && !path.endsWith("panelTestContract.tsx")),
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
  for (const file of scenarioDataFiles()) {
    const source = readFileSync(file, "utf8");
    expect(source, `${file} renders editable content`).not.toMatch(/contentEditable|draggable|type=["']file["']/i);
    expect(source, `${file} names a mutating action`).not.toMatch(/aria-label=["'][^"']*\b(create|upload|import|edit|delete)\b/i);
  }
});

it("keeps the governed catalogue and projection clients GET-only", () => {
  for (const relativePath of ["src/api/scenarioProjection.ts", "src/api/scenarioCatalogue.ts"]) {
    const source = readFileSync(join(process.cwd(), relativePath), "utf8");
    expect(source, `${relativePath} calls a mutating client method`).not.toMatch(/client\.(POST|PUT|PATCH|DELETE)\s*\(/);
    expect(source, `${relativePath} has no governed GET calls`).toMatch(/client\.GET\s*\(/);
  }
});
