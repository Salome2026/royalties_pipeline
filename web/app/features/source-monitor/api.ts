import type {
  SourceMonitorData,
  SourceMonitorItem,
  SourceMonitorProcessResult,
  SourceMonitorPublishJob,
} from "./types";

async function readError(response: Response, fallback: string) {
  try {
    const payload = await response.json();
    return payload.error || fallback;
  } catch {
    return fallback;
  }
}

export async function requestSourceMonitor(): Promise<SourceMonitorData> {
  const response = await fetch("/api/source-monitor", { cache: "no-store" });
  if (!response.ok) throw new Error(await readError(response, "No se pudo cargar el control de distribuidoras."));
  return response.json();
}

export async function requestSourceMonitorUpdate(id: string, body: Partial<SourceMonitorItem>) {
  const response = await fetch(`/api/source-monitor?id=${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await readError(response, "No se pudo actualizar el control de la distribuidora."));
}

export async function requestSourceMonitorProcess(id: string): Promise<SourceMonitorProcessResult> {
  const response = await fetch(`/api/source-monitor?id=${encodeURIComponent(id)}&action=process`, { method: "POST" });
  if (!response.ok) throw new Error(await readError(response, "No se pudo procesar la distribuidora."));
  return response.json();
}

export async function requestSourceMonitorPublish(): Promise<SourceMonitorPublishJob> {
  const response = await fetch("/api/source-monitor?action=publish", { method: "POST" });
  if (!response.ok) throw new Error(await readError(response, "No se pudieron publicar los datos analíticos."));
  return response.json();
}

export async function requestSourceMonitorPublishStatus(jobId: string): Promise<SourceMonitorPublishJob> {
  const response = await fetch(`/api/source-monitor?action=publish-status&job_id=${encodeURIComponent(jobId)}`, { cache: "no-store" });
  if (!response.ok) throw new Error(await readError(response, "No se pudo consultar el estado de publicación."));
  return response.json();
}
