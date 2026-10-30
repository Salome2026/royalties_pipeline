"use client";
import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import styles from "./RoyaltyExplorer.module.css";

export type ExplorerState = { measure: "income" | "contractual"; beneficiary: string; drill: Record<string, string>; trackName?: string };
export const initialExplorer: ExplorerState = { measure: "income", beneficiary: "", drill: {} };
export type ExplorerRank = { name: string; identity_key?: string; amount_usd: number; pending_amount_usd?: number; youtube_only?: boolean; aggregate_identity?: boolean };
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
const drillLabels: Record<string, string> = { month: "Mes", source: "Distribuidora", account: "Cuenta", dsp: "Plataforma", artist: "Artista del catálogo", monetization: "Monetización", content_origin: "Origen", territory: "Territorio", label: "Sello", track: "Tema" };

export function RoyaltyContextAction({ state, keyword, restricted = false, loading, onChange }: {
  state: ExplorerState; keyword: string; restricted?: boolean; loading: boolean;
  onChange: (state: ExplorerState) => void;
}) {
  const [match, setMatch] = useState<{ keyword: string; participant: string | null } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const query = new URLSearchParams({ keyword });
    void fetch(`/api/royalties-dashboard/explorer-options?${query}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => { if (!response.ok) return null; return response.json(); })
      .then((data: { participant: string | null } | null) => {
        if (!controller.signal.aborted) setMatch({ keyword, participant: data?.participant || null });
      }).catch(() => { if (!controller.signal.aborted) setMatch({ keyword, participant: null }); });
    return () => controller.abort();
  }, [keyword, restricted]);
  const participant = state.beneficiary || (match?.keyword === keyword ? match.participant : null);
  if (!participant) return null;
  const own = state.measure === "contractual";
  return <div className={styles.contextAction}>
    {own && <span>Mostrando {restricted ? "tu parte" : `la parte de ${participant}`}{state.drill.track && state.trackName ? ` · ${state.trackName}` : ""}</span>}
    <button type="button" disabled={loading} onClick={() => onChange({ ...state, measure: own ? "income" : "contractual", beneficiary: participant })}>
      {own ? "Ver ingresos completos" : restricted ? "Ver mi parte" : `Ver parte de ${participant}`}
    </button>
  </div>;
}

export function RoyaltyExplorerTrail({ state, loading, onChange }: { state: ExplorerState; loading: boolean; onChange: (state: ExplorerState) => void }) {
  if (!Object.keys(state.drill).length) return null;
  return <nav className={styles.trail} aria-label="Filtros de exploración">
    <button type="button" disabled={loading} onClick={() => onChange({ ...state, drill: {} })}>Volver a {state.beneficiary || "la vista general"}</button>
    {Object.entries(state.drill).filter(([key]) => key !== "track_title").map(([key, value]) => <button type="button" key={key} disabled={loading} onClick={() => { const drill = { ...state.drill }; delete drill[key]; if (key === "track") delete drill.track_title; onChange({ ...state, drill }); }}>{drillLabels[key] || key}: {key === "track" ? state.trackName || value : value}<X size={13} aria-hidden="true" /></button>)}
  </nav>;
}

export function RoyaltyExplorerPending({ info, onOpen }: { info?: ExplorerInfo; onOpen: (row: ExplorerRank) => void }) {
  if (!info?.pending_tracks) return null;
  return <details className={styles.pending}>
    <summary>{money(info.pending_amount_usd)} de ingresos pendientes de reparto · {info.pending_tracks} temas o referencias</summary>
    <p>Estos importes todavía no tienen un reparto aplicable.</p>
    <table><thead><tr><th>Tema / referencia</th><th>Motivo</th><th>Ingreso USD</th></tr></thead><tbody>{info.pending.map((row) => <tr key={`${row.identity_key}-${row.reason}`}>
      <td><button type="button" onClick={() => onOpen({ name: row.title, identity_key: row.identity_key, amount_usd: row.amount_usd, aggregate_identity: true })}>{row.title || row.identity_key}</button></td>
      <td>{row.reason}</td><td>{money(row.amount_usd)}</td>
    </tr>)}</tbody></table>
  </details>;
}

type Share = { name: string; percent: number; amount_usd: number; origins: { label: string; percent: number }[] };
type Segment = { from: string; until: string | null; version: number; label: string; months: string[]; base_amount_usd: number;
  shares?: Share[]; own_share?: { percent: number; amount_usd: number } };
type Origin = { statement_month: string; transaction_month: string | null; source: string; account: string; dsp: string; territory: string;
  monetization: string; content_origin: string; amount_usd: number; units: number; rows: number };
type Track = { identity_key: string; isrc: string | null; title: string; row_title?: string | null; base_amount_usd: number; units: number; segments: Segment[];
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

export function RoyaltyTrackDrawer({ selection, params, onClose, onParticipant }: {
  selection: ExplorerRank | null; params: string; onClose: () => void;
  onParticipant?: (name: string, track: { identity_key: string; title: string; row_title?: string | null }, youtubeOnly: boolean) => void;
}) {
  const [data, setData] = useState<TrackData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const panel = useRef<HTMLElement>(null);
  const close = useRef(onClose); close.current = onClose;
  useEffect(() => {
    if (!selection) return;
    const controller = new AbortController(); setData(null); setError(""); setLoading(true);
    const query = new URLSearchParams(params); query.delete("measure");
    query.delete("track_key"); query.delete("track_title");
    if (selection.identity_key) query.set("track_key", selection.identity_key);
    if (!selection.aggregate_identity) query.set("track_title", selection.name);
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
    <header><div><span>Reparto del tema</span><h2>{selection.name}</h2></div><button type="button" aria-label="Cerrar detalle" onClick={onClose}><X size={20} /></button></header>
    {loading && <p role="status">Consultando el reparto del período seleccionado…</p>}
    {error && <p className={styles.notice} role="alert">{error}</p>}
    {data && !data.tracks.length && <p>No hay ingresos de este tema dentro de los filtros seleccionados.</p>}
    {data?.tracks.map((track) => <details key={track.identity_key} className={styles.track} open={data.tracks.length === 1}>
      <summary>{track.title} <small>{track.isrc || "Referencia sin ISRC asociado"}</small></summary>
      <div className={styles.base}><span>Ingreso reportable del tema · filtros actuales</span><strong>{money(track.base_amount_usd)}</strong><small>{Math.round(track.units).toLocaleString("es-AR")} unidades</small></div>
      {track.segments.map((segment, i) => <section className={styles.segment} key={`${segment.version}-${segment.from}-${i}`}>
        <h3>{segment.label} · versión {segment.version}</h3><p>Vigente: {segment.from} a {segment.until || "actual"}<br />Statements incluidos: {segment.months.join(", ")}</p>
        <div className={styles.segmentBase}>Ingreso en esta vigencia: <strong>{money(segment.base_amount_usd)}</strong></div>
        {data.restricted ? <div className={styles.own}><span>Tu participación · {percentage(segment.own_share?.percent || 0)}</span><strong>{money(segment.own_share?.amount_usd || 0)}</strong></div> : <table><thead><tr><th>Participante</th><th>Porcentaje</th><th>Importe USD</th></tr></thead><tbody>{segment.shares?.map((share) => <tr key={share.name} className={explorerKey(share.name) === explorerKey(data.beneficiary || "") ? styles.selectedShare : undefined}><td>{onParticipant ? <button type="button" className={styles.participantLink} onClick={() => onParticipant(share.name, track, !!selection.youtube_only)}>{share.name}</button> : share.name}<details><summary>Composición</summary>{share.origins.map((origin, j) => <small key={j}>{origin.label}: {percentage(origin.percent)}</small>)}</details></td><td>{percentage(share.percent)}</td><td>{money(share.amount_usd)}</td></tr>)}</tbody></table>}
      </section>)}
      {track.pending.map((p, i) => <p key={i} className={styles.notice}>{money(p.amount_usd)} pendientes de reparto · {p.reason}</p>)}
      {!data.restricted && !!track.records?.length && <Origins rows={track.records} />}
    </details>)}
  </aside></div>;
}
