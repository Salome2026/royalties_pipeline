"use client";

import { useState } from "react";
import { Download, FileSpreadsheet, SlidersHorizontal } from "lucide-react";
import { downloadBlob } from "../../lib/download";
import { requestStatementReport } from "./api";
import styles from "./StatementReportModule.module.css";

type Message = { type: "ok" | "error"; text: string };

type Props = {
  onMessage: (message: Message | null) => void;
};

export function StatementReportModule({ onMessage }: Props) {
  const [reportVersion, setReportVersion] = useState("legacy");
  const [minArtistTotal, setMinArtistTotal] = useState("0");
  const [includeZeros, setIncludeZeros] = useState(false);
  const [loading, setLoading] = useState(false);
  const [lastFile, setLastFile] = useState("");

  async function generateReport() {
    setLoading(true);
    setLastFile("");
    onMessage(null);
    try {
      const report = await requestStatementReport({
        minArtistTotalUsd: Number(minArtistTotal) || 0,
        includeZeroTotalArtists: includeZeros,
        reportVersion,
      });
      downloadBlob(report.blob, report.filename);
      setLastFile(report.filename);
      onMessage({ type: "ok", text: "Reporte por statement generado correctamente." });
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo generar el reporte por statement." });
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className={styles.workspace}>
      <header className={styles.intro}>
        <div className={styles.icon} aria-hidden="true"><FileSpreadsheet size={22} /></div>
        <div>
          <span>Regalías digitales</span>
          <h1>Reporte por statement</h1>
          <p>Generá un Excel histórico desde los marts publicados, listo para revisar y compartir.</p>
        </div>
      </header>

      <div className={styles.form}>
        <div className={styles.sectionTitle}>
          <SlidersHorizontal size={18} aria-hidden="true" />
          <div>
            <strong>Configuración</strong>
            <span>Elegí el alcance antes de descargar.</span>
          </div>
        </div>

        <div className={styles.fields}>
          <div className={styles.field}>
            <label htmlFor="statement_report_version">Tipo de reporte</label>
            <select id="statement_report_version" value={reportVersion} onChange={(event) => setReportVersion(event.target.value)}>
              <option value="legacy">Reporte histórico</option>
              <option value="new">Reporte actual</option>
            </select>
            <small>El actual excluye ONErpm MAWZ y usa las variantes posteriores a Motorcito y La Nueva Sangre.</small>
          </div>

          <div className={styles.field}>
            <label htmlFor="statement_min_total">Ingreso mínimo por artista</label>
            <div className={styles.moneyInput}>
              <span>USD</span>
              <input id="statement_min_total" type="number" min="0" step="1" value={minArtistTotal} onChange={(event) => setMinArtistTotal(event.target.value)} />
            </div>
            <small>Se evalúa por artista dentro de cada distribuidora y cuenta.</small>
          </div>
        </div>

        <label className={styles.toggleRow}>
          <span>
            <strong>Incluir artistas con total cero</strong>
            <small>Si está desactivado, se incluyen únicamente importes mayores a cero.</small>
          </span>
          <input type="checkbox" checked={includeZeros} onChange={(event) => setIncludeZeros(event.target.checked)} />
        </label>

        <footer className={styles.actions}>
          <div>
            <strong>Archivo Excel</strong>
            <span>{lastFile || "Se descargará al finalizar el procesamiento."}</span>
          </div>
          <button type="button" disabled={loading} onClick={() => void generateReport()}>
            <Download size={18} aria-hidden="true" />
            {loading ? "Generando..." : "Generar y descargar"}
          </button>
        </footer>
      </div>
    </section>
  );
}
