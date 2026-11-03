"use client";

import { useLayoutEffect, useState } from "react";
import { RotateCcw, Search } from "lucide-react";
import { PeriodControl } from "../../components/PeriodControl";
import type { PeriodSelection } from "../../lib/period";
import digitalStyles from "../digital-income/DigitalIncome.module.css";
import royaltyDashboardStyles from "./RoyaltyDashboard.module.css";

export type DashboardFilters = {
  keyword: string;
  source: string;
  account: string;
  period: PeriodSelection;
  periodBasis: "statement_period" | "transaction_month";
};

type DashboardOptions = {
  sources: string[];
  accounts: string[];
  source_accounts: { source: string; account: string }[];
  first_month?: string | null;
  last_month?: string | null;
};

export function RoyaltyDashboardFilters({ initial, options, loading, wmlScope, onApply, onReset }: {
  initial: DashboardFilters;
  options?: DashboardOptions;
  loading: boolean;
  wmlScope: boolean;
  onApply: (filters: DashboardFilters) => void;
  onReset: () => void;
}) {
  const [keyword, setKeyword] = useState(initial.keyword);
  const [source, setSource] = useState(initial.source);
  const [account, setAccount] = useState(initial.account);
  const [period, setPeriod] = useState(initial.period);
  const [periodBasis, setPeriodBasis] = useState(initial.periodBasis);

  useLayoutEffect(() => {
    setKeyword(initial.keyword);
    setSource(initial.source);
    setAccount(initial.account);
    setPeriod(initial.period);
    setPeriodBasis(initial.periodBasis);
  }, [initial]);

  const accountOptions = source
    ? options?.source_accounts.filter((item) => item.source === source).map((item) => item.account) ?? []
    : options?.accounts ?? [];

  const pending = loading && keyword === initial.keyword && source === initial.source
    && account === initial.account && periodBasis === initial.periodBasis
    && JSON.stringify(period) === JSON.stringify(initial.period);

  function reset() {
    setKeyword("");
    setSource("");
    setAccount("");
    setPeriod({ mode: wmlScope ? "all" : "last_6_months" });
    setPeriodBasis("statement_period");
    onReset();
  }

  return (
    <form className={`${digitalStyles.filters} ${royaltyDashboardStyles.filters}`} onSubmit={(event) => { event.preventDefault(); onApply({ keyword, source, account, period, periodBasis }); }}>
      <div className={`${digitalStyles.field} ${royaltyDashboardStyles.searchField}`}>
        <label htmlFor="royalties_dashboard_keyword">Artista / tema / ISRC</label>
        <div className={digitalStyles.inputShell}>
          <Search size={16} aria-hidden="true" />
          <input id="royalties_dashboard_keyword" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="Buscar en el catálogo" />
        </div>
      </div>
      <div className={digitalStyles.field}>
        <label htmlFor="royalties_dashboard_source">Distribuidora</label>
        <select
          id="royalties_dashboard_source"
          value={source}
          onChange={(event) => {
            setSource(event.target.value);
            setAccount("");
          }}
        >
          <option value="">Todas</option>
          {options?.sources.map((item) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
      </div>
      <div className={digitalStyles.field}>
        <label htmlFor="royalties_dashboard_account">Cuenta</label>
        <select
          id="royalties_dashboard_account"
          value={account}
          onChange={(event) => setAccount(event.target.value)}
        >
          <option value="">Todas</option>
          {accountOptions.map((item) => (
            <option key={item} value={item}>{item}</option>
          ))}
        </select>
      </div>
      <div className={digitalStyles.field}>
        <label htmlFor="royalties_dashboard_basis">Base temporal</label>
        <select
          id="royalties_dashboard_basis"
          value={periodBasis}
          onChange={(event) => {setPeriodBasis(event.target.value as "statement_period" | "transaction_month"); if (wmlScope) setPeriod({mode:'all'});}}
        >
          <option value="statement_period">Statement</option>
          <option value="transaction_month">Consumo</option>
        </select>
      </div>
      <div className={digitalStyles.periodField}>
        <PeriodControl id="royalties_dashboard_period" label="Período" profile="dashboard_period" selection={period} frequency={wmlScope && periodBasis === 'statement_period' ? 'semiannual' : 'monthly'} presets={wmlScope ? ['all'] : ["last_6_months", "last_12_months", "all"]} minMonth={options?.first_month} maxMonth={options?.last_month} onChange={setPeriod} />
      </div>
      <div className={digitalStyles.filterActions}>
        <button type="button" className={digitalStyles.iconButton} onClick={reset} disabled={loading} aria-label="Limpiar filtros" title="Limpiar filtros">
          <RotateCcw size={17} aria-hidden="true" />
        </button>
        <button type="submit" className={digitalStyles.applyButton} disabled={pending}>
          <Search size={16} aria-hidden="true" />
          {pending ? "Cargando" : "Aplicar"}
        </button>
      </div>
    </form>
  );
}
