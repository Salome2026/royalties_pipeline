import { filenameFromDisposition } from "../../lib/download";

export type StatementReportSettings = {
  minArtistTotalUsd: number;
  includeZeroTotalArtists: boolean;
  reportVersion: string;
};

export async function requestStatementReport(settings: StatementReportSettings) {
  const response = await fetch("/api/statement", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      refresh_cache: false,
      min_artist_total_usd: settings.minArtistTotalUsd,
      include_zero_total_artists: settings.includeZeroTotalArtists,
      report_version: settings.reportVersion,
    }),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({ error: "No se pudo generar el reporte por statement." }));
    throw new Error(data.error || "No se pudo generar el reporte por statement.");
  }

  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get("content-disposition"), "vpo_statement_report.xlsx"),
  };
}
