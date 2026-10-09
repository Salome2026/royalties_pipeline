"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ArrowLeft, Check, ChevronLeft, ChevronRight, FilePenLine, RefreshCw, Search } from "lucide-react";
import styles from "./MasterContractsModule.module.css";
import { ArtistContractsPanel, type ArtistContract } from "./ArtistContractsPanel";
import { MasterAgreementsEditor, visibleAgreements, type MasterAgreement } from "./MasterAgreementsEditor";
import { PoolsAllocationEditor } from "./PoolsAllocationEditor";
import { ContractAssociationsPanel, type AssociationChoice } from "./ContractAssociationsPanel";
import { agreementAllocation, agreementIncome, allocationTotals, contractErrors, previewAllocation, type Allocation, type StatementIncome } from "./contractLogic";

type Split = Allocation & {
  code_association_overrides?: AssociationChoice[] | null;
  agreements?: MasterAgreement[];
  master_type: "pending" | "indyana_master" | "distribution" | "mawz_master" | "distribution_mawz" | "indyana_and_other" | "mawz_and_other";
  other_master_artist?: string | null;
  has_contract: boolean | null;
  agreement_confirmed: boolean;
  effective_from: string | null;
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
  source_accounts: Array<{ source: string; account: string }>;
};

type ContractDetail = ContractItem & {
  accounts: string | null;
  artist_suggestions: {
    artists: string[];
    evidence: Array<{ source: string; field: string; raw: string; used?: boolean }>;
    warnings: string[];
  };
  artist_contracts: ArtistContract[];
  first_sale_date: string | null;
  first_sale_precision: "day" | "month" | null;
  first_statement_date: string | null;
  statement_income: StatementIncome[];
  split: Split;
  updated_by: string | null;
  updated_at: string | null;
  reports_effective: false;
  pool_contracts_supported?: boolean;
};

type Message = { type: "ok" | "error"; text: string };
type Props = {
  canEdit: boolean;
  canApprove: boolean;
  onMessage: (message: Message | null) => void;
};

const PAGE_SIZE = 50;
const ACCOUNT_LABELS: Record<string, string> = { indyana_records: "INDYANA", mawzrecords: "MAWZ", gusty_dj: "GUSTY", henry_remix: "HENRY" };
const accountLabel = (account: string) => ACCOUNT_LABELS[account] || account.replace(/_/g, " ").toUpperCase();
const money = (value: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value || 0);
const percent = (value: number) => new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 }).format(value);
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
  const [sourceAccount, setSourceAccount] = useState("");
  const [offset, setOffset] = useState(0);
  const [list, setList] = useState<ContractList | null>(null);
  const [detail, setDetail] = useState<ContractDetail | null>(null);
  const [draft, setDraft] = useState<Split | null>(null);
  const [openAgreementId, setOpenAgreementId] = useState<string | null>(null);
  const [closed, setClosed] = useState(false);
  const [futureSelected, setFutureSelected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingArtist, setEditingArtist] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ status, limit: String(PAGE_SIZE), offset: String(offset) });
      if (appliedKeyword) params.set("keyword", appliedKeyword);
      if (sourceAccount) {
        const [source, account] = sourceAccount.split("/");
        params.set("source", source);
        params.set("account", account);
      }
      setList(await requestJson<ContractList>(`/api/master-contracts?${params}`));
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo cargar Contratos." });
    } finally {
      setLoading(false);
    }
  }, [appliedKeyword, offset, onMessage, sourceAccount, status]);

  useEffect(() => { void loadList(); }, [loadList]);
  useEffect(() => {
    if (!editingArtist) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const frame = requestAnimationFrame(() => document.querySelector<HTMLElement>('[role="dialog"] button')?.focus());
    function trapFocus(event: KeyboardEvent) {
      if (event.key !== "Tab") return;
      const controls = [...(document.querySelector('[role="dialog"]')?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled)') || [])].filter((item) => item.offsetParent !== null);
      const first = controls[0], last = controls.at(-1);
      if ((event.shiftKey && document.activeElement === first) || (!event.shiftKey && document.activeElement === last)) {
        event.preventDefault(); (event.shiftKey ? last : first)?.focus();
      }
    }
    document.addEventListener("keydown", trapFocus);
    return () => {
      cancelAnimationFrame(frame); document.removeEventListener("keydown", trapFocus);
      document.body.style.overflow = overflow; previousFocus?.focus();
    };
  }, [editingArtist]);

  async function openDetail(isrc: string) {
    setLoading(true);
    try {
      const loaded = await requestJson<ContractDetail>(`/api/master-contracts/${encodeURIComponent(isrc)}`);
      setDetail(loaded);
      setDraft(structuredClone(loaded.split));
      setOpenAgreementId(null);
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
  const agreements = draft ? visibleAgreements(draft.agreements, draft, detail?.first_statement_date || null) : [];
  const activeAgreement = agreements.find((item) => item.id === openAgreementId);
  const allocation = draft ? agreementAllocation(activeAgreement, draft) : null;
  const totals = allocation ? allocationTotals(activeAgreement, allocation) : { master: 0, participation: 0, general: 0 };
  const errors = draft ? contractErrors(agreements, draft) : [];
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });
  const periodIncome = detail ? agreementIncome(activeAgreement, detail.statement_income || [], today) : null;

  function returnToList() {
    if (dirty && !window.confirm("Hay cambios sin guardar. ¿Volver al catálogo?")) return;
    setDetail(null);
    setDraft(null);
    setOpenAgreementId(null);
    void loadList();
  }

  function updateDraft(patch: Partial<Split>) {
    setDraft((current) => current ? { ...current, ...patch } : current);
  }

  function contractFor(artist: string): ArtistContract | undefined {
    return detail?.artist_contracts.find((item) => artistKey(item.artist_name) === artistKey(artist));
  }

  function applyPrincipalContract(contract: ArtistContract) {
    if (!draft || !activeAgreement || !allocation) return;
    const nextAllocation = {
      ...allocation, indyana_percent: contract.indyana_percent,
      principal_percent: allocation.participants.length === 0 ? 100 - contract.indyana_percent : allocation.principal_percent,
      apply_guest_contracts: contract.is_project,
      principal_rule: { treatment: contract.is_project && activeAgreement.commercialization !== "distribution" ? "project_owners" as const : "direct" as const },
    };
    updateDraft({
      has_contract: contract.has_contract,
      agreements: agreements.map((item) => item.id === activeAgreement.id
        ? { ...item, allocation: nextAllocation, master_pool_percent: contract.indyana_percent,
          contract_kind: contract.is_project && item.commercialization !== "distribution" ? "project" : "simple" } : item),
    });
  }

  async function save(nextClosed = closed, nextSelected = futureSelected) {
    if (!detail || !draft || !canEditCurrent) return;
    if (errors.length) { onMessage({ type: "error", text: errors[0] }); return; }
    setSaving(true);
    try {
      if (agreements.some((item) => item.allocation_model === "pools") && !detail.pool_contracts_supported) {
        const current = await requestJson<ContractDetail>(`/api/master-contracts/${encodeURIComponent(detail.isrc)}`);
        if (!current.pool_contracts_supported) throw new Error("El servicio de contratos se está actualizando. Tu borrador no se guardó; volvé a intentar en unos minutos.");
        setDetail((value) => value ? { ...value, pool_contracts_supported: true } : value);
      }
      const saved = await requestJson<{
        split: Split; closed: boolean; future_reports_selected: boolean; version: number;
        updated_by: string; updated_at: string;
      }>(`/api/master-contracts/${encodeURIComponent(detail.isrc)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          split: { ...draft, agreements },
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

  const preview = activeAgreement && allocation && periodIncome !== null && errors.length === 0
    ? previewAllocation(activeAgreement, allocation, periodIncome) : null;

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    setOffset(0);
    setAppliedKeyword(keyword.trim());
    if (keyword.trim() === appliedKeyword) void loadList();
  }

  if (mode === "artists") return <ArtistContractsPanel canEdit={canEdit} onBack={() => setMode("isrc")} onMessage={onMessage} />;

  if (detail && draft && allocation) {
    const artistOptions = [...new Set([...detail.artist_suggestions.artists, ...detail.artist_contracts.map((item) => item.artist_name)])];
    return (
      <section className={styles.workspace}>
        <header className={styles.detailHeader}>
          <button type="button" className={styles.iconButton} title="Volver al catálogo" aria-label="Volver al catálogo" onClick={returnToList}><ArrowLeft size={19} /></button>
          <div className={styles.heading}>
            <span>Contratos / {detail.isrc}</span>
            <h1>{detail.title || "Sin título"}</h1>
            <p>{detail.artist_suggestions.artists.join(", ") || "Participantes por confirmar"}</p>
          </div>
          <span className={`${styles.status} ${closed ? styles.closed : styles.open}`}>{closed ? "Cerrado" : "Abierto"}</span>
          {canEditCurrent && !openAgreementId && dirty && <button type="button" className={styles.secondaryButton} disabled={saving || errors.length > 0} onClick={() => void save()}><FilePenLine size={16} />{saving ? "Guardando..." : "Guardar"}</button>}
        </header>

        <div className={styles.identityLine}>
          <div><span>ISRC</span><strong>{detail.isrc}</strong></div>
          <div><span>Ingreso base</span><strong>{money(detail.amount_usd)}</strong></div>
          <div><span>Actividad</span><strong>{detail.first_month || "-"} a {detail.last_month || "-"}</strong></div>
          <div><span>Distribuidoras</span><strong>{detail.sources || "-"}</strong></div>
        </div>

        <ContractAssociationsPanel key={detail.isrc} isrc={detail.isrc} version={detail.version} canEdit={canEditCurrent && !saving}
          choices={draft.code_association_overrides || []} onChange={(choices) => updateDraft({ code_association_overrides: choices })} />

        <div className={`${styles.detailColumns} ${openAgreementId ? "" : styles.detailColumnsSolo}`}>
          <div className={styles.formColumn}>
            <MasterAgreementsEditor
              agreements={agreements}
              fallbackAllocation={draft}
              canEdit={canEditCurrent}
              artistOptions={artistOptions}
              firstStatementDate={detail.first_statement_date}
              openId={openAgreementId}
              onOpenChange={setOpenAgreementId}
              onChange={(next) => updateDraft({ agreements: next })}
            />
            {errors.length > 0 && <div className={styles.validationErrors} role="alert">{errors.map((error) => <p key={error}>{error}</p>)}</div>}

            {openAgreementId && <>
              {activeAgreement?.allocation_model === "pools" && contractFor(allocation.principal) && <div className={styles.contractReference}>
                <span>Contrato de {contractFor(allocation.principal)?.artist_name}: Indyana {percent(contractFor(allocation.principal)!.indyana_percent)}% · artista {percent(100 - contractFor(allocation.principal)!.indyana_percent)}%</span>
                {canEditCurrent && <button type="button" className={styles.secondaryButton} onClick={() => applyPrincipalContract(contractFor(allocation.principal)!)}>Usar propuesta</button>}
              </div>}
              {activeAgreement && <PoolsAllocationEditor agreement={activeAgreement} allocation={allocation} canEdit={canEditCurrent}
                artistOptions={artistOptions} artistContracts={detail.artist_contracts} onEditArtist={setEditingArtist}
                onChange={(next) => updateDraft({ agreements: agreements.map((item) => item.id === next.id ? next : item) })} />}
              <div className={styles.totalsGrid}>
                <div><span>{activeAgreement?.allocation_model === "pools" && activeAgreement.commercialization === "distribution" ? "Total comercialización" : "Total master"}</span><strong>{percent(totals.master)}%</strong></div>
                <div><span>Total participaciones</span><strong>{percent(totals.participation)}%</strong></div>
                <div className={Math.abs(totals.general - 100) < .0001 ? styles.totalOk : totals.general > 100 ? styles.totalError : styles.totalPending}><span>Total general</span><strong>{percent(totals.general)}%</strong><small>{Math.abs(totals.general - 100) < .0001 ? "Cuadra" : totals.general < 100 ? `Faltan ${percent(100 - totals.general)} puntos` : `Excede ${percent(totals.general - 100)} puntos`}</small></div>
              </div>

            <section className={styles.band}>
              <div className={styles.sectionHeading}><h2>Estado y seguimiento</h2></div>
              <label className={styles.checkboxLine}>
                <input type="checkbox" disabled={!canEditCurrent} checked={draft.agreement_confirmed} onChange={(event) => updateDraft({ agreement_confirmed: event.target.checked })} />
                <span>Acuerdo y porcentajes confirmados</span>
              </label>
              <label className={styles.notesLabel}>Notas del acuerdo<textarea disabled={!canEditCurrent} rows={3} value={draft.notes} onChange={(event) => updateDraft({ notes: event.target.value })} /></label>
              <label className={styles.checkboxLine}>
                <input type="checkbox" disabled={!canEditCurrent || !canApprove || !closed} checked={futureSelected} onChange={(event) => setFutureSelected(event.target.checked)} />
                <span>Seleccionado para futura aplicación a reportes</span>
              </label>
              <p className={styles.safetyNote}>Esta selección no modifica ningún reporte ni dashboard actual.</p>
              {detail.updated_at && <p className={styles.auditLine}>Último guardado: {detail.updated_at} por {detail.updated_by || "-"}.</p>}
              <div className={styles.actions}>
                {canEditCurrent && <button type="button" className={styles.secondaryButton} disabled={saving || errors.length > 0 || (!dirty && detail.version > 0)} onClick={() => void save()}><FilePenLine size={16} />{saving ? "Guardando..." : "Guardar"}</button>}
                {canApprove && canEdit && <button type="button" className={styles.primaryButton} disabled={saving || errors.length > 0} onClick={() => void save(!closed, closed ? false : futureSelected)}><Check size={16} />{closed ? "Reabrir" : "Cerrar reparto"}</button>}
              </div>
            </section>
            </>}
          </div>

          {openAgreementId && <aside className={styles.previewColumn}>
            <section className={styles.previewBand}>
              <div className={styles.sectionHeading}><h2>Simulación en USD</h2></div>
              <div className={styles.periodBase}><span>Ingreso en vigencia</span><strong>{periodIncome === null ? "-" : money(periodIncome)}</strong><small>{activeAgreement?.effective_from || "Desde sin definir"} a {activeAgreement?.effective_until || "Actual"}</small></div>
              {preview ? <div className={styles.previewRows}>
                {preview.map((item, index) => <div key={index}><span>{item.artist}</span><strong>{money(item.amount)}</strong><small>{percent(item.percent)}%</small>
                  <details className={styles.previewOrigins}><summary>Composición</summary>{item.origins.map((origin, position) => <p key={position}>{origin.label}: {percent(origin.percent)}%</p>)}</details>
                </div>)}
                <div className={styles.previewTotal}><span>Total distribuido</span><strong>{money(preview.reduce((sum, item) => sum + item.amount, 0))}</strong><small>100%</small></div>
              </div> : <p className={styles.previewEmpty}>Completá todos los participantes y un reparto que sume 100% para ver la simulación.</p>}
            </section>
            <section className={styles.evidenceBand}>
              <div className={styles.sectionHeading}><h2>Participantes sugeridos</h2></div>
              <p>{detail.artist_suggestions.artists.join(", ") || "Sin nombres detectados"}</p>
              {detail.artist_suggestions.warnings.map((warning) => <p className={styles.warning} key={warning}>{warning}</p>)}
              <details><summary>Ver campos de origen</summary>
                {detail.artist_suggestions.evidence.map((item, index) => <div className={styles.evidenceRow} key={index}><strong>{item.source} · {item.field}{item.used === false ? " (contexto)" : ""}</strong><span>{item.raw}</span></div>)}
              </details>
            </section>
          </aside>}
        </div>
        {editingArtist && <div className={styles.modalBackdrop}>
          <div className={styles.artistModal} role="dialog" aria-modal="true" aria-label={`Contrato de ${editingArtist}`}>
            <ArtistContractsPanel canEdit={canEditCurrent} initialArtist={editingArtist} onBack={() => setEditingArtist(null)} onMessage={onMessage}
              onSaved={(items) => setDetail((current) => current ? { ...current, artist_contracts: items.filter((item) => item.is_active) } : current)} />
          </div>
        </div>}
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
        <select className={styles.sourceFilter} aria-label="Distribuidora y cuenta" title="Distribuidora y cuenta" value={sourceAccount} disabled={loading} onChange={(event) => { setSourceAccount(event.target.value); setOffset(0); }}>
          <option value="">Distribuidoras: todas</option>
          {(list?.source_accounts || []).map(({ source, account }) => <option key={`${source}/${account}`} value={`${source}/${account}`}>{source.toUpperCase()} / {accountLabel(account)}</option>)}
        </select>
        <div className={styles.segmented} aria-label="Estado del reparto">
          {(["all", "open", "closed"] as const).map((value) => <button type="button" key={value} aria-pressed={status === value} className={status === value ? styles.selected : ""} onClick={() => { setStatus(value); setOffset(0); }}>{value === "all" ? "Todos" : value === "open" ? "Abiertos" : "Cerrados"}</button>)}
        </div>
      </form>
      <div className={styles.listMeta}><span>{list ? `${list.total.toLocaleString("es-AR")} ISRC` : "Cargando catálogo..."}</span><span>{list?.summary.open.toLocaleString("es-AR") || "0"} abiertos · {list?.summary.closed.toLocaleString("es-AR") || "0"} cerrados</span></div>
      <div className={styles.tableWrap}><table className={styles.table}>
        <thead><tr><th>Tema</th><th>ISRC</th><th>Crédito en catálogo</th><th>Ingreso acumulado</th><th>Estado</th></tr></thead>
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
