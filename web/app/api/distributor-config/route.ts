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

const ALLOWED_CONFIGS = new Set([
  "distributor-account-policies",
  "statement-source-dictionary",
  "contract-cutoffs",
  "report-templates",
]);

export async function GET(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const name = request.nextUrl.searchParams.get("name");
  const endpoint = name && ALLOWED_CONFIGS.has(name)
    ? `/config/${encodeURIComponent(name)}`
    : "/config/distributor-overview";

  const response = await fetch(`${config.apiUrl}${endpoint}`, {
    headers: { "X-VPO-API-Key": config.apiKey },
    cache: "no-store",
  });

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}

export async function PATCH(request: NextRequest) {
  const config = await apiConfig("editor");
  if ("error" in config) return config.error;

  const payload = await request.json().catch(() => null);
  if (!payload) {
    return NextResponse.json({ error: "Payload invalido." }, { status: 400 });
  }

  const response = await fetch(`${config.apiUrl}/config/distributor-account-policies/personalization`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "X-VPO-API-Key": config.apiKey,
      "X-VPO-Username": config.user.username,
    },
    body: JSON.stringify(payload),
    cache: "no-store",
  });

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}
