import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
const directory = new URL("../app/features/master-contracts/", import.meta.url);
const compile = name => ts.transpileModule(readFileSync(new URL(name, directory), "utf8"), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText;
const uri = source => `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
const logicUrl = uri(compile("contractLogic.ts"));
const { repartition } = await import(logicUrl);
const { applyDistributionContract, distributionTemplateErrors } = await import(uri(compile("distributionContractLogic.ts").replace('"./contractLogic"', JSON.stringify(logicUrl))));
const allocation = { principal: "Artista", principal_percent: 60, indyana_percent: 30, apply_guest_contracts: false,
  principal_rule: { treatment: "direct" }, participants: [{ artist: "Invitado", percent: 10, internal_contract_indyana_percent: null,
    rule: { treatment: "artist_contract", retained_percent: 50, retained_recipient: "Indyana" } }], catalog_participant_exclusions: ["Excluido"] };
const agreement = { id: "individual", label: "Contrato principal", commercialization: "distribution", allocation_model: "pools",
  master_pool_percent: 30, company_name: "Indyana", owners: [], effective_from: "2026-01-01", effective_until: "2026-12-31", allocation };
const template = { number: 10010, version: 1, label: "Sello", sublabel: "Pop", master_pool_percent: 30,
  company_name: "Indyana", distribution_recipients: [{ name: "Indyana", percent: 20 }, { name: "Socio", percent: 10 }] };
const before = structuredClone(agreement), templateBefore = structuredClone(template);
const applied = applyDistributionContract(agreement, allocation, template);
assert.deepEqual(agreement, before); assert.deepEqual(template, templateBefore);
assert.deepEqual(applied.allocation, allocation);
assert.equal(applied.id, agreement.id); assert.equal(applied.label, agreement.label);
assert.equal(applied.effective_from, agreement.effective_from); assert.equal(applied.effective_until, agreement.effective_until);
assert.equal(applied.distribution_contract_number, 10010); assert.equal(applied.distribution_contract_version, 1);
assert.deepEqual(distributionTemplateErrors(applied), []);
assert.deepEqual(repartition(applied, allocation).map(row => [row.artist, row.percent]), [["Indyana", 25], ["Socio", 10], ["Artista", 60], ["Invitado", 5]]);
template.distribution_recipients[0].percent = 99;
assert.deepEqual(applied.distribution_recipients, templateBefore.distribution_recipients);
const single = applyDistributionContract(applied, allocation, { ...templateBefore, number: 10011, distribution_recipients: null, company_name: "Mawz" });
assert.equal(single.distribution_recipients, undefined); assert.equal(single.company_name, "Mawz");
assert.deepEqual(single.allocation, allocation);
assert.equal(repartition(single, allocation).find(row => row.artist === "Mawz").percent, 30);
const changedPool = applyDistributionContract(agreement, allocation, { ...templateBefore, master_pool_percent: 25,
  distribution_recipients: null });
assert.equal(changedPool.master_pool_percent, 25);
assert.deepEqual(changedPool.allocation, allocation); // No automatic redistribution of participants.
assert.equal(repartition(changedPool, allocation), null); // Operator completes remaining points as before.
assert.ok(distributionTemplateErrors({ ...agreement, master_pool_percent: null }).length);
assert.ok(distributionTemplateErrors({ ...agreement, company_name: " " }).length);
console.log("Distribution templates: copy initial fields, preserve participants/dates/treatments, snapshot recipients, single/multiple recipients and existing arithmetic: PASS");
