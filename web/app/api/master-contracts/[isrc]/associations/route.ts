import { NextRequest, NextResponse } from "next/server";
import { apiConfig, royaltyHeaders } from "../../../_auth";

export async function GET(_request: NextRequest, context: { params: Promise<{ isrc: string }> }) {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const { isrc } = await context.params;
  const response = await fetch(`${config.apiUrl}/master-contracts/${encodeURIComponent(isrc)}/associations`, {
    headers: { ...royaltyHeaders(config) },
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) return NextResponse.json({ error: payload.detail || `Error API ${response.status}` }, { status: response.status });
  return NextResponse.json(payload);
}
