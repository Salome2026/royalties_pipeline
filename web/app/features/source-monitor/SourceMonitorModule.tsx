"use client";

import { useEffect, useRef, useState } from "react";
import {
  BellOff,
  BellRing,
  Check,
  CloudUpload,
  Database,
  ExternalLink,
  FileCheck2,
  FileClock,
  Files,
  MonitorCheck,
  MonitorOff,
  Play,
  RefreshCw,
  RotateCw,
  ShieldAlert,
} from "lucide-react";
import type {
  SourceMonitorData,
  SourceMonitorItem,
  SourceMonitorProcessResult,
  SourceMonitorPublishJob,
  SourceMonitorPublishResult,
} from "./types";
import {
  requestSourceMonitor,
  requestSourceMonitorProcess,
  requestSourceMonitorPublish,
  requestSourceMonitorPublishStatus,
  requestSourceMonitorUpdate,
} from "./api";
import styles from "./SourceMonitorModule.module.css";

type Message = { type: "ok" | "error"; text: string };

type Props = {
  canEdit: boolean;
  onMessage: (message: Message | null) => void;
};

const INVENTORY_LABELS: Record<string, string> = {
  loaded_to_mart: "Cargados",
  pending_real: "Pendientes",
  ignored_empty: "Vacíos",
  ignored_summary: "Summaries omitidos",
  ignored_audit_detail: "Detalles auditados",
  legacy_manual: "Históricos",
};

const STATUS_LABELS: Record<SourceMonitorItem["status"], string> = {
  ok: "Al día",
  attention: "Revisar",
  alert: "Alerta",
  inactive: "Inactiva",
};

function money(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
  }).format(value || 0);
}

function inventoryLabel(summary?: Record<string, number>) {
  if (!summary) return "";
  return Object.entries(summary)
    .filter(([, count]) => count > 0)
    .map(([status, count]) => `${INVENTORY_LABELS[status] || status}: ${count}`)
    .join(" · ");
}

export function SourceMonitorModule({
  canEdit,
  onMessage,
}: Props) {
  const [data, setData] = useState<SourceMonitorData | null>(null);
  const [loading, setLoading] = useState(false);
  const [processingId, setProcessingId] = useState("");
  const [lastProcess, setLastProcess] = useState<SourceMonitorProcessResult | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [lastPublish, setLastPublish] = useState<SourceMonitorPublishResult | null>(null);
  const [publishJob, setPublishJob] = useState<SourceMonitorPublishJob | null>(null);
  const publishTimer = useRef<number | null>(null);

  async function loadMonitor() {
    setLoading(true);
    try {
      setData(await requestSourceMonitor());
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo cargar el control de distribuidoras." });
    } finally {
      setLoading(false);
    }
  }

  async function updateItem(id: string, body: Partial<SourceMonitorItem>) {
    setLoading(true);
    try {
      await requestSourceMonitorUpdate(id, body);
      await loadMonitor();
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo actualizar el control de la distribuidora." });
    } finally {
      setLoading(false);
    }
  }

  async function processItem(id: string) {
    setProcessingId(id);
    onMessage(null);
    try {
      const result = await requestSourceMonitorProcess(id);
      setLastProcess(result);
      await loadMonitor();
      onMessage({ type: "ok", text: "Archivos procesados localmente. Revisá el resumen antes de publicar." });
    } catch (error) {
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo procesar la distribuidora." });
    } finally {
      setProcessingId("");
    }
  }

  async function pollPublishJob(jobId: string) {
    try {
      const job = await requestSourceMonitorPublishStatus(jobId);
      setPublishJob(job);
      if (job.status === "completed" && job.result) {
        setLastPublish(job.result);
        setPublishing(false);
        onMessage({ type: "ok", text: "Datos analíticos publicados. La web online ya puede usar la actualización." });
        await loadMonitor();
        return;
      }
      if (job.status === "failed") {
        const errorText = typeof job.error === "string" ? job.error : JSON.stringify(job.error || "Error de publicación");
        setPublishing(false);
        onMessage({ type: "error", text: `Falló la publicación: ${errorText}` });
        return;
      }
      publishTimer.current = window.setTimeout(() => void pollPublishJob(jobId), 4000);
    } catch (error) {
      setPublishing(false);
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo consultar el estado de publicación." });
    }
  }

  async function publish() {
    setPublishing(true);
    setPublishJob(null);
    onMessage(null);
    try {
      const job = await requestSourceMonitorPublish();
      setPublishJob(job);
      onMessage({ type: "ok", text: "Publicación iniciada. Podés dejar esta pantalla abierta mientras se actualiza." });
      void pollPublishJob(job.job_id);
    } catch (error) {
      setPublishing(false);
      onMessage({ type: "error", text: error instanceof Error ? error.message : "No se pudo iniciar la publicación." });
    }
  }

  useEffect(() => {
    void loadMonitor();
    return () => {
      if (publishTimer.current !== null) window.clearTimeout(publishTimer.current);
    };
  }, []);

  const items = data?.items || [];
  const pendingTotal = items.reduce((sum, item) => sum + item.unprocessed_raw_count, 0);
  const ignoredTotal = items.reduce((sum, item) => sum + (item.ignored_raw_count || 0), 0);
  const rawTotal = items.reduce((sum, item) => sum + item.raw_files, 0);
  const loadedTotal = items.reduce((sum, item) => sum + item.files_in_mart, 0);
  const canPublish = canEdit && pendingTotal === 0 && !publishing && !processingId && !loading;
  const publishReason = !canEdit
    ? "Necesitás permiso de edición para publicar."
    : loading
      ? "Esperá a que termine la revisión."
      : processingId
        ? "Hay un procesamiento en curso."
        : pendingTotal > 0
          ? "Procesá los archivos pendientes antes de publicar."
          : "Publicar los datos analíticos validados.";

  return (
    <main className={styles.workspace}>
      <header className={styles.intro}>
        <div className={styles.introIcon}><Database size={23} /></div>
        <div>
          <span>Operación analítica</span>
          <h1>Control de distribuidoras</h1>
          <p>Estados de carga, archivos pendientes y publicación de la información validada.</p>
        </div>
        <button className={styles.refreshButton} type="button" onClick={() => void loadMonitor()} disabled={loading}>
          <RefreshCw size={16} className={loading ? styles.spinning : ""} />
          {loading ? "Revisando" : "Revisar todas"}
        </button>
      </header>

      {!canEdit && (
        <div className={styles.accessNotice}>
          <ShieldAlert size={18} />
          <span>Podés consultar el estado. Para procesar, publicar o cambiar alertas necesitás permiso de edición.</span>
        </div>
      )}

      <section className={styles.metrics} aria-label="Resumen de distribuidoras">
        <div><Database size={17} /><span>Fuentes</span><strong>{data?.summary.total ?? 0}</strong></div>
        <div><Files size={17} /><span>Raw detectados</span><strong>{rawTotal}</strong></div>
        <div><FileCheck2 size={17} /><span>Cargados</span><strong>{loadedTotal}</strong></div>
        <div className={pendingTotal > 0 ? styles.metricWarning : ""}><FileClock size={17} /><span>Pendientes</span><strong>{pendingTotal}</strong></div>
        <div><Check size={17} /><span>Ignorados válidos</span><strong>{ignoredTotal}</strong></div>
        <div className={(data?.summary.alerts || 0) > 0 ? styles.metricDanger : ""}><ShieldAlert size={17} /><span>Alertas</span><strong>{data?.summary.alerts ?? 0}</strong></div>
      </section>

      {lastProcess && (
        <section className={styles.processResult}>
          <div className={styles.processHeading}>
            <div>
              <span>Último procesamiento</span>
              <h2>{lastProcess.display_name}</h2>
              <p>{lastProcess.processed_at}</p>
            </div>
            <div className={styles.processTotal}><span>Total procesado</span><strong>{money(lastProcess.total_amount_usd)}</strong></div>
          </div>
          <div className={styles.processMeta}>
            <div><span>Statement anterior</span><strong>{lastProcess.last_statement_before || "-"}</strong></div>
            <div><span>Statement actual</span><strong>{lastProcess.last_statement_after || "-"}</strong></div>
            <div><span>Filas</span><strong>{lastProcess.total_rows.toLocaleString("es-AR")}</strong></div>
            <div><span>Pendientes</span><strong>{lastProcess.pending_files_after.length}</strong></div>
          </div>
          {lastProcess.summary.length > 0 && (
            <div className={styles.resultTableWrap}>
              <table>
                <thead><tr><th>Statement</th><th>Filas</th><th>Archivos</th><th>USD</th></tr></thead>
                <tbody>
                  {lastProcess.summary.map((row) => (
                    <tr key={row.statement_period}>
                      <td>{row.statement_period}</td>
                      <td>{row.rows.toLocaleString("es-AR")}</td>
                      <td>{row.files}</td>
                      <td>{money(row.amount_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      <section className={styles.distributors}>
        <div className={styles.sectionTitle}>
          <div><span>Fuentes configuradas</span><h2>Estado por cuenta</h2></div>
          <small>{data?.generated_at ? `Actualizado ${data.generated_at}` : "Sin revisión cargada"}</small>
        </div>

        {items.length === 0 && !loading && <div className={styles.empty}>No hay distribuidoras configuradas.</div>}

        <div className={styles.distributorList}>
          {items.map((item) => {
            const processing = processingId === item.id;
            const inventory = inventoryLabel(item.raw_inventory_summary);
            return (
              <article className={`${styles.distributorRow} ${styles[item.status]}`} key={item.id}>
                <div className={styles.identity}>
                  <div className={styles.sourceMark}>{item.display_name.slice(0, 2).toUpperCase()}</div>
                  <div>
                    <h3>{item.display_name}</h3>
                    <p>{item.source} / {item.account}</p>
                  </div>
                </div>

                <div className={styles.statement}>
                  <span>Último statement</span>
                  <strong>{item.last_statement_period || "Sin datos"}</strong>
                  <small>{item.statement_age_months === null ? "Antigüedad no disponible" : `${item.statement_age_months} mes(es) · tolerancia ${item.max_age_months}`}</small>
                </div>

                <div className={styles.fileStats}>
                  <div><span>Raw</span><strong>{item.raw_files}</strong></div>
                  <div><span>Mart</span><strong>{item.files_in_mart}</strong></div>
                  <div className={item.unprocessed_raw_count > 0 ? styles.pending : ""}><span>Pend.</span><strong>{item.unprocessed_raw_count}</strong></div>
                  <div><span>Ign.</span><strong>{item.ignored_raw_count || 0}</strong></div>
                </div>

                <div className={styles.state}>
                  <span className={`${styles.statusPill} ${styles[`status_${item.status}`]}`}>{STATUS_LABELS[item.status]}</span>
                  <p className={item.alert ? styles.alertReason : ""}>{item.reason}</p>
                </div>

                <div className={styles.primaryAction}>
                  <button
                    type="button"
                    disabled={Boolean(processingId) || !canEdit || item.unprocessed_raw_count === 0}
                    title={!canEdit ? "Necesitás permiso de edición." : processingId ? "Hay un procesamiento en curso." : item.unprocessed_raw_count === 0 ? "No hay archivos nuevos." : "Procesar archivos nuevos."}
                    onClick={() => void processItem(item.id)}
                  >
                    <Play size={15} />
                    {processing ? "Procesando" : item.unprocessed_raw_count === 0 ? "Al día" : `Procesar ${item.unprocessed_raw_count}`}
                  </button>
                </div>

                <div className={styles.details}>
                  <span title={item.input_path || ""}>{item.input_path || "Sin carpeta configurada"}</span>
                  <span title={item.latest_raw_file || ""}>Último raw: {item.latest_raw_file || "sin archivos"}</span>
                  {inventory && <span title={inventory}>{inventory}</span>}
                  {item.notes && <span title={item.notes}>{item.notes}</span>}
                </div>

                <div className={styles.secondaryActions}>
                  {item.portal_url && (
                    <a href={item.portal_url} target="_blank" rel="noreferrer" title="Abrir portal de la distribuidora" aria-label={`Abrir portal de ${item.display_name}`}><ExternalLink size={16} /></a>
                  )}
                  <button type="button" disabled={loading} title="Revisar directorios" aria-label="Revisar directorios" onClick={() => void loadMonitor()}><RotateCw size={16} /></button>
                  <button type="button" disabled={loading || !canEdit} title="Marcar como revisada" aria-label="Marcar como revisada" onClick={() => void updateItem(item.id, { last_manual_review_at: new Date().toISOString(), alert_silenced: false })}><Check size={16} /></button>
                  <button type="button" disabled={loading || !canEdit} title={item.alert_silenced ? "Reactivar alerta" : "Silenciar alerta"} aria-label={item.alert_silenced ? "Reactivar alerta" : "Silenciar alerta"} onClick={() => void updateItem(item.id, { alert_silenced: !item.alert_silenced })}>{item.alert_silenced ? <BellRing size={16} /> : <BellOff size={16} />}</button>
                  <button type="button" disabled={loading || !canEdit} title={item.monitoring_active ? "Dejar de monitorear" : "Activar monitoreo"} aria-label={item.monitoring_active ? "Dejar de monitorear" : "Activar monitoreo"} onClick={() => void updateItem(item.id, { monitoring_active: !item.monitoring_active, alert_silenced: item.monitoring_active ? true : false })}>{item.monitoring_active ? <MonitorOff size={16} /> : <MonitorCheck size={16} />}</button>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <section className={styles.publishBand}>
        <div className={styles.publishIcon}><CloudUpload size={22} /></div>
        <div>
          <span>Sincronización</span>
          <h2>Publicar datos analíticos</h2>
          <p>{pendingTotal > 0 ? `Quedan ${pendingTotal} archivo(s) por procesar antes de publicar.` : "Los datos locales están listos para publicar cuando termines la validación."}</p>
        </div>
        <button type="button" disabled={!canPublish} title={publishReason} onClick={() => void publish()}>
          <CloudUpload size={16} />{publishing ? "Publicando" : "Publicar"}
        </button>
        {publishJob && publishJob.status !== "completed" && (
          <div className={styles.publishStatus}><strong>Publicación en curso</strong><span>{publishJob.status} · {publishJob.stage}</span></div>
        )}
        {lastPublish && (
          <div className={styles.publishStatus}>
            <strong>Última publicación: {lastPublish.published_at}</strong>
            <span>{lastPublish.uploaded.length} archivos · {lastPublish.bucket}/{lastPublish.prefix}</span>
          </div>
        )}
      </section>
    </main>
  );
}
