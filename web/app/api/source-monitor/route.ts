import { NextRequest, NextResponse } from "next/server";
import { apiConfig } from "../_auth";

async function apiError(response: Response) {
  let detail = `Error API ${response.status}`;
  try {
    const payload = await response.clone().json();
    detail = payload.detail || payload.error || detail;
  } catch {
    const text = await response.text();
    detail = text || detail;
  }
  return NextResponse.json({ error: detail }, { status: response.status });
}

export async function GET(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const action = request.nextUrl.searchParams.get("action");
  if (action === "publish-status") {
    const jobId = request.nextUrl.searchParams.get("job_id");
    if (!jobId) {
      return NextResponse.json({ error: "Falta job_id de publicacion." }, { status: 400 });
    }
    const response = await fetch(`${config.apiUrl}/source-monitor/publish/${encodeURIComponent(jobId)}`, {
      headers: { "X-VPO-API-Key": config.apiKey },
      cache: "no-store",
    });

    if (!response.ok) return apiError(response);
    return NextResponse.json(await response.json());
  }

  const response = await fetch(`${config.apiUrl}/source-monitor`, {
    headers: { "X-VPO-API-Key": config.apiKey },
    cache: "no-store",
  });

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}

export async function PATCH(request: NextRequest) {
  const config = await apiConfig("editor");
  if ("error" in config) return config.error;

  const id = request.nextUrl.searchParams.get("id");
  if (!id) {
    return NextResponse.json({ error: "Falta id del monitor." }, { status: 400 });
  }

  const body = await request.json();
  const response = await fetch(`${config.apiUrl}/source-monitor/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "X-VPO-API-Key": config.apiKey,
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}

export async function POST(request: NextRequest) {
  const config = await apiConfig("editor");
  if ("error" in config) return config.error;

  const id = request.nextUrl.searchParams.get("id");
  const action = request.nextUrl.searchParams.get("action");
  if (action === "publish") {
    const response = await fetch(`${config.apiUrl}/source-monitor/publish`, {
      method: "POST",
      headers: { "X-VPO-API-Key": config.apiKey },
    });

    if (!response.ok) return apiError(response);
    return NextResponse.json(await response.json());
  }

  if (!id) {
    return NextResponse.json({ error: "Falta id del monitor." }, { status: 400 });
  }

  if (action !== "process") {
    return NextResponse.json({ error: "Accion no soportada." }, { status: 400 });
  }

  const response = await fetch(`${config.apiUrl}/source-monitor/${encodeURIComponent(id)}/process`, {
    method: "POST",
    headers: { "X-VPO-API-Key": config.apiKey },
  });

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}
