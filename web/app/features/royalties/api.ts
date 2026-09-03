export type RoyaltyReportOutput = "excel" | "executive_pdf";
export type RoyaltyReportJobOutput = RoyaltyReportOutput | "google_sheet";
export type RoyaltyPeriodBasis = "transaction_month" | "statement_period";
export type RoyaltyMatchMode = "any" | "all";
export type RoyaltyReportJobStatus = "queued" | "running" | "completed" | "failed";

export type RoyaltyReportSourceAccount = {
  source: string;
  account: string;
  display_name: string;
};

export type RoyaltyReportOptions = {
  sources: string[];
  source_accounts: RoyaltyReportSourceAccount[];
};

export type RoyaltyReportPayload = {
  keywords: string[];
  start_month: string | null;
  end_month: string | null;
  period_basis: RoyaltyPeriodBasis;
  mode: RoyaltyMatchMode;
  raw_limit: number;
  source: string | null;
  account: string | null;
};

export type RoyaltyReportJob = {
  id: number;
  report_key: string;
  output_format: RoyaltyReportJobOutput;
  requested_by: string;
  params: RoyaltyReportPayload;
  status: RoyaltyReportJobStatus;
  progress_stage: string;
  result_filename: string | null;
  result_content_type: string | null;
  result_url: string | null;
  error_message: string | null;
  attempt_count: number;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string | null;
  expires_at: string | null;
  download_ready: boolean;
};

async function responseError(response: Response, fallback: string) {
  const data = await response.json().catch(() => ({ error: fallback }));
  return new Error(data.error || fallback);
}

export async function requestRoyaltyReportOptions(): Promise<RoyaltyReportOptions> {
  const response = await fetch("/api/report-options", { cache: "no-store" });
  if (!response.ok) throw await responseError(response, "No se pudieron cargar las distribuidoras.");
  return response.json();
}

export async function createRoyaltyReportJob(payload: RoyaltyReportPayload, output: RoyaltyReportJobOutput) {
  const response = await fetch("/api/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, output }),
  });
  if (!response.ok) throw await responseError(response, "No se pudo iniciar el reporte.");
  const data = await response.json();
  if (!data.item?.id) throw new Error("El servidor no devolvió un trabajo válido.");
  return data.item as RoyaltyReportJob;
}

export async function requestRoyaltyReportJob(jobId: number) {
  const response = await fetch(`/api/report?job_id=${encodeURIComponent(jobId)}`, { cache: "no-store" });
  if (!response.ok) throw await responseError(response, "No se pudo consultar el reporte.");
  const data = await response.json();
  return data.item as RoyaltyReportJob;
}

export async function requestRecentRoyaltyReportJobs(limit = 8) {
  const response = await fetch(`/api/report?limit=${encodeURIComponent(limit)}`, { cache: "no-store" });
  if (!response.ok) throw await responseError(response, "No se pudieron consultar los reportes recientes.");
  const data = await response.json();
  return (data.items || []) as RoyaltyReportJob[];
}

export function royaltyReportJobDownloadUrl(jobId: number) {
  return `/api/report?job_id=${encodeURIComponent(jobId)}&download=1`;
}
