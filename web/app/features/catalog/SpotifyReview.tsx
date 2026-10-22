"use client";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Check, ChevronLeft, ChevronRight, ExternalLink, RefreshCw, ShieldCheck, Search } from "lucide-react";
import styles from "./SpotifyReview.module.css";

type Values = Record<string, string | number | string[] | boolean | null>;
type Item = { catalog_key: string; isrc: string | null; title: string; ours: Values; spotify: Values; provider: string;
  protected: Record<string, { by?: string; date?: string; reason?: string }>; differences: string[];
  decisions: Record<string, string>; status: string; observation_version: number; review_version: number;
  fetched_at: string; origin: string; reviewed_by: string | null; reviewed_at: string; sources: string };
type Data = { items: Item[]; total: number; offset: number; summary: Record<string, number> };
const labels: Record<string, string> = { all: "Todos", pending: "Diferencias por revisar", matching: "Coinciden",
  reviewed: "Validados", protected: "Corrección manual protegida", not_consulted: "Sin consultar",
  not_found: "No encontrado", ambiguous: "Coincidencia dudosa", rate_limited: "En pausa" };
const fields = [["track_title", "Título"], ["artists", "Artistas del tema"], ["duration_seconds", "Duración (segundos)"],
  ["release_date", "Fecha de lanzamiento"], ["label", "Sello"]];
function value(x: unknown) { return Array.isArray(x) ? x.join(" / ") : x === null || x === undefined || x === "" ? "No informado" : String(x); }
function date(x: string) { return x ? new Date(x).toLocaleString("es-AR") : "Sin consulta"; }
async function request(url: string, init?: RequestInit) {
  const r = await fetch(url, { cache: "no-store", ...init }); const d = await r.json();
  if (!r.ok) throw new Error(typeof d.error === "string" ? d.error : "No se pudo completar la operación.");
  return d;
}
export function SpotifyReview({ canEdit, onBack }: { canEdit: boolean; onBack: () => void }) {
  const [data, setData] = useState<Data | null>(null), [query, setQuery] = useState(""), [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState("all"), [offset, setOffset] = useState(0), [selected, setSelected] = useState<string | null>(null);
  const [checked, setChecked] = useState<string[]>([]), [busy, setBusy] = useState(false), [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(""), [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true);
    try { setData(await request(`/api/catalog/spotify-review?keyword=${encodeURIComponent(keyword)}&status=${status}&offset=${offset}&limit=20`)); setError(""); }
    catch (e) { setError(e instanceof Error ? e.message : "Error al consultar."); }
    finally { setLoading(false); }
  }, [keyword, status, offset]);
  useEffect(() => { void load(); }, [load]);
  async function post(body: Record<string, unknown>) { return request("/api/catalog/spotify-review", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); }
  async function decide(item: Item, field: string, decision: string) {
    setBusy(true); setError(""); setMessage("");
    try { await post({ catalog_key: item.catalog_key, field, decision, observation_version: item.observation_version, review_version: item.review_version });
      setMessage(decision === "accept" ? "Diferencia validada. La corrección quedó registrada." : "Se conservó nuestro dato."); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "No se pudo validar."); }
    finally { setBusy(false); }
  }
  async function refresh(keys: string[]) {
    setBusy(true); setError(""); setMessage(""); let complete = 0;
    try { for (const key of keys) { setMessage(`Consultando Spotify / YouTube ${complete + 1} de ${keys.length}…`); await post({ action: "refresh", catalog_key: key }); complete++; }
      setMessage(`${complete} consulta${complete === 1 ? "" : "s"} actualizada${complete === 1 ? "" : "s"}.`); }
    catch (e) { setError(`${complete} consultas completadas. ${e instanceof Error ? e.message : "No se pudo continuar."}`); }
    finally { await load(); setBusy(false); }
  }
  const current = data?.items.find((item) => item.catalog_key === selected);
  const provider = current?.provider === "youtube" ? "YouTube" : "Spotify";
  return <section className={styles.workspace}>
    <header className={styles.header}>
      <button className={styles.icon} onClick={onBack} disabled={busy} aria-label="Volver al catálogo"><ArrowLeft size={20}/></button>
      <div><span>Catálogo y distribución</span><h1>Nuestro catálogo vs. Spotify y YouTube</h1><p>Spotify primero. YouTube como alternativa, con el video vinculado al tema.</p></div>
      <button className={styles.button} onClick={() => void load()} disabled={loading || busy}><RefreshCw size={16}/>Actualizar vista</button>
    </header>
    <div className={styles.stats}>{["pending", "reviewed", "protected", "not_consulted"].map((key) => <button key={key} onClick={() => { setStatus(key); setOffset(0); }}><strong>{data?.summary[key] || 0}</strong><span>{labels[key]}</span></button>)}</div>
    <form className={styles.toolbar} onSubmit={(e) => { e.preventDefault(); setKeyword(query); setOffset(0); setSelected(null); }}>
      <div><Search size={16}/><input aria-label="Buscar tema, artista o ISRC" placeholder="Tema, artista o ISRC" value={query} onChange={(e) => setQuery(e.target.value)}/></div>
      <button className={styles.button} type="submit">Buscar</button>
      <select aria-label="Estado de revisión" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); setSelected(null); }}>{Object.entries(labels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
      {canEdit && <button className={styles.button} type="button" disabled={busy || !data?.items.length} onClick={() => setChecked(Array.from(new Set([...checked, ...(data?.items.map(item => item.catalog_key) || [])])))}>Seleccionar página</button>}
      {canEdit && <button className={styles.primary} type="button" disabled={busy || !checked.length} onClick={() => void refresh(checked)}><RefreshCw size={16}/>Consultar selección ({checked.length})</button>}
    </form>
    {error && <div className={styles.error} role="alert">{error}</div>}{message && <div className={styles.notice} role="status">{message}</div>}
    <div className={styles.layout}>
      <div><div className={styles.tableWrap}><table><thead><tr><th aria-label="Seleccionar"/><th>Tema</th><th>Estado</th><th>Última consulta</th></tr></thead><tbody>
        {data?.items.map((item) => <tr key={item.catalog_key} className={selected === item.catalog_key ? styles.selected : ""}>
          <td><input type="checkbox" aria-label={`Seleccionar ${item.title}`} checked={checked.includes(item.catalog_key)} disabled={busy || !canEdit} onChange={(e) => setChecked((old) => e.target.checked ? [...old, item.catalog_key] : old.filter((key) => key !== item.catalog_key))}/></td>
          <td><button className={styles.title} onClick={() => setSelected(item.catalog_key)}>{item.title}</button><small>{item.isrc || item.catalog_key}</small><small>{value(item.ours.artists)}</small></td>
          <td><span className={styles.badge}>{labels[item.status] || item.status}</span>{item.differences.length > 0 && <small>{item.differences.length} diferencias</small>}</td>
          <td>{date(item.fetched_at)}</td>
        </tr>)}{!loading && data?.items.length === 0 && <tr><td colSpan={4}>No hay temas para este filtro.</td></tr>}
      </tbody></table></div>
      <div className={styles.pagination}><span>{data?.total || 0} temas</span><button className={styles.icon} aria-label="Anterior" disabled={offset === 0 || loading} onClick={() => setOffset(offset - 20)}><ChevronLeft size={18}/></button><button className={styles.icon} aria-label="Siguiente" disabled={!data || offset + 20 >= data.total || loading} onClick={() => setOffset(offset + 20)}><ChevronRight size={18}/></button></div></div>
      <aside className={styles.detail}>{current ? <>
        <h2>{current.title}</h2><p>{current.isrc || current.catalog_key} · {current.sources}</p>
        <div className={styles.detailActions}>{canEdit && <button className={styles.button} disabled={busy} onClick={() => void refresh([current.catalog_key])}><RefreshCw size={15}/>Consultar fuentes</button>}
          {current.spotify.url && <a className={styles.button} href={String(current.spotify.url)} target="_blank" rel="noreferrer"><ExternalLink size={15}/>Abrir {provider}</a>}</div>
        <p className={styles.muted}>{current.origin === "legacy_cache" ? "Consulta anterior recuperada" : current.origin === "youtube_live" ? "YouTube: alternativa a Spotify" : current.origin === "spotify_live" ? "Consulta directa a Spotify" : "Sin consulta"} · {date(current.fetched_at)}</p>
        {!!current.observation_version && !current.spotify.exact_isrc && current.provider !== "youtube" && <div className={styles.notice}>No hay una coincidencia exacta y única por ISRC para aprobar.</div>}
        <div className={styles.comparisonHeading}><span>Nuestro catálogo</span><span>{provider}</span></div>
        {fields.map(([field, label]) => <div className={styles.field} key={field}>
          <h3>{label}{current.protected[field] && <span className={styles.lock}><ShieldCheck size={14}/>Protegido</span>}</h3>
          <div className={`${styles.values} ${current.differences.includes(field) ? styles.difference : ""}`}><span>{value(current.ours[field])}</span><span>{value(current.spotify[field])}</span></div>
          {current.protected[field] && <small>Confirmado por {current.protected[field].by || "el equipo"}{current.protected[field].date ? ` · ${current.protected[field].date}` : ""}</small>}
          {current.decisions[field] && <small className={styles.validated}><Check size={13}/>{current.decisions[field] === "accept" ? `Dato de ${provider} aprobado` : "Se conserva nuestro dato"}</small>}
          {canEdit && current.differences.includes(field) && !!current.observation_version && <div className={styles.fieldActions}>
            {!current.protected[field] && <button className={styles.primary} disabled={busy || (current.provider === "youtube" ? !["track_title", "duration_seconds"].includes(field) : !current.spotify.exact_isrc) || current.spotify.status !== "found"} onClick={() => void decide(current, field, "accept")}>Aceptar {provider}</button>}
            <button className={styles.button} disabled={busy} onClick={() => void decide(current, field, "keep")}>Conservar nuestro dato</button>
          </div>}
        </div>)}
        {current.spotify.fallback_note && <div className={styles.notice}>{value(current.spotify.fallback_note)}</div>}
        <div className={styles.context}>{current.provider === "youtube" ? <><h3>Video vinculado en YouTube</h3><p>Canal: {value(current.spotify.channel)}</p><small>Publicado: {value(current.spotify.published_at)}. Esta fecha corresponde al video; el canal no se toma como artista ni sello.</small></> : <><h3>Contexto del álbum en Spotify</h3><p>{value(current.spotify.album)}</p><small>{value(current.spotify.album_artists)}</small></>}</div>
        {current.reviewed_by && <p className={styles.muted}>Última validación: {current.reviewed_by} · {date(current.reviewed_at)}</p>}
      </> : <div className={styles.empty}><ShieldCheck size={30}/><h2>Elegí un tema</h2><p>Vas a ver nuestros datos, la consulta de Spotify y las correcciones protegidas.</p></div>}</aside>
    </div>
  </section>;
}
