"use client";

import { FormEvent, MouseEvent, useEffect, useMemo, useState } from "react";

type Message = {
  type: "ok" | "error";
  text: string;
};

type View = "menu" | "statement" | "royalties" | "participation";

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

const PIE_COLORS = ["#17324d", "#0f766e", "#b54708", "#6941c6", "#b42318", "#475467", "#2e90fa"];
const PARTICIPATION_CACHE_KEY = "vpo_participation_last_result";

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

export default function Home() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [view, setView] = useState<View>("menu");
  const [password, setPassword] = useState("");
  const [keywords, setKeywords] = useState("");
  const [startMonth, setStartMonth] = useState("");
  const [endMonth, setEndMonth] = useState("");
  const [mode, setMode] = useState("any");
  const [rawLimit, setRawLimit] = useState("5000");
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

    const response = await fetch("/api/report", {
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

    const blob = await response.blob();
    const filename = filenameFromDisposition(response.headers.get("content-disposition"), "vpo_corp_report.xlsx");
    downloadBlob(blob, filename);
    setLastFile(filename);
    setMessage({ type: "ok", text: "Reporte generado correctamente." });
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
      body: JSON.stringify({ refresh_cache: false }),
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
          <h1>VPO Corp</h1>
          <p>Validando sesion...</p>
        </section>
      </div>
    );
  }

  if (!authenticated) {
    return (
      <div className="login">
        <form className="panel" onSubmit={login}>
          <h1>VPO Corp</h1>
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
        <div className="brand">VPO Corp</div>
        <div className="top-actions">
          {view !== "menu" && <button type="button" onClick={() => openView("menu")}>Menu</button>}
          <button type="button" onClick={logout}>Salir</button>
        </div>
      </header>

      <main>
        {message && <div className={`message ${message.type === "error" ? "error" : ""}`}>{message.text}</div>}

        {view === "menu" && (
          <div className="menu-grid">
            <button type="button" className="menu-card" onClick={() => openView("statement")}>
              <strong>Reporte por statement</strong>
              <span>Totales por artista, statement y distribuidora.</span>
            </button>
            <button type="button" className="menu-card" onClick={() => openView("royalties")}>
              <strong>Reporte de regalias</strong>
              <span>Busqueda por palabra clave, periodo, Excel o Google Sheets.</span>
            </button>
            <button type="button" className="menu-card" onClick={() => openView("participation")}>
              <strong>Participacion en distribuidoras</strong>
              <span>Torta simple por fuente, guardada desde marts publicados.</span>
            </button>
          </div>
        )}

        {view === "statement" && (
          <section className="panel">
            <h1>Reporte por statement</h1>
            <p>Genera el reporte historico por statement usando los marts nuevos publicados.</p>
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
                  <input id="start_month" type="month" value={startMonth} onChange={(event) => setStartMonth(event.target.value)} />
                </div>
                <div>
                  <label htmlFor="end_month">Hasta</label>
                  <input id="end_month" type="month" value={endMonth} onChange={(event) => setEndMonth(event.target.value)} />
                </div>
              </div>

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
                  <option value="last_year">Ultimo ano</option>
                  <option value="all_history">Historico</option>
                  <option value="custom">Rango</option>
                </select>
              </div>

              {participationPreset === "custom" && (
                <>
                  <div>
                    <label htmlFor="participation_start">Desde</label>
                    <input
                      id="participation_start"
                      type="month"
                      value={participationStartMonth}
                      min={participation?.available_start_month || undefined}
                      onChange={(event) => setParticipationStartMonth(event.target.value)}
                    />
                  </div>
                  <div>
                    <label htmlFor="participation_end">Hasta</label>
                    <input
                      id="participation_end"
                      type="month"
                      value={participationEndMonth}
                      min={participation?.available_start_month || undefined}
                      onChange={(event) => setParticipationEndMonth(event.target.value)}
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
      </main>
    </div>
  );
}
