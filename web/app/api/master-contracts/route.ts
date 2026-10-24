import { NextRequest, NextResponse } from "next/server";
import { apiConfig, royaltyHeaders } from "../_auth";

export async function GET(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const query = request.nextUrl.searchParams.toString();
  const response = await fetch(`${config.apiUrl}/master-contracts${query ? `?${query}` : ""}`, {
    headers: { ...royaltyHeaders(config) },
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    return NextResponse.json({ error: payload.detail || `Error API ${response.status}` }, { status: response.status });
  }
  return NextResponse.json(await response.json());
}
