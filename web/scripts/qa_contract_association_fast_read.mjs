import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

const file = new URL("../app/api/master-contracts/[isrc]/associations/route.ts", import.meta.url);
const parsed = ts.createSourceFile("route.ts", fs.readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true);
const transformed = ts.transform(parsed, [(context) => (root) => ts.visitNode(root, function visit(node) {
  return ts.isImportDeclaration(node) ? undefined : ts.visitEachChild(node, visit, context);
})]);
const text = ts.createPrinter().printFile(transformed.transformed[0]);
transformed.dispose();
const compiled = ts.transpileModule(text, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const calls = [];
let config = { apiUrl: "https://api.example.test", username: "reader" };
let payload = { isrc: "ARDL12600006", items: [], version: 7, pending_codes: [], income: { amount_usd: 110 } };
let status = 200;
globalThis.__associationRouteQa = {
  apiConfig: async () => config,
  royaltyHeaders: () => ({ "x-vpo-username": "reader", "x-vpo-api-key": "test-only" }),
  NextResponse: { json: (body, options = {}) => ({ body, status: options.status ?? 200 }) },
  fetch: async (url, options) => {
    calls.push({ url: String(url), options });
    return { ok: status === 200, status, json: async () => payload };
  },
};
const prefix = "const {apiConfig,royaltyHeaders,NextResponse,fetch}=globalThis.__associationRouteQa;\n";
const { GET } = await import("data:text/javascript;base64," + Buffer.from(prefix + compiled).toString("base64"));
const invoke = (query = "") => GET({ nextUrl: new URL("https://web.example.test/associations" + query) },
  { params: Promise.resolve({ isrc: "ARDL12600006" }) });
try {
  assert.deepEqual((await invoke()).body, payload);
  assert.equal(new URL(calls.at(-1).url).search, "");
  assert.equal(calls.at(-1).options.cache, "no-store");
  assert.equal(calls.at(-1).options.headers["x-vpo-username"], "reader");
  payload = { isrc: "ARDL12600006", items: [{ code: "native" }], version: 7, pending_codes: [] };
  assert.deepEqual((await invoke("?include_income=false&username=admin&unknown=value")).body, payload);
  assert.equal(new URL(calls.at(-1).url).search, "?include_income=false");
  assert.equal(calls.at(-1).options.headers["x-vpo-username"], "reader");
  await invoke("?include_income=true");
  assert.equal(new URL(calls.at(-1).url).search, "?include_income=true");
  payload = { detail: "Cannot verify current evidence" };
  status = 503;
  assert.deepEqual(await invoke("?include_income=false"), { body: { error: payload.detail }, status: 503 });
  config = { error: { status: 401, body: { error: "Login required" } } };
  const before = calls.length;
  assert.deepEqual(await invoke("?include_income=false"), config.error);
  assert.equal(calls.length, before);
  const panel = fs.readFileSync(new URL("../app/features/master-contracts/ContractAssociationsPanel.tsx", import.meta.url), "utf8");
  assert.match(panel, /associations\?include_income=false/);
  assert.match(panel, /body\.version !== version/);
  const main = fs.readFileSync(new URL("../app/features/master-contracts/MasterContractsModule.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(main, /associations\?include_income=false/);
  assert.match(main, /refreshed\.income/);
  console.log("Association fast read: default income, explicit modes, unchanged auth, error handling, version guard and post-save totals: PASS");
} finally {
  delete globalThis.__associationRouteQa;
}
