import { NextRequest, NextResponse } from "next/server";
import { apiConfig } from "../_auth";

function stringifyApiError(value: unknown): string {
  if (!value) return "Error desconocido.";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map((item) => stringifyApiError(item)).join(" | ");
  if (typeof value === "object") {
    const item = value as { msg?: unknown; loc?: unknown; detail?: unknown; error?: unknown };
    const msg = item.msg || item.detail || item.error;
    const loc = Array.isArray(item.loc) ? item.loc.join(".") : "";
    if (msg) return loc ? `${loc}: ${stringifyApiError(msg)}` : stringifyApiError(msg);
    return JSON.stringify(value);
  }
  return String(value);
}

async function apiError(response: Response) {
  let detail = `Error API ${response.status}`;
  try {
    const payload = await response.json();
    detail = stringifyApiError(payload.detail || payload.error || detail);
  } catch {
    const text = await response.text();
    detail = text || detail;
  }
  return NextResponse.json({ error: detail }, { status: response.status });
}

export async function GET(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const params = request.nextUrl.searchParams.toString();
  const response = await fetch(`${config.apiUrl}/catalog${params ? `?${params}` : ""}`, {
    headers: { "X-VPO-API-Key": config.apiKey },
    cache: "no-store",
  });

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}

export async function PATCH(request: NextRequest) {
  const config = await apiConfig("editor");
  if ("error" in config) return config.error;

  const body = await request.json();
  const response = await fetch(`${config.apiUrl}/catalog/status`, {
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
