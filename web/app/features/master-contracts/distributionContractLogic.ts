import { distributionRecipientErrors, poolAgreement, type Allocation, type MasterAgreement, type ContractBeneficiary } from "./contractLogic";

export type DistributionContract = {
  number: number;
  label: string;
  sublabel: string;
  master_pool_percent: number;
  company_name: string;
  distribution_recipients: ContractBeneficiary[] | null;
  notes: string;
  version: number;
  updated_by: string;
  updated_at: string;
};

export const distributionContractLabel = (contract: DistributionContract) =>
  `Nro. ${contract.number} · ${contract.label}${contract.sublabel ? ` / ${contract.sublabel}` : ""}`;

export function applyDistributionContract(agreement: MasterAgreement, allocation: Allocation, contract: DistributionContract): MasterAgreement {
  return {
    ...poolAgreement(agreement, allocation),
    commercialization: "distribution", owners: [],
    master_pool_percent: contract.master_pool_percent,
    company_name: contract.company_name,
    distribution_recipients: contract.distribution_recipients == null ? undefined : structuredClone(contract.distribution_recipients),
    distribution_contract_number: contract.number,
    distribution_contract_version: contract.version,
  };
}

export function distributionTemplateErrors(agreement: MasterAgreement): string[] {
  if (agreement.master_pool_percent == null || !Number.isFinite(agreement.master_pool_percent)
    || agreement.master_pool_percent < 0 || agreement.master_pool_percent > 100)
    return ["Completá el porcentaje de comercialización entre 0 y 100."];
  if (agreement.distribution_recipients == null && !agreement.company_name?.trim())
    return ["Completá el destinatario de la comercialización."];
  return distributionRecipientErrors(agreement, true);
}
