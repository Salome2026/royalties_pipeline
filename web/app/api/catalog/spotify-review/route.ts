import { NextRequest, NextResponse } from "next/server";
import { apiConfig, royaltyHeaders } from "../../_auth";
export const maxDuration = 60;
async function forward(request: NextRequest, method: "GET" | "POST") {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const response = await fetch(`${config.apiUrl}/catalog/spotify-review${method === "GET" ? request.nextUrl.search : ""}`, {
    method, cache: "no-store", headers: { ...royaltyHeaders(config),
      ...(method === "POST" ? { "Content-Type": "application/json" } : {}) },
    ...(method === "POST" ? { body: JSON.stringify(await request.json()) } : {}),
  });
  const body = await response.json().catch(() => ({}));
  return NextResponse.json(response.ok ? body : { error: body.detail || "No se pudo completar la operación." },
    { status: response.status, headers: response.headers.get("Retry-After") ? { "Retry-After": response.headers.get("Retry-After")! } : {} });
}
export const GET = (request: NextRequest) => forward(request, "GET");
export const POST = (request: NextRequest) => forward(request, "POST");
