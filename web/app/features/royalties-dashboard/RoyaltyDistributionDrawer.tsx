"use client";

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import styles from "./RoyaltyExplorer.module.css";

type Member = { name: string; amount_usd: number };
type Distribution = {
  presentation_only?: boolean;
  amount_usd: number;
  distributed_amount_usd: number;
  pending_amount_usd: number;
  groups: Array<Member & { percentage: number; members: Member[] }>;
  pending: Array<{ reason: string; amount_usd: number }>;
};
const money = (value: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);

export function RoyaltyDistributionDrawer({ open, params, onClose }: { open: boolean; params: string; onClose: () => void }) {
  const [data, setData] = useState<Distribution | null>(null);
  const [error, setError] = useState("");
  const panel = useRef<HTMLElement>(null);
  const close = useRef(onClose); close.current = onClose;

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setData(null); setError("");
    const query = new URLSearchParams(params); query.delete("measure");
    void fetch(`/api/royalties-dashboard/distribution?${query}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const body = await response.json();
        if (!response.ok) throw new Error(body.error || "No se pudo consultar la distribución.");
        return body as Distribution;
      }).then((body) => { if (!controller.signal.aborted) setData(body); })
      .catch((cause) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "No se pudo consultar la distribución."); });
    return () => controller.abort();
  }, [open, params]);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel.current?.querySelector("button")?.focus();
    const listener = (event: KeyboardEvent) => {
      if (event.key === "Escape") close.current();
      if (event.key === "Tab" && panel.current) {
        const elements = panel.current.querySelectorAll<HTMLElement>('button:not(:disabled),summary,a[href]');
        const first = elements[0], last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener("keydown", listener);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", listener);
      previous?.focus();
    };
  }, [open]);

  if (!open) return null;
  return <div className={styles.backdrop} onClick={onClose}>
    <aside ref={panel} className={`${styles.drawer} ${data?.presentation_only ? styles.presentation : ""}`} role="dialog" aria-modal="true" aria-label="Distribución del ingreso reportable" onClick={(event) => event.stopPropagation()}>
      <header><div><span>Ingreso reportable</span><h2>Distribución de ingresos</h2></div><button type="button" aria-label="Cerrar distribución" onClick={onClose}><X size={20} /></button></header>
      <p className={styles.distributionCaption}>{data?.presentation_only ? "Vista agrupada de socios y artistas, para el período y filtros que estás viendo." : "Reparto según los contratos guardados, para el catálogo, período y filtros que estás viendo."}</p>
      {!data && !error && <p role="status">Consultando la distribución…</p>}
      {error && <p className={styles.notice} role="alert">{error}</p>}
      {data && <>
        <div className={styles.base}><span>Ingreso reportable total</span><strong>{money(data.amount_usd)}</strong></div>
        <table><thead><tr><th>Participante</th><th>% del ingreso</th><th>Importe USD</th></tr></thead>
          <tbody>{data.groups.map((group) => <tr key={group.name}>
            <td>{group.name}{group.members.length > 0 && <details><summary>Ver artistas</summary>{group.members.map((member) => <small key={member.name}>{member.name}: {money(member.amount_usd)}</small>)}</details>}</td>
            <td>{group.percentage.toLocaleString("es-AR", { maximumFractionDigits: 2 })}%</td><td>{money(group.amount_usd)}</td>
          </tr>)}</tbody>
          <tfoot><tr><th colSpan={2}>Total distribuido</th><th>{money(data.distributed_amount_usd)}</th></tr></tfoot>
        </table>
        {data.pending.length > 0 && <section className={styles.notice}><h3>Pendiente de reparto: {money(data.pending_amount_usd)}</h3>
          {data.pending.map((item) => <p key={item.reason}>{item.reason}: {money(item.amount_usd)}</p>)}
        </section>}
      </>}
    </aside>
  </div>;
}
