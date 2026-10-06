import { NextRequest, NextResponse } from "next/server";
import { apiConfig } from "../_auth";

export async function GET() {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const response = await fetch(`${config.apiUrl}/master-contract-artists`, {
    headers: { "X-VPO-API-Key": config.apiKey, "X-VPO-Username": config.user.username },
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  return NextResponse.json(response.ok ? payload : { error: payload.detail || `Error API ${response.status}` }, { status: response.status });
}

export async function PUT(request: NextRequest) {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const response = await fetch(`${config.apiUrl}/master-contract-artists`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "X-VPO-API-Key": config.apiKey,
      "X-VPO-Username": config.user.username,
    },
    body: await request.text(),
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({}));
  return NextResponse.json(response.ok ? payload : { error: payload.detail || `Error API ${response.status}` }, { status: response.status });
}
