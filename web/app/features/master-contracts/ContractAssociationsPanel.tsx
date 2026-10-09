"use client";

import { useEffect, useState } from "react";
import { ChevronDown, ChevronLeft, ChevronRight, Link2, RefreshCw, Search } from "lucide-react";
import styles from "./MasterContractsModule.module.css";

export type AssociationChoice = { key: string; included: boolean; evidence_signature: string };
type Association = AssociationChoice & {
  kind: string; code: string; source: string; account: string; titles: string[]; artists: string[];
  isrcs: string[]; automatic: boolean; status: string; selectable: boolean; reason: string;
};
type Props = {
  isrc: string; version: number; canEdit: boolean; choices: AssociationChoice[];
  onChange: (choices: AssociationChoice[]) => void;
};
const labels: Record<string, string> = { automatic: "Automático", confirmed: "Confirmado", pending: "Por validar", excluded: "Excluido", blocked: "No asignable" };

export function ContractAssociationsPanel({ isrc, version, canEdit, choices, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Association[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [kind, setKind] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  useEffect(() => {
    if (!open) return;
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
  }, [open, isrc, version, reload]);

  function selection(item: Association) {
    const choice = choices.find((value) => value.key === item.key);
    if (!choice) return { included: item.automatic && item.selectable, status: item.selectable ? (item.automatic ? "automatic" : "pending") : "blocked" };
    if (!item.selectable) return { included: false, status: "blocked" };
    if (!choice.included) return { included: false, status: "excluded" };
    return choice.evidence_signature === item.evidence_signature
      ? { included: true, status: "confirmed" } : { included: false, status: "pending" };
  }

  function toggle(item: Association, included: boolean) {
    if (!canEdit || !item.selectable) return;
    if (included && !item.automatic && !window.confirm(`${item.reason}\n\n¿Confirmás que ${item.code} corresponde al contrato de ${isrc}?`)) return;
    const next = choices.filter((choice) => choice.key !== item.key);
    // Restoring an automatic inclusion removes the explicit exclusion.
    if (!included || !item.automatic) next.push({ key: item.key, included, evidence_signature: item.evidence_signature });
    onChange(next);
  }

  const filtered = items.filter((item) => (!kind || item.kind === kind) && (!search || `${item.code} ${item.source} ${item.account} ${item.titles.join(" ")}`.toLocaleLowerCase().includes(search.toLocaleLowerCase())));
  const pageItems = filtered.slice(page * 20, (page + 1) * 20);

  return <section className={styles.associationsBand}>
    <div className={styles.associationsHeading}>
      <button type="button" className={styles.associationsToggle} aria-expanded={open} aria-controls={`associated-${isrc}`} onClick={() => setOpen((value) => !value)}>
        <Link2 size={16} />Ver códigos asociados{open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
      </button>
      {open && !loading && !error && <span className={styles.associationsCount}>{items.filter((item) => selection(item).included).length} de {items.length} incluidos</span>}
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
          <thead><tr><th>Incluir</th><th>Código</th><th>Distribuidora / cuenta</th><th>Referencia</th><th>Validación</th></tr></thead>
          <tbody>{pageItems.map((item) => {
            const state = selection(item);
            return <tr key={item.key}>
              <td><input type="checkbox" checked={state.included} disabled={!canEdit || !item.selectable} aria-label={`Incluir ${item.code} ${item.source} ${item.account}`} onChange={(event) => toggle(item, event.target.checked)} /></td>
              <td><small>{item.kind === "VIDEO" ? "Video / UGC" : item.kind === "TRACK" ? "ID de plataforma" : item.kind}</small><strong>{item.code}</strong></td>
              <td>{item.source.toUpperCase()}<small>{item.account.replace(/_/g, " ")}</small></td>
              <td>{item.titles.join(" / ") || "Sin título"}<small>{item.artists.join(" / ")}</small>{item.isrcs.some((value) => value !== isrc) && <small>{item.isrcs.join(" · ")}</small>}</td>
              <td><span className={state.status === "automatic" || state.status === "confirmed" ? styles.associationValid : styles.associationPending}>{labels[state.status]}</span><small>{item.reason}</small></td>
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
