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

const direct = { treatment: "direct" };
const simple = { ...first, allocation_model: "pools", contract_kind: "simple", master_pool_percent: 70,
  owner_split_mode: "percent", owners: [{ name: "Indyana", percent: 100 }] };
const solo = { principal: "Candu Dominguez", principal_percent: 30, indyana_percent: 70,
  apply_guest_contracts: true, principal_rule: direct, participants: [] };
assert.deepEqual(logic.previewAllocation(simple, solo, 100).map((row) => row.amount), [70, 30]);
const gusty = { ...simple, owners: [{ name: "Indyana", percent: 50 }, { name: "Gusty DJ", percent: 50 }] };
const gustyAllocation = { ...solo, principal: "GUSTY DJ" };
const gustyPreview = logic.previewAllocation(gusty, gustyAllocation, 100);
assert.deepEqual(gustyPreview.map((row) => row.amount), [35, 65]);
assert.equal(gustyPreview[1].origins.length, 2);
assert.equal(gusty.owners[0].percent, 50);
assert.equal(gusty.master_pool_percent, 70);
const project = { ...simple, contract_kind: "project", owner_split_mode: "equal", owners: [
  { name: "Indyana", percent: null }, { name: "Hernán", percent: null }, { name: "Claudio", percent: null }] };
const projectAllocation = { ...solo, principal: "La Juntada de los Artistas", principal_percent: 10,
  principal_rule: { treatment: "project_owners" }, participants: [
    { artist: "Sasha", percent: 10, internal_contract_indyana_percent: 70, rule: direct },
    { artist: "Sofi B", percent: 10, internal_contract_indyana_percent: null, rule: {
      treatment: "artist_contract", retained_percent: 70, retained_recipient: "Indyana", contract_artist: "Sofi B", contract_version: 2 } }] };
assert.deepEqual(logic.contractErrors([project], projectAllocation), []);
const projectPreview = logic.previewAllocation(project, projectAllocation, 100);
assert.deepEqual(projectPreview.map((row) => row.amount), [33.67, 26.67, 26.66, 10, 3]);
assert.equal(projectPreview[0].origins.length, 3);
assert.equal(projectPreview.some((row) => row.artist === "La Juntada de los Artistas"), false);
assert.equal(logic.previewAllocation(project, { ...projectAllocation, participants: [projectAllocation.participants[0],
  { ...projectAllocation.participants[1], rule: { treatment: "artist_contract", retained_percent: null, retained_recipient: "Indyana" } }] }, 100), null);
for (const amount of [0, .01, .02, .1, 1.005, 11646.10167091414, 1000000, -100, -.01]) {
  const preview = logic.previewAllocation(project, projectAllocation, amount);
  assert.equal(Math.round(preview.reduce((sum, row) => sum + row.amount, 0) * 100),
    Math.sign(amount) * Math.round(Math.abs(amount) * 100 + 1e-8));
}
assert.equal(logic.previewAllocation({ ...simple, owners: [{ name: "Indyana", percent: 70 }] }, solo, 100), null);
assert.equal(logic.contractErrors([{ ...gusty, owners: [{ name: "Indyana", percent: 80 }, { name: "Gusty", percent: 30 }] }], solo).length, 1);
assert.equal(logic.previewAllocation({ ...project, contract_kind: "simple" }, projectAllocation, 100), null);
const cloned = structuredClone(allocation);
const converted = logic.poolAgreement(first, allocation);
assert.equal(converted.master_pool_percent, 70);
assert.equal(converted.owners[0].percent, 100);
assert.deepEqual(logic.previewAllocation(converted, converted.allocation, 1000).map((row) => row.amount), preview.map((row) => row.amount));
assert.deepEqual(allocation, cloned);
const distribution = { ...simple, commercialization: "distribution", owners: [], company_name: "Mawz", master_pool_percent: 20 };
assert.deepEqual(logic.allocationTotals(distribution, { ...solo, principal_percent: 80 }), { master: 20, participation: 80, general: 100 });
assert.deepEqual(logic.previewAllocation(distribution, { ...solo, principal_percent: 80, indyana_percent: null }, 100).map((row) => row.amount), [20, 80]);
console.log("Two pools, master ownership, explicit nested contracts, project partners, legacy preservation and cent rounding: PASS");
