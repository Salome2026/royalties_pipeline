import { NextRequest, NextResponse } from "next/server";
import { apiConfig } from "../../../_auth";

export async function GET(_request: NextRequest, context: { params: Promise<{ isrc: string }> }) {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const { isrc } = await context.params;
  const response = await fetch(`${config.apiUrl}/master-contracts/${encodeURIComponent(isrc)}/associations`, {
    headers: { "X-VPO-API-Key": config.apiKey, "X-VPO-Username": config.user.username },
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) return NextResponse.json({ error: payload.detail || `Error API ${response.status}` }, { status: response.status });
  return NextResponse.json(payload);
}
