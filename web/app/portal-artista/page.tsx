"use client";

import Image from "next/image";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  LayoutDashboard,
  LogOut,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldCheck,
  Youtube,
} from "lucide-react";
import { PeriodControl } from "../components/PeriodControl";
import { PeriodSelection, resolvePeriod } from "../lib/period";
import { useSession } from "../shared/auth/useSession";
import styles from "./portal-artista.module.css";

type Rank = {
  name: string;
  amount_usd: number;
  units: number;
  rows: number;
  percentage: number;
};

type DashboardData = {
  period_months: string[];
  totals: {
    amount_usd: number;
    units: number;
    rows: number;
    months: number;
    sources: number;
    accounts: number;
    titles: number;
    artists: number;
    first_month: string | null;
    last_month: string | null;
  };
  monthly: { month: string; amount_usd: number; units: number; rows: number }[];
  matrix: {
    source: string;
    account: string;
    months: Record<string, number>;
    amount_usd: number;
    titles: number;
  }[];
  rankings: {
    dsp: Rank[];
    monetization: Rank[];
    content_origin: Rank[];
    territory: Rank[];
    artist: Rank[];
    title: Rank[];
    label: Rank[];
  };
  youtube: {
    totals: { amount_usd: number; units: number; rows: number; titles: number; artists: number };
    monetization: Rank[];
    content_origin: Rank[];
    title: Rank[];
    territory: Rank[];
  };
  options: {
    sources: string[];
    accounts: string[];
    source_accounts: { source: string; account: string }[];
    first_month: string | null;
    last_month: string | null;
  };
};

type ProfileData = {
  employee?: { display_name?: string | null };
};

function money(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value || 0);
}

function RankList({ title, rows, loading }: { title: string; rows: Rank[]; loading: boolean }) {
  return (
    <section className={styles.rankSection}>
      <div className={styles.rankHeader}>
        <h2>{title}</h2>
        <span>{rows.length ? `${rows.length} resultados` : "Sin datos"}</span>
      </div>
      {loading && <div className={styles.empty}>Cargando...</div>}
      {!loading && rows.length === 0 && <div className={styles.empty}>Sin datos para este filtro.</div>}
      <div className={styles.rankList}>
        {rows.map((row, index) => (
          <div className={styles.rankRow} key={`${title}-${row.name}-${index}`}>
            <span className={styles.rankIndex}>{index + 1}</span>
            <div className={styles.rankMain}>
              <strong>{row.name || "-"}</strong>
              <small>{Math.round(row.units || 0).toLocaleString("es-AR")} unidades</small>
            </div>
            <div className={styles.rankValue}>
              <strong>{money(row.amount_usd)}</strong>
              <span>{(row.percentage || 0).toLocaleString("es-AR", { maximumFractionDigits: 2 })}%</span>
            </div>
            <div className={styles.rankBar} aria-hidden="true">
              <span style={{ width: `${Math.max(2, Math.min(100, row.percentage || 0))}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function ArtistPortal() {
  const {
    authenticated,
    checkingSession,
    currentUser,
    moduleAccess,
    permissions,
    login,
    logout,
  } = useSession();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [keyword, setKeyword] = useState("");
  const [source, setSource] = useState("");
  const [account, setAccount] = useState("");
  const [periodBasis, setPeriodBasis] = useState<"statement_period" | "transaction_month">("statement_period");
  const [period, setPeriod] = useState<PeriodSelection>({ mode: "last_6_months" });
  const [tab, setTab] = useState<"overview" | "youtube">("overview");

  const permission = permissions?.find((item) => item.module_key === "royalties_dashboard");
  const artistScope = permission?.scope?.filter((item) => item.scope_type === "artist" && item.scope_ref) || [];
  const hasPortalAccess = Boolean(
    permission?.can_access
      && artistScope.length
      && !permission.scope.some((item) => item.scope_type === "all" && item.scope_ref === "*"),
  );
  const permissionsReady = currentUser?.role === "admin" || moduleAccess !== null;

  const accountOptions = useMemo(() => {
    if (!dashboard) return [];
    if (!source) return dashboard.options.accounts;
    return dashboard.options.source_accounts
      .filter((item) => item.source === source)
      .map((item) => item.account);
  }, [dashboard, source]);

  const monthlyMax = useMemo(
    () => Math.max(1, ...(dashboard?.monthly || []).map((item) => Math.abs(item.amount_usd || 0))),
    [dashboard],
  );

  const loadDashboard = useCallback(async (overrides?: {
    keyword?: string;
    source?: string;
    account?: string;
    period?: PeriodSelection;
    periodBasis?: "statement_period" | "transaction_month";
  }) => {
    setLoading(true);
    setError("");
    try {
      const nextKeyword = overrides?.keyword ?? keyword;
      const nextSource = overrides?.source ?? source;
      const nextAccount = overrides?.account ?? account;
      const nextPeriod = overrides?.period ?? period;
      const nextBasis = overrides?.periodBasis ?? periodBasis;
      const resolved = resolvePeriod(nextPeriod, "dashboard_period");
      const params = new URLSearchParams({
        period_mode: resolved.mode,
        period_basis: nextBasis,
        limit: "10",
      });
      if (nextKeyword.trim()) params.set("keyword", nextKeyword.trim());
      if (nextSource) params.set("source", nextSource);
      if (nextAccount) params.set("account", nextAccount);
      if (resolved.startMonth) params.set("start_month", resolved.startMonth);
      if (resolved.endMonth) params.set("end_month", resolved.endMonth);

      const response = await fetch(`/api/royalties-dashboard?${params.toString()}`, { cache: "no-store" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || "No se pudo cargar el dashboard.");
      setDashboard(payload);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "No se pudo cargar el dashboard.");
    } finally {
      setLoading(false);
    }
  }, [account, keyword, period, periodBasis, source]);

  useEffect(() => {
    if (!authenticated || !hasPortalAccess) return;
    let active = true;
    fetch("/api/me/permissions", { cache: "no-store" })
      .then((response) => response.json())
      .then((profile: ProfileData) => {
        if (active) setDisplayName(profile.employee?.display_name || currentUser?.username || "Artista");
      })
      .catch(() => {
        if (active) setDisplayName(currentUser?.username || "Artista");
      });
    return () => { active = false; };
  }, [authenticated, currentUser?.username, hasPortalAccess]);

  useEffect(() => {
    if (authenticated && hasPortalAccess && !dashboard && !loading) void loadDashboard();
  }, [authenticated, dashboard, hasPortalAccess, loadDashboard, loading]);

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoggingIn(true);
    setLoginError("");
    const result = await login(username, password);
    if (!result.ok) setLoginError(result.error);
    setLoggingIn(false);
  }

  function resetFilters() {
    const nextPeriod: PeriodSelection = { mode: "last_6_months" };
    setKeyword("");
    setSource("");
    setAccount("");
    setPeriodBasis("statement_period");
    setPeriod(nextPeriod);
    void loadDashboard({ keyword: "", source: "", account: "", period: nextPeriod, periodBasis: "statement_period" });
  }

  if (checkingSession) {
    return <div className={styles.centerState}><RefreshCw className={styles.spin} size={24} /><span>Validando sesión...</span></div>;
  }

  if (!authenticated) {
    return (
      <main className={styles.loginPage}>
        <form className={styles.loginPanel} onSubmit={submitLogin}>
          <Image className={styles.logo} src="/vpo-logo.png" alt="VPO Corp" width={2539} height={1298} priority />
          <div className={styles.loginHeading}>
            <span>Portal de artista</span>
            <h1>Tu catálogo, en un solo lugar</h1>
            <p>Consultá los ingresos vinculados a tu música.</p>
          </div>
          {loginError && <div className={styles.alert}>{loginError}</div>}
          <label htmlFor="artist_portal_username">Usuario</label>
          <input id="artist_portal_username" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required />
          <label htmlFor="artist_portal_password">Contraseña</label>
          <input id="artist_portal_password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
          <button type="submit" disabled={loggingIn}>{loggingIn ? "Ingresando..." : "Ingresar"}</button>
        </form>
      </main>
    );
  }

  if (!permissionsReady) {
    return <div className={styles.centerState}><RefreshCw className={styles.spin} size={24} /><span>Preparando tu portal...</span></div>;
  }

  if (!hasPortalAccess) {
    return (
      <main className={styles.accessPage}>
        <Image className={styles.logo} src="/vpo-logo.png" alt="VPO Corp" width={2539} height={1298} priority />
        <ShieldCheck size={28} />
        <h1>Este acceso no tiene un catálogo asignado</h1>
        <p>Contactá a VPO Corp para revisar tus permisos.</p>
        <button type="button" onClick={() => void logout()}>Cerrar sesión</button>
      </main>
    );
  }

  return (
    <main className={styles.portal}>
      <header className={styles.topbar}>
        <div className={styles.brandBlock}>
          <Image className={styles.headerLogo} src="/vpo-logo.png" alt="VPO Corp" width={2539} height={1298} priority />
          <span>Portal de artista</span>
        </div>
        <div className={styles.userBlock}>
          <div><strong>{displayName || currentUser?.username}</strong><span>Solo lectura</span></div>
          <button type="button" onClick={() => void logout()} aria-label="Cerrar sesión" title="Cerrar sesión"><LogOut size={17} /></button>
        </div>
      </header>

      <section className={styles.workspace}>
        <header className={styles.pageHeader}>
          <div>
            <span className={styles.eyebrow}>Royalty intelligence</span>
            <h1>Ingresos vinculados a tu catálogo</h1>
            <p>Vista informativa de ingresos reportables. No representa un saldo a cobrar.</p>
          </div>
          <button className={styles.iconButton} type="button" onClick={() => void loadDashboard()} disabled={loading} aria-label="Actualizar dashboard" title="Actualizar dashboard">
            <RefreshCw size={17} className={loading ? styles.spin : undefined} />
          </button>
        </header>

        <form className={styles.filters} onSubmit={(event) => { event.preventDefault(); void loadDashboard(); }}>
          <div className={`${styles.field} ${styles.searchField}`}>
            <label htmlFor="artist_portal_keyword">Artista / tema / ISRC</label>
            <div className={styles.inputShell}><Search size={16} /><input id="artist_portal_keyword" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="Buscar en tu catálogo" /></div>
          </div>
          <div className={styles.field}>
            <label htmlFor="artist_portal_source">Distribuidora</label>
            <select id="artist_portal_source" value={source} onChange={(event) => { setSource(event.target.value); setAccount(""); }}>
              <option value="">Todas</option>
              {(dashboard?.options.sources || []).map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </div>
          <div className={styles.field}>
            <label htmlFor="artist_portal_account">Cuenta</label>
            <select id="artist_portal_account" value={account} onChange={(event) => setAccount(event.target.value)}>
              <option value="">Todas</option>
              {accountOptions.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </div>
          <div className={styles.field}>
            <label htmlFor="artist_portal_basis">Base temporal</label>
            <select id="artist_portal_basis" value={periodBasis} onChange={(event) => setPeriodBasis(event.target.value as "statement_period" | "transaction_month")}>
              <option value="statement_period">Statement</option>
              <option value="transaction_month">Consumo</option>
            </select>
          </div>
          <div className={styles.periodField}>
            <PeriodControl id="artist_portal_period" label="Período" profile="dashboard_period" selection={period} presets={["last_6_months", "last_12_months", "all"]} minMonth={dashboard?.options.first_month} maxMonth={dashboard?.options.last_month} onChange={setPeriod} />
          </div>
          <div className={styles.filterActions}>
            <button type="button" className={styles.iconButton} onClick={resetFilters} disabled={loading} aria-label="Limpiar filtros" title="Limpiar filtros"><RotateCcw size={17} /></button>
            <button type="submit" className={styles.applyButton} disabled={loading}><Search size={16} />{loading ? "Cargando" : "Aplicar"}</button>
          </div>
        </form>

        {error && <div className={styles.alert}>{error}</div>}

        <div className={styles.metricBand} aria-live="polite">
          <div className={styles.primaryMetric}><span>Ingreso reportable</span><strong>{money(dashboard?.totals.amount_usd || 0)}</strong></div>
          <div><span>Unidades</span><strong>{Math.round(dashboard?.totals.units || 0).toLocaleString("es-AR")}</strong></div>
          <div><span>Temas</span><strong>{(dashboard?.totals.titles || 0).toLocaleString("es-AR")}</strong></div>
          <div><span>Distribuidoras</span><strong>{dashboard?.totals.sources || 0}</strong></div>
          <div><span>Rango</span><strong>{dashboard?.totals.first_month || "-"} a {dashboard?.totals.last_month || "-"}</strong></div>
        </div>

        <div className={styles.scopeLine}>
          <span>Catálogo: <strong>{artistScope.map((item) => item.scope_ref).join(", ")}</strong></span>
          <span>Fuente disponible: <strong>{dashboard?.options.first_month || "-"} a {dashboard?.options.last_month || "-"}</strong></span>
          <span>Base: <strong>{periodBasis === "statement_period" ? "statement" : "consumo"}</strong></span>
        </div>

        <div className={styles.tabs} role="tablist" aria-label="Vista del dashboard">
          <button type="button" role="tab" aria-selected={tab === "overview"} className={tab === "overview" ? styles.activeTab : undefined} onClick={() => setTab("overview")}><LayoutDashboard size={15} />General</button>
          <button type="button" role="tab" aria-selected={tab === "youtube"} className={tab === "youtube" ? styles.activeTab : undefined} onClick={() => setTab("youtube")}><Youtube size={15} />YouTube</button>
        </div>

        {tab === "overview" && (
          <>
            <section className={styles.section}>
              <div className={styles.sectionTitle}><h2>Evolución mensual</h2><span>USD reportable por {periodBasis === "statement_period" ? "mes de statement" : "mes de consumo"}</span></div>
              <div className={styles.trendRows}>
                {!loading && !dashboard?.monthly.length && <div className={styles.empty}>Sin datos para este filtro.</div>}
                {(dashboard?.monthly || []).map((month) => (
                  <div className={styles.trendRow} key={month.month}>
                    <span>{month.month}</span>
                    <div className={styles.trendTrack}><div className={month.amount_usd < 0 ? styles.negativeBar : styles.trendBar} style={{ width: `${Math.max(1, Math.abs(month.amount_usd) / monthlyMax * 100)}%` }} /></div>
                    <strong className={month.amount_usd < 0 ? styles.negativeAmount : undefined}>{money(month.amount_usd)}</strong>
                  </div>
                ))}
              </div>
            </section>

            <section className={styles.section}>
              <div className={styles.sectionTitle}><h2>Meses por distribuidora</h2><span>{dashboard?.matrix.length || 0} cuentas</span></div>
              <div className={styles.tableScroll}>
                <table className={styles.table}>
                  <thead><tr><th>Distribuidora / cuenta</th>{(dashboard?.period_months || []).map((month) => <th key={month}>{month}</th>)}<th>Total</th><th>Temas</th></tr></thead>
                  <tbody>
                    {loading && <tr><td className={styles.emptyCell} colSpan={(dashboard?.period_months.length || 0) + 3}>Cargando dashboard...</td></tr>}
                    {!loading && dashboard?.matrix.length === 0 && <tr><td className={styles.emptyCell} colSpan={(dashboard?.period_months.length || 0) + 3}>Sin datos para este filtro.</td></tr>}
                    {(dashboard?.matrix || []).map((item) => (
                      <tr key={`${item.source}-${item.account}`}><td><strong>{item.source}</strong><span>{item.account}</span></td>{dashboard?.period_months.map((month) => <td key={month}>{money(item.months[month] || 0)}</td>)}<td className={styles.totalCell}>{money(item.amount_usd)}</td><td>{item.titles.toLocaleString("es-AR")}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <div className={styles.rankGrid}>
              <RankList title="Ingresos por tema" rows={dashboard?.rankings.title || []} loading={loading} />
              <RankList title="Ingresos por artista" rows={dashboard?.rankings.artist || []} loading={loading} />
              <RankList title="Ingresos por plataforma" rows={dashboard?.rankings.dsp || []} loading={loading} />
              <RankList title="Territorios" rows={dashboard?.rankings.territory || []} loading={loading} />
            </div>
          </>
        )}

        {tab === "youtube" && (
          <>
            <div className={`${styles.metricBand} ${styles.youtubeMetrics}`}>
              <div className={styles.primaryMetric}><span>Ingreso YouTube</span><strong>{money(dashboard?.youtube.totals.amount_usd || 0)}</strong></div>
              <div><span>Unidades monetizadas</span><strong>{Math.round(dashboard?.youtube.totals.units || 0).toLocaleString("es-AR")}</strong></div>
              <div><span>Videos / assets</span><strong>{(dashboard?.youtube.totals.titles || 0).toLocaleString("es-AR")}</strong></div>
            </div>
            <div className={styles.rankGrid}>
              <RankList title="Monetización" rows={dashboard?.youtube.monetization || []} loading={loading} />
              <RankList title="Origen del contenido" rows={dashboard?.youtube.content_origin || []} loading={loading} />
              <RankList title="Territorios" rows={dashboard?.youtube.territory || []} loading={loading} />
              <RankList title="Assets de YouTube" rows={dashboard?.youtube.title || []} loading={loading} />
            </div>
          </>
        )}
      </section>
    </main>
  );
}
