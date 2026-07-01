import { NextResponse } from "next/server";
import { apiConfig } from "../_auth";

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

export async function GET(request: Request) {
  const config = await apiConfig();
  if ("error" in config) return config.error;

  const url = new URL(request.url);
  const params = new URLSearchParams();
  const artist = url.searchParams.get("artist");
  if (artist) params.set("artist", artist);

  const response = await fetch(
    `${config.apiUrl}/artist-finance/summary${params.toString() ? `?${params.toString()}` : ""}`,
    {
      headers: { "X-VPO-API-Key": config.apiKey, "X-VPO-Username": config.user.username },
      cache: "no-store",
    },
  );

  if (!response.ok) return apiError(response);
  return NextResponse.json(await response.json());
}
