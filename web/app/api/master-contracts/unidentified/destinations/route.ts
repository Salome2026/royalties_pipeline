import { NextRequest, NextResponse } from "next/server";
import { apiConfig, royaltyHeaders } from "../../../_auth";

export async function GET(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const query = new URLSearchParams({ keyword: request.nextUrl.searchParams.get("keyword") || "" });
  const response = await fetch(`${config.apiUrl}/master-contract-unidentified/destinations?${query}`, {
    headers: royaltyHeaders(config), cache: "no-store",
  });
  const body = await response.json().catch(() => ({}));
  return NextResponse.json(response.ok ? body : { error: typeof body.detail === "string" ? body.detail : "No se pudo buscar el destino." }, { status: response.status });
}
