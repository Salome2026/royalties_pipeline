import { agreementAllocation, beneficiaryKey, contractErrors, previewAllocation, type MasterAgreement } from "./contractLogic";
import { visibleAgreements } from "./MasterAgreementsEditor";
import type { ContractDetail, Split } from "./MasterContractsModule";

export type ContractModel = Pick<ContractDetail, "isrc" | "title" | "split" | "version" | "closed" | "first_statement_date" | "participant_proposal"> & {
  artist_suggestions: Pick<ContractDetail["artist_suggestions"], "artists">;
};

export function detailAgreements(detail: ContractModel) {
  return visibleAgreements(detail.split.agreements, detail.split, detail.first_statement_date);
}

// Only economic terms travel. Identity, associations, notes, periods and other agreements belong to the target.
export function applyContractModel(model: ContractModel, modelIndex: number, target: ContractDetail, targetIndex: number,
  from: string | null, until: string | null): Split {
  const source = detailAgreements(model)[modelIndex];
  const agreements = structuredClone(detailAgreements(target));
  if (!source || !agreements[targetIndex]) throw new Error("Elegí un contrato válido.");
  const allocation = structuredClone(agreementAllocation(source, model.split));
  allocation.catalog_participant_exclusions = agreementAllocation(agreements[targetIndex], target.split).catalog_participant_exclusions;
  agreements[targetIndex] = {
    ...agreements[targetIndex],
    commercialization: source.commercialization, allocation_model: source.allocation_model,
    contract_kind: source.contract_kind, master_pool_percent: source.master_pool_percent,
    company_name: source.company_name, owner_split_mode: source.owner_split_mode,
    distribution_recipients: structuredClone(source.distribution_recipients),
    owners: structuredClone(source.owners), allocation,
    effective_from: from, effective_until: until,
  };
  return { ...structuredClone(target.split), agreements, agreement_confirmed: true };
}

export function modelErrors(model: ContractModel, index: number, draft = false): string[] {
  const agreement = detailAgreements(model)[index];
  if (!draft && !model.version) return ["Guardá primero el contrato que querés usar como modelo."];
  if (!draft && Object.keys(model.participant_proposal?.added || {}).length) return ["Revisá y guardá los participantes del modelo antes de aplicarlo."];
  if (!agreement || !previewAllocation(agreement, agreementAllocation(agreement, model.split), 100))
    return ["El modelo debe tener un reparto completo que sume 100%."];
  return contractErrors([agreement], model.split);
}

export function participantSignature(detail: ContractModel, index = 0): string {
  const allocation = agreementAllocation(detailAgreements(detail)[index], detail.split);
  const exclusions = new Set((allocation.catalog_participant_exclusions || []).map(beneficiaryKey));
  return JSON.stringify([...new Set([...(detail.artist_suggestions?.artists || []), allocation.principal,
    ...allocation.participants.map((p) => p.artist)].map(beneficiaryKey).filter((name) => name && !exclusions.has(name)))].sort());
}

export function matchingModelPeriods(model: ContractModel, signature: string): number[] {
  if (!model.closed) return [];
  return detailAgreements(model).flatMap((_, index) => participantSignature(model, index) === signature && !modelErrors(model, index).length ? [index] : []);
}

export function participantDifference(model: ContractModel, modelIndex: number, target: ContractDetail, targetIndex: number) {
  const source = agreementAllocation(detailAgreements(model)[modelIndex], model.split);
  const current = agreementAllocation(detailAgreements(target)[targetIndex], target.split);
  const names = [current.principal, ...current.participants.map((p) => p.artist), ...(target.artist_suggestions?.artists || [])];
  const exclusions = new Set((current.catalog_participant_exclusions || []).map(beneficiaryKey));
  const proposed = new Set([source.principal, ...source.participants.map((p) => p.artist),
    ...detailAgreements(model)[modelIndex].owners.map((owner) => owner.name)].map(beneficiaryKey));
  const missing = [...new Set(names.filter((name) => name && !exclusions.has(beneficiaryKey(name)) && !proposed.has(beneficiaryKey(name))))];
  const known = new Set(names.map(beneficiaryKey));
  const extra = [source.principal, ...source.participants.map((p) => p.artist)].filter((name) => name && !known.has(beneficiaryKey(name)));
  return { missing, extra: [...new Set(extra)] };
}

export function closingErrors(split: Split): string[] {
  const agreements = split.agreements || [];
  return [...contractErrors(agreements, split), ...agreements.flatMap((agreement) => [
    ...(!agreement.effective_from ? ["Falta definir la vigencia desde."] : []),
    ...(!previewAllocation(agreement, agreementAllocation(agreement, split), 100) ? ["Hay un contrato sin reparto completo."] : []),
  ])];
}
