import { NextRequest, NextResponse } from "next/server";
import { apiConfig } from "../../_auth";

async function apiError(response: Response) {
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

export async function GET(_request: NextRequest, context: { params: Promise<{ showId: string }> }) {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const { showId } = await context.params;
  const response = await fetch(`${config.apiUrl}/booking/shows/${encodeURIComponent(showId)}`, {
    headers: { "X-VPO-API-Key": config.apiKey, "X-VPO-Username": config.user.username },
    cache: "no-store",
  });
  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}
