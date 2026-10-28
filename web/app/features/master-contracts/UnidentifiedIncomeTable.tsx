"use client";

import styles from "./MasterContractsModule.module.css";
import { Link2 } from "lucide-react";

export type UnidentifiedIncome = {
  id: string; kind: string; code: string | null; title: string; artist: string;
  amount_usd: number; video_url: string | null; first_month: string | null; last_month: string | null;
  source_accounts: Array<{ source: string; account: string }>;
  candidates: Array<{ isrc: string; title: string; artists: string; statuses: string[]; reasons: string[] }>;
};
const money = (value: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);

export function UnidentifiedIncomeTable({ items, loading, onOpen, onAssociate }: {
  items: UnidentifiedIncome[]; loading: boolean; onOpen: (isrc: string) => void;
  onAssociate?: (item: UnidentifiedIncome) => void;
}) {
  return <div className={styles.tableWrap}><table className={`${styles.table} ${styles.unidentifiedTable}`}>
    <thead><tr><th>Tema / referencia</th><th>Artista informado</th><th>Código</th><th>Ingreso informado (USD)</th><th>Distribuidora / cuenta</th><th>Posibles destinos</th>{onAssociate && <th aria-label="Acciones" />}</tr></thead>
    <tbody>
      {!loading && items.length === 0 && <tr><td colSpan={onAssociate ? 7 : 6} className={styles.empty}>No hay ingresos sin identificar para este filtro.</td></tr>}
      {items.map((item) => <tr key={item.id}>
        <td>{item.title}<small>{item.first_month || ""}{item.last_month && item.last_month !== item.first_month ? ` a ${item.last_month}` : ""}</small></td>
        <td>{item.artist}</td>
        <td><small>{item.kind === "VIDEO" ? "Video" : item.kind === "TEXT" ? "Referencia sin código" : item.kind === "PRODUCT" ? "Producto" : item.kind === "TRACK" ? "ID de plataforma" : item.kind}</small>
          {item.video_url ? <a href={item.video_url} target="_blank" rel="noopener noreferrer">{item.code || "Ver video"}</a> : item.code || "—"}</td>
        <td className={styles.amountCell}>{money(item.amount_usd)}</td>
        <td>{item.source_accounts.map(({ source, account }) => <div key={`${source}/${account}`}>{source.toUpperCase()}<small>{account.replace(/_/g, " ")}</small></div>)}</td>
        <td>{item.candidates.length ? item.candidates.map((candidate) => <div className={styles.unidentifiedCandidate} key={candidate.isrc}>
          <button type="button" className={styles.titleButton} title="Revisar en el contrato" onClick={() => onOpen(candidate.isrc)}>{candidate.title}</button>
          <small>{candidate.isrc}</small>
          <small className={styles.associationPending}>{candidate.statuses.includes("excluded") ? "No incluido en este tema" : candidate.statuses.every((status) => status === "blocked") ? "Revisar destino" : "Por validar"}</small>
        </div>) : <span className={styles.associationsCount}>Sin coincidencia encontrada</span>}</td>
        {onAssociate && <td><button type="button" className={styles.secondaryButton} onClick={() => onAssociate(item)}><Link2 size={14} />Asociar</button></td>}
      </tr>)}
    </tbody>
  </table></div>;
}
