import { NextRequest, NextResponse } from "next/server";
import { apiConfig, royaltyHeaders } from "../../../../_auth";

type Context = { params: Promise<{ referenceId: string }> };
async function forward(request: NextRequest, context: Context, method: "GET" | "POST") {
  if (method === "POST" && request.headers.get("origin")) {
    const host = request.headers.get("x-forwarded-host")?.split(",")[0].trim() || request.headers.get("host") || request.nextUrl.host;
    const protocol = request.headers.get("x-forwarded-proto")?.split(",")[0].trim() || request.nextUrl.protocol.replace(":", "");
    try {
      const origin = new URL(request.headers.get("origin")!);
      if (origin.host !== host || origin.protocol !== `${protocol}:`) throw new Error("Origin mismatch");
    } catch { return NextResponse.json({ error: "Origen no permitido." }, { status: 403 }); }
  }
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const { referenceId } = await context.params;
  const query = method === "GET" ? "?" + new URLSearchParams({ isrc: request.nextUrl.searchParams.get("isrc") || "" }) : "";
  const response = await fetch(`${config.apiUrl}/master-contract-unidentified/${encodeURIComponent(referenceId)}/association${query}`, {
    method, headers: { ...royaltyHeaders(config), ...(method === "POST" ? { "Content-Type": "application/json" } : {}) },
    body: method === "POST" ? JSON.stringify(await request.json()) : undefined, cache: "no-store",
  });
  const body = await response.json().catch(() => ({}));
  return NextResponse.json(response.ok ? body : { error: typeof body.detail === "string" ? body.detail : "No se pudo confirmar la asociacion." }, { status: response.status });
}
export async function GET(request: NextRequest, context: Context) { return forward(request, context, "GET"); }
export async function POST(request: NextRequest, context: Context) { return forward(request, context, "POST"); }
