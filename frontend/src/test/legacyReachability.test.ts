import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, extname, join, normalize, relative, resolve } from "node:path";

import { expect, it } from "vitest";

const SOURCE_ROOT = join(process.cwd(), "src");
const ENTRY = join(SOURCE_ROOT, "App.tsx");
const LEGACY_PREFIXES = [
  "components/editor/",
  "components/runs/",
  "components/results/",
  "components/scenarios/",
];
const LEGACY_MODULES = [
  "components/layout/ErrorBanner.tsx",
  "lib/runStatus.ts",
  "hooks/useApplyConstraint.ts",
  "hooks/useCreateScenario.ts",
  "hooks/useFixtures.ts",
  "hooks/useOverrides.ts",
  "hooks/useRun.ts",
  "hooks/useRunInsights.ts",
  "hooks/useRunResult.ts",
  "hooks/useRuns.ts",
  "hooks/useScenario.ts",
  "hooks/useScenarios.ts",
  "hooks/useTriggerRun.ts",
  // Code review (story-1.9, 2026-08-06): these mutating API-client wrappers
  // lost their only callers (the hooks above) in this same story but were
  // left undeleted and unaudited by the original sweep.
  "api/scenarios.ts",
  "api/constraints.ts",
  "api/runs.ts",
];
const IMPORT_PATTERN = /(?:import|export)\s+(?:[^"']*?\s+from\s+)?["']([^"']+)["']/g;

function resolveModule(importer: string, specifier: string): string | undefined {
  if (!specifier.startsWith("@/") && !specifier.startsWith(".")) return undefined;
  const base = specifier.startsWith("@/")
    ? join(SOURCE_ROOT, specifier.slice(2))
    : resolve(dirname(importer), specifier);
  for (const candidate of [base, `${base}.ts`, `${base}.tsx`, join(base, "index.ts"), join(base, "index.tsx")]) {
    if (existsSync(candidate) && [".ts", ".tsx"].includes(extname(candidate))) return normalize(candidate);
  }
  return undefined;
}

function reachableFromApp(): Set<string> {
  const reachable = new Set<string>();
  const pending = [ENTRY];
  while (pending.length) {
    const file = normalize(pending.pop()!);
    if (reachable.has(file)) continue;
    reachable.add(file);
    const source = readFileSync(file, "utf8");
    for (const match of source.matchAll(IMPORT_PATTERN)) {
      const dependency = resolveModule(file, match[1]);
      if (dependency && !reachable.has(dependency)) pending.push(dependency);
    }
  }
  return reachable;
}

function sourceFilesBelow(path: string): string[] {
  if (!existsSync(path)) return [];
  return readdirSync(path, { withFileTypes: true }).flatMap((entry) => {
    const child = join(path, entry.name);
    if (entry.isDirectory()) return sourceFilesBelow(child);
    return [".ts", ".tsx"].includes(extname(entry.name)) ? [child] : [];
  });
}

it("proves the deferred legacy UI and mutation hooks are unreachable from App.tsx", () => {
  const reachable = [...reachableFromApp()].map((path) => relative(SOURCE_ROOT, path).replaceAll("\\", "/"));
  const forbidden = reachable.filter((path) =>
    LEGACY_PREFIXES.some((prefix) => path.startsWith(prefix)) || LEGACY_MODULES.includes(path),
  );

  expect(forbidden).toEqual([]);
  expect(reachable).toContain("components/layout/AppBar.tsx");
  expect(reachable).toContain("components/layout/RootErrorBoundary.tsx");
  expect(reachable).toContain("lib/formatShiftWindow.ts");
});

it("keeps the proven-orphaned legacy surface deleted", () => {
  for (const prefix of LEGACY_PREFIXES) {
    expect(sourceFilesBelow(join(SOURCE_ROOT, prefix)), `${prefix} still contains source files`).toEqual([]);
  }
  for (const modulePath of LEGACY_MODULES) {
    expect(existsSync(join(SOURCE_ROOT, modulePath)), `${modulePath} still exists`).toBe(false);
  }
});
