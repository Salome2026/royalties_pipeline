"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Library,
  Pencil,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { PeriodControl } from "../../components/PeriodControl";
import { isResolvedPeriodInvalid, resolvePeriod, type PeriodSelection } from "../../lib/period";
import { requestCatalog, requestCatalogUpdate } from "./api";
import type { CatalogData, CatalogInitialFilter, CatalogItem, CatalogStatus } from "./types";
import styles from "./CatalogModule.module.css";

type Message = { type: "ok" | "error"; text: string };

type Props = {
  canEdit: boolean;
  initialFilter?: CatalogInitialFilter | null;
  onMessage: (message: Message | null) => void;
};

const PAGE_SIZE = 50;

function usd(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value || 0);
}

function normalizedLabel(item: CatalogItem) {
  return item.label_normalized || item.label_normalized_auto || item.external_label || "";
}

export function CatalogModule({ canEdit, initialFilter, onMessage }: Props) {
  const [data, setData] = useState<CatalogData | null>(null);
  const [loading, setLoading] = useState(false);
  const [source, setSource] = useState(initialFilter?.source || "");
  const [account, setAccount] = useState(initialFilter?.account || "");
  const [artist, setArtist] = useState("");
  const [keyword, setKeyword] = useState("");
  const [appliedKeyword, setAppliedKeyword] = useState("");
  const [label, setLabel] = useState("");
  const [period, setPeriod] = useState<PeriodSelection>({ mode: "all" });
  const [status, setStatus] = useState<CatalogStatus>(initialFilter?.status || "active");
  const [offset, setOffset] = useState(0);
  const [labelEditKey, setLabelEditKey] = useState("");
  const [labelDraft, setLabelDraft] = useState("");
  const [savingKey, setSavingKey] = useState("");

  const resolvedPeriod = useMemo(() => resolvePeriod(period, "activity_window"), [period]);

  const loadCatalog = useCallback(async (nextOffset: number) => {
    if (isResolvedPeriodInvalid(resolvedPeriod)) {
      onMessage({ type: "error", text: "El período desde no puede ser mayor que hasta." });
      return;
    }
    setLoading(true);
    try {
      const result = await requestCatalog({
        source,
        account,
        artist,
        keyword: appliedKeyword,
        label,
        startMonth: resolvedPeriod.startMonth,
        endMonth: resolvedPeriod.endMonth,
        status,
        limit: PAGE_SIZE,
        offset: nextOffset,
      });
      setData(result);
      setOffset(nextOffset);
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo cargar el catálogo." });
    } finally {
      setLoading(false);
    }
  }, [account, appliedKeyword, artist, label, onMessage, resolvedPeriod, source, status]);

  useEffect(() => {
    void loadCatalog(0);
  }, [loadCatalog]);

  useEffect(() => {
    if (!initialFilter) return;
    setSource(initialFilter.source || "");
    setAccount(initialFilter.account || "");
    setStatus(initialFilter.status || "active");
    setOffset(0);
  }, [initialFilter?.requestId]);

  function applySearch(event?: FormEvent) {
    event?.preventDefault();
    setOffset(0);
    setAppliedKeyword(keyword.trim());
    if (keyword.trim() === appliedKeyword) void loadCatalog(0);
  }

  function clearFilters() {
    setSource("");
    setAccount("");
    setArtist("");
    setKeyword("");
    setAppliedKeyword("");
    setLabel("");
    setPeriod({ mode: "all" });
    setStatus("active");
    setOffset(0);
  }

  async function updateStatus(item: CatalogItem) {
    if (!canEdit) return;
    const active = !item.active;
    setSavingKey(item.catalog_key);
    try {
      await requestCatalogUpdate({
        catalog_key: item.catalog_key,
        active,
        include_in_reports: active,
        business_status: active ? "vpo_catalog" : "inactive",
        notes: active ? "" : "Excluido manualmente desde Catálogo General.",
      });
      onMessage({ type: "ok", text: active ? "Tema marcado como activo." : "Tema marcado como inactivo." });
      await loadCatalog(offset);
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo actualizar el catálogo." });
    } finally {
      setSavingKey("");
    }
  }

  async function updateLabel(item: CatalogItem) {
    if (!canEdit) return;
    setSavingKey(item.catalog_key);
    try {
      await requestCatalogUpdate({
        catalog_key: item.catalog_key,
        active: item.active,
        include_in_reports: item.include_in_reports,
        business_status: item.catalog_business_status || (item.active ? "vpo_catalog" : "inactive"),
        notes: item.status_notes || "",
        label_normalized_override: labelDraft.trim() || null,
      });
      setLabelEditKey("");
      setLabelDraft("");
      onMessage({ type: "ok", text: "Label normalizado actualizado." });
      await loadCatalog(offset);
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo actualizar el label." });
    } finally {
      setSavingKey("");
    }
  }

  const firstVisible = data && data.items.length ? data.offset + 1 : 0;
  const lastVisible = data ? Math.min(data.offset + data.items.length, data.total) : 0;

  return (
    <section className={styles.workspace}>
      <header className={styles.intro}>
        <div className={styles.introIcon} aria-hidden="true"><Library size={23} /></div>
        <div>
          <span>Catálogo y distribución</span>
          <h1>Catálogo general</h1>
          <p>Una vista maestra y deduplicada del repertorio. Los estados y labels normalizados gobiernan los reportes sin alterar los datos crudos.</p>
        </div>
        <button type="button" className={styles.refreshButton} onClick={() => void loadCatalog(offset)} disabled={loading} title="Actualizar catálogo">
          <RefreshCw size={17} className={loading ? styles.spinning : ""} aria-hidden="true" />
          <span>{loading ? "Actualizando" : "Actualizar"}</span>
        </button>
      </header>

      <form className={styles.filters} onSubmit={applySearch}>
        <div className={styles.searchField}>
          <label htmlFor="catalog_keyword">Tema, artista o identificador</label>
          <div>
            <Search size={17} aria-hidden="true" />
            <input id="catalog_keyword" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="Buscar por título, artista, ISRC o ID" />
          </div>
        </div>
        <div className={styles.field}>
          <label htmlFor="catalog_source">Distribuidora</label>
          <select id="catalog_source" value={source} onChange={(event) => { setSource(event.target.value); setAccount(""); setOffset(0); }}>
            <option value="">Todas</option>
            {(data?.options.sources || []).map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor="catalog_account">Cuenta</label>
          <select id="catalog_account" value={account} onChange={(event) => { setAccount(event.target.value); setOffset(0); }}>
            <option value="">Todas</option>
            {(data?.options.accounts || []).map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </div>
        <button type="submit" className={styles.searchButton} disabled={loading}><Search size={17} aria-hidden="true" />Buscar</button>

        <div className={styles.field}>
          <label htmlFor="catalog_artist">Artista</label>
          <select id="catalog_artist" value={artist} onChange={(event) => { setArtist(event.target.value); setOffset(0); }}>
            <option value="">Todos</option>
            {(data?.options.artists || []).map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor="catalog_label">Label normalizado</label>
          <select id="catalog_label" value={label} onChange={(event) => { setLabel(event.target.value); setOffset(0); }}>
            <option value="">Todos</option>
            <option value="__missing__">No identificadas</option>
            {(data?.options.labels || []).map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </div>
        <div className={styles.periodField}>
          <PeriodControl
            id="catalog_period"
            label="Actividad"
            profile="activity_window"
            selection={period}
            onChange={(value) => { setPeriod(value); setOffset(0); }}
            minMonth={data?.options.first_month || undefined}
            maxMonth={data?.options.last_month || undefined}
            helperText="Filtra obras con actividad en el mes o rango elegido."
          />
        </div>
        <div className={styles.field}>
          <label htmlFor="catalog_status">Estado</label>
          <select id="catalog_status" value={status} onChange={(event) => { setStatus(event.target.value as CatalogStatus); setOffset(0); }}>
            <option value="active">Activos</option>
            <option value="inactive">Inactivos</option>
            <option value="all">Todos</option>
          </select>
        </div>
        <button type="button" className={styles.clearButton} onClick={clearFilters}>Limpiar</button>
      </form>

      <div className={styles.metrics} aria-label="Resumen del catálogo">
        <div><span>Obras</span><strong>{(data?.total || 0).toLocaleString("es-AR")}</strong></div>
        <div><span>Ingreso acumulado</span><strong>{usd(data?.totals.amount_usd || 0)}</strong></div>
        <div><span>Unidades</span><strong>{Math.round(data?.totals.units || 0).toLocaleString("es-AR")}</strong></div>
        <div><span>Actividad disponible</span><strong>{data?.options.first_month || "-"}<small>a</small>{data?.options.last_month || "-"}</strong></div>
      </div>

      <div className={styles.resultsHeader}>
        <div><strong>Repertorio</strong><span>{loading ? "Actualizando resultados..." : `Mostrando ${firstVisible}–${lastVisible} de ${data?.total || 0}`}</span></div>
        <div className={styles.pagination}>
          <button type="button" title="Página anterior" disabled={loading || offset === 0} onClick={() => void loadCatalog(Math.max(0, offset - PAGE_SIZE))}><ChevronLeft size={18} /></button>
          <span>Página {data?.total ? Math.floor(offset / PAGE_SIZE) + 1 : 0}</span>
          <button type="button" title="Página siguiente" disabled={loading || !data || offset + PAGE_SIZE >= data.total} onClick={() => void loadCatalog(offset + PAGE_SIZE)}><ChevronRight size={18} /></button>
        </div>
      </div>

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Estado</th><th>Tema y artista</th><th>Identidad</th><th>Distribución</th><th>Actividad</th><th>Ingreso</th><th>Metadata</th><th>Label</th><th><span className={styles.srOnly}>Acciones</span></th>
            </tr>
          </thead>
          <tbody>
            {loading && !data && <tr><td colSpan={9} className={styles.empty}>Cargando catálogo...</td></tr>}
            {!loading && data?.items.length === 0 && <tr><td colSpan={9} className={styles.empty}>No hay obras para los filtros seleccionados.</td></tr>}
            {(data?.items || []).map((item) => (
              <tr key={item.catalog_key} className={item.include_in_reports === false ? styles.inactiveRow : ""}>
                <td data-label="Estado">
                  <span className={`${styles.status} ${item.include_in_reports !== false ? styles.active : styles.inactive}`}>{item.include_in_reports !== false ? "En reportes" : "Excluido"}</span>
                  {item.status_notes && <small title={item.status_notes}>{item.status_notes}</small>}
                </td>
                <td data-label="Tema y artista" className={styles.workCell}>
                  <strong>{item.track_title || "Sin título"}</strong>
                  <span>{item.artist_statement || "Sin artista"}</span>
                  {item.title_variants && item.title_variants !== item.track_title && <small title={item.title_variants}>Variantes: {item.title_variants}</small>}
                </td>
                <td data-label="Identidad" className={styles.identityCell}>
                  <strong>{item.asset_isrc || item.track_id || "-"}</strong>
                  <small title={item.catalog_key}>{item.catalog_key}</small>
                </td>
                <td data-label="Distribución">
                  <strong>{item.sources || "-"}</strong>
                  <small>{item.accounts || "-"}</small>
                  {item.content_types && <small>{item.content_types}</small>}
                </td>
                <td data-label="Actividad"><strong>{item.first_transaction_month || "-"}</strong><small>hasta {item.last_transaction_month || "-"}</small></td>
                <td data-label="Ingreso" className={styles.amount}>{usd(item.amount_usd)}</td>
                <td data-label="Metadata">
                  <strong>{item.external_release_date || "Sin release"}</strong>
                  {item.external_match_url && <a href={item.external_match_url} target="_blank" rel="noreferrer">Abrir <ExternalLink size={12} /></a>}
                </td>
                <td data-label="Label" className={styles.labelCell}>
                  {labelEditKey === item.catalog_key ? (
                    <div className={styles.inlineEdit}>
                      <input value={labelDraft} onChange={(event) => setLabelDraft(event.target.value)} onKeyDown={(event) => {
                        if (event.key === "Enter") { event.preventDefault(); void updateLabel(item); }
                        if (event.key === "Escape") { setLabelEditKey(""); setLabelDraft(""); }
                      }} autoFocus />
                      <button type="button" title="Guardar label" disabled={savingKey === item.catalog_key} onClick={() => void updateLabel(item)}><Check size={15} /></button>
                      <button type="button" title="Cancelar edición" disabled={savingKey === item.catalog_key} onClick={() => { setLabelEditKey(""); setLabelDraft(""); }}><X size={15} /></button>
                    </div>
                  ) : canEdit ? (
                    <button type="button" className={styles.labelEdit} title="Editar label normalizado" onClick={() => { setLabelEditKey(item.catalog_key); setLabelDraft(normalizedLabel(item)); }}>
                      <span>{item.label_normalized || "Sin label"}</span><Pencil size={13} aria-hidden="true" />
                    </button>
                  ) : <strong>{item.label_normalized || "-"}</strong>}
                  {item.label_normalized_override && <small className={styles.manual}>Normalización manual</small>}
                  {item.external_label && item.external_label !== item.label_normalized && <small className={styles.original} title={item.external_label}>Original: {item.external_label}</small>}
                </td>
                <td data-label="Acción" className={styles.actionCell}>
                  <button type="button" disabled={!canEdit || savingKey === item.catalog_key} title={!canEdit ? "No tenés permiso para editar." : item.active ? "Excluir de los reportes" : "Volver a incluir en reportes"} onClick={() => void updateStatus(item)}>
                    {item.active ? "Inactivar" : "Activar"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
