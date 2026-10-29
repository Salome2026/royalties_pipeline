import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

const calls = [];
globalThis.__excelContractsQa = {
  fetch: async (url, options) => { calls.push({ url, options }); return { ok: true, json: async () => ({ item: { id: 1 } }) }; },
};
try {
  const source = fs.readFileSync(new URL("../app/features/royalties/api.ts", import.meta.url), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
  const api = await import("data:text/javascript;base64," + Buffer.from("const {fetch}=globalThis.__excelContractsQa;\n" + code).toString("base64"));
  const original = { keywords: ["tota"], start_month: null, end_month: "2026-06", period_basis: "statement_period",
    mode: "any", raw_limit: 5000, detail_mode: "limited", source: null, account: null };
  await api.createRoyaltyReportJob(original, "excel");
  assert.deepEqual(JSON.parse(calls.at(-1).options.body), { ...original, output: "excel" });
  const enriched = { ...original, include_contracts: true, contract_columns: "matching" };
  await api.createRoyaltyReportJob(enriched, "excel");
  assert.deepEqual(JSON.parse(calls.at(-1).options.body), { ...enriched, output: "excel" });
  for (const output of ["google_sheet", "executive_pdf"]) {
    await api.createRoyaltyReportJob(enriched, output);
    assert.deepEqual(JSON.parse(calls.at(-1).options.body), { ...original, output });
  }
  const ui = fs.readFileSync(new URL("../app/features/royalties/RoyaltyReportModule.tsx", import.meta.url), "utf8");
  assert.match(ui, /\[includeContracts, setIncludeContracts\] = useState\(false\)/);
  assert.match(ui, /royalty_include_contracts/);
  assert.match(ui, /disabled=\{!options\?\.excel_contracts_supported\}/);
  assert.match(ui, /Coincidentes con la búsqueda/);
  assert.match(ui, /Todos los involucrados/);
  assert.ok(ui.indexOf('id="royalty_include_contracts"') > ui.indexOf('id="royalty_period"'));
  assert.match(ui, /if \(contractual\) \{\s+const selection = prepareContractArtists/);
  assert.deepEqual(original.keywords, ["tota"]);
  console.log("Optional Excel contracts: default legacy payload, free keyword search, participant selection, capability guard and unchanged other formats: PASS");
} finally { delete globalThis.__excelContractsQa; }
