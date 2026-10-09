"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronLeft, ChevronRight, Link2, RefreshCw, Search } from "lucide-react";
import styles from "./MasterContractsModule.module.css";
import { associationScope, associationState, pendingAssociationCodes, type Association, type AssociationChoice, type AssociationValidation } from "./associationLogic";

export type { AssociationChoice, AssociationValidation } from "./associationLogic";
type Props = {
  isrc: string; version: number; canEdit: boolean; choices: AssociationChoice[];
  onChange: (choices: AssociationChoice[]) => void;
  onValidationChange: (state: AssociationValidation) => void;
};
const labels: Record<string, string> = { automatic: "Automático", confirmed: "Confirmado", pending: "Por validar", excluded: "Excluido", blocked: "No asignable" };

export function ContractAssociationsPanel({ isrc, version, canEdit, choices, onChange, onValidationChange }: Props) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Association[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [kind, setKind] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
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
        setPage(0);
      })
      .catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "No se pudieron verificar los códigos."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [isrc, version, reload]);

  const pending = pendingAssociationCodes(items, choices).length;
  useEffect(() => { onValidationChange({ loading, pending, error }); }, [loading, pending, error, onValidationChange]);

  function decide(item: Association, decision: string) {
    if (!canEdit || (decision === "included" && !item.selectable)) return;
    if (decision === "included" && !item.automatic && !window.confirm(`${item.reason}\n\n¿Confirmás que ${item.code} corresponde al contrato de ${isrc}?`)) return;
    const scope = associationScope(item.key);
    const next = choices.filter((choice) => associationScope(choice.key) !== scope);
    if (decision === "included" || decision === "excluded") {
      for (const row of items.filter((value) => associationScope(value.key) === scope)) {
        next.push({ key: row.key, included: decision === "included", evidence_signature: row.evidence_signature });
      }
    }
    onChange(next);
  }

  const filtered = items.filter((item) => (!kind || item.kind === kind) && (!search || `${item.code} ${item.source} ${item.account} ${item.titles.join(" ")}`.toLocaleLowerCase().includes(search.toLocaleLowerCase())))
    .sort((a, b) => Number(associationState(b, choices).pending) - Number(associationState(a, choices).pending));
  const pageItems = filtered.slice(page * 20, (page + 1) * 20);

  return <section className={styles.associationsBand}>
    <div className={styles.associationsHeading}>
      <button type="button" className={styles.associationsToggle} aria-expanded={open} aria-controls={`associated-${isrc}`} onClick={() => setOpen((value) => !value)}>
        <Link2 size={16} />Ver códigos asociados{open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
      </button>
      {!loading && !error && <span className={pending ? styles.associationPending : styles.associationsCount}>{pending ? `${pending} por validar` : "Validación completa"}</span>}
      {loading && <span className={styles.associationsCount}>Verificando...</span>}
      {!open && error && <span className={styles.associationPending}>No se pudo verificar</span>}
      {open && <button type="button" className={styles.iconButton} title="Actualizar códigos asociados" aria-label="Actualizar códigos asociados" disabled={loading} onClick={() => setReload((value) => value + 1)}><RefreshCw size={15} /></button>}
    </div>
    {open && <div id={`associated-${isrc}`}>
      {loading ? <p className={styles.auditLine} role="status">Verificando asociaciones...</p> : error ? <p className={styles.warning} role="alert">{error}</p> : items.length === 0 ? <p className={styles.auditLine}>Sin otros códigos asociados en los statements publicados.</p> : <>
        <div className={styles.associationsControls}>
          <select aria-label="Tipo de código asociado" value={kind} onChange={(event) => { setKind(event.target.value); setPage(0); }}>
            <option value="">Todos los códigos</option><option value="UPC">UPC</option><option value="VIDEO">Video / UGC</option><option value="TRACK">ID de plataforma</option>
          </select>
          <label><Search size={14} /><input aria-label="Buscar código asociado" placeholder="Buscar código" value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); }} /></label>
        </div>
        <div className={styles.associationsScroll}>
        <table className={styles.associationsTable}>
          <thead><tr><th>Validación</th><th>Código</th><th>Distribuidora / cuenta</th><th>Referencia</th><th>Evidencia</th></tr></thead>
          <tbody>{pageItems.map((item) => {
            const state = associationState(item, choices);
            const decision = state.status === "confirmed" ? "included" : state.status === "excluded" ? "excluded" : state.status === "automatic" ? "automatic" : "pending";
            return <tr key={item.key}>
              <td>{canEdit ? <select className={styles.associationDecision} aria-label={`Validación ${item.code} ${item.source} ${item.account}`} title={labels[state.status]} value={decision} onChange={(event) => decide(item, event.target.value)}>
                <option value={item.automatic ? "automatic" : "pending"}>{item.automatic ? "Automático" : item.selectable || item.requires_review ? "Por validar" : "No asignable"}</option>
                <option value="included" disabled={!item.selectable}>Incluir</option><option value="excluded">Descartar</option>
                {decision === "pending" && item.automatic && <option value="pending" disabled>Por validar</option>}
              </select> : <span className={state.included || state.status === "excluded" ? styles.associationValid : styles.associationPending}>{labels[state.status]}</span>}</td>
              <td><small>{item.kind === "VIDEO" ? "Video / UGC" : item.kind === "TRACK" ? "ID de plataforma" : item.kind}</small><strong>{item.code}</strong></td>
              <td>{item.source.toUpperCase()}<small>{item.account.replace(/_/g, " ")}</small></td>
              <td>{item.titles.join(" / ") || "Sin título"}<small>{item.artists.join(" / ")}</small>{item.isrcs.some((value) => value !== isrc) && <small>{item.isrcs.join(" · ")}</small>}</td>
              <td><small>{item.reason}</small></td>
            </tr>;
          })}</tbody>
        </table>
        </div>
        <div className={styles.associationsPagination}>
          <span>{filtered.length ? `${page * 20 + 1}–${Math.min((page + 1) * 20, filtered.length)} de ${filtered.length}` : "Sin coincidencias"}</span>
          <button type="button" className={styles.iconButton} title="Códigos anteriores" aria-label="Códigos anteriores" disabled={page === 0} onClick={() => setPage((value) => value - 1)}><ChevronLeft size={16} /></button>
          <button type="button" className={styles.iconButton} title="Códigos siguientes" aria-label="Códigos siguientes" disabled={(page + 1) * 20 >= filtered.length} onClick={() => setPage((value) => value + 1)}><ChevronRight size={16} /></button>
        </div>
      </>}
    </div>}
  </section>;
}
