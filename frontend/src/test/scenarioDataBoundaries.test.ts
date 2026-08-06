import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { expect, it } from "vitest";

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? sourceFiles(path) : entry.name.endsWith(".tsx") || entry.name.endsWith(".ts") ? [path] : [];
  });
}

it("keeps Scenario Data independent from agent and mutation APIs", () => {
  const files = [
    ...sourceFiles(join(process.cwd(), "src/features/scenario-data")).filter(path => !path.endsWith(".test.tsx")),
    join(process.cwd(), "src/routes/ScenarioData.tsx"),
    join(process.cwd(), "src/api/scenarioProjection.ts"),
    join(process.cwd(), "src/hooks/useScenarioProjection.ts"),
  ];
  const forbidden = ["@/api/constraints", "@/api/insights", "@/hooks/useApplyConstraint", "@/hooks/useRunInsights"];
  for (const file of files) for (const specifier of forbidden) expect(readFileSync(file, "utf8"), `${file} imports ${specifier}`).not.toContain(specifier);
});
