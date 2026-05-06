import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "vpo_web_session";

async function apiConfig() {
  const cookieStore = await cookies();
  if (cookieStore.get(SESSION_COOKIE)?.value !== "ok") {
    return { error: NextResponse.json({ error: "No autorizado." }, { status: 401 }) };
  }

  const apiUrl = process.env.VPO_API_URL;
  const apiKey = process.env.VPO_API_KEY;

  if (!apiUrl || !apiKey) {
    return { error: NextResponse.json({ error: "VPO_API_URL o VPO_API_KEY no estan configurados." }, { status: 500 }) };
  }

  return { apiUrl: apiUrl.replace(/\/$/, ""), apiKey };
}

async function apiError(response: Response) {
  let detail = `Error API ${response.status}`;
  try {
    const payload = await response.json();
    detail = payload.detail || payload.error || detail;
  } catch {
    const text = await response.text();
    detail = text || detail;
  }
  return NextResponse.json({ error: detail }, { status: response.status });
}

export async function GET() {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const response = await fetch(`${config.apiUrl}/booking/shows?limit=30`, {
    headers: { "X-VPO-API-Key": config.apiKey },
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
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}
