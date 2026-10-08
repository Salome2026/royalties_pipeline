"use client";

import { ChevronDown, Plus, Trash2 } from "lucide-react";
import styles from "./MasterContractsModule.module.css";
import { nextAgreementStart, periodBoundary, type MasterAgreement } from "./contractLogic";
export type { MasterAgreement } from "./contractLogic";

export type MasterOwner = { name: string; percent: number | null };

type LegacySplit = {
  master_type: string;
  other_master_artist?: string | null;
  effective_from: string | null;
};

const numberOrNull = (value: string) => value.trim() === "" ? null : Number(value);

export function visibleAgreements(agreements: MasterAgreement[] | undefined, split: LegacySplit, firstStatementDate: string | null): MasterAgreement[] {
  if (agreements?.length) return agreements;
  const kind = split.master_type;
  const isDistribution = kind === "distribution" || kind === "distribution_mawz";
  const isMaster = ["indyana_master", "mawz_master", "indyana_and_other", "mawz_and_other"].includes(kind);
  const primary = kind.startsWith("mawz") || kind === "distribution_mawz" ? "Mawz" : "Indyana";
  return [{
    id: "principal", label: "Contrato principal",
    commercialization: isDistribution ? "distribution" : isMaster ? "master" : "pending",
    owners: isMaster ? [
      { name: primary, percent: null },
      ...((kind === "indyana_and_other" || kind === "mawz_and_other") && split.other_master_artist
        ? [{ name: split.other_master_artist, percent: null }] : []),
    ] : [],
    effective_from: split.effective_from || firstStatementDate,
    effective_until: null,
  }];
}

export function MasterAgreementsEditor({ agreements, canEdit, artistOptions, firstStatementDate, openId, onOpenChange, onChange }: {
  agreements: MasterAgreement[];
  canEdit: boolean;
  artistOptions: string[];
  firstStatementDate: string | null;
  openId: string | null;
  onOpenChange: (id: string | null) => void;
  onChange: (agreements: MasterAgreement[]) => void;
}) {

  function update(index: number, patch: Partial<MasterAgreement>) {
    onChange(agreements.map((item, position) => position === index ? { ...item, ...patch } : item));
  }

  function updateOwner(index: number, ownerIndex: number, patch: Partial<MasterOwner>) {
    update(index, { owners: agreements[index].owners.map((owner, position) => position === ownerIndex ? { ...owner, ...patch } : owner) });
  }

  function addAgreement() {
    if (agreements.length >= 20) return;
    const id = `contract-${crypto.randomUUID()}`;
    onChange([...agreements, {
      id, label: `Contrato ${agreements.length + 1}`, commercialization: "pending", owners: [],
      effective_from: nextAgreementStart(agreements), effective_until: null,
    }]);
    onOpenChange(id);
  }

  const ownerOptions = [...new Set(["Indyana", "Mawz", ...artistOptions])];

  return (
    <section className={styles.band}>
      <div className={styles.agreementList}>
        {agreements.map((agreement, index) => {
          const open = agreement.id === openId;
          const ownerTotal = agreement.owners.reduce((sum, owner) => sum + (owner.percent || 0), 0);
          return <div className={styles.agreementItem} key={agreement.id}>
            <div className={styles.agreementRow}>
              <button type="button" className={styles.agreementToggle} aria-expanded={open} onClick={() => onOpenChange(open ? null : agreement.id)}>
                <ChevronDown size={17} className={open ? styles.chevronOpen : ""} />
                <strong>{agreement.label || (index === 0 ? "Contrato principal" : `Contrato ${index + 1}`)}</strong>
                <span>{agreement.commercialization === "master" ? "Master" : agreement.commercialization === "distribution" ? "Distribución" : "Por definir"}</span>
              </button>
              {canEdit && index === 0 && <button type="button" className={styles.iconButton} title="Agregar contrato" aria-label="Agregar contrato" disabled={agreements.length >= 20} onClick={addAgreement}><Plus size={18} /></button>}
              {canEdit && index > 0 && <button type="button" className={styles.iconButton} title={`Quitar ${agreement.label}`} aria-label={`Quitar ${agreement.label}`} onClick={() => {
                if (!window.confirm(`¿Quitar ${agreement.label}?`)) return;
                onChange(agreements.filter((_, position) => position !== index));
                if (open) onOpenChange(null);
              }}><Trash2 size={16} /></button>}
            </div>
            {open && <div className={styles.agreementBody}>
              <div className={styles.agreementFields}>
                {index > 0 && <label>Nombre del contrato<input disabled={!canEdit} maxLength={120} value={agreement.label} onChange={(event) => update(index, { label: event.target.value })} /></label>}
                <label>Comercialización
                  <select disabled={!canEdit} value={agreement.commercialization} onChange={(event) => {
                    const commercialization = event.target.value as MasterAgreement["commercialization"];
                    update(index, { commercialization, owners: commercialization === "master" ? agreement.owners.length ? agreement.owners : [{ name: "", percent: null }] : [] });
                  }}>
                    <option value="pending">Por definir</option>
                    <option value="distribution">Distribución</option>
                    <option value="master">Master</option>
                  </select>
                </label>
                <label>Vigente desde
                  <input type="date" disabled={!canEdit} value={periodBoundary(agreement.effective_from) || ""} onInput={(event) => update(index, { effective_from: event.currentTarget.value || null })} />
                </label>
                <label>Vigente hasta
                  <input type="date" disabled={!canEdit} value={periodBoundary(agreement.effective_until, true) || ""} onInput={(event) => update(index, { effective_until: event.currentTarget.value || null })} />
                  {!agreement.effective_until && <span className={styles.fieldHint}>Actual</span>}
                </label>
              </div>
              {index === 0 && firstStatementDate && <p className={styles.fieldHint}>Primer statement registrado: {firstStatementDate}</p>}
              {agreement.commercialization === "master" && <div className={styles.ownerSection}>
                <div className={styles.sectionHeading}><h3>Titulares del master</h3><span>Total master {ownerTotal.toLocaleString("es-AR", { maximumFractionDigits: 2 })}%</span></div>
                {agreement.owners.map((owner, ownerIndex) => <div className={styles.ownerRow} key={ownerIndex}>
                  <label>Titular<input list={`master-owner-options-${agreement.id}`} disabled={!canEdit} value={owner.name} onChange={(event) => updateOwner(index, ownerIndex, { name: event.target.value })} placeholder="Indyana, Mawz u otro" /></label>
                  <label>Porcentaje<input type="number" min="0" max="100" step="0.01" inputMode="decimal" disabled={!canEdit} value={owner.percent ?? ""} onChange={(event) => updateOwner(index, ownerIndex, { percent: numberOrNull(event.target.value) })} /></label>
                  {canEdit && agreement.owners.length > 1 && <button type="button" className={styles.iconButton} title="Quitar titular" aria-label="Quitar titular" onClick={() => update(index, { owners: agreement.owners.filter((_, position) => position !== ownerIndex) })}><Trash2 size={16} /></button>}
                </div>)}
                <datalist id={`master-owner-options-${agreement.id}`}>{ownerOptions.map((name) => <option key={name} value={name} />)}</datalist>
                {canEdit && <button type="button" className={styles.addButton} disabled={agreement.owners.length >= 12} onClick={() => update(index, { owners: [...agreement.owners, { name: "", percent: null }] })}><Plus size={16} /> Agregar titular</button>}
              </div>}
            </div>}
          </div>;
        })}
      </div>
    </section>
  );
}
