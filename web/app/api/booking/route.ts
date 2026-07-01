import { NextRequest, NextResponse } from "next/server";
import { apiConfig } from "../_auth";

function stringifyApiError(value: unknown): string {
  if (!value) return "Error desconocido.";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    return value.map((item) => stringifyApiError(item)).join(" | ");
  }
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

export async function GET() {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const response = await fetch(`${config.apiUrl}/booking/shows?limit=1000`, {
    headers: { "X-VPO-API-Key": config.apiKey, "X-VPO-Username": config.user.username },
    cache: "no-store",
  });

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}

export async function POST(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const body = await request.json();
  const response = await fetch(`${config.apiUrl}/booking/shows`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-VPO-API-Key": config.apiKey,
      "X-VPO-Username": config.user.username,
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}

export async function PUT(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const id = request.nextUrl.searchParams.get("id");
  if (!id) {
    return NextResponse.json({ error: "Falta id del show." }, { status: 400 });
  }

  const body = await request.json();
  const response = await fetch(`${config.apiUrl}/booking/shows/${id}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "X-VPO-API-Key": config.apiKey,
      "X-VPO-Username": config.user.username,
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}

export async function DELETE(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const id = request.nextUrl.searchParams.get("id");
  if (!id) {
    return NextResponse.json({ error: "Falta id del show." }, { status: 400 });
  }

  const response = await fetch(`${config.apiUrl}/booking/shows/${id}`, {
    method: "DELETE",
    headers: {
      "X-VPO-API-Key": config.apiKey,
      "X-VPO-Username": config.user.username,
    },
  });

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}
