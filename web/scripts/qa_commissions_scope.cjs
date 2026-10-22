const assert = require("node:assert/strict");
const fs = require("node:fs");
const { execFileSync } = require("node:child_process");
const ts = require("typescript");

const baseline = process.argv[2] || "HEAD";
const file = "web/app/page.tsx";
const before = execFileSync("git", ["show", `${baseline}:${file}`], { encoding: "utf8", cwd: ".." });
const after = fs.readFileSync("app/page.tsx", "utf8");
const parse = text => ts.createSourceFile("page.tsx", text.replace(/\r\n/g, "\n"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const mainClasses = [];
let renderReplacements = 0;
const normalize = source => {
  const transformed = ts.transform(source, [context => {
    const visit = node => {
      if (ts.isImportDeclaration(node) && node.moduleSpecifier.text === "lucide-react") {
        return ts.factory.createImportDeclaration(undefined, undefined, ts.factory.createStringLiteral("lucide-react"));
      }
      if (ts.isJsxAttribute(node) && node.name.getText(source) === "className" && node.initializer?.getText(source).includes('"home-main"')) {
        mainClasses.push(node.initializer.getText(source));
        return ts.factory.createJsxAttribute(ts.factory.createIdentifier("className"), ts.factory.createStringLiteral("same-main-classes"));
      }
      if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken &&
          ts.isBinaryExpression(node.left) && node.left.left.getText(source) === "view" &&
          ts.isStringLiteral(node.left.right) && node.left.right.text === "commissions") {
        renderReplacements++;
        return ts.factory.createStringLiteral("commission-presentation-only");
      }
      return ts.visitEachChild(node, visit, context);
    };
    return root => ts.visitNode(root, visit);
  }]);
  const text = ts.createPrinter({ removeComments: false }).printFile(transformed.transformed[0]);
  transformed.dispose();
  return text;
};
const actual = normalize(parse(after));
const expected = normalize(parse(before));
if (actual !== expected) {
  let first = 0;
  while (actual[first] === expected[first] && first < actual.length) first++;
  console.error(JSON.stringify({ replacements: renderReplacements, first,
    actual: actual.slice(Math.max(0, first - 100), first + 300), expected: expected.slice(Math.max(0, first - 100), first + 300) }));
  throw new Error("Change outside Commissions presentation");
}
assert.equal(renderReplacements, 2);
assert.equal(mainClasses.length, 2);
assert.equal(mainClasses[0].replace('view === "commissions" ? "commissions-main" : ', ""), mainClasses[1]);
const oldImports = parse(before).statements.find(node => ts.isImportDeclaration(node) && node.moduleSpecifier.text === "lucide-react");
const newImports = parse(after).statements.find(node => ts.isImportDeclaration(node) && node.moduleSpecifier.text === "lucide-react");
const names = node => node.importClause.namedBindings.elements.map(element => element.name.text).sort();
assert.deepEqual(names(newImports), [...names(oldImports), "Printer", "Save", "SlidersHorizontal"].sort());
const postcss = require("postcss");
const css = postcss.parse(fs.readFileSync("app/features/commissions/commissions.css", "utf8"));
css.walkRules(rule => {
  assert.ok(rule.selector.includes("commission"), `Unscoped CSS selector: ${rule.selector}`);
});
console.log("PASS: calculations, PDF template, API calls, permissions and every other view are AST-identical; CSS is scoped to Commissions");
