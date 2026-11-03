"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { ArrowLeft, FilePenLine, Plus, RefreshCw, Search } from "lucide-react";
import styles from "./MasterContractsModule.module.css";
import { PoolsAllocationEditor } from "./PoolsAllocationEditor";
import { beneficiaryKey, type Allocation, type MasterAgreement } from "./contractLogic";
import { distributionContractLabel, distributionTemplateErrors, type DistributionContract } from "./distributionContractLogic";

type Draft = { number: number | null; label: string; sublabel: string; notes: string; version: number; agreement: MasterAgreement };
const blankAllocation: Allocation = { principal: "", indyana_percent: null, principal_percent: null, participants: [], apply_guest_contracts: false };
const blankDraft = (): Draft => ({ number: null, label: "", sublabel: "", notes: "", version: 0,
  agreement: { id: "distribution-template", label: "Reparto inicial", commercialization: "distribution", allocation_model: "pools",
    master_pool_percent: null, company_name: "Indyana", owners: [], effective_from: null, effective_until: null } });
function contractDraft(item: DistributionContract): Draft {
  const draft = blankDraft();
  return { number: item.number, label: item.label, sublabel: item.sublabel, notes: item.notes, version: item.version,
    agreement: { ...draft.agreement, master_pool_percent: item.master_pool_percent, company_name: item.company_name,
      distribution_recipients: structuredClone(item.distribution_recipients) } };
}
type Message = { type: "ok" | "error"; text: string };

export function DistributionContractsPanel({ canEdit, onBack, onMessage }: {
  canEdit: boolean; onBack: () => void; onMessage: (message: Message | null) => void;
}) {
  const [items, setItems] = useState<DistributionContract[]>([]);
  const [query, setQuery] = useState("");
  const [draft, setDraft] = useState<Draft>(blankDraft);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/master-contract-distribution", { cache: "no-store" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "No se pudieron cargar los contratos de distribución.");
      setItems(data.items); setLoaded(true);
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudieron cargar los contratos." });
    } finally { setLoading(false); }
  }, [onMessage]);
  useEffect(() => { void load(); }, [load]);
  const selected = items.find((item) => item.number === draft.number);
  const changed = selected ? JSON.stringify(draft) !== JSON.stringify(contractDraft(selected))
    : JSON.stringify(draft) !== JSON.stringify(blankDraft());
  const filtered = useMemo(() => items.filter((item) => beneficiaryKey(distributionContractLabel(item)).includes(beneficiaryKey(query))), [items, query]);
  const errors = distributionTemplateErrors(draft.agreement);
  const duplicate = items.find((item) => item.number !== draft.number && beneficiaryKey(item.label) === beneficiaryKey(draft.label)
    && beneficiaryKey(item.sublabel) === beneficiaryKey(draft.sublabel));
  if (duplicate) errors.push(`El sello y subsello ya pertenecen al contrato nro. ${duplicate.number}. Usá un subsello diferente.`);
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!canEdit || saving || !loaded || errors.length || !draft.label.trim()) return;
    setSaving(true);
    try {
      const response = await fetch("/api/master-contract-distribution", { method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ number: draft.number, label: draft.label, sublabel: draft.sublabel, notes: draft.notes,
          master_pool_percent: draft.agreement.master_pool_percent, company_name: draft.agreement.company_name,
          distribution_recipients: draft.agreement.distribution_recipients ?? null, expected_version: draft.version }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "No se pudo guardar el contrato.");
      const saved = data as DistributionContract;
      setItems((current) => [...current.filter((item) => item.number !== saved.number), saved].sort((a, b) => a.number - b.number));
      setDraft(contractDraft(saved));
      onMessage({ type: "ok", text: `Contrato nro. ${saved.number} guardado. Ya podés aplicarlo a los temas de distribución.` });
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo guardar el contrato." });
    } finally { setSaving(false); }
  }
  const leave = (action: () => void) => { if (!changed || window.confirm("Hay cambios sin guardar. ¿Continuar?")) action(); };
  return <section className={styles.workspace}>
    <header className={styles.detailHeader}>
      <button type="button" className={styles.iconButton} aria-label="Volver a contratos" disabled={saving} onClick={() => leave(onBack)}><ArrowLeft size={19} /></button>
      <div className={styles.heading}><span>Contratos</span><h1>Contratos de distribución</h1><p>Guardá las bolsas y los destinatarios para reutilizarlos en los temas.</p></div>
      <button type="button" className={styles.iconButton} aria-label="Actualizar contratos" disabled={loading || saving} onClick={() => leave(() => void load())}><RefreshCw size={18} /></button>
    </header>
    <div className={styles.artistLayout}>
      <div className={styles.artistList}>
        <div className={styles.artistListTools}>
          <div className={styles.searchBox}><Search size={18} /><input aria-label="Buscar número, sello o subsello" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Número, sello o subsello" /></div>
          {canEdit && <button type="button" className={styles.iconButton} aria-label="Nuevo contrato de distribución" disabled={saving} onClick={() => leave(() => setDraft(blankDraft()))}><Plus size={18} /></button>}
        </div>
        <div className={styles.listMeta}><span>{loading ? "Cargando..." : `${filtered.length} contratos`}</span></div>
        <div className={styles.artistRows}>{filtered.map((item) => <button type="button" key={item.number} disabled={saving}
          className={`${styles.artistRow} ${draft.number === item.number ? styles.artistRowSelected : ""}`} onClick={() => leave(() => setDraft(contractDraft(item)))}>
          <span><strong>Nro. {item.number} · {item.label}</strong><small>{item.sublabel || "Sin subsello"}</small></span>
          <span className={styles.artistPercent}>{item.master_pool_percent.toLocaleString("es-AR", { maximumFractionDigits: 4 })}%<small>Comercialización</small></span>
        </button>)}{!loading && filtered.length === 0 && <p className={styles.artistEmpty}>No hay contratos para esta búsqueda.</p>}</div>
      </div>
      <form className={styles.artistForm} onSubmit={(event) => void save(event)}>
        <div className={styles.sectionHeading}><h2>{draft.number ? `Contrato nro. ${draft.number}` : "Nuevo contrato"}</h2><span>{draft.version ? `Versión ${draft.version}` : "Sin guardar"}</span></div>
        <div className={styles.artistFormFields}>
          <label>Número<input readOnly value={draft.number ?? "Automático al guardar"} /></label>
          <label>Sello<input required maxLength={200} disabled={!canEdit || saving} value={draft.label} onChange={(event) => setDraft({ ...draft, label: event.target.value })} /></label>
          <label>Subsello (opcional)<input maxLength={200} disabled={!canEdit || saving} value={draft.sublabel} onChange={(event) => setDraft({ ...draft, sublabel: event.target.value })} /></label>
        </div>
        <PoolsAllocationEditor initialOnly agreement={draft.agreement} allocation={blankAllocation} canEdit={canEdit && !saving}
          artistOptions={[]} artistContracts={[]} distributionRecipientsSupported onEditArtist={() => {}}
          onChange={(agreement) => setDraft({ ...draft, agreement })} />
        {changed && errors.map((error) => <p className={styles.warning} key={error}>{error}</p>)}
        <label className={styles.notesLabel}>Notas<textarea rows={3} maxLength={3000} disabled={!canEdit || saving} value={draft.notes} onChange={(event) => setDraft({ ...draft, notes: event.target.value })} /></label>
        <p className={styles.fieldHint}>Al aplicar el contrato se completan estos campos. Cada tema conserva su reparto y su vigencia.</p>
        {selected && <p className={styles.auditLine}>Último guardado: {selected.updated_at} por {selected.updated_by}.</p>}
        {canEdit && <div className={styles.actions}><button type="submit" className={styles.primaryButton} disabled={!loaded || saving || !changed || !draft.label.trim() || errors.length > 0}><FilePenLine size={16} />{saving ? "Guardando..." : "Guardar contrato"}</button></div>}
      </form>
    </div>
  </section>;
}
