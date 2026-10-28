import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

const calls = [];
let config = { apiUrl: "https://api.example.test" };
let status = 200, payload = { associated: true };
globalThis.__linkRouteQa = {
  apiConfig: async () => config,
  royaltyHeaders: () => ({ "x-vpo-username": "editor", "x-vpo-api-key": "test" }),
  NextResponse: { json: (body, options = {}) => ({ body, status: options.status ?? 200 }) },
  fetch: async (url, options) => { calls.push({ url: String(url), options }); return { ok: status === 200, status, json: async () => payload }; },
};
async function load(path) {
  const source = ts.createSourceFile("route.ts", fs.readFileSync(new URL(path, import.meta.url), "utf8"), ts.ScriptTarget.Latest, true);
  const transformed = ts.transform(source, [(context) => root => ts.visitNode(root, function visit(node) {
    return ts.isImportDeclaration(node) ? undefined : ts.visitEachChild(node, visit, context);
  })]);
  const code = ts.createPrinter().printFile(transformed.transformed[0]);
  transformed.dispose();
  const compiled = ts.transpileModule(code, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
  return import("data:text/javascript;base64," + Buffer.from("const {apiConfig,royaltyHeaders,NextResponse,fetch}=globalThis.__linkRouteQa;\n" + compiled).toString("base64"));
}
try {
  const route = await load("../app/api/master-contracts/unidentified/[referenceId]/association/route.ts");
  const search = await load("../app/api/master-contracts/unidentified/destinations/route.ts");
  const body = { isrc: "ARDL12600006", expected_version: 7, release_id: "r", reference_signature: "sig" };
  const request = (query = "", origin = "https://web.example.test") => ({
    nextUrl: new URL("https://web.example.test/api/link" + query), headers: new Headers({ origin }), json: async () => body,
  });
  const context = { params: Promise.resolve({ referenceId: "reference" }) };
  await route.GET(request("?isrc=ARDL12600006&username=admin"), context);
  assert.equal(new URL(calls.at(-1).url).search, "?isrc=ARDL12600006");
  assert.equal(calls.at(-1).options.headers["x-vpo-username"], "editor");
  await route.POST(request(), context);
  assert.equal(calls.at(-1).options.method, "POST");
  assert.deepEqual(JSON.parse(calls.at(-1).options.body), body);
  assert.equal(calls.at(-1).options.cache, "no-store");
  const count = calls.length;
  assert.equal((await route.POST(request("", "https://attacker.example"), context)).status, 403);
  assert.equal(calls.length, count);
  const proxied = request();
  proxied.nextUrl = new URL("http://0.0.0.0:8080/api/link");
  proxied.headers.set("x-forwarded-host", "web.example.test");
  proxied.headers.set("x-forwarded-proto", "https");
  assert.equal((await route.POST(proxied, context)).status, 200);
  proxied.headers.set("origin", "https://attacker.example");
  assert.equal((await route.POST(proxied, context)).status, 403);
  await search.GET(request("?keyword=La+Nave&username=admin"));
  assert.equal(new URL(calls.at(-1).url).search, "?keyword=La+Nave");
  status = 409; payload = { detail: "El contrato cambio" };
  assert.deepEqual(await route.POST(request(), context), { body: { error: payload.detail }, status: 409 });
  config = { error: { status: 401 } };
  assert.deepEqual(await route.GET(request(), context), config.error);
  const dialog = fs.readFileSync(new URL("../app/features/master-contracts/AssociateIncomeDialog.tsx", import.meta.url), "utf8");
  assert.match(dialog, /showModal\(\)/);
  assert.match(dialog, /reference_signature: preview\.reference_signature/);
  assert.match(dialog, /expected_version: preview\.target\.version/);
  assert.match(dialog, /sequence\.current/);
  const panel = fs.readFileSync(new URL("../app/features/master-contracts/ContractAssociationsPanel.tsx", import.meta.url), "utf8");
  assert.match(panel, /row\.manual \? \{ manual: true \}/);
  console.log("Unidentified association: search, auth, current-user headers, CSRF, confirmation, version checks and manual marker preservation: PASS");
} finally { delete globalThis.__linkRouteQa; }
