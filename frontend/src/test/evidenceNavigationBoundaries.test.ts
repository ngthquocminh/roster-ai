import { readFileSync, readdirSync, statSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";
import { expect, it } from "vitest";

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = resolve(directory, name);
    return statSync(path).isDirectory()
      ? sourceFiles(path)
      : /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

it("never derives navigation or DOM attributes from model-produced free text", () => {
  const roots = [
    resolve(process.cwd(), "src/features/chat"),
    resolve(process.cwd(), "src/features/evidence"),
  ];
  const inspected: string[] = [];

  for (const path of roots.flatMap(sourceFiles)) {
    const source = readFileSync(path, "utf8");
    const tree = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const visit = (node: ts.Node) => {
      if (ts.isCallExpression(node)) {
        const callee = node.expression.getText(tree);
        if (/(^|\.)navigate\??$/.test(callee)) {
          const target = node.arguments[0]?.getText(tree) ?? "";
          inspected.push(`${path}:navigate:${target}`);
          expect(target).not.toMatch(/(?:segment|prose|model|freeText)\s*\.\s*text|GroundedProseSegmentV1/i);
        }
      }
      if (ts.isJsxAttribute(node) && node.initializer) {
        const attribute = node.name.getText(tree);
        const value = node.initializer.getText(tree);
        inspected.push(`${path}:${attribute}:${value}`);
        expect(value).not.toMatch(/(?:segment|prose|model|freeText)\s*\.\s*text|GroundedProseSegmentV1/i);
      }
      ts.forEachChild(node, visit);
    };
    visit(tree);
  }

  expect(inspected.some((entry) => entry.includes(":navigate:"))).toBe(true);
  expect(inspected.some((entry) => entry.includes(":id:"))).toBe(true);
});
