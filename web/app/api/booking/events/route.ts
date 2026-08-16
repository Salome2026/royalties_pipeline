import { NextRequest, NextResponse } from "next/server";
import { apiConfig } from "../../_auth";

async function apiError(response: Response) {
  let detail = `Error API ${response.status}`;
  let candidates: unknown[] = [];
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string") {
      detail = payload.detail;
    } else if (payload.detail && typeof payload.detail === "object") {
      detail = payload.detail.message || detail;
      candidates = Array.isArray(payload.detail.candidates) ? payload.detail.candidates : [];
    } else {
      detail = payload.error || detail;
    }
  } catch {
    const text = await response.text();
    detail = text || detail;
  }
  return NextResponse.json({ error: detail, candidates }, { status: response.status });
}

export async function GET(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const query = request.nextUrl.searchParams.toString();
  const response = await fetch(`${config.apiUrl}/booking/events${query ? `?${query}` : ""}`, {
    headers: {
      "X-VPO-API-Key": config.apiKey,
      "X-VPO-Username": config.user.username,
    },
    cache: "no-store",
  });
  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}

export async function POST(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const body = await request.json();
  const response = await fetch(`${config.apiUrl}/booking/events`, {
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
