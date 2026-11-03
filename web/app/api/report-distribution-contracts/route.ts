import { NextResponse } from "next/server";
import { apiConfig, royaltyHeaders } from "../_auth";

export async function GET() {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const response = await fetch(`${config.apiUrl}/reports/royalty/distribution-contract-options`, {
    headers: royaltyHeaders(config), cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  return NextResponse.json(response.ok ? data : { error: data.detail || "No se pudieron cargar los contratos." }, { status: response.status });
}
