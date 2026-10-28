"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Check, Link2, Search, X } from "lucide-react";
import styles from "./MasterContractsModule.module.css";
import type { UnidentifiedIncome } from "./UnidentifiedIncomeTable";

type Target = { isrc: string; title: string; artists: string };
type Preview = { reference_signature: string; release_id: string; target: Target & { version: number; closed: boolean } };
async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: "no-store", ...init });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.error === "string" ? body.error : "No se pudo verificar la asociacion.");
  return body as T;
}

export function AssociateIncomeDialog({ reference, canApprove, onClose, onSaved }: {
  reference: UnidentifiedIncome; canApprove: boolean; onClose: () => void; onSaved: (isrc: string) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const sequence = useRef(0);
  const [keyword, setKeyword] = useState("");
  const [targets, setTargets] = useState<Target[]>(reference.candidates);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [searched, setSearched] = useState(false);
  const supported = !!reference.code && ["VIDEO", "TRACK", "UPC"].includes(reference.kind);
  const endpoint = `/api/master-contracts/unidentified/${encodeURIComponent(reference.id)}/association`;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.showModal();
    return () => { sequence.current++; document.body.style.overflow = overflow; previous?.focus(); };
  }, []);

  async function search(event: FormEvent) {
    event.preventDefault();
    const request = ++sequence.current;
    setBusy(true); setError(""); setPreview(null); setSelected(""); setSearched(true);
    try {
      const result = await json<{ items: Target[] }>(`/api/master-contracts/unidentified/destinations?${new URLSearchParams({ keyword })}`);
      if (request === sequence.current) setTargets(result.items);
    } catch (reason) { if (request === sequence.current) setError(String(reason instanceof Error ? reason.message : reason)); }
    finally { if (request === sequence.current) setBusy(false); }
  }
  async function choose(target: Target) {
    const request = ++sequence.current;
    setBusy(true); setPreview(null); setSelected(target.isrc); setError("");
    try {
      const result = await json<Preview>(`${endpoint}?${new URLSearchParams({ isrc: target.isrc })}`);
      if (request === sequence.current) setPreview(result);
    } catch (reason) { if (request === sequence.current) setError(String(reason instanceof Error ? reason.message : reason)); }
    finally { if (request === sequence.current) setBusy(false); }
  }
  async function confirm() {
    if (!preview || saving || busy) return;
    setSaving(true); setError("");
    try {
      const result = await json<{ isrc: string }>(endpoint, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ isrc: preview.target.isrc, expected_version: preview.target.version,
          release_id: preview.release_id, reference_signature: preview.reference_signature }) });
      onSaved(result.isrc);
    } catch (reason) { setPreview(null); setError(String(reason instanceof Error ? reason.message : reason)); }
    finally { setSaving(false); }
  }
  return <dialog ref={dialog} className={styles.linkDialog} aria-labelledby="associate-income-title"
    onCancel={(event) => { event.preventDefault(); if (!saving) onClose(); }}>
    <header className={styles.linkHeader}><h2 id="associate-income-title">Asociar referencia</h2>
      <button type="button" className={styles.iconButton} aria-label="Cerrar asociacion" title="Cerrar" disabled={saving} onClick={onClose}><X size={18} /></button></header>
    <div className={styles.linkReference}><strong>{reference.title}</strong><span>{reference.artist}</span>
      <small>{reference.code || "Sin codigo"} · {reference.source_accounts.map(row => `${row.source.toUpperCase()} / ${row.account.replace(/_/g, " ")}`).join(" · ")}</small>
      <span>Ingreso informado <strong>{new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(reference.amount_usd)}</strong></span></div>
    {!supported ? <p className={styles.warning} role="alert">{reference.kind === "PRODUCT"
      ? "Este producto sin ISRC conserva su identidad propia. No se puede asignar entero a una cancion."
      : "Esta referencia no tiene un codigo estable. No se puede asociar solamente por el texto."}</p> : <>
      <form className={styles.linkSearch} onSubmit={search}><label className={styles.searchBox}><Search size={16} />
        <input autoFocus aria-label="Buscar destino por tema o ISRC" placeholder="Tema o ISRC" value={keyword} disabled={saving} onChange={event => setKeyword(event.target.value)} /></label>
        <button type="submit" className={styles.iconButton} aria-label="Buscar destino" title="Buscar" disabled={busy || saving || !keyword.trim()}><Search size={17} /></button></form>
      <div className={styles.linkResults} aria-busy={busy}>
        {targets.map(target => <button type="button" key={target.isrc} aria-pressed={selected === target.isrc}
          className={`${styles.artistRow} ${selected === target.isrc ? styles.artistRowSelected : ""}`} disabled={saving}
          onClick={() => void choose(target)}><span><strong>{target.title}</strong><small>{target.artists}</small><small>{target.isrc}</small></span>{selected === target.isrc && <Check size={17} />}</button>)}
        {searched && !busy && !targets.length && <p className={styles.auditLine}>Sin coincidencias.</p>}
      </div>
      {busy && <p className={styles.auditLine} role="status">Verificando...</p>}
      {preview && <div className={styles.linkDestination}><span>Destino</span><strong>{preview.target.title}</strong><small>{preview.target.isrc}</small>
        <p>El contrato quedara abierto para revision. Sus porcentajes se conservan.</p>
        {preview.target.closed && !canApprove && <p className={styles.warning}>Necesitas permiso de aprobacion para reabrir este contrato.</p>}</div>}
    </>}
    {error && <p className={styles.warning} role="alert">{error}</p>}
    <footer className={styles.linkActions}><button type="button" className={styles.secondaryButton} disabled={saving} onClick={onClose}>Cancelar</button>
      <button type="button" className={styles.primaryButton} disabled={!preview || busy || saving || (preview.target.closed && !canApprove)} onClick={() => void confirm()}>
        <Link2 size={16} />{saving ? "Asociando..." : "Confirmar asociacion"}</button></footer>
  </dialog>;
}
