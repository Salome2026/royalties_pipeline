"use client";

import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import type { ExplorerRank } from "./RoyaltyExplorer";
import styles from "./RoyaltyDashboard.module.css";

export type RoyaltyRank = ExplorerRank & { units: number; rows: number; percentage: number };

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const units = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });
const percentage = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 2 });
const VIEWPORT_HEIGHT = 360;
const OVERSCAN = 4;

export function RoyaltyRankList({ title, rows: initialRows, loading, scrollable, contractual, onSelect, nextOffset, onLoadMore, emptyText = "Sin datos para este filtro." }: {
  title: string;
  rows: RoyaltyRank[];
  loading: boolean;
  scrollable: boolean;
  contractual: boolean;
  onSelect?: (row: RoyaltyRank) => void;
  nextOffset?: number | null;
  onLoadMore?: (offset: number, signal: AbortSignal) => Promise<{ rows: RoyaltyRank[]; next_offset: number | null }>;
  emptyText?: string;
}) {
  const [additional, setAdditional] = useState<RoyaltyRank[]>([]);
  const [pageOffset, setPageOffset] = useState(nextOffset);
  const [pageError, setPageError] = useState("");
  const [pageLoading, setPageLoading] = useState(false);
  const request = useRef<AbortController | null>(null);
  const rows = additional.length ? [...initialRows, ...additional] : initialRows;

  useEffect(() => () => request.current?.abort(), []);
  useLayoutEffect(() => {
    request.current?.abort();
    request.current = null;
    setAdditional([]);
    setPageOffset(nextOffset);
    setPageError("");
    setPageLoading(false);
  }, [initialRows, nextOffset]);

  async function loadMore() {
    if (!onLoadMore || pageOffset == null || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setPageLoading(true);
    setPageError("");
    try {
      const page = await onLoadMore(pageOffset, controller.signal);
      if (controller.signal.aborted) return;
      setAdditional((previous) => [...previous, ...page.rows]);
      setPageOffset(page.next_offset);
    } catch (error) {
      if (!controller.signal.aborted) {
        setPageError(error instanceof Error ? error.message : "No se pudieron cargar más resultados.");
      }
    } finally {
      if (!controller.signal.aborted) {
        request.current = null;
        setPageLoading(false);
      }
    }
  }

  const viewport = useRef<HTMLDivElement>(null);
  const [firstVisible, setFirstVisible] = useState(0);
  // Match the existing one-line row spacing, including its separator and bar.
  const rowHeight = onSelect ? 62 : 55;
  const first = scrollable ? Math.max(0, Math.min(firstVisible, Math.max(0, rows.length - 1)) - OVERSCAN) : 0;
  const end = scrollable ? Math.min(rows.length, firstVisible + Math.ceil(VIEWPORT_HEIGHT / rowHeight) + OVERSCAN) : rows.length;

  useLayoutEffect(() => {
    if (viewport.current) viewport.current.scrollTop = 0;
    setFirstVisible(0);
  }, [initialRows, scrollable, rowHeight]);

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
        <span>{rows.length ? `${rows.length}${pageOffset != null ? "+" : ""} resultados` : "Sin datos"}</span>
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
      {pageOffset != null && onLoadMore && (
        <div className={styles.detailNavigation}>
          <button type="button" disabled={loading || pageLoading} onClick={() => void loadMore()}>
            {pageLoading ? "Cargando…" : "Mostrar 50 más"}
          </button>
          {pageError && <span role="alert">{pageError}</span>}
        </div>
      )}
    </section>
  );
}
