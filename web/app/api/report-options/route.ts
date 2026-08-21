import { NextResponse } from "next/server";
import { apiConfig } from "../_auth";

export async function GET() {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const response = await fetch(`${config.apiUrl}/reports/royalty/options`, {
    headers: { "X-VPO-API-Key": config.apiKey },
    cache: "no-store",
  });
  if (!response.ok) {
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
  return NextResponse.json(await response.json());
}
