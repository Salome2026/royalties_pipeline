import { NextRequest, NextResponse } from "next/server";
import { apiConfig } from "../_auth";

export const maxDuration = 60;

async function backendError(response: Response, fallback: string) {
  let detail = fallback;
  try {
    const payload = await response.json();
    detail = payload.detail || payload.error || detail;
  } catch {
    const text = await response.text();
    detail = text || detail;
  }
  return NextResponse.json({ error: detail }, { status: response.status });
}

export async function POST(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const body = await request.json();
  const response = await fetch(`${config.apiUrl}/reports/jobs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-VPO-API-Key": config.apiKey,
      "X-VPO-Username": config.user.username,
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });

  if (!response.ok) {
    return backendError(response, "No se pudo iniciar el reporte.");
  }
  return NextResponse.json(await response.json(), { status: 202 });
}

export async function GET(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const jobId = request.nextUrl.searchParams.get("job_id");
  const download = request.nextUrl.searchParams.get("download") === "1";
  const limit = request.nextUrl.searchParams.get("limit") || "8";
  const endpoint = jobId
    ? `/reports/jobs/${encodeURIComponent(jobId)}${download ? "/download" : ""}`
    : `/reports/jobs?limit=${encodeURIComponent(limit)}`;
  const response = await fetch(`${config.apiUrl}${endpoint}`, {
    headers: {
      "X-VPO-API-Key": config.apiKey,
      "X-VPO-Username": config.user.username,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    return backendError(response, download ? "No se pudo descargar el reporte." : "No se pudo consultar el reporte.");
  }

  if (!download) return NextResponse.json(await response.json());

  const buffer = await response.arrayBuffer();
  return new NextResponse(buffer, {
    status: 200,
    headers: {
      "Content-Type": response.headers.get("content-type") || "application/octet-stream",
      "Content-Disposition": response.headers.get("content-disposition") || "attachment",
    },
  });
}
