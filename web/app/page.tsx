"use client";

import { FormEvent, useEffect, useState } from "react";

type Message = {
  type: "ok" | "error";
  text: string;
};

function filenameFromDisposition(disposition: string | null) {
  if (!disposition) return "vpo_corp_report.xlsx";
  const match = disposition.match(/filename="?([^"]+)"?/i);
  return match?.[1] || "vpo_corp_report.xlsx";
}

export default function Home() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [password, setPassword] = useState("");
  const [keywords, setKeywords] = useState("");
  const [startMonth, setStartMonth] = useState("");
  const [endMonth, setEndMonth] = useState("");
  const [mode, setMode] = useState("any");
  const [rawLimit, setRawLimit] = useState("5000");
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [message, setMessage] = useState<Message | null>(null);
  const [lastFile, setLastFile] = useState("");
  const [lastSheetUrl, setLastSheetUrl] = useState("");

  useEffect(() => {
    fetch("/api/session")
      .then((response) => response.json())
      .then((data) => setAuthenticated(Boolean(data.authenticated)))
      .catch(() => setAuthenticated(false))
      .finally(() => setCheckingSession(false));
  }, []);

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

  async function generateExcel() {
    setMessage(null);
    setLastFile("");
    setLastSheetUrl("");

    if (startMonth && endMonth && startMonth > endMonth) {
      setMessage({ type: "error", text: "El periodo desde no puede ser mayor que hasta." });
      return;
    }

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
    const filename = filenameFromDisposition(response.headers.get("content-disposition"));
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);

    setLastFile(filename);
    setMessage({ type: "ok", text: "Reporte generado correctamente." });
    setLoading(false);
  }

  async function createGoogleSheet() {
    setMessage(null);
    setLastFile("");
    setLastSheetUrl("");

    if (startMonth && endMonth && startMonth > endMonth) {
      setMessage({ type: "error", text: "El periodo desde no puede ser mayor que hasta." });
      return;
    }

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
    setMessage({ type: "ok", text: "Google Sheet creado correctamente." });
    setGoogleLoading(false);
  }

  function submitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    generateExcel();
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
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
          <button type="submit" disabled={loading}>{loading ? "Ingresando..." : "Ingresar"}</button>
        </form>
      </div>
    );
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">VPO Corp</div>
        <button type="button" onClick={logout}>Salir</button>
      </header>

      <main>
        {message && <div className={`message ${message.type === "error" ? "error" : ""}`}>{message.text}</div>}
        <div className="grid">
          <form className="panel" onSubmit={submitForm}>
            <h1>Reporte de royalties</h1>
            <label htmlFor="keywords">Palabras clave</label>
            <input
              id="keywords"
              value={keywords}
              onChange={(event) => setKeywords(event.target.value)}
              placeholder="gusty dj, juli savioli"
              required
            />

            <div className="row">
              <div>
                <label htmlFor="start_month">Desde</label>
                <input
                  id="start_month"
                  type="month"
                  value={startMonth}
                  onChange={(event) => setStartMonth(event.target.value)}
                />
              </div>
              <div>
                <label htmlFor="end_month">Hasta</label>
                <input
                  id="end_month"
                  type="month"
                  value={endMonth}
                  onChange={(event) => setEndMonth(event.target.value)}
                />
              </div>
            </div>

            <label htmlFor="mode">Coincidencia</label>
            <select id="mode" value={mode} onChange={(event) => setMode(event.target.value)}>
              <option value="any">Cualquier palabra</option>
              <option value="all">Todas las palabras</option>
            </select>

            <label htmlFor="raw_limit">Filas raw maximas</label>
            <input
              id="raw_limit"
              type="number"
              min="0"
              max="50000"
              value={rawLimit}
              onChange={(event) => setRawLimit(event.target.value)}
            />

            <button type="submit" disabled={loading || googleLoading}>{loading ? "Generando..." : "Descargar Excel"}</button>
            <button type="button" disabled={loading || googleLoading} onClick={createGoogleSheet}>
              {googleLoading ? "Creando..." : "Crear Google Sheet"}
            </button>
          </form>

          <div>
            <section className="panel">
              <h2>Salida</h2>
              <p>La web genera un XLSX formateado desde la API de VPO Corp. El archivo queda listo para abrir en Excel o subir a Google Sheets.</p>
              <div className="meta">
                <div><strong>Datos</strong>Google Cloud Storage</div>
                <div><strong>Backend</strong>Render API</div>
                <div><strong>Formato</strong>XLSX</div>
                <div><strong>Acceso</strong>Login web</div>
              </div>
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
      </main>
    </div>
  );
}
