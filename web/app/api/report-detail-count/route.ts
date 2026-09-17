import { NextRequest, NextResponse } from "next/server";
import { apiConfig } from "../_auth";

export const maxDuration = 120;

export async function POST(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const body = await request.json();
  const response = await fetch(`${config.apiUrl}/reports/royalty/detail-count`, {
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
    let detail = "No se pudo calcular la cantidad de filas.";
    try {
      const payload = await response.json();
      detail = payload.detail || payload.error || detail;
    } catch {
      const text = await response.text();
      detail = text || detail;
    }
    return NextResponse.json({ error: detail }, { status: response.status });
  }

  return NextResponse.json(await response.json());
}
