import { filenameFromDisposition } from "../../lib/download";

export type RoyaltyReportOutput = "excel" | "executive_pdf";
export type RoyaltyPeriodBasis = "transaction_month" | "statement_period";
export type RoyaltyMatchMode = "any" | "all";

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
  refresh_cache: false;
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

export async function requestRoyaltyExcelLink(payload: RoyaltyReportPayload) {
  const response = await fetch("/api/report-link", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, output: "excel" }),
  });
  if (!response.ok) throw await responseError(response, "No se pudo generar el reporte.");
  const data = await response.json();
  if (!data.url) throw new Error("La descarga no devolvió un enlace válido.");
  return String(data.url);
}

export async function requestRoyaltyExecutivePdf(payload: RoyaltyReportPayload) {
  const response = await fetch("/api/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, output: "executive_pdf" }),
  });
  if (!response.ok) throw await responseError(response, "No se pudo generar el PDF ejecutivo.");
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get("content-disposition"), "reporte_ejecutivo_regalias.pdf"),
  };
}

export async function requestRoyaltyGoogleSheet(payload: RoyaltyReportPayload) {
  const response = await fetch("/api/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, output: "google_sheet" }),
  });
  if (!response.ok) throw await responseError(response, "No se pudo crear el Google Sheet.");
  const data = await response.json();
  if (!data.url) throw new Error("Google Drive no devolvió un enlace válido.");
  return String(data.url);
}
