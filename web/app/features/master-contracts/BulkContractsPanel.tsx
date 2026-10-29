"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft } from "lucide-react";
import type { ContractDetail, ContractItem, Split } from "./MasterContractsModule";
import { pendingAssociationCodes, type Association } from "./associationLogic";
import { agreementAllocation, contractErrors, previewAllocation } from "./contractLogic";
import { applyContractModel, closingErrors, detailAgreements, modelErrors, participantDifference } from "./bulkContractLogic";
import styles from "./MasterContractsModule.module.css";

type Selection = { index: number; from: string; until: string; accepted: boolean; enabled: boolean };
type Review = { detail: ContractDetail; split: Split; pending: number | null; reason: string; error: string };
type Result = { isrc: string; title: string; state: "closed" | "open" | "error"; message: string };
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: "no-store", ...init });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Error ${response.status}`);
  return body as T;
}
const endpoint = (isrc: string) => `/api/master-contracts/${encodeURIComponent(isrc)}`;
async function mapLimited<T, U>(items: T[], fn: (item: T) => Promise<U>): Promise<U[]> {
  const output = new Array<U>(items.length); let index = 0;
  await Promise.all(Array.from({ length: Math.min(3, items.length) }, async () => {
    while (index < items.length) { const i = index++; output[i] = await fn(items[i]); }
  }));
  return output;
}

export function BulkContractsPanel({ items, canApprove, onBack, onOpen }: {
  items: ContractItem[]; canApprove: boolean; onBack: () => void; onOpen: (isrc: string) => void;
}) {
  const [details, setDetails] = useState<ContractDetail[]>([]);
  const [loadErrors, setLoadErrors] = useState<string[]>([]);
  const [modelIsrc, setModelIsrc] = useState("");
  const [modelIndex, setModelIndex] = useState(0);
  const [selection, setSelection] = useState<Record<string, Selection>>({});
  const [reviews, setReviews] = useState<Review[] | null>(null);
  const [results, setResults] = useState<Result[] | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const mounted = useRef(true);
  const saving = useRef(false);
  useEffect(() => {
    mounted.current = true;
    void mapLimited(items, async (item) => {
      try { return { detail: await request<ContractDetail>(endpoint(item.isrc)), error: "" }; }
      catch (e) { return { detail: null, error: `${item.title}: ${e instanceof Error ? e.message : "No se pudo cargar"}` }; }
    }).then((loaded) => {
      if (!mounted.current) return;
      const data = loaded.flatMap((r) => r.detail ? [r.detail] : []);
      setDetails(data); setLoadErrors(loaded.flatMap((r) => r.error ? [r.error] : []));
      setModelIsrc(data.find((d) => !modelErrors(d, 0).length)?.isrc || data[0]?.isrc || "");
      setSelection(Object.fromEntries(data.map((d) => { const a = detailAgreements(d)[0]; return [d.isrc,
        { index: 0, from: a.effective_from || "", until: a.effective_until || "", accepted: false, enabled: !d.closed }]; })));
      setBusy(false);
    });
    return () => { mounted.current = false; };
    // The selected page is fixed for the lifetime of this panel.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (!busy) return;
    const block = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    window.addEventListener("beforeunload", block);
    return () => window.removeEventListener("beforeunload", block);
  }, [busy]);
  const model = details.find((d) => d.isrc === modelIsrc);
  const source = model ? detailAgreements(model)[modelIndex] : undefined;
  const sourceErrors = model ? modelErrors(model, modelIndex) : [];
  const preview = model && source ? previewAllocation(source, agreementAllocation(source, model.split), 100) : null;
  function update(isrc: string, patch: Partial<Selection>) {
    setSelection((value) => ({ ...value, [isrc]: { ...value[isrc], ...patch } })); setReviews(null); setConfirmed(false);
  }
  async function prepare() {
    if (!model || sourceErrors.length || busy) return;
    setBusy(true); setError(""); setReviews(null); setConfirmed(false);
    try {
      const targets = details.filter((d) => selection[d.isrc]?.enabled && !d.closed);
      if (!targets.length) throw new Error("Seleccioná al menos un tema para aplicar el contrato.");
      const rows = await mapLimited(targets, async (detail): Promise<Review> => {
        const s = selection[detail.isrc], diff = participantDifference(model, modelIndex, detail, s.index);
        const split = applyContractModel(model, modelIndex, detail, s.index, s.from || null, s.until || null);
        const errors = contractErrors(split.agreements || [], split);
        if (source?.allocation_model === "pools" && !detail.pool_contracts_supported) errors.push("Volvé a abrir la ficha: falta confirmar la compatibilidad del servicio.");
        if (source?.distribution_recipients != null && !detail.distribution_recipients_supported) errors.push("El servicio todavía no admite los destinatarios de este modelo.");
        if (diff.missing.length) errors.push(`Faltan participantes: ${diff.missing.join(", ")}. Revisá este tema individualmente.`);
        if (diff.extra.length && !s.accepted) errors.push("Confirmá los participantes distintos antes de aplicar.");
        if (errors.length) return { detail, split, pending: null, reason: "", error: errors.join(" ") };
        try {
          const a = await request<{ items: Association[]; version: number }>(`${endpoint(detail.isrc)}/associations`);
          if (a.version !== detail.version) return { detail, split, pending: null, reason: "", error: "La ficha cambió. Volvé al catálogo y prepará una nueva selección." };
          const pending = pendingAssociationCodes(a.items, detail.split.code_association_overrides || []).length;
          const reason = [...closingErrors(split), ...(pending ? [`${pending} códigos por validar`] : [])].join(" · ");
          return { detail, split, pending, reason, error: "" };
        } catch {
          return { detail, split, pending: null, reason: "No se pudieron verificar los códigos; se guardará abierto.", error: "" };
        }
      });
      setReviews(rows);
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudo preparar la selección."); }
    finally { setBusy(false); }
  }
  async function apply(closeEligible: boolean) {
    if (!model || !reviews || !confirmed || saving.current || busy) return;
    saving.current = true; setBusy(true); setError(""); const done: Result[] = [];
    try {
      const current = await request<ContractDetail>(endpoint(model.isrc));
      if (current.version !== model.version) throw new Error("El modelo cambió desde la revisión. Volvé a preparar la selección.");
      for (const row of reviews) {
        setProgress(`${done.length + 1} de ${reviews.length}: ${row.detail.title}`);
        if (row.error) { done.push({ isrc: row.detail.isrc, title: row.detail.title, state: "error", message: row.error }); continue; }
        const closed = closeEligible && canApprove && row.pending === 0 && !row.reason;
        const save = (close: boolean) => request<{ closed: boolean }>(endpoint(row.detail.isrc), {
          method: "PUT", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ split: row.split, closed: close, expected_version: row.detail.version,
            future_reports_selected: false, complete_association_review: false }),
        });
        try {
          let saved: { closed: boolean }; let reason = row.reason;
          try { saved = await save(closed); }
          catch (original) {
            if (!closed) throw original;
            // New evidence can arrive after preview. Only downgrade closure when that is the confirmed cause.
            const now = await request<{ items: Association[]; version: number }>(`${endpoint(row.detail.isrc)}/associations`);
            if (now.version !== row.detail.version || !pendingAssociationCodes(now.items, row.detail.split.code_association_overrides || []).length) throw original;
            saved = await save(false); reason = "Aparecieron códigos por validar después de la revisión.";
          }
          done.push({ isrc: row.detail.isrc, title: row.detail.title, state: saved.closed ? "closed" : "open", message: saved.closed ? "Contrato aplicado y cerrado" : reason || "Contrato aplicado; guardado abierto" });
        } catch (e) { done.push({ isrc: row.detail.isrc, title: row.detail.title, state: "error", message: e instanceof Error ? e.message : "No se pudo guardar" }); }
        setResults([...done]);
      }
      setResults([...done]);
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudo aplicar el contrato."); }
    finally { saving.current = false; setBusy(false); setProgress(""); }
  }
  return <section className={styles.workspace} aria-label="Aplicar contrato a seleccionados">
    <button type="button" className={styles.secondaryButton} disabled={busy} onClick={onBack}><ArrowLeft size={16} />Volver al catálogo</button>
    <div className={styles.heading}><h1>Aplicar contrato a seleccionados</h1></div>
    <p className={styles.auditLine}>Elegí un contrato guardado como modelo. Revisá el reparto y las vigencias de cada tema antes de confirmar.</p>
    {error && <p className={styles.warning} role="alert">{error}</p>}
    {loadErrors.map((e) => <p key={e} className={styles.warning}>{e}</p>)}
    <p role="status" aria-live="polite">{progress || (busy ? "Cargando y verificando contratos…" : "")}</p>
    {results ? <>
      {!busy && <p role="status">{results.filter((r) => r.state !== "error").length} contratos aplicados: {results.filter((r) => r.state === "closed").length} cerrados y {results.filter((r) => r.state === "open").length} abiertos. {results.filter((r) => r.state === "error").length} sin aplicar.</p>}
      <div className={styles.tableWrap}><table className={styles.table}><thead><tr><th>Tema</th><th>ISRC</th><th>Resultado</th></tr></thead><tbody>{results.map((r) => <tr key={r.isrc}><td><button className={styles.titleButton} disabled={busy} onClick={() => onOpen(r.isrc)}>{r.title}</button></td><td>{r.isrc}</td><td>{r.message}</td></tr>)}</tbody></table></div>
    </> : <>
      <div className={styles.agreementFields}>
        <label>Usar como modelo<select value={modelIsrc} disabled={busy} onChange={(e) => { setModelIsrc(e.target.value); setModelIndex(0); setReviews(null); setConfirmed(false); setSelection((values) => Object.fromEntries(Object.entries(values).map(([k, v]) => [k, { ...v, accepted: false }]))); }}>{details.map((d) => <option key={d.isrc} value={d.isrc}>{d.title} · {d.isrc}</option>)}</select></label>
        {model && <label>Contrato del modelo<select value={modelIndex} disabled={busy} onChange={(e) => { setModelIndex(Number(e.target.value)); setReviews(null); setConfirmed(false); setSelection((values) => Object.fromEntries(Object.entries(values).map(([k, v]) => [k, { ...v, accepted: false }]))); }}>{detailAgreements(model).map((a, i) => <option key={a.id} value={i}>{a.label || `Contrato ${i + 1}`}</option>)}</select></label>}
      </div>
      {model && sourceErrors.length > 0 && <p className={styles.warning}>{sourceErrors.join(" ")} <button className={styles.titleButton} disabled={busy} onClick={() => onOpen(model.isrc)}>Abrir tema para definir el modelo</button></p>}
      {preview && <div className={styles.bulkPreview}><strong>Reparto que se aplicará · {source?.commercialization === "master" ? "Master" : "Distribución"}</strong>{preview.map((r) => <span key={r.artist}>{r.artist}: {r.percent.toLocaleString("es-AR", { maximumFractionDigits: 4 })}%</span>)}</div>}
      <div className={styles.tableWrap}><table className={`${styles.table} ${styles.bulkTable}`}><thead><tr><th>Aplicar</th><th>Tema / ISRC</th><th>Contrato a reemplazar</th><th>Vigencia desde</th><th>Hasta</th><th>Revisión</th></tr></thead><tbody>
        {details.map((d) => { const s = selection[d.isrc]; if (!s) return null; const diff = model ? participantDifference(model, modelIndex, d, s.index) : { missing: [], extra: [] }; const review = reviews?.find((r) => r.detail.isrc === d.isrc);
          return <tr key={d.isrc}><td><input aria-label={`Aplicar a ${d.title}`} type="checkbox" checked={s.enabled} disabled={busy || d.closed} onChange={(e) => update(d.isrc, { enabled: e.target.checked })} /></td>
            <td>{d.title}<small>{d.isrc}{d.closed ? " · Ya está cerrado: no se modificará" : d.version ? " · Reemplaza el reparto guardado del período elegido" : " · Sin reparto guardado"}</small></td>
            <td><select aria-label={`Contrato de ${d.title}`} disabled={busy} value={s.index} onChange={(e) => { const index = Number(e.target.value), a = detailAgreements(d)[index]; update(d.isrc, { index, from: a.effective_from || "", until: a.effective_until || "", accepted: false }); }}>{detailAgreements(d).map((a, i) => <option key={a.id} value={i}>{a.label || `Contrato ${i + 1}`}</option>)}</select>{detailAgreements(d).length > 1 && <small>Los otros períodos se conservan.</small>}</td>
            <td><input aria-label={`Vigente desde ${d.title}`} type="date" value={s.from.length === 7 ? `${s.from}-01` : s.from} disabled={busy} onChange={(e) => update(d.isrc, { from: e.target.value })} /></td>
            <td><input aria-label={`Vigente hasta ${d.title}`} type="date" value={s.until.length === 7 ? `${s.until}-${new Date(Number(s.until.slice(0, 4)), Number(s.until.slice(5, 7)), 0).getDate()}` : s.until} disabled={busy} onChange={(e) => update(d.isrc, { until: e.target.value })} /></td>
            <td>{diff.missing.length > 0 && <small className={styles.warning}>Faltan en el modelo: {diff.missing.join(", ")}. Revisar individualmente.</small>}{diff.extra.length > 0 && <label><input type="checkbox" checked={s.accepted} disabled={busy} onChange={(e) => update(d.isrc, { accepted: e.target.checked })} />Confirmo agregar: {diff.extra.join(", ")}</label>}{review && <small>{review.error || review.reason || "Listo para guardar y cerrar"}</small>}</td>
          </tr>;
        })}
      </tbody></table></div>
      <div className={styles.bulkToolbar}><button className={styles.secondaryButton} disabled={busy || !model || !!sourceErrors.length} onClick={() => void prepare()}>Revisar aplicación</button>
        {reviews && <><label><input type="checkbox" checked={confirmed} disabled={busy} onChange={(e) => setConfirmed(e.target.checked)} />Confirmo el reparto y las vigencias de los temas seleccionados.</label>
          <button className={styles.secondaryButton} disabled={busy || !confirmed || reviews.every((r) => !!r.error)} onClick={() => void apply(false)}>Guardar abiertos</button>
          {canApprove && <button className={styles.primaryButton} disabled={busy || !confirmed || reviews.every((r) => !!r.error)} onClick={() => void apply(true)}>Guardar y cerrar los completos</button>}</>}
      </div>
    </>}
  </section>;
}
