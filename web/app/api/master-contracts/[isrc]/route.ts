import { NextRequest, NextResponse } from "next/server";
import { apiConfig } from "../../_auth";

type Context = { params: Promise<{ isrc: string }> };

async function forward(request: NextRequest, context: Context, method: "GET" | "PUT") {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const { isrc } = await context.params;
  const response = await fetch(`${config.apiUrl}/master-contracts/${encodeURIComponent(isrc)}`, {
    method,
    headers: {
      "X-VPO-API-Key": config.apiKey,
      "X-VPO-Username": config.user.username,
      ...(method === "PUT" ? { "Content-Type": "application/json" } : {}),
    },
    body: method === "PUT" ? JSON.stringify(await request.json()) : undefined,
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    return NextResponse.json({ error: payload.detail || `Error API ${response.status}` }, { status: response.status });
  }
  return NextResponse.json(await response.json());
}

export async function GET(request: NextRequest, context: Context) {
  return forward(request, context, "GET");
}

export async function PUT(request: NextRequest, context: Context) {
  return forward(request, context, "PUT");
}
