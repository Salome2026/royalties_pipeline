'use client';
import { useState } from 'react';
import styles from './Wml.module.css';

type Reference = {reference_id:string;participant:string;percent:number;evidence_status:string;
  reference_type:string;reference_scope:string;product_type:string;statement_periods:string[];source_files:string[];notes:string};
const statuses: Record<string,string>={informed:'Informado',deduced:'Deducido',hypothesis:'Hipótesis'};

export function WmlReferences({isrc}: {isrc:string}) {
  const [rows,setRows]=useState<Reference[]|null>(null);
  const [error,setError]=useState('');
  return <details className={styles.references} onToggle={async (event) => {
    if (!event.currentTarget.open || rows !== null) return;
    try {
      const response=await fetch(`/api/wml?isrc=${encodeURIComponent(isrc)}`,{cache:'no-store'});
      const body=await response.json();
      if (!response.ok) throw new Error(body.error || 'No se pudieron cargar las referencias.');
      setRows(body.items || []);
    } catch (e) {setError(e instanceof Error ? e.message : 'Error al consultar WML.');}
  }}>
    <summary>Referencias WML · porcentajes y evidencia</summary>
    <p>Base del ingreso: 100%. Estas referencias ayudan a preparar el reporte; no modifican importes ni aplican un reparto.</p>
    {error && <p role="alert">{error}</p>}
    {!error && rows === null && <p>Cargando referencias…</p>}
    {rows?.length === 0 && <p>Sin porcentaje identificado para este ISRC.</p>}
    {rows?.map((r) => <article key={r.reference_id} className={styles.reference}>
      <strong>{r.participant}: {new Intl.NumberFormat('es-AR',{maximumFractionDigits:6}).format(r.percent)}% de la base al 100%</strong>
      <span className={styles[r.evidence_status]}>{statuses[r.evidence_status] || r.evidence_status}</span>
      <small>{r.reference_type === 'account_rate' ? 'Bolsa del contrato 91230 antes de participantes' : 'Participación de referencia'} · {r.product_type === 'group_of_versions' ? 'Referencia para el conjunto del tema; alcance por versión pendiente' : r.product_type}</small>
      <small>Statements observados: {r.statement_periods.join(', ')}. Vigencia contractual por confirmar.</small>
      <p>{r.notes}</p>
      <details><summary>Documentos de respaldo</summary>{r.source_files.map((f) => <div key={f}>{f}</div>)}</details>
    </article>)}
  </details>;
}
