"use client";

import { useEffect, useState } from "react";
import styles from "./MasterContractsModule.module.css";
import type { Allocation, MasterAgreement } from "./contractLogic";
import { applyDistributionContract, distributionContractLabel, type DistributionContract } from "./distributionContractLogic";

export function DistributionContractPicker({ agreement, allocation, contracts, canEdit, onChange }: {
  agreement: MasterAgreement; allocation: Allocation; contracts: DistributionContract[];
  canEdit: boolean; onChange: (agreement: MasterAgreement) => void;
}) {
  const [selected, setSelected] = useState(String(agreement.distribution_contract_number || ""));
  useEffect(() => setSelected(String(agreement.distribution_contract_number || "")), [agreement.id, agreement.distribution_contract_number]);
  const contract = contracts.find((item) => String(item.number) === selected);
  return <section className={styles.band}>
    <div className={styles.sectionHeading}><h2>Contrato de distribución</h2></div>
    <div className={styles.artistFormFields}>
      <label>Contrato existente<select disabled={!canEdit || contracts.length === 0} value={selected} onChange={(event) => setSelected(event.target.value)}>
        <option value="">Seleccionar contrato</option>
        {contracts.map((item) => <option key={item.number} value={item.number}>{distributionContractLabel(item)}</option>)}
      </select></label>
    </div>
    {contracts.length === 0 && <p className={styles.fieldHint}>Todavía no hay contratos de distribución. Podés cargar el reparto a mano o crear uno desde Contratos de distribución.</p>}
    {canEdit && contract && <div className={styles.actions}><button type="button" className={styles.secondaryButton}
      onClick={() => onChange(applyDistributionContract(agreement, allocation, contract))}>Aplicar contrato</button></div>}
    {agreement.distribution_contract_number && <p className={styles.fieldHint}>Contrato aplicado: nro. {agreement.distribution_contract_number} · versión {agreement.distribution_contract_version}.
      {canEdit && <button type="button" className={styles.isrcButton} onClick={() => onChange({ ...agreement,
        distribution_contract_number: undefined, distribution_contract_version: undefined })}> Desvincular y conservar los datos</button>}
    </p>}
  </section>;
}
