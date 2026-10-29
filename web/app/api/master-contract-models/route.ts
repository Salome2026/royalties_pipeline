import { NextResponse } from "next/server";
import { apiConfig, royaltyHeaders } from "../_auth";

export async function GET() {
  const config = await apiConfig();
  if ("error" in config) return config.error;
  const response = await fetch(`${config.apiUrl}/master-contract-models`, { headers: royaltyHeaders(config), cache: "no-store" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) return NextResponse.json({ error: body.detail || "No se pudieron cargar los contratos cerrados." }, { status: response.status });
  return NextResponse.json(body);
}
