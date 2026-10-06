"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { ArrowLeft, Check, ChevronLeft, ChevronRight, FilePenLine, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import styles from "./MasterContractsModule.module.css";
import { ArtistContractsPanel, type ArtistContract } from "./ArtistContractsPanel";

type Participant = {
  artist: string;
  percent: number | null;
  internal_contract_indyana_percent: number | null;
};

type Split = {
  master_type: "pending" | "indyana_master" | "distribution";
  has_contract: boolean | null;
  agreement_confirmed: boolean;
  effective_from: string | null;
  principal: string;
  indyana_percent: number | null;
  principal_percent: number | null;
  apply_guest_contracts: boolean;
  participants: Participant[];
  notes: string;
};

type ContractItem = {
  isrc: string;
  title: string;
  artists_informed: string | null;
  amount_usd: number;
  first_month: string | null;
  last_month: string | null;
  sources: string | null;
  closed: boolean;
  future_reports_selected: boolean;
  version: number;
};

type ContractList = {
  items: ContractItem[];
  total: number;
  summary: { open: number; closed: number };
  offset: number;
};

type ContractDetail = ContractItem & {
  accounts: string | null;
  artist_suggestions: {
    artists: string[];
    evidence: Array<{ source: string; field: string; raw: string }>;
    warnings: string[];
  };
  artist_contracts: ArtistContract[];
  split: Split;
  updated_by: string | null;
  updated_at: string | null;
  reports_effective: false;
};

type Message = { type: "ok" | "error"; text: string };
type Props = {
  canEdit: boolean;
  canApprove: boolean;
  onMessage: (message: Message | null) => void;
};

const PAGE_SIZE = 50;
const money = (value: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value || 0);
const percent = (value: number) => new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 }).format(value);
const numberOrNull = (value: string) => value.trim() === "" ? null : Number(value);
const artistKey = (value: string) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim().replace(/\s+/g, " ").toLocaleLowerCase();

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: "no-store", ...init });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.error === "string" ? body.error : `Error ${response.status}`);
  return body as T;
}

export function MasterContractsModule({ canEdit, canApprove, onMessage }: Props) {
  const [mode, setMode] = useState<"isrc" | "artists">("isrc");
  const [keyword, setKeyword] = useState("");
  const [appliedKeyword, setAppliedKeyword] = useState("");
  const [status, setStatus] = useState<"all" | "open" | "closed">("all");
  const [offset, setOffset] = useState(0);
  const [list, setList] = useState<ContractList | null>(null);
  const [detail, setDetail] = useState<ContractDetail | null>(null);
  const [draft, setDraft] = useState<Split | null>(null);
  const [closed, setClosed] = useState(false);
  const [futureSelected, setFutureSelected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ status, limit: String(PAGE_SIZE), offset: String(offset) });
      if (appliedKeyword) params.set("keyword", appliedKeyword);
      setList(await requestJson<ContractList>(`/api/master-contracts?${params}`));
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo cargar Contratos." });
    } finally {
      setLoading(false);
    }
  }, [appliedKeyword, offset, onMessage, status]);

  useEffect(() => { void loadList(); }, [loadList]);

  async function openDetail(isrc: string) {
    setLoading(true);
    try {
      const loaded = await requestJson<ContractDetail>(`/api/master-contracts/${encodeURIComponent(isrc)}`);
      setDetail(loaded);
      setDraft(structuredClone(loaded.split));
      setClosed(loaded.closed);
      setFutureSelected(loaded.future_reports_selected);
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo abrir el ISRC." });
    } finally {
      setLoading(false);
    }
  }

  const dirty = detail && draft && (
    JSON.stringify(draft) !== JSON.stringify(detail.split)
    || closed !== detail.closed
    || futureSelected !== detail.future_reports_selected
  );
  const canEditCurrent = canEdit && (!closed || canApprove);

  function returnToList() {
    if (dirty && !window.confirm("Hay cambios sin guardar. ¿Volver al catálogo?")) return;
    setDetail(null);
    setDraft(null);
    void loadList();
  }

  function updateDraft(patch: Partial<Split>) {
    setDraft((current) => current ? { ...current, ...patch } : current);
  }

  function updateParticipant(index: number, patch: Partial<Participant>) {
    setDraft((current) => current ? {
      ...current,
      participants: current.participants.map((item, position) => position === index ? { ...item, ...patch } : item),
    } : current);
  }

  function contractFor(artist: string): ArtistContract | undefined {
    return detail?.artist_contracts.find((item) => artistKey(item.artist_name) === artistKey(artist));
  }

  function applyPrincipalContract(contract: ArtistContract) {
    if (!draft) return;
    updateDraft({
      indyana_percent: contract.indyana_percent,
      principal_percent: draft.participants.length === 0 ? 100 - contract.indyana_percent : draft.principal_percent,
      has_contract: contract.has_contract,
      effective_from: contract.effective_from,
      apply_guest_contracts: contract.is_project,
    });
  }

  async function save(nextClosed = closed, nextSelected = futureSelected) {
    if (!detail || !draft || !canEditCurrent) return;
    setSaving(true);
    try {
      const saved = await requestJson<{
        split: Split; closed: boolean; future_reports_selected: boolean; version: number;
        updated_by: string; updated_at: string;
      }>(`/api/master-contracts/${encodeURIComponent(detail.isrc)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          split: draft,
          closed: nextClosed,
          future_reports_selected: nextSelected,
          expected_version: detail.version,
        }),
      });
      setDetail({ ...detail, ...saved });
      setDraft(structuredClone(saved.split));
      setClosed(saved.closed);
      setFutureSelected(saved.future_reports_selected);
      onMessage({ type: "ok", text: saved.closed ? "Reparto guardado y cerrado. Los reportes actuales no cambiaron." : "Borrador guardado. Los reportes actuales no cambiaron." });
      void loadList();
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo guardar el reparto." });
    } finally {
      setSaving(false);
    }
  }

  const total = useMemo(() => {
    if (!draft) return 0;
    return (draft.indyana_percent || 0) + (draft.principal_percent || 0)
      + draft.participants.reduce((sum, item) => sum + (item.percent || 0), 0);
  }, [draft]);

  const preview = useMemo(() => {
    if (!detail || !draft || Math.abs(total - 100) > 0.0001
      || !draft.principal.trim() || draft.indyana_percent === null || draft.principal_percent === null
      || draft.participants.some((item) => !item.artist.trim() || item.percent === null)) return null;
    const guestRows = draft.participants.map((item) => {
      const base = item.percent || 0;
      const retained = draft.apply_guest_contracts ? (item.internal_contract_indyana_percent || 0) : 0;
      return { artist: item.artist, percent: base * (1 - retained / 100), amount: detail.amount_usd * base * (1 - retained / 100) / 100 };
    });
    const indyanaPercent = 100 - (draft.principal_percent || 0) - guestRows.reduce((sum, item) => sum + item.percent, 0);
    return {
      indyanaPercent,
      indyanaAmount: detail.amount_usd * indyanaPercent / 100,
      principalAmount: detail.amount_usd * (draft.principal_percent || 0) / 100,
      guestRows,
    };
  }, [detail, draft, total]);

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    setAppliedKeyword(keyword.trim());
    if (keyword.trim() === appliedKeyword) void loadList();
  }

  if (mode === "artists") return <ArtistContractsPanel canEdit={canEdit} onBack={() => setMode("isrc")} onMessage={onMessage} />;

  if (detail && draft) {
    return (
      <section className={styles.workspace}>
        <header className={styles.detailHeader}>
          <button type="button" className={styles.iconButton} title="Volver al catálogo" aria-label="Volver al catálogo" onClick={returnToList}><ArrowLeft size={19} /></button>
          <div className={styles.heading}>
            <span>Contratos / {detail.isrc}</span>
            <h1>{detail.title || "Sin título"}</h1>
            <p>{detail.artists_informed || "Sin artistas informados"}</p>
          </div>
          <span className={`${styles.status} ${closed ? styles.closed : styles.open}`}>{closed ? "Cerrado" : "Abierto"}</span>
        </header>

        <div className={styles.identityLine}>
          <div><span>ISRC</span><strong>{detail.isrc}</strong></div>
          <div><span>Ingreso del catálogo</span><strong>{money(detail.amount_usd)}</strong></div>
          <div><span>Actividad</span><strong>{detail.first_month || "-"} a {detail.last_month || "-"}</strong></div>
          <div><span>Distribuidoras</span><strong>{detail.sources || "-"}</strong></div>
        </div>

        <div className={styles.detailColumns}>
          <div className={styles.formColumn}>
            <section className={styles.band}>
              <div className={styles.sectionHeading}><h2>Contrato principal</h2><span>{detail.version ? `Versión ${detail.version}` : "Sin guardar"}</span></div>
              {contractFor(draft.principal) && <div className={styles.contractReference}>
                <span>Contrato de {contractFor(draft.principal)?.artist_name}: Indyana {percent(contractFor(draft.principal)!.indyana_percent)}% · artista {percent(100 - contractFor(draft.principal)!.indyana_percent)}%</span>
                {canEditCurrent && <button type="button" className={styles.secondaryButton} onClick={() => applyPrincipalContract(contractFor(draft.principal)!)}>Usar propuesta</button>}
              </div>}
              <div className={styles.fieldGrid}>
                <label>Tipo de master
                  <select disabled={!canEditCurrent} value={draft.master_type} onChange={(event) => updateDraft({ master_type: event.target.value as Split["master_type"] })}>
                    <option value="pending">Por definir</option><option value="indyana_master">Master Indyana</option><option value="distribution">Distribución</option>
                  </select>
                </label>
                <label>¿Existe contrato?
                  <select disabled={!canEditCurrent} value={draft.has_contract === null ? "unknown" : draft.has_contract ? "yes" : "no"} onChange={(event) => updateDraft({ has_contract: event.target.value === "unknown" ? null : event.target.value === "yes" })}>
                    <option value="unknown">Por confirmar</option><option value="yes">Sí</option><option value="no">No</option>
                  </select>
                </label>
                <label>Vigente desde
                  <input type="month" disabled={!canEditCurrent} value={draft.effective_from || ""} onChange={(event) => updateDraft({ effective_from: event.target.value || null })} />
                </label>
              </div>
              <label className={styles.checkboxLine}>
                <input type="checkbox" disabled={!canEditCurrent} checked={draft.agreement_confirmed} onChange={(event) => updateDraft({ agreement_confirmed: event.target.checked })} />
                <span>Acuerdo y porcentajes confirmados</span>
              </label>
            </section>

            <section className={styles.band}>
              <div className={styles.sectionHeading}><h2>Reparto del master</h2><span>Participaciones del ingreso base</span></div>
              <div className={styles.splitRows}>
                <div className={styles.splitRow}>
                  <label>Indyana<input type="text" value="Indyana" readOnly /></label>
                  <label>Porcentaje<input inputMode="decimal" type="number" min="0" max="100" step="0.01" disabled={!canEditCurrent} value={draft.indyana_percent ?? ""} onChange={(event) => updateDraft({ indyana_percent: numberOrNull(event.target.value) })} /></label>
                </div>
                <div className={styles.splitRow}>
                  <label>Artista principal<input disabled={!canEditCurrent} value={draft.principal} onChange={(event) => updateDraft({ principal: event.target.value })} /></label>
                  <label>Porcentaje<input inputMode="decimal" type="number" min="0" max="100" step="0.01" disabled={!canEditCurrent} value={draft.principal_percent ?? ""} onChange={(event) => updateDraft({ principal_percent: numberOrNull(event.target.value) })} /></label>
                </div>
                {draft.participants.map((item, index) => (
                  <div className={styles.splitRow} key={index}>
                    <label>Participante {index + 1}<input disabled={!canEditCurrent} value={item.artist} onChange={(event) => updateParticipant(index, { artist: event.target.value })} /></label>
                    <label>Porcentaje<input inputMode="decimal" type="number" min="0" max="100" step="0.01" disabled={!canEditCurrent} value={item.percent ?? ""} onChange={(event) => updateParticipant(index, { percent: numberOrNull(event.target.value) })} /></label>
                    {canEditCurrent && <button type="button" className={styles.iconButton} title={`Quitar participante ${index + 1}`} aria-label={`Quitar participante ${index + 1}`} onClick={() => updateDraft({ participants: draft.participants.filter((_, position) => position !== index) })}><Trash2 size={16} /></button>}
                    {draft.apply_guest_contracts && <label className={styles.nestedField}>Indyana del contrato del invitado %<input inputMode="decimal" type="number" min="0" max="100" step="0.01" disabled={!canEditCurrent} value={item.internal_contract_indyana_percent ?? ""} onChange={(event) => updateParticipant(index, { internal_contract_indyana_percent: numberOrNull(event.target.value) })} placeholder="Externo: vacío" /></label>}
                    {draft.apply_guest_contracts && contractFor(item.artist) && <div className={styles.guestReference}><span>Contrato de {contractFor(item.artist)?.artist_name}: {percent(contractFor(item.artist)!.indyana_percent)}% para Indyana</span>{canEditCurrent && <button type="button" className={styles.secondaryButton} onClick={() => updateParticipant(index, { internal_contract_indyana_percent: contractFor(item.artist)!.indyana_percent })}>Usar propuesta</button>}</div>}
                  </div>
                ))}
              </div>
              {canEditCurrent && <button type="button" className={styles.addButton} disabled={draft.participants.length >= 10} onClick={() => updateDraft({ participants: [...draft.participants, { artist: "", percent: null, internal_contract_indyana_percent: null }] })}><Plus size={16} /> Agregar participante</button>}
              <label className={styles.checkboxLine}>
                <input type="checkbox" disabled={!canEditCurrent} checked={draft.apply_guest_contracts} onChange={(event) => updateDraft({ apply_guest_contracts: event.target.checked })} />
                <span>Aplicar contrato de invitados internos sobre su parte</span>
              </label>
              <div className={`${styles.totalLine} ${Math.abs(total - 100) < 0.0001 ? styles.totalOk : styles.totalPending}`}><span>Total asignado</span><strong>{percent(total)}%</strong><small>{Math.abs(total - 100) < 0.0001 ? "Cuadra" : total < 100 ? `Faltan ${percent(100 - total)} puntos` : `Excede ${percent(total - 100)} puntos`}</small></div>
            </section>

            <section className={styles.band}>
              <div className={styles.sectionHeading}><h2>Estado y seguimiento</h2></div>
              <label className={styles.notesLabel}>Notas del acuerdo<textarea disabled={!canEditCurrent} rows={3} value={draft.notes} onChange={(event) => updateDraft({ notes: event.target.value })} /></label>
              <label className={styles.checkboxLine}>
                <input type="checkbox" disabled={!canEditCurrent || !canApprove || !closed} checked={futureSelected} onChange={(event) => setFutureSelected(event.target.checked)} />
                <span>Seleccionado para futura aplicación a reportes</span>
              </label>
              <p className={styles.safetyNote}>Esta selección no modifica ningún reporte ni dashboard actual.</p>
              {detail.updated_at && <p className={styles.auditLine}>Último guardado: {detail.updated_at} por {detail.updated_by || "-"}.</p>}
              <div className={styles.actions}>
                {canEditCurrent && <button type="button" className={styles.secondaryButton} disabled={saving || (!dirty && detail.version > 0)} onClick={() => void save()}><FilePenLine size={16} />{saving ? "Guardando..." : "Guardar"}</button>}
                {canApprove && canEdit && <button type="button" className={styles.primaryButton} disabled={saving} onClick={() => void save(!closed, closed ? false : futureSelected)}><Check size={16} />{closed ? "Reabrir" : "Cerrar reparto"}</button>}
              </div>
            </section>
          </div>

          <aside className={styles.previewColumn}>
            <section className={styles.previewBand}>
              <div className={styles.sectionHeading}><h2>Simulación en USD</h2></div>
              <p>Base observada en el catálogo: {money(detail.amount_usd)}. No es una liquidación ni afecta reportes.</p>
              {preview ? <div className={styles.previewRows}>
                <div><span>Indyana</span><strong>{money(preview.indyanaAmount)}</strong><small>{percent(preview.indyanaPercent)}%</small></div>
                <div><span>{draft.principal || "Principal"}</span><strong>{money(preview.principalAmount)}</strong><small>{percent(draft.principal_percent || 0)}%</small></div>
                {preview.guestRows.map((item, index) => <div key={index}><span>{item.artist}</span><strong>{money(item.amount)}</strong><small>{percent(item.percent)}%</small></div>)}
              </div> : <p className={styles.previewEmpty}>Completá todos los participantes y un reparto que sume 100% para ver la simulación.</p>}
            </section>
            <section className={styles.evidenceBand}>
              <div className={styles.sectionHeading}><h2>Artistas informados</h2></div>
              <p>{detail.artist_suggestions.artists.join(", ") || "Sin nombres detectados"}</p>
              {detail.artist_suggestions.warnings.map((warning) => <p className={styles.warning} key={warning}>{warning}</p>)}
              <details><summary>Ver campos de origen</summary>
                {detail.artist_suggestions.evidence.map((item, index) => <div className={styles.evidenceRow} key={index}><strong>{item.source} · {item.field}</strong><span>{item.raw}</span></div>)}
              </details>
            </section>
          </aside>
        </div>
      </section>
    );
  }

  return (
    <section className={styles.workspace}>
      <header className={styles.listHeader}>
        <div className={styles.heading}><span>Catálogo y distribución</span><h1>Contratos</h1><p>Repartos por ISRC ordenados por ingreso acumulado.</p></div>
        <button type="button" className={styles.secondaryButton} onClick={() => setMode("artists")}>Contratos de artistas</button>
        <button type="button" className={styles.iconButton} title="Actualizar catálogo" aria-label="Actualizar catálogo" disabled={loading} onClick={() => void loadList()}><RefreshCw size={18} /></button>
      </header>
      <form className={styles.toolbar} onSubmit={submitSearch}>
        <div className={styles.searchBox}><Search size={18} /><input aria-label="Buscar tema, artista o ISRC" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="Buscar tema, artista o ISRC" /></div>
        <button type="submit" className={styles.secondaryButton}>Buscar</button>
        <div className={styles.segmented} aria-label="Estado del reparto">
          {(["all", "open", "closed"] as const).map((value) => <button type="button" key={value} aria-pressed={status === value} className={status === value ? styles.selected : ""} onClick={() => { setStatus(value); setOffset(0); }}>{value === "all" ? "Todos" : value === "open" ? "Abiertos" : "Cerrados"}</button>)}
        </div>
      </form>
      <div className={styles.listMeta}><span>{list ? `${list.total.toLocaleString("es-AR")} ISRC` : "Cargando catálogo..."}</span><span>{list?.summary.open.toLocaleString("es-AR") || "0"} abiertos · {list?.summary.closed.toLocaleString("es-AR") || "0"} cerrados</span></div>
      <div className={styles.tableWrap}><table className={styles.table}>
        <thead><tr><th>Tema</th><th>ISRC</th><th>Artistas informados</th><th>Ingreso acumulado</th><th>Estado</th></tr></thead>
        <tbody>
          {!loading && list?.items.length === 0 && <tr><td colSpan={5} className={styles.empty}>No hay ISRC para este filtro.</td></tr>}
          {(list?.items || []).map((item) => <tr key={item.isrc}>
            <td><button type="button" className={styles.titleButton} onClick={() => void openDetail(item.isrc)}>{item.title || "Sin título"}</button></td>
            <td><button type="button" className={styles.isrcButton} onClick={() => void openDetail(item.isrc)}>{item.isrc}</button></td>
            <td className={styles.artistCell} title={item.artists_informed || ""}>{item.artists_informed || "-"}</td>
            <td className={styles.amountCell}>{money(item.amount_usd)}</td>
            <td><span className={`${styles.status} ${item.closed ? styles.closed : styles.open}`}>{item.closed ? "Cerrado" : "Abierto"}</span>{item.future_reports_selected && <small className={styles.futureNote}>Futura aplicación</small>}</td>
          </tr>)}
        </tbody>
      </table></div>
      <div className={styles.pagination}>
        <span>{list ? `${list.offset + (list.items.length ? 1 : 0)}–${list.offset + list.items.length} de ${list.total}` : ""}</span>
        <button type="button" className={styles.iconButton} title="Página anterior" aria-label="Página anterior" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}><ChevronLeft size={18} /></button>
        <button type="button" className={styles.iconButton} title="Página siguiente" aria-label="Página siguiente" disabled={loading || !list || offset + PAGE_SIZE >= list.total} onClick={() => setOffset(offset + PAGE_SIZE)}><ChevronRight size={18} /></button>
      </div>
    </section>
  );
}
