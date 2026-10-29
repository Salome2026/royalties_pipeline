"use client";
import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import styles from "./RoyaltyExplorer.module.css";

export type ExplorerState = { measure: "income" | "contractual"; beneficiary: string; drill: Record<string, string> };
export const initialExplorer: ExplorerState = { measure: "income", beneficiary: "", drill: {} };
export type ExplorerRank = { name: string; identity_key?: string; amount_usd: number; pending_amount_usd?: number; youtube_only?: boolean };
export type ExplorerInfo = { measure: string; beneficiary: string | null; restricted: boolean; base_amount_usd: number;
  pending_amount_usd: number; pending_tracks: number; registry_revision: string;
  pending: Array<{ title: string; identity_key: string; reason: string; amount_usd: number }> };
export const explorerActive = (state: ExplorerState) => !!state.beneficiary || state.measure === "contractual" || Object.keys(state.drill).length > 0;
export function explorerParams(params: URLSearchParams, state: ExplorerState) {
  params.set("measure", state.measure);
  if (state.beneficiary) params.set("beneficiary", state.beneficiary);
  if (Object.keys(state.drill).length) params.set("drill", JSON.stringify(state.drill));
  return params;
}
export const explorerKey = (name: string) => name.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim().replace(/\s+/g, " ");
const money = (value: number) => new Intl.NumberFormat("es-AR", { style: "currency", currency: "USD" }).format(value || 0);
const percentage = (value: number) => `${value.toLocaleString("es-AR", { maximumFractionDigits: 4 })}%`;
const drillLabels: Record<string, string> = { month: "Mes", source: "Distribuidora", account: "Cuenta", dsp: "Plataforma", artist: "Artista del catálogo", monetization: "Monetización", content_origin: "Origen", territory: "Territorio", label: "Sello" };

export function RoyaltyExplorerControls({ state, keyword, restricted = false, loading, onChange }: {
  state: ExplorerState; keyword: string; restricted?: boolean; loading: boolean;
  onChange: (state: ExplorerState, clearKeyword?: boolean) => void;
}) {
  const [options, setOptions] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [wanted, setWanted] = useState<"income" | "contractual">(restricted ? "contractual" : state.measure);
  const [prompt, setPrompt] = useState(false);
  const initialized = useRef(false);
  const change = useRef(onChange); change.current = onChange;
  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/royalties-dashboard/explorer-options", { cache: "no-store", signal: controller.signal })
      .then(async (r) => { const b = await r.json(); if (!r.ok) throw new Error(b.error || "No se pudieron cargar los beneficiarios."); return b; })
      .then((data: { beneficiaries: string[] }) => {
        if (controller.signal.aborted) return;
        setOptions(data.beneficiaries);
        if (restricted && !initialized.current && data.beneficiaries.length === 1) {
          initialized.current = true;
          change.current({ ...initialExplorer, measure: "contractual", beneficiary: data.beneficiaries[0] });
        }
      }).catch((e) => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "No se pudieron cargar los beneficiarios."); });
    return () => controller.abort();
  }, [restricted]);
  function measure(value: "income" | "contractual") {
    setWanted(value);
    const matched = options.find((name) => explorerKey(name) === explorerKey(keyword));
    const beneficiary = state.beneficiary || matched || "";
    if ((value === "contractual" || restricted) && !beneficiary) { setPrompt(true); return; }
    setPrompt(false); onChange({ ...state, measure: value, beneficiary }, !!matched && !state.beneficiary);
  }
  return <div className={styles.controls} aria-label="Vista y beneficiario de regalías">
    <div className={styles.measure}>
      <button type="button" disabled={loading} aria-pressed={state.measure === "income"} onClick={() => measure("income")}>{restricted ? "Ingreso de mis temas" : "Ingreso de los temas"}</button>
      <button type="button" disabled={loading} aria-pressed={state.measure === "contractual"} onClick={() => measure("contractual")}>{restricted ? "Mi parte según contrato" : "Parte según contrato"}</button>
    </div>
    <label>Beneficiario<select aria-label="Beneficiario del reparto" value={state.beneficiary} disabled={loading || !options.length} onChange={(e) => {
      const beneficiary = e.target.value;
      setPrompt(false); onChange({ measure: beneficiary ? wanted : "income", beneficiary, drill: state.drill }, !!beneficiary && explorerKey(beneficiary) === explorerKey(keyword));
    }}>
      <option value="">{restricted ? "Elegí tu artista" : "Catálogo general"}</option>
      {options.map((name) => <option key={name} value={name}>{name}</option>)}
    </select></label>
    {prompt && <span className={styles.notice} role="status">Elegí un beneficiario para calcular su participación.</span>}
    {error && <span className={styles.notice} role="alert">{error}</span>}
  </div>;
}

export function RoyaltyExplorerTrail({ state, loading, onChange }: { state: ExplorerState; loading: boolean; onChange: (state: ExplorerState) => void }) {
  if (!Object.keys(state.drill).length) return null;
  return <nav className={styles.trail} aria-label="Filtros de exploración">
    <button type="button" disabled={loading} onClick={() => onChange({ ...state, drill: {} })}>Volver a {state.beneficiary || "la vista general"}</button>
    {Object.entries(state.drill).map(([key, value]) => <button type="button" key={key} disabled={loading} onClick={() => { const drill = { ...state.drill }; delete drill[key]; onChange({ ...state, drill }); }}>{drillLabels[key] || key}: {value}<X size={13} aria-hidden="true" /></button>)}
  </nav>;
}

export function RoyaltyExplorerPending({ info, onOpen }: { info?: ExplorerInfo; onOpen: (row: ExplorerRank) => void }) {
  if (!info?.pending_tracks) return null;
  return <details className={styles.pending}>
    <summary>{money(info.pending_amount_usd)} de ingresos pendientes de reparto · {info.pending_tracks} temas o referencias</summary>
    <p>Estos importes todavía no se atribuyen al beneficiario.</p>
    <table><thead><tr><th>Tema / referencia</th><th>Motivo</th><th>Ingreso USD</th></tr></thead><tbody>{info.pending.map((row) => <tr key={`${row.identity_key}-${row.reason}`}>
      <td><button type="button" onClick={() => onOpen({ name: row.title, identity_key: row.identity_key, amount_usd: row.amount_usd })}>{row.title || row.identity_key}</button></td>
      <td>{row.reason}</td><td>{money(row.amount_usd)}</td>
    </tr>)}</tbody></table>
  </details>;
}

type Share = { name: string; percent: number; amount_usd: number; origins: { label: string; percent: number }[] };
type Segment = { from: string; until: string | null; version: number; label: string; months: string[]; base_amount_usd: number;
  shares?: Share[]; own_share?: { percent: number; amount_usd: number } };
type Origin = { statement_month: string; transaction_month: string | null; source: string; account: string; dsp: string; territory: string;
  monetization: string; content_origin: string; amount_usd: number; units: number; rows: number };
type Track = { identity_key: string; isrc: string | null; title: string; base_amount_usd: number; units: number; segments: Segment[];
  pending: { reason: string; amount_usd: number }[]; records?: Origin[] };
type TrackData = { tracks: Track[]; restricted: boolean; beneficiary: string | null; registry_revision: string; period_basis: string };

function Origins({ rows }: { rows: Origin[] }) {
  const [page, setPage] = useState(0);
  const start = page * 20;
  return <details className={styles.origins}><summary>Registros consolidados de origen · {rows.length.toLocaleString("es-AR")} grupos</summary>
    <div className={styles.scroll}><table><thead><tr><th>Statement / consumo</th><th>Distribuidora / cuenta</th><th>Plataforma / territorio</th><th>Unidades / registros</th><th>Ingreso USD</th></tr></thead>
      <tbody>{rows.slice(start, start + 20).map((row, i) => <tr key={start + i}><td>{row.statement_month}<small>Consumo: {row.transaction_month || "Sin informar"}</small></td>
        <td>{row.source}<small>{row.account}</small></td><td>{row.dsp || "Sin informar"}<small>{row.territory || "Sin informar"} · {row.monetization || ""} · {row.content_origin || ""}</small></td>
        <td>{Math.round(row.units || 0).toLocaleString("es-AR")}<small>{row.rows.toLocaleString("es-AR")} registros</small></td><td>{money(row.amount_usd)}</td></tr>)}</tbody></table></div>
    <div className={styles.pagination}><span>{start + 1}–{Math.min(start + 20, rows.length)} de {rows.length}</span>
      <button type="button" disabled={!page} onClick={() => setPage(page - 1)} aria-label="Registros anteriores"><ChevronLeft size={16} /></button>
      <button type="button" disabled={start + 20 >= rows.length} onClick={() => setPage(page + 1)} aria-label="Registros siguientes"><ChevronRight size={16} /></button>
    </div>
  </details>;
}

export function RoyaltyTrackDrawer({ selection, params, onClose }: { selection: ExplorerRank | null; params: string; onClose: () => void }) {
  const [data, setData] = useState<TrackData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const panel = useRef<HTMLElement>(null);
  const close = useRef(onClose); close.current = onClose;
  useEffect(() => {
    if (!selection) return;
    const controller = new AbortController(); setData(null); setError(""); setLoading(true);
    const query = new URLSearchParams(params); query.delete("measure");
    if (selection.identity_key) query.set("track_key", selection.identity_key); else query.set("track_title", selection.name);
    void fetch(`/api/royalties-dashboard/track?${query}`, { cache: "no-store", signal: controller.signal }).then(async (r) => {
      const body = await r.json(); if (!r.ok) throw new Error(body.error || "No se pudo consultar el reparto."); return body;
    }).then((body: TrackData) => { if (!controller.signal.aborted) setData(body); })
      .catch((e) => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "No se pudo consultar el reparto."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [selection, params]);
  useEffect(() => {
    if (!selection) return;
    const previous = document.activeElement as HTMLElement | null, overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const listener = (event: KeyboardEvent) => {
      if (event.key === "Escape") close.current();
      if (event.key === "Tab" && panel.current) {
        const elements = panel.current.querySelectorAll<HTMLElement>('button:not(:disabled),summary,a[href],input,select');
        const first = elements[0], last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener("keydown", listener);
    return () => { document.body.style.overflow = overflow; document.removeEventListener("keydown", listener); previous?.focus(); };
  }, [selection]);
  if (!selection) return null;
  return <div className={styles.backdrop} onClick={onClose}><aside ref={panel} className={styles.drawer} role="dialog" aria-modal="true" aria-label={`Reparto de ${selection.name}`} onClick={(e) => e.stopPropagation()}>
    <header><div><span>Detalle del ingreso y contrato</span><h2>{selection.name}</h2></div><button type="button" aria-label="Cerrar detalle" onClick={onClose}><X size={20} /></button></header>
    {loading && <p role="status">Consultando el reparto del período seleccionado…</p>}
    {error && <p className={styles.notice} role="alert">{error}</p>}
    {data && !data.tracks.length && <p>No hay ingresos de este tema dentro de los filtros seleccionados.</p>}
    {data?.tracks.map((track) => <details key={track.identity_key} className={styles.track} open={data.tracks.length === 1}>
      <summary>{track.title} <small>{track.isrc || "Referencia sin ISRC asociado"}</small></summary>
      <div className={styles.base}><span>Ingreso reportable del tema · filtros actuales</span><strong>{money(track.base_amount_usd)}</strong><small>{Math.round(track.units).toLocaleString("es-AR")} unidades</small></div>
      {track.segments.map((segment, i) => <section className={styles.segment} key={`${segment.version}-${segment.from}-${i}`}>
        <h3>{segment.label} · versión {segment.version}</h3><p>Vigente: {segment.from} a {segment.until || "actual"}<br />Statements incluidos: {segment.months.join(", ")}</p>
        <div className={styles.segmentBase}>Ingreso en esta vigencia: <strong>{money(segment.base_amount_usd)}</strong></div>
        {data.restricted ? <div className={styles.own}><span>Tu participación · {percentage(segment.own_share?.percent || 0)}</span><strong>{money(segment.own_share?.amount_usd || 0)}</strong></div> : <table><thead><tr><th>Beneficiario</th><th>Porcentaje</th><th>Importe USD</th></tr></thead><tbody>{segment.shares?.map((share) => <tr key={share.name}><td>{share.name}<details><summary>Composición</summary>{share.origins.map((origin, j) => <small key={j}>{origin.label}: {percentage(origin.percent)}</small>)}</details></td><td>{percentage(share.percent)}</td><td>{money(share.amount_usd)}</td></tr>)}</tbody></table>}
      </section>)}
      {track.pending.map((p, i) => <p key={i} className={styles.notice}>{money(p.amount_usd)} pendientes de reparto · {p.reason}</p>)}
      {!data.restricted && track.records && <Origins rows={track.records} />}
    </details>)}
  </aside></div>;
}
