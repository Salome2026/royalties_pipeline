import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

const calls = [];
let config = { apiUrl: "https://api.example.test", user: { username: "rubene" } };
let status = 202, payload = { item: { id: 119, status: "queued" }, reused: false };
globalThis.__reportStartQa = {
  apiConfig: async () => config,
  royaltyHeaders: () => ({ "X-VPO-API-Key": "test", "X-VPO-Royalty-Scope": "regular" }),
  NextResponse: {
    json: (body, options = {}) => ({ body, status: options.status ?? 200 }),
    redirect: (url, responseStatus) => ({ url: String(url), status: responseStatus }),
  },
  fetch: async (url, options) => {
    calls.push({ url: String(url), options });
    return { ok: status >= 200 && status < 300, status, json: async () => payload };
  },
};

try {
  const file = new URL("../app/api/report/route.ts", import.meta.url);
  const tree = ts.createSourceFile("route.ts", fs.readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true);
  const transformed = ts.transform(tree, [(context) => root => ts.visitNode(root, function visit(node) {
    return ts.isImportDeclaration(node) ? undefined : ts.visitEachChild(node, visit, context);
  })]);
  const source = ts.createPrinter().printFile(transformed.transformed[0]);
  transformed.dispose();
  const compiled = ts.transpileModule(source, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
  }).outputText;
  const route = await import("data:text/javascript;base64," + Buffer.from(
    "const {apiConfig,royaltyHeaders,NextResponse,fetch}=globalThis.__reportStartQa;\n" + compiled,
  ).toString("base64"));
  assert.equal(route.maxDuration, 300);
  assert.ok(route.maxDuration > 65.225701607, "Accept the observed cold contractual start instead of cutting it off at 60 seconds");
  const base = {
    keywords: [], contract_artists: ["Mc Tota"], executive_mode: "contractual",
    start_month: null, end_month: null, period_basis: "statement_period",
    mode: "any", raw_limit: 0, detail_mode: "limited", source: null, account: null,
  };
  for (const output of ["executive_pdf", "excel", "google_sheet"]) {
    const body = output === "executive_pdf" ? { ...base, output } : { keywords: ["MC Tota"], output };
    assert.deepEqual(await route.POST({ json: async () => body }), { body: payload, status: 202 });
    assert.equal(calls.at(-1).url, config.apiUrl + "/reports/jobs");
    assert.equal(calls.at(-1).options.method, "POST");
    assert.deepEqual(JSON.parse(calls.at(-1).options.body), body);
    assert.equal(calls.at(-1).options.headers["X-VPO-Username"], "rubene");
    assert.equal(calls.at(-1).options.headers["X-VPO-Royalty-Scope"], "regular");
    assert.equal(calls.at(-1).options.cache, "no-store");
  }
  status = 400; payload = { detail: "Elegí artistas o proyectos del catálogo." };
  assert.deepEqual(await route.POST({ json: async () => base }), { body: { error: payload.detail }, status: 400 });
  status = 200; payload = { item: { id: 119, status: "completed", download_ready: true } };
  assert.deepEqual(await route.GET({ nextUrl: new URL("https://web.example/api/report?job_id=119") }), { body: payload, status: 200 });
  assert.equal(calls.at(-1).url, config.apiUrl + "/reports/jobs/119");
  payload = { url: "https://storage.googleapis.com/reports/119.pdf?signature=test" };
  assert.equal((await route.GET({ nextUrl: new URL("https://web.example/api/report?job_id=119&download=1") })).status, 307);
  payload = { url: "https://untrusted.example/119.pdf" };
  assert.equal((await route.GET({ nextUrl: new URL("https://web.example/api/report?job_id=119&download=1") })).status, 502);
  config = { error: { status: 401 } };
  const count = calls.length;
  assert.deepEqual(await route.POST({ json: async () => base }), config.error);
  assert.deepEqual(await route.GET({ nextUrl: new URL("https://web.example/api/report") }), config.error);
  assert.equal(calls.length, count);
  console.log("Report initiation: 300-second proxy budget, unchanged payloads/auth, error details, existing status and safe downloads: PASS");
} finally {
  delete globalThis.__reportStartQa;
}
