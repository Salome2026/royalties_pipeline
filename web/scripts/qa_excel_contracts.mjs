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
  const enriched = { ...original, include_contracts: true, contract_columns: "matching" };
  const associated = { ...enriched, keywords: ["QT5M52695720"], include_associated: true };
  for (const output of ["excel", "google_sheet"]) {
    for (const payload of [original, enriched, associated]) {
      await api.createRoyaltyReportJob(payload, output);
      assert.deepEqual(JSON.parse(calls.at(-1).options.body), { ...payload, output });
    }
    await api.createRoyaltyReportJob({ ...original, include_associated: true }, output);
    assert.deepEqual(JSON.parse(calls.at(-1).options.body), { ...original, output });
  }
  await api.createRoyaltyReportJob(associated, "executive_pdf");
  assert.deepEqual(JSON.parse(calls.at(-1).options.body), { ...original, keywords: associated.keywords, output: "executive_pdf" });
  const ui = fs.readFileSync(new URL("../app/features/royalties/RoyaltyReportModule.tsx", import.meta.url), "utf8");
  assert.match(ui, /\[includeContracts, setIncludeContracts\] = useState\(false\)/);
  assert.match(ui, /royalty_include_contracts/);
  assert.match(ui, /royalty_include_associated/);
  assert.match(ui, /disabled=\{!options\?\.excel_contracts_supported\}/);
  assert.match(ui, /Coincidentes con la búsqueda/);
  assert.match(ui, /Todos los involucrados/);
  assert.ok(ui.indexOf('id="royalty_include_contracts"') > ui.indexOf('id="royalty_period"'));
  assert.match(ui, /if \(contractual\) \{\s+const selection = prepareContractArtists/);
  assert.deepEqual(original.keywords, ["tota"]);
  console.log("Optional contracts and associates in Excel and Google Sheets: PASS");
} finally { delete globalThis.__excelContractsQa; }
