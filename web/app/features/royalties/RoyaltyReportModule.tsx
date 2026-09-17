"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { AlertCircle, CheckCircle2, Clock3, Download, ExternalLink, FileSpreadsheet, FileText, Globe2, LoaderCircle, Rows3, Search, SlidersHorizontal } from "lucide-react";
import { PeriodControl } from "../../components/PeriodControl";
import { isResolvedPeriodInvalid, resolvePeriod, type PeriodSelection } from "../../lib/period";
import {
  createRoyaltyReportJob,
  requestRecentRoyaltyReportJobs,
  requestRoyaltyDetailCount,
  requestRoyaltyReportOptions,
  requestRoyaltyReportJob,
  royaltyReportJobDownloadUrl,
  type RoyaltyMatchMode,
  type RoyaltyDetailMode,
  type RoyaltyPeriodBasis,
  type RoyaltyReportJob,
  type RoyaltyReportOptions,
  type RoyaltyReportOutput,
  type RoyaltyReportPayload,
} from "./api";
import styles from "./RoyaltyReportModule.module.css";

type Message = { type: "ok" | "error"; text: string };

type Props = {
  onMessage: (message: Message | null) => void;
};

export function RoyaltyReportModule({ onMessage }: Props) {
  const [output, setOutput] = useState<RoyaltyReportOutput>("excel");
  const [keywords, setKeywords] = useState("");
  const [period, setPeriod] = useState<PeriodSelection>({ mode: "all" });
  const [periodBasis, setPeriodBasis] = useState<RoyaltyPeriodBasis>("transaction_month");
  const [matchMode, setMatchMode] = useState<RoyaltyMatchMode>("any");
  const [rawLimit, setRawLimit] = useState("5000");
  const [detailMode, setDetailMode] = useState<RoyaltyDetailMode>("limited");
  const [options, setOptions] = useState<RoyaltyReportOptions | null>(null);
  const [source, setSource] = useState("");
  const [account, setAccount] = useState("");
  const [loading, setLoading] = useState(false);
  const [countingRows, setCountingRows] = useState(false);
  const [pendingFullReport, setPendingFullReport] = useState<{
    payload: RoyaltyReportPayload;
    output: RoyaltyReportOutput | "google_sheet";
    rows: number;
  } | null>(null);
  const [activeJob, setActiveJob] = useState<RoyaltyReportJob | null>(null);
  const [recentJobs, setRecentJobs] = useState<RoyaltyReportJob[]>([]);
  const [lastFile, setLastFile] = useState("");
  const [lastSheetUrl, setLastSheetUrl] = useState("");
  const downloadedJobs = useRef(new Set<number>());

  useEffect(() => {
    let active = true;
    requestRoyaltyReportOptions()
      .then((data) => {
        if (active) setOptions(data);
      })
      .catch((error) => {
        if (active) onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudieron cargar las distribuidoras." });
      });
    return () => {
      active = false;
    };
  }, [onMessage]);

  useEffect(() => {
    let active = true;
    requestRecentRoyaltyReportJobs()
      .then((items) => {
        if (active) setRecentJobs(items);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!activeJob || !["queued", "running"].includes(activeJob.status)) return;
    const jobId = activeJob.id;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function poll() {
      try {
        const job = await requestRoyaltyReportJob(jobId);
        if (!active) return;
        setActiveJob(job);
        setRecentJobs((items) => [job, ...items.filter((item) => item.id !== job.id)].slice(0, 8));
        if (job.status === "completed") {
          if (job.output_format === "google_sheet" && job.result_url) {
            setLastSheetUrl(job.result_url);
            onMessage({ type: "ok", text: "Google Sheet terminado y disponible." });
          } else {
            setLastFile(job.result_filename || "Reporte listo");
            onMessage({ type: "ok", text: "Reporte terminado. La descarga ya está disponible." });
            if (!downloadedJobs.current.has(job.id)) {
              downloadedJobs.current.add(job.id);
              window.location.href = royaltyReportJobDownloadUrl(job.id);
            }
          }
          return;
        }
        if (job.status === "failed") {
          onMessage({ type: "error", text: job.error_message || "El reporte no pudo completarse." });
          return;
        }
        timer = setTimeout(poll, 3000);
      } catch (error) {
        if (!active) return;
        onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo consultar el reporte." });
        timer = setTimeout(poll, 6000);
      }
    }

    timer = setTimeout(poll, 1500);
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [activeJob?.id, activeJob?.status, onMessage]);

  useEffect(() => {
    if (!pendingFullReport) return;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPendingFullReport(null);
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [pendingFullReport]);

  const accountOptions = useMemo(() => {
    if (!options || !source) return [];
    return options.source_accounts.filter((item) => item.source === source);
  }, [options, source]);

  function buildPayload(): RoyaltyReportPayload | null {
    const resolved = resolvePeriod(period, "monthly_report");
    if (isResolvedPeriodInvalid(resolved)) {
      onMessage({ type: "error", text: "El período desde no puede ser mayor que hasta." });
      return null;
    }
    const terms = keywords.split(/[;,]/).map((item) => item.trim()).filter(Boolean);
    if (output === "excel" && terms.length === 0) {
      onMessage({ type: "error", text: "Ingresá al menos una palabra clave para el Excel detallado." });
      return null;
    }
    const parsedRawLimit = Number(rawLimit);
    if (
      output === "excel"
      && detailMode === "limited"
      && (!Number.isInteger(parsedRawLimit) || parsedRawLimit < 0 || parsedRawLimit > 50000)
    ) {
      onMessage({ type: "error", text: "La cantidad máxima debe ser un número entero entre 0 y 50.000." });
      return null;
    }
    return {
      keywords: terms,
      start_month: resolved.startMonth,
      end_month: resolved.endMonth,
      period_basis: periodBasis,
      mode: matchMode,
      raw_limit: Number.isFinite(parsedRawLimit) ? parsedRawLimit : 0,
      detail_mode: output === "excel" ? detailMode : "limited",
      source: source || null,
      account: account || null,
    };
  }

  function resetResults() {
    onMessage(null);
    setLastFile("");
    setLastSheetUrl("");
  }

  async function startReport(
    payload: RoyaltyReportPayload,
    requestedOutput: RoyaltyReportOutput | "google_sheet",
  ) {
    setLoading(true);
    try {
      const job = await createRoyaltyReportJob(payload, requestedOutput);
      setActiveJob(job);
      setRecentJobs((items) => [job, ...items.filter((item) => item.id !== job.id)].slice(0, 8));
      onMessage({
        type: "ok",
        text: requestedOutput === "google_sheet"
          ? "Google Sheet recibido. Podés salir de esta pantalla y volver más tarde."
          : "Reporte recibido. Podés salir de esta pantalla y volver más tarde.",
      });
    } catch (error) {
      onMessage({
        type: "error",
        text: error instanceof Error
          ? error.message
          : requestedOutput === "google_sheet"
            ? "No se pudo iniciar el Google Sheet."
            : "No se pudo iniciar el reporte.",
      });
    } finally {
      setLoading(false);
    }
  }

  async function requestReport(
    payload: RoyaltyReportPayload,
    requestedOutput: RoyaltyReportOutput | "google_sheet",
  ) {
    if (payload.detail_mode !== "full") {
      await startReport(payload, requestedOutput);
      return;
    }

    setCountingRows(true);
    try {
      const count = await requestRoyaltyDetailCount(payload);
      if (count.exceeds_excel_limit) {
        onMessage({
          type: "error",
          text: `No se puede generar el detalle completo. Contiene ${count.rows.toLocaleString("es-AR")} filas y supera el máximo permitido por Excel de ${count.excel_max_data_rows.toLocaleString("es-AR")}. Reducí el período o aplicá más filtros.`,
        });
        return;
      }
      setPendingFullReport({ payload, output: requestedOutput, rows: count.rows });
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo calcular la cantidad de filas." });
    } finally {
      setCountingRows(false);
    }
  }

  async function submitReport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    resetResults();
    const payload = buildPayload();
    if (!payload) return;
    await requestReport(payload, output);
  }

  async function createGoogleSheet() {
    resetResults();
    const payload = buildPayload();
    if (!payload) return;
    await requestReport(payload, "google_sheet");
  }

  const jobInProgress = Boolean(activeJob && ["queued", "running"].includes(activeJob.status));
  const stageLabel = activeJob ? ({
    queued: "En cola",
    preparing: "Preparando",
    reading_data: "Leyendo datos",
    building: "Armando informe",
    uploading: "Guardando resultado",
    completed: "Listo",
    failed: "Con error",
  }[activeJob.progress_stage] || activeJob.progress_stage) : "";

  return (
    <section className={styles.workspace}>
      <header className={styles.intro}>
        <div className={styles.icon} aria-hidden="true"><FileText size={22} /></div>
        <div>
          <span>Regalías digitales</span>
          <h1>Reporte de regalías</h1>
          <p>Buscá artistas, temas o identificadores y generá el entregable adecuado con las reglas vigentes.</p>
        </div>
      </header>

      <form className={styles.surface} onSubmit={submitReport}>
        <div className={styles.formatBand}>
          <div>
            <strong>Formato de salida</strong>
            <span>El alcance económico es el mismo; cambia la presentación.</span>
          </div>
          <div className={styles.segmented} role="group" aria-label="Formato del reporte">
            <button type="button" className={output === "excel" ? styles.active : ""} onClick={() => setOutput("excel")}>
              <FileSpreadsheet size={17} aria-hidden="true" /> Excel detallado
            </button>
            <button type="button" className={output === "executive_pdf" ? styles.active : ""} onClick={() => setOutput("executive_pdf")}>
              <FileText size={17} aria-hidden="true" /> PDF ejecutivo
            </button>
          </div>
        </div>

        <div className={styles.body}>
          <div className={styles.primaryFields}>
            <div className={styles.sectionTitle}>
              <Search size={18} aria-hidden="true" />
              <div><strong>Qué querés informar</strong><span>La búsqueda acepta artista, tema, ISRC u otros identificadores reconocidos.</span></div>
            </div>

            <div className={styles.field}>
              <label htmlFor="royalty_keywords">Palabras clave {output === "executive_pdf" && <em>Opcional</em>}</label>
              <input
                id="royalty_keywords"
                value={keywords}
                onChange={(event) => setKeywords(event.target.value)}
                placeholder={output === "executive_pdf" ? "Todo el alcance o una búsqueda puntual" : "Ej. Gusty DJ, ISRC, nombre del tema"}
                required={output === "excel"}
              />
              <small>Separá varias búsquedas con coma o punto y coma.</small>
            </div>

            <div className={styles.periodField}>
              <PeriodControl
                id="royalty_period"
                label="Período"
                profile="monthly_report"
                selection={period}
                onChange={setPeriod}
                helperText="Un mes incluye ese mes completo. Un rango incluye ambos meses completos."
              />
            </div>

            <div className={styles.field}>
              <label htmlFor="royalty_period_basis">Leer el período por</label>
              <select id="royalty_period_basis" value={periodBasis} onChange={(event) => setPeriodBasis(event.target.value as RoyaltyPeriodBasis)}>
                <option value="transaction_month">Mes de consumo / performance</option>
                <option value="statement_period">Mes de statement / liquidación</option>
              </select>
              <small>Statement sirve para liquidaciones; consumo sirve para analizar cuándo ocurrió la actividad.</small>
            </div>
          </div>

          <aside className={styles.secondaryFields}>
            <div className={styles.sectionTitle}>
              <SlidersHorizontal size={18} aria-hidden="true" />
              <div><strong>{output === "excel" ? "Detalle del Excel" : "Alcance del PDF"}</strong><span>Solo aparecen las opciones necesarias para este formato.</span></div>
            </div>

            {output === "excel" ? (
              <>
                <div className={styles.field}>
                  <label htmlFor="royalty_match_mode">Coincidencia</label>
                  <select id="royalty_match_mode" value={matchMode} onChange={(event) => setMatchMode(event.target.value as RoyaltyMatchMode)}>
                    <option value="any">Cualquier palabra</option>
                    <option value="all">Todas las palabras</option>
                  </select>
                </div>
                <div className={styles.field}>
                  <label htmlFor="royalty_raw_limit">Cantidad máxima de filas</label>
                  <input
                    id="royalty_raw_limit"
                    type="number"
                    min="0"
                    max="50000"
                    step="1"
                    value={rawLimit}
                    disabled={detailMode !== "limited"}
                    onChange={(event) => setRawLimit(event.target.value)}
                  />
                  <small>Ingrese un valor entre 0 y 50.000. Use 0 para generar solo los resúmenes.</small>
                </div>
                <div className={styles.detailOptions} aria-label="Opciones de detalle">
                  <label className={detailMode === "top_countries" ? styles.detailOptionActive : ""}>
                    <input
                      type="checkbox"
                      checked={detailMode === "top_countries"}
                      onChange={(event) => setDetailMode(event.target.checked ? "top_countries" : "limited")}
                    />
                    <Globe2 size={17} aria-hidden="true" />
                    <span>
                      <strong>Priorizar los 5 países con mayores ingresos</strong>
                      <small>Incluye Spotify y YouTube en detalle. Las demás plataformas y países se muestran consolidados.</small>
                    </span>
                  </label>
                  <label className={detailMode === "full" ? styles.detailOptionActive : ""}>
                    <input
                      type="checkbox"
                      checked={detailMode === "full"}
                      onChange={(event) => setDetailMode(event.target.checked ? "full" : "limited")}
                    />
                    <Rows3 size={17} aria-hidden="true" />
                    <span>
                      <strong>Incluir todas las filas del detalle</strong>
                      <small>Genera el detalle completo, sin aplicar el límite indicado arriba.</small>
                    </span>
                  </label>
                </div>
              </>
            ) : (
              <>
                <div className={styles.field}>
                  <label htmlFor="royalty_source">Distribuidora</label>
                  <select id="royalty_source" value={source} onChange={(event) => { setSource(event.target.value); setAccount(""); }}>
                    <option value="">Todas</option>
                    {(options?.sources || []).map((item) => <option value={item} key={item}>{item.toUpperCase()}</option>)}
                  </select>
                </div>
                <div className={styles.field}>
                  <label htmlFor="royalty_account">Cuenta</label>
                  <select id="royalty_account" value={account} disabled={!source} onChange={(event) => setAccount(event.target.value)}>
                    <option value="">Todas</option>
                    {accountOptions.map((item) => <option value={item.account} key={`${item.source}:${item.account}`}>{item.display_name}</option>)}
                  </select>
                  <small>Sin distribuidora seleccionada, el PDF considera todas las cuentas.</small>
                </div>
              </>
            )}
          </aside>
        </div>

        {activeJob && (
          <div className={`${styles.jobStatus} ${styles[activeJob.status]}`}>
            <div className={styles.jobStatusIcon}>
              {activeJob.status === "completed" ? <CheckCircle2 size={20} aria-hidden="true" /> : activeJob.status === "failed" ? <AlertCircle size={20} aria-hidden="true" /> : <LoaderCircle size={20} aria-hidden="true" />}
            </div>
            <div>
              <strong>{stageLabel}</strong>
              <span>
                {activeJob.status === "failed"
                  ? activeJob.error_message || "No se pudo completar el reporte."
                  : activeJob.status === "completed"
                    ? activeJob.result_filename || "Resultado disponible"
                    : `Trabajo #${activeJob.id}. Podés salir y volver más tarde.`}
              </span>
            </div>
            {activeJob.status === "completed" && activeJob.output_format !== "google_sheet" && (
              <a href={royaltyReportJobDownloadUrl(activeJob.id)}><Download size={16} aria-hidden="true" /> Descargar</a>
            )}
            {activeJob.status === "completed" && activeJob.output_format === "google_sheet" && activeJob.result_url && (
              <a href={activeJob.result_url} target="_blank" rel="noreferrer"><ExternalLink size={16} aria-hidden="true" /> Abrir</a>
            )}
          </div>
        )}

        <footer className={styles.actions}>
          <div className={styles.result}>
            <strong>{lastSheetUrl ? "Google Sheet disponible" : lastFile ? "Último resultado" : "Listo para generar"}</strong>
            {lastSheetUrl ? (
              <a href={lastSheetUrl} target="_blank" rel="noreferrer">Abrir Google Sheet <ExternalLink size={14} aria-hidden="true" /></a>
            ) : (
              <span>{lastFile || (output === "excel" ? "Excel detallado" : "PDF ejecutivo de una página")}</span>
            )}
          </div>
          <div className={styles.actionButtons}>
            {output === "excel" && (
              <button type="button" className={styles.secondaryAction} disabled={loading || countingRows || jobInProgress} onClick={() => void createGoogleSheet()}>
                <ExternalLink size={17} aria-hidden="true" /> Crear Google Sheet
              </button>
            )}
            <button type="submit" className={styles.primaryAction} disabled={loading || countingRows || jobInProgress}>
              {jobInProgress || countingRows ? <LoaderCircle size={18} aria-hidden="true" /> : <Download size={18} aria-hidden="true" />}
              {countingRows ? "Calculando detalle..." : loading ? "Solicitando..." : jobInProgress ? "Procesando" : output === "executive_pdf" ? "Generar PDF" : "Generar Excel"}
            </button>
          </div>
        </footer>
      </form>

      {recentJobs.length > 0 && (
        <section className={styles.recentJobs}>
          <header><Clock3 size={17} aria-hidden="true" /><div><strong>Reportes recientes</strong><span>Podés recuperar resultados aunque hayas salido de la pantalla.</span></div></header>
          <div className={styles.recentList}>
            {recentJobs.map((job) => (
              <div className={styles.recentRow} key={job.id}>
                <span className={`${styles.statusDot} ${styles[job.status]}`} aria-hidden="true" />
                <div>
                  <strong>{job.output_format === "executive_pdf" ? "PDF ejecutivo" : job.output_format === "google_sheet" ? "Google Sheet" : "Excel detallado"}</strong>
                  <span>{job.params.keywords?.join(", ") || "Todas las regalías"} · #{job.id}</span>
                </div>
                <span className={styles.recentState}>{job.status === "completed" ? "Listo" : job.status === "failed" ? "Error" : job.status === "running" ? "Procesando" : "En cola"}</span>
                {job.status === "completed" && job.output_format !== "google_sheet" && <a href={royaltyReportJobDownloadUrl(job.id)} aria-label={`Descargar reporte ${job.id}`}><Download size={16} /></a>}
                {job.status === "completed" && job.output_format === "google_sheet" && job.result_url && <a href={job.result_url} target="_blank" rel="noreferrer" aria-label={`Abrir reporte ${job.id}`}><ExternalLink size={16} /></a>}
              </div>
            ))}
          </div>
        </section>
      )}

      {pendingFullReport && (
        <div className={styles.modalBackdrop} role="presentation">
          <div className={styles.confirmModal} role="dialog" aria-modal="true" aria-labelledby="full-detail-title">
            <div className={styles.confirmIcon} aria-hidden="true"><AlertCircle size={22} /></div>
            <div className={styles.confirmCopy}>
              <span>Confirmación</span>
              <h2 id="full-detail-title">Generar detalle completo</h2>
              <p>
                Este reporte contiene <strong>{pendingFullReport.rows.toLocaleString("es-AR")} filas de detalle</strong>.
                La generación puede llevar bastante tiempo.
              </p>
            </div>
            <div className={styles.modalActions}>
              <button type="button" className={styles.modalCancel} autoFocus onClick={() => setPendingFullReport(null)}>Cancelar</button>
              <button
                type="button"
                className={styles.modalConfirm}
                onClick={() => {
                  const pending = pendingFullReport;
                  setPendingFullReport(null);
                  void startReport(pending.payload, pending.output);
                }}
              >
                Generar igualmente
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
