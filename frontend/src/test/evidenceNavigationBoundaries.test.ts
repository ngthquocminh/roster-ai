import { readFileSync, readdirSync, statSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";
import { expect, it } from "vitest";

/**
 * AR15: the full locator is owned by the application and never entrusted to a
 * model-generated URL.
 *
 * This guard is an ALLOWLIST of shapes, not a denylist of identifier spellings.
 * A denylist only fails when someone writes one of a handful of pre-imagined
 * names, so `navigate(claim.narrative)` and — trivially —
 * `const t = segment.text; navigate(t)` both slipped through it. Requiring a
 * known shape instead fails closed: any new navigation source is red until a
 * human deliberately adds it below, which is the moment that source gets looked
 * at.
 */

// Calls whose RESULT is a safe, application-owned string.
const APPROVED_CALLS = new Set(["toSearchParams", "encodeURIComponent", "String"]);

// Roots of typed, application-owned data. Every one of these is either a route
// param, a persisted contract field, or an app-constructed origin — none is
// free text produced by a model.
const APPROVED_ROOTS = new Set([
  "scenarioId",
  "conversationId",
  "origin",
  "item",
  "target",
  "reference",
  "next",
  "searchParams",
]);

// `href`/`to`/`src` navigate wherever they appear (intrinsic elements and
// react-router components alike). `action`/`formAction` only navigate on real
// HTML elements — as a component prop, `action` is an ordinary ReactNode (see
// `InlineAlert`), so checking it everywhere would flag rendered buttons.
const NAVIGATIONAL_ATTRIBUTES = new Set(["href", "to", "src"]);
const INTRINSIC_ONLY_ATTRIBUTES = new Set(["action", "formAction"]);

function isIntrinsicElement(attribute: ts.JsxAttribute, tree: ts.SourceFile): boolean {
  const owner = attribute.parent.parent;
  if (!ts.isJsxOpeningElement(owner) && !ts.isJsxSelfClosingElement(owner)) return false;
  const tag = owner.tagName.getText(tree);
  return /^[a-z]/.test(tag);
}

function isNavigational(attribute: ts.JsxAttribute, tree: ts.SourceFile): boolean {
  const name = attribute.name.getText(tree);
  if (NAVIGATIONAL_ATTRIBUTES.has(name)) return true;
  return INTRINSIC_ONLY_ATTRIBUTES.has(name) && isIntrinsicElement(attribute, tree);
}

function sourceFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = resolve(directory, name);
    return statSync(path).isDirectory()
      ? sourceFiles(path)
      : /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

function rootIdentifier(node: ts.Node): string {
  let current = node;
  while (
    ts.isPropertyAccessExpression(current)
    || ts.isElementAccessExpression(current)
    || ts.isNonNullExpression(current)
    || ts.isParenthesizedExpression(current)
  ) {
    current = current.expression;
  }
  return ts.isIdentifier(current) ? current.text : "";
}

/** An interpolation is safe when it is an approved call or rooted in approved data. */
function interpolationIsOwned(expression: ts.Expression, tree: ts.SourceFile): boolean {
  if (ts.isCallExpression(expression)) {
    const callee = expression.expression;
    const name = ts.isPropertyAccessExpression(callee) ? callee.name.text : callee.getText(tree);
    return APPROVED_CALLS.has(name);
  }
  return APPROVED_ROOTS.has(rootIdentifier(expression));
}

/** A navigation target must be a literal path, optionally interpolated with owned data. */
function targetIsOwned(expression: ts.Expression | undefined, tree: ts.SourceFile): boolean {
  if (!expression) return false;
  if (ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression)) return true;
  if (!ts.isTemplateExpression(expression)) return false;
  return expression.templateSpans.every((span) => interpolationIsOwned(span.expression, tree));
}

it("derives every navigation target from application-owned data, never from model output", () => {
  const roots = [
    resolve(process.cwd(), "src/features/chat"),
    resolve(process.cwd(), "src/features/evidence"),
  ];
  const navigateTargets: string[] = [];
  const navigationalAttributes: string[] = [];

  for (const path of roots.flatMap(sourceFiles)) {
    const source = readFileSync(path, "utf8");
    const tree = ts.createSourceFile(path, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const visit = (node: ts.Node) => {
      if (ts.isCallExpression(node)) {
        const callee = node.expression.getText(tree);
        if (/(^|\.)navigate\??$/.test(callee)) {
          const target = node.arguments[0];
          navigateTargets.push(`${path}: ${target?.getText(tree) ?? "<missing>"}`);
          expect(
            targetIsOwned(target, tree),
            `${path}: navigate() target is not built from application-owned data: ${target?.getText(tree)}`,
          ).toBe(true);
        }
      }
      if (ts.isJsxAttribute(node) && node.initializer && isNavigational(node, tree)) {
        const initializer = node.initializer;
        const expression = ts.isJsxExpression(initializer) ? initializer.expression : initializer;
        navigationalAttributes.push(`${path}: ${node.name.getText(tree)}=${initializer.getText(tree)}`);
        expect(
          expression !== undefined && ts.isExpression(expression) && targetIsOwned(expression, tree),
          `${path}: ${node.name.getText(tree)} is not built from application-owned data: ${initializer.getText(tree)}`,
        ).toBe(true);
      }
      ts.forEachChild(node, visit);
    };
    visit(tree);
  }

  // Anti-vacuity: a guard that inspected nothing would pass silently.
  expect(navigateTargets.length).toBeGreaterThan(0);
});

it("rejects a navigation target derived from model-produced free text", () => {
  const tree = ts.createSourceFile(
    "probe.tsx",
    [
      "navigate(segment.text);",
      "navigate(claim.narrative);",
      "const t = segment.text; navigate(t);",
      "navigate(`/scenarios/${segment.text}`);",
    ].join("\n"),
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const rejected: string[] = [];
  const visit = (node: ts.Node) => {
    if (ts.isCallExpression(node) && /(^|\.)navigate\??$/.test(node.expression.getText(tree))) {
      if (!targetIsOwned(node.arguments[0], tree)) rejected.push(node.getText(tree));
    }
    ts.forEachChild(node, visit);
  };
  visit(tree);

  // The guard's own teeth, asserted directly: without this, a rule that accepted
  // everything would still pass the sweep above.
  expect(rejected).toHaveLength(4);
});
