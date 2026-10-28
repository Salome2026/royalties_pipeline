import { NextRequest, NextResponse } from "next/server";
import { apiConfig, royaltyHeaders } from "../../../_auth";

export async function GET(request: NextRequest, context: { params: Promise<{ isrc: string }> }) {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const { isrc } = await context.params;
  const url = new URL(`${config.apiUrl}/master-contracts/${encodeURIComponent(isrc)}/associations`);
  const includeIncome = request.nextUrl.searchParams.get("include_income");
  if (includeIncome !== null) url.searchParams.set("include_income", includeIncome);
  const response = await fetch(url, {
    headers: { ...royaltyHeaders(config) },
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) return NextResponse.json({ error: payload.detail || `Error API ${response.status}` }, { status: response.status });
  return NextResponse.json(payload);
}
