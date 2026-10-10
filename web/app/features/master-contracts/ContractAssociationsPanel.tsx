"use client";

import { useEffect, useState } from "react";
import { AudioLines, ChevronDown, ChevronLeft, ChevronRight, Link2, RefreshCw, Search } from "lucide-react";
import styles from "./MasterContractsModule.module.css";
import { associationScope, associationGroupState, groupedAssociations, pendingAssociationCodes, type Association, type AssociationChoice, type AssociationGroup, type AssociationValidation } from "./associationLogic";

export type { AssociationChoice, AssociationValidation } from "./associationLogic";
type Props = {
  isrc: string; version: number; canEdit: boolean; choices: AssociationChoice[];
  onChange: (choices: AssociationChoice[]) => void;
  onValidationChange: (state: AssociationValidation) => void;
};
const labels: Record<string, string> = { automatic: "Automático", confirmed: "Confirmado", pending: "Por validar", excluded: "Excluido", blocked: "No asignable" };

function AssociationTable({ groups, isrc, choices, canEdit, ugc = false, onDecide }: {
  groups: AssociationGroup[]; isrc: string; choices: AssociationChoice[]; canEdit: boolean; ugc?: boolean;
  onDecide: (group: AssociationGroup, decision: string) => void;
}) {
  const [page, setPage] = useState(0);
  const currentPage = Math.min(page, Math.max(0, Math.ceil(groups.length / 20) - 1));
  const pageItems = groups.slice(currentPage * 20, (currentPage + 1) * 20);
  const unique = (values: string[]) => [...new Set(values)];
  return <>
    <div className={styles.associationsScroll}>
      <table className={styles.associationsTable}>
        <thead><tr><th>{ugc ? "Relación" : "Validación"}</th><th>Código</th><th>Distribuidora / cuenta</th><th>Referencia</th><th>{ugc ? "ISRC informado" : "Evidencia"}</th></tr></thead>
        <tbody>{pageItems.map((group) => {
          const state = associationGroupState(group, choices);
          const decision = state.status === "confirmed" ? "included" : state.status === "excluded" ? "excluded" : state.status === "automatic" ? "automatic" : "pending";
          const isrcs = unique(group.items.flatMap((item) => item.isrcs));
          const shared = isrcs.some((value) => value !== isrc);
          const artTrack = group.items.every((item) => item.content_origins?.length === 1 && item.content_origins[0] === "Music / Art Track");
          return <tr key={group.scope}>
            <td>{ugc ? <span className={shared ? styles.associationsCount : styles.associationValid}>{shared ? "Compartido" : "Identificado"}</span>
              : canEdit ? <select className={styles.associationDecision} aria-label={`Validación ${group.code}`} title={labels[state.status]} value={decision} onChange={(event) => onDecide(group, event.target.value)}>
                <option value={state.automatic ? "automatic" : "pending"}>{state.automatic ? "Automático" : state.selectable || state.pending ? "Por validar" : "No asignable"}</option>
                <option value="included" disabled={!state.selectable}>Incluir</option><option value="excluded">Descartar</option>
                {decision === "pending" && state.automatic && <option value="pending" disabled>Por validar</option>}
              </select> : <span className={state.included || state.status === "excluded" ? styles.associationValid : styles.associationPending}>{labels[state.status]}</span>}</td>
            <td><small>{ugc ? "Video / UGC" : group.kind === "VIDEO" ? artTrack ? "Audio YouTube" : "Video" : group.kind === "TRACK" ? "ID de plataforma" : group.kind}</small><strong>{group.code}</strong></td>
            <td>{group.items.map((item) => <div className={styles.associationSource} key={item.key}>{item.source.toUpperCase()}<small>{item.account.replace(/_/g, " ")}</small></div>)}</td>
            <td>{unique(group.items.flatMap((item) => item.titles)).join(" / ") || "Sin título"}<small>{unique(group.items.flatMap((item) => item.artists)).join(" / ")}</small></td>
            <td>{ugc ? isrcs.map((value) => <small key={value}>{value}</small>) : <>{unique(group.items.map((item) => item.reason)).map((reason) => <small key={reason}>{reason}</small>)}{shared && <small>{isrcs.join(" · ")}</small>}</>}</td>
          </tr>;
        })}</tbody>
      </table>
    </div>
    <div className={styles.associationsPagination}>
      <span>{groups.length ? `${currentPage * 20 + 1}–${Math.min((currentPage + 1) * 20, groups.length)} de ${groups.length}` : "Sin coincidencias"}</span>
      <button type="button" className={styles.iconButton} title="Códigos anteriores" aria-label={ugc ? "Referencias UGC anteriores" : "Códigos anteriores"} disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}><ChevronLeft size={16} /></button>
      <button type="button" className={styles.iconButton} title="Códigos siguientes" aria-label={ugc ? "Referencias UGC siguientes" : "Códigos siguientes"} disabled={(currentPage + 1) * 20 >= groups.length} onClick={() => setPage(currentPage + 1)}><ChevronRight size={16} /></button>
    </div>
  </>;
}

export function ContractAssociationsPanel({ isrc, version, canEdit, choices, onChange, onValidationChange }: Props) {
  const [open, setOpen] = useState(false);
  const [ugcOpen, setUgcOpen] = useState(false);
  const [items, setItems] = useState<Association[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [kind, setKind] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setItems([]);
    void fetch(`/api/master-contracts/${encodeURIComponent(isrc)}/associations`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok) throw new Error(body.error || "No se pudieron verificar los códigos.");
        if (body.version !== version) throw new Error("La ficha cambió. Volvé a abrirla antes de elegir códigos.");
        setItems(body.items);
      })
      .catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "No se pudieron verificar los códigos."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [isrc, version, reload]);

  const pending = pendingAssociationCodes(items, choices).length;
  useEffect(() => { onValidationChange({ loading, pending, error }); }, [loading, pending, error, onValidationChange]);

  function decide(group: AssociationGroup, decision: string) {
    const state = associationGroupState(group, choices);
    if (!canEdit || (decision === "included" && !state.selectable)) return;
    const reason = [...new Set(group.items.map((item) => item.reason))].join("\n");
    if (decision === "included" && !state.automatic && !window.confirm(`${reason}\n\n¿Confirmás que ${group.code} corresponde al contrato de ${isrc}?`)) return;
    const scope = group.scope;
    const next = choices.filter((choice) => associationScope(choice.key) !== scope);
    if (decision === "included" || decision === "excluded") {
      for (const row of items.filter((value) => associationScope(value.key) === scope)) {
        next.push({ key: row.key, included: decision === "included", evidence_signature: row.evidence_signature });
      }
    }
    onChange(next);
  }

  const groups = groupedAssociations(items, choices);
  const filtered = groups.filter((group) => (!kind || group.kind === kind) && (!search || group.items.some((item) => `${item.code} ${item.source} ${item.account} ${item.titles.join(" ")} ${item.artists.join(" ")}`.toLocaleLowerCase().includes(search.toLocaleLowerCase()))))
    .sort((a, b) => Number(associationGroupState(b, choices).pending) - Number(associationGroupState(a, choices).pending));
  const associated = filtered.filter((group) => group.section === "associated");
  const ugc = filtered.filter((group) => group.section === "ugc");
  const associatedCount = groups.filter((group) => group.section === "associated").length;
  const ugcCount = groups.length - associatedCount;
  const tableKey = `${isrc}:${kind}:${search}:${reload}`;

  return <section className={styles.associationsBand}>
    <div className={styles.associationsHeading}>
      <button type="button" className={styles.associationsToggle} aria-expanded={open} aria-controls={`associated-${isrc}`} onClick={() => setOpen((value) => !value)}>
        <Link2 size={16} />Ver códigos asociados{open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
      </button>
      {!loading && !error && <span className={pending ? styles.associationPending : styles.associationsCount}>{pending ? `${pending} por validar` : "Validación completa"}</span>}
      {!loading && !error && <span className={styles.associationsCount}>{associatedCount} códigos</span>}
      {loading && <span className={styles.associationsCount}>Verificando...</span>}
      {!open && error && <span className={styles.associationPending}>No se pudo verificar</span>}
      {open && <button type="button" className={styles.iconButton} title="Actualizar códigos asociados" aria-label="Actualizar códigos asociados" disabled={loading} onClick={() => setReload((value) => value + 1)}><RefreshCw size={15} /></button>}
    </div>
    {open && <div id={`associated-${isrc}`}>
      {loading ? <p className={styles.auditLine} role="status">Verificando asociaciones...</p> : error ? <p className={styles.warning} role="alert">{error}</p> : items.length === 0 ? <p className={styles.auditLine}>Sin otros códigos asociados en los statements publicados.</p> : <>
        <div className={styles.associationsControls}>
          <select aria-label="Tipo de código asociado" value={kind} onChange={(event) => setKind(event.target.value)}>
            <option value="">Todos los códigos</option><option value="UPC">UPC</option><option value="VIDEO">Video / audio</option><option value="TRACK">ID de plataforma</option>
          </select>
          <label><Search size={14} /><input aria-label="Buscar código asociado" placeholder="Buscar código" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        </div>
        <h4 className={styles.associationsSectionTitle}>Asociados del contrato</h4>
        <AssociationTable key={`associated:${tableKey}`} groups={associated} isrc={isrc} choices={choices} canEdit={canEdit} onDecide={decide} />
        {ugcCount > 0 && <div className={styles.associationsUgc}>
          <div className={styles.associationsHeading}>
            <button type="button" className={styles.associationsToggle} aria-expanded={ugcOpen} aria-controls={`ugc-${isrc}`} onClick={() => setUgcOpen((value) => !value)}>
              <AudioLines size={16} />Referencias UGC<span className={styles.associationsCount}>{ugcCount}</span>{ugcOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
            </button>
          </div>
          {ugcOpen && <div id={`ugc-${isrc}`}><AssociationTable key={`ugc:${tableKey}`} groups={ugc} isrc={isrc} choices={choices} canEdit={false} ugc onDecide={decide} /></div>}
        </div>}
      </>}
    </div>}
  </section>;
}
