import { NextRequest, NextResponse } from "next/server";
import { apiConfig, royaltyHeaders } from "../_auth";

export async function forwardExplorer(request: NextRequest, endpoint: string) {
  const config = await apiConfig("viewer", true);
  if ("error" in config) return config.error;
  const response = await fetch(`${config.apiUrl}${endpoint}?${request.nextUrl.searchParams}`, {
    headers: royaltyHeaders(config), cache: "no-store",
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) return NextResponse.json({ error: typeof body.detail === "string" ? body.detail : "No se pudo consultar la vista contractual." }, { status: response.status });
  return NextResponse.json(body);
}
