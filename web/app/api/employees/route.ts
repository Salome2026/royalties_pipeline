import { NextRequest, NextResponse } from "next/server";
import { apiConfig } from "../_auth";

async function apiError(response: Response) {
  let detail = `Error API ${response.status}`;
  try {
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const payload = await response.json();
      detail = payload.detail || payload.error || detail;
    } else {
      const text = await response.text();
      detail = text || detail;
    }
  } catch {
    detail = `Error API ${response.status}`;
  }
  return NextResponse.json({ error: detail }, { status: response.status });
}

export async function GET() {
  const config = await apiConfig("admin");
  if ("error" in config) return config.error;

  const response = await fetch(`${config.apiUrl}/employees?include_inactive=true`, {
    headers: { "X-VPO-API-Key": config.apiKey },
    cache: "no-store",
  });

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}

export async function POST(request: NextRequest) {
  const config = await apiConfig("editor");
  if ("error" in config) return config.error;

  const body = await request.json();
  const response = await fetch(`${config.apiUrl}/employees`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-VPO-API-Key": config.apiKey,
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}

export async function PUT(request: NextRequest) {
  const config = await apiConfig("editor");
  if ("error" in config) return config.error;

  const id = request.nextUrl.searchParams.get("id");
  if (!id) {
    return NextResponse.json({ error: "Falta id del empleado." }, { status: 400 });
  }

  const body = await request.json();
  const response = await fetch(`${config.apiUrl}/employees/${id}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "X-VPO-API-Key": config.apiKey,
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}

export async function PATCH(request: NextRequest) {
  const config = await apiConfig("admin");
  if ("error" in config) return config.error;

  const id = request.nextUrl.searchParams.get("id");
  const action = request.nextUrl.searchParams.get("action");
  if (!id || action !== "password") {
    return NextResponse.json({ error: "Falta id del empleado o accion valida." }, { status: 400 });
  }

  const body = await request.json();
  const response = await fetch(`${config.apiUrl}/employees/${id}/password`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-VPO-API-Key": config.apiKey,
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}

export async function DELETE(request: NextRequest) {
  const config = await apiConfig("editor");
  if ("error" in config) return config.error;

  const id = request.nextUrl.searchParams.get("id");
  if (!id) {
    return NextResponse.json({ error: "Falta id del empleado." }, { status: 400 });
  }

  const response = await fetch(`${config.apiUrl}/employees/${id}`, {
    method: "DELETE",
    headers: { "X-VPO-API-Key": config.apiKey },
  });

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}
