import { NextRequest, NextResponse } from "next/server";
import { apiConfig } from "../_auth";

export async function GET(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const params = new URLSearchParams();
  params.set("refresh_cache", request.nextUrl.searchParams.get("refresh") === "1" ? "true" : "false");
  params.set("preset", request.nextUrl.searchParams.get("preset") || "last_year");

  const startMonth = request.nextUrl.searchParams.get("start_month");
  const endMonth = request.nextUrl.searchParams.get("end_month");
  if (startMonth) params.set("start_month", startMonth);
  if (endMonth) params.set("end_month", endMonth);

  const response = await fetch(`${config.apiUrl}/participation/distributors?${params.toString()}`, {
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
