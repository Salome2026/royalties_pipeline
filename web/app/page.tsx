"use client";

import { FormEvent, MouseEvent, useEffect, useMemo, useState } from "react";

type Message = {
  type: "ok" | "error";
  text: string;
};

type View = "menu" | "statement" | "royalties" | "participation" | "booking";

type ParticipationItem = {
  source: string;
  amount_usd: number;
  percentage: number;
};

type ParticipationData = {
  updated_at: string;
  preset: string;
  start_month: string | null;
  end_month: string | null;
  start_date: string | null;
  end_date: string | null;
  available_start_month: string | null;
  available_end_month: string | null;
  total_amount_usd: number;
  items: ParticipationItem[];
};

type ParticipationCache = {
  data: ParticipationData;
  preset: string;
  startMonth: string;
  endMonth: string;
};

type BookingShow = {
  id: number;
  artist: string;
  show_date: string;
  venue: string;
  city: string | null;
  tour_manager: string | null;
  status: string;
  currency: "ARS" | "USD";
  cachet_amount: number;
  expenses_amount: number;
  net_amount: number;
  artist_percent: number;
  producer_percent: number;
  artist_share_amount: number;
  producer_share_amount: number;
  artist_paid_amount: number;
  producer_received_amount: number;
  balance_artist_amount: number;
  balance_producer_amount: number;
  receipt_refs: string[];
  notes: string | null;
};

type BookingForm = {
  artist: string;
  showDate: string;
  venue: string;
  city: string;
  tourManager: string;
  seller: string;
  status: string;
  currency: "ARS" | "USD";
  fxRate: string;
  cachetAmount: string;
  expensesAmount: string;
  artistPaidAmount: string;
  producerReceivedAmount: string;
  artistPercent: string;
  producerPercent: string;
  receiptRefs: string;
  notes: string;
};

const PIE_COLORS = ["#17324d", "#0f766e", "#b54708", "#6941c6", "#b42318", "#475467", "#2e90fa"];
const PARTICIPATION_CACHE_KEY = "vpo_participation_last_result";
const MONTH_NAMES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
const MONTH_OPTIONS = Array.from({ length: 11 }, (_, yearIndex) => 2020 + yearIndex)
  .flatMap((year) => MONTH_NAMES.map((month, monthIndex) => {
    const value = `${year}-${String(monthIndex + 1).padStart(2, "0")}`;
    return { value, label: `${month} ${year}` };
  }));

type MonthSelectProps = {
  id: string;
  value: string;
  min?: string | null;
  onChange: (value: string) => void;
};

function filenameFromDisposition(disposition: string | null, fallback: string) {
  if (!disposition) return fallback;
  const match = disposition.match(/filename="?([^"]+)"?/i);
  return match?.[1] || fallback;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function money(value: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

function pct(value: number) {
  return `${value.toFixed(1)}%`;
}

function ars(value: number) {
  return new Intl.NumberFormat("es-AR", { style: "currency", currency: "ARS", maximumFractionDigits: 0 }).format(value);
}

function localAmount(value: number, currency: string) {
  if (currency === "USD") {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
  }
  return ars(value);
}

function MonthSelect({ id, value, min, onChange }: MonthSelectProps) {
  const options = MONTH_OPTIONS.filter((option) => !min || option.value >= min);

  return (
    <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">Sin limite</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>{option.label}</option>
      ))}
    </select>
  );
}

export default function Home() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [view, setView] = useState<View>("menu");
  const [password, setPassword] = useState("");
  const [keywords, setKeywords] = useState("");
  const [startMonth, setStartMonth] = useState("");
  const [endMonth, setEndMonth] = useState("");
  const [periodBasis, setPeriodBasis] = useState("transaction_month");
  const [mode, setMode] = useState("any");
  const [rawLimit, setRawLimit] = useState("5000");
  const [statementMinTotal, setStatementMinTotal] = useState("0");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [statementLoading, setStatementLoading] = useState(false);
  const [participationLoading, setParticipationLoading] = useState(false);
  const [message, setMessage] = useState<Message | null>(null);
  const [lastFile, setLastFile] = useState("");
  const [lastSheetUrl, setLastSheetUrl] = useState("");
  const [participation, setParticipation] = useState<ParticipationData | null>(null);
  const [participationPreset, setParticipationPreset] = useState("last_year");
  const [participationStartMonth, setParticipationStartMonth] = useState("");
  const [participationEndMonth, setParticipationEndMonth] = useState("");
  const [bookingLoading, setBookingLoading] = useState(false);
  const [bookingItems, setBookingItems] = useState<BookingShow[]>([]);
  const [bookingArtists, setBookingArtists] = useState<string[]>([]);
  const [bookingForm, setBookingForm] = useState<BookingForm>({
    artist: "",
    showDate: new Date().toISOString().slice(0, 10),
    venue: "",
    city: "",
    tourManager: "",
    seller: "",
    status: "realizado",
    currency: "ARS",
    fxRate: "",
    cachetAmount: "",
    expensesAmount: "",
    artistPaidAmount: "",
    producerReceivedAmount: "",
    artistPercent: "70",
    producerPercent: "30",
    receiptRefs: "",
    notes: "",
  });

  useEffect(() => {
    fetch("/api/session")
      .then((response) => response.json())
      .then((data) => setAuthenticated(Boolean(data.authenticated)))
      .catch(() => setAuthenticated(false))
      .finally(() => setCheckingSession(false));
  }, []);

  useEffect(() => {
    if (authenticated && view === "participation" && !participation) {
      const cached = loadParticipationCache();
      if (cached) {
        setParticipation(cached.data);
        setParticipationPreset(cached.preset);
        setParticipationStartMonth(cached.startMonth);
        setParticipationEndMonth(cached.endMonth);
        return;
      }

      loadParticipation(false);
    }
  }, [authenticated, view, participation]);

  useEffect(() => {
    if (authenticated && view === "booking") {
      loadBookingArtists();
      loadBookingShows();
    }
  }, [authenticated, view]);

  const pieStyle = useMemo(() => {
    if (!participation?.items.length) return { background: "#e4e7ec" };

    let cursor = 0;
    const parts = participation.items.map((item, idx) => {
      const start = cursor;
      const end = cursor + item.percentage;
      cursor = end;
      return `${PIE_COLORS[idx % PIE_COLORS.length]} ${start}% ${end}%`;
    });

    return { background: `conic-gradient(${parts.join(", ")})` };
  }, [participation]);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setLoading(true);

    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo ingresar." }));
      setMessage({ type: "error", text: data.error || "No se pudo ingresar." });
      setLoading(false);
      return;
    }

    setAuthenticated(true);
    setPassword("");
    setLoading(false);
  }

  async function logout() {
    await fetch("/api/logout", { method: "POST" });
    setAuthenticated(false);
    setView("menu");
    setMessage(null);
    setLastFile("");
    setLastSheetUrl("");
  }

  function buildPayload(output: "excel" | "google_sheet") {
    return {
      keywords: keywords.split(/[;,]/).map((item) => item.trim()).filter(Boolean),
      start_month: startMonth || null,
      end_month: endMonth || null,
      period_basis: periodBasis,
      mode,
      raw_limit: Number(rawLimit) || 0,
      refresh_cache: false,
      output,
    };
  }

  function validatePeriod() {
    if (startMonth && endMonth && startMonth > endMonth) {
      setMessage({ type: "error", text: "El periodo desde no puede ser mayor que hasta." });
      return false;
    }
    return true;
  }

  async function generateExcel() {
    setMessage(null);
    setLastFile("");
    setLastSheetUrl("");

    if (!validatePeriod()) return;
    setLoading(true);

    const response = await fetch("/api/report-link", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload("excel")),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo generar el reporte." }));
      setMessage({ type: "error", text: data.error || "No se pudo generar el reporte." });
      setLoading(false);
      return;
    }

    const data = await response.json();
    if (data.url) {
      window.location.href = data.url;
    }
    setLastFile("Descarga directa iniciada");
    setMessage({ type: "ok", text: "Reporte solicitado. La descarga se abre directo desde Cloud Run." });
    setLoading(false);
  }

  async function createGoogleSheet(event?: MouseEvent<HTMLButtonElement>) {
    event?.preventDefault();
    event?.stopPropagation();
    setMessage(null);
    setLastFile("");
    setLastSheetUrl("");

    if (!validatePeriod()) return;
    setGoogleLoading(true);

    const response = await fetch("/api/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildPayload("google_sheet")),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo crear el Google Sheet." }));
      setMessage({ type: "error", text: data.error || "No se pudo crear el Google Sheet." });
      setGoogleLoading(false);
      return;
    }

    const data = await response.json();
    setLastSheetUrl(data.url);
    if (data.url) window.open(data.url, "_blank", "noopener,noreferrer");
    setMessage({ type: "ok", text: "Google Sheet creado correctamente." });
    setGoogleLoading(false);
  }

  async function generateStatementReport() {
    setMessage(null);
    setStatementLoading(true);

    const response = await fetch("/api/statement", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        refresh_cache: false,
        min_artist_total_usd: Number(statementMinTotal) || 0,
      }),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo generar el reporte por statement." }));
      setMessage({ type: "error", text: data.error || "No se pudo generar el reporte por statement." });
      setStatementLoading(false);
      return;
    }

    const blob = await response.blob();
    const filename = filenameFromDisposition(response.headers.get("content-disposition"), "vpo_statement_report.xlsx");
    downloadBlob(blob, filename);
    setLastFile(filename);
    setMessage({ type: "ok", text: "Reporte por statement generado correctamente." });
    setStatementLoading(false);
  }

  function loadParticipationCache(): ParticipationCache | null {
    try {
      const raw = window.localStorage.getItem(PARTICIPATION_CACHE_KEY);
      if (!raw) return null;

      const cached = JSON.parse(raw) as ParticipationCache;
      if (!cached?.data?.items) return null;

      return cached;
    } catch {
      return null;
    }
  }

  function saveParticipationCache(data: ParticipationData) {
    try {
      window.localStorage.setItem(
        PARTICIPATION_CACHE_KEY,
        JSON.stringify({
          data,
          preset: participationPreset,
          startMonth: participationStartMonth,
          endMonth: participationEndMonth,
        }),
      );
    } catch {
      // Si el navegador bloquea localStorage, la torta sigue funcionando sin cache.
    }
  }

  async function loadParticipation(refresh: boolean) {
    setMessage(null);

    if (
      participationPreset === "custom"
      && participationStartMonth
      && participationEndMonth
      && participationStartMonth > participationEndMonth
    ) {
      setMessage({ type: "error", text: "El periodo desde no puede ser mayor que hasta." });
      return;
    }

    setParticipationLoading(true);

    const params = new URLSearchParams({
      refresh: refresh ? "1" : "0",
      preset: participationPreset,
    });

    if (participationPreset === "custom") {
      if (participationStartMonth) params.set("start_month", participationStartMonth);
      if (participationEndMonth) params.set("end_month", participationEndMonth);
    }

    const response = await fetch(`/api/participation?${params.toString()}`, { cache: "no-store" });
    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo cargar participacion." }));
      setMessage({ type: "error", text: data.error || "No se pudo cargar participacion." });
      setParticipationLoading(false);
      return;
    }

    const data = await response.json();
    setParticipation(data);
    saveParticipationCache(data);
    setParticipationLoading(false);
  }

  function updateBookingField<K extends keyof BookingForm>(key: K, value: BookingForm[K]) {
    setBookingForm((current) => ({ ...current, [key]: value }));
  }

  function parseMoneyInput(value: string) {
    const cleaned = value.replace(/\./g, "").replace(",", ".").trim();
    const parsed = Number(cleaned);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  async function loadBookingShows() {
    const response = await fetch("/api/booking", { cache: "no-store" });
    if (!response.ok) return;
    const data = await response.json();
    setBookingItems(data.items || []);
  }

  async function loadBookingArtists() {
    const response = await fetch("/api/booking/artists", { cache: "no-store" });
    if (!response.ok) return;
    const data = await response.json();
    setBookingArtists(data.items || []);
  }

  async function submitBooking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setBookingLoading(true);

    const receiptRefs = bookingForm.receiptRefs
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter(Boolean);

    const response = await fetch("/api/booking", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        artist: bookingForm.artist,
        show_date: bookingForm.showDate,
        venue: bookingForm.venue,
        city: bookingForm.city || null,
        tour_manager: bookingForm.tourManager || null,
        seller: bookingForm.seller || null,
        status: bookingForm.status,
        currency: bookingForm.currency,
        fx_rate: bookingForm.fxRate ? parseMoneyInput(bookingForm.fxRate) : null,
        cachet_amount: parseMoneyInput(bookingForm.cachetAmount),
        expenses_amount: parseMoneyInput(bookingForm.expensesAmount),
        artist_paid_amount: parseMoneyInput(bookingForm.artistPaidAmount),
        producer_received_amount: parseMoneyInput(bookingForm.producerReceivedAmount),
        artist_percent: parseMoneyInput(bookingForm.artistPercent),
        producer_percent: bookingForm.producerPercent ? parseMoneyInput(bookingForm.producerPercent) : null,
        receipt_refs: receiptRefs,
        notes: bookingForm.notes || null,
      }),
    });

    if (!response.ok) {
      const data = await response.json().catch(() => ({ error: "No se pudo guardar el show." }));
      setMessage({ type: "error", text: data.error || "No se pudo guardar el show." });
      setBookingLoading(false);
      return;
    }

    const data = await response.json();
    setBookingItems((current) => [data.item, ...current].slice(0, 30));
    setBookingForm((current) => ({
      ...current,
      artist: "",
      venue: "",
      city: "",
      cachetAmount: "",
      expensesAmount: "",
      artistPaidAmount: "",
      producerReceivedAmount: "",
      receiptRefs: "",
      notes: "",
    }));
    setMessage({ type: "ok", text: "Show cargado correctamente." });
    setBookingLoading(false);
  }

  function submitRoyalties(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    generateExcel();
  }

  function openView(nextView: View) {
    setView(nextView);
    setMessage(null);
    setLastFile("");
    setLastSheetUrl("");
  }

  if (checkingSession) {
    return (
      <div className="login">
        <section className="panel">
          <div className="login-brand">
            <span className="brand-vpo">VPO</span>
            <span className="brand-corp">Corp</span>
          </div>
          <p>Validando sesion...</p>
        </section>
      </div>
    );
  }

  if (!authenticated) {
    return (
      <div className="login">
        <form className="panel" onSubmit={login}>
          <div className="login-brand">
            <span className="brand-vpo">VPO</span>
            <span className="brand-corp">Corp</span>
          </div>
          <p className="login-copy">Sistema privado de reportes de regalias digitales.</p>
          {message && <div className={`message ${message.type === "error" ? "error" : ""}`}>{message.text}</div>}
          <label htmlFor="password">Contrasena</label>
          <input id="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
          <button type="submit" disabled={loading}>{loading ? "Ingresando..." : "Ingresar"}</button>
        </form>
      </div>
    );
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand" aria-label="VPO Corp">
          <span className="brand-vpo">VPO</span>
          <span className="brand-corp">Corp</span>
        </div>
        <div className="top-actions">
          {view !== "menu" && <button type="button" onClick={() => openView("menu")}>Menu</button>}
          <button type="button" onClick={logout}>Salir</button>
        </div>
      </header>

      <main>
        {message && <div className={`message ${message.type === "error" ? "error" : ""}`}>{message.text}</div>}

        {view === "menu" && (
          <>
            <section className="home-hero">
              <div>
                <div className="hero-brand">
                  <span className="brand-vpo">VPO</span>
                  <span className="brand-corp">Corp</span>
                </div>
                <p>Royalty intelligence para reportes, statements y participacion digital.</p>
              </div>
              <div className="hero-stats">
                <span>Marts publicados</span>
                <strong>Live</strong>
              </div>
            </section>

            <div className="menu-grid">
              <button type="button" className="menu-card" onClick={() => openView("statement")}>
                <span className="card-index">01</span>
                <strong>Reporte por statement</strong>
                <span>Totales por artista, statement y distribuidora.</span>
              </button>
              <button type="button" className="menu-card" onClick={() => openView("royalties")}>
                <span className="card-index">02</span>
                <strong>Reporte de regalias</strong>
                <span>Busqueda por palabra clave, periodo, Excel o Google Sheets.</span>
              </button>
              <button type="button" className="menu-card" onClick={() => openView("participation")}>
                <span className="card-index">03</span>
                <strong>Participacion en distribuidoras</strong>
                <span>Torta simple por fuente, guardada desde marts publicados.</span>
              </button>
              <button type="button" className="menu-card" onClick={() => openView("booking")}>
                <span className="card-index">04</span>
                <strong>Booking / carga rapida</strong>
                <span>Carga directa de shows, gastos, pagos y comprobantes.</span>
              </button>
            </div>
          </>
        )}

        {view === "statement" && (
          <section className="panel">
            <h1>Reporte por statement</h1>
            <p>Genera el reporte historico por statement usando los marts nuevos publicados.</p>
            <label htmlFor="statement_min_total">No mostrar artistas menores a USD</label>
            <input
              id="statement_min_total"
              type="number"
              min="0"
              step="1"
              value={statementMinTotal}
              onChange={(event) => setStatementMinTotal(event.target.value)}
            />
            <p className="field-help">Se aplica por artista dentro de cada distribuidora/cuenta.</p>
            <button type="button" disabled={statementLoading} onClick={generateStatementReport}>
              {statementLoading ? "Generando..." : "Descargar reporte por statement"}
            </button>
            {lastFile && <p className="filename">{lastFile}</p>}
          </section>
        )}

        {view === "royalties" && (
          <div className="grid">
            <form className="panel" onSubmit={submitRoyalties}>
              <h1>Reporte de regalias</h1>
              <label htmlFor="keywords">Palabras clave</label>
              <input id="keywords" value={keywords} onChange={(event) => setKeywords(event.target.value)} placeholder="gusty dj, juli savioli" required />

              <div className="row">
                <div>
                  <label htmlFor="start_month">Desde</label>
                  <MonthSelect id="start_month" value={startMonth} onChange={setStartMonth} />
                </div>
                <div>
                  <label htmlFor="end_month">Hasta</label>
                  <MonthSelect id="end_month" value={endMonth} onChange={setEndMonth} />
                </div>
              </div>

              <label htmlFor="period_basis">Criterio de periodo</label>
              <select id="period_basis" value={periodBasis} onChange={(event) => setPeriodBasis(event.target.value)}>
                <option value="transaction_month">Performance / mes de consumo</option>
                <option value="statement_period">Liquidacion / mes de statement</option>
              </select>

              <label htmlFor="mode">Coincidencia</label>
              <select id="mode" value={mode} onChange={(event) => setMode(event.target.value)}>
                <option value="any">Cualquier palabra</option>
                <option value="all">Todas las palabras</option>
              </select>

              <label htmlFor="raw_limit">Filas raw maximas</label>
              <input id="raw_limit" type="number" min="0" max="50000" value={rawLimit} onChange={(event) => setRawLimit(event.target.value)} />

              <button type="submit" disabled={loading || googleLoading}>{loading ? "Generando..." : "Descargar Excel"}</button>
            </form>

            <div>
              <section className="panel">
                <h2>Google Sheets</h2>
                <p>Crea el mismo reporte como spreadsheet editable en Google Drive.</p>
                <button type="button" disabled={loading || googleLoading} onClick={createGoogleSheet}>
                  {googleLoading ? "Creando..." : "Crear Google Sheet"}
                </button>
              </section>

              {lastFile && (
                <section className="panel" style={{ marginTop: 24 }}>
                  <h2>Ultimo reporte</h2>
                  <p className="filename">{lastFile}</p>
                </section>
              )}

              {lastSheetUrl && (
                <section className="panel" style={{ marginTop: 24 }}>
                  <h2>Google Sheet</h2>
                  <p><a className="button" href={lastSheetUrl} target="_blank" rel="noreferrer">Abrir Google Sheet</a></p>
                </section>
              )}
            </div>
          </div>
        )}

        {view === "participation" && (
          <section className="panel">
            <div className="section-heading">
              <div>
                <h1>Participacion en distribuidoras</h1>
                <p>
                  Ultima actualizacion: {participation?.updated_at || "sin cargar"}
                  {participation?.start_month && participation?.end_month ? ` · ${participation.start_month} a ${participation.end_month}` : ""}
                </p>
              </div>
              <button type="button" onClick={() => loadParticipation(true)} disabled={participationLoading}>
                {participationLoading ? "Actualizando..." : "Actualizar"}
              </button>
            </div>

            <div className="period-controls">
              <div>
                <label htmlFor="participation_preset">Periodo</label>
                <select
                  id="participation_preset"
                  value={participationPreset}
                  onChange={(event) => setParticipationPreset(event.target.value)}
                >
                  <option value="last_month">Ultimo mes</option>
                  <option value="last_3_months">Ultimos tres meses</option>
                  <option value="last_year">Ultimo año</option>
                  <option value="all_history">Historico</option>
                  <option value="custom">Rango</option>
                </select>
              </div>

              {participationPreset === "custom" && (
                <>
                  <div>
                    <label htmlFor="participation_start">Desde</label>
                    <MonthSelect
                      id="participation_start"
                      value={participationStartMonth}
                      min={participation?.available_start_month || undefined}
                      onChange={setParticipationStartMonth}
                    />
                  </div>
                  <div>
                    <label htmlFor="participation_end">Hasta</label>
                    <MonthSelect
                      id="participation_end"
                      value={participationEndMonth}
                      min={participation?.available_start_month || undefined}
                      onChange={setParticipationEndMonth}
                    />
                  </div>
                </>
              )}

              <button type="button" onClick={() => loadParticipation(false)} disabled={participationLoading}>
                {participationLoading ? "Cargando..." : "Aplicar"}
              </button>
            </div>

            {participation?.start_date && participation?.end_date && (
              <div className="period-meta">
                <strong>Rango aplicado</strong>
                <span>{participation.start_date} a {participation.end_date}</span>
                <strong>Total</strong>
                <span>{money(participation.total_amount_usd)}</span>
              </div>
            )}

            <div className="pie-layout">
              <div className="pie" style={pieStyle} aria-label="Participacion por distribuidora" />
              <div className="legend">
                {participation?.items.map((item, idx) => (
                  <div className="legend-row" key={item.source}>
                    <span className="swatch" style={{ background: PIE_COLORS[idx % PIE_COLORS.length] }} />
                    <strong>{item.source}</strong>
                    <span>{pct(item.percentage)}</span>
                    <span>{money(item.amount_usd)}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {view === "booking" && (
          <div className="grid booking-grid">
            <form className="panel" onSubmit={submitBooking}>
              <h1>Booking / carga rapida</h1>
              <p>Alta directa de show y rendicion inicial, sin agenda previa.</p>

              <div className="row">
                <div>
                  <label htmlFor="booking_artist">Artista</label>
                  <select id="booking_artist" value={bookingForm.artist} onChange={(event) => updateBookingField("artist", event.target.value)} required>
                    <option value="">Elegir artista</option>
                    {bookingArtists.map((artist) => (
                      <option key={artist} value={artist}>{artist}</option>
                    ))}
                  </select>
                  {bookingArtists.length === 0 && <p className="field-help">No hay artistas disponibles para cargar.</p>}
                </div>
                <div>
                  <label htmlFor="booking_date">Fecha</label>
                  <input id="booking_date" type="date" value={bookingForm.showDate} onChange={(event) => updateBookingField("showDate", event.target.value)} required />
                </div>
              </div>

              <div className="row">
                <div>
                  <label htmlFor="booking_venue">Venue / evento</label>
                  <input id="booking_venue" value={bookingForm.venue} onChange={(event) => updateBookingField("venue", event.target.value)} required />
                </div>
                <div>
                  <label htmlFor="booking_city">Ciudad</label>
                  <input id="booking_city" value={bookingForm.city} onChange={(event) => updateBookingField("city", event.target.value)} />
                </div>
              </div>

              <div className="row">
                <div>
                  <label htmlFor="booking_tm">Tour manager</label>
                  <input id="booking_tm" value={bookingForm.tourManager} onChange={(event) => updateBookingField("tourManager", event.target.value)} />
                </div>
                <div>
                  <label htmlFor="booking_status">Estado</label>
                  <select id="booking_status" value={bookingForm.status} onChange={(event) => updateBookingField("status", event.target.value)}>
                    <option value="realizado">Realizado</option>
                    <option value="pendiente">Pendiente</option>
                    <option value="rendido">Rendido</option>
                    <option value="aprobado">Aprobado</option>
                    <option value="no_cobrado">No cobrado</option>
                    <option value="cancelado">Cancelado</option>
                  </select>
                </div>
              </div>

              <div className="row three">
                <div>
                  <label htmlFor="booking_currency">Moneda</label>
                  <select id="booking_currency" value={bookingForm.currency} onChange={(event) => updateBookingField("currency", event.target.value as "ARS" | "USD")}>
                    <option value="ARS">ARS</option>
                    <option value="USD">USD</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="booking_fx">Tipo de cambio</label>
                  <input id="booking_fx" inputMode="decimal" value={bookingForm.fxRate} onChange={(event) => updateBookingField("fxRate", event.target.value)} placeholder="opcional" />
                </div>
                <div>
                  <label htmlFor="booking_cachet">Cachet</label>
                  <input id="booking_cachet" inputMode="decimal" value={bookingForm.cachetAmount} onChange={(event) => updateBookingField("cachetAmount", event.target.value)} placeholder="1000000" />
                </div>
              </div>

              <div className="row">
                <div>
                  <label htmlFor="booking_expenses">Gastos del show</label>
                  <input id="booking_expenses" inputMode="decimal" value={bookingForm.expensesAmount} onChange={(event) => updateBookingField("expensesAmount", event.target.value)} />
                </div>
                <div>
                  <label htmlFor="booking_artist_paid">Pagado al artista</label>
                  <input id="booking_artist_paid" inputMode="decimal" value={bookingForm.artistPaidAmount} onChange={(event) => updateBookingField("artistPaidAmount", event.target.value)} />
                </div>
              </div>

              <div className="row three">
                <div>
                  <label htmlFor="booking_artist_pct">% artista</label>
                  <input id="booking_artist_pct" inputMode="decimal" value={bookingForm.artistPercent} onChange={(event) => updateBookingField("artistPercent", event.target.value)} />
                </div>
                <div>
                  <label htmlFor="booking_producer_pct">% productora</label>
                  <input id="booking_producer_pct" inputMode="decimal" value={bookingForm.producerPercent} onChange={(event) => updateBookingField("producerPercent", event.target.value)} />
                </div>
                <div>
                  <label htmlFor="booking_producer_received">Rendido a productora</label>
                  <input id="booking_producer_received" inputMode="decimal" value={bookingForm.producerReceivedAmount} onChange={(event) => updateBookingField("producerReceivedAmount", event.target.value)} />
                </div>
              </div>

              <label htmlFor="booking_receipts">Comprobantes / links / rutas</label>
              <textarea id="booking_receipts" value={bookingForm.receiptRefs} onChange={(event) => updateBookingField("receiptRefs", event.target.value)} placeholder="Uno por linea: C:\\comprobantes\\show.pdf o link de Drive/WhatsApp" />

              <label htmlFor="booking_notes">Notas</label>
              <textarea id="booking_notes" value={bookingForm.notes} onChange={(event) => updateBookingField("notes", event.target.value)} />

              <button type="submit" disabled={bookingLoading || bookingArtists.length === 0}>{bookingLoading ? "Guardando..." : "Guardar show"}</button>
            </form>

            <section className="panel">
              <div className="section-heading">
                <div>
                  <h2>Ultimas cargas</h2>
                  <p>Control rapido de shows cargados localmente.</p>
                </div>
                <button type="button" onClick={loadBookingShows} disabled={bookingLoading}>Actualizar</button>
              </div>

              <div className="booking-list">
                {bookingItems.length === 0 && <p className="field-help">Todavia no hay shows cargados en esta base local.</p>}
                {bookingItems.map((item) => (
                  <article className="booking-item" key={item.id}>
                    <div>
                      <strong>{item.artist}</strong>
                      <span>{item.show_date} · {item.venue}{item.city ? ` · ${item.city}` : ""}</span>
                    </div>
                    <div className="booking-metrics">
                      <span>Cachet {localAmount(item.cachet_amount, item.currency)}</span>
                      <span>Neto {localAmount(item.net_amount, item.currency)}</span>
                      <span>Artista {localAmount(item.artist_share_amount, item.currency)}</span>
                      <span>VPO {localAmount(item.producer_share_amount, item.currency)}</span>
                    </div>
                    <div className="booking-status">
                      <span>{item.status}</span>
                      {item.receipt_refs.length > 0 && <span>{item.receipt_refs.length} comprobante(s)</span>}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
