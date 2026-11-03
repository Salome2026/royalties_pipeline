"use client";

import { useMemo, useState } from "react";
import digitalStyles from "../digital-income/DigitalIncome.module.css";
import royaltyDashboardStyles from "./RoyaltyDashboard.module.css";

const WINDOW_SIZE = 12;
const currency = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const moneyCents = (value: number) => currency.format(value);
const units = new Intl.NumberFormat("es-AR");

type Month = { month: string; amount_usd: number };
type DashboardHistory = {
  period_months: string[];
  monthly: Month[];
  matrix: { source: string; account: string; months: Record<string, number>; amount_usd: number; titles: number }[];
};

export function RoyaltyDashboardHistory({ data, loading, semester, readOnly, onDrill }: {
  data: DashboardHistory | null;
  loading: boolean;
  semester: boolean;
  readOnly: boolean;
  onDrill: (filters: Record<string, string>) => void;
}) {
  const [page, setPage] = useState(0);
  const [expandedYear, setExpandedYear] = useState<string | null>(null);
  const allMonths = data?.period_months ?? [];
  const end = allMonths.length - page * WINDOW_SIZE;
  const start = Math.max(0, end - WINDOW_SIZE);
  const months = allMonths.slice(start, end);
  const monthLabel = (month: string) => semester
    ? `${month.slice(0, 4)} H${month.endsWith("06") ? "1" : "2"}`
    : month;
  const yearly = allMonths.length > WINDOW_SIZE;
  const years = useMemo(() => {
    const groups = new Map<string, { amount: number; months: Month[] }>();
    for (const month of data?.monthly ?? []) {
      const year = month.month.slice(0, 4);
      const group = groups.get(year) ?? { amount: 0, months: [] };
      group.amount += month.amount_usd;
      group.months.push(month);
      groups.set(year, group);
    }
    return [...groups];
  }, [data]);
  const monthMax = Math.max(1, ...(data?.monthly ?? []).map((month) => Math.abs(month.amount_usd)));
  const yearMax = Math.max(1, ...years.map(([, group]) => Math.abs(group.amount)));

  function trendBar(amount: number, max: number) {
    return (
      <div className={digitalStyles.trendTrack} aria-hidden="true">
        <div className={amount < 0 ? digitalStyles.negativeBar : digitalStyles.trendBar}
          style={{ width: `${Math.max(1, Math.abs(amount) / max * 100)}%` }} />
      </div>
    );
  }

  function monthRow(month: Month) {
    return (
      <button type="button" disabled={loading || readOnly} className={`${digitalStyles.trendRow} ${royaltyDashboardStyles.trendButton}`}
        key={month.month} onClick={() => onDrill({ month: month.month })} aria-label={`Explorar ${month.month}`}>
        <span>{monthLabel(month.month)}</span>
        {trendBar(month.amount_usd, monthMax)}
        <strong className={month.amount_usd < 0 ? digitalStyles.negativeAmount : undefined}>{moneyCents(month.amount_usd)}</strong>
      </button>
    );
  }

  return (
    <>
      <section className={digitalStyles.trendSection}>
        <div className={digitalStyles.sectionTitle}>
          <h2>{yearly ? "Evolución anual" : semester ? "Evolución semestral" : "Evolución mensual"}</h2>
          <span>USD reportable</span>
        </div>
        <div className={digitalStyles.trendRows}>
          {!loading && !data?.monthly.length && <div className={digitalStyles.emptyState}>Sin datos para este filtro.</div>}
          {yearly ? years.map(([year, group]) => (
            <div key={year}>
              <button type="button" className={`${digitalStyles.trendRow} ${royaltyDashboardStyles.trendButton}`}
                aria-expanded={expandedYear === year} aria-label={`Ver meses de ${year}`}
                onClick={() => setExpandedYear(expandedYear === year ? null : year)}>
                <span>{year} {expandedYear === year ? "−" : "+"}</span>
                {trendBar(group.amount, yearMax)}
                <strong className={group.amount < 0 ? digitalStyles.negativeAmount : undefined}>{moneyCents(group.amount)}</strong>
              </button>
              {expandedYear === year && <div className={royaltyDashboardStyles.yearMonths}>{group.months.map(monthRow)}</div>}
            </div>
          )) : data?.monthly.map(monthRow)}
        </div>
      </section>
      <section className={digitalStyles.tableSection}>
        <div className={digitalStyles.sectionTitle}>
          <h2>{semester ? 'Semestres por distribuidora' : 'Meses por distribuidora'}</h2>
          <span>{data?.matrix.length || 0} cuentas</span>
        </div>
        {allMonths.length > WINDOW_SIZE && (
          <div className={royaltyDashboardStyles.detailNavigation}>
            <span aria-live="polite">Mostrando {months.length} de {allMonths.length} meses · {months[0]} a {months.at(-1)}</span>
            <button type="button" disabled={start === 0 || loading} onClick={() => setPage(page + 1)}>Ver meses anteriores</button>
            <button type="button" disabled={page === 0 || loading} onClick={() => setPage(page - 1)}>Ver meses recientes</button>
          </div>
        )}
        <div className={digitalStyles.tableScroll}>
          <table className={`${digitalStyles.table} ${digitalStyles.matrixTable} ${royaltyDashboardStyles.matrixTable}`}>
            <thead>
              <tr>
                <th>Distribuidora / cuenta</th>
                {months.map((month) => <th key={month}><button type="button" className={royaltyDashboardStyles.cellButton} disabled={loading || readOnly} onClick={() => onDrill({ month })}>{monthLabel(month)}</button></th>)}
                <th>Total del período</th>
                <th>Temas</th>
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td className={digitalStyles.emptyCell} colSpan={months.length + 3}>Cargando dashboard...</td></tr>}
              {!loading && data?.matrix.length === 0 && <tr><td className={digitalStyles.emptyCell} colSpan={months.length + 3}>Sin datos para este filtro.</td></tr>}
              {data?.matrix.map((item) => (
                <tr key={`${item.source}-${item.account}`}>
                  <td className={digitalStyles.accountCell}><button type="button" className={royaltyDashboardStyles.cellButton} disabled={loading || readOnly} onClick={() => onDrill({ source: item.source, account: item.account })}><strong>{item.source}</strong><span>{item.account}</span></button></td>
                  {months.map((month) => <td key={month}><button type="button" className={royaltyDashboardStyles.cellButton} disabled={loading || readOnly} onClick={() => onDrill({ source: item.source, account: item.account, month })}>{moneyCents(item.months[month] || 0)}</button></td>)}
                  <td className={digitalStyles.totalCell}><button type="button" className={royaltyDashboardStyles.cellButton} disabled={loading || readOnly} onClick={() => onDrill({ source: item.source, account: item.account })}>{moneyCents(item.amount_usd || 0)}</button></td>
                  <td>{units.format(item.titles)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
