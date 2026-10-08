import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../app/features/master-contracts/contractLogic.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const logic = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
const allocation = { principal: "La Juntada", indyana_percent: 70, principal_percent: 10,
  apply_guest_contracts: true, participants: [
    { artist: "Aneley", percent: 10, internal_contract_indyana_percent: 50 },
    { artist: "Onda Sabanera", percent: 10, internal_contract_indyana_percent: null },
  ] };
const first = { id: "principal", label: "Principal", commercialization: "master", owners: [{ name: "Indyana", percent: 70 }],
  effective_from: "2026-01-01", effective_until: "2026-10-31" };
const second = { ...first, id: "second", label: "Segundo", effective_from: "2026-11-01", effective_until: null };
assert.deepEqual(logic.allocationTotals(first, allocation), { master: 70, participation: 30, general: 100 });
assert.deepEqual(logic.contractErrors([second, first], allocation), []);
assert.equal(logic.contractErrors([first, { ...second, effective_from: "2026-10-31" }], allocation).length, 1);
assert.equal(logic.contractErrors([{ ...first, effective_until: null }, second], allocation).length, 1);
assert.equal(logic.contractErrors([{ ...first, owners: [{ name: "Indyana", percent: 100 }] }], allocation).length, 1);
assert.equal(logic.periodBoundary("2026-02-30"), null);
assert.equal(logic.periodBoundary("2024-02", true), "2024-02-29");
const monthly = [{ statement_month: "2026-10", amount_usd: 100 }, { statement_month: "2026-11", amount_usd: 200 }];
for (const timezone of ["UTC", "America/New_York", "America/Argentina/Buenos_Aires", "Pacific/Auckland"]) {
  process.env.TZ = timezone;
  assert.equal(logic.nextAgreementStart([first]), "2026-11-01");
  assert.equal(logic.agreementIncome(first, monthly, "2026-12-01"), 100);
  assert.equal(logic.agreementIncome(second, monthly, "2026-12-01"), 200);
  assert.equal(logic.agreementIncome({ ...first, effective_until: "2026-10" }, monthly, "2026-12-01"), 100);
}
assert.equal(logic.nextAgreementStart([second]), null);
assert.equal(logic.agreementIncome({ ...first, effective_from: null }, monthly, "2026-12-01"), null);
assert.equal(logic.agreementIncome(second, monthly, "2026-10-08"), null);
const preview = logic.previewAllocation(first, allocation, 1000);
assert.deepEqual(preview.map((row) => row.amount), [750, 100, 50, 100]);
assert.equal(preview.reduce((sum, row) => sum + row.amount, 0), 1000);
const other = { ...second, allocation: { ...allocation, principal_percent: 20, participants: [allocation.participants[0]] } };
assert.equal(logic.agreementAllocation(other, allocation).principal_percent, 20);
assert.equal(logic.agreementAllocation(first, allocation).principal_percent, 10);
assert.equal(allocation.principal_percent, 10);
assert.equal(logic.previewAllocation({ ...first, owners: [{ name: "Mawz", percent: 70 }] }, allocation, 1000).find((row) => row.artist === "Mawz").amount, 700);
assert.equal(logic.previewAllocation({ ...first, owners: [{ name: "Indyana", percent: 100 }] }, allocation, 1000), null);
console.log("Contract periods, combined percentages, isolated allocations and preview conservation: PASS");
