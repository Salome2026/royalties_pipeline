import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";
const directory = new URL("../app/features/master-contracts/", import.meta.url);
const source = (name) => readFileSync(new URL(name, directory), "utf8");
const compile = (text) => ts.transpileModule(text, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText;
const uri = (text) => `data:text/javascript;base64,${Buffer.from(text).toString("base64")}`;
const logicUrl = uri(compile(source("contractLogic.ts")));
const editor = source("MasterAgreementsEditor.tsx");
const visible = editor.slice(editor.indexOf("export function visibleAgreements"), editor.indexOf("export function MasterAgreementsEditor"));
const bulkUrl = uri(compile(source("bulkContractLogic.ts")).replace('"./contractLogic"', JSON.stringify(logicUrl)).replace('"./MasterAgreementsEditor"', JSON.stringify(uri(compile(visible)))));
const { applyContractModel, closingErrors, participantDifference, modelErrors, participantSignature, matchingModelPeriods } = await import(bulkUrl);
const allocation = { principal: "La Juntada", principal_percent: 20, indyana_percent: 70, apply_guest_contracts: false,
  participants: [{ artist: "Sergio Torres", percent: 10, internal_contract_indyana_percent: null }] };
const agreement = { id: "original", label: "Contrato individual", commercialization: "distribution", owners: [], effective_from: "2025-01-01", effective_until: null, allocation };
const detail = { isrc: "MODEL", version: 2, split: { ...allocation, agreements: [agreement], notes: "Nota del modelo", agreement_confirmed: true },
  first_statement_date: "2025-01-01", artist_suggestions: { artists: ["La Juntada", "Sergio Torres"] } };
const target = structuredClone(detail);
target.isrc = "TARGET";
target.split.notes = "Nota individual";
target.split.code_association_overrides = [{ key: '["VIDEO","individual","fuga","indyana_records"]', included: false, evidence_signature: "target" }];
target.split.agreements = [
  { ...structuredClone(agreement), id: "history", effective_from: "2024-01-01", effective_until: "2024-12-31" },
  { ...structuredClone(agreement), id: "current", effective_from: "2025-06-01", effective_until: null, allocation: { ...allocation, catalog_participant_exclusions: ["Excluido manualmente"] } },
];
const before = structuredClone(target), modelBefore = structuredClone(detail);
const result = applyContractModel(detail, 0, target, 1, "2025-06-01", null);
assert.deepEqual(target, before); assert.deepEqual(detail, modelBefore);
assert.deepEqual(result.agreements[0], target.split.agreements[0]);
assert.equal(result.agreements[1].id, "current"); assert.equal(result.agreements[1].effective_from, "2025-06-01");
assert.equal(result.notes, "Nota individual");
assert.deepEqual(result.code_association_overrides, target.split.code_association_overrides);
assert.deepEqual(result.agreements[1].allocation.catalog_participant_exclusions, ["Excluido manualmente"]);
assert.deepEqual(closingErrors(result), []);
assert.deepEqual(participantDifference(detail, 0, target, 1), { missing: [], extra: [] });
const additional = structuredClone(target); additional.artist_suggestions.artists.push("Invitado distinto");
assert.deepEqual(participantDifference(detail, 0, additional, 1).missing, ["Invitado distinto"]);
const missingDate = applyContractModel(detail, 0, target, 1, null, null);
assert(closingErrors(missingDate).includes("Falta definir la vigencia desde."));
assert(closingErrors(applyContractModel(detail, 0, target, 1, "2024-06-01", null)).some((s) => s.includes("superponen")));
assert(modelErrors({ ...detail, version: 0 }, 0).length);
assert(modelErrors({ ...detail, participant_proposal: { added: { x: ["Nuevo"] } } }, 0).length);
const distribution = structuredClone(detail);
distribution.split.agreements[0] = { ...agreement, allocation_model: "pools", master_pool_percent: 70,
  distribution_recipients: [{ name: "Indyana", percent: 40 }, { name: "Socio", percent: 30 }] };
const copiedDistribution = applyContractModel(distribution, 0, target, 1, "2025-06-01", null);
assert.deepEqual(copiedDistribution.agreements[1].distribution_recipients, distribution.split.agreements[0].distribution_recipients);
assert.deepEqual(closingErrors(copiedDistribution), []);
const copiedFlat = applyContractModel(detail, 0, { ...target, split: copiedDistribution }, 1, "2025-06-01", null);
assert.equal(copiedFlat.agreements[1].distribution_recipients, undefined);
// No pre-existing saved contract is required when defining a group contract.
const fresh = { ...structuredClone(detail), version: 0, closed: false };
assert.deepEqual(modelErrors(fresh, 0, true), []);
assert(modelErrors(fresh, 0).length);
const closed = { ...structuredClone(detail), isrc: "CLOSED-OUTSIDE-SELECTION", closed: true };
const reordered = structuredClone(target);
reordered.artist_suggestions.artists = ["SERGIO TÓRRES", "la juntada"];
assert.equal(participantSignature(reordered, 1), participantSignature(closed));
assert.deepEqual(matchingModelPeriods(closed, participantSignature(reordered, 1)), [0]);
assert.deepEqual(matchingModelPeriods({ ...closed, closed: false }, participantSignature(reordered, 1)), []);
assert.deepEqual(matchingModelPeriods(closed, participantSignature(additional, 1)), []);
const otherProject = structuredClone(closed); otherProject.split.principal = "Otro proyecto";
otherProject.split.agreements[0].allocation.principal = "Otro proyecto";
assert.deepEqual(matchingModelPeriods(otherProject, participantSignature(target, 1)), []);
assert.deepEqual(applyContractModel(fresh, 0, target, 1, "2025-06-01", null).code_association_overrides, target.split.code_association_overrides);
console.log("Bulk contracts: isolated economics, individual associations and notes, period preservation, participant mismatch, closure gates and saved model: PASS");
