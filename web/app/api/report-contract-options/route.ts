import { NextResponse } from "next/server";
import { apiConfig } from "../_auth";

export async function GET() {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const response = await fetch(`${config.apiUrl}/reports/royalty/contract-options`, {
    headers: { "X-VPO-API-Key": config.apiKey, "X-VPO-Username": config.user.username },
    cache: "no-store",
  });
  const data = await response.json();
  return NextResponse.json(response.ok ? data : { error: data.detail || "No se pudieron cargar los artistas." }, { status: response.status });
}
