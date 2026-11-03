"use client";

import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import type { ExplorerRank } from "./RoyaltyExplorer";
import styles from "./RoyaltyDashboard.module.css";

export type RoyaltyRank = ExplorerRank & { units: number; rows: number; percentage: number };

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const units = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });
const percentage = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 });
const VIEWPORT_HEIGHT = 360;
const OVERSCAN = 4;

export function RoyaltyRankList({ title, rows, loading, scrollable, contractual, onSelect, emptyText = "Sin datos para este filtro." }: {
  title: string;
  rows: RoyaltyRank[];
  loading: boolean;
  scrollable: boolean;
  contractual: boolean;
  onSelect?: (row: RoyaltyRank) => void;
  emptyText?: string;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const [firstVisible, setFirstVisible] = useState(0);
  // Match the existing one-line row spacing, including its separator and bar.
  const rowHeight = onSelect ? 62 : 55;
  const first = scrollable ? Math.max(0, Math.min(firstVisible, Math.max(0, rows.length - 1)) - OVERSCAN) : 0;
  const end = scrollable ? Math.min(rows.length, firstVisible + Math.ceil(VIEWPORT_HEIGHT / rowHeight) + OVERSCAN) : rows.length;

  useLayoutEffect(() => {
    if (viewport.current) viewport.current.scrollTop = 0;
    setFirstVisible(0);
  }, [rows, scrollable, rowHeight]);

  function revealFocusedRow(index: number) {
    const element = viewport.current;
    if (!scrollable || !element) return;
    const top = index * rowHeight;
    if (top < element.scrollTop) element.scrollTop = top;
    else if (top + rowHeight > element.scrollTop + element.clientHeight) {
      element.scrollTop = top + rowHeight - element.clientHeight;
    }
    // Focus can advance faster than the browser dispatches its scroll event.
    setFirstVisible(Math.floor(element.scrollTop / rowHeight));
  }

  return (
    <section className={styles.rankSection}>
      <div className={styles.rankHeader}>
        <h2>{title}</h2>
        <span>{rows.length ? `${rows.length} resultados` : "Sin datos"}</span>
      </div>
      {loading && <div className={styles.empty}>Cargando...</div>}
      {!loading && rows.length === 0 && <div className={styles.empty}>{emptyText}</div>}
      <div
        ref={viewport}
        className={scrollable ? styles.rankListScrollable : undefined}
        tabIndex={scrollable && rows.length > 0 ? 0 : undefined}
        role={scrollable ? "region" : undefined}
        aria-label={scrollable ? title : undefined}
        onScroll={scrollable ? (event) => setFirstVisible(Math.floor(event.currentTarget.scrollTop / rowHeight)) : undefined}
        style={scrollable ? { "--rank-row-height": `${rowHeight}px` } as CSSProperties : undefined}
      >
        <div className={styles.rankList} role="list" aria-label={title}>
          {scrollable && first > 0 && <div aria-hidden="true" style={{ height: first * rowHeight }} />}
          {rows.slice(first, end).map((row, offset) => {
            const index = first + offset;
            return (
              <div className={`${styles.rankRow}${scrollable ? ` ${styles.rankVirtualRow}` : ""}`} key={`${row.identity_key || row.name}-${index}`}
                role="listitem" aria-posinset={index + 1} aria-setsize={rows.length}>
                <span className={styles.rankIndex}>{index + 1}</span>
                <div className={styles.rankMain}>
                  {onSelect ? <button type="button" className={styles.rankName} title={row.name || "-"} disabled={loading} onFocus={() => revealFocusedRow(index)} onClick={() => onSelect(row)}>{row.name || "-"}</button> : <strong title={row.name || "-"}>{row.name || "-"}</strong>}
                  <small>{units.format(Math.round(row.units || 0))} unidades</small>
                </div>
                <div className={styles.rankValue}>
                  <strong>{contractual && row.pending_amount_usd && !row.amount_usd ? "Por validar" : money.format(row.amount_usd || 0)}</strong>
                  <span>{percentage.format(row.percentage || 0)}%</span>
                </div>
                <div className={styles.rankBar} aria-hidden="true">
                  <span style={{ width: `${Math.max(2, Math.min(100, row.percentage || 0))}%` }} />
                </div>
              </div>
            );
          })}
          {scrollable && end < rows.length && <div aria-hidden="true" style={{ height: (rows.length - end) * rowHeight }} />}
        </div>
      </div>
    </section>
  );
}
